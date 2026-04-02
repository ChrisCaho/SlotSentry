"""SlotSentry WebSocket API — frontend-facing command handlers.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Registers all WebSocket commands that the SlotSentry frontend panel calls to
manage slots and trigger lock pushes.  Each command is bound to a constant
from const.py so that command strings are never hardcoded here.

Command overview:
  slotsentry/get_slots   — Return all slots for a config entry.
  slotsentry/set_slot    — Create or update a slot.
  slotsentry/delete_slot — Clear a slot back to its empty default.
  slotsentry/push_all    — Push all dirty slots to every configured lock.
  slotsentry/push_lock   — Push all dirty slots to one specific lock.
  slotsentry/get_status  — Return per-lock sync summary.

Revision: 1.1 — require_admin, get_config allow-list, slot_number bounds.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import (
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
    DOMAIN,
    WS_DELETE_SLOT,
    WS_GET_CONFIG,
    WS_GET_SLOTS,
    WS_GET_STATUS,
    WS_PUSH_ALL,
    WS_PUSH_LOCK,
    WS_SET_SLOT,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_slot_manager(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> Any | None:
    """Look up and return the SlotManager for the config entry in *msg*.

    Sends a WebSocket error and returns None when the entry is missing or
    belongs to a different domain, so callers can do a simple ``if … is None``
    guard without repeating error-handling boilerplate.

    Args:
        hass:       The Home Assistant instance.
        connection: The active WebSocket connection.
        msg:        The incoming WebSocket message dict (must contain
                    ``"entry_id"``).

    Returns:
        The ``SlotManager`` instance, or ``None`` if the entry was not found
        or does not belong to the slotsentry domain.
    """
    entry_id: str = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)

    if entry is None or entry.domain != DOMAIN:
        connection.send_error(
            msg["id"],
            "not_found",
            f"Config entry '{entry_id}' not found or does not belong to {DOMAIN}",
        )
        return None

    slot_manager = entry.runtime_data.slot_manager
    if slot_manager is None:
        connection.send_error(
            msg["id"],
            "not_ready",
            f"SlotManager for entry '{entry_id}' is not yet initialised",
        )
        return None

    return slot_manager


def _slot_data_to_dict(slot: Any) -> dict[str, Any]:
    """Serialise a SlotData instance to a plain dict for the WebSocket response.

    NOTE: In secure mode (future implementation), codes would be masked here.
    For now they are returned as plaintext.

    Args:
        slot: A ``SlotData`` dataclass instance from storage.

    Returns:
        A JSON-serialisable dict suitable for sending to the frontend.
    """
    return {
        "slot_number": slot.slot_number,
        "label": slot.label,
        "long_code": slot.long_code,
        "short_code": slot.short_code,
        "enabled": slot.enabled,
        "created_at": slot.created_at,
        "updated_at": slot.updated_at,
    }


# ---------------------------------------------------------------------------
# WS command: get_slots
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_GET_SLOTS,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_slots(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all configured slots for a SlotSentry config entry.

    WebSocket command: ``slotsentry/get_slots``

    Request fields:
        entry_id (str): The config entry ID to query.

    Response fields:
        slots (list[dict]): Ordered list of slot dicts, each containing
            slot_number, label, long_code, short_code, enabled,
            created_at, updated_at.

    NOTE: Codes are returned as plaintext.  A future secure-mode
    implementation will mask them behind session authentication.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    slots_by_number = await slot_manager.async_get_slots()

    # Sort by slot number for a stable, predictable order.
    slot_list = [
        _slot_data_to_dict(slot)
        for slot in sorted(slots_by_number.values(), key=lambda s: s.slot_number)
    ]

    connection.send_result(msg["id"], {"slots": slot_list})
    _LOGGER.debug(
        "ws_get_slots: returned %d slot(s) for entry %s",
        len(slot_list),
        msg["entry_id"],
    )


# ---------------------------------------------------------------------------
# WS command: set_slot
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SET_SLOT,
        vol.Required("entry_id"): str,
        vol.Required("slot_number"): vol.All(int, vol.Range(min=1)),
        vol.Required("label"): str,
        vol.Required("long_code"): str,
        vol.Required("short_code"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
async def ws_set_slot(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create or update a slot for a SlotSentry config entry.

    WebSocket command: ``slotsentry/set_slot``

    Request fields:
        entry_id    (str):  The config entry ID.
        slot_number (int):  1-based slot index to write.
        label       (str):  Human-readable name for the slot.
        long_code   (str):  The long PIN code, or empty string.
        short_code  (str):  The short PIN code, or empty string.
        enabled     (bool): Whether the slot is active.

    Response fields on success:
        success (bool): True.

    Response on error:
        An error result with code ``"invalid_input"`` and a message
        describing the validation failure (label uniqueness, code length).
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    try:
        await slot_manager.async_set_slot(
            slot_number=msg["slot_number"],
            label=msg["label"],
            long_code=msg["long_code"],
            short_code=msg["short_code"],
            enabled=msg["enabled"],
        )
    except ValueError as exc:
        _LOGGER.info(
            "ws_set_slot: validation error for entry %s slot %d: %s",
            msg["entry_id"],
            msg["slot_number"],
            exc,
        )
        connection.send_error(msg["id"], "invalid_input", str(exc))
        return

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.debug(
        "ws_set_slot: slot %d updated for entry %s",
        msg["slot_number"],
        msg["entry_id"],
    )


# ---------------------------------------------------------------------------
# WS command: delete_slot
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_DELETE_SLOT,
        vol.Required("entry_id"): str,
        vol.Required("slot_number"): vol.All(int, vol.Range(min=1)),
    }
)
@websocket_api.async_response
async def ws_delete_slot(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Clear a slot back to its empty default state.

    WebSocket command: ``slotsentry/delete_slot``

    Clearing a slot resets its label, codes, and enabled flag.  The slot
    entry itself is preserved in storage (to maintain the slot_count
    invariant).  All lock commits for this slot are marked out_of_sync so
    the next push will clear the code from the physical hardware.

    Request fields:
        entry_id    (str): The config entry ID.
        slot_number (int): 1-based slot index to delete.

    Response fields:
        success (bool): True.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    await slot_manager.async_delete_slot(slot_number=msg["slot_number"])

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.debug(
        "ws_delete_slot: slot %d cleared for entry %s",
        msg["slot_number"],
        msg["entry_id"],
    )


# ---------------------------------------------------------------------------
# WS command: push_all
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_PUSH_ALL,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_push_all(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Push all dirty slots to every configured lock in parallel.

    WebSocket command: ``slotsentry/push_all``

    The push is executed inline from the perspective of this command, but
    each lock push runs in its own asyncio Task internally (see
    SlotManager.async_push_all).  The frontend should monitor push
    progress by subscribing to ``slotsentry_push_status_changed`` HA events
    or by polling ``slotsentry/get_status``.

    Request fields:
        entry_id (str): The config entry ID.

    Response fields:
        success (bool): True — indicates the push was initiated, not that
                        it has completed on all locks.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    await slot_manager.async_push_all()

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.debug(
        "ws_push_all: push initiated for entry %s", msg["entry_id"]
    )


# ---------------------------------------------------------------------------
# WS command: push_lock
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_PUSH_LOCK,
        vol.Required("entry_id"): str,
        vol.Required("lock_entity"): str,
    }
)
@websocket_api.async_response
async def ws_push_lock(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Push all dirty slots to a single configured lock.

    WebSocket command: ``slotsentry/push_lock``

    Request fields:
        entry_id    (str): The config entry ID.
        lock_entity (str): The HA entity ID of the lock to push to
                           (e.g. ``"lock.front_door"``).

    Response fields on success:
        success (bool): True.

    Response on error:
        An error result with code ``"not_found"`` when the lock entity is
        not among the configured backends for this entry.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    lock_entity: str = msg["lock_entity"]

    try:
        await slot_manager.async_push_lock(lock_entity=lock_entity)
    except KeyError as exc:
        _LOGGER.info(
            "ws_push_lock: lock '%s' not configured for entry %s: %s",
            lock_entity,
            msg["entry_id"],
            exc,
        )
        connection.send_error(
            msg["id"],
            "not_found",
            f"Lock '{lock_entity}' is not a configured backend for entry "
            f"'{msg['entry_id']}'",
        )
        return

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.debug(
        "ws_push_lock: push to '%s' initiated for entry %s",
        lock_entity,
        msg["entry_id"],
    )


# ---------------------------------------------------------------------------
# WS command: get_status
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_GET_STATUS,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the per-lock sync status summary for a config entry.

    WebSocket command: ``slotsentry/get_status``

    Request fields:
        entry_id (str): The config entry ID to query.

    Response fields:
        status (dict): Mapping of lock entity ID to a summary dict.
            Each summary contains:
              - state          (str):       Overall lock state —
                                            ``"synced"``, ``"out_of_sync"``,
                                            or ``"uncertain"``.
              - synced_count   (int):       Slots confirmed in sync.
              - failed_count   (int):       Slots that failed to push.
              - uncertain_count(int):       Slots in an uncertain state.
              - dirty_slots    (list[int]): Slot numbers needing a push.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    status = slot_manager.get_push_status()

    connection.send_result(msg["id"], {"status": status})
    _LOGGER.debug(
        "ws_get_status: returned status for %d lock(s) for entry %s",
        len(status),
        msg["entry_id"],
    )


# ---------------------------------------------------------------------------
# WS command: get_config
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_GET_CONFIG,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return config entry data needed by the frontend panel.

    WebSocket command: ``slotsentry/get_config``

    Returns the config entry data dict (lock_entities, code_length_mode,
    code lengths, slot_count, lockout settings, secure_mode) so the panel
    can display configuration info without needing access to the raw
    config_entries store.
    """
    entry_id: str = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)

    if entry is None or entry.domain != DOMAIN:
        connection.send_error(
            msg["id"],
            "not_found",
            f"Config entry '{entry_id}' not found or does not belong to {DOMAIN}",
        )
        return

    # Allow-list: only return keys the panel needs.
    _SAFE_CONFIG_KEYS = {
        CONF_LOCK_ENTITIES,
        CONF_CODE_LENGTH_MODE,
        CONF_CODE_LENGTH_SINGLE,
        CONF_CODE_LENGTH_SHORT,
        CONF_CODE_LENGTH_LONG,
        CONF_SLOT_COUNT,
        CONF_SECURE_MODE,
        CONF_LOCKOUT_ENABLED,
        CONF_LOCKOUT_TRIGGER_ENTITY,
        CONF_LOCKOUT_TARGET_STATES,
        CONF_LOCKOUT_PARTICIPATING_LOCKS,
    }
    data = {k: v for k, v in entry.data.items() if k in _SAFE_CONFIG_KEYS}

    connection.send_result(msg["id"], {"config": data})
    _LOGGER.debug("ws_get_config: returned config for entry %s", entry_id)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def async_register_ws_commands(hass: HomeAssistant) -> None:
    """Register all SlotSentry WebSocket commands with Home Assistant.

    Call this once during ``async_setup_entry`` so that the frontend panel
    can reach all commands.  HA's websocket_api de-duplicates registrations,
    so calling this more than once (e.g., for multiple config entries) is
    safe.

    Args:
        hass: The Home Assistant instance.
    """
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_get_slots)
    websocket_api.async_register_command(hass, ws_set_slot)
    websocket_api.async_register_command(hass, ws_delete_slot)
    websocket_api.async_register_command(hass, ws_push_all)
    websocket_api.async_register_command(hass, ws_push_lock)
    websocket_api.async_register_command(hass, ws_get_status)

    _LOGGER.debug(
        "SlotSentry: registered %d WebSocket command(s): %s",
        7,
        ", ".join(
            [
                WS_GET_CONFIG,
                WS_GET_SLOTS,
                WS_SET_SLOT,
                WS_DELETE_SLOT,
                WS_PUSH_ALL,
                WS_PUSH_LOCK,
                WS_GET_STATUS,
            ]
        ),
    )
