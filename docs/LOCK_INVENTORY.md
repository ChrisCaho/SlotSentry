# Z-Wave Lock Inventory

**Document Version:** 1.0
**Generated:** 2026-03-31
**Purpose:** Comprehensive reference for Z-Wave lock entities and capabilities for SlotSentry development

---

## Table of Contents

1. [Lock Groups](#lock-groups)
2. [Z-Wave Locks - In Scope for SlotSentry](#z-wave-locks---in-scope-for-slotsentry)
   - [Back Door Deadbolt (BE469ZP)](#back-door-deadbolt-be469zp)
   - [Master Bedroom Lock (FE599)](#master-bedroom-lock-fe599)
   - [Utility Room Lock (FE599)](#utility-room-lock-fe599)
   - [Office Door Lock (FE599)](#office-door-lock-fe599)
3. [Cloud Lock - Out of Scope](#cloud-lock---out-of-scope)
4. [Garage Door Remotes - Out of Scope](#garage-door-remotes---out-of-scope)
5. [Related Helpers](#related-helpers)
6. [Entity Type Summary](#entity-type-summary)

---

## Lock Groups

Lock groups provide convenient management of multiple locks together.

### lock.all_locks (Group)

**Members:** 5 locks
- `lock.schlage_front_door_deadbolt` (Cloud lock - out of scope)
- `lock.zwave_back_door_deadbolt`
- `lock.zwave_master_bedroom_lock`
- `lock.zwave_office_door_lock`
- `lock.zwave_utility_room_lock`

**Current State:** `unlocked`
**Supported Features:** 1 (toggle)

### lock.perimeter_locks (Group)

**Members:** 3 locks (only perimeter doors)
- `lock.schlage_front_door_deadbolt` (Cloud lock - out of scope)
- `lock.zwave_back_door_deadbolt`
- `lock.zwave_utility_room_lock`

**Current State:** `unlocked`
**Supported Features:** 1 (toggle)

---

## Z-Wave Locks - In Scope for SlotSentry

### Back Door Deadbolt (BE469ZP)

**Entity ID:** `lock.zwave_back_door_deadbolt`
**Friendly Name:** zwave_back_door_deadbolt
**Model:** BE469ZP (Schlage Connect Camelot - Allegion)
**Current State:** `locked`
**Last Changed:** 2026-03-31T23:45:32.613731Z
**Supported Features:** 0 (basic lock/unlock via lock.lock/lock.unlock services; no special features like open)

#### Battery Status

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `sensor.zwave_back_door_deadbolt_battery_level` | Sensor | 100.0 | % | Primary battery percentage |
| `sensor.zwave_back_door_deadbolt_battery_plus` | Sensor | 100 | % | Battery+ (advanced metric) |
| `binary_sensor.zwave_back_door_deadbolt_battery_plus_low` | Binary | off | - | Low battery warning |
| `sensor.zwave_back_door_deadbolt_battery_type` | Sensor | 4× AA | - | Battery type installed |
| `sensor.zwave_back_door_deadbolt_battery_last_replaced` | Sensor | 2025-01-27T02:38:23Z | - | Timestamp of last replacement |
| `binary_sensor.zwave_back_door_deadbolt_replace_battery_soon` | Binary | off | - | Replace soon warning |
| `binary_sensor.zwave_back_door_deadbolt_replace_battery_now` | Binary | off | - | Replace now (urgent) |
| `button.zwave_back_door_deadbolt_battery_replaced` | Button | unknown | - | Trigger when batteries replaced |

#### Door Sensor

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_back_door_deadbolt_current_status_of_the_door` | Binary | on | Door open/closed state (on=open, off=closed) |

#### Keypad Status

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_back_door_deadbolt_keypad_temporary_disabled` | Binary | off | Keypad temporarily disabled |
| `button.zwave_back_door_deadbolt_idle_access_control_keypad_state` | Button | unknown | Query keypad status |

#### Lock Status & Configuration

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `select.zwave_back_door_deadbolt_current_lock_mode` | Select | Secured | Lock mode: Secured/Unsecured |
| `binary_sensor.zwave_back_door_deadbolt_lock_jammed` | Binary | off | Lock jammed detection |
| `button.zwave_back_door_deadbolt_idle_access_control_lock_state` | Button | unknown | Query lock status |

#### Security & Hardware Status

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_back_door_deadbolt_intrusion` | Binary | off | Intrusion detection (tamper) |
| `binary_sensor.zwave_back_door_deadbolt_system_hardware_failure` | Binary | off | Hardware failure alert |
| `button.zwave_back_door_deadbolt_idle_system_hardware_status` | Button | unknown | Query hardware status |

#### Z-Wave Network

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `sensor.zwave_back_door_deadbolt_node_status` | Sensor | alive | Z-Wave node status |
| `sensor.zwave_back_door_deadbolt_last_seen` | Sensor | 2026-04-01T01:16:00Z | Last communication timestamp |
| `button.zwave_back_door_deadbolt_ping` | Button | unknown | Ping device to verify connectivity |
| `update.zwave_back_door_deadbolt_firmware` | Update | off | Firmware update availability |

#### User Code Management

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `input_number.zwave_back_door_deadbolt_user_code` | Input Number | 0.0 | - | PIN code to program (automation input) |
| `number.zwave_back_door_deadbolt_user_code_pin_length` | Number | 6.0 | - | PIN code length (4-8 digits) |
| `input_text.zwave_back_door_deadbolt_user_name` | Input Text | unknown | - | User name for lock access |
| `input_text.zwave_back_door_deadbolt_status` | Input Text | unknown | - | Status/result of last lock operation |

#### Miscellaneous Status

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `button.zwave_back_door_deadbolt_idle_power_management_battery_maintenance_status` | Button | unknown | Query power management status |

**Total Related Entities:** 29

---

### Master Bedroom Lock (FE599)

**Entity ID:** `lock.zwave_master_bedroom_lock`
**Friendly Name:** zwave_master_bedroom_lock
**Model:** FE599 (Schlage Connected Keypad - CKPD)
**Current State:** `unlocked`
**Last Changed:** 2026-03-31T23:09:45.991268Z
**Supported Features:** 0 (basic lock/unlock via lock.lock/lock.unlock services; no special features like open)

#### Battery Status

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `sensor.zwave_master_bedroom_lock_battery_level` | Sensor | 100.0 | % | Primary battery percentage |
| `sensor.zwave_master_bedroom_lock_battery_plus` | Sensor | 100 | % | Battery+ (advanced metric) |
| `binary_sensor.zwave_master_bedroom_lock_battery_plus_low` | Binary | off | - | Low battery warning |
| `sensor.zwave_master_bedroom_lock_battery_type` | Sensor | 4× AA | - | Battery type installed |
| `sensor.zwave_master_bedroom_lock_battery_last_replaced` | Sensor | 2025-01-27T02:47:56Z | - | Timestamp of last replacement |
| `button.zwave_master_bedroom_lock_battery_replaced` | Button | unknown | - | Trigger when batteries replaced |

#### Door Sensor

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_master_bedroom_lock_current_status_of_the_door` | Binary | on | Door open/closed state (on=open, off=closed) |

#### Keypad Status

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_master_bedroom_lock_keypad_temporary_disabled` | Binary | off | Keypad temporarily disabled |
| `binary_sensor.zwave_master_bedroom_lock_keypad_busy` | Binary | off | Keypad in use (active) |
| `button.zwave_master_bedroom_lock_idle_access_control_keypad_state` | Button | unknown | Query keypad status |

#### Lock Status & Configuration

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `select.zwave_master_bedroom_lock_current_lock_mode` | Select | Unsecured | Lock mode: Secured/Unsecured |

#### Z-Wave Network

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `sensor.zwave_master_bedroom_lock_node_status` | Sensor | alive | Z-Wave node status |
| `sensor.zwave_master_bedroom_lock_last_seen` | Sensor | 2026-03-31T21:02:48Z | Last communication timestamp |
| `button.zwave_master_bedroom_lock_ping` | Button | 2025-02-14T21:29:17.664862Z | Last ping timestamp |
| `binary_sensor.zwave_master_bedroom_lock_low_battery_level` | Binary | unavailable | Low battery indicator (if available) |

**Total Related Entities:** 16

---

### Utility Room Lock (FE599)

**Entity ID:** `lock.zwave_utility_room_lock`
**Friendly Name:** zwave_utility_room_lock
**Model:** FE599 (Schlage Connected Keypad - CKPD)
**Current State:** `unlocked`
**Last Changed:** 2026-03-31T23:09:45.995442Z
**Supported Features:** 0 (basic lock/unlock via lock.lock/lock.unlock services; no special features like open)

#### Battery Status

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `sensor.zwave_utility_room_lock_battery_level` | Sensor | 86.0 | % | Primary battery percentage |
| `sensor.zwave_utility_room_lock_battery_plus` | Sensor | 86 | % | Battery+ (advanced metric) |
| `binary_sensor.zwave_utility_room_lock_battery_plus_low` | Binary | off | - | Low battery warning |
| `sensor.zwave_utility_room_lock_battery_type` | Sensor | 4× AA | - | Battery type installed |
| `sensor.zwave_utility_room_lock_battery_last_replaced` | Sensor | 2025-01-27T02:51:58Z | - | Timestamp of last replacement |
| `button.zwave_utility_room_lock_battery_replaced` | Button | unknown | - | Trigger when batteries replaced |

#### Door Sensor

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_utility_room_lock_current_status_of_the_door` | Binary | on | Door open/closed state (on=open, off=closed) |

#### Keypad Status

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_utility_room_lock_keypad_temporary_disabled` | Binary | on | **Keypad currently DISABLED** |
| `binary_sensor.zwave_utility_room_lock_keypad_busy` | Binary | off | Keypad in use (active) |
| `button.zwave_utility_room_lock_idle_access_control_keypad_state` | Button | unknown | Query keypad status |

#### Lock Status & Configuration

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `select.zwave_utility_room_lock_current_lock_mode` | Select | Unsecured | Lock mode: Secured/Unsecured |

#### Z-Wave Network

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `sensor.zwave_utility_room_lock_node_status` | Sensor | alive | Z-Wave node status |
| `sensor.zwave_utility_room_lock_last_seen` | Sensor | 2026-04-01T01:12:22Z | Last communication timestamp |
| `button.zwave_utility_room_lock_ping` | Button | 2025-02-19T01:36:36.560226Z | Last ping timestamp |
| `binary_sensor.zwave_utility_room_lock_low_battery_level` | Binary | unavailable | Low battery indicator (if available) |

#### User Code Management

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `input_number.zwave_utility_room_lock_user_code` | Input Number | 0.0 | - | PIN code to program (automation input) |
| `input_text.zwave_utility_room_lock_user_name` | Input Text | unknown | - | User name for lock access |
| `input_text.zwave_utility_room_lock_status` | Input Text | unknown | - | Status/result of last lock operation |

**Total Related Entities:** 19

**NOTE:** This lock's keypad is currently disabled (likely for maintenance or troubleshooting).

---

### Office Door Lock (FE599)

**Entity ID:** `lock.zwave_office_door_lock`
**Friendly Name:** zwave_office_door_lock
**Model:** FE599 (Schlage Connected Keypad - CKPD)
**Current State:** `unlocked`
**Last Changed:** 2026-03-31T23:09:46.001632Z
**Supported Features:** 0 (basic lock/unlock via lock.lock/lock.unlock services; no special features like open)

#### Battery Status

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `sensor.zwave_office_door_lock_battery_level` | Sensor | 100.0 | % | Primary battery percentage |
| `sensor.zwave_office_door_lock_battery_plus` | Sensor | 100 | % | Battery+ (advanced metric) |
| `binary_sensor.zwave_office_door_lock_battery_plus_low` | Binary | off | - | Low battery warning |
| `sensor.zwave_office_door_lock_battery_type` | Sensor | 4× AA | - | Battery type installed |
| `sensor.zwave_office_door_lock_battery_last_replaced` | Sensor | 2025-01-27T02:54:34Z | - | Timestamp of last replacement |
| `button.zwave_office_door_lock_battery_replaced` | Button | unknown | - | Trigger when batteries replaced |

#### Door Sensor

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_office_door_lock_current_status_of_the_door` | Binary | on | Door open/closed state (on=open, off=closed) |

#### Keypad Status

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `binary_sensor.zwave_office_door_lock_keypad_temporary_disabled` | Binary | off | Keypad temporarily disabled |
| `binary_sensor.zwave_office_door_lock_keypad_busy` | Binary | off | Keypad in use (active) |
| `button.zwave_office_door_lock_idle_access_control_keypad_state` | Button | unknown | Query keypad status |

#### Lock Status & Configuration

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `select.zwave_office_door_lock_current_lock_mode` | Select | Unsecured | Lock mode: Secured/Unsecured |

#### Z-Wave Network

| Entity | Type | State | Description |
|--------|------|-------|-------------|
| `sensor.zwave_office_door_lock_node_status` | Sensor | alive | Z-Wave node status |
| `sensor.zwave_office_door_lock_last_seen` | Sensor | 2026-03-31T22:33:36Z | Last communication timestamp |
| `button.zwave_office_door_lock_ping` | Button | 2025-01-27T02:58:23.737670Z | Last ping timestamp |
| `binary_sensor.zwave_office_door_lock_low_battery_level` | Binary | unavailable | Low battery indicator (if available) |

**Total Related Entities:** 16

---

## Cloud Lock - Out of Scope

### Schlage Front Door Deadbolt

**Entity ID:** `lock.schlage_front_door_deadbolt`
**Friendly Name:** Schlage Front Door Deadbolt
**Type:** Cloud-connected (HomeKit/Schlage API)
**Current State:** `locked`
**Note:** This lock is NOT a Z-Wave device and is out of scope for SlotSentry Z-Wave lock management.

#### Related Entities (Reference Only)

| Entity | Type | State | Unit | Description |
|--------|------|-------|------|-------------|
| `sensor.schlage_front_door_deadbolt_battery` | Sensor | 82 | % | Battery level |
| `select.schlage_front_door_deadbolt_auto_lock_time` | Select | 240 | - | Auto-lock timeout |
| `switch.schlage_front_door_deadbolt_keypress_beep` | Switch | on | - | Keypress beep enabled |
| `switch.schlage_front_door_deadbolt_1_touch_locking` | Switch | on | - | 1-touch locking enabled |
| `binary_sensor.schlage_front_door_deadbolt_keypad_disabled` | Binary | off | - | Keypad disabled |

**Members of:** `lock.all_locks`, `lock.perimeter_locks`

---

## Garage Door Remotes - Out of Scope

### ratgdo_2_32f9f8 (Garage Door Remote 2)

**Lock Entity:** `lock.ratgdo_2_32f9f8_lock_remotes`
**Type:** Garage door remote (ratgdo) — NOT a door lock
**Current State:** `unlocked`
**Purpose:** Controls garage door opener remotes, not a physical lock
**Note:** This is out of scope for SlotSentry (not a residential door lock).

**Related Entities (Reference Only):**
- `cover.ratgdo_2_32f9f8_door` — Garage door status
- Multiple sensors for motion, obstruction, vehicle detection, WiFi signal, etc.

### ratgdo_1_310298 (Garage Door Remote 1)

**Lock Entity:** `lock.ratgdo_1_310298_lock_remotes`
**Type:** Garage door remote (ratgdo) — NOT a door lock
**Current State:** `unlocked`
**Purpose:** Controls garage door opener remotes, not a physical lock
**Note:** This is out of scope for SlotSentry (not a residential door lock).

**Related Entities (Reference Only):**
- `cover.ratgdo_1_310298_door` — Garage door status
- Multiple sensors for motion, obstruction, vehicle detection, WiFi signal, etc.

---

## Related Helpers

These input helpers are used for lock automation and user management:

### User Code Management Helpers

| Entity | Type | State | Purpose |
|--------|------|-------|---------|
| `input_number.zwave_back_door_deadbolt_user_code` | Input Number | 0.0 | PIN code input for back door (automation) |
| `input_number.zwave_utility_room_lock_user_code` | Input Number | 0.0 | PIN code input for utility room (automation) |
| `input_number.schlage_front_door_deadbolt_user_code` | Input Number | 0.0 | PIN code input for Schlage (automation) |

**Note:** Master bedroom and office locks do NOT have user code input helpers currently.

### Lock Status Helpers

| Entity | Type | Current State | Purpose |
|--------|------|-------|---------|
| `input_text.zwave_back_door_deadbolt_user_name` | Input Text | unknown | Username for back door access |
| `input_text.zwave_back_door_deadbolt_status` | Input Text | unknown | Last operation status for back door |
| `input_text.zwave_utility_room_lock_user_name` | Input Text | unknown | Username for utility room access |
| `input_text.zwave_utility_room_lock_status` | Input Text | unknown | Last operation status for utility room |

---

## Entity Type Summary

### Lock Entities (9 total)

**Z-Wave Locks (4):**
- `lock.zwave_back_door_deadbolt`
- `lock.zwave_master_bedroom_lock`
- `lock.zwave_utility_room_lock`
- `lock.zwave_office_door_lock`

**Cloud Lock (1):**
- `lock.schlage_front_door_deadbolt`

**Garage Door Remotes (2):**
- `lock.ratgdo_2_32f9f8_lock_remotes`
- `lock.ratgdo_1_310298_lock_remotes`

**Groups (2):**
- `lock.all_locks`
- `lock.perimeter_locks`

### Related Sensor Entities by Lock (Z-Wave only)

**Back Door Deadbolt (29 entities):**
- 1 Lock
- 6 Sensors (battery, status, etc.)
- 9 Binary Sensors (alerts, door, keypad, etc.)
- 7 Buttons (query operations)
- 1 Select (lock mode)
- 3 Input Helpers (user code, status, name)
- 1 Update (firmware)
- 1 Number (PIN length)

**Master Bedroom Lock (16 entities):**
- 1 Lock
- 6 Sensors (battery, status, etc.)
- 5 Binary Sensors (alerts, door, keypad, etc.)
- 3 Buttons (query operations)
- 1 Select (lock mode)

**Utility Room Lock (19 entities):**
- 1 Lock
- 6 Sensors (battery, status, etc.)
- 5 Binary Sensors (alerts, door, keypad, etc.)
- 3 Buttons (query operations)
- 1 Select (lock mode)
- 3 Input Helpers (user code, status, name)

**Office Door Lock (16 entities):**
- 1 Lock
- 6 Sensors (battery, status, etc.)
- 5 Binary Sensors (alerts, door, keypad, etc.)
- 3 Buttons (query operations)
- 1 Select (lock mode)

**Total Z-Wave Related:** 70 entities

### Entity Types Used

| Type | Count | Key Examples |
|------|-------|--------------|
| Lock | 4 | Main lock control entities |
| Sensor | 24 | Battery level, node status, timestamps |
| Binary Sensor | 20 | Door status, keypad state, alerts |
| Button | 16 | Ping, query operations, battery replaced |
| Select | 4 | Lock mode selection |
| Input Number | 3 | PIN codes for automation |
| Input Text | 6 | Status and user info |
| Update | 1 | Firmware availability |
| Number | 1 | PIN length configuration |

---

## Key Observations for SlotSentry Development

1. **Lock Capabilities:** All Z-Wave locks have supported_features: 0, which means they support basic lock/unlock operations via the `lock.lock` and `lock.unlock` services, but do not support additional features like open. Lock/unlock is performed through the lock entity via these standard services.

2. **Battery Monitoring:** All locks have comprehensive battery monitoring:
   - Primary level via `battery_level` sensor
   - Advanced `battery_plus` metric
   - Replacement timestamp tracking
   - Low battery warnings (both soon and now alerts)

3. **Door Status Sensors:** All locks include a built-in door status sensor (`binary_sensor.*_current_status_of_the_door`). Note: the state is `on` when door is open, `off` when closed. SlotSentry does not map these sensors for any purpose — the integration is a code manager only and does not issue lock/unlock commands.

4. **Keypad Status:** All locks provide keypad state monitoring:
   - Temporary disable status
   - Busy status (if actively in use)
   - The utility room lock currently has its keypad disabled

5. **Z-Wave Network:** Each lock provides:
   - Node status (alive/asleep/dead)
   - Last seen timestamp (important for connectivity monitoring)
   - Ping button for manual connectivity checks
   - Firmware update availability

6. **User Code Management:** Only back door and utility room locks have helper inputs for PIN management. This may need to be expanded for other locks if needed.

7. **Lock Groups:** Two groups exist that include Z-Wave locks:
   - `lock.all_locks` — includes cloud lock + all Z-Wave locks
   - `lock.perimeter_locks` — includes cloud lock + perimeter Z-Wave locks (back door, utility room)

8. **Models:** Two models represented:
   - **BE469ZP** (Schlage Connect Camelot) — Back door only
   - **FE599** (Schlage Connected Keypad CKPD) — Master bedroom, utility room, office

---

## Communication Notes for Development

- Z-Wave communication is reliable with all locks showing `alive` status
- All locks with `battery_level` at 85% or above (except utility room at 86%)
- Last seen timestamps are recent (within hours to days), indicating active communication
- All door sensors report open/closed state properly
- Firmware is current on all devices
- No hardware failures or jamming detected

---

**End of Document**

Revision: 1.0 | Last Updated: 2026-03-31
