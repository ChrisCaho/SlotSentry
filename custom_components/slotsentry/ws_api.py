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

Revision: 1.3 — code_1/code_2 field names, per-lock code length.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CODE_LENGTH_1,
    CONF_CODE_LENGTH_2,
    CONF_CODE_LENGTH_MODE,
    CONF_LOCK_ENTITIES,
    CONF_PER_LOCK_CODE_LENGTH,
    CONF_LOCKOUT_ENABLED,
    CONF_LOCKOUT_PARTICIPATING_LOCKS,
    CONF_LOCKOUT_TARGET_STATES,
    CONF_LOCKOUT_TRIGGER_ENTITY,
    CONF_SECURE_ENCRYPTION_SALT,
    CONF_SECURE_MODE,
    CONF_SECURE_PASSWORD_HASH,
    CONF_SLOT_COUNT,
    DOMAIN,
    WS_DELETE_SLOT,
    WS_GET_CONFIG,
    WS_GET_SLOTS,
    WS_GET_STATUS,
    WS_LOCK,
    WS_PUSH_ALL,
    WS_PUSH_LOCK,
    WS_CLEAR_ERRORS,
    WS_CANCEL_PUSH,
    WS_PROFILE_LATENCY,
    WS_SECURE_STATUS,
    WS_SET_SLOT,
    WS_UNLOCK,
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


def _is_secure_mode(hass: HomeAssistant, entry_id: str) -> bool:
    """Return True if this config entry has secure mode enabled."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        return False
    return bool(entry.data.get(CONF_SECURE_MODE, False))


def _require_unlocked(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> bool:
    """Check if secure mode is active and the session is unlocked.

    Returns True if access is allowed, False if blocked (error sent).
    """
    entry_id = msg["entry_id"]
    if not _is_secure_mode(hass, entry_id):
        return True

    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Entry not found")
        return False

    session = entry.runtime_data.secure_session
    if not session.is_unlocked:
        connection.send_error(
            msg["id"],
            "locked",
            "Secure mode is active. Unlock the panel with your password first.",
        )
        return False
    return True


def _slot_data_to_dict(slot: Any, mask_codes: bool = False) -> dict[str, Any]:
    """Serialise a SlotData instance to a plain dict for the WebSocket response.

    When ``mask_codes`` is True, PIN codes are replaced with asterisks
    to indicate a code is set without revealing its value.

    Args:
        slot: A ``SlotData`` dataclass instance from storage.
        mask_codes: If True, replace codes with masked placeholders.

    Returns:
        A JSON-serialisable dict suitable for sending to the frontend.
    """
    if mask_codes:
        code_1 = "****" if slot.code_1 else ""
        code_2 = "****" if slot.code_2 else ""
    else:
        code_1 = slot.code_1
        code_2 = slot.code_2

    return {
        "slot_number": slot.slot_number,
        "label": slot.label,
        "code_1": code_1,
        "code_2": code_2,
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
            slot_number, label, code_1, code_2, enabled,
            created_at, updated_at.
        locked (bool): True if secure mode is active and codes are masked.

    When secure mode is active but the session is locked, codes are
    returned as masked placeholders ("****") so the panel can show
    slot structure without revealing PINs.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    # Determine whether to mask codes.
    secure = _is_secure_mode(hass, msg["entry_id"])
    locked = False
    if secure:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is not None:
            locked = not entry.runtime_data.secure_session.is_unlocked

    slots_by_number = await slot_manager.async_get_slots()

    # Sort by slot number for a stable, predictable order.
    slot_list = [
        _slot_data_to_dict(slot, mask_codes=locked)
        for slot in sorted(slots_by_number.values(), key=lambda s: s.slot_number)
    ]

    connection.send_result(msg["id"], {"slots": slot_list, "locked": locked})
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
        vol.Required("code_1"): str,
        vol.Required("code_2"): str,
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

    Requires an unlocked secure session when secure mode is active.

    Request fields:
        entry_id    (str):  The config entry ID.
        slot_number (int):  1-based slot index to write.
        label       (str):  Human-readable name for the slot.
        code_1      (str):  The primary PIN code, or empty string.
        code_2      (str):  The secondary PIN code, or empty string.
        enabled     (bool): Whether the slot is active.

    Response fields on success:
        success (bool): True.

    Response on error:
        An error result with code ``"invalid_input"`` and a message
        describing the validation failure (label uniqueness, code length).
    """
    if not _require_unlocked(hass, connection, msg):
        return

    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    try:
        await slot_manager.async_set_slot(
            slot_number=msg["slot_number"],
            label=msg["label"],
            code_1=msg["code_1"],
            code_2=msg["code_2"],
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

    Requires an unlocked secure session when secure mode is active.

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
    if not _require_unlocked(hass, connection, msg):
        return

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

    Requires an unlocked secure session when secure mode is active.

    Response fields:
        success (bool): True — indicates the push was initiated, not that
                        it has completed on all locks.
    """
    if not _require_unlocked(hass, connection, msg):
        return

    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    hass.async_create_task(slot_manager.async_push_all())

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.debug(
        "ws_push_all: push initiated (fire-and-forget) for entry %s",
        msg["entry_id"],
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

    Requires an unlocked secure session when secure mode is active.

    Response on error:
        An error result with code ``"not_found"`` when the lock entity is
        not among the configured backends for this entry.
    """
    if not _require_unlocked(hass, connection, msg):
        return

    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    lock_entity: str = msg["lock_entity"]

    # Validate the lock exists before firing the task.
    if not slot_manager.has_lock(lock_entity):
        _LOGGER.info(
            "ws_push_lock: lock '%s' not configured for entry %s",
            lock_entity,
            msg["entry_id"],
        )
        connection.send_error(
            msg["id"],
            "not_found",
            f"Lock '{lock_entity}' is not a configured backend for entry "
            f"'{msg['entry_id']}'",
        )
        return

    hass.async_create_task(
        slot_manager.async_push_lock(lock_entity=lock_entity, force=True)
    )

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.info(
        "ws_push_lock: force-push to '%s' initiated for entry %s",
        lock_entity,
        msg["entry_id"],
    )


# ---------------------------------------------------------------------------
# WS command: cancel_push
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_CANCEL_PUSH,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_cancel_push(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Cancel all running push tasks.

    WebSocket command: ``slotsentry/cancel_push``

    Cancels any in-progress push across all locks.  The commit machines
    will stop at the next safe point and report partial results.

    Request fields:
        entry_id (str): The config entry ID.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    await slot_manager.async_cancel_push()

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.info(
        "ws_cancel_push: push cancelled for entry %s",
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

    connection.send_result(msg["id"], {
        "status": status,
        "active_push_lock": slot_manager.active_push_lock,
    })
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
        CONF_CODE_LENGTH_1,
        CONF_CODE_LENGTH_2,
        CONF_PER_LOCK_CODE_LENGTH,
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
# WS command: unlock (secure mode)
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_UNLOCK,
        vol.Required("entry_id"): str,
        vol.Required("password"): str,
    }
)
@websocket_api.async_response
async def ws_unlock(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Unlock the secure mode session with a password.

    WebSocket command: ``slotsentry/unlock``

    Request fields:
        entry_id (str): The config entry ID.
        password (str): The user's password.

    Response fields on success:
        success (bool): True.
        token   (str):  Session token for subsequent requests.

    Response on error:
        code ``"invalid_password"``: Wrong password.
        code ``"locked_out"``:       Too many failed attempts.
        code ``"not_secure"``:       Secure mode is not enabled.
    """
    entry_id: str = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)

    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Entry not found")
        return

    if not entry.data.get(CONF_SECURE_MODE, False):
        connection.send_error(
            msg["id"], "not_secure", "Secure mode is not enabled"
        )
        return

    session = entry.runtime_data.secure_session

    if session.is_locked_out:
        connection.send_error(
            msg["id"],
            "locked_out",
            "Too many failed attempts. Restart Home Assistant to reset.",
        )
        return

    stored_hash = entry.data.get(CONF_SECURE_PASSWORD_HASH)
    if not stored_hash:
        connection.send_error(
            msg["id"],
            "not_configured",
            "Secure mode is enabled but no password hash is stored. "
            "Reconfigure the integration to set a password.",
        )
        return

    from .crypto import derive_encryption_key, verify_password  # noqa: E402
    from base64 import b64decode  # noqa: E402

    password: str = msg["password"]

    if not verify_password(password, stored_hash):
        session.record_failed_attempt()
        remaining = 5 - session.failed_attempts
        connection.send_error(
            msg["id"],
            "invalid_password",
            f"Incorrect password. {max(remaining, 0)} attempts remaining.",
        )
        return

    # Derive encryption key from password + encryption salt.
    enc_salt_b64 = entry.data.get(CONF_SECURE_ENCRYPTION_SALT, "")
    if enc_salt_b64:
        enc_salt = b64decode(enc_salt_b64)
    else:
        # Fallback: use the password hash salt (shouldn't happen normally).
        enc_salt = b64decode(stored_hash["salt"])

    key = derive_encryption_key(password, enc_salt)
    token = session.unlock(key)

    # Decrypt codes in memory so the push engine and UI can access them.
    slot_manager = entry.runtime_data.slot_manager
    if slot_manager is not None:
        slot_manager.decrypt_codes_in_memory(key)

    connection.send_result(msg["id"], {"success": True, "token": token})
    _LOGGER.info("ws_unlock: secure session unlocked for entry %s", entry_id)


# ---------------------------------------------------------------------------
# WS command: lock (secure mode)
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_LOCK,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_lock(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Lock the secure mode session, wiping the encryption key from memory.

    WebSocket command: ``slotsentry/lock``

    Request fields:
        entry_id (str): The config entry ID.

    Response fields:
        success (bool): True.
    """
    entry_id: str = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)

    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Entry not found")
        return

    # Re-encrypt codes in memory before locking the session.
    session = entry.runtime_data.secure_session
    slot_manager = entry.runtime_data.slot_manager
    key = session.encryption_key
    if slot_manager is not None and key is not None:
        slot_manager.encrypt_codes_in_memory(key)

    session.lock()

    connection.send_result(msg["id"], {"success": True})
    _LOGGER.info("ws_lock: secure session locked for entry %s", entry_id)


# ---------------------------------------------------------------------------
# WS command: secure_status
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SECURE_STATUS,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_secure_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the current secure mode status.

    WebSocket command: ``slotsentry/secure_status``

    Request fields:
        entry_id (str): The config entry ID.

    Response fields:
        secure_mode (bool): Whether secure mode is enabled.
        unlocked    (bool): Whether the session is currently unlocked.
        locked_out  (bool): Whether too many failed attempts have occurred.
    """
    entry_id: str = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)

    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Entry not found")
        return

    secure = bool(entry.data.get(CONF_SECURE_MODE, False))
    session = entry.runtime_data.secure_session

    connection.send_result(
        msg["id"],
        {
            "secure_mode": secure,
            "unlocked": session.is_unlocked if secure else True,
            "locked_out": session.is_locked_out if secure else False,
        },
    )


# ---------------------------------------------------------------------------
# WS command: clear_errors
# ---------------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_CLEAR_ERRORS,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_clear_errors(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Reset session-only error and failure counters for all locks.

    WebSocket command: ``slotsentry/clear_errors``
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    slot_manager.clear_error_counters()
    connection.send_result(msg["id"], {"success": True})
    _LOGGER.debug("ws_clear_errors: counters cleared for entry %s", msg["entry_id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_PROFILE_LATENCY,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_profile_latency(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Trigger background latency profiling on all locks.

    WebSocket command: ``slotsentry/profile_latency``

    Returns immediately. Profiling runs as a background task.
    """
    slot_manager = _get_slot_manager(hass, connection, msg)
    if slot_manager is None:
        return

    # Fire-and-forget background task.
    hass.async_create_task(
        slot_manager.async_profile_latency(),
        name="slotsentry_profile_latency",
    )
    connection.send_result(msg["id"], {"profiling_started": True})
    _LOGGER.debug(
        "ws_profile_latency: background profiling started for entry %s",
        msg["entry_id"],
    )


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
    websocket_api.async_register_command(hass, ws_cancel_push)
    websocket_api.async_register_command(hass, ws_get_status)
    websocket_api.async_register_command(hass, ws_unlock)
    websocket_api.async_register_command(hass, ws_lock)
    websocket_api.async_register_command(hass, ws_secure_status)
    websocket_api.async_register_command(hass, ws_clear_errors)
    websocket_api.async_register_command(hass, ws_profile_latency)

    _LOGGER.debug(
        "SlotSentry: registered %d WebSocket command(s): %s",
        13,
        ", ".join(
            [
                WS_GET_CONFIG,
                WS_GET_SLOTS,
                WS_SET_SLOT,
                WS_DELETE_SLOT,
                WS_PUSH_ALL,
                WS_PUSH_LOCK,
                WS_CANCEL_PUSH,
                WS_GET_STATUS,
                WS_UNLOCK,
                WS_LOCK,
                WS_SECURE_STATUS,
                WS_CLEAR_ERRORS,
                WS_PROFILE_LATENCY,
            ]
        ),
    )
