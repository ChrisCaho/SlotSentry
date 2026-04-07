"""SlotSentry commit state machine.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Manages the workflow for pushing codes from SlotSentry storage to physical
locks. One LockCommitMachine instance per lock entity; all dirty slots for
that lock are processed sequentially within a single asyncio Task.

State machine per (lock, slot):

    IDLE → PENDING → PUSHING → VERIFYING → SUCCESS
                        ↓                     ↓
                      RETRY (≤ MAX_RETRIES) → FAILED

Revision: 1.1 — per-lock code length, code_1/code_2 field names.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .const import (
    ADDRESSING_NAME,
    CODE_LENGTH_DUAL,
    CONSECUTIVE_FAIL_COOLDOWN,
    CONSECUTIVE_FAIL_PAUSE,
    INTER_SLOT_DELAY,
    LATENCY_ERROR_RAMP,
    LATENCY_SLOT_MULTIPLIER,
    MAX_RETRIES,
    MIN_INTER_SLOT_DELAY,
    RETRY_BACKOFF,
    SLOW_LOCK_FAIL_COOLDOWN,
    SLOW_LOCK_FAIL_PAUSE,
    SLOW_LOCK_LATENCY_THRESHOLD,
    SLOW_LOCK_SLOT_MULTIPLIER,
    SLOW_LOCK_TIMEOUT,
    STATE_FAILED,
    STATE_IDLE,
    STATE_PUSHING,
    STATE_RETRY,
    STATE_SUCCESS,
    STATE_VERIFYING,
    SYNC_OUT_OF_SYNC,
    SYNC_SYNCED,
    SYNC_UNCERTAIN,
    VERIFY_SETTLE_DELAY,
)
from .lock_backend import LockBackend, SlotInfo
from .storage import LockSlotCommit, SlotData, SlotSentryStore, hash_code

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Result / status data classes
# ---------------------------------------------------------------------------


@dataclass
class PushError:
    """Details of a single slot push failure."""

    slot_number: int
    attempt: int
    error_message: str


@dataclass
class PushResult:
    """Summary of a push operation for one lock."""

    lock_entity: str
    total_slots: int
    synced: int
    failed: int
    uncertain: int
    errors: list[PushError] = field(default_factory=list)


@dataclass
class LockPushStatus:
    """Current status of this lock's commit machine."""

    lock_entity: str
    state: str          # "idle" | "pushing" | "complete"
    synced_count: int
    failed_count: int
    uncertain_count: int
    current_slot: int | None    # Slot currently being pushed, or None
    current_operation: str | None = None  # Human-readable status line


# ---------------------------------------------------------------------------
# LockCommitMachine
# ---------------------------------------------------------------------------


class LockCommitMachine:
    """Manages the commit workflow for a single lock.

    One instance per lock entity. Processes all dirty slots for that lock
    sequentially within a single asyncio Task so that concurrent pushes to
    the same lock are never issued (important for Z-Wave mesh stability).

    Usage::

        machine = LockCommitMachine(hass, backend, store, "lock.front_door")
        await machine.async_start(slots, mode, short_len, long_len)
        # ... later, if you need to abort:
        await machine.async_cancel()
        status = machine.get_status()
    """

    def __init__(
        self,
        hass: HomeAssistant,
        backend: LockBackend,
        store: SlotSentryStore,
        lock_entity: str,
        typical_latency: float | None = None,
    ) -> None:
        """Initialise the machine for one lock.

        Args:
            hass:            The Home Assistant instance.
            backend:         Lock backend shim for the controlled lock.
            store:           Shared SlotSentry storage instance (already loaded).
            lock_entity:     HA entity ID of the lock, e.g. ``"lock.back_door"``.
            typical_latency: Profiled round-trip latency (seconds); used to
                             compute a proactive inter-slot delay baseline.
        """
        self._hass = hass
        self._backend = backend
        self._store = store
        self._lock_entity = lock_entity

        # asyncio.Task for the current push run, or None when idle.
        self._task: asyncio.Task | None = None

        # Busy flag — rejects overlapping pushes instead of queueing.
        self._busy: bool = False

        # Per-slot retry counters.  Keys are slot numbers (int).
        self._attempt_counts: dict[int, int] = {}

        # Tracks the last Z-Wave call's elapsed time for adaptive delay.
        self._last_call_elapsed: float = 0.0

        # Profiled typical latency — used as proactive delay baseline.
        self._typical_latency: float | None = typical_latency

        # Internal machine state for get_status().
        self._machine_state: str = STATE_IDLE
        self._current_slot: int | None = None
        self._current_operation: str | None = None
        self._progress_prefix: str = ""
        self._progress_eta: str = ""

    @property
    def is_busy(self) -> bool:
        """True if a push is currently running on this lock."""
        return self._busy

    @property
    def is_slow_lock(self) -> bool:
        """True if profiled latency exceeds the slow-lock threshold.

        Slow locks (e.g., 300-series Schlage FE595/FE599) get higher
        inter-slot delays, longer timeouts, and more conservative
        failure cooldowns.
        """
        return (
            self._typical_latency is not None
            and self._typical_latency >= SLOW_LOCK_LATENCY_THRESHOLD
        )

    def update_typical_latency(self, latency: float) -> None:
        """Update the profiled latency (called by LatencyProfiler)."""
        self._typical_latency = latency

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def async_start(
        self,
        slots: dict[int, SlotData],
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None = None,
    ) -> None:
        """Wrap async_push_dirty_slots in an asyncio.Task and store it.

        If a push task is already running it is cancelled first, then the
        new task is started. This ensures at most one push runs at a time
        for this lock.

        Args:
            slots:             All slot data for this config entry, keyed
                               by slot number.
            code_length_mode:  ``CODE_LENGTH_SINGLE`` or ``CODE_LENGTH_DUAL``.
            code_length_1:     Primary code length.
            code_length_2:     Secondary code length (dual mode only).
            lock_code_length:  The code length assigned to *this* lock
                               (from per_lock_code_length mapping).
        """
        if self._task is not None and not self._task.done():
            _LOGGER.debug(
                "LockCommitMachine[%s]: cancelling existing push task before restart",
                self._lock_entity,
            )
            await self.async_cancel()

        self._task = self._hass.async_create_task(
            self.async_push_dirty_slots(
                slots, code_length_mode, code_length_1, code_length_2,
                lock_code_length,
            ),
            name=f"slotsentry_push_{self._lock_entity}",
        )
        _LOGGER.debug(
            "LockCommitMachine[%s]: push task started", self._lock_entity
        )

    async def async_cancel(self) -> None:
        """Cancel the running push task, if any.

        Awaits cancellation so that callers can be sure the task has
        actually stopped before proceeding (e.g., before restarting).
        """
        if self._task is None or self._task.done():
            return

        _LOGGER.info(
            "LockCommitMachine[%s]: cancelling push task", self._lock_entity
        )
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        finally:
            self._task = None
            self._busy = False
            self._machine_state = STATE_IDLE
            self._current_slot = None
            self._current_operation = None

    def get_status(self) -> LockPushStatus:
        """Return a snapshot of the current push status for this lock.

        Counts are computed from storage on each call to keep them
        accurate without requiring event-driven bookkeeping.

        Returns:
            LockPushStatus snapshot.
        """
        all_commits = self._store.get_all_lock_commits(self._lock_entity)

        synced = sum(1 for c in all_commits.values() if c.state == SYNC_SYNCED)
        failed = sum(1 for c in all_commits.values() if c.state == STATE_FAILED)
        uncertain = sum(
            1 for c in all_commits.values() if c.state == SYNC_UNCERTAIN
        )

        # Determine the visible machine state.
        if self._machine_state == STATE_IDLE:
            visible_state = "idle"
        elif self._task is not None and not self._task.done():
            visible_state = "pushing"
        else:
            visible_state = "complete"

        return LockPushStatus(
            lock_entity=self._lock_entity,
            state=visible_state,
            synced_count=synced,
            failed_count=failed,
            uncertain_count=uncertain,
            current_slot=self._current_slot,
            current_operation=self._current_operation,
        )

    def reset_attempt_counters(self) -> None:
        """Reset all per-slot retry counters.

        Called when the SlotSentry panel is reopened so that previously
        failed slots become eligible for retry without requiring an HA
        restart.
        """
        _LOGGER.debug(
            "LockCommitMachine[%s]: resetting attempt counters", self._lock_entity
        )
        self._attempt_counts.clear()

    # ------------------------------------------------------------------
    # Core push loop
    # ------------------------------------------------------------------

    async def async_push_dirty_slots(
        self,
        slots: dict[int, SlotData],
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None = None,
    ) -> PushResult | None:
        """Push all dirty slots for this lock to the physical hardware.

        Rejects immediately if a push is already running on this lock.
        Returns None if rejected (lock busy).

        Args:
            slots:             All slot data for this config entry.
            code_length_mode:  ``CODE_LENGTH_SINGLE`` or ``CODE_LENGTH_DUAL``.
            code_length_1:     Primary code length.
            code_length_2:     Secondary code length (dual mode).
            lock_code_length:  Code length assigned to this lock.

        Returns:
            PushResult summary, or None if the lock was busy.
        """
        if self._busy:
            _LOGGER.warning(
                "LockCommitMachine[%s]: push rejected — lock is busy",
                self._lock_entity,
            )
            return None

        self._busy = True
        try:
            return await self._do_push_dirty_slots(
                slots, code_length_mode, code_length_1, code_length_2,
                lock_code_length,
            )
        finally:
            self._busy = False

    async def _do_push_dirty_slots(
        self,
        slots: dict[int, SlotData],
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None = None,
    ) -> PushResult:
        """Inner push loop, runs under the per-lock asyncio.Lock."""
        self._machine_state = STATE_PUSHING
        result = PushResult(
            lock_entity=self._lock_entity,
            total_slots=len(slots),
            synced=0,
            failed=0,
            uncertain=0,
        )

        _LOGGER.info(
            "LockCommitMachine[%s]: beginning push for %d slot(s)",
            self._lock_entity,
            len(slots),
        )

        push_start = time.monotonic()
        consecutive_failures = 0
        slots_actually_pushed = 0

        # Pre-count slots that need sync for progress display.
        slots_needing_push = 0
        for sn in sorted(slots.keys()):
            s = slots[sn]
            c = self._store.get_lock_commit(self._lock_entity, sn)
            if self._slot_needs_sync(s, c):
                slots_needing_push += 1

        try:
            for slot_number in sorted(slots.keys()):
                slot = slots[slot_number]
                commit = self._store.get_lock_commit(
                    self._lock_entity, slot_number
                )

                # Check whether name-based backend needs re-push due to label change.
                needs_sync = self._slot_needs_sync(slot, commit)
                if not needs_sync:
                    _LOGGER.debug(
                        "LockCommitMachine[%s]: slot %d already synced, skipping",
                        self._lock_entity,
                        slot_number,
                    )
                    result.synced += 1
                    continue

                # Check if this slot has already exhausted its retries.
                attempts_so_far = self._attempt_counts.get(slot_number, 0)
                if attempts_so_far >= MAX_RETRIES:
                    _LOGGER.warning(
                        "LockCommitMachine[%s]: slot %d exhausted retries "
                        "(%d/%d); skipping until counters are reset",
                        self._lock_entity,
                        slot_number,
                        attempts_so_far,
                        MAX_RETRIES,
                    )
                    result.failed += 1
                    continue

                # Consecutive failure pause — if the lock is struggling,
                # give it a long cooldown before trying more slots.
                # Slow locks (300-series) use a lower threshold and longer cooldown.
                fail_threshold = SLOW_LOCK_FAIL_PAUSE if self.is_slow_lock else CONSECUTIVE_FAIL_PAUSE
                fail_cooldown = SLOW_LOCK_FAIL_COOLDOWN if self.is_slow_lock else CONSECUTIVE_FAIL_COOLDOWN
                if consecutive_failures >= fail_threshold:
                    _LOGGER.warning(
                        "LockCommitMachine[%s]: %d consecutive failures — "
                        "pausing %.0fs to let lock recover (slow_lock=%s)",
                        self._lock_entity,
                        consecutive_failures,
                        fail_cooldown,
                        self.is_slow_lock,
                    )
                    self._current_operation = f"Pausing {fail_cooldown:.0f}s after {consecutive_failures} failures"
                    await asyncio.sleep(fail_cooldown)
                    consecutive_failures = 0

                # Adaptive inter-slot delay — uses discovered latency as the
                # baseline (not a conservative constant).  Ramps up on errors.
                # Slow locks use a higher multiplier (3x vs 1.5x).
                if slots_actually_pushed > 0:
                    if self._typical_latency is not None:
                        # Latency-driven: use discovered latency as baseline.
                        mult = SLOW_LOCK_SLOT_MULTIPLIER if self.is_slow_lock else LATENCY_SLOT_MULTIPLIER
                        base = self._typical_latency * mult
                        # Ramp up on consecutive errors.
                        if consecutive_failures > 0:
                            base *= (1.0 + consecutive_failures * LATENCY_ERROR_RAMP)
                    else:
                        # No latency data — fall back to conservative constant.
                        base = INTER_SLOT_DELAY
                    # Reactive stretch: only increase delay when the last call
                    # was unusually slow (>3× typical latency), indicating the
                    # lock is under stress.  Normal variation stays at base.
                    adaptive_delay = base
                    if self._typical_latency and self._last_call_elapsed > self._typical_latency * 3:
                        adaptive_delay = max(base, self._last_call_elapsed / 5.0)
                    # Floor and cap.
                    adaptive_delay = max(adaptive_delay, MIN_INTER_SLOT_DELAY)
                    adaptive_delay = min(adaptive_delay, 10.0)
                    self._current_operation = f"Pacing delay {adaptive_delay:.1f}s"
                    _LOGGER.debug(
                        "LockCommitMachine[%s]: inter-slot delay %.1fs "
                        "(last call took %.1fs, typical=%.1fs, consec_errors=%d)",
                        self._lock_entity,
                        adaptive_delay,
                        self._last_call_elapsed,
                        self._typical_latency or 0.0,
                        consecutive_failures,
                    )
                    await asyncio.sleep(adaptive_delay)

                self._current_slot = slot_number

                # Progress prefix for status line: "3/19 "
                progress_idx = slots_actually_pushed + 1
                self._progress_prefix = f"{progress_idx}/{slots_needing_push} "

                # Estimate remaining time based on average elapsed per slot.
                if slots_actually_pushed > 0:
                    avg_per_slot = (time.monotonic() - push_start) / slots_actually_pushed
                    remaining = avg_per_slot * (slots_needing_push - slots_actually_pushed)
                    if remaining >= 60:
                        self._progress_eta = f" (~{remaining / 60:.0f}m left)"
                    else:
                        self._progress_eta = f" (~{remaining:.0f}s left)"
                else:
                    self._progress_eta = ""

                pre_synced = result.synced
                await self._push_slot_with_retry(
                    slot, commit, code_length_mode, code_length_1, code_length_2,
                    lock_code_length, result,
                )
                slots_actually_pushed += 1

                # Track consecutive failures for cooldown logic.
                if result.synced > pre_synced:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

        except asyncio.CancelledError:
            _LOGGER.info(
                "LockCommitMachine[%s]: push task was cancelled", self._lock_entity
            )
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "LockCommitMachine[%s]: unexpected error in push loop",
                self._lock_entity,
            )
        finally:
            self._current_slot = None
            self._current_operation = None
            self._machine_state = STATE_IDLE

        elapsed = time.monotonic() - push_start
        _LOGGER.info(
            "LockCommitMachine[%s]: push complete in %.1fs — "
            "synced=%d failed=%d uncertain=%d (pushed %d slots)",
            self._lock_entity,
            elapsed,
            result.synced,
            result.failed,
            result.uncertain,
            slots_actually_pushed,
        )
        return result

    # ------------------------------------------------------------------
    # Per-slot push with retry
    # ------------------------------------------------------------------

    async def _push_slot_with_retry(
        self,
        slot: SlotData,
        commit: LockSlotCommit,
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None,
        result: PushResult,
    ) -> None:
        """Push one slot, retrying on failure up to MAX_RETRIES times.

        Updates storage commit state and PushResult in-place.

        Args:
            slot:              The SlotData for this slot.
            commit:            Current commit record from storage.
            code_length_mode:  Code length selection mode.
            code_length_1:     Primary code length.
            code_length_2:     Secondary code length.
            lock_code_length:  Code length for this lock.
            result:            Accumulator updated with success/failure counts.
        """
        slot_number = slot.slot_number

        while True:
            attempt = self._attempt_counts.get(slot_number, 0) + 1
            self._attempt_counts[slot_number] = attempt

            retry_label = f" retry {attempt}/{MAX_RETRIES}" if attempt > 1 else ""
            self._current_operation = f"{self._progress_prefix}Slot {slot_number}: pushing{retry_label}{self._progress_eta}"
            _LOGGER.info(
                "LockCommitMachine[%s]: pushing slot %d (attempt %d/%d)",
                self._lock_entity,
                slot_number,
                attempt,
                MAX_RETRIES,
            )

            t0 = time.monotonic()
            success, error_msg = await self._attempt_push(
                slot, code_length_mode, code_length_1, code_length_2,
                lock_code_length,
            )
            self._last_call_elapsed = time.monotonic() - t0

            if success:
                # Clear attempt counter on success so future pushes start fresh.
                self._attempt_counts.pop(slot_number, None)
                # Update commit record: SUCCESS
                new_commit = LockSlotCommit(
                    slot_number=slot_number,
                    state=SYNC_SYNCED,
                    pushed_at=_utcnow_iso(),
                    code_hash=self._compute_pushed_hash(
                        slot, code_length_mode, code_length_1, code_length_2,
                        lock_code_length,
                    ),
                    last_pushed_label=slot.label if slot.label else None,
                )
                self._store.set_lock_commit(self._lock_entity, new_commit)
                await self._store.async_save()

                result.synced += 1
                self._current_operation = f"{self._progress_prefix}Slot {slot_number}: OK ({self._last_call_elapsed:.1f}s)"
                _LOGGER.info(
                    "LockCommitMachine[%s]: slot %d synced successfully",
                    self._lock_entity,
                    slot_number,
                )
                return

            # Push failed.
            result.errors.append(
                PushError(
                    slot_number=slot_number,
                    attempt=attempt,
                    error_message=error_msg or "unknown error",
                )
            )

            if attempt >= MAX_RETRIES:
                # Exhausted all retries — mark FAILED.
                failed_commit = LockSlotCommit(
                    slot_number=slot_number,
                    state=STATE_FAILED,
                    pushed_at=commit.pushed_at,
                    code_hash=commit.code_hash,
                    last_pushed_label=commit.last_pushed_label,
                )
                self._store.set_lock_commit(self._lock_entity, failed_commit)
                await self._store.async_save()

                result.failed += 1
                self._current_operation = f"{self._progress_prefix}Slot {slot_number}: FAILED, moving to next slot"
                _LOGGER.warning(
                    "LockCommitMachine[%s]: slot %d FAILED after %d attempts",
                    self._lock_entity,
                    slot_number,
                    attempt,
                )
                return

            # More retries remain — mark RETRY, apply backoff, then loop.
            retry_commit = LockSlotCommit(
                slot_number=slot_number,
                state=STATE_RETRY,
                pushed_at=commit.pushed_at,
                code_hash=commit.code_hash,
                last_pushed_label=commit.last_pushed_label,
            )
            self._store.set_lock_commit(self._lock_entity, retry_commit)
            await self._store.async_save()

            # Backoff index is 0-based; attempt is 1-based after the first
            # failure, so use (attempt - 1) clamped to the tuple length.
            backoff_idx = min(attempt - 1, len(RETRY_BACKOFF) - 1)
            delay = RETRY_BACKOFF[backoff_idx]
            self._current_operation = f"{self._progress_prefix}Slot {slot_number}: error, retrying in {delay}s"
            _LOGGER.info(
                "LockCommitMachine[%s]: slot %d will retry in %ds "
                "(attempt %d/%d failed: %s)",
                self._lock_entity,
                slot_number,
                delay,
                attempt,
                MAX_RETRIES,
                error_msg,
            )
            await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Single push attempt
    # ------------------------------------------------------------------

    async def _attempt_push(
        self,
        slot: SlotData,
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None = None,
    ) -> tuple[bool, str | None]:
        """Execute one push attempt for a slot.

        Handles both set-code and clear-code paths, then optionally
        verifies the write via readback.

        Args:
            slot:              SlotData for the slot to push.
            code_length_mode:  Code length selection mode.
            code_length_1:     Primary code length.
            code_length_2:     Secondary code length.
            lock_code_length:  Code length assigned to this lock.

        Returns:
            A ``(success, error_message)`` tuple.  ``error_message`` is
            None on success.
        """
        slot_number = slot.slot_number
        slot_info = SlotInfo(slot_number=slot_number, label=slot.label)

        # Check if this slot was ever pushed to this lock.
        commit = self._store.get_lock_commit(self._lock_entity, slot_number)
        was_pushed = commit is not None and commit.pushed_at is not None

        # Disabled or empty slots that were previously pushed need clearing
        # (the lock still has old codes).  If never pushed, skip entirely.
        if not slot.enabled or slot.is_empty():
            if was_pushed:
                _LOGGER.info(
                    "LockCommitMachine[%s]: slot %d is %s but was previously "
                    "pushed — clearing from lock",
                    self._lock_entity,
                    slot_number,
                    "disabled" if not slot.enabled else "empty",
                )
                return await self._attempt_clear(slot_info)
            _LOGGER.debug(
                "LockCommitMachine[%s]: slot %d is %s and never pushed — skipping",
                self._lock_entity,
                slot_number,
                "disabled" if not slot.enabled else "empty",
            )
            return True, None

        # Set path: select code to push.
        code = self._select_code_for_lock(
            slot, code_length_mode, code_length_1, code_length_2,
            lock_code_length,
        )
        if code is None:
            # No compatible code for this lock — skip silently and treat as
            # "uncertain" so it will not be retried until something changes.
            _LOGGER.info(
                "LockCommitMachine[%s]: slot %d has no compatible code for "
                "this lock (mode=%s, cl1=%s, cl2=%s, lock_cl=%s) — marking uncertain",
                self._lock_entity,
                slot_number,
                code_length_mode,
                code_length_1,
                code_length_2,
                lock_code_length,
            )
            # Persist uncertain state immediately.
            uncertain_commit = LockSlotCommit(
                slot_number=slot_number,
                state=SYNC_UNCERTAIN,
                pushed_at=None,
                code_hash=None,
                last_pushed_label=None,
            )
            self._store.set_lock_commit(self._lock_entity, uncertain_commit)
            await self._store.async_save()
            # Return True with a note — the outer loop counts this as uncertain
            # rather than a retryable failure.
            return True, None

        _LOGGER.debug(
            "LockCommitMachine[%s]: slot %d pushing code (len=%d)",
            self._lock_entity,
            slot_number,
            len(code),
        )

        # Push the code.
        try:
            ok = await self._backend.async_set_usercode(slot_info, code)
        except Exception as exc:  # noqa: BLE001
            return False, f"set_usercode raised: {exc}"

        if not ok:
            return False, "async_set_usercode returned False"

        # Optionally verify the write.  Wait for the lock to persist the
        # code to flash before reading back — immediate reads can return the
        # old value, causing false mismatches and unnecessary retries.
        if self._backend.supports_readback:
            self._current_operation = f"Slot {slot_number}: verifying"
            _LOGGER.debug(
                "LockCommitMachine[%s]: slot %d waiting %.1fs before verify readback",
                self._lock_entity,
                slot_number,
                VERIFY_SETTLE_DELAY,
            )
            await asyncio.sleep(VERIFY_SETTLE_DELAY)
            verified = await self._verify_slot(slot_info, code)
            if not verified:
                return (
                    False,
                    f"readback verification failed for slot {slot_number}",
                )

        return True, None

    # ------------------------------------------------------------------
    # Clear with verification
    # ------------------------------------------------------------------

    async def _attempt_clear(
        self, slot_info: SlotInfo
    ) -> tuple[bool, str | None]:
        """Clear a slot from the lock, with optional verification.

        Schlage locks sometimes silently fail to clear slots. When the lock
        supports readback, we use a robust clear sequence:
          1. Set a random temporary code (forces the slot to "occupied" state)
          2. Clear the slot
          3. Read back to verify the slot is actually empty

        On locks without readback support, we just clear and trust the result.
        """
        slot_number = slot_info.slot_number

        if not self._backend.supports_readback:
            # No readback — simple clear, trust the result.
            self._current_operation = f"Slot {slot_number}: clearing"
            _LOGGER.debug(
                "LockCommitMachine[%s]: slot %d clearing (no readback)",
                self._lock_entity,
                slot_number,
            )
            try:
                ok = await self._backend.async_clear_usercode(slot_info)
            except Exception as exc:  # noqa: BLE001
                return False, f"clear_usercode raised: {exc}"
            if not ok:
                return False, "async_clear_usercode returned False"
            return True, None

        # Readback-capable lock: robust clear sequence.
        self._current_operation = f"Slot {slot_number}: robust clear"
        _LOGGER.info(
            "LockCommitMachine[%s]: slot %d robust clear "
            "(set temp → clear → verify)",
            self._lock_entity,
            slot_number,
        )

        # Step 1: Set a random temporary code to force "occupied" state.
        import random
        min_len, max_len = self._backend.supported_code_lengths
        temp_len = max(min_len, 4)
        temp_code = "".join(str(random.randint(0, 9)) for _ in range(temp_len))

        try:
            ok = await self._backend.async_set_usercode(slot_info, temp_code)
        except Exception as exc:  # noqa: BLE001
            return False, f"clear: temp set_usercode raised: {exc}"
        if not ok:
            # Temp set failed — try direct clear anyway.
            _LOGGER.warning(
                "LockCommitMachine[%s]: slot %d temp code set failed, "
                "trying direct clear",
                self._lock_entity,
                slot_number,
            )

        # Step 2: Clear the slot.
        await asyncio.sleep(VERIFY_SETTLE_DELAY)
        try:
            ok = await self._backend.async_clear_usercode(slot_info)
        except Exception as exc:  # noqa: BLE001
            return False, f"clear_usercode raised: {exc}"
        if not ok:
            return False, "async_clear_usercode returned False"

        # Step 3: Verify the slot is actually empty.
        await asyncio.sleep(VERIFY_SETTLE_DELAY)
        try:
            readback = await self._backend.async_get_usercode(slot_info)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "LockCommitMachine[%s]: slot %d clear verify readback failed; "
                "treating as uncertain",
                self._lock_entity,
                slot_number,
                exc_info=True,
            )
            return True, None  # Optimistic — clear probably worked.

        if readback is None:
            _LOGGER.info(
                "LockCommitMachine[%s]: slot %d clear verified — slot is empty",
                self._lock_entity,
                slot_number,
            )
            return True, None

        # Slot still has data after clear — the clear failed silently.
        _LOGGER.warning(
            "LockCommitMachine[%s]: slot %d still occupied after clear "
            "(readback len=%d)",
            self._lock_entity,
            slot_number,
            len(readback),
        )
        return False, f"clear verification failed: slot {slot_number} still occupied"

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    async def _verify_slot(self, slot_info: SlotInfo, expected_code: str) -> bool:
        """Verify a slot was written correctly by reading it back.

        Args:
            slot_info:     Slot context.
            expected_code: The code that should have been written.

        Returns:
            True if verification passed (or was not possible), False if
            the readback confirms a mismatch or the slot appears empty.
        """
        if not self._backend.supports_readback:
            # Trust the service call result.
            return True

        _LOGGER.debug(
            "LockCommitMachine[%s]: verifying slot %d via readback",
            self._lock_entity,
            slot_info.slot_number,
        )

        try:
            actual = await self._backend.async_get_usercode(slot_info)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "LockCommitMachine[%s]: readback raised for slot %d; "
                "treating as uncertain",
                self._lock_entity,
                slot_info.slot_number,
                exc_info=True,
            )
            return False

        if actual is None:
            _LOGGER.warning(
                "LockCommitMachine[%s]: slot %d appears empty after push",
                self._lock_entity,
                slot_info.slot_number,
            )
            return False

        # Some locks (e.g., Schlage FE599) return asterisks.  If so, we can
        # only confirm the slot is occupied — that is the best we can do.
        if "*" in actual:
            _LOGGER.debug(
                "LockCommitMachine[%s]: slot %d returned masked code; "
                "accepting (slot is occupied)",
                self._lock_entity,
                slot_info.slot_number,
            )
            return True

        if actual == expected_code:
            _LOGGER.debug(
                "LockCommitMachine[%s]: slot %d readback verified",
                self._lock_entity,
                slot_info.slot_number,
            )
            return True

        _LOGGER.warning(
            "LockCommitMachine[%s]: slot %d readback MISMATCH "
            "(expected len=%d, got len=%d)",
            self._lock_entity,
            slot_info.slot_number,
            len(expected_code),
            len(actual),
        )
        return False

    # ------------------------------------------------------------------
    # Code selection
    # ------------------------------------------------------------------

    def _select_code_for_lock(
        self,
        slot: SlotData,
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None = None,
    ) -> str | None:
        """Determine which code to push to this lock based on per-lock code length.

        In DUAL mode, uses the lock_code_length to decide whether to push
        code_1 or code_2. If lock_code_length matches code_length_1, push
        code_1; if it matches code_length_2, push code_2. Fallback: try
        code_1 then code_2.

        In SINGLE mode, the slot's active code is used provided its length
        falls within the lock's supported range.

        Args:
            slot:              The SlotData whose codes are considered.
            code_length_mode:  ``CODE_LENGTH_SINGLE`` or ``CODE_LENGTH_DUAL``.
            code_length_1:     Primary code length (may be None).
            code_length_2:     Secondary code length (may be None).
            lock_code_length:  Code length assigned to this lock (may be None).

        Returns:
            The selected code string, or None if no compatible code exists
            for this lock.
        """
        min_len, max_len = self._backend.supported_code_lengths

        if code_length_mode == CODE_LENGTH_DUAL:
            # Use per-lock code length to pick the right code field.
            if lock_code_length is not None and code_length_1 is not None and lock_code_length == code_length_1:
                if slot.code_1 and min_len <= len(slot.code_1) <= max_len:
                    return slot.code_1
                return None
            if lock_code_length is not None and code_length_2 is not None and lock_code_length == code_length_2:
                if slot.code_2 and min_len <= len(slot.code_2) <= max_len:
                    return slot.code_2
                return None
            # Fallback: try code_1 then code_2.
            if slot.code_1 and min_len <= len(slot.code_1) <= max_len:
                return slot.code_1
            if slot.code_2 and min_len <= len(slot.code_2) <= max_len:
                return slot.code_2
            return None

        # Single mode — use whichever code is stored, provided its length
        # is within the lock's supported range.
        code = slot.get_active_code()
        if code is None:
            return None
        if min_len <= len(code) <= max_len:
            return code
        _LOGGER.debug(
            "LockCommitMachine[%s]: slot %d code length %d not in [%d, %d]",
            self._lock_entity,
            slot.slot_number,
            len(code),
            min_len,
            max_len,
        )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _slot_needs_sync(self, slot: SlotData, commit: LockSlotCommit) -> bool:
        """Return True if this slot requires a push to the lock.

        Disabled/empty slots that were previously pushed still need clearing.
        """
        was_pushed = commit.pushed_at is not None

        # Disabled or empty slots: need sync only if previously pushed
        # (lock still has old codes that must be cleared).
        if not slot.enabled or slot.is_empty():
            if was_pushed and commit.state != SYNC_SYNCED:
                return True
            return False

        if commit.state != SYNC_SYNCED:
            return True

        # Even if state==synced, confirm the code hash still matches.
        # A slot could be synced but then mutated without the commit state
        # being updated (e.g., a bug, or direct storage manipulation).
        if commit.code_hash is not None:
            current_code = slot.get_active_code()
            if current_code is not None:
                if hash_code(current_code) != commit.code_hash:
                    _LOGGER.debug(
                        "LockCommitMachine[%s]: slot %d code hash mismatch "
                        "— treating as out_of_sync",
                        self._lock_entity,
                        slot.slot_number,
                    )
                    return True
            elif not slot.is_empty():
                # Odd state: code_hash present but slot has no code.
                return True

        # Name-based backends: check for label changes.
        if (
            self._backend.addressing_mode == ADDRESSING_NAME
            and commit.last_pushed_label is not None
            and slot.label != commit.last_pushed_label
        ):
            _LOGGER.debug(
                "LockCommitMachine[%s]: slot %d label changed (%r → %r) "
                "— name-based backend requires re-push",
                self._lock_entity,
                slot.slot_number,
                commit.last_pushed_label,
                slot.label,
            )
            return True

        return False

    def _compute_pushed_hash(
        self,
        slot: SlotData,
        code_length_mode: str,
        code_length_1: int | None,
        code_length_2: int | None,
        lock_code_length: int | None = None,
    ) -> str | None:
        """Compute the hash of the code that was just pushed.

        Mirrors the selection logic in _select_code_for_lock so that the
        stored hash always reflects what was actually sent to the lock.

        Args:
            slot:              The SlotData that was pushed.
            code_length_mode:  Code length selection mode used.
            code_length_1:     Primary code length.
            code_length_2:     Secondary code length.
            lock_code_length:  Code length assigned to this lock.

        Returns:
            ``hash_code(selected_code)`` or None if no code was pushed
            (clear operation).
        """
        code = self._select_code_for_lock(
            slot, code_length_mode, code_length_1, code_length_2,
            lock_code_length,
        )
        if code is None:
            return None
        return hash_code(code)
