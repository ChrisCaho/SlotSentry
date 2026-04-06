"""SlotSentry constants.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Revision: 1.3
"""

from __future__ import annotations

VERSION = "2026.4.0a21"
DOMAIN = "slotsentry"
STORAGE_KEY = "slotsentry"
STORAGE_VERSION = 2
PLATFORMS = ["sensor", "binary_sensor", "button"]

# Code length defaults and ranges
DEFAULT_CODE_LENGTH = 6
MIN_CODE_LENGTH = 4
MAX_CODE_LENGTH = 8

# Slot limits
MAX_SLOTS = 250  # Upper bound sanity check; actual count from lock capabilities

# Push / commit
PUSH_TIMEOUT_SECONDS = 45  # Per-call timeout; S0 locks can take 30s+
MAX_RETRIES = 3
RETRY_BACKOFF = (5, 15, 30)  # Seconds between retries

# Z-Wave pacing — prevents mesh congestion and lock buffer overflow
INTER_SLOT_DELAY = 2.0       # Fallback inter-slot delay when no latency profile exists
INTER_LOCK_DELAY = 3.0       # Fallback inter-lock delay when no latency profile exists
LATENCY_SLOT_MULTIPLIER = 1.5   # Inter-slot delay = typical_latency × this
LATENCY_LOCK_MULTIPLIER = 3.0   # Inter-lock delay = max(typical_latencies) × this
LATENCY_ERROR_RAMP = 0.5        # Per consecutive error: multiply base by (1 + N × this)
MIN_INTER_SLOT_DELAY = 0.3      # Absolute floor for inter-slot delay (seconds)
VERIFY_SETTLE_DELAY = 1.5    # Seconds after set before readback verification
CONSECUTIVE_FAIL_PAUSE = 3   # After N consecutive slot failures, pause the lock
CONSECUTIVE_FAIL_COOLDOWN = 30.0  # Seconds to pause after consecutive failures

# Latency profiling
LATENCY_VARIANCE_THRESHOLD = 0.25   # 25% — triggers deep profile
LATENCY_QUICK_PING_COUNT = 3        # Pings per lock on panel open
LATENCY_DEEP_PING_COUNT = 15        # Pings when variance exceeds threshold
LATENCY_INTER_PING_DELAY = 0.5      # Seconds between pings to same lock
LATENCY_PROFILE_COOLDOWN = 300      # Seconds before re-profiling allowed

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
WS_GET_CONFIG = "slotsentry/get_config"
WS_UNLOCK = "slotsentry/unlock"
WS_LOCK = "slotsentry/lock"
WS_SECURE_STATUS = "slotsentry/secure_status"
WS_CLEAR_ERRORS = "slotsentry/clear_errors"
WS_PROFILE_LATENCY = "slotsentry/profile_latency"
WS_CANCEL_PUSH = "slotsentry/cancel_push"

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
CONF_CODE_LENGTH_1 = "code_length_1"
CONF_CODE_LENGTH_2 = "code_length_2"
CONF_PER_LOCK_CODE_LENGTH = "per_lock_code_length"
CONF_SLOT_COUNT = "slot_count"
CONF_SECURE_MODE = "secure_mode"
CONF_SECURE_PASSWORD_HASH = "secure_password_hash"
CONF_SECURE_ENCRYPTION_SALT = "secure_encryption_salt"
CONF_LOCKOUT_ENABLED = "lockout_enabled"
CONF_LOCKOUT_TRIGGER_ENTITY = "lockout_trigger_entity"
CONF_LOCKOUT_TARGET_STATE = "lockout_target_state"  # Legacy single-state key
CONF_LOCKOUT_TARGET_STATES = "lockout_target_states"
MAX_LOCKOUT_STATES = 4
CONF_LOCKOUT_PARTICIPATING_LOCKS = "lockout_participating_locks"

# Code length modes
CODE_LENGTH_SINGLE = "single"
CODE_LENGTH_DUAL = "dual"

# Events
EVENT_PUSH_STATUS_CHANGED = "slotsentry_push_status_changed"
EVENT_KEYPAD_LOCKOUT = "slotsentry_keypad_lockout"
EVENT_KEYPAD_UNLOCK = "slotsentry_keypad_unlock"
EVENT_AUDIT = "slotsentry_audit"
