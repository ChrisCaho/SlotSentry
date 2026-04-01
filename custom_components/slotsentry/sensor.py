"""SlotSentry sensor platform — per-lock sync status and overall summary.

Exposes one SyncStatusSensor per configured lock and one OverallStatusSensor
per config entry.  All sensors are event-driven (no polling); they refresh
their state when the SlotManager fires EVENT_PUSH_STATUS_CHANGED.

Revision: 1.0
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SlotSentryConfigEntry
from .const import (
    CONF_LOCK_ENTITIES,
    DOMAIN,
    EVENT_PUSH_STATUS_CHANGED,
    SYNC_OUT_OF_SYNC,
    SYNC_SYNCED,
    SYNC_UNCERTAIN,
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
    """Set up SlotSentry sensor entities from a config entry."""
    slot_manager = entry.runtime_data.slot_manager
    lock_entities: list[str] = entry.data.get(CONF_LOCK_ENTITIES, [])

    entities: list[SensorEntity] = []

    for lock_entity_id in lock_entities:
        entities.append(
            SyncStatusSensor(
                entry_id=entry.entry_id,
                lock_entity_id=lock_entity_id,
                slot_manager=slot_manager,
            )
        )

    entities.append(
        OverallStatusSensor(
            entry_id=entry.entry_id,
            lock_entities=lock_entities,
            slot_manager=slot_manager,
        )
    )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _icon_for_state(state: str) -> str:
    """Return the appropriate MDI icon for a given sync state string."""
    if state == SYNC_SYNCED:
        return "mdi:lock-check"
    if state == SYNC_OUT_OF_SYNC:
        return "mdi:lock-alert"
    return "mdi:lock-question"


def _lock_name_from_entity_id(lock_entity_id: str) -> str:
    """Derive a slug-friendly name from a lock entity ID.

    Examples:
        ``"lock.front_door"`` → ``"front_door"``
        ``"lock.garage"``     → ``"garage"``
    """
    # Strip the domain prefix (e.g. "lock.") if present.
    return lock_entity_id.split(".", 1)[-1]


# ---------------------------------------------------------------------------
# Per-lock sync status sensor
# ---------------------------------------------------------------------------


class SyncStatusSensor(SensorEntity):
    """Reports the sync status of a single managed lock.

    State values: "synced" | "out_of_sync" | "uncertain"

    Extra state attributes:
        - synced_count (int)
        - failed_count (int)
        - uncertain_count (int)
        - dirty_slots (list[int])
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "sync_status"

    def __init__(
        self,
        entry_id: str,
        lock_entity_id: str,
        slot_manager: Any,
    ) -> None:
        """Initialise the per-lock sync status sensor.

        Args:
            entry_id:       The config entry ID that owns this entity.
            lock_entity_id: The HA entity ID of the physical lock being tracked.
            slot_manager:   The SlotManager instance for this config entry.
        """
        self._entry_id = entry_id
        self._lock_entity_id = lock_entity_id
        self._slot_manager = slot_manager

        lock_slug = _lock_name_from_entity_id(lock_entity_id)
        self._attr_unique_id = f"slotsentry_{entry_id}_{lock_entity_id}_sync"
        self.entity_id = f"sensor.slotsentry_{lock_slug}_sync_status"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to push-status events when entity is added to HA."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_PUSH_STATUS_CHANGED, self._handle_push_event
            )
        )

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    @callback
    def _handle_push_event(self, event: Event) -> None:
        """Update state when a push-status event fires for this entry."""
        if event.data.get("entry_id") == self._entry_id:
            self.async_write_ha_state()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> str:
        """Return the overall sync state for this lock."""
        status = self._slot_manager.get_push_status()
        lock_status = status.get(self._lock_entity_id, {})
        return lock_status.get("state", SYNC_UNCERTAIN)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-lock sync counters and the list of dirty slot numbers."""
        status = self._slot_manager.get_push_status()
        lock_status = status.get(self._lock_entity_id, {})
        return {
            "synced_count": lock_status.get("synced_count", 0),
            "failed_count": lock_status.get("failed_count", 0),
            "uncertain_count": lock_status.get("uncertain_count", 0),
            "dirty_slots": lock_status.get("dirty_slots", []),
        }

    @property
    def icon(self) -> str:
        """Return an icon that reflects the current sync state."""
        return _icon_for_state(self.native_value or SYNC_UNCERTAIN)

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


# ---------------------------------------------------------------------------
# Overall summary sensor
# ---------------------------------------------------------------------------


class OverallStatusSensor(SensorEntity):
    """Reports a single aggregate sync status across all managed locks.

    State values:
        - "synced"       — every lock is fully synced.
        - "out_of_sync"  — at least one lock has failed slots.
        - "uncertain"    — no failures, but at least one lock is uncertain.

    Extra state attributes:
        - lock_count (int)
        - all_synced (bool)
        - locks (dict[str, str]) — mapping of lock entity → state
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "overall_status"

    def __init__(
        self,
        entry_id: str,
        lock_entities: list[str],
        slot_manager: Any,
    ) -> None:
        """Initialise the overall summary sensor.

        Args:
            entry_id:      The config entry ID that owns this entity.
            lock_entities: List of managed lock entity IDs.
            slot_manager:  The SlotManager instance for this config entry.
        """
        self._entry_id = entry_id
        self._lock_entities = lock_entities
        self._slot_manager = slot_manager

        self._attr_unique_id = f"slotsentry_{entry_id}_overall"
        self.entity_id = "sensor.slotsentry_overall_status"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to push-status events when entity is added to HA."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_PUSH_STATUS_CHANGED, self._handle_push_event
            )
        )

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    @callback
    def _handle_push_event(self, event: Event) -> None:
        """Update state when a push-status event fires for this entry."""
        if event.data.get("entry_id") == self._entry_id:
            self.async_write_ha_state()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> str:
        """Return the aggregate sync state across all managed locks."""
        status = self._slot_manager.get_push_status()

        has_out_of_sync = False
        has_uncertain = False

        for lock_entity in self._lock_entities:
            lock_state = status.get(lock_entity, {}).get("state", SYNC_UNCERTAIN)
            if lock_state == SYNC_OUT_OF_SYNC:
                has_out_of_sync = True
            elif lock_state == SYNC_UNCERTAIN:
                has_uncertain = True

        if has_out_of_sync:
            return SYNC_OUT_OF_SYNC
        if has_uncertain:
            return SYNC_UNCERTAIN
        return SYNC_SYNCED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return aggregate lock counts and per-lock state mapping."""
        status = self._slot_manager.get_push_status()

        locks_map: dict[str, str] = {
            lock_entity: status.get(lock_entity, {}).get("state", SYNC_UNCERTAIN)
            for lock_entity in self._lock_entities
        }
        all_synced = all(s == SYNC_SYNCED for s in locks_map.values())

        return {
            "lock_count": len(self._lock_entities),
            "all_synced": all_synced,
            "locks": locks_map,
        }

    @property
    def icon(self) -> str:
        """Return an icon that reflects the current aggregate sync state."""
        return _icon_for_state(self.native_value or SYNC_UNCERTAIN)

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
