"""SlotSentry config flow — multi-step setup wizard for Z-Wave lock code management.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.0
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
    EntitySelector,
    EntitySelectorConfig,
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
    CONF_LOCKOUT_TARGET_STATE,
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
# The user can still type any custom string; these are the pre-populated suggestions.
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
    """Return all lock entities whose platform is zwave_js.

    Each entry in the returned list is a dict with at minimum:
        entity_id: str
        name: str
    """
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
    """Estimate the manageable slot count as the minimum across selected locks.

    We try to read ``max_user_codes`` from each lock's state attributes, which
    Z-Wave JS typically exposes.  If the attribute is absent, we fall back to a
    conservative default of 30 so that setup is never blocked.
    """
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
    """Attempt to read minimum/maximum code length attributes from each lock.

    Returns a dict keyed by entity_id; values are the detected code length
    (as a single int when min==max) or None when undiscoverable.
    """
    result: dict[str, int | None] = {}
    for eid in entity_ids:
        state = hass.states.get(eid)
        if state is None:
            result[eid] = None
            continue
        # Z-Wave JS may expose usercode_min_length / usercode_max_length.
        min_len = state.attributes.get("usercode_min_length")
        max_len = state.attributes.get("usercode_max_length")
        if isinstance(min_len, int) and isinstance(max_len, int):
            # If the lock is fixed-length, both will be the same.
            result[eid] = min_len  # Use min as the default suggestion.
        else:
            result[eid] = None
    return result


def _suggest_code_length_defaults(
    discovered: dict[str, int | None],
) -> tuple[bool, int, int, int, bool]:
    """Derive suggested code-length defaults from discovery.

    Returns a 5-tuple:
        suggest_dual: bool        — whether to default to dual-length mode
        default_single: int       — suggested single length
        default_short: int        — suggested short length
        default_long: int         — suggested long length
        discovery_ok: bool        — True if all locks were discoverable
    """
    values = list(discovered.values())
    discovery_ok = all(v is not None for v in values)
    discovered_lengths: set[int] = {v for v in values if v is not None}

    if not discovery_ok or not discovered_lengths:
        # Cannot determine lengths — use safe defaults
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

    # Multiple different lengths detected — suggest dual mode.
    short = min(discovered_lengths)
    long_ = max(discovered_lengths)
    # Clamp to valid ranges.
    short = max(MIN_SHORT_CODE_LENGTH, min(MAX_SHORT_CODE_LENGTH, short))
    long_ = max(MIN_LONG_CODE_LENGTH, min(MAX_LONG_CODE_LENGTH, long_))
    if short >= long_:
        long_ = min(short + 1, MAX_LONG_CODE_LENGTH)
    return (True, DEFAULT_CODE_LENGTH_SINGLE, short, long_, True)


# ---------------------------------------------------------------------------
# Config Flow
# ---------------------------------------------------------------------------


class SlotSentryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SlotSentry.

    The flow is structured as 5 sequential steps:
        user         — Informational welcome screen (no fields).
        locks        — Discover and select Z-Wave lock entities.
        code_length  — Configure PIN code length(s).
        lockout      — Optional keypad lockout trigger.
        confirm      — Summary / final confirmation.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        # Step 2 results
        self._lock_entities: list[str] = []
        self._slot_count: int = 0
        # Discovered lock metadata: entity_id → code length (int | None)
        self._discovered_code_lengths: dict[str, int | None] = {}
        self._discovery_ok: bool = True

        # Step 3 results
        self._code_length_mode: str = CODE_LENGTH_SINGLE
        self._code_length_single: int | None = DEFAULT_CODE_LENGTH_SINGLE
        self._code_length_short: int | None = None
        self._code_length_long: int | None = None

        # Step 4 results
        self._lockout_enabled: bool = False
        self._lockout_trigger_entity: str | None = None
        self._lockout_target_state: str | None = None
        self._lockout_participating_locks: list[str] | None = None

    # ------------------------------------------------------------------
    # Step 1: Welcome (informational only)
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the welcome screen.

        No user input is collected here — the user just clicks Next.
        """
        # Abort if SlotSentry is already configured (single-instance check).
        self._async_abort_entries_match({})

        if user_input is not None:
            # User clicked Next — proceed to lock discovery.
            return await self.async_step_locks()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )

    # ------------------------------------------------------------------
    # Step 2: Lock Discovery & Selection
    # ------------------------------------------------------------------

    async def async_step_locks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover Z-Wave lock entities and let the user select which to manage."""
        available_locks = _discover_zwave_locks(self.hass)

        if not available_locks:
            return self.async_abort(reason="no_zwave_locks")

        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_LOCK_ENTITIES, [])

            if not selected:
                errors[CONF_LOCK_ENTITIES] = "no_locks_selected"
            else:
                # Calculate slot count from the selected locks.
                self._lock_entities = selected
                self._slot_count = _estimate_slot_count(self.hass, selected)

                # Attempt code length discovery so Step 3 can use it.
                self._discovered_code_lengths = _discover_code_lengths(
                    self.hass, selected
                )

                return await self.async_step_code_length()

        lock_options = _build_lock_options(available_locks)
        available_ids = [lock["entity_id"] for lock in available_locks]

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCK_ENTITIES, default=available_ids): SelectSelector(
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
        )

    # ------------------------------------------------------------------
    # Step 3: Code Length Configuration
    # ------------------------------------------------------------------

    async def async_step_code_length(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure PIN code lengths (single or dual mode)."""
        (
            suggest_dual,
            default_single,
            default_short,
            default_long,
            self._discovery_ok,
        ) = _suggest_code_length_defaults(self._discovered_code_lengths)

        errors: dict[str, str] = {}

        if user_input is not None:
            dual_mode: bool = user_input.get(CONF_CODE_LENGTH_MODE, False)

            if dual_mode:
                short: int = user_input.get(CONF_CODE_LENGTH_SHORT, default_short)
                long_: int = user_input.get(CONF_CODE_LENGTH_LONG, default_long)

                if short >= long_:
                    errors[CONF_CODE_LENGTH_SHORT] = "short_gte_long"
                else:
                    self._code_length_mode = CODE_LENGTH_DUAL
                    self._code_length_single = None
                    self._code_length_short = short
                    self._code_length_long = long_
                    return await self.async_step_lockout()
            else:
                single: int = user_input.get(CONF_CODE_LENGTH_SINGLE, default_single)
                self._code_length_mode = CODE_LENGTH_SINGLE
                self._code_length_single = single
                self._code_length_short = None
                self._code_length_long = None
                return await self.async_step_lockout()

        # Build schema — include dual fields at all times; the UI description
        # provides context for when each field applies.  Voluptuous cannot
        # conditionally hide fields, so we include both sets with Optional
        # keys.  Validation logic above determines which are used.
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CODE_LENGTH_MODE, default=suggest_dual
                ): bool,
                vol.Optional(
                    CONF_CODE_LENGTH_SINGLE, default=default_single
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_CODE_LENGTH, max=MAX_CODE_LENGTH),
                ),
                vol.Optional(
                    CONF_CODE_LENGTH_SHORT, default=default_short
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SHORT_CODE_LENGTH, max=MAX_SHORT_CODE_LENGTH),
                ),
                vol.Optional(
                    CONF_CODE_LENGTH_LONG, default=default_long
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_LONG_CODE_LENGTH, max=MAX_LONG_CODE_LENGTH),
                ),
            }
        )

        return self.async_show_form(
            step_id="code_length",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "discovery_notice": (
                    "Code lengths detected from your locks — defaults reflect what was found."
                    if self._discovery_ok
                    else (
                        "Could not determine code length for one or more locks. "
                        "Default values are shown — verify against your lock specifications."
                    )
                ),
            },
        )

    # ------------------------------------------------------------------
    # Step 4: Keypad Lockout (optional)
    # ------------------------------------------------------------------

    async def async_step_lockout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the optional keypad lockout trigger."""
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled: bool = user_input.get(CONF_LOCKOUT_ENABLED, False)

            if enabled:
                trigger_entity: str | None = user_input.get(
                    CONF_LOCKOUT_TRIGGER_ENTITY
                )
                target_state: str | None = user_input.get(CONF_LOCKOUT_TARGET_STATE)
                participating: list[str] = user_input.get(
                    CONF_LOCKOUT_PARTICIPATING_LOCKS, []
                )

                if not participating:
                    errors[CONF_LOCKOUT_PARTICIPATING_LOCKS] = "no_lockout_locks"
                else:
                    self._lockout_enabled = True
                    self._lockout_trigger_entity = trigger_entity or None
                    self._lockout_target_state = target_state or None
                    self._lockout_participating_locks = participating
                    return await self.async_step_confirm()
            else:
                # Lockout disabled — clear any previously stored values.
                self._lockout_enabled = False
                self._lockout_trigger_entity = None
                self._lockout_target_state = None
                self._lockout_participating_locks = None
                return await self.async_step_confirm()

        # Build the lock multi-select from already-selected locks.
        lock_labels: list[dict[str, Any]] = []
        registry = er.async_get(self.hass)
        for eid in self._lock_entities:
            entry = registry.async_get(eid)
            label = (
                entry.name or entry.original_name or eid
                if entry
                else eid
            )
            lock_labels.append({"entity_id": eid, "name": label})

        participating_options = _build_lock_options(lock_labels)

        state_options: list[SelectOptionDict] = [
            SelectOptionDict(value=s, label=s) for s in _LOCKOUT_STATE_SUGGESTIONS
        ]

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCKOUT_ENABLED, default=False): bool,
                vol.Optional(CONF_LOCKOUT_TRIGGER_ENTITY): EntitySelector(
                    EntitySelectorConfig()
                ),
                vol.Optional(
                    CONF_LOCKOUT_TARGET_STATE, default="on"
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=state_options,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_LOCKOUT_PARTICIPATING_LOCKS,
                    default=list(self._lock_entities),
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
        )

    # ------------------------------------------------------------------
    # Step 5: Summary / Confirm
    # ------------------------------------------------------------------

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a read-only summary and create the config entry on submit."""
        if user_input is not None:
            return self._create_entry()

        # Build human-readable summary for description_placeholders.
        mode_label = (
            "Two code lengths (Long + Short)"
            if self._code_length_mode == CODE_LENGTH_DUAL
            else "Single code length"
        )

        if self._code_length_mode == CODE_LENGTH_DUAL:
            lengths_detail = (
                f"Short: {self._code_length_short} digits, "
                f"Long: {self._code_length_long} digits"
            )
        else:
            lengths_detail = f"{self._code_length_single} digits"

        if self._lockout_enabled and self._lockout_trigger_entity:
            lockout_summary = (
                f"Enabled — trigger: {self._lockout_trigger_entity} "
                f"= {self._lockout_target_state}"
            )
        elif self._lockout_enabled:
            lockout_summary = "Enabled (no trigger entity configured)"
        else:
            lockout_summary = "Disabled"

        registry = er.async_get(self.hass)
        lock_names: list[str] = []
        for eid in self._lock_entities:
            entry = registry.async_get(eid)
            lock_names.append(
                entry.name or entry.original_name or eid if entry else eid
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "lock_count": str(len(self._lock_entities)),
                "lock_names": ", ".join(lock_names),
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
            CONF_LOCKOUT_TARGET_STATE: self._lockout_target_state,
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
