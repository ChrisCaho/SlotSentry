"""SlotSentry SlotManager — central orchestrator for slot state and lock pushes.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Owns all slot state, coordinates disk persistence via SlotSentryStore,
delegates lock operations to LockCommitMachine instances, and fires HA
events so sensor entities can reactively update.

Revision: 2.0 — a13 overhaul: granular dirty marking, disabled-slot rules,
                 session-only error/failure counters, STATE_FAILED recognition.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from .commit_machine import LockCommitMachine
from .const import (
    ADDRESSING_NAME,
    CODE_LENGTH_DUAL,
    CODE_LENGTH_SINGLE,
    CONF_CODE_LENGTH_1,
    CONF_CODE_LENGTH_2,
    CONF_CODE_LENGTH_MODE,
    CONF_PER_LOCK_CODE_LENGTH,
    CONF_PER_LOCK_SLOT_COUNT,
    CONF_SECURE_MODE,
    CONF_SLOT_COUNT,
    EVENT_PUSH_STATUS_CHANGED,
    INTER_LOCK_DELAY,
    LATENCY_LOCK_MULTIPLIER,
    STATE_FAILED,
    STATE_RETRY,
    SYNC_OUT_OF_SYNC,
    SYNC_SYNCED,
    SYNC_UNCERTAIN,
)
from .latency import LatencyProfile, LatencyProfiler
from .lock_backend import LockBackend
from .storage import SlotData, SlotSentryStore, hash_code

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _code_in_range(code: str, length_range: tuple[int, int]) -> bool:
    """Return True if *code* length falls within the inclusive range."""
    min_len, max_len = length_range
    return min_len <= len(code) <= max_len


# ---------------------------------------------------------------------------
# SlotManager
# ---------------------------------------------------------------------------


class SlotManager:
    """Central orchestrator for SlotSentry slot state and lock synchronisation."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: SlotSentryStore,
        backends: dict[str, LockBackend],
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._store = store
        self._backends = backends

        self._machines: dict[str, LockCommitMachine] = {}
        self._active_push_lock: str | None = None
        self._profiler = LatencyProfiler(backends)
        self._latency_profiles: dict[str, LatencyProfile] = {}

        # Tracked push tasks (for cancel support).
        self._push_tasks: list[asyncio.Task] = []

        # Session-only counters (reset on HA restart).
        self._error_counts: dict[str, int] = {}    # lock_entity → count
        self._failure_counts: dict[str, int] = {}   # lock_entity → count

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_secure_mode(self) -> bool:
        return bool(self._entry.data.get(CONF_SECURE_MODE, False))

    @property
    def slot_count(self) -> int:
        return int(self._entry.data.get(CONF_SLOT_COUNT, 0))

    @property
    def code_length_mode(self) -> str:
        return str(self._entry.data.get(CONF_CODE_LENGTH_MODE, CODE_LENGTH_DUAL))

    @property
    def code_length_1(self) -> int | None:
        val = self._entry.data.get(CONF_CODE_LENGTH_1)
        return int(val) if val is not None else None

    @property
    def code_length_2(self) -> int | None:
        val = self._entry.data.get(CONF_CODE_LENGTH_2)
        return int(val) if val is not None else None

    @property
    def per_lock_code_length(self) -> dict[str, int]:
        return dict(self._entry.data.get(CONF_PER_LOCK_CODE_LENGTH, {}))

    @property
    def per_lock_slot_count(self) -> dict[str, int]:
        return dict(self._entry.data.get(CONF_PER_LOCK_SLOT_COUNT, {}))

    def get_lock_total_slots(self, lock_entity: str) -> int:
        """Return the total physical slot count for a lock (per-lock or fallback)."""
        return self.per_lock_slot_count.get(lock_entity, self.slot_count)

    @property
    def active_push_lock(self) -> str | None:
        return self._active_push_lock

    def has_lock(self, lock_entity: str) -> bool:
        return lock_entity in self._machines

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load storage from disk and initialise lock commit entries."""
        await self._store.async_load()

        existing_slots = self._store.get_slots()
        for n in range(1, self.slot_count + 1):
            if n not in existing_slots:
                self._store.set_slot(SlotData.empty(n))

        self._apply_seed_data()

        for lock_entity in self._backends:
            self._store.initialise_lock_commits(lock_entity, self.slot_count)

        # On fresh setup, mark empty+disabled slots as synced.
        existing_slots = self._store.get_slots()
        for lock_entity in self._backends:
            for sn, slot in existing_slots.items():
                if not slot.enabled and slot.is_empty():
                    commit = self._store.get_lock_commit(lock_entity, sn)
                    if commit.state != SYNC_SYNCED:
                        commit.state = SYNC_SYNCED
                        self._store.set_lock_commit(lock_entity, commit)

        # Auto-clear stale FAILED/RETRY states from previous sessions.
        # On restart, these should revert to pending (out_of_sync with no
        # pushed_at) so next push retries them cleanly.
        for lock_entity in self._backends:
            commits = self._store.get_all_lock_commits(lock_entity)
            for sn, commit in commits.items():
                if commit.state in (STATE_FAILED, STATE_RETRY):
                    commit.state = SYNC_OUT_OF_SYNC
                    self._store.set_lock_commit(lock_entity, commit)

        # Load latency profiles from storage.
        raw_profiles = self._store.get_all_latency_profiles()
        for eid, raw in raw_profiles.items():
            self._latency_profiles[eid] = LatencyProfile.from_dict(eid, raw)

        for lock_entity, backend in self._backends.items():
            typical = None
            if lock_entity in self._latency_profiles:
                typical = self._latency_profiles[lock_entity].typical_latency
            self._machines[lock_entity] = LockCommitMachine(
                self._hass, backend, self._store, lock_entity,
                typical_latency=typical,
            )
            # Apply saved latency to backend timeout.
            if typical is not None and hasattr(backend, "update_timeout"):
                backend.update_timeout(typical)
            self._error_counts[lock_entity] = 0
            self._failure_counts[lock_entity] = 0

        await self._async_save()
        _LOGGER.debug(
            "SlotManager loaded: %d slots, %d backends",
            self.slot_count, len(self._backends),
        )

    async def _async_save(self) -> None:
        if self.is_secure_mode:
            session = self._entry.runtime_data.secure_session
            key = session.encryption_key
            if key is not None:
                await self._store.async_save_encrypted(key)
                return
        await self._store.async_save()

    def decrypt_codes_in_memory(self, key: bytes) -> None:
        if self._store.is_encrypted:
            self._store.decrypt_codes(key)
            _LOGGER.info("In-memory codes decrypted for secure session")

    def encrypt_codes_in_memory(self, key: bytes) -> None:
        self._store.encrypt_codes(key)
        _LOGGER.info("In-memory codes re-encrypted (session locked)")

    async def async_shutdown(self) -> None:
        for lock_entity, machine in self._machines.items():
            _LOGGER.debug("Cancelling commit machine for %s", lock_entity)
            await machine.async_cancel()

    # ------------------------------------------------------------------
    # Slot CRUD
    # ------------------------------------------------------------------

    async def async_get_slots(self) -> dict[int, SlotData]:
        return self._store.get_slots()

    async def async_set_slot(
        self,
        slot_number: int,
        label: str,
        code_1: str,
        code_2: str,
        enabled: bool,
    ) -> None:
        """Create or update a slot with granular dirty marking."""
        # -- Label uniqueness --
        if label.strip():
            existing_slots = self._store.get_slots()
            label_lower = label.strip().lower()
            for sn, slot in existing_slots.items():
                if sn == slot_number:
                    continue
                if slot.label.strip().lower() == label_lower:
                    raise ValueError(
                        f"Label '{label}' is already used by slot {sn} "
                        f"(case-insensitive match)"
                    )

        # -- Code length validation --
        for lock_entity, backend in self._backends.items():
            code_range = backend.supported_code_lengths
            if code_1 and not _code_in_range(code_1, code_range):
                raise ValueError(
                    f"Code 1 length {len(code_1)} is outside the "
                    f"supported range {code_range} for lock {lock_entity}"
                )
            if code_2 and not _code_in_range(code_2, code_range):
                raise ValueError(
                    f"Code 2 length {len(code_2)} is outside the "
                    f"supported range {code_range} for lock {lock_entity}"
                )

        # -- Read old slot for change detection --
        old_slot = self._store.get_slot(slot_number)

        # -- Persist slot data --
        slot = SlotData(
            slot_number=slot_number,
            label=label,
            code_1=code_1,
            code_2=code_2,
            enabled=enabled,
            created_at="",
            updated_at="",
        )
        self._store.set_slot(slot)

        # -- Granular dirty marking --
        self._mark_dirty_commits_granular(
            slot_number, old_slot, label, code_1, code_2, enabled,
        )
        await self._async_save()

        self._fire_push_status_event()
        _LOGGER.info("Slot %d updated (label=%r, enabled=%s)", slot_number, label, enabled)

    async def async_delete_slot(self, slot_number: int) -> None:
        """Clear a slot. If it was enabled with data, mark all locks dirty."""
        old_slot = self._store.get_slot(slot_number)
        was_enabled_with_data = (
            old_slot is not None
            and old_slot.enabled
            and not old_slot.is_empty()
        )

        self._store.delete_slot(slot_number)

        # Only mark locks dirty if there was actually something to clear.
        if was_enabled_with_data:
            for lock_entity in self._backends:
                commit = self._store.get_lock_commit(lock_entity, slot_number)
                commit.state = SYNC_OUT_OF_SYNC
                self._store.set_lock_commit(lock_entity, commit)

        await self._async_save()
        self._fire_push_status_event()
        _LOGGER.info("Slot %d deleted", slot_number)

    # ------------------------------------------------------------------
    # Push engine
    # ------------------------------------------------------------------

    async def async_push_all(self) -> None:
        """Push dirty slots to all configured locks sequentially.

        First-ever push per lock triggers full reconciliation (force + unmanaged clearing).
        Subsequent pushes are incremental (only dirty slots).
        """
        if not self._machines:
            return

        mode = self.code_length_mode
        cl1 = self.code_length_1
        cl2 = self.code_length_2
        plcl = self.per_lock_code_length

        # Compute latency-based inter-lock delay.
        latencies = [
            p.typical_latency
            for p in self._latency_profiles.values()
            if p.typical_latency is not None
        ]
        if latencies:
            inter_lock = max(latencies) * LATENCY_LOCK_MULTIPLIER
        else:
            inter_lock = INTER_LOCK_DELAY

        lock_count = 0
        for lock_entity, machine in self._machines.items():
            # Skip locks that are already being pushed (e.g., a Push Lock
            # is running on this lock from a separate request).
            if machine.is_busy:
                _LOGGER.info(
                    "SlotManager: skipping %s — already busy",
                    lock_entity,
                )
                continue

            # Inter-lock delay — give the Z-Wave mesh breathing room
            # between finishing one lock and starting the next.
            if lock_count > 0:
                _LOGGER.info(
                    "SlotManager: inter-lock delay %.1fs before %s",
                    inter_lock,
                    lock_entity,
                )
                await asyncio.sleep(inter_lock)

            self._active_push_lock = lock_entity
            self._fire_push_status_event()

            # First-push detection: if this lock has never had a full push,
            # do a full reconciliation (force + unmanaged slot clearing).
            is_first_push = not self._store.is_initial_push_done(lock_entity)
            force = is_first_push
            total_lock_slots = self.get_lock_total_slots(lock_entity) if is_first_push else None

            if force:
                machine.reset_attempt_counters()
                for sn in range(1, self.slot_count + 1):
                    commit = self._store.get_lock_commit(lock_entity, sn)
                    commit.state = SYNC_OUT_OF_SYNC
                    self._store.set_lock_commit(lock_entity, commit)
                _LOGGER.info(
                    "First push for %s: full reconciliation (total_lock_slots=%s)",
                    lock_entity, total_lock_slots,
                )

            slots = self._store.get_slots()
            lock_cl = plcl.get(lock_entity)
            result = await machine.async_push_dirty_slots(
                slots, mode, cl1, cl2, lock_cl, force=force,
                total_lock_slots=total_lock_slots,
            )

            # Accumulate error/failure counters from the result.
            if result is not None:
                self._error_counts[lock_entity] = (
                    self._error_counts.get(lock_entity, 0) + len(result.errors)
                )
                self._failure_counts[lock_entity] = (
                    self._failure_counts.get(lock_entity, 0) + result.failed
                )

                # Mark initial push done on success (even if some slots failed).
                if is_first_push:
                    self._store.set_initial_push_done(lock_entity, True)
                    await self._async_save()
                    _LOGGER.info("Initial push completed for %s", lock_entity)

            self._fire_push_status_event()
            lock_count += 1

        self._active_push_lock = None
        self._fire_push_status_event()

    async def async_push_lock(self, lock_entity: str) -> None:
        """Push Lock — full reconciliation of ALL slots on a single lock.

        Always force-pushes all managed slots and clears unmanaged slots
        beyond the managed range (3-phase push).

        Raises:
            RuntimeError: If the lock is already being pushed.
        """
        machine = self._machines.get(lock_entity)
        if machine is None:
            raise KeyError(f"No backend configured for lock '{lock_entity}'")

        if machine.is_busy:
            raise RuntimeError(
                f"Lock '{lock_entity}' is already being pushed — "
                f"cancel the current push first or wait for it to finish"
            )

        # Mark every slot dirty for this lock so the push loop processes all.
        machine.reset_attempt_counters()
        for sn in range(1, self.slot_count + 1):
            commit = self._store.get_lock_commit(lock_entity, sn)
            commit.state = SYNC_OUT_OF_SYNC
            self._store.set_lock_commit(lock_entity, commit)

        total_lock_slots = self.get_lock_total_slots(lock_entity)
        _LOGGER.info(
            "Push Lock: full reconciliation for %s (managed=%d, total=%d)",
            lock_entity, self.slot_count, total_lock_slots,
        )

        self._active_push_lock = lock_entity
        self._fire_push_status_event()

        slots = self._store.get_slots()
        lock_cl = self.per_lock_code_length.get(lock_entity)
        result = await machine.async_push_dirty_slots(
            slots, self.code_length_mode, self.code_length_1, self.code_length_2,
            lock_cl, force=True, total_lock_slots=total_lock_slots,
        )

        if result is not None:
            self._error_counts[lock_entity] = (
                self._error_counts.get(lock_entity, 0) + len(result.errors)
            )
            self._failure_counts[lock_entity] = (
                self._failure_counts.get(lock_entity, 0) + result.failed
            )

            # Push Lock always counts as initial push done.
            if not self._store.is_initial_push_done(lock_entity):
                self._store.set_initial_push_done(lock_entity, True)
                await self._async_save()

        self._active_push_lock = None
        self._fire_push_status_event()

    def register_push_task(self, task: asyncio.Task) -> None:
        """Track a fire-and-forget push task so cancel can find it."""
        self._push_tasks.append(task)
        # Auto-clean completed tasks.
        self._push_tasks = [t for t in self._push_tasks if not t.done()]

    async def async_cancel_push(self) -> None:
        """Cancel all running push tasks across all locks."""
        _LOGGER.info("SlotManager: cancelling all push tasks")

        # Cancel tracked fire-and-forget tasks (push_all / push_lock).
        for task in self._push_tasks:
            if not task.done():
                task.cancel()
        for task in self._push_tasks:
            if not task.done():
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._push_tasks.clear()

        # Also cancel any tasks stored on the commit machines themselves.
        for lock_entity, machine in self._machines.items():
            await machine.async_cancel()

        self._active_push_lock = None
        self._fire_push_status_event()

    def clear_error_counters(self) -> None:
        """Reset session-only error/failure counters and allow failed slots to retry.

        Resets:
          - Session-only error_count / failure_count accumulators
          - Per-slot attempt counters in each commit machine (so retries restart)
          - STATE_FAILED commit states → SYNC_OUT_OF_SYNC (so next push retries them)
        """
        for lock_entity in self._error_counts:
            self._error_counts[lock_entity] = 0
            self._failure_counts[lock_entity] = 0

        for lock_entity, machine in self._machines.items():
            machine.reset_attempt_counters()
            # Reset FAILED commits back to out_of_sync so next push retries.
            # Keep pushed_at/code_hash intact — they record what was attempted.
            commits = self._store.get_all_lock_commits(lock_entity)
            for sn, commit in commits.items():
                if commit.state in (STATE_FAILED, STATE_RETRY):
                    commit.state = SYNC_OUT_OF_SYNC
                    self._store.set_lock_commit(lock_entity, commit)

        self._fire_push_status_event()
        _LOGGER.info("Error/failure counters and failed states cleared for all locks")

    # ------------------------------------------------------------------
    # Latency profiling
    # ------------------------------------------------------------------

    async def async_profile_latency(self) -> dict[str, LatencyProfile]:
        """Run latency profiling on all locks and update pacing.

        Called as a background task when the panel opens. Updates stored
        profiles and pushes new typical_latency values into machines.
        """
        self._latency_profiles = await self._profiler.async_profile_all(
            self._latency_profiles,
        )

        # Persist and push updated latencies into commit machines and backends.
        for eid, profile in self._latency_profiles.items():
            self._store.set_latency_profile(eid, profile.to_dict())
            if profile.typical_latency is not None:
                machine = self._machines.get(eid)
                if machine:
                    machine.update_typical_latency(profile.typical_latency)
                backend = self._backends.get(eid)
                if backend and hasattr(backend, "update_timeout"):
                    backend.update_timeout(profile.typical_latency)

        await self._async_save()
        _LOGGER.info(
            "Latency profiling complete: %s",
            {eid: f"{p.typical_latency:.3f}s" for eid, p in self._latency_profiles.items()
             if p.typical_latency is not None},
        )
        return self._latency_profiles

    @property
    def latency_profiles(self) -> dict[str, LatencyProfile]:
        """Current latency profiles for all locks."""
        return dict(self._latency_profiles)

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_push_status(self) -> dict[str, Any]:
        """Return a per-lock summary of sync status.

        Recognises SYNC_SYNCED, SYNC_OUT_OF_SYNC, STATE_FAILED, STATE_RETRY,
        and SYNC_UNCERTAIN commit states.
        """
        result: dict[str, Any] = {}
        existing_slots = self._store.get_slots()

        for lock_entity in self._backends:
            commits = self._store.get_all_lock_commits(lock_entity)
            synced = 0
            failed = 0
            pending = 0
            uncertain = 0
            dirty: list[int] = []
            failed_slots: list[int] = []

            for sn, commit in commits.items():
                slot = existing_slots.get(sn)

                # Disabled slots are invisible to locks.
                if slot and not slot.enabled:
                    synced += 1
                    continue

                # Empty slots that were never pushed — nothing to clear.
                if slot and slot.is_empty() and commit.pushed_at is None:
                    synced += 1
                    continue

                if commit.state == SYNC_SYNCED:
                    synced += 1
                elif commit.state in (STATE_FAILED, STATE_RETRY):
                    # STATE_FAILED = all retries exhausted.
                    failed += 1
                    dirty.append(sn)
                    failed_slots.append(sn)
                elif commit.state == SYNC_OUT_OF_SYNC:
                    pending += 1
                    dirty.append(sn)
                elif commit.state == SYNC_UNCERTAIN:
                    uncertain += 1
                    dirty.append(sn)

            if failed > 0:
                overall = SYNC_OUT_OF_SYNC
            elif pending > 0:
                overall = "pending"
            elif uncertain > 0:
                overall = SYNC_UNCERTAIN
            else:
                overall = SYNC_SYNCED

            # Get live operation from commit machine.
            machine = self._machines.get(lock_entity)
            current_op = None
            current_slot = None
            if machine is not None:
                ms = machine.get_status()
                current_op = ms.current_operation
                current_slot = ms.current_slot

            result[lock_entity] = {
                "state": overall,
                "synced_count": synced,
                "failed_count": failed,
                "pending_count": pending,
                "uncertain_count": uncertain,
                "dirty_slots": sorted(dirty),
                "failed_slots": sorted(failed_slots),
                "error_count": self._error_counts.get(lock_entity, 0),
                "failure_count": self._failure_counts.get(lock_entity, 0),
                "current_operation": current_op,
                "current_slot": current_slot,
            }

        return result

    def get_lock_commit_state(self, lock_entity: str, slot_number: int) -> Any:
        return self._store.get_lock_commit(lock_entity, slot_number)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_seed_data(self) -> None:
        """Populate storage slots from seed data in the config entry."""
        seed_slots: list[dict] = self._entry.data.get("seed_slots", [])
        if not seed_slots:
            return

        _LOGGER.info("Applying %d seed slot(s) from config flow", len(seed_slots))

        for seed in seed_slots:
            sn = seed.get("slot_number", 0)
            if sn < 1 or sn > self.slot_count:
                continue
            slot = SlotData(
                slot_number=sn,
                label=seed.get("label", ""),
                code_1=seed.get("code_1", seed.get("short_code", "")),
                code_2=seed.get("code_2", seed.get("long_code", "")),
                enabled=seed.get("enabled", True),
                created_at="",
                updated_at="",
            )
            self._store.set_slot(slot)

        new_data = dict(self._entry.data)
        new_data.pop("seed_slots", None)
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)
        _LOGGER.info("Seed data applied and removed from config entry")

    def _select_code_for_backend(
        self, slot: SlotData, backend: LockBackend, lock_entity: str,
    ) -> str | None:
        """Choose which code to push to a backend based on per-lock code length."""
        code_range = backend.supported_code_lengths

        if self.code_length_mode == CODE_LENGTH_SINGLE:
            code = slot.code_1 or slot.code_2
            if code and _code_in_range(code, code_range):
                return code
            return None

        lock_cl = self.per_lock_code_length.get(lock_entity)
        cl1 = self.code_length_1
        cl2 = self.code_length_2

        if lock_cl is not None and cl1 is not None and lock_cl == cl1:
            if slot.code_1 and _code_in_range(slot.code_1, code_range):
                return slot.code_1
        elif lock_cl is not None and cl2 is not None and lock_cl == cl2:
            if slot.code_2 and _code_in_range(slot.code_2, code_range):
                return slot.code_2
        else:
            if slot.code_1 and _code_in_range(slot.code_1, code_range):
                return slot.code_1
            if slot.code_2 and _code_in_range(slot.code_2, code_range):
                return slot.code_2

        return None

    def _lock_uses_code_field(self, lock_entity: str, code_field: str) -> bool:
        """Return True if *lock_entity* uses the given code field ('code_1' or 'code_2').

        In single mode, all locks use code_1.
        In dual mode, check per_lock_code_length mapping.
        """
        if self.code_length_mode == CODE_LENGTH_SINGLE:
            return code_field == "code_1"

        lock_cl = self.per_lock_code_length.get(lock_entity)
        cl1 = self.code_length_1
        cl2 = self.code_length_2

        if code_field == "code_1":
            return lock_cl is not None and cl1 is not None and lock_cl == cl1
        if code_field == "code_2":
            return lock_cl is not None and cl2 is not None and lock_cl == cl2
        return False

    def _mark_dirty_commits_granular(
        self,
        slot_number: int,
        old_slot: SlotData | None,
        label: str,
        code_1: str,
        code_2: str,
        enabled: bool,
    ) -> None:
        """Granular dirty marking based on what actually changed.

        Rules:
          - If slot is disabled (enabled=False) and stays disabled: never dirty.
          - ON→OFF toggle: all locks dirty (need to clear codes from locks).
          - OFF→ON toggle: all locks dirty (need to push codes to locks).
          - Code 1 change: only locks that use code_1 get dirty.
          - Code 2 change: only locks that use code_2 get dirty.
          - Label change: only name-based-addressing locks get dirty.
          - If newly enabled is False, skip (disabled slots don't dirty locks).
        """
        old_enabled = old_slot.enabled if old_slot else False
        old_label = old_slot.label if old_slot else ""
        old_code_1 = old_slot.code_1 if old_slot else ""
        old_code_2 = old_slot.code_2 if old_slot else ""

        enabled_changed = old_enabled != enabled
        code_1_changed = old_code_1 != code_1
        code_2_changed = old_code_2 != code_2
        label_changed = old_label != label

        # If slot was disabled and stays disabled, never mark locks dirty.
        if not old_enabled and not enabled:
            _LOGGER.info(
                "Slot %d: disabled→disabled, no dirty marking (c1=%s→%s, c2=%s→%s)",
                slot_number, bool(old_code_1), bool(code_1), bool(old_code_2), bool(code_2),
            )
            return

        # Enabled toggle: all locks dirty.
        if enabled_changed:
            for lock_entity in self._backends:
                commit = self._store.get_lock_commit(lock_entity, slot_number)
                commit.state = SYNC_OUT_OF_SYNC
                self._store.set_lock_commit(lock_entity, commit)
                _LOGGER.info(
                    "Slot %d: enabled toggled (%s→%s) — %s marked out_of_sync",
                    slot_number, old_enabled, enabled, lock_entity,
                )
            return

        # Slot is enabled. Check field-level changes.
        if not enabled:
            return

        for lock_entity, backend in self._backends.items():
            should_dirty = False
            reason = ""

            if code_1_changed and self._lock_uses_code_field(lock_entity, "code_1"):
                should_dirty = True
                reason = "code_1 changed"
            elif code_2_changed and self._lock_uses_code_field(lock_entity, "code_2"):
                should_dirty = True
                reason = "code_2 changed"

            if label_changed and backend.addressing_mode == ADDRESSING_NAME:
                should_dirty = True
                reason = (reason + " + " if reason else "") + "label changed"

            if should_dirty:
                commit = self._store.get_lock_commit(lock_entity, slot_number)
                commit.state = SYNC_OUT_OF_SYNC
                self._store.set_lock_commit(lock_entity, commit)
                _LOGGER.info(
                    "Slot %d: %s — %s marked out_of_sync",
                    slot_number, reason, lock_entity,
                )

        if not any([enabled_changed, code_1_changed, code_2_changed, label_changed]):
            _LOGGER.info(
                "Slot %d: no field changes detected — no locks marked dirty",
                slot_number,
            )

    def _fire_push_status_event(self) -> None:
        self._hass.bus.async_fire(
            EVENT_PUSH_STATUS_CHANGED,
            {"entry_id": self._entry.entry_id},
        )
