# SlotSentry Project Notes

## Project Location
- Source: `/homeassistant/SlotSentry/`
- Status: **Documentation/planning complete — NO CODE WRITTEN YET**
- User: ChrisCaho
- Phase: Pre-development (user said "dont start writing it until we agree we are finished discussing")

## Documentation Deliverables (All Complete — 2026-03-31)

| File | Author | Status |
|------|--------|--------|
| `docs/PRODUCT_SPEC.md` | Opus | Accepted |
| `docs/PROJECT_PLAN.md` | Sonnet | Accepted (v1.1 — door sensor removed, dynamic slot count, button flow, trigger example, code discovery) |
| `docs/HA_QUALITY_STANDARDS.md` | Sonnet | Accepted |
| `docs/UI_MOCKUPS.md` | Sonnet | Accepted (19 ASCII screens) |
| `docs/USER_GUIDE.md` | Haiku | Accepted (v1.1 — door sensor removed, dynamic slot count, button flow, trigger example, code discovery) |
| `docs/DEVELOPER_GUIDE.md` | Haiku | Accepted (v1.1 — door sensor removed, dynamic slot count, button flow, code discovery) |
| `docs/DATA_MODEL.md` | Haiku | Accepted (v1.1 — door sensor removed, dynamic slot count, code discovery) |
| `docs/LOCK_INVENTORY.md` | Haiku | Accepted (fixed model names) |
| `README.md` | Haiku | Accepted (v1.1 — door sensor removed, dynamic slot count, button flow, trigger example, code discovery) |
| `CONTRIBUTING.md` | Haiku | Accepted |

## Reminders
- `number.zwave_back_door_deadbolt_user_code_pin_length` was enabled (was disabled by integration) — **disable it again** when project is complete
- Current BE469ZP PIN length: **6 digits**
- Slot 19 on BE469ZP was used for testing — cleared after test

## Z-Wave Locks on This System

| Lock | Entity ID | Model | Slots | Code Length | Code Readback |
|------|-----------|-------|-------|-------------|---------------|
| Back Door | `lock.zwave_back_door_deadbolt` | BE469ZP | 30 (use 19) | 6 digits (configurable 4-8) | Yes (codes visible in Z-Wave JS UI) |
| Master Bedroom | `lock.zwave_master_bedroom_lock` | FE599 | 19 | 4 digits (fixed) | No (asterisks in Z-Wave JS UI) |
| Utility Room | `lock.zwave_utility_room_lock` | FE599 | 19 | 4 digits (fixed) | No (asterisks in Z-Wave JS UI) |
| Office | `lock.zwave_office_door_lock` | FE599 | 19 | 4 digits (fixed) | No (asterisks in Z-Wave JS UI) |

- Front Door (BE479 Encode Plus) is Schlage cloud, not Z-Wave — out of scope for MVP
- Max slots = 19 (determined by the lock with the smallest capacity across all configured locks — the three FE599s)
- Utility Room keypad currently showing as temporarily disabled
- Z-Wave JS add-on slug: `a0d7b954_zwavejs2mqtt`

## Test Results (2026-03-31)

### Per-Slot Enable/Disable (status 0x02) Test — BE469ZP Slot 19
- Set slot 19 with code "999999" via `set_lock_usercode`
- Then set status to 0x02 (Disabled) via `invoke_cc_api` (CC 99, method "set", params [19, 2, "999999"])
- **Result: Lock IGNORED the disable status.** Code 999999 still unlocked the door.
- Z-Wave JS UI showed slot 19 as "enabled" — firmware did not honor 0x02
- Z-Wave JS UI separate fields are misleading — they go through the same coupled API underneath
- Research confirmed: zwave-js author says "only setting user ID status doesn't work"

### Code Readback
- BE469ZP: codes are readable (visible in Z-Wave JS UI) — can verify actual codes
- FE599: codes show as asterisks (firmware masks them) — can only verify slot status (occupied/available)

## Architecture Decisions (Agreed)

### Config Flow (Integration Setup)
- Lock discovery/selection during integration add
- Optional lockout trigger selection during setup
- Secure mode on/off handled at integration level (configure/reconfigure)
  - Turn on: checkbox → warning about encryption/data loss → double password entry (8-16 chars)
  - Turn off: requires current password to decrypt → warning → stores plain
  - Bad password recovery: after N failures → offer new password with data loss warning + reinit
- Code length configuration at integration level:
  - Integration auto-detects code lengths from lock capabilities and suggests defaults
  - If discovery fails or data unavailable: default to 4/6 (two lengths) or 6 (single)
  - Checkbox: support one code length or two (long + short)
  - If TWO code lengths:
    - "Short" field: default 4, range 4-7
    - "Long" field: default 6, range 5-8
  - If ONE code length:
    - "Code Length" field: default 6, range 4-8
  - These globals determine how many code fields show per slot in the UI
- Add/remove locks via reconfigure
- Keypad lockout settings (lockout trigger entity, per-lock participation checkboxes) via reconfigure
- **No door sensor mapping** — SlotSentry is a code manager only and never issues lock/unlock commands

### Dynamic Slot Count
- Slot count is NOT hardcoded to 19 or any other fixed number
- Determined at integration setup from the lock with the smallest slot capacity among selected locks
- On this system that happens to be 19 (three FE599s), but the design is generic
- Commit arrays are sized at setup time and stored in config entry
- If locks change via reconfigure, slot count is re-evaluated

### Sidebar Panel — Slot Manager UI

#### Top Bar (Secure Mode)
- Password field at top of panel (only visible in secure mode)
- "Reveal Codes" checkbox to the right of password field
- Reveal checkbox **grayed out** until at least 8 characters entered in password field
- Entering correct password unlocks panel data (codes show as asterisks)
- Checking "Reveal Codes" requires password validation → then codes become visible
- Without correct password: no slot data displayed at all

#### Slot Grid
- Rows = slots (count determined dynamically — see Dynamic Slot Count above)
- Columns per row:
  - Slot number
  - Enable/disable checkbox
  - Label (text field, e.g., "Dog Sitter")
  - Long code field (only shown if two code lengths configured)
  - Short code field (only shown if two code lengths configured)
  - Single "Code" field (if one code length configured)
  - Help button (?) next to code fields — explains long/short code concept
- Codes visible while editing; asterisks after save (secure mode) or always visible (open mode)
- If a code length is unnecessary for a slot, leave that field empty

#### Save / Discard / Exit Button Flow
- **Exit**: shown when panel opens with no pending changes; closes the panel
- **Save**: shown when user has made edits; commits to disk and pushes to locks
- **Discard**: shown alongside Save while edits are pending; reverts all unsaved edits
- After a successful Save, **Exit** is shown again (no pending changes)
- No "Save / Update" combined name — the button is always just "Save"

### Commit State Machine (Critical)

#### Data Structures
- **Disk commit array**: per-slot, per-field — tracks what's saved to `.storage/slotsentry`
- **Lock commit arrays**: per-lock, per-slot, per-field — tracks sync state with each physical lock
- States: `synced`, `out_of_sync`, `uncertain` (timed out / unknown result)

#### Save Flow
1. **Commit to disk first** — write updated slots to `.storage/slotsentry`, update disk commit array
2. **Mark lock arrays** — all locks get `out_of_sync` for any fields/slots just updated to disk
3. **Push to locks one at a time** — for each lock:
   a. Push changed slots to this lock
   b. **Verify** where possible (invoke_cc_api get → check occupied/available; BE469ZP can verify actual codes)
   c. Update lock commit array based on verification (not just write success)
   d. Persist lock commit array to disk
   e. Continue to next lock
4. **Success** — all locks synced → show "All committed" message on screen
5. **Partial failure** — maintain `out_of_sync` / `uncertain` for failed fields/slots in lock arrays, persist to disk, continue to next lock, keep trying

#### Timeout & Error Handling
- **Max 1 minute timeout per lock operation** — no spinning forever
- If timeout: mark slot as `uncertain` (don't know if it committed)
- Suggest user "Save" again → walks lock arrays, retries `out_of_sync` and `uncertain` fields only
- Second retry fails → one more attempt allowed
- Third failure → gray out Save button, message: "Exit UI and reopen to try again, or reboot HA if problem continues"
- Nuclear option: Save becomes "Wipe Lock / Update All Slots" button
- Last resort: reconfigure integration → remove lock → save → re-add lock → update/save

#### On Panel Open
- Check lock commit arrays for any `out_of_sync` or `uncertain` slots
- If found: automatically attempt to re-push those slots
- Visual indicator on affected slots so user knows something needs attention

### Enable/Disable Per Slot
- **Disable:** `zwave_js.clear_lock_usercode` → slot empty on lock, code retained in SlotSentry storage
- **Enable:** `zwave_js.set_lock_usercode` → re-push stored code to lock
- **Verify:** After set/clear, `invoke_cc_api` get → confirm status=Occupied or status=Available
- Dog sitter scenario: toggle enable → codes pushed to all locks. Toggle disable → codes cleared from all locks. No code editing needed.

### Keypad Lockout Feature
- Lockout trigger: user-configurable, any entity (alarm, presence, time of day, anything)
- Per-lock checkbox: "Participate in keypad lockout" (on/off)
- When lockout trigger target state = true → disable keypad on participating locks (keypad enable/disable only — no lock/unlock commands)
- When lockout trigger changes away from target state → re-enable keypad
- Never clear codes for this — keypad enable/disable is the hardware gate
- Interior and exterior locks all have the checkbox, user decides participation
- No assumptions about "armed/disarmed" — it's generic sensor + target state
- SlotSentry does NOT issue `lock.lock` or `lock.unlock` commands — it is a code manager only

### Secure Mode (Summary)
- **Setup/teardown:** handled in integration config flow (not sidebar panel)
- **Panel access:** password at top of sidebar panel, no data without correct password
- **Code reveal:** separate checkbox requiring re-entry of password, grayed out until 8+ chars typed
- **Storage:** password IS the encryption key, all slot data encrypted in `.storage/slotsentry`
- **Password loss:** data lost forever, reinit required
- **Default:** OFF (open mode — no password, no asterisks, no risk of data loss)

### Audit Trail
- Log code pushes (slot #, lock name, timestamp, success/fail)
- Log code changes (slot label changes, no codes in logs ever)
- Log keypad disable/enable events with trigger reason
- Log slot enable/disable events
- Rolling history in `.storage/slotsentry` (configurable depth)
- Optionally expose as HA logbook-compatible events
- No codes ever written to logs — only slot numbers and labels

### Entities (Minimal)
- `sensor.slotsentry_push_status` — last push result
- `binary_sensor.slotsentry_suppressed` — keypad lockout active
- `button.slotsentry_push_all` — force push all codes to all locks
- `button.slotsentry_retry` — retry failed pushes

### Build Phases
1. **MVP** — config flow (lock selection, code length config with auto-detection, dynamic slot count), storage, sidebar panel slot grid, push codes to locks, commit state machine, verification
2. **Robust** — keypad lockout, secure mode, audit trail
3. **Extensible** — `LockBackend` protocol, HACS distribution

### LockBackend Shim Pattern

SlotSentry supports multiple lock protocols through a unified `LockBackend` interface using the shim/adapter pattern:

- **Interface Design:** SlotManager calls the same `LockBackend` interface for all lock types (push_code, clear_slot, verify_slot)
- **Per-Protocol Shims:** Each lock protocol gets a shim (adapter) that translates generic SlotManager calls to protocol-specific operations
- **SlotInfo Dataclass:** Carries both `slot_number` and `label` to every backend call, enabling flexible addressing modes
  - Z-Wave shim uses `slot_number` for addressing, ignores `label`
  - Cloud shim uses `label` as code identifier (required for name-based addressing), `slot_number` is internal index only
  - Label uniqueness enforced in SlotManager (required for name-based backends like Schlage cloud)
- **Phase 1:** ZWaveJSBackend shim (slot-number addressing) — production ready
- **Future:** SchlageCloudBackend shim (name-based addressing) — planned for v2+
- **Backend Properties:**
  - `addressing_mode` property: returns "slot" or "name" to indicate addressing strategy
  - `supported_code_lengths` property: returns (min, max) tuple for pre-push validation (e.g., BE469ZP returns (4, 8), FE599 returns (4, 4))

### Keypad Lockout Feature — Important Backend Limitation

Schlage cloud locks (e.g., Schlage BE479 Encode Plus) do NOT support programmatic keypad disable. The `binary_sensor.slotsentry_suppressed` sensor will be read-only for cloud-backed locks. Keypad lockout will only function on locks whose backend explicitly supports the `clear_lock_keypad` operation (currently Z-Wave JS only).

### Future Ideas (Not MVP)
- **Temporary codes:** checkbox on a slot marked "Temp", with expiration (days/hours). Code auto-disabled (cleared from locks) on expiry, retained on disk with status=disabled.

## Research Completed: Per-Slot Enable/Disable (2026-03-31)

**Verdict: Status 0x02 does NOT work. Clear/re-set is the only reliable approach.**

### Key Findings
1. Z-Wave spec status 0x02 is "Reserved by Administrator" — NOT "Disabled". Schlage ignores it entirely.
2. zwave-js library author (AlCalzone) confirms: "Only setting the user ID status doesn't work" — code and status are always coupled in the underlying Z-Wave command.
3. Z-Wave JS UI shows separate fields but they go through the same coupled `setValue` API — the UI is misleading.
4. Every production lock code manager (Keymaster, Lock Code Manager) uses the clear/re-set pattern. Battle-tested across thousands of installations.
5. Code readback: Schlage locks return masked codes (`****`) on FE599 — SlotSentry MUST capture and store codes at set-time. BE469ZP returns actual codes (useful for verification).
6. BE469ZP Config Parameter 6 ("User Slot Bit Field") is READ-ONLY — useful for verification but cannot disable slots.
7. Supervision results from `set` method indicate whether lock acknowledged the command — use for push status.

### Sources
- [zwave-js Discussion #6717](https://github.com/zwave-js/zwave-js/discussions/6717) — AlCalzone confirming limitation
- [Keymaster](https://github.com/FutureTense/keymaster) — uses clear/re-set pattern
- [Lock Code Manager](https://github.com/raman325/lock_code_manager) — same pattern
- [Z-Wave JS UI Issue #3845](https://github.com/zwave-js/zwave-js-ui/issues/3845) — Schlage slot display issues

### Z-Wave JS Server Websocket (for reference)
- Port 3000, path /zjs in the add-on
- Commands: `endpoint.invoke_cc_api` with nodeId, endpoint, commandClass, methodName, args
- SlotSentry should NOT connect directly — use HA's `zwave_js.*` services instead to avoid conflicts
