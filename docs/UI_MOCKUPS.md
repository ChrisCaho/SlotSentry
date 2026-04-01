# SlotSentry — UI Mockups
# Revision: 1.1
# All screens shown in monospace / ASCII box-drawing format.
# These mockups are intended to guide frontend development.
# Sizes are approximate; actual rendering adapts to HA panel width.

---

## Table of Contents

1. [Config Flow — Step 1: Welcome](#1-config-flow--step-1-welcome)
2. [Config Flow — Step 2: Lock Discovery & Selection](#2-config-flow--step-2-lock-discovery--selection)
3. [Config Flow — Step 3: Code Length Configuration](#3-config-flow--step-3-code-length-configuration)
4. [Config Flow — Step 4: Lockout Trigger Selection](#4-config-flow--step-4-lockout-trigger-selection)
5. [Config Flow — Step 5: Confirmation / Summary](#5-config-flow--step-5-confirmation--summary)
6. [Config Flow — Reconfigure](#6-config-flow--reconfigure)
7. [Sidebar Panel — Slot Manager (Open Mode, Two Code Lengths)](#7-sidebar-panel--slot-manager-open-mode-two-code-lengths)
8. [Sidebar Panel — Slot Manager (Open Mode, Single Code Length)](#8-sidebar-panel--slot-manager-open-mode-single-code-length)
9. [Sidebar Panel — Slot Manager (Secure Mode, Locked)](#9-sidebar-panel--slot-manager-secure-mode-locked)
10. [Sidebar Panel — Slot Manager (Secure Mode, Unlocked, Codes Hidden)](#10-sidebar-panel--slot-manager-secure-mode-unlocked-codes-hidden)
11. [Sidebar Panel — Slot Manager (Secure Mode, Codes Revealed)](#11-sidebar-panel--slot-manager-secure-mode-codes-revealed)
12. [Sidebar Panel — Commit Status (In Progress)](#12-sidebar-panel--commit-status-in-progress)
13. [Sidebar Panel — Commit Status (Success)](#13-sidebar-panel--commit-status-success)
14. [Sidebar Panel — Commit Status (Partial Failure)](#14-sidebar-panel--commit-status-partial-failure)
15. [Sidebar Panel — Commit Status (Escalated Failure)](#15-sidebar-panel--commit-status-escalated-failure)
16. [Post-Commit Popup](#16-post-commit-popup)
17. [Secure Mode Setup Dialog](#17-secure-mode-setup-dialog)
18. [Password Recovery Dialog](#18-password-recovery-dialog)
19. [Help Popup (? Button)](#19-help-popup--button)

---

## 1. Config Flow — Step 1: Welcome

```
┌──────────────────────────────────────────────────────────────┐
│  Add Integration                                  [ HA logo ] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│         🔐  SlotSentry                                       │
│         Z-Wave Lock Code Manager                             │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  SlotSentry gives you a single place to manage PIN    │  │
│  │  codes across all your Z-Wave locks.                  │  │
│  │                                                        │  │
│  │  With SlotSentry you can:                             │  │
│  │                                                        │  │
│  │    • Manage named code slots across all your locks     │  │
│  │    • Push codes to multiple locks simultaneously      │  │
│  │    • Enable or disable individual slots per person    │  │
│  │    • Optionally use two code lengths (e.g., 6-digit   │  │
│  │      deadbolts + 4-digit interior keypads)            │  │
│  │    • Optionally encrypt stored codes (Secure Mode)    │  │
│  │    • Automatically suppress keypads based on any      │  │
│  │      sensor state (e.g., when you're home and the     │  │
│  │      alarm is armed) (Keypad Lockout)                 │  │
│  │                                                        │  │
│  │  This wizard will help you discover your locks,       │  │
│  │  configure code lengths, and optionally set up a      │  │
│  │  keypad lockout trigger.                              │  │
│  │                                                        │  │
│  │  Note: Secure Mode can be enabled now or later via    │  │
│  │  Reconfigure. Default is OFF (open mode).             │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│                                       [ Cancel ]  [ Next > ] │
└──────────────────────────────────────────────────────────────┘
```

**Notes:**
- This is a standard HA config flow dialog rendered inside the Integrations UI.
- No user input required on this step — it is informational only.
- "Next >" advances to lock discovery.
- "Cancel" aborts the entire setup and removes the integration entry.

---

## 2. Config Flow — Step 2: Lock Discovery & Selection

```
┌──────────────────────────────────────────────────────────────┐
│  Add Integration — SlotSentry (Step 2 of 5)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Select Z-Wave Locks                                         │
│  ─────────────────────────────────────────────────────────  │
│  The following Z-Wave lock entities were found.              │
│  Select all locks you want SlotSentry to manage.            │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  [x]  Back Door          lock.zwave_back_door_deadbolt │  │
│  │       Model: BE469ZP  •  Slots: 30  •  Code: 4-8 dig. │  │
│  │       Code readback: YES                               │  │
│  │                                                        │  │
│  │  [x]  Master Bedroom     lock.zwave_master_bedroom_lock│  │
│  │       Model: FE599    •  Slots: 19  •  Code: 4 dig.   │  │
│  │       Code readback: NO (firmware masks codes)         │  │
│  │                                                        │  │
│  │  [x]  Utility Room       lock.zwave_utility_room_lock  │  │
│  │       Model: FE599    •  Slots: 19  •  Code: 4 dig.   │  │
│  │       Code readback: NO (firmware masks codes)         │  │
│  │       ⚠  Keypad currently shows as temporarily disabled│  │
│  │                                                        │  │
│  │  [x]  Office Door        lock.zwave_office_door_lock   │  │
│  │       Model: FE599    •  Slots: 19  •  Code: 4 dig.   │  │
│  │       Code readback: NO (firmware masks codes)         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Manageable slots: 19  (set by the lock with the smallest capacity)  │
│                                                              │
│  ℹ  Locks not shown here are not Z-Wave entities or are     │
│     not supported. Cloud-managed locks (e.g., Schlage       │
│     Encode) are out of scope.                               │
│                                                              │
│  At least one lock must be selected.                         │
│                                                              │
│                             [ < Back ]  [ Cancel ]  [ Next > ]│
└──────────────────────────────────────────────────────────────┘
```

**Notes:**
- Lock list is populated by querying HA entity registry for entities with platform `zwave_js` and device class `lock`.
- Model, slot count, and code readback capability are read from Z-Wave JS node metadata at discovery time.
- "Manageable slots" dynamically computes the minimum slot count across all selected locks. Updates live as user checks/unchecks.
- Warning icon on Utility Room reflects current keypad state — informational only, does not block selection.
- Deselecting all locks shows an inline error: "At least one lock must be selected" and disables Next.
- If no Z-Wave locks are found at all, an error state replaces the list: "No Z-Wave lock entities found. Ensure Z-Wave JS is configured and locks are paired."

---

## 3. Config Flow — Step 3: Code Length Configuration

### Variant A — Two Code Lengths (checkbox checked)

```
┌──────────────────────────────────────────────────────────────┐
│  Add Integration — SlotSentry (Step 3 of 5)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ℹ  Code lengths have been detected from your selected       │
│     locks. Defaults below reflect what was discovered.       │
│     Adjust if needed.                                        │
│                                                              │
│  Code Length Configuration                                   │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Some households have locks that accept different PIN        │
│  lengths (e.g., a 6-digit deadbolt and 4-digit interior     │
│  keypads). SlotSentry can manage two code lengths at once,  │
│  showing a separate field for each in the Slot Manager.     │
│                                                              │
│  [x]  Support two code lengths (Long + Short)               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Short code length:                                    │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  4                                               │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │  (digits per PIN — range 4 to 7, default 4)           │  │
│  │                                                        │  │
│  │  Long code length:                                     │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  6                                               │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │  (digits per PIN — range 5 to 8, default 6)           │  │
│  │                                                        │  │
│  │  Note: Short must be strictly less than Long.          │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ℹ  These values apply globally. You can change them later  │
│     via Reconfigure, but existing codes will need to be     │
│     re-entered if the lengths change.                       │
│                                                              │
│                             [ < Back ]  [ Cancel ]  [ Next > ]│
└──────────────────────────────────────────────────────────────┘
```

### Variant B — Single Code Length (checkbox unchecked)

```
┌──────────────────────────────────────────────────────────────┐
│  Add Integration — SlotSentry (Step 3 of 5)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ℹ  Code lengths have been detected from your selected       │
│     locks. Defaults below reflect what was discovered.       │
│     Adjust if needed.                                        │
│                                                              │
│  Code Length Configuration                                   │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Some households have locks that accept different PIN        │
│  lengths (e.g., a 6-digit deadbolt and 4-digit interior     │
│  keypads). SlotSentry can manage two code lengths at once,  │
│  showing a separate field for each in the Slot Manager.     │
│                                                              │
│  [ ]  Support two code lengths (Long + Short)               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Code length:                                          │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  6                                               │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │  (digits per PIN — range 4 to 8, default 6)           │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ℹ  These values apply globally. You can change them later  │
│     via Reconfigure, but existing codes will need to be     │
│     re-entered if the lengths change.                       │
│                                                              │
│                             [ < Back ]  [ Cancel ]  [ Next > ]│
└──────────────────────────────────────────────────────────────┘
```

**Notes:**
- When the "two code lengths" checkbox is toggled ON, the Short and Long fields animate in; toggling OFF collapses them to the single Code Length field.
- Validation:
  - Short must be in range [4, 7].
  - Long must be in range [5, 8].
  - Short must be strictly less than Long (e.g., Short=5, Long=5 is invalid).
  - Single code length must be in range [4, 8].
- Inline error example for invalid short >= long: "Short code length must be less than long code length."
- Out-of-range entry: "Must be between 4 and 7." shown beneath the offending field.
- **Code length discovery:** The integration reads code length metadata from Z-Wave JS node properties for each selected lock during Step 2. If all locks report discoverable code lengths, those values are used as the defaults on this screen. If one or more locks cannot report their code length, an alternate info banner is shown:
  - `⚠  Unable to determine code length for one or more locks. Default values shown — please verify against your lock specifications.`
  - In this undiscoverable case, the two-length variant defaults to Short=4, Long=6; the single-length variant defaults to 6.
- Default values when all locks are discoverable: defaults match the detected lock code lengths.

---

## 4. Config Flow — Step 4: Lockout Trigger Selection

```
┌──────────────────────────────────────────────────────────────┐
│  Add Integration — SlotSentry (Step 4 of 5)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Keypad Lockout — Optional                                   │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  SlotSentry can automatically disable lock keypads on       │
│  selected locks when a sensor reaches a target state        │
│  (e.g., when you're home and the alarm is armed, at night,  │
│  or any other condition).                                   │
│                                                              │
│  This uses the lock's keypad-enable/disable hardware        │
│  feature — codes are preserved, only keypad entry is        │
│  blocked.                                                    │
│                                                              │
│  [ ]  Enable Keypad Lockout feature                         │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  (collapsed — only visible when checkbox is checked)   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
│                                                              │
│  [x]  Enable Keypad Lockout feature          (EXPANDED)      │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Lockout trigger entity (any HA entity):               │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  binary_sensor.alarm_armed_home              [x] │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │  (search or select from entity picker)                 │  │
│  │                                                        │  │
│  │  Target state (lockout active when entity equals):     │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  on                                          [v] │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │  Options: on / off / home / away / armed / disarmed /  │  │
│  │           triggered / custom...                        │  │
│  │                                                        │  │
│  │  Participating locks (which locks honor lockout):      │  │
│  │  [x]  Back Door           lock.zwave_back_door_deadbolt│  │
│  │  [x]  Master Bedroom      lock.zwave_master_bedroom_lock│ │
│  │  [ ]  Utility Room        lock.zwave_utility_room_lock │  │
│  │  [x]  Office Door         lock.zwave_office_door_lock  │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  You can skip this step. Keypad Lockout can be configured   │
│  later via Reconfigure.                                     │
│                                                              │
│                             [ < Back ]  [ Cancel ]  [ Next > ]│
└──────────────────────────────────────────────────────────────┘
```

**Notes:**
- When "Enable Keypad Lockout feature" is unchecked, the entire inner block is hidden (collapsed).
- Lockout trigger entity uses HA's standard entity picker component — user can type to search.
- Target state dropdown is populated based on the entity's domain (binary_sensor gets on/off; alarm_control_panel gets armed/disarmed/etc.; a generic sensor gets a "custom..." text entry).
- Per-lock participation checkboxes default to all checked. Utility Room example shows it unchecked — user may exclude locks they don't want to participate.
- Selecting no participating locks while the feature is enabled shows a warning: "At least one lock must participate in lockout. Otherwise disable the feature."
- This step is fully optional; skipping (Next with checkbox unchecked) is valid.

---

## 5. Config Flow — Step 5: Confirmation / Summary

```
┌──────────────────────────────────────────────────────────────┐
│  Add Integration — SlotSentry (Step 5 of 5)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Review & Confirm                                            │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Please review your configuration before finishing.         │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Managed Locks (4)                                     │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │   Back Door       BE469ZP   6-digit    Readback: YES   │  │
│  │   Master Bedroom  FE599     4-digit    Readback: NO    │  │
│  │   Utility Room    FE599     4-digit    Readback: NO    │  │
│  │   Office Door     FE599     4-digit    Readback: NO    │  │
│  │                                                        │  │
│  │  Code Lengths                                          │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │   Mode:  Two code lengths (Long + Short)               │  │
│  │   Long:  6 digits                                      │  │
│  │   Short: 4 digits                                      │  │
│  │                                                        │  │
│  │  Keypad Lockout                                        │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │   Enabled:  YES                                        │  │
│  │   Trigger:  binary_sensor.alarm_armed_home = on        │  │
│  │   Locks:    Back Door, Master Bedroom, Office Door     │  │
│  │             (Utility Room excluded)                    │  │
│  │                                                        │  │
│  │  Secure Mode                                           │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │   Status:   OFF (codes stored in plain text)           │  │
│  │   You can enable Secure Mode later via Reconfigure.    │  │
│  │                                                        │  │
│  │  Available Slots                                       │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │   19 slots (determined by lock with fewest slots)      │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  After finishing, open the SlotSentry panel from the        │
│  sidebar to begin entering codes.                           │
│                                                              │
│                          [ < Back ]  [ Cancel ]  [ Finish ] │
└──────────────────────────────────────────────────────────────┘
```

**Notes:**
- All summary fields are read-only. "< Back" at any point in the flow re-navigates to the appropriate step.
- "Finish" creates the config entry, registers entities, and initializes `.storage/slotsentry` with empty slots (count determined by the lock with the smallest capacity).
- No codes are pushed at this point — the user enters codes in the sidebar panel.
- If Secure Mode was configured during setup (not typical; default is OFF), it appears as "ON — codes encrypted."
- A spinner may appear briefly on "Finish" while the integration initializes Z-Wave JS connections.

---

## 6. Config Flow — Reconfigure

```
┌──────────────────────────────────────────────────────────────┐
│  Reconfigure — SlotSentry                                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  SECTION: Secure Mode                                  │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │                                                        │  │
│  │  Current status:  OFF (open mode)                      │  │
│  │                                                        │  │
│  │  [x]  Enable Secure Mode                               │  │
│  │                                                        │  │
│  │  (When checked, password fields appear below)          │  │
│  │                                                        │  │
│  │  New password (8-16 characters):                       │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  ••••••••••                                      │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  Confirm password:                                     │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  ••••••••••                                      │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  ⚠  WARNING: The password IS the encryption key.      │  │
│  │     If you forget it, all stored code data is lost    │  │
│  │     forever and must be re-entered.                   │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  SECTION: Managed Locks                                │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │                                                        │  │
│  │  [x]  Back Door           lock.zwave_back_door_deadbolt│  │
│  │  [x]  Master Bedroom      lock.zwave_master_bedroom_lock│ │
│  │  [x]  Utility Room        lock.zwave_utility_room_lock │  │
│  │  [x]  Office Door         lock.zwave_office_door_lock  │  │
│  │                                                        │  │
│  │  Uncheck a lock to stop managing it (its codes will    │  │
│  │  not be cleared from the physical lock automatically). │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  SECTION: Code Lengths                                 │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │                                                        │  │
│  │  [x]  Support two code lengths (Long + Short)          │  │
│  │                                                        │  │
│  │  Short code length:  [ 4 ]   (range 4-7)               │  │
│  │  Long  code length:  [ 6 ]   (range 5-8)               │  │
│  │                                                        │  │
│  │  ⚠  Changing code lengths will invalidate any         │  │
│  │     existing codes of the wrong length. Affected      │  │
│  │     slots will be flagged and must be re-entered.     │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  SECTION: Keypad Lockout                               │  │
│  │  ─────────────────────────────────────────────────     │  │
│  │                                                        │  │
│  │  [x]  Enable Keypad Lockout feature                    │  │
│  │                                                        │  │
│  │  Lockout trigger entity:                               │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  binary_sensor.alarm_armed_home            [x]  │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  Target state:                                         │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  on                                        [v]  │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  Per-lock participation:                               │  │
│  │  [x]  Back Door           lock.zwave_back_door_deadbolt│  │
│  │  [x]  Master Bedroom      lock.zwave_master_bedroom_lock│ │
│  │  [ ]  Utility Room        lock.zwave_utility_room_lock │  │
│  │  [x]  Office Door         lock.zwave_office_door_lock  │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│                                    [ Cancel ]  [ Save ]      │
└──────────────────────────────────────────────────────────────┘
```

**Notes:**
- Reconfigure is accessed via the Integration card > "..." menu > Reconfigure.
- All three sections are shown expanded on one scrollable page (no wizard steps).
- Secure Mode toggle behavior:
  - Currently OFF → checking "Enable Secure Mode" shows password fields.
  - Currently ON → unchecking "Enable Secure Mode" shows: "Enter current password to decrypt and disable Secure Mode" + current password field.
  - Bad password on disable: shows inline error, does not save.
- Removing a lock (unchecking it): a warning tooltip appears: "Removing a lock from management will not clear its codes. Use the Slot Manager to clear codes first if desired."
- Changing code lengths while slots have existing codes: a warning banner appears at the top of the Code Lengths section. On save, affected slots are marked as needing re-entry in storage.
- "Save" applies all changes and restarts affected integrations if needed.

---

## 7. Sidebar Panel — Slot Manager (Open Mode, Two Code Lengths)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  Open (codes visible)   Code lengths: Long 6-digit / Short 4-digit   ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦═══╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  1 ║  [x]  ║  Master          ║  [ 847291 ]      ║  [ 2847 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ 391047 ]      ║  [ 3910 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  3 ║  [x]  ║  Guest           ║  [ 102938 ]      ║  [ 1029 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  4 ║  [x]  ║  Cleaner         ║  [ 774421 ]      ║  [ 7744 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  5 ║  [ ]  ║  Contractor      ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  6 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  7 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  8 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  9 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 10 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 11 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 12 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 13 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 14 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 15 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 16 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 17 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 18 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 19 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩═══╝

  [ ] Update All Slots                                          [ Exit ]
```

*(When edits are pending — dirty state:)*
```
  [ ] Update All Slots                          [ Discard ]  [ Save ]
```

**Notes:**
- Panel is rendered as a full-width HA sidebar panel (not a dialog).
- Header shows connected lock names and current mode.
- Column widths adapt to panel width; minimum viable width ~720px.
- `#` column: slot number, read-only.
- `On?` column: checkbox. Unchecked = slot disabled. Disabled slots are shown with dimmed row styling (gray text).
- **Button flow:** When no changes have been made, only `[ Exit ]` is shown. As soon as any field is edited (dirty state), the button area switches to `[ Discard ]  [ Save ]`. "Discard" discards all pending changes and exits the panel. "Save" commits changes to disk and pushes to locks. Checking "Update All Slots" counts as a dirty action and causes Save + Discard to appear.
- The slot count shown (19 rows in this example) is dynamic — it reflects the number of manageable slots determined by the lock with the smallest capacity.
  - Slot 2 (Dog Sitter) is disabled — its codes are stored but cleared from all locks.
  - Slot 5 (Contractor) is disabled and empty — codes not yet entered.
- `Label` column: free-text field, max 24 characters. Labels must be unique (case-insensitive) when non-empty, enforced by SlotManager for compatibility with name-based lock backends (planned for future cloud lock support).
- `Long Code` column: numeric field, exactly `long_code_length` digits required. Shows inline length hint on focus.
- `Short Code` column: numeric field, exactly `short_code_length` digits required.
- `?` column: clicking opens the Help Popup (see Screen 19).
- Dirty tracking: when a user edits any field, the row background changes to a subtle yellow/amber tint to indicate unsaved changes.
- `Update All Slots` checkbox: when checked, Save ignores dirty tracking and pushes all slots to all locks. Checking this counts as a dirty action — Save + Discard buttons appear.
- Slot 5 (Contractor): enabled checkbox is checked but codes are empty — saving will attempt to push an empty code, which is treated as a clear/disable. An inline warning may appear: "Enable is checked but codes are empty. Slot will be disabled on locks."

---

## 8. Sidebar Panel — Slot Manager (Open Mode, Single Code Length)

```
╔══════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                  v1.0.0      ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door          ║
║  Mode:  Open (codes visible)   Code length: 6-digit                     ║
╠════╦═══════╦══════════════════════╦══════════════════════╦═══╣
║  # ║  On?  ║  Label               ║  Code                ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  1 ║  [x]  ║  Master              ║  [ 847291 ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  2 ║  [ ]  ║  Dog Sitter          ║  [ 391047 ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  3 ║  [x]  ║  Guest               ║  [ 102938 ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  4 ║  [x]  ║  Cleaner             ║  [ 774421 ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  5 ║  [ ]  ║  Contractor          ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  6 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  7 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  8 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║  9 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 10 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 11 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 12 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 13 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 14 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 15 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 16 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 17 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 18 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╠════╬═══════╬══════════════════════╬══════════════════════╬═══╣
║ 19 ║  [ ]  ║                      ║  [        ]          ║ ? ║
╚════╩═══════╩══════════════════════╩══════════════════════╩═══╝

  [ ] Update All Slots                                          [ Exit ]
```

*(When edits are pending — dirty state:)*
```
  [ ] Update All Slots                          [ Discard ]  [ Save ]
```

**Notes:**
- Identical to the two-code-length variant except the "Long Code" and "Short Code" columns are replaced by a single "Code" column.
- The `?` help button in this mode explains that the single code will be pushed to all locks regardless of their native PIN length (user is responsible for ensuring all locks accept the configured length).
- The "Code length: 6-digit" header hint reminds the user of the configured length.
- All other behavior (dirty tracking, enable/disable, Save button, Update All, Exit/Discard flow) is identical to Screen 7.

---

## 9. Sidebar Panel — Slot Manager (Secure Mode, Locked)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  SECURE — Enter password to access slot data                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Password:  [ __________________________ ]  Reveal Codes  [ ] (grayed out)  ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║                                                                              ║
║           ╔═══════════════════════════════════════════╗                      ║
║           ║                                           ║                      ║
║           ║   Enter your password above to view       ║                      ║
║           ║   and edit slot data.                     ║                      ║
║           ║                                           ║                      ║
║           ║   Slot data is encrypted and cannot       ║                      ║
║           ║   be displayed without the correct        ║                      ║
║           ║   password.                               ║                      ║
║           ║                                           ║                      ║
║           ╚═══════════════════════════════════════════╝                      ║
║                                                                              ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**Notes:**
- When Secure Mode is ON, this is the initial state of the panel — the slot grid is entirely absent.
- The password field accepts input. After each keystroke, the integration checks if length >= 8.
  - Below 8 chars: "Reveal Codes" checkbox remains grayed out and unclickable.
  - At 8+ chars: "Reveal Codes" becomes clickable but does not automatically reveal — it waits for the password to be validated.
- Pressing Enter or tabbing out of the password field triggers validation:
  - Correct password: transitions to Secure Mode Unlocked state (Screen 10).
  - Wrong password: inline error below field: "Incorrect password. X attempts remaining before recovery mode." (configurable threshold, e.g., 5 attempts).
  - Attempt counter persists across panel close/reopen (stored in `.storage/slotsentry`).
- The placeholder text in the password field is "Enter password…" (shown in lighter gray).
- **Reveal Codes pre-check behavior:** If the user checks "Reveal Codes" before entering the password (once the checkbox becomes active at 8+ chars), the checkbox state is remembered. After the password is validated successfully, codes are revealed immediately on that same password validation — no second prompt is needed.

---

## 10. Sidebar Panel — Slot Manager (Secure Mode, Unlocked, Codes Hidden)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  SECURE — Unlocked  [Lock Now]          Code lengths: Long 6 / Sh 4  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Password:  [ •••••••••• ]   [x] Reveal Codes  (click to show code values)  ║
║                                                                              ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦═══╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  1 ║  [x]  ║  Master          ║  [ ****** ]      ║  [ **** ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ ****** ]      ║  [ **** ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  3 ║  [x]  ║  Guest           ║  [ ****** ]      ║  [ **** ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  4 ║  [x]  ║  Cleaner         ║  [ ****** ]      ║  [ **** ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  5 ║  [ ]  ║  Contractor      ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  6 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  7 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ .. ║  ...  ║  ...             ║  ...             ║  ...          ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 19 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩═══╝

  [ ] Update All Slots                                          [ Exit ]
```

*(When edits are pending — dirty state:)*
```
  [ ] Update All Slots                          [ Discard ]  [ Save ]
```

**Notes:**
- After a correct password is entered (Screen 9), the slot grid appears with labels and enable states visible.
- All code fields show `******` (asterisks) — codes are NOT visible yet even though the panel is unlocked.
- "Reveal Codes" checkbox is now active (not grayed). It is unchecked by default on every panel open.
- The password field retains the dot-obscured value so the user can check "Reveal Codes" without re-typing.
- `[Lock Now]` button in the header immediately returns the panel to the locked state (Screen 9) and clears the decrypted data from memory.
- Editing a code field (clicking into a `[ ****** ]` cell) will:
  - Clear the asterisks and show the new input in plaintext while being typed.
  - New codes remain visible until the next Save/commit, then are covered with asterisks.
  - If the user clicks away without entering a valid code, the field reverts to `******` (restoring the original stored code).
- Enabling/disabling slots and editing labels works normally — these fields are not encrypted.
- Save in secure mode: the correct password must be present in the password field (it is, since we're already unlocked). The backend re-validates before writing to storage.
- **Reveal Codes post-auth behavior:** If the user checks "Reveal Codes" after already having authenticated (unlocked state), a second password prompt appears. The password field must be re-entered and validated before codes are revealed.

---

## 11. Sidebar Panel — Slot Manager (Secure Mode, Codes Revealed)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  SECURE — Unlocked  [Lock Now]          Code lengths: Long 6 / Sh 4  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Password:  [ •••••••••• ]   [x] Reveal Codes  ← codes now visible below   ║
║                                                                              ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦═══╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  1 ║  [x]  ║  Master          ║  [ 847291 ]      ║  [ 2847 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ 391047 ]      ║  [ 3910 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  3 ║  [x]  ║  Guest           ║  [ 102938 ]      ║  [ 1029 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  4 ║  [x]  ║  Cleaner         ║  [ 774421 ]      ║  [ 7744 ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║  5 ║  [ ]  ║  Contractor      ║  [        ]      ║  [      ]     ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ .. ║  ...  ║  ...             ║  ...             ║  ...          ║ ? ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬═══╣
║ 19 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║ ? ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩═══╝

  [ ] Update All Slots                                          [ Exit ]
```

*(When edits are pending — dirty state:)*
```
  [ ] Update All Slots                          [ Discard ]  [ Save ]
```

**Notes:**
- Checking "Reveal Codes" triggers a second password validation call to the backend before revealing.
  - If password in field still matches: codes are decrypted and rendered in plaintext.
  - If something changed (timeout, session invalidated): error message and return to locked state.
- Unchecking "Reveal Codes" immediately replaces all code values with `******` again (no server round-trip needed; values stay in decrypted memory until Lock Now or panel close).
- Panel close / navigation away: decrypted values are wiped from frontend memory. Next open returns to Screen 9 (locked).
- The "Reveal Codes" revealed state looks identical to Open Mode (Screen 7) except for the password bar and Lock Now button at the top.
- Timeout: after a configurable inactivity period (default 5 minutes), the panel automatically returns to the locked state with a toast notification: "Session timed out. Please re-enter your password."

---

## 12. Sidebar Panel — Commit Status (In Progress)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  Open (codes visible)   Code lengths: Long 6-digit / Short 4-digit   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │  Committing changes...                                               │   ║
║  │                                                                      │   ║
║  │  [====================>                    ]  Saving to disk...      │   ║
║  │                                                                      │   ║
║  │  Back Door           ⟳  Pushing slot 3 (Guest)...                   │   ║
║  │  Master Bedroom      ●  Waiting...                                   │   ║
║  │  Utility Room        ●  Waiting...                                   │   ║
║  │  Office Door         ●  Waiting...                                   │   ║
║  │                                                                      │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
║                                                                              ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦══════╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ Stat ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  1 ║  [x]  ║  Master          ║  [ 847291 ]      ║  [ 2847 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ 391047 ]      ║  [ 3910 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  3 ║  [x]  ║  Guest           ║  [ 102938 ]      ║  [ 1029 ]     ║  ⟳   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  4 ║  [x]  ║  Cleaner         ║  [ 774421 ]      ║  [ 7744 ]     ║  ●   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  5 ║  [ ]  ║  Contractor      ║  [        ]      ║  [      ]     ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  6 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ .. ║  ...  ║  ...             ║  ...             ║  ...          ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ 19 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║  —   ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩══════╝

  [ ] Update All Slots           [ Exit ]  [ Save ]  ← both grayed during push
```

**Status Icon Legend:**
```
  ✓  = Synced to all locks (confirmed)
  ⟳  = Push in progress (spinner)
  ●  = Waiting / queued
  ✗  = Failed / error
  ⚠  = Uncertain (timed out — result unknown)
  —  = Not applicable (slot empty / not modified)
```

**Notes:**
- When Save is pressed, the slot grid enters a read-only push state. All inputs are disabled.
- A progress banner appears above the grid showing per-lock status and an overall progress bar.
- Saves to disk occur first (step 1 of commit flow). Progress bar fills to ~20% during disk write.
- After disk commit, locks are pushed one at a time in order. The progress banner updates per lock.
- The "Stat" column appears during and after a push operation. It is hidden in normal edit mode.
- The `⟳` spinner rotates while a lock push is in progress.
- `●` (filled circle) = queued / waiting to start.
- Both Exit and Save buttons are grayed and unclickable during the push operation to prevent interruption.

---

## 13. Sidebar Panel — Commit Status (Success)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  Open (codes visible)   Code lengths: Long 6-digit / Short 4-digit   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │  ✓  All slots committed successfully.                                │   ║
║  │                                                                      │   ║
║  │  [====================================]  Complete                    │   ║
║  │                                                                      │   ║
║  │  Back Door           ✓  4 slots synced, 0 errors                    │   ║
║  │  Master Bedroom      ✓  4 slots synced, 0 errors                    │   ║
║  │  Utility Room        ✓  4 slots synced, 0 errors                    │   ║
║  │  Office Door         ✓  4 slots synced, 0 errors                    │   ║
║  │                                                                      │   ║
║  │  Completed at 2:47 PM                                                │   ║
║  │                                                                      │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
║                                                                              ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦══════╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ Stat ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  1 ║  [x]  ║  Master          ║  [ 847291 ]      ║  [ 2847 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ 391047 ]      ║  [ 3910 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  3 ║  [x]  ║  Guest           ║  [ 102938 ]      ║  [ 1029 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  4 ║  [x]  ║  Cleaner         ║  [ 774421 ]      ║  [ 7744 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  5 ║  [ ]  ║  Contractor      ║  [        ]      ║  [      ]     ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ .. ║  ...  ║  ...             ║  ...             ║  ...          ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ 19 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║  —   ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩══════╝

  [ ] Update All Slots                                          [ Exit ]
```

**Notes:**
- Success state: all row Stat indicators show `✓`.
- After a successful commit there are no dirty rows, so only `[ Exit ]` is shown. If the user makes additional edits, Save + Discard reappear.
- The success banner auto-dismisses after ~10 seconds (or user can dismiss with an X button on the banner).
- After success, the post-commit popup (Screen 16) appears as an overlay (unless "Don't show this again" was previously checked).
- The banner remains visible even after dismiss (it becomes a smaller inline success indicator) until the next edit begins.

---

## 14. Sidebar Panel — Commit Status (Partial Failure)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  Open (codes visible)   Code lengths: Long 6-digit / Short 4-digit   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │  ⚠  Partial failure — some slots did not sync.                      │   ║
║  │                                                                      │   ║
║  │  [====================================]  Complete (with errors)      │   ║
║  │                                                                      │   ║
║  │  Back Door           ✓  4 slots synced, 0 errors                    │   ║
║  │  Master Bedroom      ✗  2 slots failed (slots 3, 4 — timeout)       │   ║
║  │  Utility Room        ⚠  1 slot uncertain (slot 3 — no ack)          │   ║
║  │  Office Door         ✓  4 slots synced, 0 errors                    │   ║
║  │                                                                      │   ║
║  │  Click [Save] to retry failed and uncertain slots only.             │   ║
║  │  (Attempt 1 of 3)                                                    │   ║
║  │                                                                      │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
║                                                                              ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦══════╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ Stat ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  1 ║  [x]  ║  Master          ║  [ 847291 ]      ║  [ 2847 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ 391047 ]      ║  [ 3910 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  3 ║  [x]  ║  Guest           ║  [ 102938 ]      ║  [ 1029 ]     ║  ✗   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  4 ║  [x]  ║  Cleaner         ║  [ 774421 ]      ║  [ 7744 ]     ║  ⚠   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  5 ║  [ ]  ║  Contractor      ║  [        ]      ║  [      ]     ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ .. ║  ...  ║  ...             ║  ...             ║  ...          ║  —   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ 19 ║  [ ]  ║                  ║  [        ]      ║  [      ]     ║  —   ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩══════╝

  [ ] Update All Slots                          [ Exit ]  [ Save ]
```

**Notes:**
- Rows 3 and 4 have error/uncertain status — their row backgrounds are tinted red/orange respectively.
- The Stat column shows per-slot aggregate status across all locks. A slot is `✗` if any lock failed; `⚠` if any lock is uncertain (timed out); `✓` only if all locks confirmed success.
- Banner shows attempt count: "(Attempt 1 of 3)". User presses Save to retry.
- On retry, Save only pushes slots with `out_of_sync` or `uncertain` state in the lock commit arrays — it does not re-push already-synced slots.
- After retry attempt 2: attempt counter becomes "(Attempt 2 of 3)".
- If the user presses Exit during a partial failure state, a warning dialog appears: "Some slots are not yet synced. Are you sure you want to exit? You can retry on next visit. [Go Back] [Exit Anyway]"

---

## 15. Sidebar Panel — Commit Status (Escalated Failure)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SlotSentry — Slot Manager                                    v1.0.0        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Locks: Back Door • Master Bedroom • Utility Room • Office Door              ║
║  Mode:  Open (codes visible)   Code lengths: Long 6-digit / Short 4-digit   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │  ✗  Persistent failure — manual intervention required.              │   ║
║  │                                                                      │   ║
║  │  Master Bedroom failed after 3 attempts.                            │   ║
║  │                                                                      │   ║
║  │  Recommended steps:                                                  │   ║
║  │   1. Close and reopen the SlotSentry panel, then try again.         │   ║
║  │   2. Reboot Home Assistant if the problem continues.                │   ║
║  │   3. Last resort: Reconfigure → remove this lock → save →           │   ║
║  │      re-add lock → check Update All Slots → Save.                   │   ║
║  │                                                                      │   ║
║  │  Your code data is safe — it was written to disk before pushing     │   ║
║  │  began. No data has been lost.                                      │   ║
║  │                                                                      │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
║                                                                              ║
╠════╦═══════╦══════════════════╦══════════════════╦═══════════════╦══════╣
║  # ║  On?  ║  Label           ║  Long Code       ║  Short Code   ║ Stat ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  1 ║  [x]  ║  Master          ║  [ 847291 ]      ║  [ 2847 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  2 ║  [ ]  ║  Dog Sitter      ║  [ 391047 ]      ║  [ 3910 ]     ║  ✓   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  3 ║  [x]  ║  Guest           ║  [ 102938 ]      ║  [ 1029 ]     ║  ✗   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║  4 ║  [x]  ║  Cleaner         ║  [ 774421 ]      ║  [ 7744 ]     ║  ✗   ║
╠════╬═══════╬══════════════════╬══════════════════╬═══════════════╬══════╣
║ .. ║  ...  ║  ...             ║  ...             ║  ...          ║  —   ║
╚════╩═══════╩══════════════════╩══════════════════╩═══════════════╩══════╝

  [ ] Update All Slots                   [ ~~Save~~ (grayed) ]  [ Exit ]
```

**Notes:**
- After 3 consecutive failed attempts for the same lock/slot, the Save button is grayed and disabled. Only Exit remains active.
- The button tooltip (hover) on the grayed Save repeats: "Close the panel and reopen it to reset and try again."
- The failure banner now shows recovery steps in numbered order. Steps are actionable — step 3 mentions Reconfigure flow as last resort.
- All code data is confirmed written to disk (step 1 of commit flow completes before any lock pushing). The banner explicitly reassures the user their data is not lost.
- When the panel is next opened (after closing from this state), the integration checks lock commit arrays for `out_of_sync` / `uncertain` slots and automatically attempts to re-push them (on-open sync attempt). This resets the attempt counter.

---

## 16. Post-Commit Popup

```
                 ┌──────────────────────────────────────────┐
                 │                                          │
                 │   Codes Updated — Test Your Locks        │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   We recommend testing each updated      │
                 │   code on the physical lock to confirm   │
                 │   it works before relying on it.         │
                 │                                          │
                 │   Codes that fail to unlock may          │
                 │   indicate a Z-Wave communication        │
                 │   issue. Come back in, verify codes,     │
                 │   check Update All Slots, and press      │
                 │   Save to re-push all codes.             │
                 │                                          │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   [ ] Don't show this again              │
                 │                                          │
                 │                            [  OK  ]      │
                 │                                          │
                 └──────────────────────────────────────────┘
```

**Notes:**
- Appears as a modal overlay centered on the sidebar panel after a fully successful commit.
- Does NOT appear after a partial failure (failure state is already visible in the panel).
- "Don't show this again" state is stored in `.storage/slotsentry` per user (or per config entry if multi-user support is out of scope for MVP).
- Clicking OK or pressing Escape dismisses the popup. Checking "Don't show this again" before OK suppresses future appearances.
- The popup is not shown if the user already checked "Don't show this again" in a previous session.
- If the user returns to the panel without making any changes, only `[ Exit ]` is shown (no dirty state). The popup message above suggests: if a code doesn't work, come back in, verify codes, check "Update All Slots", and press Save to re-push all codes to all locks.
- (Future consideration: per-lock commit for targeted troubleshooting.)

---

## 17. Secure Mode Setup Dialog

Shown inside the HA Reconfigure flow (Settings → Integrations → SlotSentry → Configure). This dialog is NOT inside the sidebar panel — it appears as a step in the standard HA config flow when Secure Mode checkbox is checked in Reconfigure, or during initial setup if Secure Mode is selected:

```
                 ┌──────────────────────────────────────────┐
                 │                                          │
                 │   Enable Secure Mode                     │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   ⚠  Read this before continuing:        │
                 │                                          │
                 │   Secure Mode encrypts all stored PIN    │
                 │   codes using your password as the       │
                 │   encryption key.                        │
                 │                                          │
                 │   IMPORTANT:                             │
                 │   • Your password cannot be recovered.   │
                 │   • If you forget it, all stored code    │
                 │     data is PERMANENTLY LOST and you     │
                 │     must re-enter all codes from         │
                 │     scratch.                             │
                 │   • SlotSentry does NOT store your       │
                 │     password anywhere.                   │
                 │                                          │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   Create password (8-16 characters):     │
                 │   ┌──────────────────────────────────┐   │
                 │   │  ••••••••••                      │   │
                 │   └──────────────────────────────────┘   │
                 │                                          │
                 │   Confirm password:                      │
                 │   ┌──────────────────────────────────┐   │
                 │   │  ••••••••••                      │   │
                 │   └──────────────────────────────────┘   │
                 │                                          │
                 │   Password strength:  [====------]  Fair │
                 │                                          │
                 │   ✓ Passwords match                      │
                 │                                          │
                 │              [ Cancel ]  [ Continue ]    │
                 │                                          │
                 └──────────────────────────────────────────┘
```

**Validation states shown inline (examples):**

```
   Password strength:  [----------]  (empty — type a password)

   Password strength:  [===-------]  Too short (min 8 chars)
   ✗ Must be at least 8 characters

   Password strength:  [======----]  Fair
   ✓ Passwords match

   Password strength:  [=========]  Strong
   ✓ Passwords match

   Password strength:  [====------]  Fair
   ✗ Passwords do not match
```

**Notes:**
- Minimum length: 8 characters. Maximum: 16 characters.
- Password strength meter is visual feedback only — no minimum strength required (length is the only enforced rule).
- "Passwords match" indicator only appears once the confirm field has any content.
- "Continue" is disabled until both passwords are non-empty, match, and are 8-16 characters.
- "Cancel" returns to the previous config flow step without enabling Secure Mode.
- On "Continue": the password is used to derive an encryption key (e.g., PBKDF2), existing plain slot data is encrypted, and the config entry is updated with Secure Mode = ON.
- The password field uses `type="password"` (browser-native masking). No show/hide toggle is provided in this dialog (for security).
- IMPORTANT: This dialog appears within the HA Reconfigure flow (Settings → Integrations → SlotSentry → Configure), NOT inside the sidebar panel.

---

## 18. Password Recovery Dialog

Shown after N consecutive failed password attempts (default threshold: 5):

```
                 ┌──────────────────────────────────────────┐
                 │                                          │
                 │   Access Locked                          │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   Too many failed password attempts      │
                 │   (5 of 5 used).                         │
                 │                                          │
                 │   If you remember your password, close   │
                 │   and reopen the panel to try again      │
                 │   (attempt counter resets on reopen).    │
                 │                                          │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   Forgotten your password?               │
                 │                                          │
                 │   You can create a new password, but     │
                 │   ALL stored code data will be           │
                 │   permanently deleted and must be        │
                 │   re-entered from scratch.               │
                 │                                          │
                 │   This action cannot be undone.          │
                 │                                          │
                 │       [ Cancel ]  [ Create New Password ]│
                 │                                          │
                 └──────────────────────────────────────────┘
```

**"Create New Password" confirmation step:**

```
                 ┌──────────────────────────────────────────┐
                 │                                          │
                 │   Confirm Data Reset                     │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   Are you absolutely sure?               │
                 │                                          │
                 │   Clicking Confirm will:                 │
                 │   • Delete all stored slot data          │
                 │   • Remove all code entries              │
                 │   • Reset SlotSentry to empty state      │
                 │                                          │
                 │   Your locks will NOT be automatically   │
                 │   cleared — existing codes on the        │
                 │   physical locks remain until you        │
                 │   explicitly overwrite or clear them     │
                 │   via Save.                              │
                 │                                          │
                 │     [ Go Back ]  [ Confirm — Erase All ] │
                 │                                          │
                 └──────────────────────────────────────────┘
```

**After confirmation — New Password entry:**

```
                 ┌──────────────────────────────────────────┐
                 │                                          │
                 │   Set New Password                       │
                 │  ─────────────────────────────────────   │
                 │                                          │
                 │   All previous data has been erased.     │
                 │   Set a new password to continue.        │
                 │                                          │
                 │   New password (8-16 characters):        │
                 │   ┌──────────────────────────────────┐   │
                 │   │  ••••••••••••                    │   │
                 │   └──────────────────────────────────┘   │
                 │                                          │
                 │   Confirm password:                      │
                 │   ┌──────────────────────────────────┐   │
                 │   │  ••••••••••••                    │   │
                 │   └──────────────────────────────────┘   │
                 │                                          │
                 │   ✓ Passwords match                      │
                 │                                          │
                 │                        [  Save  ]        │
                 │                                          │
                 └──────────────────────────────────────────┘
```

**Notes:**
- The attempt counter is stored in `.storage/slotsentry` and persists across browser sessions and HA restarts.
- Closing and reopening the panel resets the attempt counter — this is by design (prevents brute-force lock-out without true data loss).
- The threshold (default 5) is a config option not exposed in the UI — set in `const.py` or similar.
- "Cancel" on the first dialog closes the dialog and returns to the locked panel (Screen 9), with the attempt counter NOT reset.
- "Create New Password" → "Confirm — Erase All" triggers an irreversible backend call that: (1) wipes `.storage/slotsentry` slot data, (2) destroys the encryption key, (3) reinitializes with empty slots (count based on managed locks).
- The note "Your locks will NOT be automatically cleared" is critical UX — the user must be aware their physical locks still have the old codes.

---

## 19. Help Popup (? Button)

### Variant A — Two Code Lengths Mode

```
     ┌────────────────────────────────────────────────────────┐
     │                                                        │
     │   About Long and Short Codes                      [X]  │
     │  ─────────────────────────────────────────────────     │
     │                                                        │
     │   SlotSentry is configured to manage two PIN           │
     │   lengths simultaneously.                              │
     │                                                        │
     │   Long Code  (6 digits)                                │
     │   ─────────────────────                                │
     │   Pushed to locks that accept 6-digit PINs.           │
     │   Example: Schlage BE469ZP deadbolt (configurable      │
     │   4-8 digits, set to 6).                               │
     │                                                        │
     │   Short Code  (4 digits)                               │
     │   ──────────────────────                               │
     │   Pushed to locks with fixed 4-digit keypads.          │
     │   Example: Schlage FE599 interior lock (fixed          │
     │   4 digits only).                                      │
     │                                                        │
     │   Tip: Use the same numeric sequence where possible    │
     │   so users only have to remember one code pattern.     │
     │   Example — Long: 847291, Short: 8472 (first 4 of 6)  │
     │                                                        │
     │   If a slot has only one code type filled in, the      │
     │   other code field is skipped for the locks that       │
     │   would use it. Leaving a field blank effectively      │
     │   clears that lock type for the slot.                  │
     │                                                        │
     │                                        [  Got it  ]    │
     │                                                        │
     └────────────────────────────────────────────────────────┘
```

### Variant B — Single Code Length Mode

```
     ┌────────────────────────────────────────────────────────┐
     │                                                        │
     │   About PIN Codes                                 [X]  │
     │  ─────────────────────────────────────────────────     │
     │                                                        │
     │   SlotSentry is configured for a single code           │
     │   length (6 digits).                                   │
     │                                                        │
     │   The same 6-digit code is pushed to all managed       │
     │   locks when a slot is enabled and saved.              │
     │                                                        │
     │   Note: All of your locks must accept 6-digit PINs    │
     │   for this to work correctly. If some locks only       │
     │   accept 4-digit PINs, consider enabling the           │
     │   "Two code lengths" option in Reconfigure.            │
     │                                                        │
     │   Slot states:                                         │
     │   • Enabled  + Code entered  →  code pushed to locks  │
     │   • Disabled + Code retained →  code cleared on locks │
     │   • Enabled  + Empty code    →  treated as disabled   │
     │                                                        │
     │                                        [  Got it  ]    │
     │                                                        │
     └────────────────────────────────────────────────────────┘
```

**Notes:**
- The `?` button appears at the end of each row in the slot grid. Every row has the same `?` — it opens the same global help popup (not per-row).
- Popup is a lightweight tooltip-style modal, not a full dialog. Clicking anywhere outside it, pressing Escape, or clicking `[X]` or "Got it" dismisses it.
- Content adapts based on whether two code lengths or single code length is configured (Variant A vs B).
- The code length values shown in the popup (e.g., "6 digits", "4 digits") are dynamically pulled from the integration config — they update automatically if lengths change in Reconfigure.
- The "Tip" in Variant A (use first N digits of the long code as the short code) is a user-experience suggestion, not enforced by the system.

---

## Appendix — Slot Row State Reference

The following shows how a single row appears in each state:

```
  State: Empty (no label, no code, disabled)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬───┐
  │  6 │  [ ]  │                  │  [        ]      │  [      ]     │ ? │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴───┘
  Row styling: normal (white background)

  State: Populated and enabled
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬───┐
  │  1 │  [x]  │  Master          │  [ 847291 ]      │  [ 2847 ]     │ ? │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴───┘
  Row styling: normal

  State: Populated but disabled (codes retained, cleared from locks)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬───┐
  │  2 │  [ ]  │  Dog Sitter      │  [ 391047 ]      │  [ 3910 ]     │ ? │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴───┘
  Row styling: dimmed (gray text, slightly grayed background)

  State: Dirty (user has edited but not yet saved)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬───┐
  │  3 │  [x]  │  Guest       *   │  [ 112233 ]  *   │  [ 1122 ]  *  │ ? │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴───┘
  Row styling: amber/yellow tint background; asterisk (*) marks dirty fields

  State: Currently being pushed (commit in progress)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬──────┐
  │  3 │  [x]  │  Guest           │  [ 112233 ]      │  [ 1122 ]     │  ⟳  │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴──────┘
  Row styling: inputs disabled (read-only), spinner in Stat column

  State: Synced (commit success)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬──────┐
  │  3 │  [x]  │  Guest           │  [ 112233 ]      │  [ 1122 ]     │  ✓  │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴──────┘
  Row styling: normal

  State: Failed (commit error)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬──────┐
  │  3 │  [x]  │  Guest           │  [ 112233 ]      │  [ 1122 ]     │  ✗  │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴──────┘
  Row styling: light red tint background

  State: Uncertain (timed out, result unknown)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬──────┐
  │  3 │  [x]  │  Guest           │  [ 112233 ]      │  [ 1122 ]     │  ⚠  │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴──────┘
  Row styling: light orange tint background

  State: Needs attention (flagged out-of-sync on panel open)
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬──────┐
  │  3 │  [x]  │  Guest       !   │  [ 112233 ]   !  │  [ 1122 ]  !  │  ⚠  │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴──────┘
  Row styling: orange tint background; ! marks fields that are out-of-sync
  A banner at top of panel explains: "Some slots were not fully synced last time.
  Auto-retry in progress..."

  State: Secure mode — unlocked, codes hidden
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬───┐
  │  1 │  [x]  │  Master          │  [ ****** ]      │  [ **** ]     │ ? │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴───┘
  Row styling: normal; code fields show asterisks, not editable without reveal

  State: Secure mode — codes revealed
  ┌────┬───────┬──────────────────┬──────────────────┬───────────────┬───┐
  │  1 │  [x]  │  Master          │  [ 847291 ]      │  [ 2847 ]     │ ? │
  └────┴───────┴──────────────────┴──────────────────┴───────────────┴───┘
  Row styling: normal; identical to open mode
```

---

## Appendix — Commit Flow State Diagram (Text)

```
  User presses [Save]
          │
          v
  [1] Write to disk (.storage/slotsentry)
      Mark all pushed slots as out_of_sync on lock commit arrays
          │
          v
  [2] For each managed lock (in sequence):
      │
      ├─> Push changed slots to lock via zwave_js.set_lock_usercode
      │       (or zwave_js.clear_lock_usercode for disabled slots)
      │
      ├─> Verify: invoke_cc_api get → check occupied/available
      │       BE469ZP: can verify actual code value
      │       FE599:   can only verify occupied/available
      │
      ├─> Update lock commit array:
      │       verified OK       → synced
      │       verify failed     → out_of_sync
      │       timeout (>60s)    → uncertain
      │
      └─> Persist lock commit array to disk, continue to next lock
          │
          v
  [3] All locks done:
      │
      ├─ All synced?        → SUCCESS banner + post-commit popup
      │
      └─ Any out_of_sync or uncertain?
              │
              ├─ Attempt < 3? → PARTIAL FAILURE banner + retry offered
              │
              └─ Attempt = 3? → ESCALATED FAILURE + Save button grayed
                                 + recovery instructions shown

  [On next panel open if any out_of_sync or uncertain remain]:
      → Auto-retry affected slots (resets attempt counter)
      → Visual "needs attention" indicators on affected rows
```

---

*End of UI Mockups — Revision 1.1*
