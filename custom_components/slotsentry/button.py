"""SlotSentry button platform — Push All action button.

Exposes one ButtonEntity per config entry.  When pressed it delegates to
SlotManager.async_push_all(), which pushes every out-of-sync slot to all
configured locks in parallel.

Revision: 1.0
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SlotSentryConfigEntry
from .const import DOMAIN

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
    """Set up SlotSentry button entities from a config entry."""
    slot_manager = entry.runtime_data.slot_manager

    async_add_entities(
        [
            PushAllButton(
                entry_id=entry.entry_id,
                slot_manager=slot_manager,
            )
        ]
    )


# ---------------------------------------------------------------------------
# Push All button
# ---------------------------------------------------------------------------


class PushAllButton(ButtonEntity):
    """Triggers an immediate push of all out-of-sync slots to every lock.

    Pressing this button is the manual equivalent of the automatic
    background push cycle — useful for forcing a sync after bulk edits or
    after a connectivity interruption.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "push_all"
    _attr_icon = "mdi:upload-lock"

    def __init__(
        self,
        entry_id: str,
        slot_manager: Any,
    ) -> None:
        """Initialise the Push All button.

        Args:
            entry_id:     The config entry ID that owns this entity.
            slot_manager: The SlotManager instance for this config entry.
        """
        self._entry_id = entry_id
        self._slot_manager = slot_manager

        self._attr_unique_id = f"slotsentry_{entry_id}_push_all"
        self.entity_id = "button.slotsentry_push_all"

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------

    async def async_press(self) -> None:
        """Push all out-of-sync slots to every configured lock."""
        _LOGGER.info(
            "Push All triggered for SlotSentry entry %s", self._entry_id
        )
        await self._slot_manager.async_push_all()

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
