"""SlotSentry config flow — multi-step setup wizard for Z-Wave lock code management.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.2
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

# Common state values presented in the lockout target state selector.
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
        SelectOptionDict(value=lock["entity_id"], label=lock["name"] or lock["entity_id"])
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
        return 30  # Conservative fallback
    return min(counts)


def _discover_code_lengths(
    hass: HomeAssistant, entity_ids: list[str]
) -> dict[str, int | None]:
    """Attempt to read code length attributes from each lock.

    Returns a dict keyed by entity_id; values are the detected code length
    or None when undiscoverable.
    """
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

    Returns:
        suggest_dual, default_single, default_short, default_long, discovery_ok
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


def _check_keypad_support(
    hass: HomeAssistant, lock_entity_ids: list[str]
) -> dict[str, str]:
    """Check each lock for keypad disable (Protection CC) support.

    Looks for select entities on the same device with 'protection' in the
    entity_id. Returns dict: entity_id -> "supported" | "unsupported" | "unknown"
    """
    registry = er.async_get(hass)
    result: dict[str, str] = {}

    # Build device_id -> set of entity_ids map for protection entities.
    protection_devices: set[str] = set()
    for entry in registry.entities.values():
        if (
            entry.domain == "select"
            and entry.device_id
            and "protection" in (entry.entity_id or "").lower()
        ):
            protection_devices.add(entry.device_id)

    for lock_eid in lock_entity_ids:
        lock_entry = registry.async_get(lock_eid)
        if lock_entry is None or lock_entry.device_id is None:
            result[lock_eid] = "unknown"
            continue

        if lock_entry.device_id in protection_devices:
            result[lock_eid] = "supported"
        else:
            state = hass.states.get(lock_eid)
            if state is None or state.state in ("unavailable", "unknown"):
                result[lock_eid] = "unknown"
            else:
                result[lock_eid] = "unsupported"

    return result


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
        user              — Welcome screen.
        locks             — Discover and select Z-Wave lock entities.
        code_length_mode  — Single vs. dual code length toggle.
        code_length_single — Single code length slider.
        code_length_dual  — Short + long code length sliders.
        lockout           — Optional keypad lockout with multi-state trigger.
        confirm           — Full configuration summary.
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
        self._lock_keypad_support: dict[str, str] = {}

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
                self._lock_keypad_support = _check_keypad_support(
                    self.hass, selected
                )
                return await self.async_step_code_length_mode()

        lock_options = _build_lock_options(available_locks)
        default_ids = (
            self._lock_entities
            if self._lock_entities
            else [lock["entity_id"] for lock in available_locks]
        )

        # Check for unavailable locks.
        unavailable: list[str] = []
        for lock in available_locks:
            state = self.hass.states.get(lock["entity_id"])
            if state and state.state in ("unavailable", "unknown"):
                unavailable.append(lock["name"])

        desc_extra = ""
        if unavailable:
            names = ", ".join(unavailable)
            desc_extra = (
                f"\n\n⚠ The following locks appear unavailable: {names}. "
                "They may not be fully interviewed by Z-Wave JS. Consider "
                "waking them or checking the Z-Wave network before continuing."
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCK_ENTITIES, default=default_ids): SelectSelector(
                    SelectSelectorConfig(
                        options=lock_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="locks",
            data_schema=schema,
            errors=errors,
            last_step=False,
            description_placeholders={"unavailable_notice": desc_extra},
        )

    # ------------------------------------------------------------------
    # Step 3a: Code Length Mode Toggle
    # ------------------------------------------------------------------

    async def async_step_code_length_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose single or dual code length mode."""
        (
            suggest_dual,
            default_single,
            default_short,
            default_long,
            self._discovery_ok,
        ) = _suggest_code_length_defaults(self._discovered_code_lengths)

        # Restore previous selection on back-navigation.
        if self._code_length_mode == CODE_LENGTH_DUAL:
            suggest_dual = True

        if user_input is not None:
            dual_mode: bool = user_input.get(CONF_CODE_LENGTH_MODE, False)

            if dual_mode:
                self._code_length_mode = CODE_LENGTH_DUAL
                # Pre-fill from discovery if we haven't been here before.
                if self._code_length_short == DEFAULT_CODE_LENGTH_SHORT:
                    self._code_length_short = default_short
                if self._code_length_long == DEFAULT_CODE_LENGTH_LONG:
                    self._code_length_long = default_long
                return await self.async_step_code_length_dual()
            else:
                self._code_length_mode = CODE_LENGTH_SINGLE
                if self._code_length_single == DEFAULT_CODE_LENGTH_SINGLE:
                    self._code_length_single = default_single
                return await self.async_step_code_length_single()

        if self._discovery_ok:
            notice = (
                "Code lengths detected from your locks — defaults reflect "
                "what was found."
            )
        else:
            notice = (
                "Could not determine code lengths for all locks. "
                "Verify settings against your lock specifications."
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CODE_LENGTH_MODE, default=suggest_dual
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="code_length_mode",
            data_schema=schema,
            last_step=False,
            description_placeholders={"discovery_notice": notice},
        )

    # ------------------------------------------------------------------
    # Step 3b: Single Code Length
    # ------------------------------------------------------------------

    async def async_step_code_length_single(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a single code length for all locks."""
        if user_input is not None:
            self._code_length_single = int(
                user_input.get(CONF_CODE_LENGTH_SINGLE, DEFAULT_CODE_LENGTH_SINGLE)
            )
            self._code_length_short = DEFAULT_CODE_LENGTH_SHORT
            self._code_length_long = DEFAULT_CODE_LENGTH_LONG
            return await self.async_step_lockout()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CODE_LENGTH_SINGLE, default=self._code_length_single
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
    # Step 3c: Dual Code Lengths
    # ------------------------------------------------------------------

    async def async_step_code_length_dual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure short and long code lengths."""
        errors: dict[str, str] = {}

        if user_input is not None:
            short = int(user_input.get(CONF_CODE_LENGTH_SHORT, DEFAULT_CODE_LENGTH_SHORT))
            long_ = int(user_input.get(CONF_CODE_LENGTH_LONG, DEFAULT_CODE_LENGTH_LONG))

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
                    CONF_CODE_LENGTH_SHORT, default=self._code_length_short
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
                    CONF_CODE_LENGTH_LONG, default=self._code_length_long
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

        # Build lock options with capability annotations.
        lock_labels: list[dict[str, Any]] = []
        supportable_ids: list[str] = []
        for eid in self._lock_entities:
            name = _get_lock_name(self.hass, eid)
            cap = self._lock_keypad_support.get(eid, "unknown")
            if cap == "unsupported":
                label = f"{name} (unsupported)"
            elif cap == "unknown":
                label = f"{name} (capability unknown)"
            else:
                label = name
            lock_labels.append({"entity_id": eid, "name": label})
            # Allow selection for supported and unknown; exclude unsupported.
            if cap != "unsupported":
                supportable_ids.append(eid)

        participating_options = _build_lock_options(lock_labels)

        state_options: list[SelectOptionDict] = [
            SelectOptionDict(value=s, label=s) for s in _LOCKOUT_STATE_SUGGESTIONS
        ]

        # Restore previous selection on back-navigation.
        default_states = (
            self._lockout_target_states
            if self._lockout_target_states
            else []
        )
        default_participating = (
            self._lockout_participating_locks
            if self._lockout_participating_locks
            else supportable_ids
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
                        mode=SelectSelectorMode.LIST,
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

        # Build human-readable summary.
        lock_names: list[str] = [
            _get_lock_name(self.hass, eid) for eid in self._lock_entities
        ]
        lock_list = "\n".join(f"  • {name}" for name in lock_names)

        if self._code_length_mode == CODE_LENGTH_DUAL:
            mode_label = "Two code lengths"
            lengths_detail = (
                f"Short: {self._code_length_short} digits, "
                f"Long: {self._code_length_long} digits"
            )
        else:
            mode_label = "Single code length"
            lengths_detail = f"{self._code_length_single} digits"

        if self._lockout_enabled and self._lockout_trigger_entity:
            states_str = ", ".join(self._lockout_target_states)
            lockout_summary = (
                f"Enabled\n"
                f"  Trigger: {self._lockout_trigger_entity}\n"
                f"  Active when state is: {states_str}"
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
                "secure_mode": "OFF (codes stored in plain text)",
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
