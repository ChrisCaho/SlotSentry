# SlotSentry Developer Guide

**Revision: 1.1**

Complete technical guide to the SlotSentry architecture, implementation details, and workflows.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Component Details](#component-details)
- [Configuration Flow](#configuration-flow)
- [WebSocket API](#websocket-api)
- [Frontend Communication](#frontend-communication)
- [Commit State Machine](#commit-state-machine)
- [Lock Backends](#lock-backends)
- [Extending SlotSentry](#extending-slotsentry)
- [Debugging Tips](#debugging-tips)

## Architecture Overview

SlotSentry is a Home Assistant integration for managing Z-Wave lock codes. It consists of:

1. **Backend (Python)** - Custom HA integration handling storage, code pushing, verification
2. **Frontend (JavaScript)** - Sidebar web component for the UI
3. **Storage Layer** - JSON file with optional encryption
4. **Z-Wave Integration** - Communication via HA WebSocket and Z-Wave JS services

SlotSentry is a code manager only. It never issues `lock.lock` or `lock.unlock` commands. All lock operations are limited to reading and writing user code slots.

### System Diagram

```
Home Assistant Core
├── SlotSentry Integration (Python)
│   ├── Config Flow (setup, reconfigure)
│   ├── Coordinator (main loop, push logic)
│   ├── WebSocket Handler (frontend <-> backend)
│   ├── Storage Manager (disk I/O, encryption)
│   ├── Lock Backends (Z-Wave JS via services)
│   └── Entities (sensors, buttons)
│
├── Z-Wave JS Integration
│   └── Services
│       ├── zwave_js.set_lock_usercode (push)
│       ├── zwave_js.clear_lock_usercode (disable)
│       └── zwave_js.invoke_cc_api (verify)
│
└── Frontend (Sidebar Panel)
    ├── Authentication (secure mode)
    ├── Slot Grid (edit slots)
    ├── Status Display (commit state)
    └── WebSocket Client
        └── Backend Connection
```

## Project Structure

Expected file layout for SlotSentry:

```
custom_components/slotsentry/
├── __init__.py                 # Integration setup, coordinator init
├── manifest.json               # Integration metadata
├── config_flow.py              # Setup/reconfigure UI
├── coordinator.py              # Data updates, push logic, commit machine
├── storage.py                  # Disk I/O, encryption/decryption
├── const.py                    # Constants, defaults
├── entity.py                   # Base entity class
├── sensor.py                   # Push status sensor
├── binary_sensor.py            # Suppressed (keypad lockout) sensor
├── button.py                   # Push all, retry buttons
├── websocket_api.py            # Frontend <-> backend communication
├── lock_backend.py             # Lock interface/protocol
├── lock_backends/
│   └── zwave_js.py             # Z-Wave JS implementation
├── strings.json                # UI translation strings
├── translations/
│   └── en.json                 # English translations
├── icons.json                  # Entity icons
├── www/                        # Frontend code
│   ├── slotsentry-panel.js     # Main sidebar component
│   ├── manifest.json           # Frontend metadata
│   └── package.json            # npm dependencies
└── tests/                      # Unit tests
    ├── test_config_flow.py
    ├── test_coordinator.py
    ├── test_storage.py
    └── test_websocket.py
```

## Component Details

### Integration Initialization (`__init__.py`)

Responsibilities:

1. **Async setup** - Create coordinator, register WebSocket
2. **Coordinator creation** - Initialize data synchronization
3. **Event listeners** - Home Assistant startup/shutdown
4. **Cleanup** - Graceful shutdown on HA restart

Key function:
```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up SlotSentry from a config entry."""
    # Load storage
    # Create coordinator
    # Register WebSocket handler
    # Forward setup to domains (sensor, binary_sensor, button)
```

### Configuration Flow (`config_flow.py`)

Three main flows:

1. **ADD** - Initial setup
   - Lock discovery/selection (multi-select)
   - Code length configuration (single or dual length); defaults discovered from lock capabilities
   - Secure mode toggle (with password entry)
   - Optional lockout trigger entity for keypad lockout

2. **RECONFIGURE** - Modify existing integration
   - Add/remove locks
   - Adjust code lengths
   - Enable/disable secure mode (with password handling)
   - Keypad lockout participation per lock

3. **OPTIONS** - User-accessible settings
   - Password entry for secure mode (change/disable)
   - Bad password recovery workflow

#### Password Handling

In secure mode:
- **Setup**: User enters password 8-16 characters, must match confirmation
- **Reconfigure**: User can disable secure mode (requires current password)
- **Bad password**: After N failures, offer password reset with data loss warning
- **Recovery**: Data is unrecoverable after password loss

### Coordinator (`coordinator.py`)

The brain of SlotSentry. Responsibilities:

1. **Data synchronization** - Update slots from storage on interval
2. **Slot management** - Track slots, dirty state, verification
3. **Push logic** - Coordinate code pushes to locks
4. **Commit tracking** - Maintain commit state for each lock/slot
5. **Timeout handling** - 60-second max per lock operation
6. **Verification** - After push, verify codes on lock
7. **Retry logic** - Handle out_of_sync and uncertain states
8. **Audit logging** - Track all operations

Key data structures:
```python
class Slot:
    slot_number: int           # 1 through available slot count
    label: str                 # "Dog Sitter"
    long_code: str             # encrypted if secure mode
    short_code: str            # encrypted if secure mode
    enabled: bool              # Active on locks

class LockCommitStatus:
    lock_entity_id: str
    slot_number: int
    state: str                 # "synced" | "out_of_sync" | "uncertain"
    last_push: datetime | None
    last_verify: datetime | None
```

The slot count is determined at integration setup time by the lock with the smallest slot capacity among the configured locks. Commit arrays are sized accordingly.

Key functions:
```python
async def push_codes_to_all_locks(
    self, slots: list[Slot], force_all: bool = False
) -> bool:
    """Push codes to all configured locks.

    Args:
        slots: List of slots to push
        force_all: If True, push all slots. If False, push only dirty slots.

    Returns:
        True if all locks synced successfully
    """

async def verify_lock_slots(
    self, lock_entity_id: str, slots: list[Slot]
) -> dict[int, VerifyResult]:
    """Verify slot status on a specific lock.

    Returns:
        Mapping of slot number to verification result
    """
```

### Storage Manager (`storage.py`)

Handles persistent data with optional encryption.

Features:
- JSON serialization of slots and commit state
- Optional AES encryption (secure mode)
- Atomic writes (temp file -> rename)
- Backward compatibility for schema changes
- Audit trail storage

File location: `.storage/slotsentry`

File format (open mode):
```json
{
  "version": 1,
  "secure_mode": false,
  "slots": [
    {"slot_number": 1, "label": "Dog Sitter", "long_code": "123456", ...}
  ],
  "commit_state": {...},
  "audit_log": [...]
}
```

File format (secure mode):
```json
{
  "version": 1,
  "secure_mode": true,
  "encrypted_data": "base64_encoded_aes_ciphertext",
  "iv": "base64_encoded_initialization_vector",
  "salt": "base64_encoded_salt"
}
```

Encryption (secure mode):
- Algorithm: AES-256-CBC
- Key derivation: PBKDF2 (100,000 iterations)
- Salt: random 16 bytes
- IV: random 16 bytes
- Decryption requires password - data loss if password forgotten

Key functions:
```python
async def load_data(self, password: str | None = None) -> SlotSentryData:
    """Load slots and commit state from disk.

    If secure mode and password is wrong, raises PasswordError.
    """

async def save_data(
    self, data: SlotSentryData, password: str | None = None
) -> None:
    """Save slots and commit state to disk.

    Encrypts if password provided.
    """

async def validate_password(self, password: str) -> bool:
    """Test if password can decrypt current storage."""
```

### WebSocket API Handler (`websocket_api.py`)

Bidirectional communication between frontend and backend.

Commands from frontend:

1. **slotsentry/authenticate** - Validate password
   - Request: `{"type": "slotsentry/authenticate", "password": "..."}`
   - Response: `{"success": true/false}`

2. **slotsentry/get_slots** - Fetch all slots
   - Request: `{"type": "slotsentry/get_slots"}`
   - Response: `{"slots": [...]}`

3. **slotsentry/update_slots** - Save edited slots
   - Request: `{"type": "slotsentry/update_slots", "slots": [...]}`
   - Response: `{"success": true, "message": "..."}`
   - Side effect: Initiates push to all locks

4. **slotsentry/get_commit_status** - Get sync status
   - Request: `{"type": "slotsentry/get_commit_status"}`
   - Response: `{"status": {...}, "locks": {...}}`

5. **slotsentry/push_all** - Force push all slots
   - Request: `{"type": "slotsentry/push_all"}`
   - Response: `{"success": true, "message": "..."}`

6. **slotsentry/retry_failed** - Retry out_of_sync slots
   - Request: `{"type": "slotsentry/retry_failed"}`
   - Response: `{"success": true, "retried": N}`

Errors sent from backend:
```python
# Password required but not authenticated
{"type": "slotsentry/error", "code": "UNAUTHENTICATED", "message": "..."}

# Invalid password
{"type": "slotsentry/error", "code": "INVALID_PASSWORD", "message": "..."}

# Push failed
{"type": "slotsentry/error", "code": "PUSH_FAILED", "message": "..."}
```

### Entities

#### Sensor: `sensor.slotsentry_push_status`

Shows result of last push operation:
- State: "synced", "out_of_sync", "pushing", "uncertain"
- Attributes:
  - `last_push`: ISO timestamp
  - `failed_locks`: List of locks that failed
  - `message`: Human-readable status

#### Binary Sensor: `binary_sensor.slotsentry_suppressed`

Indicates if keypad lockout is active:
- On: Keypad is disabled on participating locks
- Off: Keypad is enabled
- Attributes:
  - `trigger`: Entity ID of the lockout trigger causing suppression
  - `since`: When suppression started

#### Button: `button.slotsentry_push_all`

Press to force push all slots to all locks (ignoring dirty state).

#### Button: `button.slotsentry_retry`

Press to retry any out_of_sync or uncertain slots.

## Configuration Flow

### ADD Integration

```
Step 1: Select Locks
  - Multi-select all available Z-Wave locks
  - Validate at least one lock selected
  - Determine slot count from the lock with the smallest capacity

Step 2: Code Length Configuration
  - Auto-detect supported code lengths from locks
  - Option A: Single code length (4-8 digits, default from detection)
  - Option B: Two code lengths (short 4-7, long 5-8, defaults from detection)
  - If undiscoverable: default to 4/6 (two lengths) or 6 (single)
  - Determine what fields show in sidebar panel

Step 3: Secure Mode (Optional)
  - Checkbox: "Enable secure mode"
  - If checked:
    - Show warning: "Codes will be encrypted. Password cannot be recovered."
    - Password field (8-16 chars)
    - Confirm password field
    - Validate both match

Step 4: Review
  - Show selected locks, slot count, code config, secure mode setting
  - Final confirmation

Step 5: Initialize Storage
  - Create .storage/slotsentry with empty slots sized to discovered slot count
  - Set commit state to "synced" (nothing pushed yet)
  - Coordinator starts, ready to receive code updates from panel
```

### RECONFIGURE Integration

Menu path: Settings > Devices & Services > SlotSentry > Options > Reconfigure

```
Step 1: Update Locks
  - Current locks shown (checkboxes)
  - Add new locks
  - Remove locks
  - Validate at least one
  - Note: slot count is re-evaluated from the updated lock selection

Step 2: Keypad Lockout
  - Select lockout trigger entity (alarm, presence, etc.)
  - Select target state ("Armed" or specific state)
  - Per lock: checkbox "Participate in lockout"

Step 3: Review & Save
  - Show changes
  - If locks removed: warning about data loss (can re-add)
  - Confirm
```

### Secure Mode Management

#### Enable Secure Mode (config flow)
1. User adds integration and checks "Enable secure mode"
2. Password entry (must match confirmation)
3. On save: storage file encrypted with password
4. Sidebar panel shows password field at top

#### Disable Secure Mode (config flow)
1. User navigates to integration options
2. Prompts for current password (for decryption)
3. Warning: "Codes will be stored unencrypted. This cannot be undone."
4. Confirmation
5. On save: storage re-written without encryption

#### Bad Password Recovery
1. User enters wrong password N times in sidebar panel
2. System offers reset option
3. Warning: "Previous codes will be lost. New password required."
4. User enters new password (8-16 chars)
5. Storage re-initialized with empty slots, new password
6. User must re-enter all codes

## WebSocket API

### Connection Flow

```
Frontend
  |
  | (WebSocket connect)
  |
  HA WebSocket Server
  |
  | (register handler)
  |
SlotSentry Integration (websocket_api.py)
```

### Message Format

All messages are JSON:

```json
{
  "type": "slotsentry/command",
  "id": "msg_12345",
  "payload": {...}
}
```

Responses:

```json
{
  "type": "slotsentry/response",
  "id": "msg_12345",
  "success": true,
  "data": {...}
}
```

Errors:

```json
{
  "type": "slotsentry/error",
  "id": "msg_12345",
  "code": "ERROR_CODE",
  "message": "Human readable message"
}
```

## Frontend Communication

### Sidebar Panel Lifecycle

```
1. Panel Loads
   - Show login form (secure mode) or empty grid (open mode)

2. Authentication (Secure Mode Only)
   - User enters password
   - Send slotsentry/authenticate command
   - Get response (success or error)
   - If success: unlock grid, fetch slots
   - If error: show error message, allow retry

3. Fetch Slots
   - Send slotsentry/get_slots command
   - Receive full slot array
   - Render grid with current values
   - Mark all as clean (no modifications)

4. Edit Slots
   - User modifies label, codes, enable/disable
   - Track dirty fields per slot
   - Show visual indication of changes
   - "Reveal Codes" checkbox in secure mode (separate password validation)

5. Save
   - User clicks "Save" button (shown when changes are pending)
   - Collect all dirty slots (or all if "Update All" checked)
   - Send slotsentry/update_slots command
   - Show loading indicator
   - Receive success or error
   - If success: show confirmation popup
   - Reload slots from server (to catch any changes)
   - Mark all as clean
   - Show "Exit" button (no pending changes)
   - "Discard" button available alongside "Save" while edits are pending

6. Monitor Status
   - Periodically fetch slotsentry/get_commit_status
   - Show per-lock status (synced, out_of_sync, uncertain)
   - If out_of_sync found on panel open: auto-retry
   - Show warning badges on locks with issues

7. Manual Retry
   - User clicks "Retry Failed"
   - Send slotsentry/retry_failed command
   - Show loading, then result
```

### Button States

- **Exit** — shown when no unsaved edits exist; closes the panel
- **Save** — shown when the user has made edits; commits and pushes
- **Discard** — shown alongside Save; reverts all unsaved edits
- After a successful Save, "Exit" is shown again

### Error Handling on Frontend

- Network error: "Connection lost, retrying..."
- Authentication failed: "Invalid password"
- Push timeout: "One or more locks took too long. Codes may not be synced."
- Partial failure: "Synced with X of Y locks"
- Out of memory: Show clear error, suggest exit and reopen

## Commit State Machine

### Overview

Three commit arrays track code synchronization:

1. **Disk Commit Array** - What's saved in `.storage/slotsentry`
2. **Lock Commit Arrays** - What's synced to each physical lock
3. **Dirty State** - What the UI has modified (in memory only)

The arrays are sized to match the slot count determined at integration setup (minimum across selected locks).

State values:
- `synced` - Code matches disk and lock
- `out_of_sync` - Code on lock differs from disk
- `uncertain` - Unknown state (timed out, unverified)

### Save Flow (with Commit Machine)

```
Step 1: Save to Disk
  ├─ Write slots to .storage/slotsentry
  └─ Update disk commit array to "synced"

Step 2: Mark Locks as Out of Sync
  ├─ For each affected lock
  └─ Set commit state to "out_of_sync" (for changed slots)

Step 3: Push to Each Lock (Sequential)
  ├─ For each lock in order:
  │  ├─ Connect to lock (timeout: 60 sec)
  │  ├─ Push changed codes via zwave_js.set_lock_usercode
  │  ├─ Verify (if enabled) via zwave_js.invoke_cc_api
  │  ├─ Update lock commit array:
  │  │  ├─ If verified: set to "synced"
  │  │  ├─ If write succeeded but verify timed out: set to "uncertain"
  │  │  └─ If write failed: stay "out_of_sync"
  │  ├─ Save lock commit array to disk
  │  └─ Move to next lock
  │
  └─ End loop

Step 4: Report Status
  ├─ All synced → show "All committed"
  ├─ Some out_of_sync → show "Retry available"
  └─ Some uncertain → show "Verify recommended"
```

### State Diagram

```
                    User Saves Slot
                          |
                          v
     +-----------+------ out_of_sync -----+
     |           |                        |
     |        (Push)                   (Timeout)
     |           |                        |
     |           v                        |
     |        Verify Success?           uncertain
     |           |                        |
     |           |                        |
     |    (Yes) /  \ (No)            (Retry)
     |         /    \                     |
     |        v      v                    |
     |      synced   out_of_sync         |
     |               |                    |
     |               +<----(Retry)-------+
     |
     v
  User Clicks "Retry Failed"
     |
     v
  Re-push only out_of_sync and uncertain slots
```

### Timeout Handling

- Each lock operation has 60-second timeout
- If timeout: mark as `uncertain` (unknown if committed)
- Keep trying on next retry
- After 3 failures: suggest HA restart
- User can manually "Wipe & Reupload" as last resort

### Verification Strategy

After pushing a code:

**For locks that support readback (BE469ZP):**
- Use `invoke_cc_api` with method "get"
- Read actual code back from lock
- Compare to what was pushed
- If mismatch: mark uncertain, retry

**For locks that don't support readback (FE599):**
- Use `invoke_cc_api` with method "get"
- Check if slot shows "Occupied" or "Available"
- If matches expected: mark synced
- Cannot verify actual code value

**If verification fails:**
- Mark as `uncertain` instead of `out_of_sync`
- User can retry or force re-push

## Lock Backends

SlotSentry uses a protocol-based approach to support different lock types.

### LockBackend Protocol

SlotSentry uses a shim/adapter pattern to support different lock protocols. All backends implement the same protocol, but each translates generic calls to protocol-specific operations.

```python
class SlotInfo:
    """Slot information for backend communication."""
    slot_number: int        # Numeric slot index (used by Z-Wave)
    label: str              # User-defined label (used by cloud/name-based backends)

class LockBackend(Protocol):
    """Interface for lock communication."""

    async def push_code(
        self,
        lock_entity_id: str,
        slot_info: SlotInfo,
        code: str,
    ) -> bool:
        """Push a code to a lock slot.

        Args:
            lock_entity_id: HA entity ID of the lock
            slot_info: SlotInfo containing slot_number and label
            code: The PIN code to push

        Returns:
            True if push succeeded (verified or unverified)
            False if push failed

        Raises:
            TimeoutError: If operation exceeds timeout
        """

    async def clear_slot(
        self,
        lock_entity_id: str,
        slot_info: SlotInfo,
    ) -> bool:
        """Clear a slot on a lock.

        Args:
            lock_entity_id: HA entity ID of the lock
            slot_info: SlotInfo containing slot_number and label

        Returns:
            True if clear succeeded
            False if clear failed
        """

    async def verify_slot(
        self,
        lock_entity_id: str,
        slot_info: SlotInfo,
        expected_code: str | None = None,
    ) -> VerifyResult:
        """Verify slot status on lock.

        Args:
            lock_entity_id: HA entity ID of the lock
            slot_info: SlotInfo containing slot_number and label
            expected_code: Optional code to verify against

        Returns:
            VerifyResult with status and optional code
        """

    @property
    def addressing_mode(self) -> str:
        """Return "slot" (numeric) or "name" (label-based) addressing mode."""

    @property
    def supported_code_lengths(self) -> tuple[int, int]:
        """Return (min, max) supported code lengths for validation."""

    @property
    def supports_readback(self) -> bool:
        """True if lock returns actual codes."""
```

### Z-Wave JS Backend (`lock_backends/zwave_js.py`)

Uses Home Assistant's Z-Wave JS integration to control locks.

Services used:

1. **zwave_js.set_lock_usercode**
   ```
   entity_id: lock.xxx
   user_code: "123456"
   code_slot: 1
   ```

2. **zwave_js.clear_lock_usercode**
   ```
   entity_id: lock.xxx
   code_slot: 1
   ```

3. **zwave_js.invoke_cc_api**
   ```
   endpoint: 0
   command_class: 99
   method_name: "get"
   method_arguments: [1]  (slot number)
   ```

Implementation details:

- Convert HA service calls to `hass.services.async_call()`
- Handle different lock models (BE469ZP vs FE599)
- Parse verification response to extract status
- Manage timeouts at service call level

### Adding a New Lock Backend

1. Create `lock_backends/new_backend.py`
2. Implement `LockBackend` protocol
3. Register in coordinator initialization:
   ```python
   from .lock_backends.new_backend import NewBackend

   backend = NewBackend(hass, lock_type)
   ```
4. Test with real hardware before submitting PR
5. Document supported lock models in README

## Extending SlotSentry

### Adding a New Sensor Entity

1. Create class in `sensor.py`:
   ```python
   class SlotSentryNewSensor(CoordinatorEntity, SensorEntity):
       entity_description = SensorEntityDescription(
           key="new_sensor",
           name="New Sensor",
           icon="mdi:icon",
       )

       @property
       def native_value(self):
           return self.coordinator.data.get("new_field")
   ```

2. Register in `async_setup_entry` in `__init__.py`:
   ```python
   await hass.config_entries.async_forward_entry_setup(
       entry, "sensor"
   )
   ```

3. Add strings and icon to `strings.json` and `icons.json`

### Adding a WebSocket Command

1. Add handler in `websocket_api.py`:
   ```python
   @websocket_handler("slotsentry/new_command")
   async def handle_new_command(hass, connection, msg):
       result = await coordinator.do_something(msg.get("param"))
       connection.send_json({"type": "result", "success": True, "data": result})
   ```

2. Update frontend to send new command
3. Update DATA_MODEL.md with command documentation

### Modifying Storage Schema

When changing the stored data structure:

1. Increment version in storage.py
2. Write migration function:
   ```python
   async def _migrate_v1_to_v2(data: dict) -> dict:
       """Migrate storage from v1 to v2."""
       # transform data
       return updated_data
   ```

3. Call migration in `load_data()`:
   ```python
   while data["version"] < CURRENT_VERSION:
       if data["version"] == 1:
           data = await _migrate_v1_to_v2(data)
   ```

4. Update DATA_MODEL.md with new schema
5. Test migration with existing storage files

## Debugging Tips

### Enable Debug Logging

Add to Home Assistant `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.slotsentry: debug
```

Then restart Home Assistant.

### Common Issues

**Issue: Codes not pushing to lock**
- Check Z-Wave JS add-on is running: Settings > Addons > Z-Wave JS
- Verify lock entity exists in HA: Settings > Devices & Services > Devices
- Check coordinator logs for service call failures
- Verify code length matches lock configuration (4-8 digits)

**Issue: Timeout on every push**
- Check HA CPU usage - coordinator might be starved
- Check Z-Wave network health: Settings > Devices > Lock > Logs
- Try pushing to one lock at a time instead of all
- Check network latency between HA and Z-Wave JS add-on

**Issue: Password doesn't work in secure mode**
- Check password has no leading/trailing spaces
- Verify password is 8-16 characters
- Try reconfiguring integration with new password (will lose old codes)
- Check .storage/slotsentry file exists and is readable

**Issue: Codes show as asterisks but can still unlock**
- This is expected on FE599 locks (firmware masks display)
- Codes are encrypted in secure mode, still functional
- Verification checks slot occupancy instead of code value

### Useful Commands

Check storage file format:
```bash
cat ~/.homeassistant/.storage/slotsentry | python -m json.tool
```

View coordinator state:
```python
# In developer tools > python shell
await hass.data["slotsentry"]["coordinator"].async_request_refresh()
print(hass.data["slotsentry"]["coordinator"].data)
```

Test Z-Wave service:
```yaml
# In developer tools > services
Service: zwave_js.set_lock_usercode
Data:
  entity_id: lock.zwave_back_door_deadbolt
  code_slot: 1
  user_code: "123456"
```

### Performance Considerations

- Slot grid: render only visible slots (virtualization for large slot counts may be needed)
- Coordinator: update interval 30-60 seconds (not real-time)
- Push operations: sequential per lock, 60-second timeout
- Storage writes: atomic (temp file + rename) to prevent corruption
- Memory: keep audit log size bounded (rolling buffer)

### Thread Safety

- Coordinator runs in event loop (async)
- WebSocket handlers run in event loop (async)
- Storage I/O is async (file operations)
- No locks needed (single-threaded event loop)

## References

- [Home Assistant Integration Development](https://developers.home-assistant.io/docs/creating_component_index)
- [Z-Wave JS Service Documentation](https://github.com/zwave-js/node-zwave-js)
- [LitElement Best Practices](https://lit.dev/docs/)
- [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket)
