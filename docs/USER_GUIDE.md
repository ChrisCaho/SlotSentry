# SlotSentry User Guide

**Revision: 1.1**

Complete walkthrough for installing, configuring, and using SlotSentry to manage Z-Wave lock access codes in Home Assistant.

## Table of Contents

1. [Installation](#installation)
2. [Initial Setup](#initial-setup)
3. [Using the Slot Manager](#using-the-slot-manager)
4. [Managing Codes](#managing-codes)
5. [Understanding Commit Status](#understanding-commit-status)
6. [Secure Mode Setup](#secure-mode-setup)
7. [Keypad Lockout Configuration](#keypad-lockout-configuration)
8. [Troubleshooting](#troubleshooting)
9. [FAQ](#faq)

## Installation

### Step 1: Add the Custom Repository

1. Open Home Assistant and navigate to **Settings** (bottom left)
2. Click **Devices & Services**
3. Click the **HACS** option in the left sidebar (if not visible, install HACS first)
4. Click the menu icon (three horizontal lines) in the top right corner
5. Select **Custom repositories**
6. In the dialog box, enter:
   - Repository URL: `https://github.com/ChrisCaho/SlotSentry`
   - Category: **Integration**
7. Click **Create**

You should see a success message confirming the repository was added.

### Step 2: Install SlotSentry

1. In HACS, click **Integrations** in the left sidebar
2. Click the search icon and search for "SlotSentry"
3. Click the SlotSentry entry
4. Click **Install** (or **Upgrade** if updating)
5. A notification appears: "Restart required to load"
6. Click **Restart** or wait for Home Assistant to restart automatically (within a few minutes)

After restart, SlotSentry is ready to configure.

### Step 3: Verify Z-Wave JS Integration

Before setting up SlotSentry, ensure your locks are properly integrated:

1. Navigate to **Settings > Devices & Services > Integrations**
2. Look for **Z-Wave JS** in the list
3. Click it to view your Z-Wave network status
4. Verify all locks appear in the device list with green status indicators
5. If a lock shows gray or offline, check:
   - Lock has fresh batteries
   - Lock is within Z-Wave mesh range
   - Z-Wave JS add-on is running

If locks are not showing, troubleshoot Z-Wave connectivity before proceeding to SlotSentry setup.

## Initial Setup

### Step 1: Create the Integration

1. Navigate to **Settings > Devices & Services > Integrations**
2. Click **Add Integration** (the **+** button at the bottom right)
3. Search for "SlotSentry"
4. Click **SlotSentry** from the results
5. Click **Create**

The configuration flow begins.

### Step 2: Select Locks (First Screen)

The first configuration screen shows all available Z-Wave locks:

**Available Locks:**
- Each lock is listed with its Z-Wave JS entity ID (e.g., `lock.back_door_deadbolt`)
- A checkbox next to each lock lets you select which locks to manage

**Recommended approach:**
1. Check all locks you want SlotSentry to manage
2. Leave unchecked any locks you manage manually or via other integrations
3. Click **Next**

**Note:** You can add or remove locks later via reconfiguration. The number of available slots is determined by the lock with the smallest slot capacity among your selected locks.

### Step 3: Configure Code Lengths (Second Screen)

SlotSentry auto-detects code lengths supported by your locks and suggests appropriate defaults. This screen determines how many code fields appear per slot in the Slot Manager UI:

**Option A: Single Code Length**
- Choose this if all your locks use the same code length
- Enter the code length: 4–8 digits (suggested default based on your locks, typically 6)
- Each slot will show one **Code** field

**Option B: Two Code Lengths (Mixed)**
- Choose this if some locks use different code lengths (e.g., 4-digit and 6-digit)
- **Short Code Length:** 4–7 digits (suggested default: 4)
- **Long Code Length:** 5–8 digits (suggested default: 6)
- Each slot will show separate **Long Code** and **Short Code** fields
- Useful for households with both Schlage FE599 locks (4-digit fixed) and BE469ZP locks (6-digit configurable)

If code lengths cannot be discovered automatically, SlotSentry defaults to 4/6 (two lengths) or 6 (single length).

Click **Next** when you've made your selection.

### Step 4: Secure Mode (Third Screen) [Optional]

**Secure Mode** encrypts all slot data with a password. Only enable if you want codes encrypted on disk:

**If enabling Secure Mode:**
1. Check the **Enable Secure Mode** checkbox
2. A warning appears: "All slot data will be encrypted using AES-256. Your password is the encryption key. If you forget the password, data cannot be recovered."
3. Create a strong password (8–16 characters, recommended: 12+ with mixed case and numbers)
4. **Confirm Password:** Re-enter the password to verify
5. Click **Next**

**If not using Secure Mode:**
- Leave the checkbox unchecked
- Codes are stored in plain text in `.storage/slotsentry`
- Sidebar panel shows codes in clear text (no asterisks)
- Click **Next**

**When to enable Secure Mode:**
- Shared Home Assistant admin account
- Multi-tenant or shared HA instance
- Compliance/audit requirements

**When to skip Secure Mode:**
- Single-user HA instance
- Family-only setup
- Simpler UX (no password prompts)

### Step 5: Keypad Lockout Configuration (Fourth Screen) [Optional]

Enable keypad lockout to disable lock keypads when a monitored sensor reaches a target state:

**If enabling Keypad Lockout:**

1. **Select Trigger Sensor:** Click the field and choose any Home Assistant entity (e.g., `alarm_control_panel.alarm` or `binary_sensor.anyone_home`)

2. **Target State:** Select the state that should trigger lockout (e.g., "armed_home" for alarm, "off" for presence, "true" for any binary sensor)

3. **Participating Locks:** Below the sensor selection, checkboxes appear for each lock:
   - Check locks that should have keypads disabled when the trigger activates
   - Uncheck locks that should remain accessible (e.g., interior doors during alarm armed)

4. Click **Finish**

**Example Scenarios:**

| Sensor | Target State | Locks | Behavior |
|--------|--------------|-------|----------|
| `alarm_control_panel.alarm` | `armed_home` | Back Door, Garage Door | Keypads disabled when alarm is armed home; re-enabled when disarmed |
| `binary_sensor.anyone_home` | `false` | All exterior locks | Keypads disabled when no one is home; re-enabled when someone arrives |
| `input_boolean.guest_mode` | `on` | Kitchen Door | Keypad disabled during guest mode for maximum security |

**Important Notes:**
- Keypad lockout does NOT clear codes—codes remain on the lock
- Re-enabling the keypad requires no manual action from SlotSentry
- Codes work when keypad is enabled, are ignored when keypad is disabled
- Can be combined with per-slot code enabling/disabling for layered security

### Step 6: Finish

After the final screen, click **Finish**. SlotSentry is now active:

- The **SlotSentry** sidebar item appears in the left menu
- Four new entities are created:
  - `sensor.slotsentry_push_status`
  - `binary_sensor.slotsentry_suppressed`
  - `button.slotsentry_push_all`
  - `button.slotsentry_retry`
- No default codes are loaded; the grid starts empty

## Using the Slot Manager

### Accessing the Sidebar Panel

1. Open Home Assistant
2. Look for **SlotSentry** in the left sidebar (below the main menu items)
3. Click it to open the Slot Manager sidebar panel

If SlotSentry doesn't appear:
- Restart Home Assistant (`Settings > System > Restart`)
- Clear browser cache (Ctrl+Shift+Delete or Cmd+Shift+Delete on Mac)
- Check that the integration finished setup with no errors

### Panel Layout (Open Mode)

In open mode (secure mode disabled), you see:

```
┌─────────────────────────────────────────────────┐
│  SlotSentry - Slot Manager                      │
├─────────────────────────────────────────────────┤
│  Slot │ Enable │ Label       │ Code              │
├─────────────────────────────────────────────────┤
│  1    │ [ ]    │ [________]  │ [______]          │
│  2    │ [ ]    │ [________]  │ [______]          │
│  3    │ [✓]    │ [Owner____] │ [123456]          │
│  ...  │ ...    │ ...         │ ...               │
├─────────────────────────────────────────────────┤
│  Update All Slots: [ ]                          │
│                            [Save]               │
│  Push Status: All Synced                        │
└─────────────────────────────────────────────────┘
```

The number of slot rows matches the slot capacity of the lock with the smallest capacity among your configured locks. This is established at integration setup time.

**Columns:**
- **Slot** — Fixed slot number (1 through available count)
- **Enable** — Checkbox to enable/disable this slot on locks
- **Label** — Optional description (e.g., "Dog Sitter", "Contractor")
- **Code** — The access code (single field in single code mode)

If two code lengths are configured, you see **Long Code** and **Short Code** fields instead of one **Code** field.

### Button Flow

The panel uses three action buttons depending on context:

- **Exit** — Shown when the panel is first opened (no unsaved changes). Closes the panel.
- **Save** — Shown after you make changes. Commits changes to disk and pushes codes to locks.
- **Discard** — Shown alongside Save when you have unsaved changes. Reverts all edits since the last save.
- **Exit** — Shown again after a successful Save (no pending changes).

### Panel Layout (Secure Mode)

In secure mode, the panel starts locked:

```
┌─────────────────────────────────────────────────┐
│  SlotSentry - Slot Manager (Locked)            │
├─────────────────────────────────────────────────┤
│  Unlock with Password:                          │
│  [___________________]  [Reveal Codes]         │
│                                  (grayed out)   │
├─────────────────────────────────────────────────┤
│  Enter your password to view and edit codes.   │
│  Push Status: All Synced                        │
└─────────────────────────────────────────────────┘
```

**To unlock:**
1. Type your secure mode password in the field (8+ characters)
2. The **Reveal Codes** checkbox activates when 8+ characters are entered
3. Once unlocked, the slot grid appears
4. Codes are displayed as asterisks (`***`) by default
5. Check **Reveal Codes** to temporarily show actual codes (requires re-entering password)

**After unlocking:**
- Codes remain asterisks on screen for security while editing
- To see a specific code, check **Reveal Codes**—you'll be prompted for your password again
- After you click away, codes return to asterisks automatically

## Managing Codes

### Adding a New Code

1. Open the Slot Manager
2. Find an empty slot (one with no label and empty code field)
3. **Label** — Type a description (e.g., "Housekeeper", "Plumber", "Guest #1")
   - Labels are optional but recommended for organization
   - Labels are stored plain text (even in secure mode)
4. **Code** — Enter the access code
   - Respect the configured code length (e.g., 4 digits or 6 digits)
   - Do not include dashes or spaces (e.g., enter "123456", not "1234-56")
5. **Enable Checkbox** — Should be checked by default for new codes
6. Scroll to the bottom
7. Click **Save**
8. Watch the **Push Status** indicator:
   - **Syncing...** — Codes are being pushed to locks
   - **All Synced** — Codes are now active on all locks
   - **Out of Sync / Error** — See [Understanding Commit Status](#understanding-commit-status)
9. Test the code at your lock to confirm it works

**Verification:**
After a successful push, try unlocking the door with the new code. Lights or sounds should indicate success. If the code doesn't work:
- Check that the code was entered without errors (no extra spaces)
- Check that the lock is online (green indicator in Z-Wave JS UI)
- Check the **Push Status** for error details
- Try pressing the **Retry** button and testing again

### Editing a Code

1. Open the Slot Manager
2. Find the slot with the code you want to change
3. Update the **Label** or **Code** field
4. Keep the **Enable** checkbox checked (unless you want to disable temporarily)
5. Click **Save**
6. Wait for the status to show **All Synced**

**Important:** Editing a code replaces the old code on all locks. Anyone with the old code can no longer unlock.

### Disabling a Code Temporarily

Perfect for temporary access that might be needed again:

1. Find the slot with the code you want to disable
2. **Uncheck** the **Enable** checkbox
3. Leave the label and code in place (they're preserved)
4. Click **Save**
5. Wait for the status to show **All Synced**
6. The code is now cleared from all locks

**The code is retained on disk.** To re-enable it later:
1. Find the same slot
2. **Check** the **Enable** checkbox
3. Click **Save**
4. The code is pushed back to all locks

This is much faster than re-typing codes for recurring access (dog sitter visits, seasonal contractors).

### Clearing a Code Permanently

1. Find the slot with the code you want to remove
2. Clear the **Label** field (optional)
3. Clear the **Code** field
4. **Uncheck** the **Enable** checkbox
5. Click **Save**
6. The slot is now empty and reusable

**Alternatively,** keep an empty disabled slot as a placeholder if you think you might re-enable it.

### Working with Mixed Code Lengths

If your SlotSentry is configured with two code lengths (e.g., 4-digit and 6-digit):

**Per-Slot Code Assignment:**
- **Long Code Field** — For locks that require longer codes (e.g., 6 digits)
- **Short Code Field** — For locks that require shorter codes (e.g., 4 digits)
- **Slot Pattern:** One access identity, two codes

**Example:** Set up a "Contractor" slot
- **Label:** Contractor
- **Long Code:** 987654 (for 6-digit locks like BE469ZP)
- **Short Code:** 9876 (for 4-digit locks like FE599)
- **Enable:** Checked
- When you save, SlotSentry pushes:
  - 987654 to all BE469ZP locks
  - 9876 to all FE599 locks
  - Same person (contractor) uses their assigned code at each lock

**Leaving a Field Empty:**
- If a slot doesn't need both code lengths, leave one field empty
- SlotSentry skips pushing that field to locks
- Useful for person-specific access needs

### Bulk Update Mode

The **Update All Slots** checkbox at the bottom of the panel overrides per-slot change tracking:

**Normal Mode (unchecked):**
- SlotSentry tracks which slots you changed
- Only changed slots are pushed to locks
- Fast and efficient

**Bulk Update Mode (checked):**
- All slots are pushed to all locks, whether you changed them or not
- Useful if you suspect out-of-sync state
- Slower but comprehensive
- Use sparingly; it generates more Z-Wave traffic

**When to use Bulk Update:**
- A lock was offline and now is back online
- You manually changed codes via the Z-Wave JS UI
- You want to guarantee all locks have the same codes

## Understanding Commit Status

SlotSentry tracks whether codes on your locks match what you intended. The **Push Status** sensor shows the current state:

### Status Indicators

**All Synced**
- Your codes match the intended state on all locks
- No action needed
- Codes are saved on disk and confirmed on locks

**Syncing...**
- SlotSentry is currently pushing codes to one or more locks
- Do not edit codes or close the sidebar panel while syncing
- This phase typically takes 10–30 seconds depending on the number of locks

**Out of Sync**
- One or more locks have not been updated with your latest code changes
- This happens when:
  - A lock was offline when you pressed Save
  - A push timed out
  - Verification failed (code didn't match after push)
- **Action:** Press the **Retry** button to re-attempt the push, or click **Save** again
- If the lock comes back online, SlotSentry will automatically detect and retry out-of-sync slots next time you open the panel

**Error**
- A push operation failed with an error (e.g., lock rejected the code format)
- Details appear in the status field
- Common errors:
  - "Code too short" — Code length doesn't match lock requirements
  - "Invalid code" — Lock rejected the code (e.g., code contains invalid characters)
  - "Lock unreachable" — Lock is offline; will retry automatically when online
- **Action:** Check the error message, fix the code if needed, and press **Save** again

### Verification Process

After pushing a code to a lock, SlotSentry verifies success by checking:

1. **Code Readback** (for locks that support it, like BE469ZP)
   - SlotSentry reads back the actual code and compares it to what was intended
   - Most reliable verification method

2. **Slot Occupancy** (for all locks)
   - SlotSentry checks whether the slot is "occupied" or "available"
   - Confirms the code was stored without confirming the exact code

3. **Supervision Result** (if available)
   - The lock's response to the set command
   - Indicates whether the lock acknowledged the write

If any verification fails, SlotSentry marks the slot as `out_of_sync` and suggests retry.

### Automatic Retry

SlotSentry automatically retries failed pushes in these scenarios:

- **Lock comes back online** — When you open the Slot Manager again, it detects out-of-sync slots and retries automatically
- **Manual retry** — Press the **Retry** button to immediately re-push out-of-sync slots
- **Re-save** — Clicking **Save** again re-pushes all changed slots

### Timeout Handling

Each lock operation has a **1-minute timeout**:

- If a lock doesn't respond within 1 minute, SlotSentry marks the slot as `uncertain` (doesn't know if it succeeded)
- The slot is added to the retry queue
- Next time you open the panel or press **Retry**, SlotSentry re-attempts the uncertain slots

If a lock repeatedly times out:
1. Check lock batteries (low battery = slow response)
2. Check lock distance from Z-Wave mesh
3. Restart the Z-Wave JS add-on
4. If still failing, consider removing and re-adding the lock in Z-Wave JS

## Secure Mode Setup

Secure mode encrypts all slot data (labels, codes, enable/disable state) using AES-256 encryption.

### Enabling Secure Mode

Secure mode must be enabled during initial setup or via reconfiguration. **It cannot be toggled from the sidebar panel.**

**During Initial Setup:**
1. On the "Secure Mode" configuration screen, check **Enable Secure Mode**
2. Create a strong password (8–16 characters)
3. Confirm the password
4. Click **Next** and finish setup

**Via Reconfiguration (if not initially set):**
1. Go to **Settings > Devices & Services > Integrations**
2. Find **SlotSentry**, click the menu (three dots)
3. Click **Reconfigure**
4. On the "Secure Mode" screen, check **Enable Secure Mode**
5. Create your password, confirm, and finish

### Using Secure Mode in the Sidebar Panel

**Unlocking the Panel:**
1. Open the SlotSentry sidebar panel
2. Type your password in the top field
3. Once you've typed 8+ characters, SlotSentry validates your password
4. The slot grid appears (codes shown as asterisks)

**Viewing Codes:**
- By default, codes appear as asterisks (`***`) for security
- To temporarily reveal codes:
  1. Check the **Reveal Codes** checkbox
  2. You'll be prompted to re-enter your password
  3. Codes become visible
  4. After a timeout or navigation, codes return to asterisks

**Editing Codes:**
- You can edit codes while they're shown as asterisks (asterisks are just display obfuscation)
- Type new codes in the asterisk fields
- The new code is encrypted when saved

### Secure Mode Best Practices

**Password Strength:**
- Use 12+ characters for maximum security
- Mix uppercase, lowercase, numbers, and symbols
- Do not use personal information (birthdays, names, addresses)
- Do not reuse passwords from other services

**Backup:**
- SlotSentry does NOT back up or export encrypted data
- If you forget your password, all slot data is unrecoverable
- Before enabling secure mode, consider manually exporting your codes to a secure location
- Home Assistant's built-in backup feature backs up encrypted data but does not backup your password

**Password Recovery:**
- If you forget your secure mode password:
  1. SlotSentry detects repeated failed attempts
  2. A reconfiguration option appears: "Reset Secure Mode Password"
  3. You can set a new password
  4. **Warning:** This action reinitializes all slots (clears all data)

**Shared HA Admin Account:**
- If multiple people have HA admin access, all have access to the SlotSentry password if they reconfigure the integration
- For multi-user setups, consider:
  - Separate SlotSentry instances per user (via subfolders in `.storage`)
  - YAML-based code management as an alternative
  - Documenting who has access to what

### Disabling Secure Mode

To turn off encryption and switch to plain-text storage:

1. Go to **Settings > Devices & Services > Integrations**
2. Find **SlotSentry**, click the menu (three dots)
3. Click **Reconfigure**
4. On the "Secure Mode" screen, **uncheck Enable Secure Mode**
5. Enter your current secure mode password to decrypt existing data
6. A warning appears: "Codes will be stored in plain text."
7. Click **Confirm**

All codes are decrypted and stored plainly. The sidebar panel no longer shows asterisks.

## Keypad Lockout Configuration

Keypad lockout disables lock keypads (preventing PIN entry) when a monitored sensor reaches a target state.

### When to Use Keypad Lockout

**Scenario 1: Alarm Armed Home**
- Trigger Sensor: `alarm_control_panel.alarm`
- Target State: `armed_home`
- Participating Locks: Back Door, Front Door, Garage Door
- Effect: When alarm is armed home, keypads are disabled on exterior doors (prevents accidental unlock from outside)

**Scenario 2: Nobody Home**
- Trigger Sensor: `binary_sensor.anyone_home`
- Target State: `false` (everyone has left)
- Participating Locks: All doors
- Effect: Keypads disabled when the house is empty; no one can enter via PIN

**Scenario 3: Guest Mode**
- Trigger Sensor: `input_boolean.guest_mode` (toggle created in automations)
- Target State: `on`
- Participating Locks: Kitchen Door, Media Room
- Effect: During guest visits, keep some interior doors locked; codes still work but keypads are disabled for extra security

### How Keypad Lockout Works

1. SlotSentry monitors your chosen trigger sensor
2. When the sensor reaches the target state:
   - SlotSentry disables the keypad on participating locks (via Z-Wave command)
   - The lock's display may turn off or show a message
3. When the sensor leaves the target state:
   - SlotSentry re-enables the keypad
   - The lock returns to normal operation

**Important Distinction:**
- **Keypad Disabled** → Lock does NOT accept PIN entry (keypads ignored)
- **Codes Disabled** → Codes are erased from lock memory (via SlotSentry disable/enable)
- Use both together for maximum security, or either separately depending on your needs

SlotSentry is a code manager only — it does not issue lock or unlock commands as part of keypad lockout.

### Configuring Keypad Lockout

#### During Initial Setup

1. On the "Keypad Lockout" configuration screen:
2. Click **Select Trigger Sensor**
3. Search for an entity (e.g., `alarm_control_panel.alarm_system`, `binary_sensor.anyone_home`)
4. Click the entity to select it
5. **Target State** — Choose the state that should trigger lockout:
   - For alarm: `armed_home`, `armed_away`, `armed_night`, etc.
   - For binary sensor: `on`, `off`, `true`, `false`
   - Dropdown shows available states based on your chosen sensor
6. **Participating Locks** — Check boxes for locks that should have keypads disabled:
   - Select only exterior locks if using alarm state
   - Select all locks if using presence detection
7. Click **Finish**

#### Modifying Keypad Lockout

To change the trigger sensor, target state, or lock participation:

1. Go to **Settings > Devices & Services > Integrations**
2. Find **SlotSentry**, click the menu (three dots)
3. Click **Reconfigure**
4. Navigate to the "Keypad Lockout" screen
5. Modify settings and click **Finish**

### Checking Keypad Lockout Status

The **binary_sensor.slotsentry_suppressed** entity shows keypad lockout status:

- **State: `on`** — Keypad lockout is active (trigger sensor is at target state)
- **State: `off`** — Keypad lockout is inactive (trigger sensor is not at target state)

**Use in automations:**

```yaml
automation:
  - alias: "Notify when keypad locked out"
    trigger:
      platform: state
      entity_id: binary_sensor.slotsentry_suppressed
      to: "on"
    action:
      service: notify.admin
      data:
        message: "SlotSentry: Keypad lockout activated"
```

### Troubleshooting Keypad Lockout

**Keypad Lockout Not Engaging:**
1. Check that your trigger sensor exists and has the correct entity ID
2. Manually change the sensor state to the target state
3. Check **binary_sensor.slotsentry_suppressed** — it should change to `on`
4. If it doesn't, the trigger sensor may be incorrect
5. Reconfigure and re-select the sensor

**Keypad Still Accepting Codes:**
- Keypad lockout disables PIN entry, but existing codes are still on the lock
- If codes work after keypad lockout is enabled, the lock may not support keypad disable
- Alternatively, use SlotSentry's per-slot enable/disable to clear codes instead

**Sensor State Not Detected:**
1. Verify the sensor exists: go to **Developer Tools > States** and search for it
2. Manually change the sensor state
3. Wait a few seconds and check **binary_sensor.slotsentry_suppressed**
4. If no change, the integration may not be monitoring the sensor correctly
5. Reconfigure or restart Home Assistant

## Troubleshooting

### Issue: "Integration Not Found"

**Symptoms:**
- SlotSentry doesn't appear in **Settings > Devices & Services > Integrations**
- "Create Automation" button doesn't show SlotSentry as an option

**Solution:**
1. Verify HACS installation: go to **Settings > Devices & Services** and look for HACS
2. Add the custom repository again (see [Installation](#installation))
3. Restart Home Assistant: **Settings > System > Restart**
4. Clear browser cache: Ctrl+Shift+Delete (Windows/Linux) or Cmd+Shift+Delete (Mac)
5. Try to create SlotSentry integration again

### Issue: "Sidebar Panel Not Showing"

**Symptoms:**
- SlotSentry integration is created, but no "SlotSentry" menu item appears in the sidebar

**Solution:**
1. Restart Home Assistant: **Settings > System > Restart**
2. After restart, refresh the browser page (F5 or Cmd+R)
3. Check if SlotSentry appears in the sidebar (may take 30 seconds after restart)
4. If still missing, in developer tools, check for JavaScript errors (F12 > Console tab)
5. If errors appear, uninstall and reinstall SlotSentry via HACS

### Issue: "Locks Not Appearing in Setup"

**Symptoms:**
- During initial configuration, the lock selection screen is blank or shows no locks

**Solution:**
1. Verify Z-Wave JS integration is installed: **Settings > Devices & Services** and look for "Z-Wave JS"
2. Verify locks are added to Z-Wave JS:
   - Click on the Z-Wave JS integration
   - Look for your locks in the device list
   - If they're gray or offline, reboot the lock (remove batteries, wait 30 seconds, reinsert) or check Z-Wave mesh connectivity
3. If locks are present in Z-Wave JS but not showing in SlotSentry:
   - Restart Home Assistant: **Settings > System > Restart**
   - Try setting up SlotSentry again

### Issue: "Push Status Shows 'Out of Sync' or 'Error'"

**Symptoms:**
- After clicking **Save**, the Push Status shows "Out of Sync" or displays an error message

**Solution:**
1. **Check lock status:**
   - Go to **Settings > Devices & Services > Z-Wave JS**
   - Verify the affected lock shows green (online) status
   - If gray or offline, check lock batteries and Z-Wave mesh distance

2. **Check code length:**
   - Verify your code matches the configured length (e.g., 6 digits if configured for 6)
   - Avoid codes with spaces or special characters

3. **Retry manually:**
   - Press the **Retry** button in the sidebar panel
   - Wait for the status to update

4. **Bulk update:**
   - Check **Update All Slots** and click **Save**
   - This re-pushes all codes to all locks

5. **Restart Z-Wave JS:**
   - Go to **Settings > Add-ons > Z-Wave JS**
   - Click **Restart**
   - Wait 30 seconds for locks to reconnect
   - Try **Retry** again

6. **If error persists:**
   - Check the Z-Wave JS UI logs: open Z-Wave JS UI in a new tab and look for error messages related to your lock
   - Consider removing and re-adding the lock in Z-Wave JS

### Issue: "Secure Mode Password Not Working"

**Symptoms:**
- Password field in sidebar panel rejects your correct password
- Cannot unlock the panel

**Solution:**
1. **Verify password:**
   - Ensure Caps Lock is off
   - Copy and paste your password if possible (to avoid typos)
   - Check that you're typing in the correct field (not a code field)

2. **Failed password detection:**
   - After several failed attempts, SlotSentry may lock you out
   - Wait 1 minute and try again (rate limiting)
   - Alternatively, reconfigure the integration (see Password Recovery below)

3. **Password recovery:**
   - Go to **Settings > Devices & Services > Integrations**
   - Find **SlotSentry**, click the menu (three dots)
   - Click **Reconfigure**
   - On the "Secure Mode" screen, select "I forgot my password"
   - Follow the prompts to set a new password
   - **Warning:** This action reinitializes all slots and clears all stored data

### Issue: "Z-Wave Lock Commands Failing"

**Symptoms:**
- "Lock unreachable" or "Command failed" errors when pushing codes

**Solution:**
1. **Check lock batteries:**
   - Low batteries prevent Z-Wave response
   - Replace batteries if low
   - Wait 30 seconds for the lock to reconnect to mesh

2. **Check Z-Wave mesh:**
   - Ensure lock is within range of Z-Wave JS add-on (20–50 feet, line of sight preferred)
   - Check for interference (microwaves, routers on 2.4 GHz)
   - Add Z-Wave repeaters if the lock is far from the hub

3. **Restart Z-Wave JS add-on:**
   - Go to **Settings > Add-ons > Z-Wave JS**
   - Click **Restart**
   - Wait 2 minutes for the mesh to stabilize
   - Retry code pushes

4. **Re-add the lock:**
   - If problems persist, remove the lock from Z-Wave JS and re-add it:
     - Go to Z-Wave JS UI (in a new tab), find the lock, click **Remove**
     - In Home Assistant, go to **Settings > Devices & Services > Z-Wave JS > Devices**
     - Remove the lock device
     - Use Z-Wave JS UI to re-add the lock
     - Reconfigure SlotSentry to select the re-added lock

### Issue: "Codes Work Sometimes But Not Always"

**Symptoms:**
- A code works one day but not the next
- Inconsistent unlock behavior

**Solution:**
1. **Test with fresh batteries:**
   - Replace lock batteries
   - Some locks misreport slot status with low batteries

2. **Verify codes in Z-Wave JS UI:**
   - Open Z-Wave JS UI, find the lock
   - Check the slot status in the "CC 0x63" section
   - Verify your code matches what you entered in SlotSentry

3. **Check for code conflicts:**
   - If multiple people are managing codes (via SlotSentry, Z-Wave JS UI, lock app), conflicts can occur
   - Designate SlotSentry as the single source of truth
   - Avoid editing codes via Z-Wave JS UI or lock apps while using SlotSentry

4. **Verify code format:**
   - Some locks reject codes starting with 0 or containing repeating digits
   - Try a different code pattern (e.g., avoid 000000 or 111111)
   - Check lock manual for code restrictions

## FAQ

### General Questions

**Q: How many locks can SlotSentry manage?**

A: SlotSentry supports any number of Z-Wave locks simultaneously. Performance is limited by your Z-Wave JS add-on and network latency. Recommended maximum: 5–10 locks. Each code push takes 10–30 seconds per lock.

**Q: How is the slot count determined?**

A: The number of slots is determined by the lock with the smallest slot capacity among your configured locks. This is established at integration setup and the commit arrays are sized at that time. Adding a lock with fewer slots via reconfigure will reduce the available slot count.

**Q: Can I migrate codes from Keymaster to SlotSentry?**

A: Not automatically. If you're switching from Keymaster:
1. Manually note all active codes from Keymaster
2. Disable Keymaster
3. Set up SlotSentry
4. Re-enter codes into SlotSentry, one by one
5. A bulk import tool may be available in future versions

**Q: Does SlotSentry work with HomeKit or Apple Home?**

A: SlotSentry manages Z-Wave codes only. HomeKit integration is separate—if your lock supports HomeKit and Z-Wave, both can be active simultaneously. HomeKit codes are managed via Apple Home; Z-Wave codes are managed via SlotSentry.

**Q: Can I use SlotSentry on multiple Home Assistant instances?**

A: No. SlotSentry is tied to a single HA instance. If you have multiple HA servers, install SlotSentry separately on each instance, pointing to different lock subsets.

**Q: What's the maximum code length?**

A: Configured per lock type:
- Schlage BE469ZP: 4–8 digits (configurable)
- Schlage FE599: 4 digits (fixed)
- Most locks: 4–8 digits, some support up to 16 characters

**Q: Can I set a code via the Z-Wave JS UI while using SlotSentry?**

A: Technically yes, but not recommended. SlotSentry doesn't know about codes set via Z-Wave JS UI. For consistency, always manage codes through SlotSentry. If you manually set a code via Z-Wave JS UI:
1. Update it in SlotSentry's slot grid to match
2. Click **Save** (check **Update All Slots** for safety)

### Security Questions

**Q: Are codes visible in Home Assistant logs?**

A: No. SlotSentry explicitly avoids logging actual codes. Logs show slot numbers, labels, and push status only.

**Q: Is secure mode encryption military-grade?**

A: SlotSentry uses AES-256 encryption, the same standard used for government and banking data. If your Home Assistant instance is physically secure, encryption adds minimal risk reduction—someone with server access can potentially extract data. Encryption is best for:
- Shared admin accounts
- Untrusted network access
- Compliance/audit requirements

**Q: Can Home Assistant backup/restore encrypt my secure mode data?**

A: Yes, Home Assistant backups include encrypted SlotSentry data in `.storage`. However:
- Your secure mode password is NOT backed up
- Restoring a backup without knowing the password locks you out forever
- Always save your password in a secure location (password manager) before enabling secure mode

**Q: What happens if I factory reset a lock while using SlotSentry?**

A: Factory reset clears all codes from the lock. After reset:
1. The lock shows as offline in Z-Wave JS until you re-add it
2. Re-add the lock in Z-Wave JS UI
3. Reconfigure SlotSentry to select the lock again
4. Click **Save** to re-push all codes

### Troubleshooting Questions

**Q: Why is my lock offline in Z-Wave JS?**

A: Common causes:
- Low battery (most common)
- Out of Z-Wave mesh range
- Z-Wave JS add-on crashed
- Lock firmware outdated

**Solution:**
1. Check lock batteries
2. Move closer to HA hub or add Z-Wave repeaters
3. Restart Z-Wave JS add-on
4. Update lock firmware via Z-Wave JS UI

**Q: Can I use SlotSentry with non-Z-Wave locks?**

A: Not currently. SlotSentry is designed for Z-Wave JS integration. Future versions may support other protocols. For now:
- Zigbee locks: Use Zigbee integration with manual code management
- Bluetooth locks: Use lock's native app
- HomeKit locks: Use Apple Home app

**Q: Why did my codes get cleared when I reconfigured SlotSentry?**

A: Reconfiguring SlotSentry does NOT clear codes. However:
- If you removed a lock during reconfiguration and then added it back, that lock's codes may need re-pushing
- Click **Save** (with **Update All Slots** checked) to re-push

**Q: How do I know if my lock supports code readback?**

A: Check the **Push Status** sensor after a code push:
- If status shows "Code verified: [actual code]", readback is supported
- If status shows "Slot status verified: Occupied", only occupancy is verified
- Different lock models behave differently

### Advanced Questions

**Q: Can I automate code enable/disable with Home Assistant automations?**

A: Not directly—SlotSentry doesn't expose service calls for enabling/disabling individual slots. However:
- Press the **button.slotsentry_push_all** button to force a full push
- Use **binary_sensor.slotsentry_suppressed** as a trigger for other automations
- For advanced scenarios, manually edit `.storage/slotsentry` and call the reload service (not recommended)

**Q: Can I export my SlotSentry data?**

A: Secure mode data cannot be safely exported (encrypted). Open mode data is stored in `.storage/slotsentry` as JSON:
1. Go to **Developer Tools > States**
2. Search for `slotsentry`
3. Note the current state
4. Access your HA server filesystem
5. Copy `/homeassistant/.storage/slotsentry`
6. Keep this file secure and private (it contains codes)

**Q: Can I run SlotSentry on Home Assistant in Docker?**

A: Yes, but with caveats:
- Ensure Z-Wave JS add-on is also running in Docker
- Mount the Z-Wave device correctly (`/dev/ttyACM0` or similar)
- SlotSentry uses standard HA paths, so Docker paths must be configured correctly
- Backup and encryption work the same way

**Q: How do I contribute to SlotSentry development?**

A: See the [Contributing section](../README.md#contributing) in the main README.

---

**Need more help?** Open an issue on [GitHub](https://github.com/ChrisCaho/SlotSentry/issues) or check the main [README](../README.md) for additional resources.
