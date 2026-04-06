# SlotSentry — Project Plan

**Version:** 1.2
**Date:** 2026-04-01
**Status:** Planning

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Summary](#architecture-summary)
3. [File Manifest](#file-manifest)
4. [Phase 1 — MVP](#phase-1--mvp)
5. [Phase 2 — Robust](#phase-2--robust)
6. [Phase 3 — Extensible](#phase-3--extensible)
7. [Dependency Graph](#dependency-graph)
8. [Testing Strategy](#testing-strategy)
9. [Risk Assessment](#risk-assessment)
10. [Definition of Done](#definition-of-done)

---

## Overview

SlotSentry is a custom Home Assistant integration for Z-Wave lock code management. It provides a full-featured, Alarmo-style sidebar panel with a slot grid UI, persistent code storage, a commit state machine for reliable code delivery to physical locks, and advanced features including keypad lockout and secure mode with encrypted code storage.

SlotSentry is a code manager only. It never issues `lock.lock` or `lock.unlock` commands. All hardware interaction is limited to reading and writing user code slots via Z-Wave JS services.

**Design principles:**
- Codes are the source of truth on disk; the lock is always brought into sync with disk state, not the reverse.
- No code is lost due to a transient Z-Wave failure — the state machine retries until success or escalation.
- The UI never talks directly to the lock; all mutations go through the Python backend via WebSocket API.
- Secure mode is opt-in but opinionated: codes are encrypted at rest, the panel requires a password, and codes are never exposed in HA state attributes.
- The slot count is determined dynamically at integration setup by the lock with the smallest slot capacity among the selected locks. Commit arrays are sized at that time.

---

## Architecture Summary

```
Browser (LitElement panel)
        |
        | WebSocket commands (custom WS API)
        v
Python backend (integration)
        |
        +-- Storage layer (.storage/slotsentry)
        |
        +-- Z-Wave JS services (set_lock_usercode / clear_lock_usercode)
        |
        +-- HA entity platform (sensor, binary_sensor, button)
        |
        +-- Event bus (audit trail, logbook)
```

**Frontend:** LitElement web component registered as a custom panel via `frontend.async_register_built_in_panel` or a custom panel resource. The panel communicates exclusively through HA's WebSocket API using custom `slotsentry/*` commands.

**Backend:** Standard HA custom integration. A `DataUpdateCoordinator`-like manager (the `SlotManager`) owns all state. The WebSocket API layer translates panel commands into `SlotManager` calls.

**Storage:** HA `.storage/slotsentry` JSON file. Codes and commit state are persisted there. Secure mode encrypts code values using a key derived from a user-supplied password (never stored in plaintext).

**Lock communication:** All lock writes use existing Z-Wave JS services exposed through HA's service layer. No direct Z-Wave JS WebSocket connection is opened by this integration. SlotSentry only calls `set_lock_usercode`, `clear_lock_usercode`, and `invoke_cc_api` — never `lock.lock` or `lock.unlock`.

**Shim/adapter pattern:** The `LockBackend` protocol is the adapter boundary between the `SlotManager` and any physical lock type. The `SlotManager` always works with `SlotInfo` objects (carrying both slot number and label) and never knows how a backend addresses a physical lock. Each backend shim translates `SlotInfo` to the appropriate lock-specific API: `ZWaveJSBackend` uses `slot_info.slot_number` for all Z-Wave JS service calls; a future `SchlageCloudBackend` would use `slot_info.label` as the code name sent to the Schlage cloud API. The `addressing_mode` property on each backend makes this difference explicit and allows the `SlotManager` to apply backend-specific validation rules without tight coupling.

---

## File Manifest

Every file that must be created is listed here. Files are grouped by component. Column **Phase** indicates the build phase in which the file is first required.

### Integration root

| File | Purpose | Phase |
|------|---------|-------|
| `custom_components/slotsentry/__init__.py` | Integration setup, platform loading, SlotManager init, WebSocket API registration | 1 |
| `custom_components/slotsentry/manifest.json` | HA integration manifest (domain, version, dependencies, requirements) | 1 |
| `custom_components/slotsentry/const.py` | All constants: domain, storage key, service names, WS command names, state machine states, defaults | 1 |
| `custom_components/slotsentry/config_flow.py` | Config flow: lock entity multi-select, code length (auto-detected from locks), lockout trigger selection, secure mode toggle | 1 |
| `custom_components/slotsentry/strings.json` | UI strings for config flow and options flow | 1 |
| `custom_components/slotsentry/translations/en.json` | English translations (mirrors strings.json) | 1 |
| `custom_components/slotsentry/storage.py` | `.storage/slotsentry` schema, read/write helpers, migration, encryption stub | 1 |
| `custom_components/slotsentry/slot_manager.py` | Central state manager: in-memory slot state, disk commit arrays, per-lock lock commit arrays, public API for CRUD and push | 1 |
| `custom_components/slotsentry/ws_api.py` | WebSocket command handlers (`slotsentry/get_slots`, `slotsentry/set_slot`, `slotsentry/delete_slot`, `slotsentry/push_all`, `slotsentry/push_lock`, `slotsentry/get_status`) | 1 |
| `custom_components/slotsentry/lock_backend.py` | `LockBackend` base class + `ZWaveJSBackend` concrete implementation; Z-Wave JS service calls, verification, timeout | 1 |
| `custom_components/slotsentry/commit_machine.py` | Async state machine: `IDLE` → `PENDING` → `PUSHING` → `VERIFYING` → `SUCCESS` / `FAILED` / `RETRY`; per-lock per-slot state; retry escalation | 1 |
| `custom_components/slotsentry/sensor.py` | `push_status` sensor entity (state = last push result, attributes = per-lock detail) | 1 |
| `custom_components/slotsentry/binary_sensor.py` | `suppressed` binary_sensor (True when keypad lockout is active on participating locks) | 1 |
| `custom_components/slotsentry/button.py` | `push_all` and `retry_failed` button entities | 1 |
| `custom_components/slotsentry/icons.json` | MDI icon assignments for all entities | 1 |
| `custom_components/slotsentry/hacs.json` | HACS compatibility metadata | 3 |
| `custom_components/slotsentry/diagnostics.py` | HA diagnostics support (redacts codes before export) | 2 |
| `custom_components/slotsentry/keypad_lockout.py` | Keypad lockout logic: monitor lockout trigger entity, disable/enable keypads on participating locks based on target state | 2 |
| `custom_components/slotsentry/secure_mode.py` | Password-based key derivation (PBKDF2-HMAC-SHA256), AES-GCM encryption/decryption, panel authentication WS commands | 2 |
| `custom_components/slotsentry/audit.py` | Event logging, rolling in-memory audit history (last N events), logbook integration, `slotsentry/get_audit` WS command | 2 |

### Frontend panel

| File | Purpose | Phase |
|------|---------|-------|
| `custom_components/slotsentry/frontend/slotsentry-panel.js` | Main LitElement panel web component: sidebar registration, routing to sub-views | 1 |
| `custom_components/slotsentry/frontend/components/slot-grid.js` | Slot grid component: renders slot rows, handles inline edit, Save/Discard/Exit flow | 1 |
| `custom_components/slotsentry/frontend/components/lock-status-bar.js` | Per-lock status badges (synced, pending, failed) | 1 |
| `custom_components/slotsentry/frontend/components/push-toolbar.js` | Push All / Retry Failed buttons and progress indicator | 1 |
| `custom_components/slotsentry/frontend/components/secure-mode-gate.js` | Password prompt overlay; wraps protected content; handles token caching | 2 |
| `custom_components/slotsentry/frontend/components/audit-log.js` | Scrollable audit history table | 2 |
| `custom_components/slotsentry/frontend/slotsentry-panel.css` | Panel styles (CSS custom properties, responsive grid) | 1 |

### Documentation

| File | Purpose | Phase |
|------|---------|-------|
| `docs/PROJECT_PLAN.md` | This file | 1 |
| `docs/architecture.md` | Deep-dive architecture notes, storage schema, WS API reference | 1 |
| `docs/CHANGELOG.md` | Version history | 1 |
| `README.md` | Public-facing HACS README: features, install, config screenshots | 3 |

### Tools / development aids

| File | Purpose | Phase |
|------|---------|-------|
| `tools/simulate_push.py` | Dev script: simulate a push cycle against a mocked lock to exercise state machine | 1 |
| `tools/dump_storage.py` | Dev script: pretty-print `.storage/slotsentry` to stdout (decrypts if password given) | 1 |

---

## Phase 1 — MVP

**Goal:** A working integration that can discover Z-Wave locks, determine slot count from lock capabilities, store slot codes persistently, display them in a sidebar panel, push codes to locks, and track commit state.

---

### Task 1.1 — Integration Scaffold

**Complexity:** S
**Blocks:** Everything else

**Deliverables:**
- `manifest.json` with domain `slotsentry`, version `0.1.0`, `iot_class: local_push`, dependencies `["zwave_js"]`, no codeowners
- `const.py` with all string constants (no magic strings anywhere else in the codebase)
- `__init__.py` with `async_setup_entry` / `async_unload_entry` stubs that log on entry

**Checklist:**
- [ ] Integration loads without errors in HA (`ha core logs` shows no warnings)
- [ ] `manifest.json` passes `hass --script check_config` (or equivalent)
- [ ] All platform names listed in manifest match actual platform files that exist

**Constants to define in `const.py`:**
```python
DOMAIN = "slotsentry"
STORAGE_KEY = "slotsentry"
STORAGE_VERSION = 1
PLATFORMS = ["sensor", "binary_sensor", "button"]
DEFAULT_CODE_LENGTH_SINGLE = 6
DEFAULT_CODE_LENGTH_SHORT = 4
DEFAULT_CODE_LENGTH_LONG = 6
MAX_SLOTS = 250
PUSH_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

# Z-Wave JS service constants
ZWAVE_DOMAIN = "zwave_js"
SERVICE_SET_LOCK_USERCODE = "set_lock_usercode"
SERVICE_CLEAR_LOCK_USERCODE = "clear_lock_usercode"

# WebSocket commands
WS_GET_SLOTS = "slotsentry/get_slots"
WS_SET_SLOT = "slotsentry/set_slot"
WS_DELETE_SLOT = "slotsentry/delete_slot"
WS_PUSH_ALL = "slotsentry/push_all"
WS_PUSH_LOCK = "slotsentry/push_lock"
WS_GET_STATUS = "slotsentry/get_status"

# State machine states
STATE_IDLE = "idle"
STATE_PENDING = "pending"
STATE_PUSHING = "pushing"
STATE_VERIFYING = "verifying"
STATE_SUCCESS = "success"
STATE_FAILED = "failed"
STATE_RETRY = "retry"
```

---

### Task 1.2 — Config Flow

**Complexity:** M
**Blocks:** Task 1.5 (storage layer needs to know which locks are configured)

**Deliverables:**
- `config_flow.py` with `SlotSentryConfigFlow` and `SlotSentryOptionsFlow`
- `strings.json` and `translations/en.json`

**Config flow steps:**

| Step | Fields | Validation |
|------|--------|------------|
| `user` | `lock_entities` (multi-select from `lock.*` entities) | At least one lock required |
| `options` | `code_length` (int 4–8, auto-suggested from lock discovery), `slot_count` (int 1–250, auto-set from minimum lock capacity) | Range validation |
| `options` | `secure_mode` (bool) | Conditional: if secure_mode, warn user about password setup |

**Code length discovery:** During config flow, the integration queries each selected lock's capabilities (via `invoke_cc_api` or lock entity attributes) to suggest appropriate code length defaults. If discovery fails or the data is unavailable, defaults to 4/6 (two lengths) or 6 (single length).

**Slot count:** Automatically determined as the minimum slot capacity across the selected locks. Displayed to the user for confirmation but not manually editable.

**Options flow:** All config fields re-exposed so user can add/remove locks and change code length post-setup. Slot count is re-evaluated when locks change.

**Checklist:**
- [ ] Config flow appears in Integrations UI and completes without error
- [ ] Selected locks are stored in `config_entry.data["lock_entities"]` (list of entity IDs)
- [ ] Code length stored in `config_entry.options["code_length"]`
- [ ] Slot count stored in `config_entry.data["slot_count"]`
- [ ] Options flow changes are applied on reload without full HA restart
- [ ] Removing a lock from options flow triggers cleanup of its commit state

---

### Task 1.3 — Storage Layer

**Complexity:** M
**Blocks:** Task 1.4 (SlotManager reads/writes storage), Task 1.7 (commit machine persists state here)

**Deliverables:**
- `storage.py` with async `load()`, `save()`, `migrate()` functions
- Defined JSON schema (documented in `docs/architecture.md`)

**Storage schema (`slotsentry` key in `.storage/slotsentry`):**

```json
{
  "version": 1,
  "slot_count": 19,
  "slots": {
    "1": {
      "label": "House Cleaner",
      "code": "1234",
      "enabled": true,
      "created_at": "2026-03-31T00:00:00Z",
      "updated_at": "2026-03-31T00:00:00Z"
    }
  },
  "disk_commit": {
    "1": "2026-03-31T00:00:00Z"
  },
  "lock_commit": {
    "lock.front_door": {
      "1": {
        "state": "success",
        "pushed_at": "2026-03-31T00:00:00Z",
        "code_hash": "sha256:abcd..."
      }
    }
  },
  "config": {
    "code_length": 4,
    "slot_count": 19
  }
}
```

**Commit tracking semantics:**
- `disk_commit[slot_id]` = timestamp of last disk write for this slot. Updated immediately on any slot mutation.
- `lock_commit[lock_entity][slot_id].code_hash` = SHA-256 of the code last successfully pushed to that lock. If the current slot's code hash differs from `lock_commit`, the slot is dirty for that lock.
- A slot is considered "in sync" for a lock when `code_hash` matches AND `state == "success"`.

**Checklist:**
- [ ] `.storage/slotsentry` file is created on first setup
- [ ] File survives HA restart (data is loaded back correctly)
- [ ] Schema version field enables future migrations
- [ ] `migrate()` is a no-op at version 1 but logs a warning for unknown versions

---

### Task 1.4 — SlotManager

**Complexity:** L
**Blocks:** Task 1.5 (WS API calls SlotManager), Task 1.6 (entities query SlotManager)

**Deliverables:**
- `slot_manager.py` with `SlotManager` class

**Public API:**
```python
class SlotManager:
    async def async_load(self) -> None: ...
    async def async_get_slots(self) -> dict[int, SlotData]: ...
    async def async_set_slot(self, slot_id: int, label: str, code: str, enabled: bool) -> None: ...
    async def async_delete_slot(self, slot_id: int) -> None: ...
    async def async_push_all(self) -> None: ...
    async def async_push_lock(self, lock_entity: str) -> None: ...
    def get_push_status(self) -> dict: ...
    def get_lock_commit_state(self, lock_entity: str, slot_id: int) -> CommitState: ...
    @property
    def slot_count(self) -> int: ...  # From config entry; minimum across configured locks
```

**Internal responsibilities:**
- Holds in-memory copy of all slot data
- On `set_slot` / `delete_slot`: writes to disk (via `storage.py`) then fires push for all configured locks
- Manages `dirty` tracking per lock per slot (compare code hash)
- Fires HA events on state changes (`slotsentry_push_status_changed`) so entities can update
- Enforces label uniqueness (case-insensitive) across all non-empty slots before any write; empty labels are exempt from this check
- Constructs a `SlotInfo` dataclass from slot data before every backend call, carrying both `slot_number` and `label` so backends have full context regardless of their `addressing_mode`

**Label uniqueness rule:** Before writing a slot, `set_slot` checks that no other slot with a non-empty label shares the same label (case-insensitive). If a duplicate is found, the operation is rejected with a descriptive error. This prevents name collision on name-based backends (e.g., Schlage cloud) and improves UX on slot-based backends by eliminating ambiguous labels in the UI.

**Checklist:**
- [ ] `get_slots()` returns correct data after HA restart
- [ ] `set_slot()` immediately marks slot dirty for all locks
- [ ] `delete_slot()` clears slot from disk and from all lock commit states
- [ ] Manager emits events that trigger entity state updates
- [ ] `set_slot` with a duplicate label returns error (case-insensitive match, empty labels exempt)

---

### Task 1.5 — WebSocket API

**Complexity:** M
**Blocks:** Task 1.6 (frontend uses WS commands)

**Deliverables:**
- `ws_api.py` with all Phase 1 command handlers registered in `__init__.py`

**Command specifications:**

| Command | Direction | Payload | Response |
|---------|-----------|---------|----------|
| `slotsentry/get_slots` | C→S | `{}` | `{slots: {id: SlotData}, config: {...}, slot_count: N}` |
| `slotsentry/set_slot` | C→S | `{slot_id, label, code, enabled}` | `{success: bool, error?: str}` |
| `slotsentry/delete_slot` | C→S | `{slot_id}` | `{success: bool}` |
| `slotsentry/push_all` | C→S | `{}` | `{success: bool}` (push is async, status via get_status) |
| `slotsentry/push_lock` | C→S | `{lock_entity}` | `{success: bool}` |
| `slotsentry/get_status` | C→S | `{}` | `{push_status: {...}, lock_states: {...}}` |

**All commands require authentication** (HA WS auth is handled by the HA framework before commands are dispatched).

**Error handling:** Every handler must return `{success: false, error: "human readable message"}` for all failure modes rather than raising unhandled exceptions that disconnect the WS client.

**Checklist:**
- [ ] Commands appear in HA developer tools → WebSocket API tester
- [ ] `get_slots` returns correct data structure including `slot_count`
- [ ] `set_slot` with invalid code length returns error (not exception)
- [ ] Commands require `hass.auth` (no anonymous access)

---

### Task 1.6 — Entity Platform

**Complexity:** S
**Blocks:** Nothing (but is a deliverable for MVP)

**Deliverables:**
- `sensor.py` — `SlotSentryPushStatusSensor`
- `binary_sensor.py` — `SlotSentrySupressedSensor`
- `button.py` — `SlotSentryPushAllButton`, `SlotSentryRetryButton`
- `icons.json`

**Entity specifications:**

| Entity | Class | State | Attributes |
|--------|-------|-------|-----------|
| `sensor.slotsentry_push_status` | SensorEntity | `idle` / `pushing` / `success` / `failed` | `{locks: {entity_id: {state, last_push, dirty_slots}}}` |
| `binary_sensor.slotsentry_suppressed` | BinarySensorEntity | `on` when keypad lockout active | `{trigger_entity, target_state}` |
| `button.slotsentry_push_all` | ButtonEntity | — | — |
| `button.slotsentry_retry_failed` | ButtonEntity | — | — |

**Entities must:**
- Use `async_write_ha_state()` on `slotsentry_push_status_changed` event
- Have unique IDs based on `config_entry.entry_id + "_" + entity_type`
- Have device info grouping all entities under a single `SlotSentry` device

**Checklist:**
- [ ] All entities appear in HA UI under a single device
- [ ] `push_all` button press triggers `slot_manager.async_push_all()`
- [ ] Sensor state updates within 1 second of a push completing
- [ ] Entities survive config entry reload

---

### Task 1.7 — Commit State Machine

**Complexity:** XL
**Blocks:** Nothing (called by SlotManager), but must be solid before MVP is declared done

**Deliverables:**
- `commit_machine.py` with `LockCommitMachine` class

**State machine per (lock, slot) pair:**

```
IDLE
  │  (slot marked dirty)
  ▼
PENDING
  │  (push worker picks up)
  ▼
PUSHING ──── timeout / service error ──▶ RETRY (up to MAX_RETRIES)
  │                                           │
  │ (service call returned)                   │ (retries exhausted)
  ▼                                           ▼
VERIFYING                                  FAILED
  │  (readback matches)
  ▼
SUCCESS ──── (slot mutated again) ──▶ PENDING
```

**Implementation notes:**
- The machine runs as an `asyncio.Task` spawned per lock (not per slot), iterating over all dirty slots for that lock sequentially.
- `VERIFYING` step: read current lock usercode via `zwave_js.get_lock_usercode` (if available) or via `invoke_cc_api` with `UserCode CC`, compare to what was written. If Z-Wave JS does not support readback, skip verify and go directly to `SUCCESS` with a flag `verified: false`.
- Retry backoff: 5s, 15s, 30s (fixed, not exponential, to keep UX predictable).
- The machine persists its state to storage so a mid-push HA restart picks up where it left off.
- `LockSlotCommit` must be implemented as a proper Python dataclass (not a bare dict). This makes the schema explicit, enables type checking, and allows new fields to be added as clean schema migrations. Include a `last_pushed_label: str | None` field (default `None`) in the dataclass now, even though it is only acted on by name-based backends. This avoids a schema migration when a name-based backend is added later.

```python
@dataclass
class LockSlotCommit:
    state: str                    # "synced" | "out_of_sync" | "uncertain" | "error"
    code_hash: str | None         # sha256 of last successfully pushed code
    pushed_at: str | None         # ISO timestamp of last successful push
    last_pushed_label: str | None = None  # Label used in last push (for name-based backends)
```

**Checklist:**
- [ ] A dirty slot for a healthy lock reaches `SUCCESS` state
- [ ] A Z-Wave service call failure triggers retry, not crash
- [ ] After `MAX_RETRIES` failures, state is `FAILED` and sensor reflects this
- [ ] HA restart with an in-progress push resumes correctly (not stuck in `PUSHING`)
- [ ] Multiple locks push concurrently (one task per lock, not serialized)

---

### Task 1.8 — Lock Backend

**Complexity:** M
**Blocks:** Task 1.7 (state machine calls backend)

**Deliverables:**
- `lock_backend.py` with `SlotInfo` dataclass, `LockBackend` Protocol, and `ZWaveJSBackend`

**Interface:**
```python
@dataclass
class SlotInfo:
    slot_number: int
    label: str

class LockBackend(Protocol):
    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool: ...
    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool: ...
    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None: ...
    async def async_get_all_usercodes(self) -> dict[int, str] | None: ...
    @property
    def supports_readback(self) -> bool: ...
    @property
    def addressing_mode(self) -> str: ...  # "slot" or "name"
    @property
    def supported_code_lengths(self) -> tuple[int, int]: ...  # (min, max)
```

All methods receive a `SlotInfo` dataclass instead of a bare `slot: int`. This makes the protocol extensible: future backends that need the label (e.g., `SchlageCloudBackend`) receive it without any method signature changes. `ZWaveJSBackend` uses `slot_info.slot_number` for all service calls and ignores `slot_info.label` entirely.

The `SlotManager` is responsible for constructing `SlotInfo` from slot data before every backend call.

**ZWaveJSBackend implementation:**
- `async_set_usercode`: calls `zwave_js.set_lock_usercode` with `code_slot=slot_info.slot_number`, `usercode=code`. Ignores `slot_info.label`.
- `async_clear_usercode`: calls `zwave_js.clear_lock_usercode` with `code_slot=slot_info.slot_number`. Ignores `slot_info.label`.
- `async_get_usercode`: calls `zwave_js.invoke_cc_api` with `commandClassName: "User Code"`, `methodName: "get"`, `args: [slot_info.slot_number]`. Returns `None` if not supported.
- `async_get_all_usercodes`: returns `None`. Z-Wave JS does not support efficient bulk readback; the commit machine falls back to per-slot `async_get_usercode` queries.
- `supports_readback`: `True` if `async_get_usercode` returned data on test call during init, `False` otherwise (graceful degradation).
- `addressing_mode`: returns `"slot"`. Z-Wave locks address codes by physical slot number.
- `supported_code_lengths`: returns the lock's configured code length range as `(min, max)` discovered during init (e.g., `(6, 6)` for a lock fixed at 6 digits, `(4, 8)` for a fully configurable lock). This allows the commit machine to pre-validate code length before attempting a push.

**Checklist:**
- [ ] `set_usercode` returns `True` on successful service call, `False` on service error
- [ ] `get_usercode` returns `None` without raising if Z-Wave JS does not support UserCode CC get
- [ ] Backend instantiated per lock entity (not shared)
- [ ] `SlotInfo` dataclass carries both slot_number and label to every backend call
- [ ] `addressing_mode` returns `"slot"` for ZWaveJSBackend
- [ ] `supported_code_lengths` returns correct range for each lock

---

### Task 1.9 — Sidebar Panel (Frontend)

**Complexity:** XL
**Blocks:** Nothing upstream; depends on WS API being complete (Task 1.5)

**Deliverables:**
- `frontend/slotsentry-panel.js` (main panel LitElement component)
- `frontend/components/slot-grid.js`
- `frontend/components/lock-status-bar.js`
- `frontend/components/push-toolbar.js`
- `frontend/slotsentry-panel.css`
- Panel registration in `__init__.py` via `hass.components.frontend.async_register_built_in_panel` or custom panel resource

**UI layout:**

```
┌─────────────────────────────────────────┐
│  SlotSentry                    [Push All]│
│  ─────────────────────────────────────  │
│  Lock Status: front_door [synced]        │
│              back_door   [2 pending]     │
│  ─────────────────────────────────────  │
│  Slot  Label           Code    Enabled   │
│  ───   ─────────────   ──────  ───────   │
│  1     House Cleaner   ****    [on]  [✎] │
│  2     Dog Walker      ****    [on]  [✎] │
│  3     (empty)         —       —     [+] │
│  ...                                     │
│  ─────────────────────────────────────  │
│  Update All Slots: [ ]   [Discard] [Save]│
│                                   [Exit] │
└─────────────────────────────────────────┘
```

**Slot row states:**
- `clean` — green dot, shows masked code (`****`)
- `dirty` — yellow dot, unsaved changes indicator
- `pushing` — spinner
- `failed` — red dot, retry button appears

**Edit flow:**
1. User clicks edit icon on a row → row expands with label input and code input
2. User types new code → real-time length validation (must match configured `code_length`)
3. User clicks Save → WS `set_slot` → row returns to `dirty` state briefly → transitions to `pushing` → `clean`
4. User clicks Discard → row returns to previous state with no WS call
5. Exit shown when no pending changes; closes the panel

**Button flow rules:**
- On panel open (no changes): show **Exit**
- After any edit: show **Save** and **Discard**; hide **Exit**
- After successful Save: show **Exit** again

**Checklist:**
- [ ] Panel appears in HA sidebar after integration setup
- [ ] Panel loads slot data via `get_slots` WS command on mount
- [ ] Slot row edit validates code length before allowing save
- [ ] Status badges update in real time (poll `get_status` every 2s during active push)
- [ ] Panel is mobile-responsive (single column below 600px)
- [ ] Panel works in both light and dark HA themes (uses CSS custom properties `--primary-color` etc.)
- [ ] Save/Discard/Exit button states follow the defined flow

---

## Phase 2 — Robust

**Goal:** Production-quality integration. Keypad lockout, secure mode, audit trail, and diagnostics. Safe to use in a real home.

---

### Task 2.1 — Keypad Lockout

**Complexity:** M
**Depends on:** Phase 1 complete

**Deliverables:**
- `keypad_lockout.py` with `KeypadLockoutMonitor`

**Behavior:**
- User selects a **lockout trigger entity** (any HA entity: alarm panel, presence sensor, time of day, binary sensor, etc.) and a **target state** for it.
- Per-lock checkboxes allow individual locks to **participate** in keypad lockout.
- When the lockout trigger reaches the target state:
  - Disable keypads on participating locks via `invoke_cc_api` with `DoorLock CC`, `setConfiguration`, setting `"Operating Mode"` to `"Secured"` (or equivalent per lock hardware)
  - Fire `slotsentry_keypad_lockout` HA event with `{lock_entity, sensor_entity, target_state}`
- When the sensor changes away from the target state:
  - Re-enable keypads on participating locks (set back to normal operating mode)
  - Fire `slotsentry_keypad_unlock` HA event
- Codes are **never** cleared; only the hardware keypad input is gated.
- SlotSentry does not issue `lock.lock` or `lock.unlock` commands as part of keypad lockout.
- Example: When `alarm_control_panel.alarm` reaches `"armed_home"`, disable keypads on back door and utility room locks.

**Config options added:**
- `keypad_lockout_enabled` (bool, default `false`)
- `lockout_trigger_entity` (str, entity ID of lockout trigger, e.g., `alarm_control_panel.alarm`)
- `keypad_lockout_target_state` (str, target state to trigger lockout, e.g., `"armed_home"`)

**Checklist:**
- [ ] Monitor starts when integration loads and stops cleanly on unload
- [ ] Lockout trigger changes to target state → keypads disabled on participating locks within 5 seconds
- [ ] Sensor changes away from target state → keypads re-enabled
- [ ] Lockout fires `slotsentry_keypad_lockout` event that appears in logbook
- [ ] Locks with `participating: false` are ignored by the monitor
- [ ] Codes remain intact in storage and on locks throughout lockout/unlock cycle

---

### Task 2.2 — Secure Mode

**Complexity:** L
**Depends on:** Task 1.3, Task 1.5

**Deliverables:**
- `secure_mode.py` with encryption/decryption and panel auth WS commands
- `frontend/components/secure-mode-gate.js`

**Encryption scheme:**
- Key derivation: PBKDF2-HMAC-SHA256, 260,000 iterations, 16-byte random salt stored in `.storage/slotsentry`
- Encryption: AES-256-GCM, 12-byte random nonce per encrypted value
- Storage format: `{"cipher": "aes-256-gcm", "salt": "hex", "nonce": "hex", "tag": "hex", "ciphertext": "hex"}`
- Password is never stored; only the salt is stored
- Python stdlib `hashlib` + `cryptography` package (added to `requirements` in manifest)

**Panel authentication flow:**
1. Panel loads → detects `secure_mode: true` in config → renders `<secure-mode-gate>`
2. Gate shows password prompt, sends `slotsentry/auth_panel` WS command with password
3. Backend derives key, attempts to decrypt one test value; if successful, returns a short-lived session token (UUID, stored in memory only, 4-hour TTL)
4. Panel stores token in `sessionStorage`; includes in all subsequent WS commands
5. On token expiry or HA restart: panel shows password prompt again

**Code reveal:**
- By default, codes are shown as `****` in the panel regardless of secure mode
- User can click a reveal icon on a row to send `slotsentry/reveal_slot` with session token
- Backend decrypts and returns plaintext code; panel shows it for 10 seconds then re-masks

**New WS commands added in this task:**

| Command | Payload | Response |
|---------|---------|----------|
| `slotsentry/auth_panel` | `{password}` | `{success, session_token?, error?}` |
| `slotsentry/reveal_slot` | `{slot_id, session_token}` | `{success, code?, error?}` |
| `slotsentry/set_secure_password` | `{old_password?, new_password, session_token?}` | `{success, error?}` |

**Checklist:**
- [ ] Codes stored as encrypted blobs in `.storage/slotsentry` when secure mode enabled
- [ ] Wrong password returns `{success: false}` without leaking timing information (constant-time compare)
- [ ] Session token not logged anywhere
- [ ] Code reveal auto-hides after 10 seconds (client-side timer)
- [ ] HA restart invalidates all session tokens
- [ ] `diagnostics.py` never exports plaintext codes (exports `[REDACTED]`)

---

### Task 2.3 — Audit Trail

**Complexity:** M
**Depends on:** Task 1.4, Task 1.5

**Deliverables:**
- `audit.py` with `AuditLogger`
- `frontend/components/audit-log.js`

**Audit events to record:**

| Event | Data |
|-------|------|
| `slot_created` | `{slot_id, label, by: "panel"}` |
| `slot_updated` | `{slot_id, label, code_changed: bool}` |
| `slot_deleted` | `{slot_id, label}` |
| `push_started` | `{lock_entity, dirty_slots: [ids]}` |
| `push_success` | `{lock_entity, slot_id, verified: bool}` |
| `push_failed` | `{lock_entity, slot_id, error, attempt}` |
| `keypad_lockout` | `{lock_entity, sensor_entity, target_state}` |
| `secure_auth_success` | `{ip_address}` |
| `secure_auth_failure` | `{ip_address}` |
| `code_revealed` | `{slot_id, ip_address}` |

**Storage:** Rolling ring buffer of last 1,000 events in `.storage/slotsentry` under `audit_log` key. Events older than the buffer are dropped.

**Logbook integration:** Fire `slotsentry_audit` HA events for significant operations so they appear in the HA logbook UI.

**New WS command:**

| Command | Payload | Response |
|---------|---------|----------|
| `slotsentry/get_audit` | `{limit?: int, since?: iso_timestamp}` | `{events: [...], total: int}` |

**Checklist:**
- [ ] Audit log persists across HA restart
- [ ] Events appear in HA logbook for push operations
- [ ] `get_audit` with `limit=10` returns only last 10 events
- [ ] Code values are never written to audit log (label only, `code_changed: bool`)
- [ ] Audit log view in panel shows timestamp, event type, details in a scrollable table

---

### Task 2.4 — Diagnostics

**Complexity:** S
**Depends on:** Phase 1 complete

**Deliverables:**
- `diagnostics.py`

**Required by HA quality scale.** Must implement `async_get_config_entry_diagnostics`.

**Export includes:**
- Config entry options (minus password/key material)
- Number of configured slots and slot count
- Per-lock commit state summary (state counts: success/failed/pending)
- Audit log summary (last 5 events, codes redacted)

**Must NOT include:**
- Any slot code values (replace with `[REDACTED]`)
- Encryption keys or salts
- Session tokens

**Checklist:**
- [ ] Diagnostics download from UI contains no plaintext codes
- [ ] Diagnostics includes enough data to diagnose a stuck push
- [ ] File passes HA diagnostics validator (if available)

---

## Phase 3 — Extensible

**Goal:** HACS distribution, LockBackend protocol for other lock types, temporary codes.

---

### Task 3.1 — LockBackend Protocol (Formalize) + SchlageCloudBackend Foundation

**Complexity:** M
**Depends on:** Phase 1 Task 1.8

**Context:** The `LockBackend` protocol is already fully defined in Phase 1 (Task 1.8), including `SlotInfo`, `addressing_mode`, `supported_code_lengths`, and `async_get_all_usercodes`. Phase 3 does not need to redesign the protocol — it formalizes documentation, adds `MockLockBackend`, and delivers the first name-based backend shim.

**Deliverables:**
- Complete full docstrings on `LockBackend`, `SlotInfo`, and `ZWaveJSBackend` in `lock_backend.py` explaining the contract, the `addressing_mode` discriminator, and how to implement a new backend
- Add `MockLockBackend` for testing — implements all protocol methods with configurable behavior (configurable `supports_readback`, `addressing_mode`, `supported_code_lengths`; records calls for assertion in tests)
- Document how third-party developers can implement alternative backends (e.g., Yale via Bluetooth, August via cloud)
- Add `backend_type` field to config entry so future backends can be selected in config flow (default `"zwave_js"`)
- Begin `SchlageCloudBackend` as a new class in `lock_backend.py` (or a separate `schlage_backend.py`): implements `LockBackend` with `addressing_mode = "name"`, using `schlage.add_code` / `schlage.delete_code` / `schlage.get_codes` HA services. `async_get_all_usercodes` calls `schlage.get_codes` once and maps names to slot numbers via the `SlotManager`'s label index. This backend is a planned Phase 2/3 deliverable and is the primary motivation for the `addressing_mode` and `SlotInfo` design choices made in Phase 1.

**Checklist:**
- [ ] `MockLockBackend` can be injected in tests
- [ ] Protocol class has full docstrings explaining contract
- [ ] Config entry schema includes `backend_type` (default `"zwave_js"`)
- [ ] `SchlageCloudBackend` implements `LockBackend` with `addressing_mode = "name"`
- [ ] `SchlageCloudBackend.async_get_all_usercodes` returns full code dict from a single `schlage.get_codes` call

---

### Task 3.2 — Temporary Codes

**Complexity:** L
**Depends on:** Phase 2 complete

**Deliverables:**
- Extend storage schema with `expires_at` field on slots
- `SlotManager` checks expiry on load and periodically (every 60 seconds)
- Expired slots are automatically deleted (triggers push to clear from locks)
- Config flow / options adds `enable_temp_codes` toggle
- Panel UI: date-time picker on slot edit form when temp codes enabled
- Expiry shown in slot grid as relative time ("expires in 3h")
- Audit event: `slot_expired` with `{slot_id, label}`

**New WS command:**

| Command | Payload | Response |
|---------|---------|----------|
| `slotsentry/set_slot` | Extended: `{..., expires_at?: iso_timestamp}` | unchanged |

**Checklist:**
- [ ] Slot with `expires_at` in the past is deleted on HA restart
- [ ] Expiry timer fires within 60 seconds of expiry time
- [ ] Expired slot deletion triggers push to clear code from all locks
- [ ] Audit log records `slot_expired` event
- [ ] Panel shows expiry countdown in slot grid

---

### Task 3.3 — HACS Packaging

**Complexity:** S
**Depends on:** Phase 2 complete (MVP-quality code before publishing)

**Deliverables:**
- `hacs.json`
- `README.md` (public-facing, with screenshots, install instructions)
- `docs/CHANGELOG.md` updated
- GitHub Actions workflow: `.github/workflows/release.yml` — tags a release, zips `custom_components/slotsentry/`, creates GitHub release with attached zip
- Brand assets: `custom_components/slotsentry/brands/icon.png`, `icon@2x.png` (256x256 and 512x512)

**`hacs.json`:**
```json
{
  "name": "SlotSentry",
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

**Checklist:**
- [ ] Integration installable via HACS custom repository
- [ ] GitHub release includes correct file structure for HACS auto-detection
- [ ] `README.md` includes: features list, prerequisites (Z-Wave JS), install steps, config steps, screenshot of panel
- [ ] Release workflow runs on `git tag v*` push

---

### Task 3.4 — Management Mode Selection (Group / Independent / Lead Lock)

**Complexity:** XL
**Depends on:** Phase 2 complete, Task 3.1

**Context:** SlotSentry currently operates in a single mode — **group mode** — where all locks share the same slot grid and receive the same codes. Phase 3 introduces a **management mode** config flow choice offering three modes, each serving a different use case.

---

#### Mode A: Group Mode (current default)

Unchanged from today. All locks share one slot grid. Save → push to all locks. Best for households where every door should have identical codes.

---

#### Mode B: Independent Lock Mode

Each lock has its own slot grid with its own codes, labels, and enable states. Front door can have 10 codes while garage has 3 completely different codes. Best for mixed-use properties, Airbnb hosts with per-unit locks, or any scenario where locks need different code sets.

**Behavior:**
- Storage uses per-lock slot arrays: `slots.<lock_entity_id>.{slot_number: SlotData}`
- Each lock keeps its own slot count (from its hardware `code_slot_count`)
- Panel shows a tab or dropdown per lock, each with its own independent slot grid
- Push operations apply only to the selected lock's slots
- Code lengths are per-lock (already supported via `per_lock_code_length`)

**Design considerations:**
- `SlotManager` needs mode-aware methods: `get_slots(lock_entity=None)` returns shared slots in group, per-lock slots in independent
- `commit_machine.py` is unaffected — already operates per-lock
- Panel needs significant rework: lock selector tab bar, per-lock grids
- Migration: group → independent copies shared slots to each lock; independent → group asks user to pick a source lock

---

#### Mode C: Lead Lock Mode

Like group mode (shared slot grid, all locks get the same codes), but one lock is designated the **lead lock**. SlotSentry monitors the lead lock for code changes made outside the panel (e.g., programmed at the keypad, changed via another integration, or set by a property manager). When a change is detected on the lead lock, SlotSentry automatically propagates it to all other managed locks.

**Use case:** A rental property manager programs codes directly on the front door deadbolt (the lead lock). SlotSentry detects the new code and pushes it to the back door, garage, and utility room locks automatically — no need to open the panel.

**Behavior:**
- Config flow designates one lock as the lead lock (dropdown from managed locks)
- **Lead lock constraint:** In single code length mode, the lead lock can be any managed lock. In dual code length mode, the lead lock **must** be a lock assigned the longer code length (`code_length_2`). This is because the propagation strategy truncates the lead lock's code to derive the shorter code.
- SlotSentry periodically polls the lead lock's code slots (configurable interval, default every 5 minutes) using `async_get_usercode` readback
- On detecting a change (code added, modified, or cleared on the lead lock):
  1. Update the SlotSentry storage to match the lead lock's state
  2. In dual mode: the lead lock's full code becomes `code_2` (long code); the first N digits become `code_1` (short code), where N = `code_length_1`
  3. Mark all other locks as out_of_sync for the affected slots
  4. Trigger a push to propagate the change to all follower locks
  5. Fire an audit event: `lead_lock_change_detected` with slot number and action (set/clear)
- The lead lock's codes are the **source of truth** — if someone edits a code in the panel AND on the lead lock simultaneously, the lead lock wins on next poll
- Lead lock changes detected via panel edits still work normally (save → push to all)

**Lead lock requirements:**
- Must support code readback (`supports_readback = True`). Locks that return asterisks (e.g., FE599) cannot be lead locks.
- In dual mode, must be assigned the longer code length

**Code truncation example (dual mode):**
- Lead lock has code length 6, follower locks have code length 4
- User programs `123456` on the lead lock's slot 5
- SlotSentry detects: `code_2 = "123456"`, derives `code_1 = "1234"` (first 4 digits)
- Pushes `123456` to other 6-digit locks, `1234` to 4-digit locks

**Polling strategy:**
- Default: poll lead lock every 5 minutes (`LEAD_LOCK_POLL_INTERVAL = 300`)
- Poll is a sequential readback of all active slots (reuses existing `async_get_usercode`)
- Inter-slot delay applies (uses latency profiling data)
- Poll skipped if a push is currently in progress on the lead lock
- Configurable: user can increase/decrease interval in config flow options

**New config keys:**
- `CONF_MANAGEMENT_MODE`: `"group"` | `"independent"` | `"lead_lock"`
- `CONF_LEAD_LOCK_ENTITY`: entity_id of the lead lock
- `CONF_LEAD_LOCK_POLL_INTERVAL`: seconds between polls (default 300)

**Checklist:**
- [ ] Config flow offers Group / Independent / Lead Lock mode choice
- [ ] Lead lock dropdown only shows readback-capable locks
- [ ] In dual mode, lead lock dropdown only shows locks with the longer code length
- [ ] Periodic poll detects added, changed, and cleared codes on lead lock
- [ ] Detected changes propagate to all follower locks automatically
- [ ] Dual mode truncation: lead lock's full code → short code uses first N digits
- [ ] Lead lock changes override panel edits on conflict (lead lock is source of truth)
- [ ] Audit events fired for all lead lock change detections
- [ ] Poll respects latency profiling and inter-slot delay
- [ ] Poll skipped during active push operations
- [ ] Panel shows lead lock indicator badge and last-poll timestamp

---

**Shared deliverables across all three modes:**
- Config flow adds **management mode** selector on a new step after lock selection
- `CONF_MANAGEMENT_MODE` stored in config entry (default `"group"` for backwards compatibility)
- `SlotManager` becomes mode-aware; all existing group-mode behavior preserved exactly
- Migration path between modes handled via reconfigure flow with data migration warnings
- All modes support: latency profiling, keypad lockout, secure mode, push status tracking

---

## Dependency Graph

```
Task 1.1 (Scaffold)
    ├── Task 1.2 (Config Flow)
    │       └── Task 1.3 (Storage)
    │               └── Task 1.4 (SlotManager)
    │                       ├── Task 1.5 (WS API)
    │                       │       └── Task 1.9 (Frontend Panel)
    │                       └── Task 1.6 (Entity Platform)
    ├── Task 1.8 (Lock Backend)
    │       └── Task 1.7 (Commit Machine)
    │               └── [Task 1.4 calls Task 1.7]
    │
Phase 2 (all depend on Phase 1 complete):
    ├── Task 2.1 (Keypad Lockout)      — independent
    ├── Task 2.2 (Secure Mode)         — depends on Task 1.3, 1.5
    ├── Task 2.3 (Audit Trail)         — depends on Task 1.4, 1.5
    └── Task 2.4 (Diagnostics)         — independent

Phase 3 (all depend on Phase 2 complete):
    ├── Task 3.1 (LockBackend Protocol) — refactor of Task 1.8
    ├── Task 3.2 (Temporary Codes)      — depends on Phase 2 complete
    ├── Task 3.3 (HACS Packaging)       — depends on Phase 2 complete
    └── Task 3.4 (Management Modes)     — depends on Task 3.1
        ├── Mode B (Independent Lock)   — storage + panel rework
        └── Mode C (Lead Lock)          — polling + truncation + audit
```

**Critical path:** 1.1 → 1.2 → 1.3 → 1.4 → 1.7 → panel demo

---

## Testing Strategy

### Phase 1 — MVP

| Layer | Approach | Tools |
|-------|----------|-------|
| Storage schema | Unit tests: write schema, reload, compare | Python unittest + `pytest` |
| SlotManager | Unit tests with mocked storage and mocked backend | pytest + `unittest.mock` |
| WS API | Integration tests using `hass_ws_client` fixture from `pytest-homeassistant-custom-component` | pytest |
| Commit machine | Unit tests: inject `MockLockBackend`, step through state transitions | pytest |
| Config flow | Unit tests using HA test helpers (`config_entries_flow_manager`) | pytest |
| Frontend panel | Manual testing in browser developer tools; WebSocket command trace via HA developer tools | Browser devtools |
| End-to-end | Set up integration on test instance, push a code to a real Z-Wave lock, verify via lock keypad | Manual |

**Test files to create:**
- `tests/test_storage.py`
- `tests/test_slot_manager.py`
- `tests/test_ws_api.py`
- `tests/test_commit_machine.py`
- `tests/test_config_flow.py`
- `tests/conftest.py` (shared fixtures)

### Phase 2 — Robust

| Layer | Approach |
|-------|----------|
| Keypad lockout | Unit tests: fire mock sensor state changes, verify keypad disable/enable on participating locks |
| Secure mode | Unit tests: encrypt/decrypt round trip; auth token lifecycle; constant-time compare verification |
| Audit trail | Unit tests: fire operations, assert correct audit events written |
| Diagnostics | Unit test: export diagnostics, assert no code values present |

### Phase 3 — Extensible

| Layer | Approach |
|-------|----------|
| LockBackend protocol | Unit tests with `MockLockBackend` covering all protocol methods |
| Temp codes | Unit tests: set expiry in past, call periodic check, assert slot deleted |
| HACS packaging | Manual: install via HACS custom repo on a test HA instance |

### General testing rules

- No test may call a real Z-Wave JS service; always use `MockLockBackend`.
- No test may write to the real `.storage` directory; use `tmp_path` fixture.
- Tests must pass with `pytest` and `pytest-homeassistant-custom-component` installed.
- CI (Phase 3): GitHub Actions runs `pytest` on every push to `main`.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Z-Wave JS `UserCode CC get` not supported on all locks | High | Medium | `supports_readback` flag in backend; skip verify step gracefully, log a warning |
| Z-Wave mesh delays cause false `FAILED` state | Medium | Medium | Configurable `PUSH_TIMEOUT_SECONDS`; retry logic; status shown to user so they can manually retry |
| Lock firmware differences in UserCode slot numbering (0-based vs 1-based) | Medium | High | Make slot offset configurable per lock in options flow; document in README |
| HA `.storage` write failure corrupts state | Low | High | Always write to a temp file then rename (atomic write); storage.py validates schema on load |
| Secure mode password forgotten | Medium | Medium | Provide a "reset secure mode" option in config flow that wipes encrypted data and lets user start fresh; document prominently |
| Frontend panel resource fails to load after HA update | Low | High | Pin frontend to a specific build; use standard LitElement patterns with no exotic dependencies |
| Z-Wave JS integration API changes between HA versions | Medium | High | Abstract all Z-Wave JS calls behind `ZWaveJSBackend`; version-check in `__init__.py` |
| Lockout trigger changes state unexpectedly (e.g., transient state change) | Low | Medium | Lockout only acts on state changes; use a stable entity (e.g., alarm panel) not noisy binary sensors; per-lock opt-out prevents accidental lockout |
| AES-GCM nonce reuse (IV collision in secure mode) | Very Low | Critical | Use `os.urandom(12)` for every encryption; never reuse nonce; document this in code |
| HACS custom repository blocked by HA authentication requirements | Low | Low | Follow HACS developer guide; ensure `hacs.json` and manifest are correct before first publish |

---

## Definition of Done

### Phase 1 — MVP

- [ ] Integration loads cleanly on HA 2024.1+ with no errors in logs
- [ ] Config flow completes and creates a config entry with at least one lock
- [ ] Slot count is determined dynamically from lock capabilities and stored in config entry
- [ ] `.storage/slotsentry` is created and persists across restart
- [ ] Sidebar panel renders slot grid with data loaded via WebSocket
- [ ] User can add, edit, and delete slot codes from the panel
- [ ] Saving a slot triggers a push to all configured locks
- [ ] Commit state machine reaches `SUCCESS` for a real Z-Wave lock within 30 seconds
- [ ] Failed push results in `FAILED` state on sensor entity
- [ ] `push_all` button in panel and in entity list works
- [ ] All Phase 1 unit tests pass with `pytest`
- [ ] No hardcoded magic strings (all in `const.py`)
- [ ] HA `check_config` passes

### Phase 2 — Robust

- [ ] All Phase 1 criteria still met
- [ ] Keypad lockout fires and auto-clears as configured (verified with simulated events)
- [ ] Secure mode: codes stored encrypted in `.storage`, panel requires password, codes masked in UI
- [ ] Audit log records all operations and persists across restart
- [ ] Diagnostics export contains no plaintext code values
- [ ] All Phase 2 unit tests pass

### Phase 3 — Extensible

- [ ] All Phase 2 criteria still met
- [ ] `LockBackend` is a formal Protocol with `MockLockBackend` available for tests
- [ ] `SchlageCloudBackend` implements `LockBackend` with `addressing_mode = "name"` and passes `MockLockBackend` test suite
- [ ] Temporary codes expire and are cleared from locks automatically
- [ ] Integration installable via HACS custom repository
- [ ] `README.md` describes setup process accurately with screenshots
- [ ] GitHub Actions release workflow produces a valid HACS-compatible zip

---

## Complexity Summary

| Task | Component | Complexity |
|------|-----------|-----------|
| 1.1 | Integration scaffold | S |
| 1.2 | Config flow | M |
| 1.3 | Storage layer | M |
| 1.4 | SlotManager | L |
| 1.5 | WebSocket API | M |
| 1.6 | Entity platform | S |
| 1.7 | Commit state machine | XL |
| 1.8 | Lock backend | M |
| 1.9 | Frontend panel | XL |
| 2.1 | Keypad lockout | M |
| 2.2 | Secure mode | L |
| 2.3 | Audit trail | M |
| 2.4 | Diagnostics | S |
| 3.1 | LockBackend protocol + SchlageCloudBackend | L |
| 3.2 | Temporary codes | L |
| 3.3 | HACS packaging | S |

**Total:** 2 XL, 4 L, 6 M, 4 S

---

*End of SlotSentry Project Plan v1.2*
