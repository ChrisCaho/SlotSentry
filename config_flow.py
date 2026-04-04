"""SlotSentry config flow — multi-step setup wizard for Z-Wave lock code management.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 2.0 — per-lock code length selection, code_1/code_2 field names.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from base64 import b64encode
from typing import Any

import voluptuous as vol

from homeassistant.components.zwave_js import DOMAIN as ZWAVE_JS_DOMAIN
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CODE_LENGTH_DUAL,
    CODE_LENGTH_SINGLE,
    CONF_CODE_LENGTH_1,
    CONF_CODE_LENGTH_2,
    CONF_CODE_LENGTH_MODE,
    CONF_LOCK_ENTITIES,
    CONF_LOCKOUT_ENABLED,
    CONF_LOCKOUT_PARTICIPATING_LOCKS,
    CONF_LOCKOUT_TARGET_STATES,
    CONF_LOCKOUT_TRIGGER_ENTITY,
    CONF_PER_LOCK_CODE_LENGTH,
    CONF_SECURE_ENCRYPTION_SALT,
    CONF_SECURE_MODE,
    CONF_SECURE_PASSWORD_HASH,
    CONF_SLOT_COUNT,
    DEFAULT_CODE_LENGTH,
    DOMAIN,
    MAX_CODE_LENGTH,
    MAX_PASSWORD_LENGTH,
    MAX_SLOTS,
    MIN_CODE_LENGTH,
    MIN_PASSWORD_LENGTH,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

_LOCKOUT_STATE_SUGGESTIONS: list[str] = [
    "on",
    "off",
    "home",
    "away",
    "armed_home",
    "armed_away",
    "armed_night",
    "disarmed",
    "triggered",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discover_zwave_locks(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return all lock entities whose platform is zwave_js."""
    t0 = time.monotonic()
    registry = er.async_get(hass)
    locks: list[dict[str, Any]] = []
    for entry in registry.entities.values():
        if entry.domain == "lock" and entry.platform == ZWAVE_JS_DOMAIN:
            locks.append(
                {
                    "entity_id": entry.entity_id,
                    "name": entry.name or entry.original_name or entry.entity_id,
                    "slots": None,
                    "code_length": None,
                }
            )
    elapsed = time.monotonic() - t0
    _LOGGER.info(
        "PERF _discover_zwave_locks: found %d lock(s) in %.3fs",
        len(locks), elapsed,
    )
    return locks


async def _async_discover_lock_capabilities(
    hass: HomeAssistant, locks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Probe each lock for slot count and code length (in parallel).

    Annotates each lock dict in-place with 'slots' and 'code_length' keys.
    Uses the Z-Wave User Code CC and searches for pin-length number entities
    on the same device.
    """
    t_total = time.monotonic()
    registry = er.async_get(hass)

    async def _probe_one(lock: dict[str, Any]) -> None:
        eid = lock["entity_id"]
        t_lock = time.monotonic()

        # --- Slot count via node cache ---
        t0 = time.monotonic()
        lock["slots"] = await _async_get_max_user_codes(hass, eid)
        _LOGGER.info(
            "PERF %s: _async_get_max_user_codes took %.3fs (slots=%s)",
            eid, time.monotonic() - t0, lock["slots"],
        )

        # --- Code length: try state attributes first ---
        t0 = time.monotonic()
        code_len: int | None = None
        state = hass.states.get(eid)
        if state:
            min_len = state.attributes.get("usercode_min_length")
            if isinstance(min_len, int):
                code_len = min_len
                _LOGGER.info(
                    "PERF %s: code_length from state attributes: %d (%.3fs)",
                    eid, code_len, time.monotonic() - t0,
                )

        # Fallback: find a number.*pin_length entity on the same device.
        if code_len is None:
            t1 = time.monotonic()
            lock_entry = registry.async_get(eid)
            if lock_entry and lock_entry.device_id:
                for ent in registry.entities.values():
                    if (
                        ent.device_id == lock_entry.device_id
                        and ent.domain == "number"
                        and "pin_length" in (ent.entity_id or "").lower()
                    ):
                        pin_state = hass.states.get(ent.entity_id)
                        if pin_state and pin_state.state not in (
                            "unknown",
                            "unavailable",
                        ):
                            try:
                                code_len = int(float(pin_state.state))
                            except (ValueError, TypeError):
                                pass
                            break
            _LOGGER.info(
                "PERF %s: code_length pin_length entity scan: %s (%.3fs)",
                eid, code_len, time.monotonic() - t1,
            )

        lock["code_length"] = code_len
        _LOGGER.info(
            "PERF %s: total lock discovery took %.3fs (slots=%s, code_length=%s)",
            eid, time.monotonic() - t_lock, lock["slots"], lock["code_length"],
        )

    await asyncio.gather(*[_probe_one(lock) for lock in locks])

    _LOGGER.info(
        "PERF _async_discover_lock_capabilities: %d lock(s) total %.3fs",
        len(locks), time.monotonic() - t_total,
    )
    return locks


def _build_lock_options(locks: list[dict[str, Any]]) -> list[SelectOptionDict]:
    """Convert lock dicts to SelectOptionDicts with capability annotations."""
    options: list[SelectOptionDict] = []
    for lock in locks:
        annotations: list[str] = []
        if lock.get("code_length"):
            annotations.append(f"code len: {lock['code_length']}")
        if lock.get("slots"):
            annotations.append(f"Slots: {lock['slots']}")
        if annotations:
            label = f"{lock['name']} ({', '.join(annotations)})"
        else:
            label = lock["name"] or lock["entity_id"]
        options.append(SelectOptionDict(value=lock["entity_id"], label=label))
    return options


def _build_lock_options_plain(locks: list[dict[str, Any]]) -> list[SelectOptionDict]:
    """Convert lock dicts to SelectOptionDicts without annotations."""
    return [
        SelectOptionDict(
            value=lock["entity_id"],
            label=lock["name"] or lock["entity_id"],
        )
        for lock in locks
    ]


def _get_zwave_node(hass: HomeAssistant, entity_id: str):
    """Return the Z-Wave JS node object for an entity.

    Handles varying return types across HA versions.
    """
    from homeassistant.components.zwave_js.helpers import (
        async_get_node_from_entity_id,
    )

    node_info = async_get_node_from_entity_id(hass, entity_id)
    return node_info[0] if isinstance(node_info, tuple) else node_info


async def _async_get_max_user_codes(
    hass: HomeAssistant, entity_id: str
) -> int | None:
    """Query the Z-Wave node cache for the supported number of code slots.

    Scans cached ``userIdStatus`` values to find the highest slot number
    present (gap-tolerant). Returns None if nothing found so the config
    flow can ask the user.
    """
    _SCAN_LIMIT = 50  # well above any residential lock capacity
    t0 = time.monotonic()
    try:
        node = _get_zwave_node(hass, entity_id)
        from zwave_js_server.util.node import get_value_id_str

        max_found = 0
        for slot in range(1, _SCAN_LIMIT + 1):
            value_id = get_value_id_str(
                node, 99, "userIdStatus", endpoint=0, property_key=slot,
            )
            if value_id in node.values:
                max_found = slot

        if max_found > 0:
            capped = min(max_found, MAX_SLOTS)
            _LOGGER.info(
                "PERF %s: node value scan found highest slot %d in %.3fs",
                entity_id, capped, time.monotonic() - t0,
            )
            return capped
        _LOGGER.info(
            "PERF %s: node value scan found no slots in %.3fs",
            entity_id, time.monotonic() - t0,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "PERF %s: node value scan failed after %.3fs",
            entity_id, time.monotonic() - t0,
            exc_info=True,
        )

    _LOGGER.warning(
        "Could not discover slot count for %s via any method", entity_id,
    )
    return None


async def _async_probe_lock_readback(
    hass: HomeAssistant, entity_id: str
) -> bool:
    """Return True if the lock can return actual PIN digits for a code slot.

    Reads ``userCode`` and ``userIdStatus`` values directly from the Z-Wave
    JS node cache for slots 1–5 (to handle empty slot 1). If any occupied
    slot has actual digits, readback is supported. If any has asterisks,
    the lock masks codes (not readable).
    """
    try:
        node = _get_zwave_node(hass, entity_id)
        from zwave_js_server.util.node import get_value_id_str

        for slot in range(1, 6):
            status_vid = get_value_id_str(
                node, 99, "userIdStatus", endpoint=0, property_key=slot,
            )
            code_vid = get_value_id_str(
                node, 99, "userCode", endpoint=0, property_key=slot,
            )

            status_val = node.values.get(status_vid)
            code_val = node.values.get(code_vid)

            if status_val is None:
                continue

            user_status = (
                status_val.value
                if hasattr(status_val, "value")
                else status_val
            )
            if isinstance(user_status, dict):
                user_status = user_status.get("value", 0)
            if not user_status or user_status == 0:
                continue

            # Slot is occupied — check the code value.
            user_code = (
                code_val.value if hasattr(code_val, "value") else code_val
            ) if code_val is not None else None

            if user_code and "*" in str(user_code):
                _LOGGER.info(
                    "Lock %s returns masked codes (asterisks, slot %d) "
                    "— not readable",
                    entity_id, slot,
                )
                return False

            if user_code and str(user_code).strip():
                code_str = str(user_code).strip()
                if code_str.isdigit():
                    _LOGGER.info(
                        "Lock %s supports full readback "
                        "(slot %d returned digits)",
                        entity_id, slot,
                    )
                    return True

        _LOGGER.debug(
            "Lock %s: no occupied slots found in 1–5 — readback unknown",
            entity_id,
        )
        return False
    except Exception:  # noqa: BLE001
        _LOGGER.debug(
            "Readback probe failed for %s", entity_id, exc_info=True,
        )
        return False


async def _async_read_lock_codes(
    hass: HomeAssistant, entity_id: str, max_slots: int,
) -> dict[int, str]:
    """Read all occupied code slots from a lock via the Z-Wave node cache.

    Returns a dict of ``{slot_number: code_string}`` for all slots that
    contain actual digit codes (not empty, not masked).
    """
    codes: dict[int, str] = {}

    try:
        node = _get_zwave_node(hass, entity_id)
        from zwave_js_server.util.node import get_value_id_str

        for slot_num in range(1, max_slots + 1):
            status_vid = get_value_id_str(
                node, 99, "userIdStatus", endpoint=0, property_key=slot_num,
            )
            code_vid = get_value_id_str(
                node, 99, "userCode", endpoint=0, property_key=slot_num,
            )

            status_val = node.values.get(status_vid)
            code_val = node.values.get(code_vid)

            if status_val is None:
                continue

            user_status = (
                status_val.value
                if hasattr(status_val, "value")
                else status_val
            )
            if isinstance(user_status, dict):
                user_status = user_status.get("value", 0)
            if not user_status or user_status == 0:
                continue

            user_code = (
                code_val.value if hasattr(code_val, "value") else code_val
            ) if code_val is not None else None

            if (
                user_code
                and isinstance(str(user_code), str)
                and str(user_code).strip().isdigit()
            ):
                codes[slot_num] = str(user_code).strip()
                _LOGGER.debug(
                    "Read code from %s slot %d (len=%d)",
                    entity_id,
                    slot_num,
                    len(codes[slot_num]),
                )
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Failed to read codes from %s via node cache",
            entity_id,
            exc_info=True,
        )

    _LOGGER.info(
        "Read %d occupied code(s) from %s (scanned %d slots)",
        len(codes),
        entity_id,
        max_slots,
    )
    return codes


def _get_lock_default_code_length(
    discovered: dict[str, int | None], entity_id: str,
) -> int | None:
    """Return the default code length for a lock from discovery data.

    Returns None when the code length was not discovered, so the UI can
    show a placeholder prompting the user to select manually.
    """
    val = discovered.get(entity_id)
    if val is not None and MIN_CODE_LENGTH <= val <= MAX_CODE_LENGTH:
        return val
    return None


def _get_lock_name(hass: HomeAssistant, entity_id: str) -> str:
    """Resolve a lock entity_id to its friendly name."""
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry:
        return entry.name or entry.original_name or entity_id
    return entity_id


# ---------------------------------------------------------------------------
# Config Flow
# ---------------------------------------------------------------------------


class SlotSentryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SlotSentry.

    Steps:
        user               — Welcome screen.
        locks              — Discover locks (with capabilities), select locks.
        lock_code_lengths  — Per-lock code length dropdown (auto-detects single/dual).
        seed               — Optional: seed slot data from a readable lock.
        lockout            — Optional keypad lockout with multi-state trigger.
        secure_mode        — Optional Secure Mode toggle.
        confirm            — Full configuration summary.
    """

    VERSION = 2

    def __init__(self) -> None:
        """Initialise flow state."""
        self._available_locks: list[dict[str, Any]] = []
        self._lock_entities: list[str] = []
        self._slot_count: int = 0
        self._discovered_code_lengths: dict[str, int | None] = {}
        self._discovery_ok: bool = True

        self._code_length_mode: str = CODE_LENGTH_SINGLE
        self._code_length_1: int = DEFAULT_CODE_LENGTH
        self._code_length_2: int | None = None
        self._per_lock_code_length: dict[str, int] = {}

        # Seed from existing lock
        self._readable_locks: dict[str, dict[int, str]] = {}
        self._seed_slots: list[dict[str, Any]] = []
        self._seed_lock_names: list[str] = []  # friendly names of chosen seed locks

        self._lockout_enabled: bool = False
        self._lockout_trigger_entity: str | None = None
        self._lockout_target_states: list[str] = []
        self._lockout_participating_locks: list[str] = []

        self._secure_mode: bool = False
        self._secure_password: str = ""

    # ------------------------------------------------------------------
    # Step 1: Welcome
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the welcome screen."""
        self._async_abort_entries_match({})

        if user_input is not None:
            return await self.async_step_locks()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            last_step=False,
            description_placeholders={"version": VERSION},
        )

    # ------------------------------------------------------------------
    # Step 2: Lock Discovery, Selection & Code Length Mode
    # ------------------------------------------------------------------

    async def async_step_locks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover Z-Wave locks with capabilities and let user select which to manage.

        This step shows a lock selector with annotations:
        "Lock Name (code len: N, Slots: NN)".
        """
        # Discover and probe all locks on first visit (or re-entry).
        if not self._available_locks:
            t_discovery = time.monotonic()
            _LOGGER.info("PERF: Starting full lock discovery...")
            raw_locks = _discover_zwave_locks(self.hass)
            if not raw_locks:
                _LOGGER.info(
                    "PERF: No Z-Wave locks found (%.3fs)",
                    time.monotonic() - t_discovery,
                )
                return self.async_abort(reason="no_zwave_locks")
            self._available_locks = await _async_discover_lock_capabilities(
                self.hass, raw_locks
            )
            _LOGGER.info(
                "PERF: Full lock discovery complete: %d locks in %.3fs",
                len(self._available_locks), time.monotonic() - t_discovery,
            )

        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_LOCK_ENTITIES, [])

            if not selected:
                errors[CONF_LOCK_ENTITIES] = "no_locks_selected"
            else:
                self._lock_entities = selected

                # Compute slot count from discovered data.
                slot_counts = [
                    lock["slots"]
                    for lock in self._available_locks
                    if lock["entity_id"] in selected and lock.get("slots")
                ]
                self._slot_count = min(slot_counts) if slot_counts else 30
                if not slot_counts:
                    _LOGGER.warning(
                        "Could not determine slot count for selected locks; "
                        "using default 30"
                    )
                else:
                    _LOGGER.info(
                        "Slot count: %d (min of %s)",
                        self._slot_count,
                        slot_counts,
                    )

                # Build code length discovery from already-probed data.
                self._discovered_code_lengths = {
                    lock["entity_id"]: lock.get("code_length")
                    for lock in self._available_locks
                    if lock["entity_id"] in selected
                }

                # If slot count discovery failed, ask the user.
                if not slot_counts:
                    return await self.async_step_slot_count()

                return await self.async_step_lock_code_lengths()

        # Build lock options with capability annotations.
        lock_options = _build_lock_options(self._available_locks)
        default_ids = (
            self._lock_entities
            if self._lock_entities
            else [lock["entity_id"] for lock in self._available_locks]
        )

        # Build description notice.
        if all(lock.get("code_length") for lock in self._available_locks):
            discovery_notice = (
                "Code lengths and slot counts detected from your locks."
            )
        elif any(lock.get("code_length") for lock in self._available_locks):
            discovery_notice = (
                "Some locks reported their capabilities. "
                "Others may need manual verification."
            )
        else:
            discovery_notice = (
                "Could not auto-detect code lengths. "
                "Please verify against your lock specifications."
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCK_ENTITIES, default=default_ids
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=lock_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="locks",
            data_schema=schema,
            errors=errors,
            last_step=False,
            description_placeholders={"discovery_notice": discovery_notice},
        )

    # ------------------------------------------------------------------
    # Step 2b: Slot Count (shown only when auto-discovery fails)
    # ------------------------------------------------------------------

    async def async_step_slot_count(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user manually set the slot count when auto-discovery fails."""
        if user_input is not None:
            self._slot_count = int(user_input.get(CONF_SLOT_COUNT, 30))
            return await self.async_step_lock_code_lengths()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SLOT_COUNT, default=self._slot_count or 30
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=MAX_SLOTS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="slot_count",
            data_schema=schema,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Step 3: Per-Lock Code Length Selection
    # ------------------------------------------------------------------

    async def async_step_lock_code_lengths(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a per-lock code length dropdown for each selected lock.

        Each lock gets a dropdown with options 4–8 digits, pre-populated
        from discovery data. After submission, the distinct selected lengths
        determine single vs dual mode:
          - 1 distinct length → single mode (code_length_1 = that length)
          - 2 distinct lengths → dual mode (shorter → code_length_1,
            longer → code_length_2)
          - >2 distinct lengths → error (max 2 supported)
        """
        # Build code length options (4–8 digits) with placeholder.
        _PLACEHOLDER_VALUE = ""
        code_len_options = [
            SelectOptionDict(value=_PLACEHOLDER_VALUE, label="Select PIN length"),
        ] + [
            SelectOptionDict(value=str(n), label=f"{n} digits")
            for n in range(MIN_CODE_LENGTH, MAX_CODE_LENGTH + 1)
        ]

        errors: dict[str, str] = {}

        if user_input is not None:
            # Collect per-lock code lengths.
            per_lock: dict[str, int] = {}
            has_unselected = False
            for eid in self._lock_entities:
                field_key = f"code_length_{eid}"
                val = user_input.get(field_key)
                if val is not None and val != _PLACEHOLDER_VALUE:
                    per_lock[eid] = int(val)
                else:
                    has_unselected = True

            if has_unselected:
                errors["base"] = "no_code_length_selected"
            else:
                distinct = sorted(set(per_lock.values()))

                if len(distinct) > 2:
                    errors["base"] = "too_many_code_lengths"
                else:
                    self._per_lock_code_length = per_lock

                    if len(distinct) == 1:
                        self._code_length_mode = CODE_LENGTH_SINGLE
                        self._code_length_1 = distinct[0]
                        self._code_length_2 = None
                    else:
                        self._code_length_mode = CODE_LENGTH_DUAL
                        self._code_length_1 = distinct[0]  # shorter
                        self._code_length_2 = distinct[1]  # longer

                    _LOGGER.info(
                        "Code lengths: mode=%s, cl1=%s, cl2=%s, per_lock=%s",
                        self._code_length_mode,
                        self._code_length_1,
                        self._code_length_2,
                        self._per_lock_code_length,
                    )
                    return await self.async_step_seed()

        # Build schema with one dropdown per lock.
        schema_fields: dict[Any, Any] = {}
        for eid in self._lock_entities:
            name = _get_lock_name(self.hass, eid)
            field_key = f"code_length_{eid}"

            # Use previously selected value or discovery default.
            if eid in self._per_lock_code_length:
                default_val = str(self._per_lock_code_length[eid])
            else:
                disc = _get_lock_default_code_length(
                    self._discovered_code_lengths, eid,
                )
                default_val = str(disc) if disc is not None else _PLACEHOLDER_VALUE

            schema_fields[
                vol.Required(field_key, default=default_val)
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=code_len_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="lock_code_lengths",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Step 4: Seed From Existing Lock (optional)
    # ------------------------------------------------------------------

    async def async_step_seed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionally seed slot data by reading codes from an existing lock.

        Probes each selected lock for readback support, reads codes from
        readable locks, and presents dropdown(s) to the user.

        Single code length mode: one dropdown.
        Dual code length mode: two dropdowns (one per code length).

        Selecting "None" (the default) skips seeding.
        """
        _NONE_VALUE = "__none__"

        # On first visit, probe locks and read codes.
        if not self._readable_locks:
            await self._async_discover_readable_locks()

        if user_input is not None:
            self._seed_slots = []
            self._seed_lock_names = []

            if self._code_length_mode == CODE_LENGTH_DUAL:
                seed_1 = user_input.get("seed_lock_1", _NONE_VALUE)
                seed_2 = user_input.get("seed_lock_2", _NONE_VALUE)
                slot_num = 1

                if seed_1 != _NONE_VALUE:
                    self._seed_lock_names.append(
                        f"Code 1: {_get_lock_name(self.hass, seed_1)}"
                    )
                if seed_2 != _NONE_VALUE:
                    self._seed_lock_names.append(
                        f"Code 2: {_get_lock_name(self.hass, seed_2)}"
                    )

                # Seed code_1 (shorter code length).
                if seed_1 != _NONE_VALUE and seed_1 in self._readable_locks:
                    codes = self._readable_locks[seed_1]
                    for _orig_slot, code in sorted(codes.items()):
                        if len(code) == self._code_length_1:
                            self._seed_slots.append({
                                "slot_number": slot_num,
                                "code_1": code,
                                "code_2": "",
                                "label": "",
                                "enabled": True,
                            })
                            slot_num += 1
                            if slot_num > self._slot_count:
                                break

                # Seed code_2 (longer code length) — merge or append.
                if seed_2 != _NONE_VALUE and seed_2 in self._readable_locks:
                    codes = self._readable_locks[seed_2]
                    idx = 0
                    for _orig_slot, code in sorted(codes.items()):
                        if self._code_length_2 is not None and len(code) == self._code_length_2:
                            if idx < len(self._seed_slots):
                                self._seed_slots[idx]["code_2"] = code
                            else:
                                sn = len(self._seed_slots) + 1
                                if sn <= self._slot_count:
                                    self._seed_slots.append({
                                        "slot_number": sn,
                                        "code_1": "",
                                        "code_2": code,
                                        "label": "",
                                        "enabled": True,
                                    })
                            idx += 1
                            if len(self._seed_slots) >= self._slot_count:
                                break
            else:
                # Single mode.
                seed_lock = user_input.get("seed_lock", _NONE_VALUE)
                if seed_lock != _NONE_VALUE:
                    self._seed_lock_names.append(
                        _get_lock_name(self.hass, seed_lock)
                    )
                if seed_lock != _NONE_VALUE and seed_lock in self._readable_locks:
                    codes = self._readable_locks[seed_lock]
                    slot_num = 1
                    for _orig_slot, code in sorted(codes.items()):
                        if len(code) == self._code_length_1:
                            self._seed_slots.append({
                                "slot_number": slot_num,
                                "code_1": code,
                                "code_2": "",
                                "label": "",
                                "enabled": True,
                            })
                            slot_num += 1
                            if slot_num > self._slot_count:
                                break

            if self._seed_slots:
                _LOGGER.info(
                    "Seed: %d slot(s) will be pre-populated from lock data",
                    len(self._seed_slots),
                )
            return await self.async_step_lockout()

        # Build dropdown options.
        # When viable locks exist, default to the first one (not "None").
        # Include "None" only as an opt-out when there are viable choices.
        none_option = SelectOptionDict(value=_NONE_VALUE, label="None")
        no_locks_option = SelectOptionDict(
            value=_NONE_VALUE, label="None Available"
        )

        if self._code_length_mode == CODE_LENGTH_DUAL:
            viable_1: list[SelectOptionDict] = []
            viable_2: list[SelectOptionDict] = []

            for eid, codes in self._readable_locks.items():
                name = _get_lock_name(self.hass, eid)
                codes_1 = [c for c in codes.values()
                           if len(c) == self._code_length_1]
                codes_2 = [c for c in codes.values()
                           if self._code_length_2 is not None
                           and len(c) == self._code_length_2]
                if codes_1:
                    viable_1.append(SelectOptionDict(
                        value=eid,
                        label=f"{name} ({len(codes_1)} codes, "
                              f"{self._code_length_1} digits)",
                    ))
                if codes_2:
                    viable_2.append(SelectOptionDict(
                        value=eid,
                        label=f"{name} ({len(codes_2)} codes, "
                              f"{self._code_length_2} digits)",
                    ))

            if viable_1:
                options_1 = viable_1 + [none_option]
                default_1 = viable_1[0]["value"]
            else:
                options_1 = [no_locks_option]
                default_1 = _NONE_VALUE

            if viable_2:
                options_2 = viable_2 + [none_option]
                default_2 = viable_2[0]["value"]
            else:
                options_2 = [no_locks_option]
                default_2 = _NONE_VALUE

            schema = vol.Schema({
                vol.Required(
                    "seed_lock_1", default=default_1
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options_1,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    "seed_lock_2", default=default_2
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options_2,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            })
        else:
            # Single mode — one dropdown.
            viable_single: list[SelectOptionDict] = []

            for eid, codes in self._readable_locks.items():
                name = _get_lock_name(self.hass, eid)
                matching = [c for c in codes.values()
                            if len(c) == self._code_length_1]
                if matching:
                    viable_single.append(SelectOptionDict(
                        value=eid,
                        label=f"{name} ({len(matching)} codes, "
                              f"{self._code_length_1} digits)",
                    ))

            if viable_single:
                lock_options = viable_single + [none_option]
                default_single = viable_single[0]["value"]
            else:
                lock_options = [no_locks_option]
                default_single = _NONE_VALUE

            schema = vol.Schema({
                vol.Required(
                    "seed_lock", default=default_single
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=lock_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            })

        placeholders: dict[str, str] = {
            "code_length_1": str(self._code_length_1),
            "code_length_2": str(self._code_length_2) if self._code_length_2 else "N/A",
        }

        return self.async_show_form(
            step_id="seed",
            data_schema=schema,
            last_step=False,
            description_placeholders=placeholders,
        )

    async def _async_discover_readable_locks(self) -> None:
        """Probe each selected lock for readback support and read codes.

        Populates ``self._readable_locks`` with ``{entity_id: {slot: code}}``.
        """
        self._readable_locks = {}

        for lock in self._available_locks:
            eid = lock["entity_id"]
            if eid not in self._lock_entities:
                continue

            max_slots = lock.get("slots") or self._slot_count or 30
            _LOGGER.info("Probing %s for readback support...", eid)

            readable = await _async_probe_lock_readback(self.hass, eid)
            if not readable:
                _LOGGER.info("Lock %s does not support readback, skipping", eid)
                continue

            _LOGGER.info(
                "Lock %s supports readback — reading up to %d slots",
                eid,
                max_slots,
            )
            codes = await _async_read_lock_codes(self.hass, eid, max_slots)
            if codes:
                self._readable_locks[eid] = codes

    # ------------------------------------------------------------------
    # Step 5: Keypad Lockout (optional, multi-state)
    # ------------------------------------------------------------------

    async def async_step_lockout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure optional keypad lockout trigger with multiple states.

        Validation matrix (toggle × trigger × state):
          OFF + no trigger + no state         → proceed (lockout disabled)
          OFF + trigger or state present       → error: turn on toggle or remove
          ON  + trigger + state + participating → proceed (lockout enabled)
          ON  + missing any required field      → error: specific field errors
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled: bool = user_input.get(CONF_LOCKOUT_ENABLED, False)
            trigger_entity = user_input.get(CONF_LOCKOUT_TRIGGER_ENTITY)
            target_states: list[str] = user_input.get(
                CONF_LOCKOUT_TARGET_STATES, []
            )
            participating: list[str] = user_input.get(
                CONF_LOCKOUT_PARTICIPATING_LOCKS, []
            )

            has_trigger = bool(trigger_entity)
            has_states = bool(target_states)

            _LOGGER.debug(
                "Lockout step: enabled=%s, trigger=%s, states=%s, "
                "participating=%s, has_trigger=%s, has_states=%s",
                enabled, trigger_entity, target_states,
                participating, has_trigger, has_states,
            )

            if enabled:
                # Toggle ON — all three fields required.
                if not has_trigger:
                    errors[CONF_LOCKOUT_TRIGGER_ENTITY] = "no_lockout_trigger"
                if not has_states:
                    errors[CONF_LOCKOUT_TARGET_STATES] = "no_lockout_states"
                if not participating:
                    errors[CONF_LOCKOUT_PARTICIPATING_LOCKS] = "no_lockout_locks"
                if errors:
                    errors["base"] = "lockout_incomplete"
                else:
                    self._lockout_enabled = True
                    self._lockout_trigger_entity = trigger_entity
                    self._lockout_target_states = target_states
                    self._lockout_participating_locks = participating
                    return await self.async_step_secure_mode()
            else:
                # Toggle OFF → disabled, proceed. Any filled fields are
                # silently ignored (the toggle is the authoritative switch).
                self._lockout_enabled = False
                self._lockout_trigger_entity = None
                self._lockout_target_states = []
                self._lockout_participating_locks = []
                return await self.async_step_secure_mode()

            _LOGGER.warning("Lockout validation errors: %s", errors)

        # Build lock options (plain names — no capability annotations).
        lock_labels: list[dict[str, Any]] = []
        for eid in self._lock_entities:
            name = _get_lock_name(self.hass, eid)
            lock_labels.append({"entity_id": eid, "name": name})

        participating_options = _build_lock_options_plain(lock_labels)

        state_options: list[SelectOptionDict] = [
            SelectOptionDict(value=s, label=s) for s in _LOCKOUT_STATE_SUGGESTIONS
        ]

        # Preserve user input on re-render after validation errors.
        if user_input is not None:
            default_enabled = user_input.get(CONF_LOCKOUT_ENABLED, self._lockout_enabled)
            default_trigger = user_input.get(CONF_LOCKOUT_TRIGGER_ENTITY)
            default_states = user_input.get(CONF_LOCKOUT_TARGET_STATES, [])
            default_participating = user_input.get(
                CONF_LOCKOUT_PARTICIPATING_LOCKS, list(self._lock_entities)
            )
        else:
            default_enabled = self._lockout_enabled
            default_trigger = self._lockout_trigger_entity
            default_states = self._lockout_target_states or []
            default_participating = (
                self._lockout_participating_locks or list(self._lock_entities)
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCKOUT_ENABLED, default=default_enabled
                ): BooleanSelector(),
                vol.Optional(
                    CONF_LOCKOUT_TRIGGER_ENTITY,
                    description={"suggested_value": default_trigger},
                ): EntitySelector(
                    EntitySelectorConfig()
                ),
                vol.Optional(
                    CONF_LOCKOUT_TARGET_STATES,
                    default=default_states,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=state_options,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_LOCKOUT_PARTICIPATING_LOCKS,
                    default=default_participating,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=participating_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="lockout",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Step 5: Secure Mode (optional)
    # ------------------------------------------------------------------

    async def async_step_secure_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionally enable Secure Mode for PIN code storage encryption.

        When enabled, password + password confirm are required on the same form.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = user_input.get(CONF_SECURE_MODE, False)
            password = user_input.get("secure_password", "")
            password_confirm = user_input.get("secure_password_confirm", "")
            has_password_data = bool(password or password_confirm)

            if enabled:
                # Secure mode ON — require matching passwords >= 8 chars.
                if not password:
                    errors["secure_password"] = "password_required"
                elif len(password) < MIN_PASSWORD_LENGTH:
                    errors["secure_password"] = "password_too_short"
                elif len(password) > MAX_PASSWORD_LENGTH:
                    errors["secure_password"] = "password_too_long"
                elif password != password_confirm:
                    errors["secure_password_confirm"] = "password_mismatch"
                else:
                    self._secure_mode = True
                    self._secure_password = password
                    return await self.async_step_confirm()
            elif has_password_data:
                # Secure mode OFF but password fields not empty — user
                # must clear them or enable secure mode.
                errors["secure_password"] = "password_without_secure_mode"
            else:
                # Secure mode OFF, no password data — proceed.
                self._secure_mode = False
                return await self.async_step_confirm()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SECURE_MODE, default=self._secure_mode
                ): BooleanSelector(),
                vol.Optional("secure_password", default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional("secure_password_confirm", default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(
            step_id="secure_mode",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Step 6: Summary / Confirm
    # ------------------------------------------------------------------

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a read-only configuration summary."""
        if user_input is not None:
            return self._create_entry()

        lock_names: list[str] = [
            _get_lock_name(self.hass, eid) for eid in self._lock_entities
        ]
        lock_list = ", ".join(lock_names)

        if self._code_length_mode == CODE_LENGTH_DUAL:
            mode_label = "Two code lengths"
            lengths_detail = (
                f"Code 1 = {self._code_length_1} digits, "
                f"Code 2 = {self._code_length_2} digits"
            )
        else:
            mode_label = "Single code length"
            lengths_detail = f"{self._code_length_1} digits"

        if self._lockout_enabled and self._lockout_trigger_entity:
            states_str = ", ".join(self._lockout_target_states)
            lockout_summary = (
                f"Enabled — Trigger: {self._lockout_trigger_entity} "
                f"— Active when: {states_str}"
            )
        elif self._lockout_enabled:
            lockout_summary = "Enabled (no trigger entity configured)"
        else:
            lockout_summary = "Disabled"

        seed_summary = (
            ", ".join(self._seed_lock_names)
            if self._seed_lock_names
            else "None"
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            last_step=True,
            description_placeholders={
                "lock_count": str(len(self._lock_entities)),
                "lock_list": lock_list,
                "slot_count": str(self._slot_count),
                "code_length_mode": mode_label,
                "code_lengths": lengths_detail,
                "seed_summary": seed_summary,
                "lockout_summary": lockout_summary,
                "secure_mode": "ON (encrypted)" if self._secure_mode else "OFF (plain text)",
            },
        )

    # ------------------------------------------------------------------
    # Entry creation
    # ------------------------------------------------------------------

    @callback
    def _create_entry(self) -> ConfigFlowResult:
        """Assemble the config entry data and create the entry."""
        data: dict[str, Any] = {
            CONF_LOCK_ENTITIES: self._lock_entities,
            CONF_SLOT_COUNT: self._slot_count,
            CONF_CODE_LENGTH_MODE: self._code_length_mode,
            CONF_CODE_LENGTH_1: self._code_length_1,
            CONF_CODE_LENGTH_2: self._code_length_2,
            CONF_PER_LOCK_CODE_LENGTH: self._per_lock_code_length,
            CONF_SECURE_MODE: self._secure_mode,
            CONF_LOCKOUT_ENABLED: self._lockout_enabled,
            CONF_LOCKOUT_TRIGGER_ENTITY: self._lockout_trigger_entity,
            CONF_LOCKOUT_TARGET_STATES: self._lockout_target_states,
            CONF_LOCKOUT_PARTICIPATING_LOCKS: self._lockout_participating_locks,
        }

        # Hash password and generate encryption salt when secure mode is on.
        if self._secure_mode and self._secure_password:
            from .crypto import hash_password as _hash_pw  # noqa: E402

            data[CONF_SECURE_PASSWORD_HASH] = _hash_pw(self._secure_password)
            data[CONF_SECURE_ENCRYPTION_SALT] = b64encode(
                os.urandom(16)
            ).decode("ascii")

        # Include seed data if the user chose to seed from a lock.
        if self._seed_slots:
            data["seed_slots"] = self._seed_slots

        _LOGGER.info(
            "Creating SlotSentry config entry: %d locks, %d slots, mode=%s, "
            "lockout=%s, seed_slots=%d",
            len(self._lock_entities),
            self._slot_count,
            self._code_length_mode,
            self._lockout_enabled,
            len(self._seed_slots),
        )

        return self.async_create_entry(title="SlotSentry", data=data)

    # ==================================================================
    # Reconfigure flow — modify existing entry (safe settings only)
    # ==================================================================

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point for the reconfigure flow.

        Allows changing: lock selection, lockout config, secure mode.
        Does NOT allow changing: code lengths, slot count (too destructive).

        Routes through: reconfig_locks → reconfig_lockout → reconfig_secure
        → applies changes to the existing entry.
        """
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")

        # Pre-populate flow state from the existing entry.
        self._lock_entities = list(entry.data.get(CONF_LOCK_ENTITIES, []))
        self._slot_count = int(entry.data.get(CONF_SLOT_COUNT, 0))
        self._code_length_mode = str(
            entry.data.get(CONF_CODE_LENGTH_MODE, CODE_LENGTH_SINGLE)
        )
        cl1 = entry.data.get(CONF_CODE_LENGTH_1)
        self._code_length_1 = int(cl1) if cl1 is not None else DEFAULT_CODE_LENGTH
        cl2 = entry.data.get(CONF_CODE_LENGTH_2)
        self._code_length_2 = int(cl2) if cl2 is not None else None
        self._per_lock_code_length = dict(
            entry.data.get(CONF_PER_LOCK_CODE_LENGTH, {})
        )
        self._lockout_enabled = bool(entry.data.get(CONF_LOCKOUT_ENABLED, False))
        self._lockout_trigger_entity = entry.data.get(CONF_LOCKOUT_TRIGGER_ENTITY)
        self._lockout_target_states = list(
            entry.data.get(CONF_LOCKOUT_TARGET_STATES, [])
        )
        self._lockout_participating_locks = list(
            entry.data.get(CONF_LOCKOUT_PARTICIPATING_LOCKS, [])
        )
        self._secure_mode = bool(entry.data.get(CONF_SECURE_MODE, False))

        # Snapshot originals so the confirm step can compute a diff.
        self._orig_lock_entities = list(self._lock_entities)
        self._orig_slot_count = self._slot_count
        self._orig_lockout_enabled = self._lockout_enabled
        self._orig_lockout_trigger_entity = self._lockout_trigger_entity
        self._orig_lockout_target_states = list(self._lockout_target_states)
        self._orig_lockout_participating_locks = list(
            self._lockout_participating_locks
        )
        self._orig_secure_mode = self._secure_mode

        return await self.async_step_reconfig_locks()

    # ------------------------------------------------------------------
    # Reconfig Step 1: Lock Selection (add/remove locks)
    # ------------------------------------------------------------------

    async def async_step_reconfig_locks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user add or remove locks from the managed set."""
        if not self._available_locks:
            raw_locks = _discover_zwave_locks(self.hass)
            if not raw_locks:
                return self.async_abort(reason="no_zwave_locks")
            self._available_locks = await _async_discover_lock_capabilities(
                self.hass, raw_locks
            )

        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_LOCK_ENTITIES, [])
            if not selected:
                errors[CONF_LOCK_ENTITIES] = "no_locks_selected"
            else:
                self._lock_entities = selected

                # Recompute slot count from selected locks.
                slot_counts = [
                    lock["slots"]
                    for lock in self._available_locks
                    if lock["entity_id"] in selected and lock.get("slots")
                ]
                if slot_counts:
                    new_slot_count = min(slot_counts)
                    # Only increase slot count, never decrease (would lose data).
                    if new_slot_count > self._slot_count:
                        self._slot_count = new_slot_count
                        _LOGGER.info(
                            "Reconfigure: slot count increased to %d",
                            self._slot_count,
                        )

                return await self.async_step_reconfig_lockout()

        lock_options = _build_lock_options(self._available_locks)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCK_ENTITIES, default=self._lock_entities
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=lock_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfig_locks",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Reconfig Step 2: Keypad Lockout
    # ------------------------------------------------------------------

    async def async_step_reconfig_lockout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure keypad lockout settings.

        Reuses the same validation logic as the initial lockout step.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled: bool = user_input.get(CONF_LOCKOUT_ENABLED, False)
            trigger_entity = user_input.get(CONF_LOCKOUT_TRIGGER_ENTITY)
            target_states: list[str] = user_input.get(
                CONF_LOCKOUT_TARGET_STATES, []
            )
            participating: list[str] = user_input.get(
                CONF_LOCKOUT_PARTICIPATING_LOCKS, []
            )

            has_trigger = bool(trigger_entity)
            has_states = bool(target_states)

            if enabled:
                if not has_trigger:
                    errors[CONF_LOCKOUT_TRIGGER_ENTITY] = "no_lockout_trigger"
                if not has_states:
                    errors[CONF_LOCKOUT_TARGET_STATES] = "no_lockout_states"
                if not participating:
                    errors[CONF_LOCKOUT_PARTICIPATING_LOCKS] = "no_lockout_locks"
                if errors:
                    errors["base"] = "lockout_incomplete"
                else:
                    self._lockout_enabled = True
                    self._lockout_trigger_entity = trigger_entity
                    self._lockout_target_states = target_states
                    self._lockout_participating_locks = participating
                    return await self.async_step_reconfig_secure()
            else:
                self._lockout_enabled = False
                self._lockout_trigger_entity = None
                self._lockout_target_states = []
                self._lockout_participating_locks = []
                return await self.async_step_reconfig_secure()

        # Build form — same structure as initial lockout step.
        lock_labels: list[dict[str, Any]] = []
        for eid in self._lock_entities:
            name = _get_lock_name(self.hass, eid)
            lock_labels.append({"entity_id": eid, "name": name})

        participating_options = _build_lock_options_plain(lock_labels)
        state_options: list[SelectOptionDict] = [
            SelectOptionDict(value=s, label=s) for s in _LOCKOUT_STATE_SUGGESTIONS
        ]

        if user_input is not None:
            default_enabled = user_input.get(CONF_LOCKOUT_ENABLED, self._lockout_enabled)
            default_trigger = user_input.get(CONF_LOCKOUT_TRIGGER_ENTITY)
            default_states = user_input.get(CONF_LOCKOUT_TARGET_STATES, [])
            default_participating = user_input.get(
                CONF_LOCKOUT_PARTICIPATING_LOCKS, list(self._lock_entities)
            )
        else:
            default_enabled = self._lockout_enabled
            default_trigger = self._lockout_trigger_entity
            default_states = self._lockout_target_states or []
            default_participating = (
                self._lockout_participating_locks or list(self._lock_entities)
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCKOUT_ENABLED, default=default_enabled
                ): BooleanSelector(),
                vol.Optional(
                    CONF_LOCKOUT_TRIGGER_ENTITY,
                    description={"suggested_value": default_trigger},
                ): EntitySelector(
                    EntitySelectorConfig()
                ),
                vol.Optional(
                    CONF_LOCKOUT_TARGET_STATES,
                    default=default_states,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=state_options,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_LOCKOUT_PARTICIPATING_LOCKS,
                    default=default_participating,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=participating_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfig_lockout",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Reconfig Step 3: Secure Mode
    # ------------------------------------------------------------------

    async def async_step_reconfig_secure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure secure mode settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = user_input.get(CONF_SECURE_MODE, False)
            password = user_input.get("secure_password", "")
            password_confirm = user_input.get("secure_password_confirm", "")
            has_password_data = bool(password or password_confirm)

            if enabled:
                if not password:
                    errors["secure_password"] = "password_required"
                elif len(password) < MIN_PASSWORD_LENGTH:
                    errors["secure_password"] = "password_too_short"
                elif len(password) > MAX_PASSWORD_LENGTH:
                    errors["secure_password"] = "password_too_long"
                elif password != password_confirm:
                    errors["secure_password_confirm"] = "password_mismatch"
                else:
                    self._secure_mode = True
                    self._secure_password = password
                    return await self.async_step_reconfig_confirm()
            elif has_password_data:
                errors["secure_password"] = "password_without_secure_mode"
            else:
                self._secure_mode = False
                self._secure_password = ""
                return await self.async_step_reconfig_confirm()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SECURE_MODE, default=self._secure_mode
                ): BooleanSelector(),
                vol.Optional("secure_password", default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional("secure_password_confirm", default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfig_secure",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Reconfig Step 4: Review & Confirm (with warnings)
    # ------------------------------------------------------------------

    async def async_step_reconfig_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a summary of what changed and warn about consequences."""
        if user_input is not None:
            return self._apply_reconfigure()

        # --- Build change summary and warnings ---
        changes: list[str] = []
        warnings: list[str] = []

        # Lock changes
        orig_set = set(self._orig_lock_entities)
        new_set = set(self._lock_entities)
        added_locks = new_set - orig_set
        removed_locks = orig_set - new_set

        if added_locks:
            added_names = [_get_lock_name(self.hass, e) for e in added_locks]
            changes.append(f"Adding locks: {', '.join(added_names)}")
            warnings.append(
                "New locks will show all slots as out-of-sync until "
                "you push codes to them."
            )

        if removed_locks:
            removed_names = [_get_lock_name(self.hass, e) for e in removed_locks]
            changes.append(f"Removing locks: {', '.join(removed_names)}")
            warnings.append(
                "Removed locks will keep their existing PIN codes on "
                "the physical hardware. SlotSentry will stop managing "
                "them, but codes already programmed will remain active."
            )

        if self._slot_count != self._orig_slot_count:
            changes.append(
                f"Slot count: {self._orig_slot_count} → {self._slot_count}"
            )
            if self._slot_count > self._orig_slot_count:
                warnings.append(
                    f"Slot count increased from {self._orig_slot_count} to "
                    f"{self._slot_count}. New slots will be empty."
                )

        # Lockout changes
        if self._lockout_enabled != self._orig_lockout_enabled:
            if self._lockout_enabled:
                changes.append("Keypad lockout: Disabled → Enabled")
                warnings.append(
                    "Keypads may lock immediately if the trigger entity "
                    "is already in a target state."
                )
            else:
                changes.append("Keypad lockout: Enabled → Disabled")
                warnings.append(
                    "All lock keypads will become active immediately, "
                    "regardless of the former trigger entity state."
                )
        elif self._lockout_enabled:
            # Lockout stayed enabled — check for sub-changes.
            lockout_subchanges: list[str] = []
            if self._lockout_trigger_entity != self._orig_lockout_trigger_entity:
                lockout_subchanges.append("trigger entity changed")
            if sorted(self._lockout_target_states) != sorted(
                self._orig_lockout_target_states
            ):
                lockout_subchanges.append("target states changed")
            if sorted(self._lockout_participating_locks) != sorted(
                self._orig_lockout_participating_locks
            ):
                lockout_subchanges.append("participating locks changed")
                removed_from_lockout = set(
                    self._orig_lockout_participating_locks
                ) - set(self._lockout_participating_locks)
                if removed_from_lockout:
                    rem_names = [
                        _get_lock_name(self.hass, e)
                        for e in removed_from_lockout
                    ]
                    warnings.append(
                        f"Locks removed from lockout ({', '.join(rem_names)}) "
                        "will have their keypads re-enabled."
                    )
            if lockout_subchanges:
                changes.append(
                    f"Keypad lockout updated: {', '.join(lockout_subchanges)}"
                )

        # Secure mode changes
        if self._secure_mode != self._orig_secure_mode:
            if self._secure_mode:
                changes.append("Secure Mode: OFF → ON")
                warnings.append(
                    "PIN codes will be encrypted at rest. You will need "
                    "your password to access the SlotSentry panel."
                )
            else:
                changes.append("Secure Mode: ON → OFF")
                warnings.append(
                    "PIN codes will be stored in plain text. Anyone with "
                    "access to the HA server can read them."
                )

        # Build the description string
        if not changes:
            summary = "No changes detected. Click Submit to keep the current configuration."
        else:
            change_lines = "\n".join(f"- {c}" for c in changes)
            if warnings:
                warning_lines = "\n".join(f"⚠ {w}" for w in warnings)
                summary = (
                    f"The following changes will be applied:\n\n"
                    f"{change_lines}\n\n"
                    f"Please review these warnings:\n\n"
                    f"{warning_lines}"
                )
            else:
                summary = (
                    f"The following changes will be applied:\n\n"
                    f"{change_lines}"
                )

        return self.async_show_form(
            step_id="reconfig_confirm",
            data_schema=vol.Schema({}),
            last_step=True,
            description_placeholders={"changes_summary": summary},
        )

    # ------------------------------------------------------------------
    # Apply reconfigure changes
    # ------------------------------------------------------------------

    @callback
    def _apply_reconfigure(self) -> ConfigFlowResult:
        """Update the existing config entry with the reconfigured values."""
        data: dict[str, Any] = {
            CONF_LOCK_ENTITIES: self._lock_entities,
            CONF_SLOT_COUNT: self._slot_count,
            CONF_CODE_LENGTH_MODE: self._code_length_mode,
            CONF_CODE_LENGTH_1: self._code_length_1,
            CONF_CODE_LENGTH_2: self._code_length_2,
            CONF_PER_LOCK_CODE_LENGTH: self._per_lock_code_length,
            CONF_SECURE_MODE: self._secure_mode,
            CONF_LOCKOUT_ENABLED: self._lockout_enabled,
            CONF_LOCKOUT_TRIGGER_ENTITY: self._lockout_trigger_entity,
            CONF_LOCKOUT_TARGET_STATES: self._lockout_target_states,
            CONF_LOCKOUT_PARTICIPATING_LOCKS: self._lockout_participating_locks,
        }

        # Handle secure mode password hash and encryption salt.
        entry = self._get_reconfigure_entry()
        if self._secure_mode and self._secure_password:
            # New password — hash it and generate a fresh encryption salt.
            from .crypto import hash_password as _hash_pw  # noqa: E402

            data[CONF_SECURE_PASSWORD_HASH] = _hash_pw(self._secure_password)
            data[CONF_SECURE_ENCRYPTION_SALT] = b64encode(
                os.urandom(16)
            ).decode("ascii")
        elif self._secure_mode:
            # Secure mode stays on but password not changed — keep existing.
            data[CONF_SECURE_PASSWORD_HASH] = entry.data.get(
                CONF_SECURE_PASSWORD_HASH
            )
            data[CONF_SECURE_ENCRYPTION_SALT] = entry.data.get(
                CONF_SECURE_ENCRYPTION_SALT
            )
        else:
            # Secure mode off — clear password data.
            data[CONF_SECURE_PASSWORD_HASH] = None
            data[CONF_SECURE_ENCRYPTION_SALT] = None

        _LOGGER.info(
            "Reconfigure: updating entry with %d locks, lockout=%s, secure=%s",
            len(self._lock_entities),
            self._lockout_enabled,
            self._secure_mode,
        )

        return self.async_update_reload_and_abort(entry, data=data)
