# SlotSentry LockBackend Protocol — Design Review

**Version:** 1.0
**Date:** 2026-04-01
**Status:** Review
**Scope:** Evaluate the current `LockBackend` protocol against both Z-Wave (Phase 1) and Schlage cloud (future) lock types. Identify minimal changes to make now, before Phase 1 coding begins, that future-proof the architecture without over-engineering.

---

## Table of Contents

1. [Current Protocol Gaps](#1-current-protocol-gaps)
2. [Proposed Protocol Changes](#2-proposed-protocol-changes)
3. [Label as Identifier](#3-label-as-identifier)
4. [Slot Number Semantics](#4-slot-number-semantics)
5. [Lock Commit Arrays](#5-lock-commit-arrays)
6. [Code Length Implications](#6-code-length-implications)
7. [Keypad Lockout](#7-keypad-lockout)
8. [Readback and Verification](#8-readback-and-verification)
9. [Recommended Changes to Make Now](#9-recommended-changes-to-make-now)
10. [What to Defer](#10-what-to-defer)

---

## 1. Current Protocol Gaps

The current `LockBackend` protocol from PROJECT_PLAN.md:

```python
class LockBackend(Protocol):
    async def async_set_usercode(self, slot: int, code: str) -> bool: ...
    async def async_clear_usercode(self, slot: int) -> bool: ...
    async def async_get_usercode(self, slot: int) -> str | None: ...
    @property
    def supports_readback(self) -> bool: ...
```

### Gap 1: Slot-only addressing

Every method takes `slot: int` as the sole identifier. Z-Wave locks use slot numbers to address codes on the physical lock, so this works for Phase 1. However, the Schlage cloud API identifies codes by **name** (via `add_access_code(AccessCode)` and `delete()` on an AccessCode object found by name). The cloud lock has no concept of slot numbers -- codes are an unordered bag identified by `access_code_id` and `name`.

The current protocol provides no way to pass a label/name to the backend, so a Schlage cloud shim would have no idea what name to use when calling `add_access_code()`.

### Gap 2: No slot metadata on set

`async_set_usercode(slot, code)` passes only the slot number and code. The Schlage cloud backend needs at minimum the label (name) to create the code on the lock. Without it, the shim would have to fabricate names like "Slot 3" which defeats the purpose of the label field in SlotSentry.

### Gap 3: No delete-by-identity

`async_clear_usercode(slot)` assumes the backend can identify which code to delete by slot number. The Schlage cloud API deletes by `access_code_id` (looked up by name). The shim needs a way to know which code to delete -- either by label, or by maintaining its own internal name-to-id mapping.

### Gap 4: Readback model assumes single-slot queries

`async_get_usercode(slot)` assumes codes can be fetched one at a time by slot index. The Schlage cloud API returns ALL codes at once via `get_access_codes()`. This is not a blocker (the shim can cache and index) but it is an efficiency consideration -- calling get_access_codes() 19 times to verify 19 slots is wasteful when one call returns everything.

### Gap 5: No capability advertisement beyond readback

`supports_readback` is the only capability flag. Other backend differences are not surfaced:
- Does the backend support per-code enable/disable (Schlage cloud: `AccessCode.disabled` field) vs. requiring clear/re-set (Z-Wave)?
- Does the backend accept variable code lengths or enforce a specific range?
- Does the backend use slot-based or name-based addressing?
- Can the backend return all codes in one call?

---

## 2. Proposed Protocol Changes

The key insight from the project architect is correct: **the SlotManager should always work with slots that have both a number and a label. The LockBackend shim translates.** The protocol methods should pass enough context for either backend type to do its job.

### Revised Protocol (recommended for Phase 1)

```python
@dataclass
class SlotInfo:
    """Context passed to LockBackend methods for each slot operation."""
    slot_number: int          # 1-based index (physical slot for Z-Wave, array index for cloud)
    label: str                # Human-readable label for this slot
    # Future fields can be added here without changing method signatures


class LockBackend(Protocol):
    """Protocol that all lock backend implementations must satisfy.

    The SlotManager calls these methods. Each backend translates
    to the appropriate lock-specific API:
    - Z-Wave: uses slot_info.slot_number, ignores label
    - Schlage cloud: uses slot_info.label as the code identifier,
      slot_number is just the internal array index
    """

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        """Push a code to the lock for the given slot."""
        ...

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        """Clear/delete the code for the given slot from the lock."""
        ...

    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None:
        """Read back the code for the given slot, if supported.

        Returns the code string if readable, None if slot is empty
        or readback is not supported.
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
        """
        ...
```

### Why SlotInfo instead of adding parameters

Wrapping context in a `SlotInfo` dataclass is preferable to adding `label` as a second parameter because:

1. **Extensibility**: future backends may need additional context (e.g., `expires_at` for temporary codes, `disabled` flag for Schlage cloud). Adding fields to `SlotInfo` does not change method signatures.
2. **Clean call sites**: the SlotManager already has the full Slot object; constructing a `SlotInfo` from it is trivial.
3. **Backward compatible**: adding a field to `SlotInfo` with a default value does not break existing backends.

### ZWaveJSBackend (Phase 1 -- unchanged behavior)

```python
class ZWaveJSBackend:
    """Z-Wave JS lock backend. Uses slot_number for all operations."""

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        # Calls zwave_js.set_lock_usercode with code_slot=slot_info.slot_number
        # Ignores slot_info.label entirely
        ...

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        # Calls zwave_js.clear_lock_usercode with code_slot=slot_info.slot_number
        ...

    @property
    def addressing_mode(self) -> str:
        return "slot"
```

### Future SchlageCloudBackend (not built in Phase 1)

```python
class SchlageCloudBackend:
    """Schlage cloud lock backend. Uses label as code name."""

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool:
        # Calls lock.add_access_code(AccessCode(name=slot_info.label, code=code))
        # If code with that name already exists, updates it via save()
        # slot_info.slot_number is ignored for lock communication
        ...

    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool:
        # Finds code by name matching slot_info.label, calls code.delete()
        ...

    @property
    def addressing_mode(self) -> str:
        return "name"
```

---

## 3. Label as Identifier

### The bridge between slot-based and name-based protocols

The `label` field in SlotSentry's data model serves dual purpose:

- **Z-Wave locks**: label is purely cosmetic. It is displayed in the SlotSentry UI only. The lock hardware knows nothing about it. The slot number is the physical identifier.
- **Schlage cloud locks**: label IS the identifier sent to the lock. The Schlage cloud API `add_access_code(name, code)` requires a name; that name becomes the code's identity on the lock.

This means the label field is the natural bridge -- it already exists in the data model, and SlotSentry already has UI for editing it. No new fields are needed.

### Rename implications on Schlage cloud

When a user changes a label on a slot that is synced to a Schlage cloud lock, the shim must:

1. Delete the old code (by old name) from the lock.
2. Add the new code (with new name) to the lock.

This is a destructive rename -- effectively a delete + re-add. The commit machine should treat a label change on a name-based lock as a code change (marking the lock commit as `out_of_sync`), even though on a Z-Wave lock a label change is disk-only and does not touch the lock.

### Recommended Phase 1 handling

In the current data model, label changes are described as "disk-only; labels do not affect lock commit state" (PRODUCT_SPEC section 7.4.4). This is correct for Z-Wave. For Phase 1:

- **Keep this behavior** -- label changes do not dirty lock commit arrays.
- **Add a note in the code** (comment, not implementation) that name-based backends will need to treat label changes as lock-dirtying events.
- The `addressing_mode` property on the backend is the hook: when the SlotManager processes a label change, it can check `backend.addressing_mode` and conditionally dirty the lock commit state. This logic is not needed until a name-based backend is built.

### Label uniqueness

Schlage cloud does not enforce unique names on codes (you can have two codes named "Guest"). However, SlotSentry's `delete_code` operation uses name matching, and the HA Schlage integration normalizes names (lowercase, stripped) for delete. If two codes share a name, delete becomes ambiguous.

**Recommendation for Phase 1**: Add a uniqueness constraint on labels in the SlotManager validation. Labels must be unique across all non-empty slots. This prevents the ambiguity problem on name-based locks and is also good UX for Z-Wave (prevents confusion). Empty labels (for unassigned slots) are exempt from the uniqueness check.

### Label required for name-based locks

On Z-Wave, an empty label is fine -- the slot number is the identifier. On Schlage cloud, a code MUST have a name. The SlotManager should enforce that name-based backends cannot push a slot with an empty label. This validation belongs in the commit machine, not the UI layer, and is only needed when a name-based backend is configured.

**Recommendation for Phase 1**: No action. Z-Wave allows empty labels. Add a validation hook in the commit machine that name-based backends can activate.

---

## 4. Slot Number Semantics

### Z-Wave: slot number = physical address

On Z-Wave locks, slot number is the hardware's code slot index. `set_lock_usercode(code_slot=3, usercode="1234")` writes to physical slot 3 on the lock. The slot number has meaning to the lock firmware.

### Schlage cloud: slot number = internal array index

Schlage cloud locks have no concept of slot numbers. Codes are an unordered collection identified by `access_code_id` (a UUID-like string) and `name`. When SlotSentry assigns slot number 3 to a Schlage cloud code, that number is purely an internal organizational index -- it means "the 3rd row in the SlotSentry grid."

### How this works in practice

The SlotManager always works with slot numbers 1 through N. It does not care whether the backend interprets the slot number as a physical address or ignores it. The `SlotInfo` dataclass passes both the slot number and the label; the backend uses whichever is appropriate.

The `addressing_mode` property makes this explicit:
- `"slot"` backends use `slot_info.slot_number` for lock operations.
- `"name"` backends use `slot_info.label` for lock operations.

### Edge case: slot count

For Z-Wave, slot count is bounded by physical hardware (e.g., 19 slots on FE599). For Schlage cloud, the lock may accept an unlimited (or very large) number of codes. When mixing Z-Wave and Schlage cloud locks:

- The slot count is still the minimum across all configured locks.
- If the minimum comes from a Z-Wave lock, Schlage cloud codes beyond that count are simply not managed by SlotSentry.
- If all locks are Schlage cloud, the slot count would need a different source. The simplest approach is to set a configurable maximum (e.g., 30) in the config flow when no Z-Wave locks are selected.

**Recommendation for Phase 1**: No changes needed. All current locks are Z-Wave, so slot count is determined by hardware. The config flow already stores slot_count from discovery. When a cloud backend is added, the config flow step can offer a user-configurable slot count if no hardware-constrained locks are present.

---

## 5. Lock Commit Arrays

### Current design

Per-lock commit arrays track sync state per slot:

```
lock_commit["lock.front_door"][slot_number] = {
    state: "synced" | "out_of_sync" | "uncertain" | "error",
    code_hash: "sha256:...",
    last_push: "2026-03-31T14:25:00Z",
    ...
}
```

This design works for both lock types because:

1. The commit array is keyed by slot_number, which exists for both Z-Wave (physical) and cloud (internal index).
2. The `code_hash` comparison works regardless of backend -- it compares the hash of what was last successfully pushed against the current slot code.
3. The state machine transitions are backend-agnostic.

### Name-based lock: additional tracking

For a Schlage cloud lock, the commit array may also need to track the **name that was last pushed** so that rename detection works:

```python
# Future extension to LockSlotCommit:
last_pushed_label: str | None  # Label used in the last successful push to this lock
```

When the SlotManager detects that `slot.label != lock_commit[slot].last_pushed_label` AND `backend.addressing_mode == "name"`, it marks the slot as `out_of_sync` for that lock (even if the code itself has not changed).

**Recommendation for Phase 1**: Do not add `last_pushed_label` yet. It is only relevant for name-based backends. However, design the `LockSlotCommit` dataclass as extensible (use a class, not a bare dict) so adding this field later is a non-breaking schema migration.

### Mixed-backend commit flow

When SlotSentry manages both a Z-Wave lock and a Schlage cloud lock simultaneously:

1. User edits slot 3 label from "Guest" to "Airbnb Guest" and changes the code.
2. Commit machine marks all locks as `out_of_sync` for slot 3 (code changed).
3. Z-Wave push: calls `set_lock_usercode(slot=3, code="5678")`. Label is irrelevant.
4. Schlage push: calls `delete_code("Guest")` then `add_code("Airbnb Guest", "5678")`.

Both locks process independently. The commit array for each lock tracks its own state. This is already how the architecture works -- one task per lock, sequential slots per lock.

---

## 6. Code Length Implications

### Z-Wave: fixed per lock

Z-Wave locks enforce a specific code length. The FE599 accepts exactly 4 digits. The BE469ZP is configurable (4-8 digits, currently set to 6). A code of the wrong length is rejected at push time by the lock firmware.

SlotSentry's dual-code-length feature (long + short) is designed to handle this: the commit machine knows each lock's code length capability and pushes the appropriate code field (long_code or short_code).

### Schlage cloud: 4-8 digits

The Schlage cloud API accepts codes 4-8 digits long (enforced by regex `^\d{4,8}$` in the HA integration). There is no per-lock code length configuration -- any valid-length code works. The Schlage cloud lock is naturally flexible.

### How the shim handles this

The `ZWaveJSBackend` does not validate code length itself -- it passes the code to the Z-Wave JS service, and the lock firmware rejects incompatible lengths. The commit machine then reports the failure.

A future `SchlageCloudBackend` would:
- Accept any code 4-8 digits long.
- Not need the long_code/short_code distinction (any single code field works).
- The shim picks whichever code field is populated. If both are populated (dual-length mode), the shim should pick the one that matches the lock's preference -- but since Schlage cloud has no preference, a deterministic rule is needed (e.g., prefer long_code, fall back to short_code).

### Recommendation for Phase 1

No changes. The current dual-code-length model with per-lock code_type selection already supports this. The commit machine already matches code fields to lock capabilities. A future Schlage cloud lock would be configured as `code_type: "both"` (accepting either length) or `code_type: "long"` (using only the long code field).

One consideration: add a `supported_code_lengths` property to the `LockBackend` protocol:

```python
@property
def supported_code_lengths(self) -> tuple[int, ...] | None:
    """Tuple of supported code lengths, or None if any length 4-8 is accepted."""
    ...
```

This allows the commit machine to pre-validate before attempting a push, giving better error messages ("Code length 4 is not supported by this lock" vs. a cryptic Z-Wave error). For Phase 1, `ZWaveJSBackend` returns a tuple based on the lock's discovered capabilities; a future Schlage backend returns `None` (accepts all).

---

## 7. Keypad Lockout

### Z-Wave: `invoke_cc_api` with Door Lock CC

The current design uses `invoke_cc_api` with the Door Lock Command Class to set the operating mode to "Secured" (disabling keypad input). This is a direct hardware command through Z-Wave.

### Schlage cloud: read-only `binary_sensor.keypad_disabled`

Based on investigation of this HA instance and the HA Schlage integration source:

- **Entity exists**: `binary_sensor.schlage_front_door_deadbolt_keypad_disabled` (currently `off`)
- **Device class**: `problem` (diagnostic entity)
- **Read-only**: The HA Schlage integration provides no service to enable/disable the keypad. The binary sensor only reports the current state.
- **Hardware behavior**: The Schlage cloud lock's keypad disables automatically after too many failed PIN attempts. It re-enables after a timeout. This is a lock firmware safety feature, not a user-controllable setting.
- **pyschlage library**: The `keypad_disabled()` method is read-only. There is no `set_keypad_disabled()` or equivalent method.

### Conclusion: keypad lockout is NOT possible on Schlage cloud locks

The Schlage cloud API does not expose a keypad enable/disable control. The keypad lockout feature in SlotSentry cannot be extended to Schlage cloud locks via the same mechanism.

**Alternative approaches for Schlage cloud (all have drawbacks)**:

| Approach | Feasibility | Problem |
|----------|-------------|---------|
| Delete all codes to simulate lockout | Technically possible | Destructive; re-adding codes takes multiple API calls and cloud latency |
| Set all codes to `disabled` via AccessCode.disabled field | Possible via pyschlage | Not exposed in HA Schlage integration services currently |
| Use a different lock attribute | No suitable candidate | No keypad control API exists |

The `AccessCode.disabled` field in pyschlage is the most promising future avenue. If the HA Schlage integration adds a service to disable/enable individual codes (or if SlotSentry talks to pyschlage directly), then keypad lockout could be simulated by disabling all codes rather than disabling the keypad hardware.

### Recommendation for Phase 1

No changes. Keypad lockout is a Phase 2 feature and only targets Z-Wave locks. When the Schlage cloud backend is built:

1. Add a `supports_keypad_lockout` property to `LockBackend`:
   ```python
   @property
   def supports_keypad_lockout(self) -> bool:
       """True if this lock supports programmatic keypad disable."""
       ...
   ```
2. Z-Wave backend: returns `True`.
3. Schlage cloud backend: returns `False` (until a disable mechanism is available).
4. The lockout monitor skips locks whose backend reports `False`, same as the per-lock participation checkbox already allows.

---

## 8. Readback and Verification

### Z-Wave readback (current)

- **BE469ZP**: Full readback. `invoke_cc_api` with User Code CC `get` returns the actual code digits. Verification compares returned code against what was pushed.
- **FE599**: Masked readback. Returns `****` (asterisks). Verification can only confirm "slot is occupied" or "slot is available", not that the correct code is stored.
- **supports_readback**: `True` for BE469ZP, `False` for FE599.

### Schlage cloud readback

The Schlage cloud API via `get_access_codes()` returns ALL codes with their actual digits, names, and metadata. This is full readback with 100% accuracy -- the cloud is the source of truth.

However, the readback model differs:
- **Z-Wave**: per-slot queries (`get_usercode(slot=3)`)
- **Schlage cloud**: bulk query (`get_access_codes()` returns a list)

### Verification strategy per backend

| Backend | Verification Method | Confidence |
|---------|---------------------|------------|
| Z-Wave (BE469ZP) | Read slot N, compare code digits | High -- exact match |
| Z-Wave (FE599) | Read slot N, check occupied/available | Medium -- status only |
| Schlage cloud | Bulk read all codes, find by name, compare code | High -- exact match |

### Proposed enhancement: bulk readback

Add an optional bulk readback method to the protocol:

```python
class LockBackend(Protocol):
    ...

    async def async_get_all_usercodes(self) -> dict[int, str | None] | None:
        """Read all codes from the lock at once.

        Returns a dict of {slot_number: code_or_None}, or None if bulk
        readback is not supported (caller should fall back to per-slot).

        For name-based backends, the slot_number key is resolved by
        matching code names against labels in the SlotManager.
        """
        ...
```

- **ZWaveJSBackend**: returns `None` (Z-Wave does not support bulk readback efficiently).
- **SchlageCloudBackend**: calls `get_access_codes()`, maps names to slot numbers via the SlotManager's label-to-slot mapping, returns the full dict.

The commit machine can use this to verify all slots in one call instead of N individual calls.

### Recommendation for Phase 1

Add `async_get_all_usercodes` to the protocol with a default return of `None`. The commit machine checks: if bulk readback returns a dict, use it for verification; otherwise fall back to per-slot `async_get_usercode`. The Z-Wave backend returns `None` so Phase 1 behavior is unchanged.

This is a small addition that makes the Schlage cloud backend significantly more efficient when it is built.

---

## 9. Recommended Changes to Make Now

These are minimal, low-risk changes to implement in Phase 1 that prevent design debt:

### 9.1 Replace bare parameters with SlotInfo dataclass

**Change**: Instead of `async_set_usercode(self, slot: int, code: str)`, use `async_set_usercode(self, slot_info: SlotInfo, code: str)`.

**Cost**: Trivial. One small dataclass, and the Z-Wave backend simply reads `slot_info.slot_number`.

**Benefit**: Extensible. Future backends get whatever context they need without method signature changes.

```python
@dataclass
class SlotInfo:
    slot_number: int
    label: str
```

### 9.2 Add `addressing_mode` property to LockBackend

**Change**: Add `addressing_mode` property returning `"slot"` for Z-Wave.

**Cost**: One property, one line in Z-Wave backend.

**Benefit**: The SlotManager can branch on this for label-change dirtying logic, validation rules, etc. It is the single discriminator between slot-based and name-based backends.

### 9.3 Add `async_get_all_usercodes` with default None

**Change**: Add optional bulk readback method to LockBackend protocol.

**Cost**: One method that returns `None` in the Z-Wave backend. Commit machine adds a 3-line check.

**Benefit**: When the Schlage backend is built, it can return all codes in one API call instead of N individual calls.

### 9.4 Enforce label uniqueness in SlotManager

**Change**: `async_set_slot()` rejects duplicate labels across non-empty slots.

**Cost**: A few lines of validation in SlotManager.

**Benefit**: Prevents name collision problems on name-based backends. Also improves UX on Z-Wave (no confusion between slots).

### 9.5 Use a dataclass (not bare dict) for LockSlotCommit

**Change**: Define `LockSlotCommit` as a Python dataclass rather than a raw dict in storage.

**Cost**: Standard practice; no extra effort.

**Benefit**: Adding `last_pushed_label` or other fields later is a clean schema migration, not a dict key hunt.

### 9.6 Add `supported_code_lengths` to LockBackend

**Change**: Property returning a tuple of accepted code lengths, or `None` for "any length 4-8".

**Cost**: One property. Z-Wave backend returns the discovered length tuple.

**Benefit**: Commit machine can pre-validate codes before attempting a push, giving clear error messages.

### Summary of Phase 1 protocol

```python
@dataclass
class SlotInfo:
    """Context for a single slot operation."""
    slot_number: int
    label: str


class LockBackend(Protocol):
    """Protocol for lock backends. Implementations translate
    SlotManager operations to lock-specific APIs."""

    async def async_set_usercode(self, slot_info: SlotInfo, code: str) -> bool: ...
    async def async_clear_usercode(self, slot_info: SlotInfo) -> bool: ...
    async def async_get_usercode(self, slot_info: SlotInfo) -> str | None: ...
    async def async_get_all_usercodes(self) -> dict[int, str | None] | None: ...

    @property
    def supports_readback(self) -> bool: ...

    @property
    def addressing_mode(self) -> str: ...

    @property
    def supported_code_lengths(self) -> tuple[int, ...] | None: ...
```

---

## 10. What to Defer

These items are only relevant when the Schlage cloud backend is actually built. Do NOT implement them in Phase 1:

### 10.1 SchlageCloudBackend implementation

No code for the Schlage cloud shim. The protocol is ready; the implementation waits until there is a concrete need.

### 10.2 Label-change dirtying logic

The logic that marks lock commit arrays as `out_of_sync` when a label changes on a name-based lock. In Phase 1, label changes remain disk-only. The `addressing_mode` property is the hook for adding this later -- a simple `if backend.addressing_mode == "name"` check in the SlotManager.

### 10.3 `last_pushed_label` field in LockSlotCommit

Only needed for name-based rename detection. Add via schema migration when the Schlage backend is built.

### 10.4 Name-to-access_code_id mapping

The Schlage cloud backend will need to maintain an internal mapping of `{label: access_code_id}` to efficiently update and delete codes. This is entirely internal to the Schlage backend class and does not affect the protocol.

### 10.5 Keypad lockout for cloud locks

As established in section 7, there is currently no API to programmatically disable a Schlage cloud lock's keypad. The `supports_keypad_lockout` property can be added when the lockout feature (Phase 2) is built. Even then, the Schlage backend will return `False` until an API mechanism exists.

### 10.6 Config flow changes for backend selection

The config flow currently discovers Z-Wave locks only. When a second backend type is added, the config flow will need a backend selector step and lock discovery per backend type. This is Phase 3 scope (Task 3.1 already plans for a `backend_type` field in the config entry).

### 10.7 AccessCode.disabled flag for per-code enable/disable

The Schlage cloud `AccessCode` has a `disabled` boolean that can be toggled via `save()`. This is a cleaner enable/disable mechanism than clear/re-set. However, it is not exposed in the HA Schlage integration's services, so using it would require either:
- Adding a service to the HA Schlage integration (upstream PR)
- Calling pyschlage directly (adding a dependency and auth management)

Defer entirely. The clear/re-set pattern works universally and is already the design for Z-Wave.

### 10.8 Slot count for cloud-only configurations

If all configured locks are cloud-based (no Z-Wave), slot count cannot be auto-detected from hardware. The config flow would need a manual slot count input. Defer until a cloud backend exists.

---

## Appendix A: Schlage Cloud Integration Reference

Gathered from the live HA instance (`lock.schlage_front_door_deadbolt`) and HA core source.

### Entities on this instance

| Entity | Domain | State |
|--------|--------|-------|
| `lock.schlage_front_door_deadbolt` | lock | locked |
| `binary_sensor.schlage_front_door_deadbolt_keypad_disabled` | binary_sensor | off |
| `sensor.schlage_front_door_deadbolt_battery` | sensor | 82% |
| `switch.schlage_front_door_deadbolt_keypress_beep` | switch | on |
| `switch.schlage_front_door_deadbolt_1_touch_locking` | switch | on |
| `select.schlage_front_door_deadbolt_auto_lock_time` | select | 240 |

### HA Schlage integration services

| Service | Parameters | Notes |
|---------|-----------|-------|
| `schlage.get_codes` | target: lock entity | Returns all codes with names and values |
| `schlage.add_code` | target: lock entity, name: str, code: str (4-8 digits) | Creates code identified by name |
| `schlage.delete_code` | target: lock entity, name: str (case-insensitive) | Deletes code found by name |

### pyschlage AccessCode model

| Field | Type | Description |
|-------|------|-------------|
| `access_code_id` | str | Unique ID (server-assigned) |
| `name` | str | User-specified name (used as identifier in HA services) |
| `code` | str | The PIN digits |
| `device_id` | str | Lock device ID |
| `disabled` | bool | Whether the code is inactive |
| `notify_on_use` | bool | Send notification when code is used |
| `schedule` | Schedule or None | Temporal schedule for the code |

Methods: `save()` (update), `delete()` (remove)

### Key differences from Z-Wave

| Aspect | Z-Wave | Schlage Cloud |
|--------|--------|---------------|
| Code addressing | Slot number (physical) | Name (string) |
| Code length | Fixed per lock model | Any 4-8 digits |
| Readback | Per-slot; some locks mask codes | Bulk; all codes returned with values |
| Keypad disable | invoke_cc_api Door Lock CC | Not controllable (read-only sensor) |
| Per-code disable | Not reliable (status 0x02 ignored) | AccessCode.disabled field (not in HA services) |
| Slot count | Hardware-limited | Unlimited (practical limit unknown) |
| Latency | Local Z-Wave mesh (~1-5s) | Cloud API (~2-10s) |
| Offline operation | Works (Z-Wave is local) | Fails (requires internet) |

---

## Appendix B: Decision Log

| Decision | Rationale |
|----------|-----------|
| Pass SlotInfo dataclass instead of bare int | Extensible without signature changes; trivial cost |
| Add addressing_mode property | Single discriminator for backend-type-specific logic |
| Add bulk readback method | Prevents N+1 API calls for cloud verification |
| Enforce label uniqueness | Prevents name collision on cloud locks; better UX on Z-Wave |
| Defer label-change dirtying | No name-based backend in Phase 1; adds complexity with no benefit yet |
| Defer keypad lockout for cloud | No API exists; cannot be implemented |
| Defer AccessCode.disabled usage | Not exposed in HA integration; clear/re-set is universal |

---

*End of SlotSentry LockBackend Protocol Design Review v1.0*
