"""SlotSentry lock backend protocol and Z-Wave JS implementation.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.0

Defines the LockBackend Protocol that all lock backends must implement,
the SlotInfo dataclass passed to every backend method, and the
ZWaveJSBackend Phase 1 implementation.

The shim/adapter pattern applies throughout: the commit engine (SlotManager)
always calls the same LockBackend interface regardless of lock type. Each
backend translates those calls to the appropriate lock-specific API.

Phase 1 backends:
  - ZWaveJSBackend: slot-based, uses zwave_js HA services

Planned future backends (not in Phase 1):
  - SchlageCloudBackend: name-based, uses schlage HA services
  - ZigbeeBackend, MatterBackend, etc.

NOTE (name-based backends): When addressing_mode == "name", a label change
on a slot requires a delete + re-add on the lock and must dirty the lock
commit state even if the code itself is unchanged. The commit engine should
check backend.addressing_mode and conditionally dirty the lock commit array
on label changes. This logic is not needed until a name-based backend is
built; ZWaveJSBackend uses "slot" mode where label changes are disk-only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from homeassistant.core import HomeAssistant

from .const import (
    ADDRESSING_SLOT,
    MAX_CODE_LENGTH,
    MIN_CODE_LENGTH,
    PUSH_TIMEOUT_SECONDS,
    SERVICE_CLEAR_LOCK_USERCODE,
    SERVICE_INVOKE_CC_API,
    SERVICE_SET_LOCK_USERCODE,
    ZWAVE_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SlotInfo dataclass
# ---------------------------------------------------------------------------


@dataclass
class SlotInfo:
    """Context passed to LockBackend methods for each slot operation.

    Both fields are always provided. The backend uses whichever is
    appropriate for its addressing mode.

    Wrapping context in a dataclass rather than bare parameters allows
    new fields (e.g., expires_at, disabled) to be added for future
    backends without changing any method signatures.

    Attributes:
        slot_number: Physical slot on the lock (Z-Wave) or internal array
                     index (cloud). 1-based, matches the SlotSentry slot
                     grid row number.
        label:       Human name for this slot. Used as the code identifier
                     on name-based backends (e.g., Schlage cloud). Purely
                     cosmetic on slot-based backends (e.g., Z-Wave).
    """

    slot_number: int
    label: str


# ---------------------------------------------------------------------------
# LockBackend Protocol
# ---------------------------------------------------------------------------


class LockBackend(Protocol):
    """Protocol that all lock backend implementations must satisfy.

    The commit engine (SlotManager) calls these methods. Each backend
    shim translates them to the appropriate lock-specific API:

    - ZWaveJSBackend: uses slot_info.slot_number for all operations.
      Ignores slot_info.label entirely (Z-Wave addresses by slot number).
    - SchlageCloudBackend (planned, Phase 2/3): uses slot_info.label as
      the code identifier. slot_info.slot_number is the internal array
      index only and is not sent to the lock.

    Adding new backends does not require changes to the commit engine.
    All methods must be safe to call concurrently on different slots
    (one lock = one asyncio.Task in the commit engine, slots sequential).
    """

    @property
    def entity_id(self) -> str:
        """HA entity_id of the lock this backend controls."""
        ...

    @property
    def addressing_mode(self) -> str:
        """How this lock identifies codes: 'slot' or 'name'.

        'slot': codes are addressed by physical slot number (Z-Wave).
                Label changes are disk-only; the lock is not contacted.
        'name': codes are addressed by label/name (Schlage cloud).
                Label changes require a delete + re-add on the lock and
                must dirty the lock commit state even if the code is
                unchanged.

        The commit engine uses this property to decide whether a label
        change should mark a lock's slot as out_of_sync.
        """
        ...

    @property
    def supports_readback(self) -> bool:
        """True if async_get_usercode can return actual code digits.

        False means the backend cannot verify what is stored on the lock
        (e.g., FE599 returns asterisks). The commit engine falls back to
        trusting supervision results when this is False.
        """
        ...

    @property
    def supported_code_lengths(self) -> tuple[int, int]:
        """Supported code length range as (min_length, max_length).

        Used by the commit engine to pre-validate codes before attempting
        a push, enabling clear error messages ("Code length 4 is not
        supported by this lock") rather than cryptic Z-Wave errors.

        Z-Wave backend: returns the range discovered from lock capabilities
                        (e.g., (4, 4) for FE599, (4, 8) for BE469ZP).
        Schlage cloud backend (planned): returns (4, 8).
        """
        ...

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        """Push a code to the lock for the given slot.

        Args:
            slot_info: Slot context (number and label).
            code:      The PIN digits to write.

        Returns:
            True on success. The commit engine marks the slot as synced
            (pending verification) on True, error on False.
        """
        ...

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        """Clear/delete the code for the given slot from the lock.

        Args:
            slot_info: Slot context (number and label).

        Returns:
            True on success, False on service error.
        """
        ...

    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None:
        """Read back the code for the given slot, if supported.

        Args:
            slot_info: Slot context (number and label).

        Returns:
            The code string if readable, None if the slot is empty or
            if readback is not supported by this backend.
        """
        ...

    async def async_get_all_usercodes(self) -> dict[int, str] | None:
        """Read all codes from the lock in a single call, if supported.

        Returns:
            A dict of {slot_number: code_string} on success, or None if
            bulk readback is not supported (the commit engine falls back
            to per-slot async_get_usercode calls).

        Z-Wave backend returns None (Z-Wave does not support efficient
        bulk reads). Schlage cloud backend (planned) calls get_access_codes()
        once and maps names back to slot numbers via label matching, avoiding
        N individual API calls during verification.
        """
        ...


# ---------------------------------------------------------------------------
# ZWaveJSBackend — Phase 1 implementation
# ---------------------------------------------------------------------------

# User Code Command Class identifier used with invoke_cc_api.
# This is the Z-Wave command class name as accepted by zwave_js.
_USER_CODE_CC = "User Code"

# Door Lock Command Class name (reserved for keypad lockout — Phase 2).
_DOOR_LOCK_CC = "Door Lock"

# Slot used for readback capability probing during init.
_PROBE_SLOT = 1

# Z-Wave config parameter number that governs lock code length on some models.
# Not all locks expose this; used as a best-effort discovery hint only.
_ZWAVE_CODE_LENGTH_PARAM = 33

# Default code length range when discovery is not possible.
_DEFAULT_CODE_LENGTH_RANGE: tuple[int, int] = (MIN_CODE_LENGTH, MAX_CODE_LENGTH)


class ZWaveJSBackend:
    """Z-Wave JS lock backend.

    Translates LockBackend protocol calls to zwave_js HA service calls.
    Uses slot_info.slot_number for all lock operations; ignores
    slot_info.label entirely (Z-Wave addresses codes by physical slot).

    One instance per lock entity. Call async_init() after construction
    before using any other methods.

    Attributes:
        _hass:                  HomeAssistant instance.
        _entity_id:             HA entity_id of the controlled lock.
        _supports_readback:     Set during async_init by probing slot 1.
        _supported_code_lengths: Discovered (min, max) range from init.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Construct the backend. Call async_init() before use.

        Args:
            hass:      The HomeAssistant instance.
            entity_id: HA entity_id of the Z-Wave lock to control.
        """
        self._hass = hass
        self._entity_id = entity_id
        self._supports_readback: bool = False
        self._supported_code_lengths: tuple[int, int] = _DEFAULT_CODE_LENGTH_RANGE

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def async_init(self) -> None:
        """Probe the lock to discover capabilities.

        Must be called once after construction. Determines:
          1. Whether full-digit readback is available (supports_readback).
          2. The supported code-length range (supported_code_lengths).

        Failures are logged and silently swallowed; defaults are used so
        that a temporarily unreachable lock does not block startup.
        """
        _LOGGER.debug(
            "ZWaveJSBackend.async_init: probing %s", self._entity_id
        )

        # Step 1: probe readback by reading slot 1.
        probe_slot = SlotInfo(slot_number=_PROBE_SLOT, label="")
        result = await self.async_get_usercode(probe_slot)
        # A non-None return (even an empty string) means the CC responded.
        self._supports_readback = result is not None
        _LOGGER.debug(
            "ZWaveJSBackend: %s supports_readback=%s (probe result=%r)",
            self._entity_id,
            self._supports_readback,
            result,
        )

        # Step 2: discover code length range from lock entity attributes.
        self._supported_code_lengths = self._discover_code_lengths()
        _LOGGER.debug(
            "ZWaveJSBackend: %s supported_code_lengths=%s",
            self._entity_id,
            self._supported_code_lengths,
        )

    def _discover_code_lengths(self) -> tuple[int, int]:
        """Attempt to read code length range from the lock entity state.

        Checks the lock entity's state attributes for code-length fields
        exposed by the zwave_js integration. Falls back to the global
        default range (MIN_CODE_LENGTH, MAX_CODE_LENGTH) if the attributes
        are absent or the entity is unavailable.

        Returns:
            A (min_length, max_length) tuple.
        """
        state = self._hass.states.get(self._entity_id)
        if state is None:
            _LOGGER.warning(
                "ZWaveJSBackend: entity %s not found during code length "
                "discovery; using default range %s",
                self._entity_id,
                _DEFAULT_CODE_LENGTH_RANGE,
            )
            return _DEFAULT_CODE_LENGTH_RANGE

        attrs: dict[str, Any] = state.attributes

        # zwave_js exposes 'code_slot_count' and occasionally
        # 'usercode_min_length' / 'usercode_max_length' depending on the
        # lock model and firmware version.
        min_len: int | None = attrs.get("usercode_min_length")
        max_len: int | None = attrs.get("usercode_max_length")

        if isinstance(min_len, int) and isinstance(max_len, int):
            if MIN_CODE_LENGTH <= min_len <= max_len <= MAX_CODE_LENGTH:
                _LOGGER.debug(
                    "ZWaveJSBackend: %s code lengths from attributes: (%d, %d)",
                    self._entity_id,
                    min_len,
                    max_len,
                )
                return (min_len, max_len)
            _LOGGER.warning(
                "ZWaveJSBackend: %s attributes report unusual code length "
                "range (%d, %d); using default %s",
                self._entity_id,
                min_len,
                max_len,
                _DEFAULT_CODE_LENGTH_RANGE,
            )
            return _DEFAULT_CODE_LENGTH_RANGE

        # No length attributes present — inspect 'code_slot' entries if the
        # lock state exposes them; otherwise fall back to global default.
        _LOGGER.debug(
            "ZWaveJSBackend: %s has no code-length attributes; "
            "using default range %s",
            self._entity_id,
            _DEFAULT_CODE_LENGTH_RANGE,
        )
        return _DEFAULT_CODE_LENGTH_RANGE

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def entity_id(self) -> str:
        """HA entity_id of the controlled lock."""
        return self._entity_id

    @property
    def addressing_mode(self) -> str:
        """Returns 'slot' — Z-Wave locks address codes by physical slot number."""
        return ADDRESSING_SLOT

    @property
    def supports_readback(self) -> bool:
        """True if the lock reported actual code digits during init probe."""
        return self._supports_readback

    @property
    def supported_code_lengths(self) -> tuple[int, int]:
        """Discovered (min, max) code length range for this lock."""
        return self._supported_code_lengths

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        """Push a code to the lock via zwave_js.set_lock_usercode.

        Ignores slot_info.label — Z-Wave does not use code names.

        Args:
            slot_info: Provides the physical slot number.
            code:      The PIN digits to write to the slot.

        Returns:
            True on success, False on any exception (service error,
            entity unavailable, timeout, etc.).
        """
        service_data: dict[str, Any] = {
            "entity_id": self._entity_id,
            "code_slot": slot_info.slot_number,
            "usercode": code,
        }
        _LOGGER.info(
            "ZWaveJSBackend.async_set_usercode: %s slot=%d — sending",
            self._entity_id,
            slot_info.slot_number,
        )
        t0 = time.monotonic()
        try:
            async with asyncio.timeout(PUSH_TIMEOUT_SECONDS):
                await self._hass.services.async_call(
                    ZWAVE_DOMAIN,
                    SERVICE_SET_LOCK_USERCODE,
                    service_data,
                    blocking=True,
                )
        except TimeoutError:
            elapsed = time.monotonic() - t0
            _LOGGER.warning(
                "ZWaveJSBackend.async_set_usercode: TIMEOUT after %.1fs "
                "for %s slot %d",
                elapsed,
                self._entity_id,
                slot_info.slot_number,
            )
            return False
        except Exception:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            _LOGGER.warning(
                "ZWaveJSBackend.async_set_usercode: FAILED after %.1fs "
                "for %s slot %d",
                elapsed,
                self._entity_id,
                slot_info.slot_number,
                exc_info=True,
            )
            return False

        elapsed = time.monotonic() - t0
        _LOGGER.info(
            "ZWaveJSBackend.async_set_usercode: OK in %.1fs — %s slot=%d",
            elapsed,
            self._entity_id,
            slot_info.slot_number,
        )
        return True

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        """Clear a code slot on the lock via zwave_js.clear_lock_usercode.

        Ignores slot_info.label — Z-Wave does not use code names.

        Args:
            slot_info: Provides the physical slot number to clear.

        Returns:
            True on success, False on any exception.
        """
        service_data: dict[str, Any] = {
            "entity_id": self._entity_id,
            "code_slot": slot_info.slot_number,
        }
        _LOGGER.info(
            "ZWaveJSBackend.async_clear_usercode: %s slot=%d — sending",
            self._entity_id,
            slot_info.slot_number,
        )
        t0 = time.monotonic()
        try:
            async with asyncio.timeout(PUSH_TIMEOUT_SECONDS):
                await self._hass.services.async_call(
                    ZWAVE_DOMAIN,
                    SERVICE_CLEAR_LOCK_USERCODE,
                    service_data,
                    blocking=True,
                )
        except TimeoutError:
            elapsed = time.monotonic() - t0
            _LOGGER.warning(
                "ZWaveJSBackend.async_clear_usercode: TIMEOUT after %.1fs "
                "for %s slot %d",
                elapsed,
                self._entity_id,
                slot_info.slot_number,
            )
            return False
        except Exception:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            _LOGGER.warning(
                "ZWaveJSBackend.async_clear_usercode: FAILED after %.1fs "
                "for %s slot %d",
                elapsed,
                self._entity_id,
                slot_info.slot_number,
                exc_info=True,
            )
            return False

        elapsed = time.monotonic() - t0
        _LOGGER.info(
            "ZWaveJSBackend.async_clear_usercode: OK in %.1fs — %s slot=%d",
            elapsed,
            self._entity_id,
            slot_info.slot_number,
        )
        return True

    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None:
        """Read the current code for a slot via User Code CC invoke_cc_api.

        Calls zwave_js.invoke_cc_api with the User Code command class,
        method "get", and the slot number as the argument. Parses the
        response to extract the code string.

        Some locks (e.g., FE599) return asterisks ("****") rather than
        digits; the caller (commit engine) should check supports_readback
        to determine whether the return value is meaningful.

        Args:
            slot_info: Provides the physical slot number to read.

        Returns:
            The code string on success (may be asterisks on masked locks),
            or None if the CC is unsupported, the call fails, or the slot
            is empty.
        """
        service_data: dict[str, Any] = {
            "entity_id": self._entity_id,
            "command_class": _USER_CODE_CC,
            "endpoint": 0,
            "method_name": "get",
            "parameters": [slot_info.slot_number],
        }
        _LOGGER.debug(
            "ZWaveJSBackend.async_get_usercode: %s slot=%d",
            self._entity_id,
            slot_info.slot_number,
        )
        try:
            async with asyncio.timeout(PUSH_TIMEOUT_SECONDS):
                response = await self._hass.services.async_call(
                    ZWAVE_DOMAIN,
                    SERVICE_INVOKE_CC_API,
                    service_data,
                    blocking=True,
                    return_response=True,
                )
        except TimeoutError:
            _LOGGER.warning(
                "ZWaveJSBackend.async_get_usercode: timeout after %ds "
                "for %s slot %d",
                PUSH_TIMEOUT_SECONDS,
                self._entity_id,
                slot_info.slot_number,
            )
            return None
        except Exception:  # noqa: BLE001
            # Service not supported or entity unavailable — not an error
            # condition worth logging at WARNING during normal readback probing.
            _LOGGER.debug(
                "ZWaveJSBackend.async_get_usercode: service call failed "
                "for %s slot %d",
                self._entity_id,
                slot_info.slot_number,
                exc_info=True,
            )
            return None

        return self._extract_usercode(response, slot_info.slot_number)

    def _extract_usercode(
        self, response: Any, slot_number: int
    ) -> str | None:
        """Parse the invoke_cc_api response and return the code string.

        The zwave_js invoke_cc_api response shape for User Code CC "get":

            {
                "userIdStatus": 1,   # 0=available, 1=enabled, 2=disabled
                "userCode": "123456"
            }

        or, for a per-entity response (when called with entity_id targeting):

            {
                "<entity_id>": {
                    "userIdStatus": 1,
                    "userCode": "123456"
                }
            }

        Args:
            response: Raw service call return value.
            slot_number: Slot being read (for logging only).

        Returns:
            The code string, or None if the slot is empty/unavailable or
            the response cannot be parsed.
        """
        if not isinstance(response, dict):
            _LOGGER.debug(
                "ZWaveJSBackend._extract_usercode: unexpected response type "
                "%s for %s slot %d",
                type(response).__name__,
                self._entity_id,
                slot_number,
            )
            return None

        # Unwrap per-entity envelope if present.
        payload: dict[str, Any] = response
        if self._entity_id in payload:
            inner = payload[self._entity_id]
            if isinstance(inner, dict):
                payload = inner

        user_id_status: int | None = payload.get("userIdStatus")
        user_code: str | None = payload.get("userCode")

        # userIdStatus 0 = slot available (empty); anything else = occupied.
        if user_id_status == 0 or not user_code:
            _LOGGER.debug(
                "ZWaveJSBackend._extract_usercode: slot %d on %s is empty "
                "(userIdStatus=%s)",
                slot_number,
                self._entity_id,
                user_id_status,
            )
            return None

        return str(user_code)

    async def async_get_all_usercodes(self) -> dict[int, str] | None:
        """Returns None — Z-Wave does not support efficient bulk readback.

        The commit engine falls back to per-slot async_get_usercode calls
        when this returns None.

        Returns:
            Always None for ZWaveJSBackend.
        """
        return None
