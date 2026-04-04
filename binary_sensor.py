"""SlotSentry binary_sensor platform — keypad lockout active indicator.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Creates one BinarySensorEntity per config entry when keypad lockout is
enabled.  The sensor is ON when the configured trigger entity equals the
target state, and OFF otherwise.  State is updated reactively via
async_track_state_change_event; no polling is performed.

Revision: 1.2
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import SlotSentryConfigEntry
from .const import (
    CONF_LOCKOUT_ENABLED,
    CONF_LOCKOUT_TARGET_STATE,
    CONF_LOCKOUT_TARGET_STATES,
    CONF_LOCKOUT_TRIGGER_ENTITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SlotSentryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SlotSentry binary_sensor entities from a config entry.

    A KeypadLockoutSensor is only created when lockout is enabled in the
    config entry.
    """
    lockout_enabled: bool = entry.data.get(CONF_LOCKOUT_ENABLED, False)

    if not lockout_enabled:
        _LOGGER.debug(
            "Keypad lockout is disabled for entry %s; skipping binary sensor",
            entry.entry_id,
        )
        return

    trigger_entity: str | None = entry.data.get(CONF_LOCKOUT_TRIGGER_ENTITY)

    # Support both new multi-state and legacy single-state config keys.
    target_states: list[str] = entry.data.get(CONF_LOCKOUT_TARGET_STATES, [])
    if not target_states:
        legacy = entry.data.get(CONF_LOCKOUT_TARGET_STATE)
        if legacy:
            target_states = [legacy]

    if not trigger_entity or not target_states:
        _LOGGER.warning(
            "Lockout is enabled for entry %s but trigger_entity or target_states "
            "is missing from config — binary sensor will not be created.",
            entry.entry_id,
        )
        return

    async_add_entities(
        [
            KeypadLockoutSensor(
                entry_id=entry.entry_id,
                trigger_entity=trigger_entity,
                target_states=target_states,
            )
        ]
    )


# ---------------------------------------------------------------------------
# Keypad lockout binary sensor
# ---------------------------------------------------------------------------


class KeypadLockoutSensor(BinarySensorEntity):
    """Indicates whether the keypad lockout is currently active.

    State:
        ON  — lockout is active (trigger entity state matches any target state).
        OFF — lockout is not active.

    Device class: LOCK (ON = locked/secured, aligns with lockout-active
    semantics where keypads are disabled).
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_translation_key = "keypad_lockout"

    def __init__(
        self,
        entry_id: str,
        trigger_entity: str,
        target_states: list[str],
    ) -> None:
        """Initialise the keypad lockout binary sensor.

        Args:
            entry_id:       The config entry ID that owns this entity.
            trigger_entity: The HA entity ID to watch for the lockout
                            trigger condition.
            target_states:  State values of trigger_entity that activate
                            lockout (any match = lockout active).
        """
        self._entry_id = entry_id
        self._trigger_entity = trigger_entity
        self._target_states = target_states

        self._attr_unique_id = f"slotsentry_{entry_id}_lockout"
        self.entity_id = "binary_sensor.slotsentry_keypad_lockout"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Start tracking the trigger entity once added to HA.

        Performs an immediate state snapshot so the sensor reflects the
        current lockout status without waiting for the first change event.
        """
        # Capture the initial state immediately.
        self._update_from_trigger_state()

        # Register a change listener for ongoing updates.
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._trigger_entity],
                self._handle_trigger_state_change,
            )
        )

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    @callback
    def _handle_trigger_state_change(self, event: Event) -> None:
        """React to a state change on the lockout trigger entity."""
        self._update_from_trigger_state()
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _update_from_trigger_state(self) -> None:
        """Snapshot the current trigger entity state into _attr_is_on."""
        trigger_state = self.hass.states.get(self._trigger_entity)
        if trigger_state is None:
            self._attr_is_on = False
            _LOGGER.debug(
                "Trigger entity %s not yet available; lockout sensor set to OFF",
                self._trigger_entity,
            )
            return

        self._attr_is_on = trigger_state.state in self._target_states
        _LOGGER.debug(
            "Lockout sensor updated: trigger=%s state=%r targets=%r → is_on=%s",
            self._trigger_entity,
            trigger_state.state,
            self._target_states,
            self._attr_is_on,
        )

    # ------------------------------------------------------------------
    # Icon
    # ------------------------------------------------------------------

    @property
    def icon(self) -> str:
        """Return an icon that conveys whether lockout is engaged."""
        return "mdi:shield-lock" if self.is_on else "mdi:shield-lock-open"

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    @property
    def device_info(self) -> DeviceInfo:
        """Associate this entity with the SlotSentry virtual device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="SlotSentry",
            manufacturer="SlotSentry",
            model="Lock Code Manager",
        )
