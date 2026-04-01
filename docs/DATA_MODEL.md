# SlotSentry Data Model

**Revision: 1.2**

Complete specification of all data structures, storage schema, and state machines used in SlotSentry.

## Table of Contents

- [Storage Schema](#storage-schema)
- [Core Data Structures](#core-data-structures)
- [Commit State Machine](#commit-state-machine)
- [Validation Rules](#validation-rules)
- [Configuration Schema](#configuration-schema)
- [WebSocket Message Schema](#websocket-message-schema)
- [Encryption Specification](#encryption-specification)
- [Migration Strategy](#migration-strategy)

## Storage Schema

### File Location

`.storage/slotsentry` in Home Assistant config directory

### Version

Current schema version: **1**

### File Format (Open Mode)

```json
{
  "version": 1,
  "secure_mode": false,
  "code_type": "long",
  "code_type_long_length": 6,
  "code_type_short_length": 4,
  "slot_count": 19,
  "locks": [
    {
      "entity_id": "lock.zwave_back_door_deadbolt",
      "name": "Back Door",
      "code_type": "long",
      "keypad_lockout_participate": true
    }
  ],
  "slots": [
    {
      "slot_number": 1,
      "label": "Dog Sitter",
      "long_code": "123456",
      "short_code": null,
      "enabled": true
    },
    {
      "slot_number": 2,
      "label": "",
      "long_code": null,
      "short_code": null,
      "enabled": true
    }
  ],
  "commit_state": {
    "disk": [
      {
        "slot_number": 1,
        "state": "synced",
        "last_modified": "2026-03-31T14:23:00Z"
      }
    ],
    "locks": {
      "lock.zwave_back_door_deadbolt": [
        {
          "slot_number": 1,
          "state": "synced",
          "pushed_at": "2026-03-31T14:25:00Z",
          "last_verify": "2026-03-31T14:25:10Z",
          "code_hash": "sha256:abcd1234...",
          "last_pushed_label": null
        }
      ]
    }
  },
  "audit_log": [
    {
      "timestamp": "2026-03-31T14:25:00Z",
      "event_type": "push",
      "lock_entity_id": "lock.zwave_back_door_deadbolt",
      "slot_number": 1,
      "status": "success",
      "message": "Code pushed and verified"
    }
  ]
}
```

### File Format (Secure Mode)

```json
{
  "version": 1,
  "secure_mode": true,
  "iv": "base64_encoded_16_bytes",
  "salt": "base64_encoded_16_bytes",
  "encrypted_data": "base64_encoded_aes_ciphertext"
}
```

The `encrypted_data` field, when decrypted, contains the same structure as open mode (minus `secure_mode: true`).

### Field Descriptions

#### Root Level

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Schema version for migrations |
| `secure_mode` | bool | True if storage is encrypted |
| `code_type` | "long" \| "short" \| "both" | Global code type setting |
| `code_type_long_length` | int | (if code_type="both") Long code length 5-8 |
| `code_type_short_length` | int | (if code_type="both") Short code length 4-7 |
| `slot_count` | int | Number of slots; determined at setup by the lock with the smallest capacity |
| `locks` | array | List of lock configurations |
| `slots` | array | List of code slots (length = slot_count) |
| `commit_state` | object | Sync status tracking |
| `audit_log` | array | History of operations |

#### Lock Configuration

```typescript
interface LockConfig {
  entity_id: string;        // Must exist in Home Assistant
  name: string;             // Display name (e.g., "Back Door")
  code_type: "long" | "short" | "both";  // Codes stored for this lock
  keypad_lockout_participate: boolean;  // Include in lockout feature
}
```

#### SlotInfo

Context passed from the SlotManager to a lock backend for each slot operation. The `label` field bridges slot-number-based protocols (Z-Wave) and name-based protocols (Schlage cloud) — see the LockBackend protocol below.

```typescript
interface SlotInfo {
    slot_number: number;  // Physical slot (Z-Wave) or internal array index (cloud)
    label: string;        // Human name; used as code identifier on name-based backends
}
```

#### Slot

```typescript
interface Slot {
  slot_number: number;      // 1 through slot_count (determined by smallest lock capacity)
  label: string;            // User-friendly name (empty allowed)
  long_code: string | null; // 5-8 digit code (encrypted if secure)
  short_code: string | null;  // 4-7 digit code (encrypted if secure)
  enabled: boolean;         // Active on locks
}
```

Constraints:
- `slot_number` must be between 1 and `slot_count`
- `slot_count` is determined at integration setup time by the lock with the smallest slot capacity among the selected locks; it is not hardcoded
- `long_code` and `short_code` must be numeric strings if present
- If `code_type` global is "long", `short_code` must be null
- If `code_type` global is "short", `long_code` must be null
- If `code_type` global is "both", one or both can be null (optional per slot)
- Empty `label` is valid
- `enabled` determines if slot is active on locks
- **Label uniqueness**: non-empty labels must be unique (case-insensitive) across all slots within a config entry. Empty/blank labels are exempt from this check. This rule is required because name-based lock backends (e.g., Schlage cloud) use the label as the code's identity on the lock — duplicate names make delete operations ambiguous.

#### Commit State

```typescript
interface CommitState {
  disk: SlotCommit[];  // What's saved to disk
  locks: {             // Per-lock sync status
    [lock_entity_id: string]: SlotCommit[];
  };
}

interface SlotCommit {
  slot_number: number;
  state: "synced" | "out_of_sync" | "uncertain";
  last_modified?: string;       // ISO timestamp (disk only)
  pushed_at?: string;           // ISO timestamp (lock only)
  last_verify?: string;         // ISO timestamp (lock only)
  code_hash?: string | null;    // SHA-256 of last pushed code (lock only)
  last_pushed_label?: string | null;  // Label at time of last push (name-based backends only; null for Z-Wave)
}
```

State meanings:
- `synced` - Code matches disk and is verified on lock
- `out_of_sync` - Code differs; needs push and verification
- `uncertain` - Push may have succeeded but verification timed out

#### Audit Log Entry

```typescript
interface AuditLogEntry {
  timestamp: string;  // ISO 8601
  event_type: "push" | "clear" | "enable" | "disable" | "label_change";
  lock_entity_id?: string;  // Omitted for storage-only events
  slot_number: number;
  status: "success" | "failed" | "timeout";
  message: string;  // Human readable (no codes)
}
```

Constraints:
- Never log code values
- Never log passwords
- Keep audit log bounded (max 1000 entries, rolling)
- Include meaningful error messages for debugging

## Core Data Structures

### Python Type Definitions

#### SlotInfo Dataclass

`SlotInfo` is the context object passed to every `LockBackend` method. It bridges the two lock addressing models: Z-Wave uses `slot_number` to address physical hardware slots, while name-based backends (e.g., Schlage cloud) use `label` as the code identifier sent to the lock API. Wrapping both values in a single dataclass lets either backend extract what it needs without requiring method signature changes as the protocol evolves.

```python
@dataclass
class SlotInfo:
    """Passed to every LockBackend method. Z-Wave uses slot_number, cloud uses label."""
    slot_number: int  # Physical slot (Z-Wave) or internal array index (cloud)
    label: str        # Human name; used as code identifier on name-based backends
```

#### Slot Class

```python
@dataclass
class Slot:
    """Single access code slot."""
    slot_number: int              # 1 through slot_count
    label: str                    # "" allowed
    long_code: str | None         # 5-8 digits or None
    short_code: str | None        # 4-7 digits or None
    enabled: bool                 # True = active on locks

    def is_empty(self) -> bool:
        """True if no codes set."""
        return self.long_code is None and self.short_code is None

    def get_active_code(self) -> str | None:
        """Get the code that should be pushed to lock.

        Returns long_code if present, else short_code.
        Returns None if slot is empty.
        """

    def to_dict(self) -> dict:
        """Serialize to JSON."""

    @classmethod
    def from_dict(cls, data: dict) -> Slot:
        """Deserialize from JSON."""
```

#### Lock Configuration Class

```python
@dataclass
class LockConfig:
    """Configuration for a single Z-Wave lock."""
    entity_id: str                    # e.g., "lock.back_door"
    name: str                         # Display name
    code_type: str                    # "long", "short", or "both"
    keypad_lockout_participate: bool  # Include in lockout

    def is_valid(self, hass: HomeAssistant) -> bool:
        """Check if lock entity exists."""
```

#### LockSlotCommit Dataclass

Tracks per-slot sync state for a single lock. Defined as a dataclass (not a bare dict) so that adding fields is a clean schema migration rather than scattered dict-key references throughout the codebase.

```python
@dataclass
class LockSlotCommit:
    """Per-slot sync state for one lock. Stored in commit_state.locks[entity_id]."""
    slot_number: int
    state: str                        # "synced" | "out_of_sync" | "uncertain"
    pushed_at: str | None             # ISO timestamp of last push attempt
    code_hash: str | None             # SHA-256 of the code at last successful push
    last_pushed_label: str | None     # Label at time of last push.
                                      # Z-Wave backends set this to None (label is cosmetic).
                                      # Name-based backends (Schlage cloud) track it so that
                                      # a rename is detected as out_of_sync even if code unchanged.

    @property
    def needs_retry(self) -> bool:
        """True if state is out_of_sync or uncertain."""

    @property
    def is_recent(self) -> bool:
        """True if last push was within 1 hour."""
```

#### Coordinator Data Class

```python
@dataclass
class CoordinatorData:
    """All runtime data managed by coordinator."""
    slots: list[Slot]
    slot_count: int                     # Determined at setup; minimum across selected locks
    locks: list[LockConfig]
    commit_state: dict[str, any]
    secure_mode: bool
    dirty_slots: set[int]           # Slots modified in UI, not yet pushed
    authenticated: bool             # (Secure mode) password validated
    keypad_lockout_trigger: str | None  # Entity ID of trigger sensor
    keypad_lockout_target_state: any    # Expected state value
    keypad_lockout_active: bool         # Currently suppressed
```

#### LockBackend Protocol

`LockBackend` is the Protocol that all lock implementations must satisfy. Methods receive a `SlotInfo` object so that both Z-Wave (slot-number-addressed) and name-based (label-addressed) backends can be implemented without changing call sites in the SlotManager.

```python
class LockBackend(Protocol):
    """Protocol for lock backends. Implementations translate
    SlotManager operations to lock-specific APIs.

    - Z-Wave backend: uses slot_info.slot_number, ignores label
    - Schlage cloud backend (future): uses slot_info.label as code identifier,
      slot_info.slot_number is the internal array index only
    """

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        """Push a code to the lock for the given slot."""
        ...

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        """Clear/delete the code for the given slot from the lock."""
        ...

    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None:
        """Read back the code for the given slot.

        Returns the code string if readable, None if slot is empty
        or readback is not supported.
        """
        ...

    async def async_get_all_usercodes(self) -> dict[int, str] | None:
        """Read all codes from the lock in a single call.

        Returns {slot_number: code} for all occupied slots, or None if
        bulk readback is not supported (caller falls back to per-slot).
        For name-based backends, slot numbers are resolved by matching
        code names against slot labels in the SlotManager.
        Z-Wave backend returns None (no efficient bulk read exists).
        """
        ...

    @property
    def supports_readback(self) -> bool:
        """True if async_get_usercode can return actual code digits."""
        ...

    @property
    def addressing_mode(self) -> str:
        """How this lock identifies codes: 'slot' or 'name'.

        - 'slot': codes addressed by physical slot number (Z-Wave)
        - 'name': codes addressed by label/name (Schlage cloud)

        The SlotManager uses this to determine whether a label change
        should dirty the lock commit state for this backend.
        """
        ...

    @property
    def supported_code_lengths(self) -> tuple[int, int]:
        """(min_length, max_length) of accepted codes.

        Used by the commit machine to pre-validate code length before
        attempting a push, producing clear error messages instead of
        opaque lock firmware errors.
        Example: Z-Wave FE599 returns (4, 4); Schlage cloud returns (4, 8).
        """
        ...
```

### Verification Result

```python
@dataclass
class VerifyResult:
    """Result of verifying a slot on a lock."""
    slot_number: int
    occupied: bool                # True if slot has code
    actual_code: str | None       # Only for locks supporting readback
    status: str                   # "ok", "mismatch", "timeout", "error"
    message: str                  # Human readable

    @property
    def verified(self) -> bool:
        """True if verification succeeded."""
        return self.status == "ok"
```

## Commit State Machine

### State Definitions

```
[synced]
  - Code on disk matches code on physical lock
  - No action needed
  - Transition: User edits code → out_of_sync

[out_of_sync]
  - Code on disk differs from code on physical lock
  - Needs push and verification
  - Transition: Push & verify succeeds → synced
  - Transition: Push & verify times out → uncertain
  - Transition: Retry pushed → uncertain or synced

[uncertain]
  - Push operation started but verification timed out
  - Unknown if code actually committed to lock
  - Transition: User clicks "Retry" → out_of_sync (retry push)
  - Transition: Verify succeeds → synced
  - Transition: Verify fails → out_of_sync
```

### State Transitions

```
User Save → Disk Write
    ↓
Disk marked "synced"
All affected locks marked "out_of_sync"
    ↓
Push to Lock 1
    ├─ Write succeeds
    ├─ Verify succeeds → Lock 1 marked "synced"
    └─ Verify times out → Lock 1 marked "uncertain"
    ↓
Push to Lock 2
    (repeat)
    ↓
All locks processed
    ├─ All synced → Show "All committed"
    ├─ Some uncertain → Show "Verify recommended"
    └─ Some out_of_sync → Show "Retry available"
    ↓
Panel Open Later
    ├─ Check commit state for uncertain/out_of_sync
    ├─ Auto-retry those slots
    └─ Show status badge if issues found
```

### State Diagram (ASCII)

```
                         ┌─────────────────┐
                         │     synced      │
                         │   Code matches  │
                         │  disk & lock    │
                         └────────┬────────┘
                                  │
                       User edits code
                                  │
                         ┌────────▼────────┐
                         │   out_of_sync   │
                         │  Needs push &   │
                         │   verification  │
                         └─┬──────────┬─┬──┘
                           │          │ │
                      Push │          │ │ Timeout
                           │          │ │
                         ┌─▼──────────▼─▼──┐
                         │   uncertain     │
                         │ Unknown state   │
                         │ Verify timeout  │
                         └─┬──────────┬────┘
                           │          │
                        Verify ok     │ Verify failed
                           │          │
                      Retry │         │
                           │          │
                         ┌─▼──────────▼────┐
                         │   out_of_sync   │ (retry again)
                         └────────┬────────┘
                                  │
                      (Eventually) │
                                  │ Success
                         ┌────────▼────────┐
                         │     synced      │
                         └─────────────────┘
```

### Timeout Handling

- Each push operation has **60-second timeout**
- If timeout during write: operation marked `uncertain`
- If timeout during verify: operation marked `uncertain`
- Retry immediately up to 3 times
- After 3 failures: user must close/reopen panel or restart HA
- Mark as `uncertain` not `out_of_sync` to distinguish write vs verify timeout

### Retry Strategy

```
User clicks "Save" or "Retry Failed"
    ↓
For each lock with out_of_sync slots:
    ├─ Only push modified slots (dirty tracking)
    ├─ After push: verify
    ├─ Update commit state based on verification
    ├─ Save commit state to disk
    └─ Move to next lock
    ↓
For each lock with uncertain slots:
    ├─ Only verify (don't re-push)
    ├─ If verify succeeds → synced
    ├─ If verify fails → back to out_of_sync
    ├─ Update commit state
    ├─ Save to disk
    └─ Move to next lock
```

## Validation Rules

These rules are enforced by the SlotManager before any write to storage or push to a lock backend.

### Label Uniqueness

- Non-empty labels must be unique within a config entry, compared case-insensitively.
- Empty/blank labels are exempt — any number of slots may have no label.
- Rationale: name-based lock backends (e.g., Schlage cloud) use the label as the code's identity on the lock. Duplicate labels make delete and rename operations ambiguous because the `schlage.delete_code` service matches by name.
- Validation location: `SlotManager.async_set_slot()` (rejects the update before writing).

### Code Length

- The code written to any slot must fall within the `supported_code_lengths` range advertised by every lock backend the slot will be pushed to.
- The commit machine pre-validates code length before attempting a push; a clear error message is raised if the code is out of range, rather than relying on the lock firmware to reject it.
- For dual-code-type configurations ("both"), each code field is validated against the backends that will receive it (long_code to locks configured for "long" or "both", short_code to locks configured for "short" or "both").

### SlotInfo Construction

- A `SlotInfo` object is always constructed from the current live slot data immediately before any backend call. It is never cached or reused across calls.
- This ensures that the label seen by the backend is always current, even if a rename happened since the last push.

### Storage Schema Constraints (lock_commit entries)

The `commit_state.locks` entries in storage must conform to the `LockSlotCommit` shape. Example showing all fields:

```json
"lock_commit": {
    "lock.front_door": {
        "1": {
            "state": "synced",
            "pushed_at": "2026-03-31T00:00:00Z",
            "code_hash": "sha256:abcd...",
            "last_pushed_label": "House Cleaner"
        }
    }
}
```

- `last_pushed_label` is `null` for Z-Wave backends (label is cosmetic on Z-Wave; the slot number addresses the lock).
- `last_pushed_label` is populated for name-based backends so that a subsequent label rename can be detected as `out_of_sync` even when the code itself has not changed.

## Configuration Schema

### Config Entry Data

Stored in Home Assistant's config entries system (not in .storage/slotsentry).

```python
entry.data = {
    "locks": [
        "lock.zwave_back_door_deadbolt",
        "lock.zwave_master_bedroom_lock",
    ],
    "code_type": "long",              # or "short" or "both"
    "code_type_long_length": 6,       # (if "both") long code digits
    "code_type_short_length": 4,      # (if "both") short code digits
    "secure_mode": False,              # Enable encryption
    "slot_count": 19,                 # Set at setup; minimum across selected locks
}

entry.options = {
    "keypad_lockout_trigger": "binary_sensor.alarm_status",
    "keypad_lockout_target_state": "armed_home",
    "locks": [
        {
            "entity_id": "lock.zwave_back_door_deadbolt",
            "keypad_lockout_participate": True,
        },
        {
            "entity_id": "lock.zwave_master_bedroom_lock",
            "keypad_lockout_participate": False,
        },
    ]
}
```

### Service Parameters

#### zwave_js.set_lock_usercode

```yaml
service: zwave_js.set_lock_usercode
data:
  entity_id: lock.zwave_back_door_deadbolt
  code_slot: 1          # 1 through slot_count
  user_code: "123456"   # Numeric string
```

#### zwave_js.clear_lock_usercode

```yaml
service: zwave_js.clear_lock_usercode
data:
  entity_id: lock.zwave_back_door_deadbolt
  code_slot: 1          # 1 through slot_count
```

#### zwave_js.invoke_cc_api

```yaml
service: zwave_js.invoke_cc_api
data:
  endpoint: 0
  command_class: 99     # User Code CC
  method_name: "get"
  method_arguments:
    - 1                 # slot number
```

Response:
```json
{
  "status": "Occupied",  // or "Available"
  "user_id_status": 1,   // 1=enabled, 2=disabled (not reliable)
  "user_code": "123456"  // Only if readable lock
}
```

## WebSocket Message Schema

### Message Structure

```typescript
interface WebSocketMessage {
  type: string;            // Command type
  id?: string;             // Message ID (echo in response)
  [key: string]: any;      // Command-specific fields
}

interface WebSocketResponse {
  type: string;            // "success", "error", etc.
  id?: string;             // Echo of request ID
  success?: boolean;
  data?: any;
  code?: string;           // Error code
  message?: string;        // Human readable message
}
```

### Commands from Frontend

#### slotsentry/authenticate

```json
{
  "type": "slotsentry/authenticate",
  "id": "msg_1",
  "password": "password123"
}
```

Response (success):
```json
{
  "type": "slotsentry/response",
  "id": "msg_1",
  "success": true
}
```

Response (failure):
```json
{
  "type": "slotsentry/error",
  "id": "msg_1",
  "code": "INVALID_PASSWORD",
  "message": "Invalid password"
}
```

#### slotsentry/get_slots

```json
{
  "type": "slotsentry/get_slots",
  "id": "msg_2"
}
```

Response:
```json
{
  "type": "slotsentry/response",
  "id": "msg_2",
  "success": true,
  "data": {
    "secure_mode": true,
    "code_type": "both",
    "code_type_long_length": 6,
    "code_type_short_length": 4,
    "slot_count": 19,
    "slots": [
      {
        "slot_number": 1,
        "label": "Dog Sitter",
        "long_code": "123456",
        "short_code": "1234",
        "enabled": true
      }
    ]
  }
}
```

#### slotsentry/update_slots

```json
{
  "type": "slotsentry/update_slots",
  "id": "msg_3",
  "slots": [
    {
      "slot_number": 1,
      "label": "Dog Sitter (Updated)",
      "long_code": "654321",
      "short_code": "4321",
      "enabled": true
    }
  ],
  "force_all": false
}
```

Response:
```json
{
  "type": "slotsentry/response",
  "id": "msg_3",
  "success": true,
  "data": {
    "message": "Codes pushed to 3 locks",
    "synced_count": 3,
    "out_of_sync_count": 0,
    "uncertain_count": 0
  }
}
```

Error response:
```json
{
  "type": "slotsentry/error",
  "id": "msg_3",
  "code": "PUSH_FAILED",
  "message": "Failed to push to lock.zwave_back_door_deadbolt: timeout"
}
```

#### slotsentry/get_commit_status

```json
{
  "type": "slotsentry/get_commit_status",
  "id": "msg_4"
}
```

Response:
```json
{
  "type": "slotsentry/response",
  "id": "msg_4",
  "success": true,
  "data": {
    "disk": [
      {"slot_number": 1, "state": "synced", "last_modified": "2026-03-31T14:25:00Z"},
      {"slot_number": 2, "state": "out_of_sync"}
    ],
    "locks": {
      "lock.zwave_back_door_deadbolt": [
        {"slot_number": 1, "state": "synced", "last_push": "2026-03-31T14:25:00Z"}
      ]
    }
  }
}
```

#### slotsentry/push_all

```json
{
  "type": "slotsentry/push_all",
  "id": "msg_5"
}
```

Response: Same as `slotsentry/update_slots`

#### slotsentry/retry_failed

```json
{
  "type": "slotsentry/retry_failed",
  "id": "msg_6"
}
```

Response:
```json
{
  "type": "slotsentry/response",
  "id": "msg_6",
  "success": true,
  "data": {
    "message": "Retried 2 failed slots",
    "retried_count": 2,
    "synced_count": 1,
    "still_failed_count": 1
  }
}
```

## Encryption Specification

### Algorithm Details

- **Cipher**: AES-256-CBC (Advanced Encryption Standard, 256-bit key)
- **Key Derivation**: PBKDF2-SHA256
- **Iterations**: 100,000
- **Salt**: 16 random bytes (generated per encryption)
- **IV**: 16 random bytes (generated per encryption)
- **Authentication**: None (implicitly authenticated by decryption success)

### Encryption Process

```
1. User enters password
   │
2. Generate salt (16 random bytes)
   │
3. Derive key from password + salt using PBKDF2
   │      └─ 100,000 iterations of SHA-256
   │      └─ Output: 32-byte AES key
   │
4. Generate IV (16 random bytes)
   │
5. Serialize data to JSON
   │
6. Encrypt JSON using AES-256-CBC with key + IV
   │
7. Encode as base64:
   │    {
   │      "version": 1,
   │      "secure_mode": true,
   │      "salt": "base64(16 bytes)",
   │      "iv": "base64(16 bytes)",
   │      "encrypted_data": "base64(ciphertext)"
   │    }
   │
8. Write to .storage/slotsentry
```

### Decryption Process

```
1. Read .storage/slotsentry
   │
2. Decode JSON
   │
3. User enters password
   │
4. Decode salt from base64
   │
5. Derive key from password + salt (same PBKDF2 as encryption)
   │
6. Decode IV and ciphertext from base64
   │
7. Decrypt ciphertext using AES-256-CBC with key + IV
   │
8. Validate decryption by parsing JSON
   │   └─ If JSON invalid: password was wrong, data corrupted
   │
9. Return decrypted data
```

### Security Properties

- **Password strength**: 8-16 character minimum enforced in config flow
- **Salt uniqueness**: New salt for every encryption (prevents rainbow tables)
- **IV uniqueness**: New IV for every encryption (required for CBC mode)
- **Password loss**: Data unrecoverable if password forgotten
- **Brute force resistance**: 100,000 PBKDF2 iterations slows attacks
- **No master key**: Only user password can decrypt data

### Bad Password Recovery

If user enters wrong password N times in sidebar panel (typically 3):

1. Offer "Reset with new password" option
2. Warning: "Previous codes will be lost. Cannot be undone."
3. User confirms and enters new password
4. Storage re-initialized with empty slots (count preserved from config entry)
5. Codes must be re-entered
6. Historical audit log lost

## Migration Strategy

### Version Tracking

- Schema version stored in root of storage file
- Current version: 1
- Coordinator checks version on load

### Adding Migrations

When schema changes:

1. **Increment version** in `const.py`:
   ```python
   STORAGE_VERSION = 2  # was 1
   ```

2. **Write migration function** in `storage.py`:
   ```python
   async def _migrate_v1_to_v2(data: dict) -> dict:
       """Migrate from v1 to v2.

       Changes:
       - Added 'new_field' to root
       """
       data["new_field"] = "default_value"
       return data
   ```

3. **Apply in load_data()** in `storage.py`:
   ```python
   while data["version"] < STORAGE_VERSION:
       if data["version"] == 1:
           _LOGGER.info("Migrating storage v1 → v2")
           data = await _migrate_v1_to_v2(data)
           data["version"] = 2
   ```

4. **Test with real storage files**:
   - Export existing storage
   - Test migration preserves data
   - Verify integration works after migration
   - Document data loss (if any) in migration notes

### Backward Compatibility

- New fields must have sensible defaults
- Never delete fields (deprecated fields can be ignored)
- Migrations are one-way (older versions upgrade to newer)
- Version rollback not supported (users must stay on latest)

### Migration Example: Adding Audit Log

```
v1 storage:
{
  "version": 1,
  "slots": [...],
  ...
}

Migration:
async def _migrate_v1_to_v2(data: dict) -> dict:
    data["audit_log"] = []  # New field with empty log
    return data

v2 storage:
{
  "version": 2,
  "slots": [...],
  "audit_log": [],
  ...
}
```

### Migration Example: Changing Slot Structure

```
v1 slot: {"slot_number": 1, "code": "123456", "enabled": true}

Migration:
async def _migrate_v1_to_v2(data: dict) -> dict:
    for slot in data.get("slots", []):
        if "code" in slot:
            slot["long_code"] = slot.pop("code")
            slot["short_code"] = None
    return data

v2 slot: {"slot_number": 1, "long_code": "123456", "short_code": null, ...}
```
