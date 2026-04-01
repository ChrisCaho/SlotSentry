# SlotSentry Product Specification

**Version:** 1.2.0-draft
**Date:** 2026-04-01
**Status:** Draft
**Author:** Chris Caho (architect), Claude Code (developer tool)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Overview & Goals](#2-product-overview--goals)
3. [Target Users](#3-target-users)
4. [System Requirements & Dependencies](#4-system-requirements--dependencies)
5. [Architecture Overview](#5-architecture-overview)
6. [Config Flow Specification](#6-config-flow-specification)
7. [Sidebar Panel UI Specification](#7-sidebar-panel-ui-specification)
8. [Data Model](#8-data-model)
9. [Commit State Machine](#9-commit-state-machine)
10. [Z-Wave Communication Layer](#10-z-wave-communication-layer)
11. [Secure Mode Specification](#11-secure-mode-specification)
12. [Keypad Lockout Feature](#12-keypad-lockout-feature)
13. [Audit Trail](#13-audit-trail)
14. [Entity Specifications](#14-entity-specifications)
15. [Error Handling & Recovery](#15-error-handling--recovery)
16. [Build Phases & Milestones](#16-build-phases--milestones)
17. [Future Enhancements](#17-future-enhancements)
18. [Glossary](#18-glossary)

---

## 1. Executive Summary

SlotSentry is a custom Home Assistant integration that provides centralized management of Z-Wave lock user codes through a dedicated sidebar panel. It replaces both Keymaster (bloated, performance issues) and Lock Code Manager (abandoned) with a minimal, reliable, and security-conscious alternative.

The integration manages user code slots across multiple Z-Wave locks, supports optional encryption of stored codes, provides a commit state machine that tracks synchronization between persistent storage and physical locks, and offers a keypad lockout feature driven by arbitrary Home Assistant entities.

SlotSentry is the single source of truth for all lock codes. Codes are stored in `.storage/slotsentry`, pushed to locks via Z-Wave JS services, and verified after each operation. The sidebar panel (Alarmo-style, not a Lovelace card) provides the management UI built with LitElement and communicating through a WebSocket API.

---

## 2. Product Overview & Goals

### 2.1 Problem Statement

Existing Z-Wave lock code management solutions for Home Assistant are inadequate:

- **Keymaster:** Bloated architecture, creates excessive entities, performance degradation with multiple locks, complex setup.
- **Lock Code Manager:** Abandoned by maintainer, no active development, unresolved bugs.

Neither solution provides a clean, dedicated UI panel with proper code synchronization tracking, secure storage, or a reliable commit state machine.

### 2.2 Goals

| Priority | Goal |
|----------|------|
| G1 | Single source of truth for all lock codes across all managed locks |
| G2 | Reliable commit state machine that tracks disk and per-lock sync status per slot per field |
| G3 | Sidebar panel UI that is intuitive, responsive, and does not require Lovelace configuration |
| G4 | Optional secure mode with password-based encryption for code storage |
| G5 | Generic keypad lockout driven by any HA entity, not coupled to alarm semantics |
| G6 | Minimal entity footprint (4 entities total, not per-slot) |
| G7 | Extensible backend protocol for future non-Z-Wave lock support |
| G8 | HACS-distributable as a custom repository |

### 2.3 Non-Goals

- SlotSentry does NOT manage lock/unlock operations (HA already does this).
- SlotSentry does NOT auto-discover codes already programmed on locks.
- SlotSentry does NOT provide scheduling or temporary code expiration in MVP.
- SlotSentry does NOT connect directly to the Z-Wave JS WebSocket server; it uses HA services exclusively.

---

## 3. Target Users

### 3.1 Primary User

Home Assistant administrators who manage one or more Z-Wave locks and need to:
- Assign, modify, and revoke user codes across multiple locks.
- Track whether codes have been successfully pushed to each lock.
- Optionally encrypt stored codes.
- Suppress keypads based on external conditions (alarm state, presence, time of day).

### 3.2 Assumed Technical Proficiency

- Comfortable with Home Assistant integration setup via the UI.
- Understands the concept of Z-Wave lock user code slots.
- Does not need to write YAML or automations to use SlotSentry.

---

## 4. System Requirements & Dependencies

### 4.1 Home Assistant

| Requirement | Minimum |
|-------------|---------|
| Home Assistant Core | 2024.1.0 or later |
| Python | 3.12+ (as bundled with HA) |
| Z-Wave JS integration | Installed and configured |
| Z-Wave JS Server | Running with at least one lock node |

### 4.2 Z-Wave Lock Compatibility

SlotSentry targets locks that support the Z-Wave `User Code` Command Class (CC 0x63). The initial target hardware:

| Lock | Entity ID | Model | Max Slots | Code Length | Code Readback |
|------|-----------|-------|-----------|-------------|---------------|
| Back Door | `lock.zwave_back_door_deadbolt` | Schlage BE469ZP | 30 | 6 digits (configurable 4-8) | Yes (actual codes) |
| Master Bedroom | `lock.zwave_master_bedroom_lock` | Schlage FE599 | 19 | 4 digits (fixed) | No (asterisks) |
| Utility Room | `lock.zwave_utility_room_lock` | Schlage FE599 | 19 | 4 digits (fixed) | No (asterisks) |
| Office | `lock.zwave_office_door_lock` | Schlage FE599 | 19 | 4 digits (fixed) | No (asterisks) |

**Note:** The slot count used by SlotSentry is not hardcoded. It is determined dynamically at integration setup time as the capacity of the lock with the smallest slot capacity across all selected locks. If only the BE469ZP is selected, 30 slots are available. If any FE599 is added, the working slot count drops to 19. This value is computed during lock selection and stored in the config entry.

### 4.3 Known Hardware Constraints

- **Schlage per-slot disable (status 0x02) does NOT work.** The User Code CC `Disabled` status is not honored by Schlage locks. SlotSentry must use `clear_lock_usercode` to disable a slot and `set_lock_usercode` to re-enable it.
- **BE469ZP** returns actual code digits on readback via `invoke_cc_api`. This enables verification.
- **FE599** returns asterisks (`****`) on readback. Verification relies on supervision results and Z-Wave JS acknowledgment, not code comparison.

### 4.4 Python Dependencies

No external Python packages beyond what Home Assistant Core provides. The integration uses:
- `homeassistant.helpers.storage` for persistent storage
- `homeassistant.components.websocket_api` for WebSocket commands
- `homeassistant.components.panel_custom` for sidebar panel registration
- `homeassistant.components.zwave_js` services for lock communication
- Standard library `hashlib`, `json`, `logging`, `asyncio`
- `cryptography` library (bundled with HA) for secure mode AES encryption

### 4.5 Frontend Dependencies

- LitElement (bundled with HA frontend)
- No additional JS dependencies

---

## 5. Architecture Overview

### 5.1 Component Diagram

```
+--------------------------------------------------+
|                  Home Assistant                   |
|                                                   |
|  +------------------+    +--------------------+   |
|  | SlotSentry       |    | Sidebar Panel      |   |
|  | Integration      |<-->| (LitElement)       |   |
|  |                  |    |                    |   |
|  | - Config Flow    | WS | - Slot Grid        |   |
|  | - Coordinator    |<-->| - Save/Discard     |   |
|  | - Entities       |    | - Secure Mode UI   |   |
|  | - WS API         |    +--------------------+   |
|  | - Lock Backend   |                             |
|  | - Commit Engine  |                             |
|  | - Keypad Lockout |                             |
|  +--------+---------+                             |
|           |                                       |
|  +--------v---------+    +--------------------+   |
|  | .storage/         |    | Z-Wave JS          |   |
|  | slotsentry        |    | Integration        |   |
|  | (persistent)      |    | (HA services)      |   |
|  +-------------------+    +--------+-----------+   |
|                                    |               |
+------------------------------------+---------------+
                                     |
                              +------v------+
                              | Z-Wave      |
                              | Locks       |
                              +-------------+
```

### 5.2 Module Structure

```
custom_components/slotsentry/
    __init__.py          # Integration setup, platform loading, panel registration
    config_flow.py       # Config flow and options flow (reconfigure)
    const.py             # Constants, domains, service names
    coordinator.py       # Data coordinator, dirty tracking
    commit_engine.py     # Commit state machine, disk + lock sync
    lock_backend.py      # LockBackend protocol + Z-Wave JS implementation
    keypad_lockout.py    # Keypad suppression logic
    storage.py           # Storage manager, encryption/decryption
    ws_api.py            # WebSocket command handlers
    sensor.py            # Push status sensor
    binary_sensor.py     # Suppressed binary sensor
    button.py            # Push All, Retry buttons
    audit.py             # Audit trail logging
    strings.json         # UI strings
    translations/
        en.json          # English translations
    manifest.json        # Integration manifest
    frontend/
        slotsentry-panel.js   # LitElement sidebar panel (built)
```

### 5.3 Data Flow Summary

1. **User edits slots** in sidebar panel.
2. **Panel sends** WebSocket command `slotsentry/save` with changed fields.
3. **WS API handler** passes changes to the Commit Engine.
4. **Commit Engine** writes to `.storage/slotsentry` (disk commit).
5. **Commit Engine** iterates locks, pushes changed codes via Lock Backend.
6. **Lock Backend** calls Z-Wave JS services, verifies results.
7. **Commit Engine** updates per-lock commit state arrays, persists.
8. **WS API** sends result back to panel.
9. **Panel** updates UI to reflect sync status.

---

## 6. Config Flow Specification

The config flow uses Home Assistant's standard `config_flow.py` pattern. SlotSentry supports a single config entry (not multi-instance).

### 6.1 Step 1: Lock Selection (`step_user`)

**Trigger:** User adds SlotSentry integration.

**UI Elements:**

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `locks` | Multi-select | List of discovered Z-Wave lock entities | At least one lock must be selected |

**Behavior:**
- Integration queries `homeassistant.components.zwave_js` to discover all lock entities.
- Only entities with the `lock` domain that are Z-Wave JS devices are shown.
- Each lock is displayed with its friendly name and entity ID.
- After the user submits their selection, the integration queries each selected lock to determine its maximum slot capacity. The working slot count is set to the capacity of the lock with the smallest slot capacity across all selected locks. This value is stored in the config entry and used to size commit arrays and the slot grid. For example: selecting only a BE469ZP (30 slots) yields 30 working slots; adding any FE599 (19 slots) drops the count to 19.

**Validation:**
- At least one lock must be selected.
- Selected entities must be valid Z-Wave lock entities at the time of submission.

### 6.2 Step 2: Code Length Configuration (`step_code_length`)

This step appears after lock selection. Before displaying the form, the integration attempts to discover code length capabilities from each selected lock by inspecting Z-Wave JS device attributes.

**Discovery Behavior:**

| Discovery Outcome | Default Values Used |
|-------------------|---------------------|
| All selected locks report the same discoverable code length | Defaults set to match discovered value; user informed of discovery |
| Locks report different discoverable code lengths | Dual-length mode suggested, defaults set to discovered values; user informed |
| Any lock's code length is undiscoverable | Defaults of 4 (short) and 6 (long) in dual-length mode, or 6 in single-length mode; user warned |

A notice at the top of this step informs the user what was found:
- "Discovered: Back Door supports 4-8 digits; Master Bedroom, Utility Room, Office support 4 digits only. Dual code length mode is suggested."
- Or: "Could not determine code length for one or more locks. Using default values. If you enter incorrect lengths, codes will be rejected by locks at push time. Verify the supported code length for each lock before continuing."

**UI Elements:**

| Field | Type | Default | Description | Validation |
|-------|------|---------|-------------|------------|
| `dual_code_length` | Checkbox | Discovered or `false` | Support two code lengths (long + short) | N/A |
| `code_length` | Integer | Discovered or 6 | Single code length (shown if `dual_code_length` is false) | Range 4-8 |
| `short_code_length` | Integer | Discovered or 4 | Short code length (shown if `dual_code_length` is true) | Range 4-7 |
| `long_code_length` | Integer | Discovered or 6 | Long code length (shown if `dual_code_length` is true) | Range 5-8 |

**Validation:**
- If `dual_code_length` is true: `short_code_length` < `long_code_length`.
- Each code length must be within its specified range.
- Code lengths must be compatible with selected locks. If a lock has a fixed code length (e.g., FE599 = 4 digits), a warning is displayed but setup is not blocked. The lock will reject codes of incompatible length at push time, and the commit engine will report the error.

### 6.3 Step 3: Optional Sensor & Lockout Configuration (`step_sensors`)

**UI Elements:**

| Field | Type | Default | Description | Validation |
|-------|------|---------|-------------|------------|
| `lockout_trigger_entity` | Entity selector | None | Entity whose state drives keypad lockout | Must be a valid entity_id if provided |
| `lockout_target_state` | String | `armed_home` | State value that triggers lockout | Non-empty if `lockout_trigger_entity` is set |
| `lock_lockout_participation` | Per-lock checkboxes | All checked | Which locks participate in keypad lockout | At least one if `lockout_trigger_entity` is set |

**Behavior:**
- The lockout trigger entity can be ANY Home Assistant entity (alarm panel, input_boolean, sensor, time helper, presence sensor, etc.).
- The `lockout_target_state` is compared as a string against the entity's state. For example: `"armed_home"` on an alarm panel, `"on"` on an input_boolean, or any other string value.
- When the lockout trigger reaches the target state, keypads on participating locks are disabled via `clear_lock_usercode`. When it leaves the target state, codes are restored via `set_lock_usercode`. SlotSentry does NOT issue any lock/unlock commands; keypad management is its only action.
- Per-lock participation checkboxes allow excluding specific locks from the lockout behavior.

### 6.4 Step 4: Secure Mode (`step_secure_mode`)

**UI Elements:**

| Field | Type | Default | Description | Validation |
|-------|------|---------|-------------|------------|
| `secure_mode` | Checkbox | `false` | Enable encrypted code storage | N/A |
| `password` | Password | N/A | Encryption password (shown if `secure_mode` is true) | 8-16 characters |
| `password_confirm` | Password | N/A | Password confirmation | Must match `password` |

**Behavior:**
- If `secure_mode` is checked, a warning is displayed: "Enabling secure mode encrypts all stored codes. If you lose your password, all codes must be re-entered. This cannot be undone without data loss."
- Password fields only appear when `secure_mode` is checked.
- Password is never stored in the config entry; it is used to derive an encryption key via PBKDF2 and then discarded. Only a verification hash is stored.

**Validation:**
- Password must be 8-16 characters.
- `password` and `password_confirm` must match.

### 6.5 Config Entry Creation

On successful completion of all steps, the config entry is created with:

```python
{
    "locks": ["lock.entity_1", "lock.entity_2", ...],
    "slot_count": int,                 # Determined at setup: capacity of the lock with the smallest slot capacity
    "dual_code_length": bool,
    "code_length": int | None,         # Set if dual_code_length is false
    "short_code_length": int | None,   # Set if dual_code_length is true
    "long_code_length": int | None,    # Set if dual_code_length is true
    "secure_mode": bool,
    "password_hash": str | None,       # PBKDF2 hash for verification, only if secure_mode
    "salt": str | None,                # Random salt for PBKDF2, only if secure_mode
    "lockout_trigger_entity": str | None,
    "lockout_target_state": str | None,
    "lock_lockout_participation": {
        "lock.entity_1": bool,
        "lock.entity_2": bool,
        ...
    }
}
```

### 6.6 Reconfigure Flow (`async_step_reconfigure`)

The reconfigure flow allows modifying all settings after initial setup. It re-uses the same steps as the initial config flow but pre-populates existing values.

**Additional Reconfigure Behavior:**

- **Adding a lock:** New lock is added with all slots in `out_of_sync` state. The slot count is recalculated: if the new lock has fewer slots than the current slot count, the slot count is reduced and any slots above the new limit are preserved in storage but marked `not_applicable` for that lock.
- **Removing a lock:** Lock is removed from config. Its commit array is deleted from storage. Codes on the physical lock are NOT cleared (user must do this manually or via a separate action). The slot count is recalculated and may increase if the removed lock was the limiting one.
- **Enabling secure mode (was off):** Follows step 4 flow. Existing plain-text codes are encrypted with the new password and re-saved.
- **Disabling secure mode (was on):** User must enter current password to decrypt. Warning displayed: "Disabling secure mode will store codes in plain text." On success, codes are decrypted and re-saved as plain text.
- **Failed password during disable:** After 5 consecutive failures, offer: "Reset secure mode? This will delete all stored codes and require re-entry." User must confirm.

---

## 7. Sidebar Panel UI Specification

### 7.1 Panel Registration

The panel is registered in `__init__.py` using `panel_custom`:

```python
await hass.components.panel_custom.async_register_panel(
    component_name="slotsentry-panel",
    sidebar_title="SlotSentry",
    sidebar_icon="mdi:lock-smart",
    frontend_url_path="slotsentry",
    config={},
    require_admin=True,
)
```

**Access:** Admin users only.

### 7.2 Panel Layout

```
+------------------------------------------------------------------+
| SlotSentry                                                [?]    |
+------------------------------------------------------------------+
| [Password: __________ ] [x] Reveal Codes    (secure mode only)   |
+------------------------------------------------------------------+
|                                                                   |
| +---+----+--------+----------------+----------------+-----------+ |
| | # | On | Label  | Long Code      | Short Code     | Status    | |
| +---+----+--------+----------------+----------------+-----------+ |
| | 1 | [x]| Admin  | ******         | ****           | [synced]  | |
| | 2 | [x]| Guest  | ******         | ****           | [synced]  | |
| | 3 | [ ]| (empty)| (empty)        | (empty)        | [synced]  | |
| | ...                                                            | |
| | N | [ ]| (empty)| (empty)        | (empty)        | [synced]  | |
| +---+----+--------+----------------+----------------+-----------+ |
|  (N = slot count determined at setup by lock with fewest slots)   |
|                                                                   |
|                    [ ] Update All Slots          [ Exit ]         |
+------------------------------------------------------------------+
```

**Note:** The slot count N shown in the grid is dynamic — it is determined during integration setup as the capacity of the lock with the smallest slot capacity across all selected locks. The grid has no hardcoded maximum.

### 7.3 Top Bar (Secure Mode Only)

Visible only when `secure_mode` is enabled in the config entry.

| Element | Type | Behavior |
|---------|------|----------|
| Password field | `<input type="password">` | Free-text input, no submit button |
| "Reveal Codes" checkbox | `<input type="checkbox">` | Disabled (grayed out) until password field contains 8+ characters |

**Authentication Flow:**
1. Panel opens. If secure mode is enabled, the slot grid is hidden. A message reads: "Enter your password to access slot data."
2. User types password. When 8+ characters are entered, the "Reveal Codes" checkbox becomes clickable.
3. User presses Enter or clicks a "Unlock" button. Password is validated via WebSocket command `slotsentry/authenticate`.
4. On success: slot grid appears, codes shown as asterisks (`******` / `****`).
5. On failure: error message "Incorrect password", password field cleared.
6. **Reveal Codes — checked before authenticating:** If the user checks "Reveal Codes" before submitting the password, codes are revealed immediately on successful password validation (no second prompt). The single authentication call serves both purposes.
7. **Reveal Codes — checked after already authenticated:** If the user is already viewing the grid (codes as asterisks) and then checks "Reveal Codes", a second password prompt appears. On success, codes are shown as plain digits. On failure, the checkbox unchecks and an error message appears.
8. If the user unchecks "Reveal Codes" at any time, codes revert to asterisks in the UI (no backend call needed).

**Open Mode (secure mode disabled):**
- Top bar is not rendered.
- Slot grid is immediately visible with codes shown as plain digits.

### 7.4 Slot Grid

#### 7.4.1 Columns

| Column | Width | Content | Editable |
|--------|-------|---------|----------|
| `#` | 40px | Slot number (1 through N, where N is the configured slot count) | No |
| `On` | 40px | Enable/disable checkbox | Yes |
| `Label` | 150px | Free-text label for the slot | Yes |
| `Long Code` | 120px | Code digits (or single "Code" column if `dual_code_length` is false) | Yes |
| `Short Code` | 120px | Code digits (hidden if `dual_code_length` is false) | Yes |
| `Status` | 80px | Sync status indicator | No |

#### 7.4.2 Column Behavior: `#` (Slot Number)

- Displays integer 1 through N, where N is the slot count determined at integration setup (the capacity of the lock with the smallest slot capacity).
- Static, non-interactive.
- Slot numbers are 1-indexed for display. Internal storage uses the same 1-based indexing to match Z-Wave slot numbers.

#### 7.4.3 Column Behavior: `On` (Enable/Disable)

- Checkbox. Checked = slot is enabled on all participating locks.
- Changing this checkbox marks the slot as dirty.
- **Disable action (uncheck):** On save, calls `clear_lock_usercode` for this slot on all locks. The code is retained in storage but removed from the lock.
- **Enable action (check):** On save, calls `set_lock_usercode` to push the stored code to all locks.
- If a slot has no code entered, the checkbox is disabled (grayed out) and cannot be checked.

#### 7.4.4 Column Behavior: `Label`

- Free-text input, max 32 characters.
- Allowed characters: alphanumeric, spaces, hyphens, apostrophes.
- Labels are for human reference only on Z-Wave (slot-based) locks; they are not sent to the lock hardware. On name-based backends (e.g., planned Schlage cloud), the label IS the code identifier sent to the lock. See section 10.8 for the `addressing_mode` protocol property.
- Changing a label marks the slot as dirty (disk-only for Z-Wave; labels do not affect Z-Wave lock commit state). For name-based backends, a label change would require a delete + re-add on the lock — this logic is gated on `backend.addressing_mode == "name"` and is deferred until a name-based backend is built.
- **Label uniqueness is enforced by the SlotManager:** labels must be unique across all non-empty slots (case-insensitive comparison). This prevents ambiguity on name-based backends (where the label is the delete key) and improves UX on all backends. Empty labels (unassigned slots) are exempt from the uniqueness check. The SlotManager's `async_set_slot()` rejects saves that would create a duplicate label.

#### 7.4.5 Column Behavior: `Long Code` / `Short Code` / `Code`

- Numeric input fields.
- If `dual_code_length` is false: single column titled "Code" with length = `code_length`.
- If `dual_code_length` is true: two columns with lengths `long_code_length` and `short_code_length`.
- Validation: digits only, exact length match for the configured code length.
- Empty field = no code for that slot/length.
- Changing a code marks the slot as dirty for both disk and lock commit arrays.

**Code display in secure mode (asterisks):**
- Saved codes are shown as asterisks (`******` or `****`) when secure mode is active and "Reveal Codes" is not checked.
- Clicking a code field that is currently showing asterisks clears the field. The user then types a new code in plain text. The new code remains visible until Save/commit, after which it is covered with asterisks.
- If the user clicks a masked field, then clicks away without entering a valid code (correct number of digits), the field reverts to asterisks representing the original stored code — no change is made.

**Code display in open mode:**
- Codes are always visible as plain digits.

**Which code goes to which lock:**
- Each lock in the config has a known code length capability. When pushing codes:
  - If the lock supports the long code length, the long code is pushed.
  - If the lock supports the short code length, the short code is pushed.
  - If `dual_code_length` is false, the single code is pushed to all locks.
- If a lock's fixed code length does not match any configured length, the slot is skipped for that lock and marked with a warning status.

#### 7.4.6 Column Behavior: `Status`

Visual sync status indicator per slot. This is the aggregate status across all locks.

| Icon/Color | Meaning |
|------------|---------|
| Green circle | `synced` — all locks confirmed |
| Yellow triangle | `out_of_sync` — changes pending push |
| Orange question mark | `uncertain` — push attempted but verification inconclusive |
| Red X | `error` — push failed on one or more locks |
| Gray dash | `empty` — no code in slot |

Hovering over the status icon shows a tooltip with per-lock breakdown:
```
Back Door: synced
Master Bedroom: out_of_sync
Utility Room: synced
Office: error - timeout
```

### 7.5 Action Buttons (Save / Discard / Exit)

The bottom action bar shows different buttons depending on the current state of the panel. There is never a button labeled "Save / Update" — these are always separate buttons.

| Panel State | Buttons Shown | Behavior |
|-------------|---------------|----------|
| Clean (no changes) | `Exit` | Closes the panel |
| Dirty (changes made, including "Update All Slots" checked) | `Discard` + `Save` | Discard reverts all changes and exits; Save commits and pushes |
| After successful commit | `Exit` | Returns to the exit-only state |
| Partial failure (some locks succeeded, some failed) | `Exit` (with warning badge) + `Save` | Exit closes with warning; Save retries only the failed locks |
| Escalated failure (communication problems detected, retry count exceeded) | `Exit` (only) | Save is removed or grayed out; user must exit and investigate |

**Dirty State Trigger:**
- Any edit to a slot field (label, code, enabled toggle) marks the panel dirty.
- Checking "Update All Slots" also marks the panel dirty (shows Save + Discard).

| Element | Type | Behavior |
|---------|------|----------|
| "Update All Slots" checkbox | Checkbox | Default unchecked. When checked, ALL slots (not just dirty ones) are pushed to all locks on next Save. Checking this counts as a dirty action. |
| `Save` button | Button | Commits changes. Shown only in dirty or partial-failure state. |
| `Discard` button | Button | Reverts all unsaved changes and exits. Shown only in dirty state. |
| `Exit` button | Button | Closes the panel. Always shown when not dirty, or alongside Save in partial-failure state. |

**Save Flow:**
1. User clicks `Save`.
2. Button shows spinner, becomes disabled.
3. Panel sends `slotsentry/save` WebSocket command with payload (see section 8).
4. Commit engine processes (see section 9).
5. On completion, panel receives result via WebSocket.
6. Grid updates status indicators.
7. If all locks succeeded: panel returns to Exit-only state.
8. If partial failure: `Exit` (with warning) + `Save` (retry) are shown.
9. If any slots were modified, a popup appears: "Changes saved. We recommend testing updated codes on each lock." with a "Don't show again" checkbox. The "Don't show again" preference is stored in browser `localStorage`.

### 7.6 Panel Open Behavior

When the sidebar panel is opened:

1. Panel sends `slotsentry/get_state` WebSocket command.
2. Backend returns full slot data and commit state.
3. If any slots have `out_of_sync` or `uncertain` status, the panel displays a banner: "Some slots are out of sync. Retrying..." and the backend automatically attempts to re-push those slots.
4. The status column updates in real-time as retries complete.
5. On initial open with no pending changes, only the `Exit` button is shown in the action bar.

### 7.7 Responsive Design

- Minimum width: 600px (typical sidebar panel width).
- On narrow viewports: code columns stack vertically within each row.
- Slot grid is scrollable vertically if it exceeds the viewport height.

---

## 8. Data Model

### 8.1 Storage File

**Path:** `.storage/slotsentry`

**Format:** JSON, managed by `homeassistant.helpers.storage.Store` with version migration support.

### 8.2 Top-Level Storage Schema

```typescript
interface SlotSentryStorage {
    version: 1;
    data: {
        slots: SlotData[];
        lock_commit_state: Record<string, LockCommitArray>;
        audit_log: AuditEntry[];
        preferences: UserPreferences;
    };
}
```

### 8.3 SlotData

Represents one user code slot. Array index 0 = slot 1. The total number of slots is determined at setup by the capacity of the lock with the smallest slot capacity.

```typescript
interface SlotData {
    slot_number: number;          // 1-N, matches Z-Wave slot number; N = configured slot_count
    enabled: boolean;             // Whether the slot is active on locks
    label: string;                // Human-readable label, max 32 chars
    long_code: string | null;     // Long code digits, or null if empty
    short_code: string | null;    // Short code digits, or null if empty
                                  // (If dual_code_length is false, long_code
                                  //  holds the single code, short_code is null)
    disk_commit: DiskCommitState;
    created_at: string;           // ISO 8601 timestamp
    modified_at: string;          // ISO 8601 timestamp
}
```

**Encrypted storage:** When secure mode is enabled, the `long_code` and `short_code` fields are stored as AES-256-GCM encrypted base64 strings. All other fields remain in plain text.

### 8.4 DiskCommitState

Tracks whether the in-memory state matches what is persisted to disk.

```typescript
interface DiskCommitState {
    status: "synced" | "dirty";
    last_saved: string | null;    // ISO 8601 timestamp of last successful save
}
```

### 8.5 LockCommitArray

Per-lock synchronization state. Keyed by lock entity_id.

```typescript
interface LockCommitArray {
    entity_id: string;            // e.g., "lock.zwave_back_door_deadbolt"
    slots: LockSlotCommit[];      // Array index 0 = slot 1
}

interface LockSlotCommit {
    slot_number: number;          // 1-N (matches configured slot_count)
    code_status: CommitStatus;    // Sync state for the code field
    enabled_status: CommitStatus; // Sync state for the enabled field
    last_pushed: string | null;   // ISO 8601 timestamp
    last_verified: string | null; // ISO 8601 timestamp
    error_message: string | null; // Last error, null if none
    retry_count: number;          // Consecutive failures
    last_pushed_label: string | null;  // Label used in last successful push (for name-based backends)
}

// Implementation note: LockSlotCommit MUST be implemented as a Python dataclass
// (not a bare dict) to support clean schema migrations. The last_pushed_label
// field is null for Z-Wave (slot-based) locks in Phase 1 but is reserved for
// Schlage cloud (name-based) backends: when slot.label != lock_commit.last_pushed_label
// AND backend.addressing_mode == "name", the slot is marked out_of_sync for that lock
// even if the code has not changed (rename requires delete + re-add on cloud locks).
// This field is populated but not used in the rename-detection logic until a
// name-based backend is built.

type CommitStatus = "synced" | "out_of_sync" | "uncertain" | "error" | "not_applicable";
```

- `synced`: Lock confirmed to have the correct code/state.
- `out_of_sync`: Storage has changed since last successful push.
- `uncertain`: Push was sent but verification was inconclusive (e.g., FE599 asterisk readback after a timeout).
- `error`: Push failed with a definitive error.
- `not_applicable`: Lock does not support the code length for this slot.

### 8.6 AuditEntry

```typescript
interface AuditEntry {
    timestamp: string;            // ISO 8601
    event_type: AuditEventType;
    slot_number: number | null;   // null for non-slot events
    lock_entity_id: string | null;
    details: string;              // Human-readable description, NEVER contains codes
}

type AuditEventType =
    | "code_changed"       // Code was modified (details say "Slot 3 code updated", NOT the code)
    | "label_changed"      // Label was modified (details include old and new label)
    | "slot_enabled"       // Slot enabled
    | "slot_disabled"      // Slot disabled
    | "push_success"       // Code pushed to lock successfully
    | "push_failure"       // Code push failed
    | "push_retry"         // Retry attempted
    | "keypad_lockout"     // Keypad suppressed
    | "keypad_restore"     // Keypad restored
    | "secure_mode_on"     // Secure mode enabled
    | "secure_mode_off"    // Secure mode disabled
    | "panel_opened"       // Panel accessed
    | "panel_authenticated"; // Secure mode authentication
```

### 8.7 UserPreferences

```typescript
interface UserPreferences {
    suppress_test_reminder: boolean;  // "Don't show again" for post-save popup
}
```

Note: `suppress_test_reminder` is stored server-side here but the primary "Don't show again" is in browser `localStorage`. This server-side field is a fallback/default.

### 8.8 WebSocket API Payloads

#### `slotsentry/get_state` (request)

```typescript
interface GetStateRequest {
    type: "slotsentry/get_state";
}
```

#### `slotsentry/get_state` (response)

```typescript
interface GetStateResponse {
    slots: SlotDataForUI[];
    lock_commit_state: Record<string, LockCommitArray>;
    config: {
        secure_mode: boolean;
        dual_code_length: boolean;
        code_length: number | null;
        short_code_length: number | null;
        long_code_length: number | null;
        locks: string[];
    };
    authenticated: boolean;       // Whether password has been validated this session
}

interface SlotDataForUI {
    slot_number: number;
    enabled: boolean;
    label: string;
    long_code: string | null;     // Actual digits, asterisks, or null depending on auth state
    short_code: string | null;
    aggregate_status: CommitStatus;
    per_lock_status: Record<string, CommitStatus>;
}
```

#### `slotsentry/save` (request)

```typescript
interface SaveRequest {
    type: "slotsentry/save";
    changes: SlotChange[];
    update_all: boolean;          // "Update All Slots" checkbox
}

interface SlotChange {
    slot_number: number;
    enabled?: boolean;
    label?: string;
    long_code?: string | null;
    short_code?: string | null;
}
```

Only dirty fields are included in `changes`. If `update_all` is true, all slots are pushed regardless of dirty state.

#### `slotsentry/save` (response)

```typescript
interface SaveResponse {
    success: boolean;
    results: SlotResult[];
    message: string;
}

interface SlotResult {
    slot_number: number;
    disk_saved: boolean;
    lock_results: Record<string, LockPushResult>;
}

interface LockPushResult {
    entity_id: string;
    success: boolean;
    status: CommitStatus;
    error: string | null;
}
```

#### `slotsentry/authenticate` (request/response)

```typescript
interface AuthenticateRequest {
    type: "slotsentry/authenticate";
    password: string;
}

interface AuthenticateResponse {
    success: boolean;
    error: string | null;
}
```

#### `slotsentry/slot_toggle` (request)

For immediate enable/disable without full save:

```typescript
interface SlotToggleRequest {
    type: "slotsentry/slot_toggle";
    slot_number: number;
    enabled: boolean;
}
```

---

## 9. Commit State Machine

### 9.1 Overview

The commit state machine ensures that code changes are reliably persisted to disk and then pushed to each lock individually. It provides granular tracking at the per-slot, per-field, per-lock level.

### 9.2 State Definitions

| State | Meaning | Stored In |
|-------|---------|-----------|
| `synced` | Data on disk/lock matches the authoritative state | `LockSlotCommit` |
| `out_of_sync` | Authoritative state has changed; push pending | `LockSlotCommit` |
| `uncertain` | Push was attempted but verification was inconclusive | `LockSlotCommit` |
| `error` | Push definitively failed | `LockSlotCommit` |
| `not_applicable` | Lock cannot accept this code (length mismatch) | `LockSlotCommit` |

### 9.3 State Transition Diagram

```
                    User edits slot
                         |
                         v
                   +-------------+
                   | out_of_sync |<------ Retry after error
                   +------+------+
                          |
                    Save clicked
                          |
                   +------v------+
                   | Disk Commit |
                   +------+------+
                          |
                   Success? ──No──> Disk error (retry)
                          |
                         Yes
                          |
                   +------v------+
                   | Push to     |
                   | Lock N      |
                   +------+------+
                          |
              +-----------+-----------+
              |           |           |
           Success    Timeout    Failure
              |           |           |
              v           v           v
          +--------+ +-----------+ +-------+
          | Verify | | uncertain | | error |
          +---+----+ +-----------+ +-------+
              |
        +-----+-----+
        |           |
     Verified   Inconclusive
        |           |
        v           v
   +--------+ +-----------+
   | synced | | uncertain |
   +--------+ +-----------+
```

### 9.4 Commit Sequence (Detailed)

**Phase 1: Disk Commit**

1. Receive `SaveRequest` with changed slots.
2. For each changed slot:
   a. Update `SlotData` in memory.
   b. Set `disk_commit.status = "dirty"`.
3. Call `Store.async_save()` to persist to `.storage/slotsentry`.
4. On success: set `disk_commit.status = "synced"`, update `disk_commit.last_saved`.
5. On failure: return error to panel, do not proceed to lock push.

**Phase 2: Lock Commit**

6. For each changed slot, for each lock:
   a. Set `LockSlotCommit.code_status = "out_of_sync"` (if code changed).
   b. Set `LockSlotCommit.enabled_status = "out_of_sync"` (if enabled changed).
   c. Persist updated commit arrays to storage.
7. Iterate through locks sequentially (not in parallel, to avoid Z-Wave congestion):
   a. For each lock, iterate through dirty slots:
      - If code changed and slot is enabled: call `set_lock_usercode`.
      - If slot was disabled: call `clear_lock_usercode`.
      - If slot was enabled (re-enabled): call `set_lock_usercode`.
   b. Wait for response (max 60 seconds per operation).
   c. On success response:
      - Call verification (readback) if supported.
      - If verified or supervision confirmed: set status = `synced`.
      - If readback returns asterisks (FE599): set status = `synced` (trust supervision result).
      - If readback returns wrong code: set status = `error`, record message.
   d. On timeout: set status = `uncertain`.
   e. On failure: set status = `error`, record error message.
   f. Persist commit arrays after each lock completes.

**Phase 3: Result Reporting**

8. Compile results for all slots and locks.
9. Return `SaveResponse` to panel.
10. Update `sensor.slotsentry_push_status` entity.

### 9.5 Auto-Retry on Panel Open

When the panel is opened and `slotsentry/get_state` is called:

1. Backend scans all `LockSlotCommit` entries.
2. Any slot with `out_of_sync` or `uncertain` status is queued for retry.
3. Retries execute in the background.
4. Panel receives real-time updates via WebSocket subscription (`slotsentry/subscribe`).

### 9.6 Dirty Tracking

The coordinator maintains an in-memory dirty set:

```python
dirty_slots: dict[int, set[str]]  # slot_number -> set of dirty field names
# Field names: "long_code", "short_code", "label", "enabled"
```

Only dirty fields are included in save operations. The dirty set is cleared after successful disk commit. Lock commit arrays independently track their own sync state.

---

## 10. Z-Wave Communication Layer

### 10.1 Services Used

SlotSentry communicates with Z-Wave locks exclusively through Home Assistant services provided by the Z-Wave JS integration.

| Service | Purpose | Parameters |
|---------|---------|------------|
| `zwave_js.set_lock_usercode` | Set or update a user code on a slot | `entity_id`, `code_slot`, `usercode` |
| `zwave_js.clear_lock_usercode` | Remove a user code from a slot | `entity_id`, `code_slot` |
| `zwave_js.invoke_cc_api` | Read back user codes for verification | `entity_id`, `command_class`, `method_name`, `parameters` |

### 10.2 Setting a User Code

```python
await hass.services.async_call(
    "zwave_js",
    "set_lock_usercode",
    {
        "entity_id": lock_entity_id,
        "code_slot": slot_number,      # 1-based
        "usercode": code_string,        # e.g., "123456"
    },
    blocking=True,
)
```

**Timeout:** 60 seconds (enforced by `asyncio.wait_for`).

### 10.3 Clearing a User Code

```python
await hass.services.async_call(
    "zwave_js",
    "clear_lock_usercode",
    {
        "entity_id": lock_entity_id,
        "code_slot": slot_number,
    },
    blocking=True,
)
```

### 10.4 Verification (Readback)

```python
result = await hass.services.async_call(
    "zwave_js",
    "invoke_cc_api",
    {
        "entity_id": lock_entity_id,
        "command_class": 99,            # User Code CC
        "method_name": "get",
        "parameters": [slot_number],
    },
    blocking=True,
    return_response=True,
)
```

**Interpreting Results:**

| Lock Model | Readback Value | Interpretation |
|------------|----------------|----------------|
| BE469ZP | Actual digits (e.g., `"123456"`) | Compare with stored code. Match = `synced`, mismatch = `error`. |
| FE599 | Asterisks (e.g., `"****"`) | Cannot verify code content. Trust supervision result. |
| Any | Empty / status 0x00 | Slot is empty/available. Expected after `clear_lock_usercode`. |

### 10.5 Verification After Clear

After clearing a slot, readback should return an empty slot status. If the slot still shows occupied, mark as `uncertain`.

### 10.6 Lock Operation Sequencing

- Operations to a single lock are sequential (one slot at a time).
- Operations across different locks are also sequential to avoid Z-Wave mesh congestion.
- A 500ms delay is inserted between consecutive operations to the same lock.
- A 1000ms delay is inserted between switching to a different lock.

### 10.7 Supervision Results

Z-Wave JS returns supervision results that indicate whether the receiving node acknowledged the command. These are used as a primary verification signal for locks that do not support code readback (FE599).

| Supervision Status | Interpretation |
|-------------------|----------------|
| `Success` | Command acknowledged by lock. Mark `synced`. |
| `Fail` | Lock rejected command. Mark `error`. |
| `Working` | Lock is processing. Wait and re-check. |
| `No Supervision` | Lock does not support supervision. Attempt readback. |

### 10.8 LockBackend Protocol

`lock_backend.py` defines both the `SlotInfo` dataclass and the `LockBackend` protocol. The protocol is formally defined beginning in Phase 1 (not deferred to Phase 3) so that the Z-Wave backend is built against it from the start. This makes adding future backends a matter of implementing the same interface without changing the commit engine.

The **shim/adapter pattern** applies throughout: the `SlotManager` (commit engine) always calls the same `LockBackend` interface regardless of lock type. Each backend shim translates those calls to the appropriate lock-specific API.

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class SlotInfo:
    """Context passed to LockBackend methods for each slot operation.

    Both fields are always provided. The backend uses whichever is
    appropriate for its addressing mode.

    slot_number: Physical slot on the lock (Z-Wave) or internal array
                 index (cloud). 1-based, matches the SlotSentry slot grid.
    label:       Human name for this slot. Used as the code identifier on
                 name-based backends (e.g., Schlage cloud). Purely cosmetic
                 on slot-based backends (e.g., Z-Wave).
    """
    slot_number: int
    label: str


class LockBackend(Protocol):
    """Protocol that all lock backend implementations must satisfy.

    The commit engine (SlotManager) calls these methods. Each backend
    shim translates them to the appropriate lock-specific API:

    - ZWaveJSBackend: uses slot_info.slot_number for all operations.
      Ignores slot_info.label entirely (Z-Wave addresses by slot number).
    - SchlageCloudBackend (planned, Phase 2/3): uses slot_info.label as
      the code identifier. slot_info.slot_number is the internal array
      index only and is not sent to the lock.

    Adding new backends does not require changes to the commit engine.
    """

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        """Push a code to the lock for the given slot.

        Returns True on success. The commit engine marks the slot as
        synced (pending verification) on True, error on False.
        """
        ...

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        """Clear/delete the code for the given slot from the lock.

        Returns True on success.
        """
        ...

    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None:
        """Read back the code for the given slot, if supported.

        Returns the code string if readable, None if the slot is empty
        or if readback is not supported by this backend.
        """
        ...

    async def async_get_all_usercodes(self) -> dict[int, str] | None:
        """Read all codes from the lock in a single call, if supported.

        Returns a dict of {slot_number: code_string} on success, or None
        if bulk readback is not supported (the commit engine falls back to
        per-slot async_get_usercode calls).

        Z-Wave backend returns None (Z-Wave does not support efficient bulk
        reads). Schlage cloud backend (planned) calls get_access_codes() once
        and returns all codes, mapping names back to slot numbers via label
        matching. This avoids N individual API calls during verification.
        """
        ...

    @property
    def supports_readback(self) -> bool:
        """True if async_get_usercode can return actual code digits.

        False means the backend cannot verify what is stored on the lock
        (e.g., FE599 returns asterisks). The commit engine falls back to
        trusting supervision results when this is False.
        """
        ...

    @property
    def addressing_mode(self) -> str:
        """How this lock identifies codes: 'slot' or 'name'.

        'slot': codes are addressed by physical slot number (Z-Wave).
                Label changes are disk-only; the lock is not contacted.
        'name': codes are addressed by label/name (Schlage cloud).
                Label changes require a delete + re-add on the lock and
                must dirty the lock commit state even if the code is unchanged.

        The commit engine uses this property to decide whether a label
        change should mark a lock's slot as out_of_sync.
        """
        ...

    @property
    def supported_code_lengths(self) -> tuple[int, int]:
        """Supported code length range as (min_length, max_length).

        Used by the commit engine to pre-validate codes before attempting
        a push, enabling clear error messages ("Code length 4 is not
        supported by this lock") rather than cryptic Z-Wave errors.

        Z-Wave backend: returns the range discovered from lock capabilities
                        (e.g., (4, 4) for FE599, (4, 8) for BE469ZP).
        Schlage cloud backend (planned): returns (4, 8).
        """
        ...
```

**ZWaveJSBackend — Phase 1 implementation summary:**

| Property / Method | Z-Wave behavior |
|-------------------|-----------------|
| `async_set_usercode` | Calls `zwave_js.set_lock_usercode` with `code_slot=slot_info.slot_number`. Ignores `slot_info.label`. |
| `async_clear_usercode` | Calls `zwave_js.clear_lock_usercode` with `code_slot=slot_info.slot_number`. |
| `async_get_usercode` | Calls `invoke_cc_api` User Code CC `get` with `slot_info.slot_number`. Returns digits or `None`. |
| `async_get_all_usercodes` | Returns `None` (per-slot query only). |
| `supports_readback` | `True` for BE469ZP; `False` for FE599. |
| `addressing_mode` | Returns `"slot"`. |
| `supported_code_lengths` | Returns the discovered range, e.g. `(4, 4)` for FE599 or `(4, 8)` for BE469ZP. |

**Schlage cloud — planned future backend (Phase 2/3):**

Schlage cloud (`lock.schlage_front_door_deadbolt` on this HA instance) is a concrete planned future backend. The protocol additions above future-proof the design for it without requiring any changes to the commit engine when the backend is built. See SCHLAGE_CLOUD_RESEARCH.md and BACKEND_REVIEW.md for full API details. Key differences:

| Property / Method | Schlage cloud behavior |
|-------------------|------------------------|
| `async_set_usercode` | Calls `schlage.add_code` with `name=slot_info.label, code=code`. |
| `async_clear_usercode` | Calls `schlage.delete_code` with `name=slot_info.label`. |
| `async_get_usercode` | Falls back from bulk read; not called per-slot if bulk succeeds. |
| `async_get_all_usercodes` | Calls `schlage.get_codes`, maps names to slot numbers via label matching. |
| `supports_readback` | `True` (cloud returns actual code digits). |
| `addressing_mode` | Returns `"name"`. |
| `supported_code_lengths` | Returns `(4, 8)`. |

---

## 11. Secure Mode Specification

### 11.1 Overview

Secure mode provides at-rest encryption for user codes stored in `.storage/slotsentry`. It is optional and configured at the integration level, not in the sidebar panel.

### 11.2 Encryption Details

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-256-GCM |
| Key Derivation | PBKDF2-HMAC-SHA256, 600,000 iterations |
| Salt | 32 bytes, randomly generated at setup, stored in config entry |
| IV/Nonce | 12 bytes, randomly generated per encryption operation |
| Encrypted Fields | `long_code` and `short_code` in `SlotData` only |
| Unencrypted Fields | `slot_number`, `enabled`, `label`, all commit state, audit log |

### 11.3 Password Handling

- The password is NEVER stored anywhere persistently.
- At setup: password is used to derive the encryption key and a verification hash. The verification hash (PBKDF2 with a different salt) is stored in the config entry. The encryption key is held in memory only while the integration is loaded.
- On HA restart: the encryption key is NOT in memory. The panel requires password entry to unlock.
- On panel open: password is sent via `slotsentry/authenticate`. Backend derives the key, checks the verification hash, and if correct, holds the key in memory for the session.

### 11.4 Session Management

- An authenticated session lasts until the panel is closed or the browser tab is closed.
- There is no idle timeout (the user explicitly closes the panel).
- The backend tracks authentication state per WebSocket connection.

### 11.5 Reveal Codes Flow

**Case 1: "Reveal Codes" checked before initial authentication**
1. User checks "Reveal Codes" before submitting their password.
2. User submits password via the "Unlock" button.
3. A single `slotsentry/authenticate` call validates the password and signals reveal intent.
4. On success: slot grid appears with codes shown as plain digits (not asterisks).
5. No second password prompt is needed.

**Case 2: "Reveal Codes" checked after already authenticated**
1. User is authenticated; slot grid is visible with codes as asterisks.
2. User checks "Reveal Codes" checkbox.
3. Panel prompts for password again (second authentication challenge).
4. Panel sends `slotsentry/authenticate` with the entered password.
5. Backend re-validates. On success, the next `slotsentry/get_state` response includes plain-text codes.
6. On failure: checkbox unchecks, error message appears.

**Unreveal:**
- If the user unchecks "Reveal Codes" at any time, codes revert to asterisks in the UI (no backend call needed).

### 11.6 Password Recovery (Failure Escalation)

| Consecutive Failures | Action |
|---------------------|--------|
| 1-4 | Display "Incorrect password" error |
| 5 | Display warning: "Too many failed attempts. You can reset secure mode, but this will delete all stored codes." |
| 5+ | Offer "Reset Secure Mode" button. Clicking it requires typing "RESET" to confirm. This clears all `SlotData` codes (sets to null), disables secure mode, and clears all lock commit arrays to `out_of_sync`. |

---

## 12. Keypad Lockout Feature

### 12.1 Overview

Keypad lockout is a mechanism to suppress (disable) the keypad on participating locks when a lockout trigger entity enters a target state. This is intentionally generic: the lockout trigger can be an alarm panel, a presence sensor, a time-of-day helper, or any other entity. For example: disable keypads when you are home and the alarm is armed, at night, or under any other condition.

**Important:** SlotSentry only manages keypad enable/disable. It does NOT issue lock or unlock commands under any circumstances. The keypad lockout feature disables entry via keypad only — it does not physically lock the door.

### 12.2 Configuration

Configured during integration setup or reconfigure (see section 6.3).

| Setting | Description |
|---------|-------------|
| `lockout_trigger_entity` | Entity ID of the lockout trigger |
| `lockout_target_state` | String state value that triggers lockout (e.g., `"armed_home"`, `"on"`, `"true"`) |
| `lock_lockout_participation` | Per-lock boolean map of which locks participate |

### 12.3 Lockout Trigger Flow

1. `lockout_trigger_entity` state changes to `lockout_target_state`.
2. For each participating lock:
   a. **Disable all enabled slots** by calling `clear_lock_usercode` for each enabled slot.
   b. Update `binary_sensor.slotsentry_suppressed` to `on`.
3. Audit log entry: `keypad_lockout` for each lock.

SlotSentry does NOT call `lock.lock` or any other lock/unlock service. Keypad suppression only prevents code entry — it does not physically secure the door.

### 12.4 Lockout Restore Flow

1. `lockout_trigger_entity` state changes to any value OTHER than `lockout_target_state`.
2. For each participating lock:
   a. **Re-enable all previously enabled slots** by calling `set_lock_usercode` with stored codes.
   b. Verify each slot after re-push.
3. Update `binary_sensor.slotsentry_suppressed` to `off`.
4. Audit log entry: `keypad_restore` for each lock.

### 12.5 Edge Cases

| Scenario | Behavior |
|----------|----------|
| HA restarts while in lockout state | On startup, check `lockout_trigger_entity` state. If still in target state, ensure keypads remain suppressed. If not, restore codes. |
| Lockout trigger becomes unavailable | Do NOT change lockout state. Log a warning. Keep current state. |
| Lock unresponsive during lockout | Log error, mark as `uncertain`. Retry on next state change. |
| User saves codes while in lockout | Codes are saved to storage but NOT pushed to locks that are in lockout. Mark as `out_of_sync`. Push when lockout is lifted. |

### 12.6 Suppression Tracking

The integration maintains an in-memory set of suppressed locks:

```python
suppressed_locks: set[str]  # Set of entity_ids currently in lockout
```

This set is also persisted to storage so it survives HA restarts.

---

## 13. Audit Trail

### 13.1 Overview

SlotSentry maintains an audit trail of significant events. The trail serves two purposes: local storage history and optional HA logbook integration.

### 13.2 Storage

Audit entries are stored in `.storage/slotsentry` under the `audit_log` array (see section 8.6).

**Rolling Window:** Maximum 1000 entries. When the limit is reached, the oldest entries are removed (FIFO).

### 13.3 Events Logged

| Event Type | Trigger | Details Content |
|------------|---------|-----------------|
| `code_changed` | Code field modified and saved | "Slot {N} code updated" (NEVER includes the code) |
| `label_changed` | Label field modified and saved | "Slot {N} label changed from '{old}' to '{new}'" |
| `slot_enabled` | Slot enabled | "Slot {N} enabled" |
| `slot_disabled` | Slot disabled | "Slot {N} disabled" |
| `push_success` | Code pushed to lock | "Slot {N} pushed to {lock_name}" |
| `push_failure` | Code push failed | "Slot {N} push to {lock_name} failed: {error}" |
| `push_retry` | Retry attempted | "Slot {N} retry #{count} to {lock_name}" |
| `keypad_lockout` | Keypad suppressed on lock | "Keypad lockout on {lock_name}" |
| `keypad_restore` | Keypad restored on lock | "Keypad restored on {lock_name}" |
| `secure_mode_on` | Secure mode enabled | "Secure mode enabled" |
| `secure_mode_off` | Secure mode disabled | "Secure mode disabled" |
| `panel_opened` | Panel accessed | "Panel opened by {user}" |
| `panel_authenticated` | Password validated | "Panel authenticated by {user}" |

### 13.4 HA Logbook Integration

Optionally, audit events are also fired as HA events (`slotsentry_audit`) which appear in the HA logbook. The event data matches `AuditEntry` but NEVER includes code values.

```python
hass.bus.async_fire("slotsentry_audit", {
    "event_type": "push_success",
    "slot_number": 3,
    "lock_entity_id": "lock.zwave_back_door_deadbolt",
    "details": "Slot 3 pushed to Back Door",
})
```

### 13.5 Code Security in Logs

**Absolute rule:** No user code value (digits) may EVER appear in:
- Audit trail entries
- HA logbook events
- Python log messages (`_LOGGER.*`)
- WebSocket error responses
- Any other output

Labels are permitted in logs. Slot numbers are permitted. Codes are NEVER logged.

---

## 14. Entity Specifications

SlotSentry creates exactly 4 entities. These are integration-level entities, not per-lock or per-slot.

### 14.1 `sensor.slotsentry_push_status`

| Property | Value |
|----------|-------|
| Domain | `sensor` |
| Entity ID | `sensor.slotsentry_push_status` |
| Name | "SlotSentry Push Status" |
| Icon | `mdi:lock-check` (synced), `mdi:lock-alert` (other) |
| Device Class | None |
| State Class | None |

**State Values:**

| State | Meaning |
|-------|---------|
| `idle` | No operations in progress, all slots synced |
| `pushing` | Currently pushing codes to locks |
| `synced` | All slots on all locks are confirmed synced |
| `partial` | Some slots synced, some out_of_sync or uncertain |
| `error` | One or more slots have errors |

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_slots` | int | Number of slots with codes |
| `synced_count` | int | Slots fully synced across all locks |
| `out_of_sync_count` | int | Slots pending push |
| `uncertain_count` | int | Slots with inconclusive verification |
| `error_count` | int | Slots with push errors |
| `last_push` | str | ISO 8601 timestamp of last push operation |

### 14.2 `binary_sensor.slotsentry_suppressed`

| Property | Value |
|----------|-------|
| Domain | `binary_sensor` |
| Entity ID | `binary_sensor.slotsentry_suppressed` |
| Name | "SlotSentry Keypad Suppressed" |
| Icon | `mdi:lock-off` (on), `mdi:lock-open` (off) |
| Device Class | None |

**State Values:**

| State | Meaning |
|-------|---------|
| `on` | Keypad lockout is active on one or more locks |
| `off` | All keypads are operational |

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `suppressed_locks` | list[str] | Entity IDs of currently suppressed locks |
| `lockout_trigger_entity` | str | Entity ID of the lockout trigger |
| `lockout_target_state` | str | State value that triggers lockout |

### 14.3 `button.slotsentry_push_all`

| Property | Value |
|----------|-------|
| Domain | `button` |
| Entity ID | `button.slotsentry_push_all` |
| Name | "SlotSentry Push All" |
| Icon | `mdi:upload-multiple` |

**Behavior:** Pressing this button triggers a full push of all enabled slots to all locks, equivalent to checking "Update All Slots" and clicking "Save" in the panel.

### 14.4 `button.slotsentry_retry`

| Property | Value |
|----------|-------|
| Domain | `button` |
| Entity ID | `button.slotsentry_retry` |
| Name | "SlotSentry Retry" |
| Icon | `mdi:refresh` |

**Behavior:** Pressing this button retries all slots that are in `out_of_sync`, `uncertain`, or `error` state. Equivalent to the auto-retry that occurs on panel open.

---

## 15. Error Handling & Recovery

### 15.1 Error Categories

| Category | Examples | Severity |
|----------|----------|----------|
| Disk I/O | Storage write failure, filesystem full | Critical |
| Z-Wave Communication | Timeout, node unreachable, command rejected | High |
| Validation | Invalid code length, empty code on enable | Medium |
| Authentication | Wrong password, session expired | Low |

### 15.2 Retry Escalation (Z-Wave Failures)

The retry escalation applies per lock, per slot, per operation:

| Failure Count | Action | UI Indicator |
|---------------|--------|--------------|
| 1 | Automatic retry after 5 seconds | Yellow triangle, "Retrying..." |
| 2 | Second retry after 15 seconds | Yellow triangle, "Retry 2/3..." |
| 3 | Stop retrying. Suggest user click "Save" again. | Orange, "Re-save recommended" |
| 4 (after manual re-save) | Retry as above | Same escalation |
| 7 (cumulative) | Gray out Save button. Display: "Communication problems detected. Please close and reopen the panel." | Red, Save button disabled |
| 10 (cumulative) | Offer "Wipe Lock / Update All" option. This clears all slots on the lock, then re-pushes all enabled slots from scratch. | Red, with "Nuclear" option |
| 13+ (cumulative) | Direct user to reconfigure the integration and verify Z-Wave connectivity. | Red, permanent error |

**Retry counter reset:** Successfully pushing ANY slot to a lock resets that lock's cumulative failure counter to 0.

### 15.3 Disk I/O Failure

If `.storage/slotsentry` cannot be written:

1. Return error to panel: "Failed to save to disk. Changes are in memory only."
2. Do NOT proceed with lock push (codes must be persisted before pushing).
3. Retry disk save on next "Save" click.
4. If disk save fails 3 consecutive times, log a critical error and suggest checking filesystem health.

### 15.4 Z-Wave Integration Unavailable

If the Z-Wave JS integration is not loaded or the lock entity is unavailable:

1. Disk save proceeds normally.
2. Lock push is skipped for unavailable locks.
3. Lock commit arrays are marked `out_of_sync`.
4. Status sensor shows `partial` or `error`.
5. When the Z-Wave integration becomes available, the next panel open or button press triggers retry.

### 15.5 Partial Push Failure

If some locks succeed and others fail within a single save operation:

1. Successful locks are marked `synced`.
2. Failed locks retain their error/uncertain state.
3. The operation continues to the next lock (does NOT abort on first failure).
4. The `SaveResponse` includes per-lock results so the panel can show granular status.

### 15.6 Startup Recovery

On HA startup / integration load:

1. Load `.storage/slotsentry`.
2. If secure mode is enabled, encrypted fields remain encrypted in memory until password is provided.
3. Scan lock commit arrays for non-`synced` states.
4. Do NOT auto-retry on startup (wait for panel open or button press).
5. Set entity states based on stored commit arrays.
6. If `lockout_trigger_entity` is configured, check its current state and ensure lockout/restore is consistent.

---

## 16. Build Phases & Milestones

### 16.1 Phase 1: MVP

**Goal:** Core functionality end-to-end.

| Component | Description |
|-----------|-------------|
| Config flow | Lock selection, code length configuration |
| Storage | `.storage/slotsentry` with SlotData, plain text |
| Sidebar panel | Slot grid, edit codes, save button |
| Commit engine | Disk commit + lock push with basic state tracking |
| Z-Wave backend | `set_lock_usercode`, `clear_lock_usercode`, basic verification |
| Entities | `sensor.slotsentry_push_status` |
| WebSocket API | `get_state`, `save`, `subscribe` |

**Acceptance Criteria:**
- Can add integration and select locks.
- Can open sidebar panel and see slot grid.
- Can enter codes, labels, and click save.
- Codes are persisted to storage.
- Codes are pushed to Z-Wave locks.
- Status column shows sync state.
- Push status sensor reflects current state.

### 16.2 Phase 2: Robust

**Goal:** Production-ready reliability and security.

| Component | Description |
|-----------|-------------|
| Secure mode | Encryption, password authentication, reveal codes |
| Keypad lockout | Lockout trigger entity, per-lock participation, suppress/restore |
| Audit trail | Rolling log, HA logbook events |
| Retry escalation | Full failure escalation path |
| Enable/disable slots | Checkbox behavior with clear/re-set |
| Entities | `binary_sensor.slotsentry_suppressed`, `button.slotsentry_push_all`, `button.slotsentry_retry` |
| Config reconfigure | Add/remove locks, change settings post-setup |

**Acceptance Criteria:**
- Secure mode encrypts/decrypts codes correctly.
- Password loss recovery works (reset flow).
- Keypad lockout triggers on sensor state change.
- Keypad restore re-pushes all codes.
- Audit trail records all events without exposing codes.
- All 4 entities function correctly.
- Reconfigure flow works without data loss.

### 16.3 Phase 3: Extensible

**Goal:** Community distribution and future-proofing.

| Component | Description |
|-----------|-------------|
| `LockBackend` protocol | Protocol is already defined and in use from Phase 1 (see section 10.8). Phase 3 documents it for external developers and adds the mock backend for testing. |
| HACS distribution | `hacs.json`, GitHub releases, custom repository setup |
| Documentation | User guide, developer guide for custom backends |
| Testing | Unit tests, integration tests, mock Z-Wave backend |

**Acceptance Criteria:**
- `LockBackend` protocol (already defined in Phase 1, section 10.8) is documented for external implementors.
- Z-Wave JS backend implements the full protocol including `addressing_mode`, `supported_code_lengths`, and `async_get_all_usercodes`.
- HACS installation works from custom repository.
- Test suite covers critical paths with a mock backend.

---

## 17. Future Enhancements

These items are explicitly out of scope for Phases 1-3 but are tracked for future consideration.

### 17.1 Temporary Codes with Expiration

- Assign a code to a slot with a start/end datetime.
- Automatically enable at start time, disable at end time.
- Useful for Airbnb guests, house cleaners, etc.

### 17.2 Non-Z-Wave Lock Backends

- `LockBackend` protocol (defined in section 10.8) enables supporting:
  - **Schlage cloud** (`lock.schlage_front_door_deadbolt`) — concrete planned backend. Uses name-based addressing via `schlage.add_code` / `schlage.delete_code` HA services. See BACKEND_REVIEW.md and SCHLAGE_CLOUD_RESEARCH.md for full design. The protocol changes in section 10.8 were made specifically to future-proof for this backend.
  - Zigbee locks (via ZHA)
  - Wi-Fi/cloud locks (August, Yale, etc.)
  - Matter locks
- Each backend implements the `LockBackend` protocol: `async_set_usercode(slot_info, code)`, `async_clear_usercode(slot_info)`, `async_get_usercode(slot_info)`, `async_get_all_usercodes()`, plus the `supports_readback`, `addressing_mode`, and `supported_code_lengths` properties.

### 17.3 Per-Lock Slot Assignments

- Currently, all locks get the same code for a given slot.
- Future: allow different codes for different locks on the same slot number.

### 17.4 Code Generation

- Button to auto-generate random codes meeting length requirements.
- Avoids sequential or repeated digit patterns.

### 17.5 Notification Integration

- Send HA notifications when codes are used (requires lock event integration).
- Alert on push failures.

---

## 18. Glossary

| Term | Definition |
|------|------------|
| **Slot** | A numbered position in a lock's user code table. Each slot holds one code. The total number of working slots is determined at setup by the capacity of the lock with the smallest slot capacity. |
| **User Code** | A numeric PIN (4-8 digits) that grants access when entered on a lock's keypad. |
| **Commit** | The act of writing data to persistent storage (disk commit) or pushing a code to a physical lock (lock commit). |
| **Commit State** | The synchronization status of a slot on a specific lock: `synced`, `out_of_sync`, `uncertain`, `error`, or `not_applicable`. |
| **Dirty** | A field that has been modified in the UI but not yet saved/pushed. |
| **Disk Commit** | Writing slot data to `.storage/slotsentry`. |
| **Lock Commit** | Pushing a code to a physical Z-Wave lock and verifying it. |
| **Readback** | Reading a code back from a lock to verify it was set correctly. Uses `invoke_cc_api` with User Code CC. |
| **Supervision** | Z-Wave protocol feature where the receiving node acknowledges command receipt and reports success/failure. |
| **Keypad Lockout** | Temporarily disabling all user codes on participating locks by clearing them via `clear_lock_usercode`, triggered when a lockout trigger entity enters a target state. SlotSentry does not issue lock or unlock commands. |
| **Keypad Suppression** | Synonym for keypad lockout. |
| **Secure Mode** | Optional feature that encrypts stored codes with a user-provided password. |
| **LockBackend** | Abstract protocol/interface for lock communication. Defined in `lock_backend.py` (section 10.8). Z-Wave JS is the Phase 1 implementation; Schlage cloud is the planned Phase 2/3 implementation. |
| **SlotInfo** | Dataclass passed to all `LockBackend` methods. Contains `slot_number` (physical slot for Z-Wave, internal index for cloud) and `label` (human name; used as code identifier on name-based backends). Wrapping context in a dataclass rather than bare parameters allows adding new fields without changing method signatures. |
| **addressing_mode** | `LockBackend` property returning `"slot"` (Z-Wave) or `"name"` (Schlage cloud). Determines whether the backend uses `slot_info.slot_number` or `slot_info.label` as the lock's code identifier, and whether label changes dirty the lock commit state. |
| **supported_code_lengths** | `LockBackend` property returning `(min_length, max_length)`. Enables the commit engine to pre-validate codes before attempting a push, providing clear error messages on length mismatches. |
| **Sidebar Panel** | A dedicated page in the HA sidebar (like Alarmo), NOT a Lovelace dashboard card. |
| **WebSocket API** | The communication channel between the sidebar panel (frontend) and the integration (backend). Custom commands are registered under the `slotsentry/` namespace. |
| **Commit Engine** | The backend module responsible for orchestrating disk saves, lock pushes, verification, retry logic, and state tracking. |
| **Aggregate Status** | The worst-case sync status across all locks for a given slot. If any lock is `error`, the aggregate is `error`. |
| **PBKDF2** | Password-Based Key Derivation Function 2. Used to derive an encryption key from the user's password. |
| **AES-256-GCM** | Authenticated encryption algorithm used for secure mode code storage. |
| **Code Readback** | See "Readback". |
| **FE599** | Schlage keypad lever lock. Fixed 4-digit code length. Returns asterisks on readback. |
| **BE469ZP** | Schlage Connect smart deadbolt. Configurable 4-8 digit code length. Returns actual codes on readback. |

---

*End of Product Specification Document*
