"""SlotSentry constants.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.
"""

from __future__ import annotations

VERSION = "2026.4.0a1"
DOMAIN = "slotsentry"
STORAGE_KEY = "slotsentry"
STORAGE_VERSION = 1
PLATFORMS = ["sensor", "binary_sensor", "button"]

# Code length defaults and ranges
DEFAULT_CODE_LENGTH_SINGLE = 6
DEFAULT_CODE_LENGTH_SHORT = 4
DEFAULT_CODE_LENGTH_LONG = 6
MIN_CODE_LENGTH = 4
MAX_CODE_LENGTH = 8
MIN_SHORT_CODE_LENGTH = 4
MAX_SHORT_CODE_LENGTH = 7
MIN_LONG_CODE_LENGTH = 5
MAX_LONG_CODE_LENGTH = 8

# Slot limits
MAX_SLOTS = 250  # Upper bound sanity check; actual count from lock capabilities

# Push / commit
PUSH_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF = (5, 15, 30)  # Seconds between retries

# Secure mode
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 16
PBKDF2_ITERATIONS = 260_000
SESSION_TOKEN_TTL_HOURS = 4
MAX_PASSWORD_ATTEMPTS = 5

# Z-Wave JS service constants
ZWAVE_DOMAIN = "zwave_js"
SERVICE_SET_LOCK_USERCODE = "set_lock_usercode"
SERVICE_CLEAR_LOCK_USERCODE = "clear_lock_usercode"
SERVICE_INVOKE_CC_API = "invoke_cc_api"

# WebSocket commands
WS_GET_SLOTS = "slotsentry/get_slots"
WS_SET_SLOT = "slotsentry/set_slot"
WS_DELETE_SLOT = "slotsentry/delete_slot"
WS_PUSH_ALL = "slotsentry/push_all"
WS_PUSH_LOCK = "slotsentry/push_lock"
WS_GET_STATUS = "slotsentry/get_status"

# Commit state machine states
STATE_IDLE = "idle"
STATE_PENDING = "pending"
STATE_PUSHING = "pushing"
STATE_VERIFYING = "verifying"
STATE_SUCCESS = "success"
STATE_FAILED = "failed"
STATE_RETRY = "retry"
STATE_UNCERTAIN = "uncertain"

# Lock commit sync states (per-lock per-slot)
SYNC_SYNCED = "synced"
SYNC_OUT_OF_SYNC = "out_of_sync"
SYNC_UNCERTAIN = "uncertain"

# Backend addressing modes
ADDRESSING_SLOT = "slot"
ADDRESSING_NAME = "name"

# Config entry keys
CONF_LOCK_ENTITIES = "lock_entities"
CONF_CODE_LENGTH_MODE = "code_length_mode"
CONF_CODE_LENGTH_SINGLE = "code_length_single"
CONF_CODE_LENGTH_SHORT = "code_length_short"
CONF_CODE_LENGTH_LONG = "code_length_long"
CONF_SLOT_COUNT = "slot_count"
CONF_SECURE_MODE = "secure_mode"
CONF_LOCKOUT_ENABLED = "lockout_enabled"
CONF_LOCKOUT_TRIGGER_ENTITY = "lockout_trigger_entity"
CONF_LOCKOUT_TARGET_STATE = "lockout_target_state"
CONF_LOCKOUT_PARTICIPATING_LOCKS = "lockout_participating_locks"

# Code length modes
CODE_LENGTH_SINGLE = "single"
CODE_LENGTH_DUAL = "dual"

# Events
EVENT_PUSH_STATUS_CHANGED = "slotsentry_push_status_changed"
EVENT_KEYPAD_LOCKOUT = "slotsentry_keypad_lockout"
EVENT_KEYPAD_UNLOCK = "slotsentry_keypad_unlock"
EVENT_AUDIT = "slotsentry_audit"
