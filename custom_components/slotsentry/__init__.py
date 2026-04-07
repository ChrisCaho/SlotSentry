"""SlotSentry — Z-Wave Lock Code Manager.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.7 — config entry migration v1→v2.
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

from .const import (
    CODE_LENGTH_DUAL,
    CODE_LENGTH_SINGLE,
    CONF_CODE_LENGTH_1,
    CONF_CODE_LENGTH_2,
    CONF_CODE_LENGTH_MODE,
    CONF_LOCK_ENTITIES,
    CONF_PER_LOCK_CODE_LENGTH,
    CONF_PER_LOCK_SLOT_COUNT,
    CONF_SECURE_MODE,
    CONF_SLOT_COUNT,
    DEFAULT_CODE_LENGTH,
    DOMAIN,
    PLATFORMS,
    VERSION,
)
from .crypto import SecureSession
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
    secure_session: SecureSession = field(default_factory=SecureSession)


type SlotSentryConfigEntry = ConfigEntry[SlotSentryData]


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: SlotSentryConfigEntry,
) -> bool:
    """Migrate config entry from an older version to the current version.

    v1 → v2: Rename code_length_single/short/long to code_length_1/2,
    build per_lock_code_length mapping from existing data.
    """
    if config_entry.version == 1:
        _LOGGER.info("Migrating SlotSentry config entry from v1 to v2")
        old_data = dict(config_entry.data)
        new_data = dict(old_data)

        # Extract old code length fields.
        old_mode = old_data.get("code_length_mode", CODE_LENGTH_SINGLE)
        old_single = old_data.get("code_length_single", DEFAULT_CODE_LENGTH)
        old_short = old_data.get("code_length_short")
        old_long = old_data.get("code_length_long")

        # Remove old keys.
        for key in ("code_length_single", "code_length_short", "code_length_long"):
            new_data.pop(key, None)

        # Compute new code_length_1 / code_length_2.
        if old_mode == CODE_LENGTH_DUAL and old_short and old_long:
            lengths = sorted([int(old_short), int(old_long)])
            new_data[CONF_CODE_LENGTH_1] = lengths[0]
            new_data[CONF_CODE_LENGTH_2] = lengths[1]
            new_data[CONF_CODE_LENGTH_MODE] = CODE_LENGTH_DUAL
        else:
            new_data[CONF_CODE_LENGTH_1] = int(old_single) if old_single else DEFAULT_CODE_LENGTH
            new_data[CONF_CODE_LENGTH_2] = None
            new_data[CONF_CODE_LENGTH_MODE] = CODE_LENGTH_SINGLE

        # Build per_lock_code_length mapping.
        # For single mode, all locks get code_length_1.
        # For dual mode, try to match each lock's discovered code length;
        # fallback: assign code_length_1 to all.
        lock_entities = new_data.get(CONF_LOCK_ENTITIES, [])
        per_lock: dict[str, int] = {}
        cl1 = new_data[CONF_CODE_LENGTH_1]
        cl2 = new_data.get(CONF_CODE_LENGTH_2)

        if new_data[CONF_CODE_LENGTH_MODE] == CODE_LENGTH_DUAL and cl2 is not None:
            # During migration we don't have discovery data, so assign
            # code_length_1 to all locks. Users can reconfigure later.
            for eid in lock_entities:
                per_lock[eid] = cl1
        else:
            for eid in lock_entities:
                per_lock[eid] = cl1

        new_data[CONF_PER_LOCK_CODE_LENGTH] = per_lock

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2,
        )
        _LOGGER.info("SlotSentry config entry migrated to v2 successfully")

    return True


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

    # 2b. Migrate: derive per-lock slot counts for existing installs.
    if CONF_PER_LOCK_SLOT_COUNT not in entry.data:
        _LOGGER.info("Deriving per-lock slot counts for existing install")
        from .config_flow import _async_get_max_user_codes  # noqa: E402

        per_lock_slots: dict[str, int] = {}
        fallback_count = int(entry.data.get(CONF_SLOT_COUNT, 0))
        for eid in lock_entities:
            try:
                discovered = await _async_get_max_user_codes(hass, eid)
                per_lock_slots[eid] = discovered if discovered else fallback_count
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not discover slot count for %s; using fallback %d",
                    eid, fallback_count,
                )
                per_lock_slots[eid] = fallback_count

        new_data = dict(entry.data)
        new_data[CONF_PER_LOCK_SLOT_COUNT] = per_lock_slots
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.info("Per-lock slot counts: %s", per_lock_slots)

    # 3. Create and load SlotManager
    slot_manager = SlotManager(hass, entry, store, backends)
    await slot_manager.async_load()

    # 3b. Process initial latency samples from config flow (one-time).
    initial_samples = entry.data.get("initial_latency_samples")
    if initial_samples:
        import statistics

        from .latency import LatencyProfile

        for eid, samples in initial_samples.items():
            if samples:
                median_val = round(statistics.median(samples), 4)
                profile = LatencyProfile(
                    entity_id=eid,
                    typical_latency=median_val,
                    sample_count=len(samples),
                    last_profiled_at=None,
                    last_raw_samples=[round(s, 4) for s in samples],
                )
                store.set_latency_profile(eid, profile.to_dict())
                _LOGGER.info(
                    "Initial latency profile for %s: %.3fs (%d samples)",
                    eid, median_val, len(samples),
                )
        await store.async_save()

        # Strip one-time data from config entry.
        new_data = {k: v for k, v in entry.data.items() if k != "initial_latency_samples"}
        hass.config_entries.async_update_entry(entry, data=new_data)

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
        try:
            async_remove_panel(hass, DOMAIN)
            _LOGGER.debug("SlotSentry sidebar panel removed")
        except Exception as err:
            _LOGGER.error("Failed to remove sidebar panel: %s", err)

    return unload_ok


async def async_remove_entry(
    hass: HomeAssistant, entry: SlotSentryConfigEntry,
) -> None:
    """Clean up when the user permanently removes the integration.

    Deletes:
      - The SlotSentry storage file (.storage/slotsentry.<entry_id>)
      - The copied panel JS directory (www/slotsentry/)
    """
    _LOGGER.info("Removing SlotSentry integration — cleaning up")

    # Delete storage file.
    store = SlotSentryStore(hass, entry.entry_id)
    try:
        await store.async_remove()
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Failed to remove storage file for entry %s",
            entry.entry_id,
            exc_info=True,
        )

    # Delete copied panel JS directory.
    panel_dir = Path(hass.config.path("www", "slotsentry"))
    if panel_dir.is_dir():
        try:
            await hass.async_add_executor_job(shutil.rmtree, panel_dir)
            _LOGGER.debug("Removed panel JS directory: %s", panel_dir)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to remove panel JS directory: %s",
                panel_dir,
                exc_info=True,
            )

    _LOGGER.info("SlotSentry cleanup complete")


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
    try:
        await hass.async_add_executor_job(_copy_panel_js, hass)
    except Exception as err:
        _LOGGER.error("Failed to copy panel JS: %s", err)
        raise

    try:
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
                    "js_url": f"/local/slotsentry/slotsentry-panel.js?v={VERSION}",
                }
            },
            require_admin=True,
        )
    except Exception as err:
        _LOGGER.error("Failed to register sidebar panel: %s", err)
        raise
    _LOGGER.debug("SlotSentry sidebar panel registered")
