"""SlotSentry — Z-Wave Lock Code Manager.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.2
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_LOCK_ENTITIES, DOMAIN, PLATFORMS
from .lock_backend import ZWaveJSBackend
from .slot_manager import SlotManager
from .storage import SlotSentryStore

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .lock_backend import LockBackend

_LOGGER = logging.getLogger(__name__)


@dataclass
class SlotSentryData:
    """Runtime data for a SlotSentry config entry (stored in entry.runtime_data)."""

    slot_manager: SlotManager | None = None
    lock_backends: dict[str, LockBackend] = field(default_factory=dict)


type SlotSentryConfigEntry = ConfigEntry[SlotSentryData]


async def async_setup_entry(hass: HomeAssistant, entry: SlotSentryConfigEntry) -> bool:
    """Set up SlotSentry from a config entry."""
    _LOGGER.info("Setting up SlotSentry integration")

    # 1. Create storage layer
    store = SlotSentryStore(hass, entry.entry_id)

    # 2. Initialise lock backends
    lock_entities: list[str] = entry.data.get(CONF_LOCK_ENTITIES, [])
    backends: dict[str, LockBackend] = {}

    for entity_id in lock_entities:
        backend = ZWaveJSBackend(hass, entity_id)
        try:
            await backend.async_init()
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to initialise backend for %s; will use defaults",
                entity_id,
                exc_info=True,
            )
        backends[entity_id] = backend

    # 3. Create and load SlotManager
    slot_manager = SlotManager(hass, entry, store, backends)
    await slot_manager.async_load()

    # 4. Store runtime data on entry
    runtime_data = SlotSentryData(
        slot_manager=slot_manager,
        lock_backends=backends,
    )
    entry.runtime_data = runtime_data

    # 5. Register WebSocket API commands (idempotent — only registers once)
    from .ws_api import async_register_ws_commands  # noqa: E402

    async_register_ws_commands(hass)

    # 6. Register sidebar panel
    await _async_register_panel(hass)

    # 7. Forward entity platform setup
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(p) for p in PLATFORMS]
    )

    _LOGGER.info(
        "SlotSentry setup complete: %d locks, %d slots",
        len(backends),
        slot_manager.slot_count,
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SlotSentryConfigEntry,
) -> bool:
    """Unload a SlotSentry config entry."""
    _LOGGER.info("Unloading SlotSentry integration")

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )

    if unload_ok:
        # Cancel running commit machines
        if entry.runtime_data.slot_manager is not None:
            await entry.runtime_data.slot_manager.async_shutdown()

        # Remove sidebar panel
        async_remove_panel(hass, DOMAIN)
        _LOGGER.debug("SlotSentry sidebar panel removed")

    return unload_ok


def _copy_panel_js(hass: HomeAssistant) -> None:
    """Copy the panel JS file to HA's www directory (runs in executor)."""
    src = Path(__file__).parent / "www" / "slotsentry-panel.js"
    dst_dir = Path(hass.config.path("www", "slotsentry"))
    dst = dst_dir / "slotsentry-panel.js"

    if src.is_file():
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        _LOGGER.debug("Copied panel JS to %s", dst)
    else:
        _LOGGER.warning("Panel JS source not found at %s", src)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the SlotSentry sidebar panel.

    Copies the JS file from the integration's www/ directory to HA's
    www/slotsentry/ so that it's served at /local/slotsentry/. Then
    registers the panel_custom entry.
    """
    # File I/O must run in the executor to avoid blocking the event loop.
    await hass.async_add_executor_job(_copy_panel_js, hass)

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="SlotSentry",
        sidebar_icon="mdi:lock-smart",
        frontend_url_path=DOMAIN,
        config={
            "_panel_custom": {
                "name": "slotsentry-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": "/local/slotsentry/slotsentry-panel.js",
            }
        },
        require_admin=True,
    )
    _LOGGER.debug("SlotSentry sidebar panel registered")
