# SlotSentry — Home Assistant Integration Quality Standards

**Document version:** 1.0
**Last updated:** 2026-03-31
**Target:** Gold quality at first publish; Platinum as stretch goal

---

## Overview

The Home Assistant Integration Quality Scale is a formal framework for grading
integrations based on user experience, feature completeness, code quality, and
developer experience. There are four progressive tiers: **Bronze, Silver, Gold,
and Platinum**. To reach a tier, the integration must fulfill all rules of that
tier AND all rules of every tier below it.

The quality scale was formally introduced in HA 2024.11 and is now the gating
requirement for new core integrations. While the scale officially applies to
core integrations (those shipped with HA), HACS-distributed integrations that
aspire to this standard benefit greatly: it produces more reliable, more
maintainable, and more user-friendly integrations that are better candidates
for future promotion to core.

This document maps every quality scale rule to SlotSentry, records our
target status (MVP, Phase 2, Exempt, or N/A), and provides implementation
guidance specific to SlotSentry's architecture.

---

## Formal Applicability to HACS Integrations

The HA quality scale is formally enforced only for core (bundled) integrations.
HACS integrations are NOT required to meet it. However:

- The rules represent best practices that directly improve user outcomes.
- Any future promotion to core would require meeting at least Bronze at submission.
- Gold-level HACS integrations receive much better community reception.
- The `quality_scale.yaml` file can be included in any integration and is
  understood by tooling and reviewers even when not enforced by hassfest.

**SlotSentry's stance:** We treat the quality scale as a firm development
standard, not an optional aspiration. Our target is Gold at v1.0 publish,
with Platinum achievable in a near-term follow-up.

---

## Quality Scale Checklist

The tables below list every rule, its tier, what it means, how it applies to
SlotSentry, and our implementation target.

**Status legend:**
- `[MVP]` — Required for our v1.0 launch (no exceptions)
- `[P2]` — Phase 2 (post-MVP, before Gold publish)
- `[EXEMPT]` — Does not apply; we will document the exemption reason in `quality_scale.yaml`
- `[STRETCH]` — Platinum goal, not required for Gold publish

---

## Bronze Tier (18 Rules)

All Bronze rules are hard requirements for our v1.0 launch. No Bronze rule
should be deferred to Phase 2.

### B-01 · action-setup

**Rule:** Service actions (custom HA services) must be registered in
`async_setup`, not in `async_setup_entry`. Actions registered in
`async_setup_entry` are lost when the config entry is unloaded.

**SlotSentry application:** SlotSentry will expose service actions such as
`slotsentry.push_all` and `slotsentry.retry_failed`. These must be registered
in `async_setup` in `__init__.py`, not in the per-entry setup.

**Status:** `[MVP]`

**Implementation note:** If SlotSentry has NO service actions at MVP (only
buttons that call internal methods), this rule may be marked `exempt` in
`quality_scale.yaml` with the reason "integration does not register service
actions". Revisit when actions are added.

---

### B-02 · appropriate-polling

**Rule:** Polling-based integrations must use appropriate intervals. The
interval should be set programmatically based on what makes sense for the
device/service — it must NOT be user-configurable, and must not poll more
frequently than the data actually changes.

**SlotSentry application:** SlotSentry is primarily event-driven (Z-Wave JS
events), not polled. The `DataUpdateCoordinator` (if used) should poll at an
interval appropriate to lock state changes — once per minute at most for sync
status checks.

**Status:** `[MVP]`

**Implementation note:** Use `async_track_state_change_event` for Z-Wave lock
state changes rather than polling. If a coordinator is used for health checks,
set `update_interval = timedelta(minutes=1)` or longer. Document the reasoning
in a comment.

---

### B-03 · brands

**Rule:** The integration must have branding assets — an icon and/or logo —
registered in the HA brands repository (for core integrations). For HACS
integrations, this means having a recognizable icon in `custom_components/
slotsentry/brands/` or as the standard `icon.png`.

**SlotSentry application:** We need a `brands/` directory with `icon.png`
(256x256) and optionally `icon@2x.png` (512x512). A lock-with-slots or
keypad icon is appropriate. The brand icon appears in the integration card
in Settings > Devices & Services.

**Status:** `[MVP]`

**Implementation note:** Create `/homeassistant/claudeSrc/SlotSentry/
custom_components/slotsentry/brands/icon.png`. SVG source should be kept in
`/docs/assets/` for future edits. A simple padlock with a grid overlay or
numbered slots would communicate the product clearly.

---

### B-04 · common-modules

**Rule:** Common patterns and shared constants must live in dedicated modules
rather than being duplicated across files. Specifically:
- Constants go in `const.py`
- Data update logic goes in `coordinator.py`
- Entity base classes go in `entity.py`
- Do not define the same string or value in multiple files

**SlotSentry application:** We already planned this structure. Enforce it:
- `const.py` — all domain strings, service names, attribute names, storage keys
- `coordinator.py` — `SlotSentryCoordinator` with all data fetching
- `entity.py` — `SlotSentryEntity` base class

**Status:** `[MVP]`

---

### B-05 · config-flow

**Rule:** The integration must be configurable via the UI (Settings > Devices &
Services > Add Integration), not only via YAML. A `config_flow.py` with a
`ConfigFlow` class is required.

**SlotSentry application:** This is a core requirement. Our config flow covers:
1. Lock discovery and selection (multi-select of discovered Z-Wave locks)
2. Code length configuration (one length or two, with ranges)
3. Optional lockout trigger selection for keypad lockout
4. Secure mode toggle (with password setup sub-flow)

**Status:** `[MVP]`

**Implementation note:** Use `vol.Schema` with `selector` types for all form
fields. Lock selection should use `entity` selectors filtered to `lock` domain.
Sensor selection should use `entity` selector with no domain filter (user picks
any binary_sensor or input_boolean).

---

### B-06 · config-flow-test-coverage

**Rule:** The config flow must have full test coverage — every step, every
error path, every branch.

**SlotSentry application:** Write `tests/test_config_flow.py` covering:
- Happy path: complete setup with all options
- No locks found (abort flow with error)
- Lock selection, then secure mode enable path
- Lock selection, then secure mode disable (skip)
- Code length: single mode
- Code length: dual mode with valid ranges
- Abort on duplicate config entry (unique_config_entry rule)
- Options flow: add lock, remove lock, change code length

**Status:** `[MVP]`

**Target coverage:** 100% of config flow branches.

---

### B-07 · dependency-transparency

**Rule:** External dependencies must be declared clearly. The `manifest.json`
`requirements` array must list all Python packages. Dependencies must be
available on PyPI. No vendored or bundled library code.

**SlotSentry application:** SlotSentry does not use external Python libraries
beyond HA's built-in integrations (zwave_js services). If cryptography is
needed for secure mode (Fernet/AES), `cryptography` must be listed in
`requirements`.

**Status:** `[MVP]`

**Implementation note:**
```json
"requirements": ["cryptography>=42.0.0"]
```
If we use only HA's built-in `homeassistant.util.encryption` or the
`homeassistant.helpers.storage` encryption support, no external dependency
is needed. Prefer built-ins over adding a dependency.

---

### B-08 · docs-actions

**Rule:** The documentation must describe every service action the integration
provides, including parameters, expected behavior, and example usage.

**SlotSentry application:** Document:
- `slotsentry.push_all` — force push all slots to all locks
- `slotsentry.retry_failed` — retry out-of-sync / uncertain slots
- Any future `slotsentry.set_slot` or `slotsentry.clear_slot` actions

**Status:** `[MVP]` (document alongside implementation)

---

### B-09 · docs-high-level-description

**Rule:** Documentation must include a plain-language description of what the
integration does, what devices or services it works with, and what it enables
the user to accomplish.

**SlotSentry application:** The README and docs landing page must explain:
- What SlotSentry does (Z-Wave lock code management with a sidebar UI)
- Which locks are supported (Z-Wave via Z-Wave JS integration)
- What it enables (named slots, per-person codes, enable/disable without losing codes)

**Status:** `[MVP]`

---

### B-10 · docs-installation-instructions

**Rule:** Documentation must provide step-by-step instructions for installing
the integration.

**SlotSentry application:** Document the HACS custom repository install path:
1. HACS > Integrations > ... > Custom repositories
2. Add `https://github.com/ChrisCaho/SlotSentry`
3. Install SlotSentry
4. Restart HA
5. Settings > Devices & Services > Add Integration > SlotSentry
6. Follow config flow

**Status:** `[MVP]`

---

### B-11 · docs-removal-instructions

**Rule:** Documentation must describe how to remove the integration cleanly,
including any side effects (data loss, state cleanup, etc.).

**SlotSentry application:** Document:
- Go to Settings > Devices & Services > SlotSentry > Delete
- Slot data in `.storage/slotsentry` is retained after removal (user must
  delete manually if desired)
- Codes remain on physical locks (SlotSentry does not clear codes on removal)
- Warn user to manually clear codes if they want the locks code-free

**Status:** `[MVP]`

---

### B-12 · entity-event-setup

**Rule:** Entity event subscriptions (e.g., listening to HA events or state
changes) must be set up in the entity's `async_added_to_hass` lifecycle
method, and torn down in `async_will_remove_from_hass` (or via the returned
cleanup callback).

**SlotSentry application:** The `SlotSentryCoordinator` or individual entities
that listen to Z-Wave JS state changes must subscribe in `async_added_to_hass`
and unsubscribe on removal.

**Status:** `[MVP]`

**Code pattern:**
```python
async def async_added_to_hass(self) -> None:
    await super().async_added_to_hass()
    self.async_on_remove(
        async_track_state_change_event(
            self.hass,
            self._lock_entity_id,
            self._handle_lock_state_change,
        )
    )
```

---

### B-13 · entity-unique-id

**Rule:** Every entity must have a `unique_id` that is stable across restarts
and uniquely identifies the entity within its platform.

**SlotSentry application:** Entity unique IDs should be constructed from
the config entry ID (stable) plus a stable suffix:

```python
# Sensor
self._attr_unique_id = f"{entry.entry_id}_push_status"

# Binary sensor
self._attr_unique_id = f"{entry.entry_id}_suppressed"

# Button - push all
self._attr_unique_id = f"{entry.entry_id}_push_all"

# Button - retry
self._attr_unique_id = f"{entry.entry_id}_retry_failed"
```

**Status:** `[MVP]`

---

### B-14 · has-entity-name

**Rule:** All entities must set `_attr_has_entity_name = True`. This enables
HA to construct the full entity name as `"{Device Name} {Entity Name}"`,
which is the modern HA naming convention. Entities should NOT include the
device/integration name in their `_attr_name`.

**SlotSentry application:**
```python
class SlotSentryEntity(CoordinatorEntity):
    _attr_has_entity_name = True

class SlotSentryPushStatusSensor(SlotSentryEntity):
    _attr_name = "Push Status"  # Full name becomes "SlotSentry Push Status"
```

**Status:** `[MVP]`

---

### B-15 · runtime-data

**Rule:** Data shared between the config entry and its platforms must be stored
in `entry.runtime_data`, not in `hass.data`. This is the modern HA pattern
introduced in 2024.

**SlotSentry application:**
```python
# In __init__.py async_setup_entry:
coordinator = SlotSentryCoordinator(hass, entry)
await coordinator.async_config_entry_first_refresh()
entry.runtime_data = coordinator

# In platform setup (sensor.py, button.py, etc.):
coordinator = entry.runtime_data
```

**Status:** `[MVP]`

**Implementation note:** Use a typed dataclass if runtime_data holds multiple
objects:
```python
@dataclass
class SlotSentryRuntimeData:
    coordinator: SlotSentryCoordinator
    storage: SlotSentryStorage
```

---

### B-16 · test-before-configure

**Rule:** The config flow must test connectivity or availability before
completing setup. If the device or service cannot be reached during config
flow, the flow must fail with a clear error message rather than succeeding
silently.

**SlotSentry application:** During config flow, before accepting the user's
lock selection, verify:
1. The selected lock entities actually exist in HA's entity registry
2. The `zwave_js` integration is loaded and the Z-Wave JS add-on is accessible
   (call a benign service or check entity state)
3. If any selected lock is unavailable, surface a warning (not hard fail —
   the lock may be temporarily unreachable)

**Status:** `[MVP]`

**Implementation note:** Use `try/except` around any service calls in the
config flow with `errors["base"] = "cannot_connect"` pattern. Map error
keys to `strings.json` messages.

---

### B-17 · test-before-setup

**Rule:** During `async_setup_entry`, verify that setup is possible before
completing. Raise `ConfigEntryNotReady` if prerequisites are missing, allowing
HA to retry automatically.

**SlotSentry application:**
```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Check Z-Wave JS integration is available
    if not hass.services.has_service("zwave_js", "set_lock_usercode"):
        raise ConfigEntryNotReady(
            "Z-Wave JS integration is not available. "
            "Ensure the Z-Wave JS add-on is running."
        )
    coordinator = SlotSentryCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    ...
```

**Status:** `[MVP]`

---

### B-18 · unique-config-entry

**Rule:** The same device or service must not be able to be added twice. The
config flow must detect when the user attempts a duplicate setup and abort
with a clear message.

**SlotSentry application:** SlotSentry manages a single set of locks system-wide.
Use a fixed unique ID (e.g., the HA instance UUID or a constant) to prevent
duplicate entries:

```python
class SlotSentryConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        ...
```

**Status:** `[MVP]`

---

## Silver Tier (10 Rules)

Silver rules must be met before the v1.0 Gold-targeted publish. A few Silver
rules (particularly `integration-owner` and `test-coverage`) may be deferred
to a point release, but the runtime/reliability rules must be in for v1.0.

---

### S-01 · action-exceptions

**Rule:** Service actions must raise appropriate exceptions when they encounter
failures, rather than silently failing or logging and returning. Use
`ServiceValidationError` for invalid input, `HomeAssistantError` for runtime
failures.

**SlotSentry application:**
```python
async def async_handle_push_all(call: ServiceCall) -> None:
    coordinator: SlotSentryCoordinator = ...
    try:
        await coordinator.push_all_slots()
    except SlotSentryPushError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="push_failed",
        ) from err
```

**Status:** `[MVP]`

---

### S-02 · config-entry-unloading

**Rule:** The integration must support config entry unloading. Implement
`async_unload_entry` to cleanly tear down all platforms, cancel tasks,
unsubscribe from events, and release resources.

**SlotSentry application:**
```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

The coordinator's `async_will_remove_from_hass` handles subscription cleanup.
Any background tasks started in `async_setup_entry` must be cancelled here.

**Status:** `[MVP]`

---

### S-03 · docs-configuration-parameters

**Rule:** Documentation must describe every configuration parameter (options
flow settings) with allowed values, defaults, and effect.

**SlotSentry application:** Document the reconfigure options:
- Code length mode (single/dual)
- Short code length (4-7 if dual)
- Long code length (5-8 if dual)
- Single code length (4-8 if single)
- Secure mode (on/off)
- Per-lock participation in keypad lockout
- Door sensor mapping per lock

**Status:** `[P2]` (document alongside each feature as it's built)

---

### S-04 · docs-installation-parameters

**Rule:** Documentation must describe parameters that are set during initial
install (config flow), not just reconfigure options.

**SlotSentry application:** Document:
- Lock selection (which Z-Wave locks to manage)
- Initial code length config
- Lockout trigger entity for keypad lockout (optional)
- Secure mode setup (optional, with password)

**Status:** `[P2]`

---

### S-05 · entity-unavailable

**Rule:** Entities must be marked unavailable (`_attr_available = False`) when
the underlying device, service, or data source is unreachable. They must not
report stale data as current.

**SlotSentry application:** Entities should be unavailable if:
- Z-Wave JS integration is not loaded
- The coordinator last refresh failed

Using `CoordinatorEntity` handles this automatically:
```python
class SlotSentryEntity(CoordinatorEntity[SlotSentryCoordinator]):
    # available property returns coordinator.last_update_success automatically
    pass
```

For individual lock entities, additionally check if the lock entity itself is
unavailable in HA.

**Status:** `[MVP]`

---

### S-06 · integration-owner

**Rule:** The integration must have at least one active code owner listed.
For core integrations this is `CODEOWNERS`. For HACS integrations, the
`manifest.json` may include the owner, but the key quality requirement is
that someone is maintaining it.

**SlotSentry application:** The manifest already has `"codeowners": []`
for privacy. This rule technically requires at least one owner for Silver
tier. Since SlotSentry is a HACS integration and we have chosen to omit
codeowners for privacy, document this in `quality_scale.yaml` as an
**exemption with reason** rather than a failure.

**Status:** `[EXEMPT]` — HACS integration; codeowner omitted intentionally
for privacy. Chris Caho is the de facto owner via the public GitHub repo.

**quality_scale.yaml exemption:**
```yaml
integration-owner:
  status: exempt
  comment: >-
    HACS custom integration. Codeowner omitted from manifest for privacy.
    The integration is maintained by the GitHub repository owner.
```

---

### S-07 · log-when-unavailable

**Rule:** When a device, service, or API becomes unavailable, log once at
WARNING level. Do not spam the log on every failed poll. Log again at INFO
level when connectivity is restored.

**SlotSentry application:** The `DataUpdateCoordinator` base class handles
this automatically — it logs once on first failure and once on recovery.
For any additional connectivity checks (e.g., Z-Wave JS service availability),
implement a simple state tracker:

```python
self._zwave_unavailable_logged = False

async def _check_zwave(self) -> bool:
    available = self.hass.services.has_service("zwave_js", "set_lock_usercode")
    if not available and not self._zwave_unavailable_logged:
        _LOGGER.warning("Z-Wave JS service is unavailable")
        self._zwave_unavailable_logged = True
    elif available and self._zwave_unavailable_logged:
        _LOGGER.info("Z-Wave JS service is back online")
        self._zwave_unavailable_logged = False
    return available
```

**Status:** `[MVP]`

---

### S-08 · parallel-updates

**Rule:** The integration must declare the number of parallel updates it
supports. This prevents HA from hammering devices with simultaneous requests.

**SlotSentry application:** Set `PARALLEL_UPDATES = 1` in each platform file
(sensor.py, button.py, binary_sensor.py). SlotSentry operations are
inherently sequential (one lock at a time), so 1 is correct.

```python
# At module level in each platform file:
PARALLEL_UPDATES = 1
```

**Status:** `[MVP]`

---

### S-09 · reauthentication-flow

**Rule:** If the integration authenticates with a remote service, it must
implement a reauthentication flow that can be triggered from the UI when
credentials expire or become invalid. Raise `ConfigEntryAuthFailed` to trigger it.

**SlotSentry application:** SlotSentry does not authenticate with a remote
service — it interacts with local Z-Wave JS services via HA's service registry.
There is no authentication that can expire.

However, Secure Mode uses a password as an encryption key. Password change
or recovery is handled through the reconfigure flow, not a reauthentication
flow. This rule is exempt.

**Status:** `[EXEMPT]` — No remote authentication. Z-Wave JS is accessed via
local HA services, no credentials are maintained.

**quality_scale.yaml exemption:**
```yaml
reauthentication-flow:
  status: exempt
  comment: >-
    Integration does not authenticate with any remote service. Local Z-Wave JS
    services are accessed via HA's service registry without credentials.
```

---

### S-10 · test-coverage

**Rule:** All integration modules must have above 95% test coverage.

**SlotSentry application:** This is a hard requirement for Silver. Every module
must be tested:
- `test_config_flow.py` — full config flow coverage (see B-06)
- `test_coordinator.py` — coordinator data fetching, error handling
- `test_sensor.py` — entity state, unavailability
- `test_binary_sensor.py`
- `test_button.py` — action invocation, error paths
- `test_storage.py` — slot read/write, encryption/decryption, schema migration
- `test_init.py` — setup, unload, reload
- `test_lock_backend.py` — Z-Wave push, verify, clear operations

**Status:** `[P2]` — Full 95%+ coverage is a pre-publish gate, not MVP-day.
MVP will have coverage for the critical paths (config flow, push operations,
storage). Full coverage is achieved before Gold publish.

---

## Gold Tier (21 Rules)

Gold is our target for the first public release. All Gold rules below are
either implemented, exempted with reason, or deferred to a specific point
release milestone.

---

### G-01 · devices

**Rule:** The integration must create Device Registry entries. Entities must
be associated with a device, not floating as standalone entities.

**SlotSentry application:** Create a single "SlotSentry" device representing
the integration instance:
```python
device_registry.async_get_or_create(
    config_entry_id=entry.entry_id,
    identifiers={(DOMAIN, entry.entry_id)},
    name="SlotSentry",
    manufacturer="SlotSentry",
    model="Lock Code Manager",
    sw_version=INTEGRATION_VERSION,
)
```

All entities (sensor, binary_sensor, buttons) are associated with this device.

**Status:** `[MVP]`

---

### G-02 · diagnostics

**Rule:** The integration must implement the `diagnostics` platform, providing
a `async_get_config_entry_diagnostics` function that returns sanitized debug
data for troubleshooting.

**SlotSentry application:**
```python
# diagnostics.py
async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: SlotSentryCoordinator = entry.runtime_data
    return {
        "config": {
            "num_locks": len(entry.data[CONF_LOCKS]),
            "code_length_mode": entry.data[CONF_CODE_LENGTH_MODE],
            "secure_mode": entry.data[CONF_SECURE_MODE],
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update": coordinator.last_updated.isoformat()
            if coordinator.last_updated else None,
        },
        "slot_summary": coordinator.get_slot_summary(),  # counts only, no codes
        "lock_sync_status": coordinator.get_lock_sync_status(),
    }
```

**CRITICAL:** Never include PIN codes or passwords in diagnostics output.

**Status:** `[MVP]`

---

### G-03 · discovery

**Rule:** Devices should be automatically discovered when possible (via Zeroconf,
DHCP, USB, Z-Wave, Bluetooth, etc.).

**SlotSentry application:** SlotSentry does not discover hardware directly —
it piggybacks on the Z-Wave JS integration which handles Z-Wave discovery.
SlotSentry discovers available lock entities at setup time by querying the
entity registry. True hardware discovery is not applicable.

**Status:** `[EXEMPT]` — Integration manages HA entities (locks discovered by
Z-Wave JS), not hardware directly. Network/hardware discovery is not applicable.

---

### G-04 · discovery-update-info

**Rule:** When discovery is used to set up a device, the integration must use
the discovery info to update the device's network information (IP address,
host, etc.) in the Device Registry when it changes.

**SlotSentry application:** Not applicable — discovery is exempt (see G-03).

**Status:** `[EXEMPT]` — Follows from discovery exemption.

---

### G-05 · docs-data-update

**Rule:** Documentation must describe how the integration fetches and updates
data: polling interval, push events, webhook, etc.

**SlotSentry application:** Document:
- SlotSentry listens to Z-Wave JS state change events for lock status
- Slot data is stored in `.storage/slotsentry` and loaded on startup
- No polling of external APIs; data push is user-triggered via the panel
- Lock sync verification uses `invoke_cc_api` after each push operation

**Status:** `[P2]`

---

### G-06 · docs-examples

**Rule:** Documentation must provide automation examples the user can use.

**SlotSentry application:** Provide YAML automation examples for:
- Trigger an action when `binary_sensor.slotsentry_suppressed` turns on
- Use `button.slotsentry_push_all` in a script after bulk slot edits
- Example: "Notify when keypad lockout activates"
- Example: "Retry failed pushes automatically at midnight"

**Status:** `[P2]`

---

### G-07 · docs-known-limitations

**Rule:** Documentation must describe known limitations of the integration.

**SlotSentry application:** Document prominently:
- FE599 locks do not return stored codes (firmware masks them) — SlotSentry
  stores the code it set, but cannot verify it was accepted correctly
- Schlage's BE469ZP does not honor Z-Wave per-slot disable (status 0x02) —
  SlotSentry uses clear/re-set pattern instead
- Secure Mode password loss = permanent data loss (no recovery)
- Front Door (BE479 Encode Plus, cloud-based) is out of scope
- Code readback verification is best-effort on FE599 (occupied/available only)

**Status:** `[P2]`

---

### G-08 · docs-supported-devices

**Rule:** Documentation must list known supported and unsupported devices.

**SlotSentry application:** Document the supported hardware matrix:

| Lock | Model | Code Readback | Slot Count | Notes |
|------|-------|---------------|------------|-------|
| Schlage BE469ZP | Z-Wave Plus | Full (actual codes) | 30 | Full support |
| Schlage FE599 | Z-Wave | Masked (occupied/available) | 19 | Supported, limited verify |
| Any Z-Wave lock | via Z-Wave JS | Varies | Varies | Generic support |

Unsupported (out of scope for MVP):
- Schlage BE479 Encode Plus (cloud, not Z-Wave)
- Non-Z-Wave smart locks
- Bluetooth-only locks

**Status:** `[P2]`

---

### G-09 · docs-supported-functions

**Rule:** Documentation must describe all entities provided, their states,
attributes, and what they represent.

**SlotSentry application:** Document each entity:

| Entity | Type | States | Purpose |
|--------|------|--------|---------|
| `sensor.slotsentry_push_status` | Sensor | `idle`, `pushing`, `success`, `partial_fail`, `failed` | Last push operation result |
| `binary_sensor.slotsentry_suppressed` | Binary Sensor | `on`/`off` | Keypad lockout active |
| `button.slotsentry_push_all` | Button | — | Force push all slots to all locks |
| `button.slotsentry_retry` | Button | — | Retry out-of-sync/uncertain slots |

**Status:** `[P2]`

---

### G-10 · docs-troubleshooting

**Rule:** Documentation must provide troubleshooting guidance.

**SlotSentry application:** Document:
- "Codes not updating on lock" → Check push status sensor, try retry button
- "Panel shows no data" → Check config entry is loaded, check HA logs
- "Z-Wave JS not available" → Ensure Z-Wave JS add-on is running
- "Secure mode: forgot password" → Data loss warning, reinit procedure
- How to enable debug logging for SlotSentry
- How to download diagnostics

**Status:** `[P2]`

---

### G-11 · docs-use-cases

**Rule:** Documentation must describe use cases that illustrate why someone
would use this integration.

**SlotSentry application:** Document use cases such as:
- "Dog sitter visits: enable their slot before arrival, disable when done —
  no code editing required"
- "Family code management: each family member has a named slot"
- "Keypad lockout: disable all keypads when alarm is armed"
- "Verify codes were pushed after a power outage"

**Status:** `[P2]`

---

### G-12 · dynamic-devices

**Rule:** If a hub or service can add devices after initial setup, the
integration should detect and add them without requiring a reconfigure.

**SlotSentry application:** New Z-Wave locks added to the Z-Wave network
after SlotSentry is set up should be available to add through the reconfigure
flow, not automatically managed. Auto-detection of newly added locks would
require subscribing to the device registry and is complex enough to defer.

Since SlotSentry explicitly selects which locks to manage (not managing all
locks automatically), this rule is partially applicable. We will implement
a reconfigure-based add-lock flow as a proxy for this.

**Status:** `[P2]` — Reconfigure flow to add/remove locks satisfies the spirit
of this rule for SlotSentry's architecture.

---

### G-13 · entity-category

**Rule:** Entities must be assigned an appropriate `EntityCategory`:
- `EntityCategory.CONFIG` — for configuration/settings entities
- `EntityCategory.DIAGNOSTIC` — for status/diagnostic entities
- No category — for primary functional entities the user interacts with

**SlotSentry application:**
```python
class SlotSentryPushStatusSensor(SlotSentryEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

class SlotSentrySuppressedBinarySensor(SlotSentryEntity):
    _attr_entity_category = None  # Primary functional entity

class SlotSentryPushAllButton(SlotSentryEntity):
    _attr_entity_category = None  # Primary action

class SlotSentryRetryButton(SlotSentryEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
```

**Status:** `[MVP]`

---

### G-14 · entity-device-class

**Rule:** Entities should use HA device classes wherever an appropriate one
exists. Device classes define standard icons, units, and behavior.

**SlotSentry application:**
```python
class SlotSentrySuppressedBinarySensor(SlotSentryEntity):
    _attr_device_class = BinarySensorDeviceClass.LOCK
    # Or BinarySensorDeviceClass.SAFETY — pick most semantically accurate

class SlotSentryPushAllButton(SlotSentryEntity):
    _attr_device_class = ButtonDeviceClass.UPDATE
    # Or no device class if none fits well

class SlotSentryPushStatusSensor(SlotSentryEntity):
    _attr_device_class = None  # No standard device class for "push status"
    _attr_state_class = None
```

**Status:** `[MVP]`

**Implementation note:** Do not force a device class that does not semantically
fit. The `BinarySensorDeviceClass.LOCK` on the suppressed sensor communicates
"keypad is locked out" clearly.

---

### G-15 · entity-disabled-by-default

**Rule:** Less popular, noisy, or diagnostic entities should be disabled by
default. Users can enable them if needed. This reduces clutter for the majority
of users.

**SlotSentry application:**
```python
class SlotSentryPushStatusSensor(SlotSentryEntity):
    _attr_entity_registry_enabled_default = False  # Diagnostic, disabled by default

class SlotSentryRetryButton(SlotSentryEntity):
    _attr_entity_registry_enabled_default = False  # Power-user feature

class SlotSentrySuppressedBinarySensor(SlotSentryEntity):
    _attr_entity_registry_enabled_default = True   # Primary feature

class SlotSentryPushAllButton(SlotSentryEntity):
    _attr_entity_registry_enabled_default = True   # Primary action
```

**Status:** `[MVP]`

---

### G-16 · entity-translations

**Rule:** Entity names must be translatable. Use the `entity` section in
`strings.json` with the `name` key for each entity, and set
`_attr_translation_key` on each entity class.

**SlotSentry application:**
```python
class SlotSentryPushStatusSensor(SlotSentryEntity):
    _attr_translation_key = "push_status"
```

`strings.json`:
```json
{
  "entity": {
    "sensor": {
      "push_status": {
        "name": "Push Status",
        "state": {
          "idle": "Idle",
          "pushing": "Pushing",
          "success": "Success",
          "partial_fail": "Partial Failure",
          "failed": "Failed"
        }
      }
    },
    "binary_sensor": {
      "suppressed": {
        "name": "Keypad Lockout Active"
      }
    },
    "button": {
      "push_all": {
        "name": "Push All Slots"
      },
      "retry_failed": {
        "name": "Retry Failed Pushes"
      }
    }
  }
}
```

**Status:** `[MVP]`

---

### G-17 · exception-translations

**Rule:** Exception messages raised by the integration (especially those shown
in the UI as repairs or notifications) must be translatable. Use
`HomeAssistantError(translation_domain=DOMAIN, translation_key="key")`.

**SlotSentry application:** Any `HomeAssistantError` or `ServiceValidationError`
raised in service actions or coordinator must use translation keys, not
hardcoded English strings.

```python
raise HomeAssistantError(
    translation_domain=DOMAIN,
    translation_key="push_failed",
    translation_placeholders={"lock_name": lock_name},
)
```

`strings.json`:
```json
{
  "exceptions": {
    "push_failed": {
      "message": "Failed to push codes to lock {lock_name}."
    },
    "zwave_unavailable": {
      "message": "Z-Wave JS is not available. Check that the add-on is running."
    }
  }
}
```

**Status:** `[MVP]`

---

### G-18 · icon-translations

**Rule:** Entity icons should be defined in `icons.json` using translation
keys, allowing icons to vary based on entity state.

**SlotSentry application:**
`icons.json`:
```json
{
  "entity": {
    "sensor": {
      "push_status": {
        "default": "mdi:sync",
        "state": {
          "idle": "mdi:sync",
          "pushing": "mdi:sync-circle",
          "success": "mdi:check-circle",
          "partial_fail": "mdi:alert-circle",
          "failed": "mdi:close-circle"
        }
      }
    },
    "binary_sensor": {
      "suppressed": {
        "default": "mdi:lock-open",
        "state": {
          "on": "mdi:lock",
          "off": "mdi:lock-open"
        }
      }
    },
    "button": {
      "push_all": {
        "default": "mdi:upload-multiple"
      },
      "retry_failed": {
        "default": "mdi:refresh-circle"
      }
    }
  }
}
```

**Status:** `[MVP]`

---

### G-19 · reconfiguration-flow

**Rule:** Integrations must provide a reconfigure flow for changing settings
after initial setup. Users should not need to delete and re-add the integration
to change configuration.

**SlotSentry application:** The reconfigure flow is central to SlotSentry's
design. It must support:
- Adding or removing locks from management
- Changing code length mode and lengths
- Adding/removing/changing the lockout trigger entity for keypad lockout
- Enabling/disabling Secure Mode (with password setup/teardown)
- Per-lock keypad lockout participation toggle

**Status:** `[MVP]` (core to architecture)

---

### G-20 · repair-issues

**Rule:** When user intervention is needed (not just a transient error), raise
a `RepairIssue` via `ir.async_create_issue()` rather than logging or showing
a persistent notification.

**SlotSentry application:** Use repair issues for:
- Persistent lock sync failure after multiple retries (action required)
- Secure mode password entry failure exceeding threshold
- Configuration referencing a lock entity that no longer exists

**Status:** `[P2]` — Repair issues require the `homeassistant.components.
repairs` integration. MVP uses persistent notifications as fallback; proper
repair issues added in Phase 2.

---

### G-21 · stale-devices

**Rule:** If devices can be removed from the underlying service, the integration
must proactively remove them from HA's device and entity registries rather
than leaving stale entries.

**SlotSentry application:** If a user removes a lock from SlotSentry's managed
set (via reconfigure), all entities associated with that lock's device entry
must be cleaned up. If a Z-Wave lock is removed from the Z-Wave network
entirely, SlotSentry should detect the entity is no longer present and mark
its configuration stale.

**Status:** `[P2]` — Implement during the reconfigure flow enhancement. When
a lock is removed in reconfigure, clean up its device/entity registry entries.

---

## Platinum Tier (3 Rules)

Platinum is our stretch goal. These three rules are purely technical code
quality standards and can be addressed in a post-Gold release.

---

### P-01 · async-dependency

**Rule:** All external library dependencies must be fully asynchronous. No
blocking I/O in the event loop. If a library is synchronous, it must be run
in an executor via `hass.async_add_executor_job()`.

**SlotSentry application:** SlotSentry has no external library I/O — all
operations go through HA's service registry and storage helpers, which are
already async. If the `cryptography` library is used for secure mode, ensure
encryption/decryption of large data sets is executor-wrapped:

```python
import asyncio
from homeassistant.util.executor import async_get_executor

encrypted = await hass.async_add_executor_job(
    fernet.encrypt, plaintext_bytes
)
```

In practice, Fernet operations on kilobyte-scale slot data are fast enough
not to matter, but for Platinum compliance they should be executor-wrapped.

**Status:** `[STRETCH]`

---

### P-02 · inject-websession

**Rule:** If the integration uses HTTP (aiohttp or httpx), it must use HA's
shared client session via `async_get_clientsession(hass)` rather than creating
its own session. This reduces resource usage.

**SlotSentry application:** SlotSentry does not make HTTP requests directly.
All communication goes through HA's service registry (zwave_js services).
This rule is exempt.

**Status:** `[EXEMPT]` — No HTTP client usage. Integration communicates
exclusively via HA service calls.

**quality_scale.yaml exemption:**
```yaml
inject-websession:
  status: exempt
  comment: >-
    Integration does not make HTTP requests. All external communication
    is via HA service calls to the zwave_js integration.
```

---

### P-03 · strict-typing

**Rule:** All code must be fully typed with Python type annotations. The
integration must pass `mypy --strict` with no errors. All public functions,
methods, and class attributes must have type annotations.

**SlotSentry application:** Build with strict typing from day one. Use:
- Type annotations on all function signatures
- `TypedDict` for structured dicts
- `Final` for constants
- `Generic` for typed coordinators
- Run `mypy --strict` in CI before each release

```python
from __future__ import annotations
from typing import Any, Final
from homeassistant.core import HomeAssistant

DOMAIN: Final = "slotsentry"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: SlotSentryConfigEntry,
) -> bool:
    ...
```

Use the typed config entry pattern:
```python
type SlotSentryConfigEntry = ConfigEntry[SlotSentryRuntimeData]
```

**Status:** `[STRETCH]` — Write with typing from the start; full mypy --strict
pass is the Platinum gate.

---

## Custom Panel Considerations

SlotSentry includes a sidebar panel (Lovelace custom panel / frontend module).
The quality scale does not formally address custom frontend panels, but the
following standards apply:

### Panel Architecture
- The panel must be a standalone JavaScript module registered via
  `hass.components.frontend.async_register_panel()`
- Panel registration must happen in `async_setup_entry` and be removed in
  `async_unload_entry`
- Panel assets (JS bundle) are served from `custom_components/slotsentry/
  frontend/` via HA's static file serving

### Panel Quality Standards (Aspirational)
- **Accessibility:** ARIA labels, keyboard navigation for all interactive elements
- **Responsive:** Functional on mobile viewport (some features may be desktop-preferred)
- **Error states:** Panel shows clear error UI when coordinator is unavailable
- **Loading states:** Spinner/skeleton UI while data loads
- **No direct Z-Wave calls from frontend:** All operations go via HA WebSocket
  API → backend service → coordinator → Z-Wave JS
- **Websocket auth:** Use HA's authenticated WebSocket connection; never bypass auth
- **CSP compliance:** No inline scripts; panel JS is a proper ES module

### Panel Does NOT Affect Quality Scale Tier
The HA quality scale evaluates the integration backend (Python). A beautifully
built panel does not move the tier needle, but a broken or insecure panel
would damage the integration's reputation regardless of backend quality.

---

## HACS-Specific Checklist

Beyond the HA quality scale, HACS distribution requires:

| Item | Requirement | Status |
|------|-------------|--------|
| `hacs.json` | Present with `name`, `content_in_root: false` | `[MVP]` |
| GitHub releases | Semantic version tags (e.g., `v1.0.0`) | `[MVP]` |
| `manifest.json` version | Matches GitHub tag | `[MVP]` |
| `custom_components/slotsentry/` | Correct subdirectory structure | `[MVP]` |
| README.md | Install instructions visible on HACS page | `[MVP]` |
| No hardcoded secrets | No API keys, passwords in source | `[MVP]` |
| MIT or compatible license | `LICENSE` file present | `[MVP]` |

---

## `quality_scale.yaml` Template

Place this file at `custom_components/slotsentry/quality_scale.yaml`:

```yaml
rules:
  # Bronze
  action-setup:
    status: todo
  appropriate-polling:
    status: todo
  brands:
    status: todo
  common-modules:
    status: todo
  config-flow:
    status: todo
  config-flow-test-coverage:
    status: todo
  dependency-transparency:
    status: todo
  docs-actions:
    status: todo
  docs-high-level-description:
    status: todo
  docs-installation-instructions:
    status: todo
  docs-removal-instructions:
    status: todo
  entity-event-setup:
    status: todo
  entity-unique-id:
    status: todo
  has-entity-name:
    status: todo
  runtime-data:
    status: todo
  test-before-configure:
    status: todo
  test-before-setup:
    status: todo
  unique-config-entry:
    status: todo

  # Silver
  action-exceptions:
    status: todo
  config-entry-unloading:
    status: todo
  docs-configuration-parameters:
    status: todo
  docs-installation-parameters:
    status: todo
  entity-unavailable:
    status: todo
  integration-owner:
    status: exempt
    comment: >-
      HACS custom integration. Codeowner omitted from manifest for privacy.
      Maintained by the GitHub repository owner.
  log-when-unavailable:
    status: todo
  parallel-updates:
    status: todo
  reauthentication-flow:
    status: exempt
    comment: >-
      Integration does not authenticate with any remote service. Local Z-Wave JS
      services are accessed via HA service registry without credentials.
  test-coverage:
    status: todo

  # Gold
  devices:
    status: todo
  diagnostics:
    status: todo
  discovery:
    status: exempt
    comment: >-
      Integration manages HA lock entities already discovered by Z-Wave JS.
      Hardware discovery is handled by the upstream Z-Wave JS integration.
  discovery-update-info:
    status: exempt
    comment: Follows from discovery exemption.
  docs-data-update:
    status: todo
  docs-examples:
    status: todo
  docs-known-limitations:
    status: todo
  docs-supported-devices:
    status: todo
  docs-supported-functions:
    status: todo
  docs-troubleshooting:
    status: todo
  docs-use-cases:
    status: todo
  dynamic-devices:
    status: todo
  entity-category:
    status: todo
  entity-device-class:
    status: todo
  entity-disabled-by-default:
    status: todo
  entity-translations:
    status: todo
  exception-translations:
    status: todo
  icon-translations:
    status: todo
  reconfiguration-flow:
    status: todo
  repair-issues:
    status: todo
  stale-devices:
    status: todo

  # Platinum
  async-dependency:
    status: todo
  inject-websession:
    status: exempt
    comment: >-
      Integration does not make HTTP requests. All external communication
      is via HA service calls to the zwave_js integration.
  strict-typing:
    status: todo
```

Update each rule's `status` from `todo` to `done` as implementation is completed.

---

## Development Phase Map

| Phase | Quality Level | Gates |
|-------|---------------|-------|
| MVP (v0.9) | Bronze | All 18 Bronze rules done; Silver runtime rules done (S-01, S-02, S-05, S-07, S-08) |
| v1.0 Publish | Gold | All Bronze + All Silver + All Gold rules done or exempted |
| v1.1 | Platinum | P-01 executor wrapping; P-03 mypy --strict pass |

---

## Quick-Reference: Rules by File

### `__init__.py`
- B-01 action-setup (register services here)
- B-17 test-before-setup (raise ConfigEntryNotReady)
- S-02 config-entry-unloading (async_unload_entry)
- G-01 devices (create device registry entry)

### `config_flow.py`
- B-05 config-flow
- B-16 test-before-configure
- B-18 unique-config-entry
- S-09 reauthentication-flow (exempt)
- G-19 reconfiguration-flow

### `coordinator.py`
- B-02 appropriate-polling
- B-12 entity-event-setup (subscription setup)
- S-07 log-when-unavailable
- S-05 entity-unavailable (coordinator.last_update_success)

### `entity.py`
- B-13 entity-unique-id
- B-14 has-entity-name
- B-15 runtime-data (access pattern)
- G-13 entity-category
- G-14 entity-device-class
- G-15 entity-disabled-by-default

### `sensor.py`, `binary_sensor.py`, `button.py`
- S-08 parallel-updates (PARALLEL_UPDATES = 1 constant)
- G-16 entity-translations (_attr_translation_key)
- G-18 icon-translations

### `diagnostics.py`
- G-02 diagnostics

### `strings.json` / `translations/en.json`
- G-16 entity-translations
- G-17 exception-translations

### `icons.json`
- G-18 icon-translations

### `quality_scale.yaml`
- Tracks status of all rules

### `tests/`
- B-06 config-flow-test-coverage
- S-10 test-coverage (95%+ all modules)

---

## Sources

The following sources were consulted in preparing this document:

- [Integration Quality Scale — Home Assistant Developer Docs](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
- [Quality Scale — Home Assistant User Docs](https://www.home-assistant.io/docs/quality_scale/)
- [Integration Quality Scale Rules Index — Developer Docs](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/)
- [ADR-0022: Integration Quality Scale — HA Architecture](https://github.com/home-assistant/architecture/blob/master/adr/0022-integration-quality-scale.md)
- [hassfest quality_scale.py — HA Core](https://github.com/home-assistant/core/blob/dev/script/hassfest/quality_scale.py)
- [Integration Quality Scale Blog Post — November 2024](https://developers.home-assistant.io/blog/2024/11/20/integration-quality-scale/)
- [inject-websession Rule — Developer Docs](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/inject-websession/)
- [Integration Quality Scale Discussion Chapter 3](https://github.com/home-assistant/architecture/discussions/1155)
