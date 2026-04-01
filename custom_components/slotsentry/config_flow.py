"""SlotSentry config flow — multi-step setup wizard for Z-Wave lock code management.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.3
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
    MAX_SHORT_CODE_LENGTH,
    MAX_SLOTS,
    MIN_CODE_LENGTH,
    MIN_LONG_CODE_LENGTH,
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
                }
            )
    return locks


def _build_lock_options(locks: list[dict[str, Any]]) -> list[SelectOptionDict]:
    """Convert a list of lock dicts into voluptuous SelectOptionDicts."""
    return [
        SelectOptionDict(
            value=lock["entity_id"],
            label=lock["name"] or lock["entity_id"],
        )
        for lock in locks
    ]


def _estimate_slot_count(hass: HomeAssistant, entity_ids: list[str]) -> int:
    """Estimate slot count as the minimum across selected locks."""
    counts: list[int] = []
    for eid in entity_ids:
        state = hass.states.get(eid)
        if state is None:
            continue
        max_codes = state.attributes.get("max_user_codes")
        if isinstance(max_codes, int) and 1 <= max_codes <= MAX_SLOTS:
            counts.append(max_codes)
    if not counts:
        return 30
    return min(counts)


def _discover_code_lengths(
    hass: HomeAssistant, entity_ids: list[str]
) -> dict[str, int | None]:
    """Attempt to read code length attributes from each lock."""
    result: dict[str, int | None] = {}
    for eid in entity_ids:
        state = hass.states.get(eid)
        if state is None:
            result[eid] = None
            continue
        min_len = state.attributes.get("usercode_min_length")
        max_len = state.attributes.get("usercode_max_length")
        if isinstance(min_len, int) and isinstance(max_len, int):
            result[eid] = min_len
        else:
            result[eid] = None
    return result


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
        user        — Welcome screen.
        locks       — Discover and select Z-Wave lock entities.
        code_length — Code length mode toggle + all sliders on one form.
        lockout     — Optional keypad lockout with multi-state trigger.
        confirm     — Full configuration summary.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
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
    # Step 2: Lock Discovery & Selection
    # ------------------------------------------------------------------

    async def async_step_locks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover Z-Wave locks and let the user select which to manage."""
        available_locks = _discover_zwave_locks(self.hass)

        if not available_locks:
            return self.async_abort(reason="no_zwave_locks")

        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_LOCK_ENTITIES, [])

            if not selected:
                errors[CONF_LOCK_ENTITIES] = "no_locks_selected"
            else:
                self._lock_entities = selected
                self._slot_count = _estimate_slot_count(self.hass, selected)
                self._discovered_code_lengths = _discover_code_lengths(
                    self.hass, selected
                )
                return await self.async_step_code_length()

        lock_options = _build_lock_options(available_locks)
        default_ids = (
            self._lock_entities
            if self._lock_entities
            else [lock["entity_id"] for lock in available_locks]
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCK_ENTITIES, default=default_ids): SelectSelector(
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
        )

    # ------------------------------------------------------------------
    # Step 3: Code Length (all on one form)
    # ------------------------------------------------------------------

    async def async_step_code_length(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure code length mode and values on a single form.

        Shows a mode toggle plus all three sliders. The description explains
        which sliders apply. Validation uses the relevant values based on mode.
        """
        (
            suggest_dual,
            default_single,
            default_short,
            default_long,
            self._discovery_ok,
        ) = _suggest_code_length_defaults(self._discovered_code_lengths)

        # Restore previous selections on back-navigation.
        if self._code_length_mode == CODE_LENGTH_DUAL:
            suggest_dual = True
            if self._code_length_short != DEFAULT_CODE_LENGTH_SHORT:
                default_short = self._code_length_short
            if self._code_length_long != DEFAULT_CODE_LENGTH_LONG:
                default_long = self._code_length_long
        else:
            if self._code_length_single != DEFAULT_CODE_LENGTH_SINGLE:
                default_single = self._code_length_single

        errors: dict[str, str] = {}

        if user_input is not None:
            dual_mode: bool = user_input.get(CONF_CODE_LENGTH_MODE, False)

            if dual_mode:
                short = int(user_input.get(CONF_CODE_LENGTH_SHORT, default_short))
                long_ = int(user_input.get(CONF_CODE_LENGTH_LONG, default_long))
                if short >= long_:
                    errors[CONF_CODE_LENGTH_SHORT] = "short_gte_long"
                else:
                    self._code_length_mode = CODE_LENGTH_DUAL
                    self._code_length_short = short
                    self._code_length_long = long_
                    self._code_length_single = DEFAULT_CODE_LENGTH_SINGLE
                    return await self.async_step_lockout()
            else:
                single = int(
                    user_input.get(CONF_CODE_LENGTH_SINGLE, default_single)
                )
                self._code_length_mode = CODE_LENGTH_SINGLE
                self._code_length_single = single
                self._code_length_short = DEFAULT_CODE_LENGTH_SHORT
                self._code_length_long = DEFAULT_CODE_LENGTH_LONG
                return await self.async_step_lockout()

        if self._discovery_ok:
            notice = (
                "Code lengths detected from your locks. "
                "Defaults reflect what was found."
            )
        else:
            notice = (
                "Could not auto-detect code lengths for all locks. "
                "Please verify against your lock specifications."
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CODE_LENGTH_MODE, default=suggest_dual
                ): BooleanSelector(),
                vol.Optional(
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
                vol.Optional(
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
                vol.Optional(
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
            step_id="code_length",
            data_schema=schema,
            errors=errors,
            last_step=False,
            description_placeholders={"discovery_notice": notice},
        )

    # ------------------------------------------------------------------
    # Step 4: Keypad Lockout (optional, multi-state)
    # ------------------------------------------------------------------

    async def async_step_lockout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure optional keypad lockout trigger with multiple states."""
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled: bool = user_input.get(CONF_LOCKOUT_ENABLED, False)

            if enabled:
                trigger_entity = user_input.get(CONF_LOCKOUT_TRIGGER_ENTITY)
                target_states: list[str] = user_input.get(
                    CONF_LOCKOUT_TARGET_STATES, []
                )
                participating: list[str] = user_input.get(
                    CONF_LOCKOUT_PARTICIPATING_LOCKS, []
                )

                if not target_states:
                    errors[CONF_LOCKOUT_TARGET_STATES] = "no_lockout_states"
                elif not participating:
                    errors[CONF_LOCKOUT_PARTICIPATING_LOCKS] = "no_lockout_locks"
                else:
                    self._lockout_enabled = True
                    self._lockout_trigger_entity = trigger_entity or None
                    self._lockout_target_states = target_states
                    self._lockout_participating_locks = participating
                    return await self.async_step_confirm()
            else:
                self._lockout_enabled = False
                self._lockout_trigger_entity = None
                self._lockout_target_states = []
                self._lockout_participating_locks = []
                return await self.async_step_confirm()

        # Build lock options (plain names — no capability annotations).
        lock_labels: list[dict[str, Any]] = []
        for eid in self._lock_entities:
            name = _get_lock_name(self.hass, eid)
            lock_labels.append({"entity_id": eid, "name": name})

        participating_options = _build_lock_options(lock_labels)

        state_options: list[SelectOptionDict] = [
            SelectOptionDict(value=s, label=s) for s in _LOCKOUT_STATE_SUGGESTIONS
        ]

        default_states = self._lockout_target_states or []
        default_participating = (
            self._lockout_participating_locks or list(self._lock_entities)
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCKOUT_ENABLED, default=self._lockout_enabled
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
    # Step 5: Summary / Confirm
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
            last_step=False,
            description_placeholders={
                "lock_count": str(len(self._lock_entities)),
                "lock_list": lock_list,
                "slot_count": str(self._slot_count),
                "code_length_mode": mode_label,
                "code_lengths": lengths_detail,
                "lockout_summary": lockout_summary,
                "secure_mode": "OFF (plain text)",
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
            CONF_SECURE_MODE: False,
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
