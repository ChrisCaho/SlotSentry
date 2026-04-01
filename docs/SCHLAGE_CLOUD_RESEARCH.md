# Schlage Cloud Integration Research

**Document revision:** 1.0
**Research date:** 2026-04-01
**Researcher:** Claude Code
**Sources:** HA integration docs, HA core source (dev branch), pyschlage source (main branch), live entity inspection

---

## 1. Summary

The HA Schlage integration is a cloud-polling integration that communicates with Schlage's cloud API via the `pyschlage` library. It exposes three services for PIN code management. Codes are identified exclusively by name (case-insensitive). There is no slot-number concept. Code enable/disable is a property in the pyschlage `AccessCode` object but is **not exposed by any HA service or entity** in the current integration. The `get_codes` service was tested live but returned HTTP 400 — see Section 8.

---

## 2. Live Entities on This HA Instance

All entities found via `search_entities_tool` with query "schlage":

| Entity ID | Domain | Current State | Notes |
|---|---|---|---|
| `lock.schlage_front_door_deadbolt` | lock | locked | `supported_features: 0` |
| `binary_sensor.schlage_front_door_deadbolt_keypad_disabled` | binary_sensor | off (normal) | device_class: problem |
| `sensor.schlage_front_door_deadbolt_battery` | sensor | 82% | diagnostic |
| `select.schlage_front_door_deadbolt_auto_lock_time` | select | 240 (4 min) | options: 0/5/15/30/60/120/240/300 |
| `switch.schlage_front_door_deadbolt_keypress_beep` | switch | on | aka "Keypress Beep" |
| `switch.schlage_front_door_deadbolt_1_touch_locking` | switch | on | aka "1-Touch Locking" |
| `input_number.schlage_front_door_deadbolt_user_code` | input_number | 0.0 | user-created helper, not integration |
| `input_text.schlage_front_door_deadbolt_status` | input_text | unknown | user-created helper, not integration |
| `input_text.schlage_front_door_deadbolt_user_name` | input_text | unknown | user-created helper, not integration |

The three `input_*` entities are user-created helpers, not part of the Schlage integration itself.

The lock entity reports `supported_features: 0`, meaning the standard `lock.open` and `lock.set_user_code` LockEntityFeature flags are not implemented — all code management goes through custom services.

---

## 3. Available Schlage Services

Source: `homeassistant/components/schlage/services.yaml` (dev branch) and `lock.py`.

### 3.1 `schlage.get_codes`

Retrieves all PIN codes currently stored on the lock.

**Target:** lock entity with `integration: schlage`
**Fields:** none

**Returns (ServiceResponse dict):**
```
{
  "<uuid-access-code-id>": {
    "name": "<friendly name>",
    "code": "<pin digits as string>"
  },
  ...
}
```
Keys are UUID strings (internal Schlage `accesscodeId` values). Values contain only `name` and `code`. The `disabled` field is **not** included in the returned dict even though it exists in the underlying `AccessCode` object.

**Implementation detail** (`lock.py`):
```python
async def get_codes(self) -> ServiceResponse:
    await self._async_fetch_access_codes()
    if self._lock.access_codes:
        return {
            code: {
                "name": self._lock.access_codes[code].name,
                "code": self._lock.access_codes[code].code,
            }
            for code in self._lock.access_codes
        }
    return {}
```
Only `name` and `code` are returned. The `disabled`, `schedule`, and `notify_on_use` fields are discarded.

---

### 3.2 `schlage.add_code`

Adds a new PIN code to the lock.

**Target:** lock entity with `integration: schlage`
**Fields:**

| Field | Type | Required | Selector | Notes |
|---|---|---|---|---|
| `name` | string | yes | text (single line) | Label for the code owner |
| `code` | string | yes | text (password type) | 4–8 digit PIN |

**Validation (before API call):**
1. Calls `refresh_access_codes()` on the lock to get a fresh list.
2. Checks that `name` does not already exist (case-insensitive, whitespace-stripped). Raises `ServiceValidationError` with key `schlage_name_exists` if duplicate.
3. Checks that the PIN `code` value does not already exist (exact string match). Raises `ServiceValidationError` with key `schlage_code_exists` if duplicate.
4. Creates `AccessCode(name=name, code=code)` — all other fields default: `disabled=False`, `schedule=None`, `notify_on_use=False`.
5. Calls `self._lock.add_access_code(access_code)` in executor.
6. Triggers coordinator refresh.

**Raises:** `HomeAssistantError` with key `schlage_add_code_failed` on API error.

**services.yaml field definition:**
```yaml
add_code:
  target:
    entity:
      domain: lock
      integration: schlage
  fields:
    name:
      required: true
      example: "Example Person"
      selector:
        text:
          multiline: false
    code:
      required: true
      example: "1111"
      selector:
        text:
          multiline: false
          type: password
```

Note: The services.yaml has **no min/max length validator** on `code`. The 4–8 digit constraint is enforced by the Schlage cloud API, not by HA's service schema.

---

### 3.3 `schlage.delete_code`

Deletes a PIN code by name.

**Target:** lock entity with `integration: schlage`
**Fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Case-insensitive match against stored code names |

**Behavior:**
1. Calls `refresh_access_codes()` to get a fresh list.
2. If no codes exist, returns silently (no error).
3. Normalizes the supplied name with `.lower().strip()`.
4. Finds the first code whose normalized name matches.
5. If not found, returns silently (no error — idempotent).
6. Calls `codes[code_id_to_delete].delete()` in executor.
7. Triggers coordinator refresh.

**Raises:** `HomeAssistantError` with key `schlage_delete_code_failed` on API error.

**Key behavior:** Deletion is **idempotent**. Calling `delete_code` for a name that does not exist raises no error.

---

## 4. Code Identification — Name vs. Slot Number

**There are no slot numbers in the Schlage HA integration.**

Codes are identified by:
- **Internally** (pyschlage): UUID string (`accesscodeId` / `access_code_id` field)
- **In HA services**: Human-readable `name` string (case-insensitive)

The `get_codes` service returns UUIDs as dict keys, but there is no integer slot index concept anywhere in the integration. This differs from Z-Wave lock integrations where codes occupy numbered slots (0–N).

The UUID returned by `get_codes` is the Schlage cloud's internal identifier and is stable across sessions. It is not a slot number.

---

## 5. Keypad Disabled — Read-Only

The `binary_sensor.schlage_front_door_deadbolt_keypad_disabled` entity:
- `device_class: problem`
- State `off` = keypad is enabled (normal)
- State `on` = keypad is disabled (problem condition)

**Source** (`binary_sensor.py`): The sensor calls `data.lock.keypad_disabled(data.logs)`. This reads a computed property from the lock object and its activity log.

**There is no service, switch, or control to enable/disable the keypad.** It is read-only. The keypad becomes disabled automatically when too many incorrect codes are entered. There is no HA mechanism to re-enable it — this must be done physically at the lock or via the Schlage app.

The `switch.py` source confirms only two switches exist: **Keypress Beep** and **1-Touch Locking**. Neither relates to keypad disable/enable.

---

## 6. AccessCode Object — Full Field Reference

Source: `pyschlage/code.py` (pyschlage main branch)

```python
@dataclass
class AccessCode(Mutable):
    name: str = ""                              # friendly name shown in Schlage app
    code: str = ""                              # PIN digits as zero-padded string
    schedule: TemporarySchedule | RecurringSchedule | None = None
    notify_on_use: bool = False                 # app notification on use
    disabled: bool = False                      # whether the code is disabled
    device_id: str | None = None                # lock's device UUID
    access_code_id: str | None = None           # code's own UUID (accesscodeId)
```

**`disabled` field exists in pyschlage** but is not surfaced by the HA integration in any service call or entity. To disable a code, you would need to:
1. Call `schlage.get_codes` to get the `access_code_id` UUID.
2. Use a Python script or custom integration to call `code.save()` with `disabled=True`.

This is **not possible with out-of-the-box HA services**.

**Schedule types:**
- `TemporarySchedule(start: datetime, end: datetime)` — code active only between two timestamps
- `RecurringSchedule(days_of_week, start_hour, start_minute, end_hour, end_minute)` — weekly recurring window

Neither schedule type is configurable via HA services. The `add_code` service always creates codes with `schedule=None` (always active).

---

## 7. Polling Interval and Rate Limits

Source: `homeassistant/components/schlage/const.py`

```python
UPDATE_INTERVAL = timedelta(seconds=30)
```

The integration polls the Schlage cloud API every **30 seconds**.

No explicit rate limit is documented in the HA docs or pyschlage source. The integration uses Schlage's undocumented cloud API (IoT class: `cloud_polling`). Calling `add_code` or `delete_code` triggers an immediate `coordinator.async_request_refresh()` after the API call completes, so the coordinator data updates faster than the 30-second cycle following a code change.

Each `schlage.get_codes`, `schlage.add_code`, or `schlage.delete_code` call first invokes `lock.refresh_access_codes()` which makes an additional live API call before the main operation. This means each service call makes at least 2 cloud API requests (refresh + operation).

---

## 8. Live Service Test Result

A live call to `schlage.get_codes` with `entity_id: lock.schlage_front_door_deadbolt` was attempted via the MCP `call_service_tool`. It returned:

```
HTTP error: 400 - Bad Request
```

This may indicate:
- The service requires the entity to be targeted differently (entity services vs. domain services may behave differently via the REST API vs. WebSocket)
- The MCP tool may not correctly format entity platform services (which use `async_register_platform_entity_service`, not `hass.services.register`)
- The Schlage cloud account may be rate-limiting or the session may be expired

This does not indicate the service is broken — the `call_service_tool` MCP wrapper may not support entity-targeted platform services correctly. Testing via HA Developer Tools > Services UI is recommended to verify live behavior.

---

## 9. Code Enable/Disable — Can We Do It Programmatically?

**Short answer: Not via built-in HA services.**

The `disabled` field exists in pyschlage's `AccessCode` and is serialized as `"disabled": int(self.disabled)` in the JSON sent to the Schlage cloud API. The `save()` method sends `updateaccesscode` when `access_code_id` is set.

To programmatically disable a code without deleting it, a custom approach would be required:

**Option A — Python Script (pyschlage direct):**
Get a reference to the `SchlageLockEntity`, access `self._lock.access_codes`, find the code by name/UUID, set `code.disabled = True`, call `code.save()`. This requires a `python_script` or `pyschlage`-aware custom component.

**Option B — Delete + Re-add pattern:**
Simulate disable by deleting the code with `schlage.delete_code` and storing the PIN value externally. Re-enable by calling `schlage.add_code` with the stored PIN. This is destructive (the `access_code_id` UUID changes on re-add) but achievable with HA automations alone.

**Option C — Schedule workaround:**
The `RecurringSchedule` feature in pyschlage can set a code active only during specific hours/days, effectively "disabling" it outside that window. But this is not configurable through HA services.

The Z-Wave lock pattern of "enable/disable slot" does not exist in the Schlage cloud integration.

---

## 10. Complete Entity Inventory

**Platforms registered:** `binary_sensor`, `lock`, `select`, `sensor`, `switch`

| Platform | Entity | Read/Write | Notes |
|---|---|---|---|
| lock | `lock.schlage_front_door_deadbolt` | R/W | lock/unlock; `supported_features=0` |
| binary_sensor | `binary_sensor.schlage_front_door_deadbolt_keypad_disabled` | R | problem sensor |
| sensor | `sensor.schlage_front_door_deadbolt_battery` | R | battery % |
| select | `select.schlage_front_door_deadbolt_auto_lock_time` | R/W | 0/5/15/30/60/120/240/300 seconds |
| switch | `switch.schlage_front_door_deadbolt_keypress_beep` | R/W | audible beep on keypress |
| switch | `switch.schlage_front_door_deadbolt_1_touch_locking` | R/W | lock with single touch |

---

## 11. Implications for SlotSentry

Based on this research, the following design constraints apply when building against the Schlage integration:

1. **No slot numbers.** SlotSentry cannot use slot indices. Code identity must be tracked by name (and optionally by UUID from `get_codes`).

2. **No native enable/disable.** A "disable without delete" pattern requires either the delete+re-add approach or a future enhancement to pyschlage that wraps the `disabled` field in an HA service. For now, design around delete+re-add if soft-disable is needed.

3. **`get_codes` returns name and PIN value.** If SlotSentry needs to store PINs (e.g., for re-add after delete), it must store them securely, as `get_codes` does return the actual PIN digits.

4. **Duplicate detection is by name AND value.** `add_code` rejects codes where either the name or the PIN already exists. SlotSentry must handle `ServiceValidationError` for both conditions.

5. **30-second polling.** State may lag up to 30 seconds after a code add/delete. However, the integration does request an immediate coordinator refresh after each code operation, so lag should typically be under a few seconds in practice.

6. **Deletion is idempotent.** Calling `delete_code` for a non-existent name is safe and raises no error.

7. **Keypad disabled is observable but not controllable.** SlotSentry can alert on this condition but cannot programmatically clear it.
