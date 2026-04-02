"""SlotSentry config flow — multi-step setup wizard for Z-Wave lock code management.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.6
"""

from __future__ import annotations

import logging
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
    CONF_CODE_LENGTH_LONG,
    CONF_CODE_LENGTH_MODE,
    CONF_CODE_LENGTH_SHORT,
    CONF_CODE_LENGTH_SINGLE,
    CONF_LOCK_ENTITIES,
    CONF_LOCKOUT_ENABLED,
    CONF_LOCKOUT_PARTICIPATING_LOCKS,
    CONF_LOCKOUT_TARGET_STATES,
    CONF_LOCKOUT_TRIGGER_ENTITY,
    CONF_SECURE_MODE,
    CONF_SLOT_COUNT,
    DEFAULT_CODE_LENGTH_LONG,
    DEFAULT_CODE_LENGTH_SHORT,
    DEFAULT_CODE_LENGTH_SINGLE,
    DOMAIN,
    MAX_CODE_LENGTH,
    MAX_LONG_CODE_LENGTH,
    MAX_PASSWORD_LENGTH,
    MAX_SHORT_CODE_LENGTH,
    MAX_SLOTS,
    MIN_CODE_LENGTH,
    MIN_LONG_CODE_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_SHORT_CODE_LENGTH,
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
    return locks


async def _async_discover_lock_capabilities(
    hass: HomeAssistant, locks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Probe each lock for slot count and code length.

    Annotates each lock dict in-place with 'slots' and 'code_length' keys.
    Uses the Z-Wave User Code CC and searches for pin-length number entities
    on the same device.
    """
    registry = er.async_get(hass)

    for lock in locks:
        eid = lock["entity_id"]

        # --- Slot count via User Code CC ---
        lock["slots"] = await _async_get_max_user_codes(hass, eid)

        # --- Code length: try state attributes first ---
        code_len: int | None = None
        state = hass.states.get(eid)
        if state:
            min_len = state.attributes.get("usercode_min_length")
            if isinstance(min_len, int):
                code_len = min_len

        # Fallback: find a number.*pin_length entity on the same device.
        if code_len is None:
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

        lock["code_length"] = code_len
        _LOGGER.debug(
            "Lock %s: slots=%s, code_length=%s",
            eid,
            lock["slots"],
            lock["code_length"],
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


async def _async_get_max_user_codes(
    hass: HomeAssistant, entity_id: str
) -> int | None:
    """Query the Z-Wave User Code CC for the supported number of code slots.

    Two approaches, tried in order:
      1. invoke_cc_api with ``getUsersCount`` — sends a UserCodeCCUsersNumberGet
         command to the device and returns the count directly.
      2. Iterate cached node values — counts ``userIdStatus`` property keys
         already cached by Z-Wave JS from the node interview. No RF traffic.
    """
    # -- Approach 1: getUsersCount via CC API --
    try:
        response = await hass.services.async_call(
            "zwave_js",
            "invoke_cc_api",
            {
                "entity_id": entity_id,
                "command_class": 99,
                "endpoint": 0,
                "method_name": "getUsersCount",
                "parameters": [],
            },
            blocking=True,
            return_response=True,
        )
        if isinstance(response, dict):
            payload = response.get(entity_id, response)
            # getUsersCount returns a plain integer.
            if isinstance(payload, int) and payload > 0:
                _LOGGER.info(
                    "getUsersCount reports %d slots for %s", payload, entity_id,
                )
                return payload
            # Some versions may wrap in a dict.
            if isinstance(payload, dict):
                count = payload.get("supportedUsers")
                if isinstance(count, int) and count > 0:
                    _LOGGER.info(
                        "getUsersCount (dict) reports %d slots for %s",
                        count,
                        entity_id,
                    )
                    return count
    except Exception:  # noqa: BLE001
        _LOGGER.debug("getUsersCount CC API failed for %s", entity_id)

    # -- Approach 2: count cached userIdStatus values from the node --
    try:
        from homeassistant.components.zwave_js.helpers import (
            async_get_node_from_entity_id,
        )
        from zwave_js_server.util.node import get_value_id_str

        node_info = async_get_node_from_entity_id(hass, entity_id)
        # async_get_node_from_entity_id returns (node, ...) or just node
        # depending on HA version — handle both.
        node = node_info[0] if isinstance(node_info, tuple) else node_info

        slot = 1
        while slot <= 254:
            value_id = get_value_id_str(
                node, 99, "userIdStatus", endpoint=0, property_key=slot,
            )
            if value_id not in node.values:
                break
            slot += 1
        count = slot - 1
        if count > 0:
            _LOGGER.info(
                "Node value iteration found %d slots for %s", count, entity_id,
            )
            return count
    except Exception:  # noqa: BLE001
        _LOGGER.debug(
            "Node value iteration failed for %s", entity_id, exc_info=True,
        )

    _LOGGER.warning(
        "Could not discover slot count for %s via any method", entity_id,
    )
    return None



def _suggest_code_length_defaults(
    discovered: dict[str, int | None],
) -> tuple[bool, int, int, int, bool]:
    """Derive suggested code-length defaults from discovery.

    Returns: suggest_dual, default_single, default_short, default_long, discovery_ok
    """
    values = list(discovered.values())
    discovery_ok = all(v is not None for v in values)
    discovered_lengths: set[int] = {v for v in values if v is not None}

    if not discovery_ok or not discovered_lengths:
        return (
            False,
            DEFAULT_CODE_LENGTH_SINGLE,
            DEFAULT_CODE_LENGTH_SHORT,
            DEFAULT_CODE_LENGTH_LONG,
            False,
        )

    if len(discovered_lengths) == 1:
        length = next(iter(discovered_lengths))
        return (False, length, DEFAULT_CODE_LENGTH_SHORT, length, True)

    short = min(discovered_lengths)
    long_ = max(discovered_lengths)
    short = max(MIN_SHORT_CODE_LENGTH, min(MAX_SHORT_CODE_LENGTH, short))
    long_ = max(MIN_LONG_CODE_LENGTH, min(MAX_LONG_CODE_LENGTH, long_))
    if short >= long_:
        long_ = min(short + 1, MAX_LONG_CODE_LENGTH)
    return (True, DEFAULT_CODE_LENGTH_SINGLE, short, long_, True)


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
        user                — Welcome screen.
        locks               — Discover locks (with capabilities), select + mode toggle.
        code_length_single  — Single code length slider (if mode = single).
        code_length_dual    — Short + Long sliders (if mode = dual).
        lockout             — Optional keypad lockout with multi-state trigger.
        secure_mode         — Optional Secure Mode toggle.
        confirm             — Full configuration summary.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._available_locks: list[dict[str, Any]] = []
        self._lock_entities: list[str] = []
        self._slot_count: int = 0
        self._discovered_code_lengths: dict[str, int | None] = {}
        self._discovery_ok: bool = True

        self._code_length_mode: str = CODE_LENGTH_SINGLE
        self._code_length_single: int = DEFAULT_CODE_LENGTH_SINGLE
        self._code_length_short: int = DEFAULT_CODE_LENGTH_SHORT
        self._code_length_long: int = DEFAULT_CODE_LENGTH_LONG

        self._lockout_enabled: bool = False
        self._lockout_trigger_entity: str | None = None
        self._lockout_target_states: list[str] = []
        self._lockout_participating_locks: list[str] = []

        self._secure_mode: bool = False

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
        )

    # ------------------------------------------------------------------
    # Step 2: Lock Discovery, Selection & Code Length Mode
    # ------------------------------------------------------------------

    async def async_step_locks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover Z-Wave locks with capabilities, let user select and choose mode.

        This step shows:
          - Lock selector with annotations: "Lock Name (code len: N, Slots: NN)"
          - Code length mode toggle: single vs dual
          - Description with discovery results and mode explanation
        """
        # Discover and probe all locks on first visit (or re-entry).
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
            dual_mode: bool = user_input.get(CONF_CODE_LENGTH_MODE, False)

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

                self._code_length_mode = (
                    CODE_LENGTH_DUAL if dual_mode else CODE_LENGTH_SINGLE
                )

                # If slot count discovery failed, ask the user.
                if not slot_counts:
                    return await self.async_step_slot_count()

                if dual_mode:
                    return await self.async_step_code_length_dual()
                return await self.async_step_code_length_single()

        # Build lock options with capability annotations.
        lock_options = _build_lock_options(self._available_locks)
        default_ids = (
            self._lock_entities
            if self._lock_entities
            else [lock["entity_id"] for lock in self._available_locks]
        )

        # Suggest dual mode if locks have different code lengths.
        discovered_lengths = {
            lock.get("code_length")
            for lock in self._available_locks
            if lock.get("code_length") is not None
        }
        suggest_dual = len(discovered_lengths) > 1
        if self._code_length_mode == CODE_LENGTH_DUAL:
            suggest_dual = True

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
                vol.Required(
                    CONF_CODE_LENGTH_MODE, default=suggest_dual
                ): BooleanSelector(),
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
            if self._code_length_mode == CODE_LENGTH_DUAL:
                return await self.async_step_code_length_dual()
            return await self.async_step_code_length_single()

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
    # Step 3b: Single Code Length slider
    # ------------------------------------------------------------------

    async def async_step_code_length_single(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a single code length slider."""
        (
            _suggest_dual,
            default_single,
            _default_short,
            _default_long,
            _discovery_ok,
        ) = _suggest_code_length_defaults(self._discovered_code_lengths)

        # Restore previous value on back-navigation.
        if self._code_length_single != DEFAULT_CODE_LENGTH_SINGLE:
            default_single = self._code_length_single

        if user_input is not None:
            self._code_length_single = int(
                user_input.get(CONF_CODE_LENGTH_SINGLE, default_single)
            )
            self._code_length_short = DEFAULT_CODE_LENGTH_SHORT
            self._code_length_long = DEFAULT_CODE_LENGTH_LONG
            return await self.async_step_lockout()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CODE_LENGTH_SINGLE, default=default_single
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_CODE_LENGTH,
                        max=MAX_CODE_LENGTH,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="digits",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="code_length_single",
            data_schema=schema,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Step 3c: Dual Code Length sliders (Short + Long)
    # ------------------------------------------------------------------

    async def async_step_code_length_dual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show short and long code length sliders."""
        (
            _suggest_dual,
            _default_single,
            default_short,
            default_long,
            _discovery_ok,
        ) = _suggest_code_length_defaults(self._discovered_code_lengths)

        # Restore previous values on back-navigation.
        if self._code_length_short != DEFAULT_CODE_LENGTH_SHORT:
            default_short = self._code_length_short
        if self._code_length_long != DEFAULT_CODE_LENGTH_LONG:
            default_long = self._code_length_long

        errors: dict[str, str] = {}

        if user_input is not None:
            short = int(user_input.get(CONF_CODE_LENGTH_SHORT, default_short))
            long_ = int(user_input.get(CONF_CODE_LENGTH_LONG, default_long))
            if short >= long_:
                errors[CONF_CODE_LENGTH_SHORT] = "short_gte_long"
            else:
                self._code_length_short = short
                self._code_length_long = long_
                self._code_length_single = DEFAULT_CODE_LENGTH_SINGLE
                return await self.async_step_lockout()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CODE_LENGTH_SHORT, default=default_short
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SHORT_CODE_LENGTH,
                        max=MAX_SHORT_CODE_LENGTH,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="digits",
                    )
                ),
                vol.Required(
                    CONF_CODE_LENGTH_LONG, default=default_long
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_LONG_CODE_LENGTH,
                        max=MAX_LONG_CODE_LENGTH,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="digits",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="code_length_dual",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ------------------------------------------------------------------
    # Step 4: Keypad Lockout (optional, multi-state)
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
            elif has_trigger or has_states:
                # Toggle OFF but fields filled — user must enable or clear.
                errors["base"] = "lockout_incomplete"
                if has_trigger:
                    errors[CONF_LOCKOUT_TRIGGER_ENTITY] = "lockout_incomplete"
                if has_states:
                    errors[CONF_LOCKOUT_TARGET_STATES] = "lockout_incomplete"
            else:
                # Toggle OFF, no trigger, no state → disabled, proceed.
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
            default_states = user_input.get(CONF_LOCKOUT_TARGET_STATES, [])
            default_participating = user_input.get(
                CONF_LOCKOUT_PARTICIPATING_LOCKS, list(self._lock_entities)
            )
        else:
            default_enabled = self._lockout_enabled
            default_states = self._lockout_target_states or []
            default_participating = (
                self._lockout_participating_locks or list(self._lock_entities)
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCKOUT_ENABLED, default=default_enabled
                ): BooleanSelector(),
                vol.Optional(CONF_LOCKOUT_TRIGGER_ENTITY): EntitySelector(
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
                    # Password will be hashed/stored during entry setup
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
                f"Short = {self._code_length_short} digits, "
                f"Long = {self._code_length_long} digits"
            )
        else:
            mode_label = "Single code length"
            lengths_detail = f"{self._code_length_single} digits"

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
            CONF_CODE_LENGTH_SINGLE: self._code_length_single,
            CONF_CODE_LENGTH_SHORT: self._code_length_short,
            CONF_CODE_LENGTH_LONG: self._code_length_long,
            CONF_SECURE_MODE: self._secure_mode,
            CONF_LOCKOUT_ENABLED: self._lockout_enabled,
            CONF_LOCKOUT_TRIGGER_ENTITY: self._lockout_trigger_entity,
            CONF_LOCKOUT_TARGET_STATES: self._lockout_target_states,
            CONF_LOCKOUT_PARTICIPATING_LOCKS: self._lockout_participating_locks,
        }

        _LOGGER.info(
            "Creating SlotSentry config entry: %d locks, %d slots, mode=%s, lockout=%s",
            len(self._lock_entities),
            self._slot_count,
            self._code_length_mode,
            self._lockout_enabled,
        )

        return self.async_create_entry(title="SlotSentry", data=data)
