"""SlotSentry SlotManager — central orchestrator for slot state and lock pushes.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Owns all slot state, coordinates disk persistence via SlotSentryStore,
delegates lock operations to LockCommitMachine instances, and fires HA
events so sensor entities can reactively update.

Revision: 1.6 — per-lock code length, code_1/code_2 field names.
"""

from __future__ import annotations

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
    CONF_SECURE_MODE,
    CONF_SLOT_COUNT,
    EVENT_PUSH_STATUS_CHANGED,
    SYNC_OUT_OF_SYNC,
    SYNC_SYNCED,
    SYNC_UNCERTAIN,
)
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
    """Central orchestrator for SlotSentry slot state and lock synchronisation.

    Responsibilities:
      - Load / save slot data via ``SlotSentryStore``.
      - Enforce business rules (label uniqueness, code length validation).
      - Delegate pushes to ``LockCommitMachine`` instances (one per lock).
      - Track per-lock per-slot commit state (synced / out_of_sync / uncertain).
      - Fire ``EVENT_PUSH_STATUS_CHANGED`` so HA entities react to changes.

    One ``SlotManager`` instance exists per config entry, held in
    ``entry.runtime_data.slot_manager``.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: SlotSentryStore,
        backends: dict[str, LockBackend],
    ) -> None:
        """Initialise the manager.

        Args:
            hass:     The Home Assistant instance.
            entry:    The config entry that owns this manager.
            store:    The storage layer (already constructed, not yet loaded).
            backends: Mapping of lock entity_id to its LockBackend instance.
                      All backends must have been initialised (``async_init``
                      called) before they are passed here.
        """
        self._hass = hass
        self._entry = entry
        self._store = store
        self._backends = backends

        # One commit machine per lock — created during async_load().
        self._machines: dict[str, LockCommitMachine] = {}

        # Track which lock is currently being pushed (for panel spinner).
        self._active_push_lock: str | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_secure_mode(self) -> bool:
        """True if secure mode is enabled on this entry."""
        return bool(self._entry.data.get(CONF_SECURE_MODE, False))

    @property
    def slot_count(self) -> int:
        """Number of configured slots (from config entry data)."""
        return int(self._entry.data.get(CONF_SLOT_COUNT, 0))

    @property
    def code_length_mode(self) -> str:
        """Return 'single' or 'dual' from config entry data."""
        return str(
            self._entry.data.get(CONF_CODE_LENGTH_MODE, CODE_LENGTH_DUAL)
        )

    @property
    def code_length_1(self) -> int | None:
        """Configured primary code length (shorter in dual mode)."""
        val = self._entry.data.get(CONF_CODE_LENGTH_1)
        return int(val) if val is not None else None

    @property
    def code_length_2(self) -> int | None:
        """Configured secondary code length (longer in dual mode), or None if single."""
        val = self._entry.data.get(CONF_CODE_LENGTH_2)
        return int(val) if val is not None else None

    @property
    def per_lock_code_length(self) -> dict[str, int]:
        """Mapping of lock entity_id → code length assigned to that lock."""
        return dict(self._entry.data.get(CONF_PER_LOCK_CODE_LENGTH, {}))

    @property
    def active_push_lock(self) -> str | None:
        """Entity ID of the lock currently being pushed, or None."""
        return self._active_push_lock

    def has_lock(self, lock_entity: str) -> bool:
        """Return True if *lock_entity* is a configured backend."""
        return lock_entity in self._machines

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load storage from disk and initialise lock commit entries.

        Must be called once during ``async_setup_entry`` before any other
        method is used.
        """
        await self._store.async_load()

        # Ensure all slot numbers 1…slot_count exist in storage.
        # On first run the storage file has zero slots; this populates
        # empty SlotData entries so the frontend can display editable rows.
        existing_slots = self._store.get_slots()
        for n in range(1, self.slot_count + 1):
            if n not in existing_slots:
                self._store.set_slot(SlotData.empty(n))

        # Apply seed data from config flow (one-time, first setup only).
        self._apply_seed_data()

        # Ensure every configured backend has commit entries for all slots.
        for lock_entity in self._backends:
            self._store.initialise_lock_commits(lock_entity, self.slot_count)

        # On fresh setup, mark empty+disabled slots as synced — there is
        # nothing to push so they should not appear as errors or pending.
        existing_slots = self._store.get_slots()
        for lock_entity in self._backends:
            for sn, slot in existing_slots.items():
                if not slot.enabled and slot.is_empty():
                    commit = self._store.get_lock_commit(lock_entity, sn)
                    if commit.state != SYNC_SYNCED:
                        commit.state = SYNC_SYNCED
                        self._store.set_lock_commit(lock_entity, commit)

        # Create one LockCommitMachine per lock backend.
        for lock_entity, backend in self._backends.items():
            self._machines[lock_entity] = LockCommitMachine(
                self._hass, backend, self._store, lock_entity,
            )

        await self._async_save()
        _LOGGER.debug(
            "SlotManager loaded: %d slots, %d backends, %d commit machines",
            self.slot_count,
            len(self._backends),
            len(self._machines),
        )

    async def _async_save(self) -> None:
        """Save storage, using encrypted write if secure mode is active and unlocked."""
        if self.is_secure_mode:
            session = self._entry.runtime_data.secure_session
            key = session.encryption_key
            if key is not None:
                await self._store.async_save_encrypted(key)
                return
            # If locked, codes in memory are still encrypted from load.
            # Save as-is (they're already encrypted).
        await self._store.async_save()

    def decrypt_codes_in_memory(self, key: bytes) -> None:
        """Decrypt all encrypted codes in the in-memory storage.

        Called after a successful secure mode unlock so that the push
        engine and slot accessors see plaintext codes.

        Args:
            key: 32-byte AES-256 encryption key.
        """
        if self._store.is_encrypted:
            self._store.decrypt_codes(key)
            _LOGGER.info("In-memory codes decrypted for secure session")

    def encrypt_codes_in_memory(self, key: bytes) -> None:
        """Re-encrypt all plaintext codes in memory.

        Called when the user locks the secure session so that codes
        are not held in plaintext in memory while the session is locked.

        Args:
            key: 32-byte AES-256 encryption key.
        """
        self._store.encrypt_codes(key)
        _LOGGER.info("In-memory codes re-encrypted (session locked)")

    async def async_shutdown(self) -> None:
        """Cancel all running commit machines. Called during unload."""
        for lock_entity, machine in self._machines.items():
            _LOGGER.debug("Cancelling commit machine for %s", lock_entity)
            await machine.async_cancel()

    # ------------------------------------------------------------------
    # Slot CRUD
    # ------------------------------------------------------------------

    async def async_get_slots(self) -> dict[int, SlotData]:
        """Return all slots from storage."""
        return self._store.get_slots()

    async def async_set_slot(
        self,
        slot_number: int,
        label: str,
        code_1: str,
        code_2: str,
        enabled: bool,
    ) -> None:
        """Create or update a slot.

        Validates label uniqueness (case-insensitive, empty labels exempt)
        and code lengths against each backend's supported range. Persists
        to disk, marks affected lock commits as out_of_sync where the code
        hash has changed, and fires a push-status event.

        Args:
            slot_number: 1-based slot index.
            label:       Human-readable name for this slot.
            code_1:      The primary PIN code (or empty string).
            code_2:      The secondary PIN code (or empty string).
            enabled:     Whether the slot is active.

        Raises:
            ValueError: If the label duplicates another slot (case-insensitive)
                        or if a code length is outside the range supported by a
                        configured backend.
        """
        # -- Label uniqueness --------------------------------------------------
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

        # -- Code length validation against backends ---------------------------
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

        # -- Persist slot data -------------------------------------------------
        slot = SlotData(
            slot_number=slot_number,
            label=label,
            code_1=code_1,
            code_2=code_2,
            enabled=enabled,
            created_at="",   # set_slot() handles timestamps
            updated_at="",
        )
        self._store.set_slot(slot)

        # -- Dirty detection: mark lock commits out_of_sync where needed -------
        self._mark_dirty_commits(slot_number, label, code_1, code_2)
        await self._async_save()

        self._fire_push_status_event()
        _LOGGER.info("Slot %d updated (label=%r, enabled=%s)", slot_number, label, enabled)

    async def async_delete_slot(self, slot_number: int) -> None:
        """Clear a slot and mark all lock commits as out_of_sync.

        Args:
            slot_number: 1-based slot index to delete.
        """
        self._store.delete_slot(slot_number)
        await self._async_save()
        self._fire_push_status_event()
        _LOGGER.info("Slot %d deleted", slot_number)

    # ------------------------------------------------------------------
    # Push engine — delegates to LockCommitMachine
    # ------------------------------------------------------------------

    async def async_push_all(self) -> None:
        """Push dirty slots to all configured locks sequentially.

        Locks are pushed one at a time to avoid Z-Wave network congestion.
        Fires a push-status event after each lock completes so the panel
        can update incrementally.
        """
        if not self._machines:
            _LOGGER.debug("async_push_all: no commit machines, nothing to push")
            return

        mode = self.code_length_mode
        cl1 = self.code_length_1
        cl2 = self.code_length_2
        plcl = self.per_lock_code_length

        for lock_entity, machine in self._machines.items():
            self._active_push_lock = lock_entity
            self._fire_push_status_event()

            slots = self._store.get_slots()
            lock_cl = plcl.get(lock_entity)
            await machine.async_start(slots, mode, cl1, cl2, lock_cl)

            # Wait for this lock to finish before starting the next.
            if machine._task is not None and not machine._task.done():
                try:
                    await machine._task
                except Exception:  # noqa: BLE001
                    pass  # Errors are handled inside the machine.

            self._fire_push_status_event()

        self._active_push_lock = None
        self._fire_push_status_event()

    async def async_push_lock(self, lock_entity: str) -> None:
        """Push all dirty slots to a single lock via its commit machine.

        Args:
            lock_entity: Entity ID of the lock to push to.

        Raises:
            KeyError: If ``lock_entity`` is not a configured backend.
        """
        machine = self._machines.get(lock_entity)
        if machine is None:
            raise KeyError(f"No backend configured for lock '{lock_entity}'")

        self._active_push_lock = lock_entity
        self._fire_push_status_event()

        slots = self._store.get_slots()
        lock_cl = self.per_lock_code_length.get(lock_entity)
        await machine.async_start(
            slots, self.code_length_mode, self.code_length_1, self.code_length_2,
            lock_cl,
        )

        # Wait for completion.
        if machine._task is not None and not machine._task.done():
            try:
                await machine._task
            except Exception:  # noqa: BLE001
                pass

        self._active_push_lock = None
        self._fire_push_status_event()

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_push_status(self) -> dict[str, Any]:
        """Return a per-lock summary of sync status.

        Returns:
            Mapping of ``lock_entity`` to a dict containing:
              - ``synced_count``: Number of slots confirmed in sync.
              - ``failed_count``: Number of slots that failed a push attempt.
              - ``pending_count``: Number of slots needing first push.
              - ``uncertain_count``: Number of slots in uncertain state.
              - ``dirty_slots``: List of slot numbers that need a push.
              - ``state``: Overall lock state — ``"synced"`` if all clean,
                ``"out_of_sync"`` if any failed, ``"pending"`` if never
                pushed, ``"uncertain"`` otherwise.
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

            for sn, commit in commits.items():
                # Skip empty+disabled slots — nothing to push.
                slot = existing_slots.get(sn)
                if slot and not slot.enabled and slot.is_empty():
                    synced += 1
                    continue

                # Skip empty slots that were never pushed — nothing to clear.
                if slot and slot.is_empty() and commit.pushed_at is None:
                    synced += 1
                    continue

                if commit.state == SYNC_SYNCED:
                    synced += 1
                elif commit.state == SYNC_OUT_OF_SYNC:
                    if commit.pushed_at is None:
                        # Never pushed — pending first sync, not a failure.
                        pending += 1
                    else:
                        failed += 1
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

            result[lock_entity] = {
                "state": overall,
                "synced_count": synced,
                "failed_count": failed,
                "pending_count": pending,
                "uncertain_count": uncertain,
                "dirty_slots": sorted(dirty),
            }

        return result

    def get_lock_commit_state(
        self, lock_entity: str, slot_number: int
    ) -> Any:
        """Return the commit state for a specific lock + slot."""
        return self._store.get_lock_commit(lock_entity, slot_number)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_seed_data(self) -> None:
        """Populate storage slots from seed data in the config entry.

        Seed data is a one-time payload set by the config flow when the user
        chooses to pre-populate slots from an existing readable lock. After
        processing, the seed_slots key is removed from the entry data.
        """
        seed_slots: list[dict] = self._entry.data.get("seed_slots", [])
        if not seed_slots:
            return

        _LOGGER.info(
            "Applying %d seed slot(s) from config flow", len(seed_slots)
        )

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
            _LOGGER.debug(
                "Seed: slot %d populated (code_1=%s, code_2=%s)",
                sn,
                "yes" if slot.code_1 else "no",
                "yes" if slot.code_2 else "no",
            )

        # Remove seed_slots from entry data (one-time operation).
        new_data = dict(self._entry.data)
        new_data.pop("seed_slots", None)
        self._hass.config_entries.async_update_entry(
            self._entry, data=new_data
        )
        _LOGGER.info("Seed data applied and removed from config entry")

    def _select_code_for_backend(
        self, slot: SlotData, backend: LockBackend, lock_entity: str,
    ) -> str | None:
        """Choose which code to push to a backend based on per-lock code length.

        Used by ``_mark_dirty_commits`` for hash-based dirty detection.
        The actual push code selection is in LockCommitMachine.

        Returns:
            The code string that would be pushed, or ``None`` if the slot
            has no applicable code for this backend.
        """
        code_range = backend.supported_code_lengths

        if self.code_length_mode == CODE_LENGTH_SINGLE:
            code = slot.code_1 or slot.code_2
            if code and _code_in_range(code, code_range):
                return code
            return None

        # Dual mode — use per-lock code length mapping to pick field.
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
            # Fallback: try code_1 then code_2.
            if slot.code_1 and _code_in_range(slot.code_1, code_range):
                return slot.code_1
            if slot.code_2 and _code_in_range(slot.code_2, code_range):
                return slot.code_2

        return None

    def _mark_dirty_commits(
        self,
        slot_number: int,
        label: str,
        code_1: str,
        code_2: str,
    ) -> None:
        """Mark lock commits out_of_sync where the pushed code would change.

        Compares the hash of the code that *would* be pushed to each backend
        against the hash recorded in the commit entry. Also dirties
        name-based backends when the label changes.
        """
        slot = self._store.get_slot(slot_number)
        if slot is None:
            return

        for lock_entity, backend in self._backends.items():
            commit = self._store.get_lock_commit(lock_entity, slot_number)
            code = self._select_code_for_backend(slot, backend, lock_entity)

            current_hash = hash_code(code) if code else None
            code_changed = current_hash != commit.code_hash

            label_changed = (
                backend.addressing_mode == ADDRESSING_NAME
                and commit.last_pushed_label is not None
                and commit.last_pushed_label != label
            )

            if code_changed or label_changed:
                commit.state = SYNC_OUT_OF_SYNC
                self._store.set_lock_commit(lock_entity, commit)
                _LOGGER.debug(
                    "Slot %d marked out_of_sync for %s "
                    "(code_changed=%s, label_changed=%s)",
                    slot_number,
                    lock_entity,
                    code_changed,
                    label_changed,
                )

    def _fire_push_status_event(self) -> None:
        """Fire an HA event so sensor entities refresh their state."""
        self._hass.bus.async_fire(
            EVENT_PUSH_STATUS_CHANGED,
            {"entry_id": self._entry.entry_id},
        )
