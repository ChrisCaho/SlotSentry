[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom%20Repository-orange)](https://hacs.xyz/)
[![Home Assistant Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![GitHub Release](https://img.shields.io/github/release/ChrisCaho/SlotSentry?style=flat)](https://github.com/ChrisCaho/SlotSentry/releases)

# SlotSentry v2026.4.0a10

Centralized Z-Wave lock user code management for Home Assistant. SlotSentry provides a professional sidebar panel UI for managing access codes across multiple Z-Wave smart locks with mixed code lengths, enabling per-slot controls, and optional password-protected storage.

SlotSentry is a code manager only — it reads and writes user code slots and never issues lock or unlock commands.

## Table of Contents

- [Features](#features)
- [Motivation](#motivation)
- [Supported Devices](#supported-devices)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Entities](#entities)
- [Architecture](#architecture)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)
- [Credits](#credits)

## Features

SlotSentry delivers enterprise-grade lock code management with an intuitive interface:

- **Centralized Slot-Based Management** — Manage user codes for multiple Z-Wave locks from a single sidebar panel
- **Mixed Code Lengths** — Support locks with different code lengths simultaneously (e.g., 4-digit and 6-digit)
- **Per-Slot Enable/Disable** — Disable temporary access without losing stored codes; re-enable instantly
- **Secure Mode** — Optional password-protected storage with AES encryption for sensitive deployments
- **Keypad Lockout Control** — Disable keypads on participating locks via any Home Assistant sensor (alarm armed, presence detection, etc.)
- **Dynamic Slot Count** — Slot count is determined by the lock with the smallest capacity among your selected locks; no hardcoded limit
- **Code Length Discovery** — Integration auto-detects supported code lengths from your locks and suggests defaults
- **Commit State Tracking** — Real-time verification of code pushes with automatic retry on failure
- **Audit Trail Logging** — Full history of code changes without exposing codes in logs
- **Minimal Entity Footprint** — Only 4 entities exposed; the sidebar panel is the primary interface
- **Code Readback Verification** — For supported locks, verify actual codes match after push

## Motivation

Why SlotSentry when [Keymaster](https://github.com/FutureTense/keymaster) exists?

**Keymaster** is powerful but designed around traditional code management workflows—it excels at temporary codes with expiration, complex scheduling, and granular logging. **SlotSentry** takes a different approach:

1. **Simplicity First** — Fewer configuration options, faster setup. If you manage codes manually (dog sitter, contractor, visiting family), SlotSentry is lighter weight.
2. **Multi-Lock Support with Mixed Lengths** — SlotSentry seamlessly handles locks with different code lengths in the same household without complex workarounds.
3. **Per-Slot Toggle Pattern** — Enable/disable access by toggling a checkbox—no re-entering codes. Perfect for recurring temporary access (housekeeping visits, seasonal contractors).
4. **Code Readback** — Verify that codes on certain locks (e.g., Schlage BE469ZP) match what you intended to set.
5. **Keypad Lockout** — Integrated control over lock keypads tied to any sensor, not just Keymaster's specific trigger patterns.
6. **Modern UI** — LitElement-based sidebar panel instead of YAML automations or separate dashboards.

Choose **Keymaster** if you need advanced scheduling, complex automation triggers, or temporary codes with precise expiration windows. Choose **SlotSentry** if you want straightforward code management, multi-lock harmony, and an intuitive interface.

## Supported Devices

SlotSentry works with any Z-Wave lock compatible with Home Assistant's Z-Wave JS integration. Tested and recommended on:

- **Schlage Connect Camelot (BE469ZP)** — 30 slots, 4–8 digit codes, code readback (visible in logs)
- **Schlage FE599** — 19 slots, 4-digit codes, code readback masked (firmware restriction)

SlotSentry uses the Z-Wave JS integration's standard `set_lock_usercode` and `clear_lock_usercode` services. Any Z-Wave lock supporting User Code Command Class (CC 0x63) should work. Verification features are optional—SlotSentry manages codes even on locks that don't expose code readback.

**Not Supported:**
- Zigbee locks (no Z-Wave JS integration)
- Bluetooth locks without Z-Wave
- Schlage Sense (cloud-only, no Z-Wave)
- Standard locks without user code support

## Requirements

- **Home Assistant** 2024.1 or later
- **Z-Wave JS integration** enabled and connected
- **At least one Z-Wave lock** with user code support
- **HACS** for installation (custom repository)

## Installation

### 1. Add Custom Repository to HACS

1. Open **Settings > Devices & Services > HACS**
2. Click the menu (three dots) and select **Custom repositories**
3. Enter:
   - **Repository:** `https://github.com/ChrisCaho/SlotSentry`
   - **Category:** Integration
4. Click **Create**

### 2. Install SlotSentry

1. Go to **HACS > Integrations**
2. Search for "SlotSentry"
3. Click **Install**
4. Restart Home Assistant

### 3. Set Up the Integration

1. Open **Settings > Devices & Services > Integrations**
2. Click **Add Integration** (the + button at the bottom right) and search for "SlotSentry"
3. Click **Create**
4. Follow the configuration flow:
   - Select your Z-Wave locks
   - Configure code length (auto-detected from locks; single or mixed)
   - Optionally enable secure mode
   - Optionally configure keypad lockout
5. Click **Finish**

## Quick Start

### Access the Slot Manager

1. Open the Home Assistant sidebar
2. Look for **SlotSentry** in the sidebar menu
3. If secure mode is enabled, enter your password and click **Unlock**
4. The slot grid appears — the number of rows is determined by the lock with the smallest slot capacity among your configured locks

### Add a Code

1. In an empty row, type a label like "Dog Sitter"
2. Enter the code in the **Code** field (or **Long Code** and **Short Code** if mixed lengths are configured)
3. The **Enable** checkbox is checked by default
4. Scroll to the bottom and click **Save**
5. Watch the **Push Status** sensor at the top of the panel
6. Once all locks show **Synced**, the code is active on all locks

### Disable a Code Temporarily

1. Find the slot (e.g., "Dog Sitter")
2. **Uncheck** the Enable checkbox
3. Click **Save**
4. SlotSentry clears the code from all locks, but the label and code are retained on disk
5. To re-enable, check the Enable checkbox again and save

### Verify After Update

SlotSentry automatically attempts to verify code pushes. For locks with code readback (e.g., BE469ZP), codes are compared post-push. For other locks (e.g., FE599), slot occupancy is verified. If verification fails, the **Push Status** sensor shows the error and suggests manual testing.

## Configuration

### Initial Setup (Config Flow)

The configuration flow handles all settings:

- **Select Locks** — Choose which Z-Wave locks to manage
- **Code Length Configuration** — Single length or two lengths; defaults auto-detected from locks
- **Secure Mode** — Enable password protection with AES encryption
- **Keypad Lockout** — Select a sensor and which locks participate

### Reconfiguration

Modify settings anytime:

1. **Settings > Devices & Services > Integrations**
2. Find **SlotSentry** and click the menu (three dots)
3. Click **Reconfigure**
4. Update locks, code lengths, secure mode, or keypad settings
5. Click **Finish**

### Secure Mode

**Enable Secure Mode:**
1. During initial setup or reconfiguration, check **Enable Secure Mode**
2. Create a password (8–16 characters)
3. Confirm the password
4. A warning appears: "All slot data will be encrypted. Back up your config if needed."
5. Click **Confirm**

**Access Encrypted Data:**
1. Open the SlotSentry sidebar panel
2. Enter your password in the top field
3. Click **Unlock**
4. Codes remain hidden (asterisks) until you check **Reveal Codes**
5. Codes are stored encrypted on disk; your password is the decryption key

**Disable Secure Mode:**
1. Reconfigure the integration
2. Uncheck **Enable Secure Mode**
3. Enter your current password to decrypt the data
4. A warning appears: "Codes will be stored in plain text. Consider re-enabling security later."
5. Click **Confirm**

### Code Length Configuration

**Single Code Length:**
- Choose one length (4–8 digits; SlotSentry suggests a default based on your locks)
- The sidebar panel shows one **Code** field per slot

**Two Code Lengths (Mixed):**
- Define a short length (4–7 digits, e.g., 4)
- Define a long length (5–8 digits, e.g., 6)
- The sidebar panel shows **Long Code** and **Short Code** fields per slot
- Useful for locks with different capabilities in the same household

If code lengths cannot be detected automatically from your locks, SlotSentry defaults to 4/6 (two lengths) or 6 (single length).

## Entities

SlotSentry exposes four entities for automation and monitoring:

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.slotsentry_push_status` | Sensor | Last push result: "Synced", "Out of Sync", "Syncing", or error details |
| `binary_sensor.slotsentry_suppressed` | Binary Sensor | Keypad lockout active (true = keypads disabled on participating locks) |
| `button.slotsentry_push_all` | Button | Force push all codes to all locks immediately |
| `button.slotsentry_retry` | Button | Retry failed pushes (useful if a lock was offline) |

### Example Automations

**Retry failed pushes on trigger:**

```yaml
automation:
  - alias: "SlotSentry Retry on Connection"
    trigger:
      platform: event
      event_type: zwave_js_lock_connected
    action:
      service: button.press
      target:
        entity_id: button.slotsentry_retry
```

**Monitor push failures:**

```yaml
automation:
  - alias: "Notify on SlotSentry Push Failure"
    trigger:
      platform: state
      entity_id: sensor.slotsentry_push_status
      to:
        - "Out of Sync"
        - "Error"
    action:
      service: notify.admin
      data:
        message: "SlotSentry: {{ states('sensor.slotsentry_push_status') }}"
```

**Notify when keypad lockout activates:**

```yaml
automation:
  - alias: "Notify on Keypad Lockout"
    trigger:
      platform: state
      entity_id: binary_sensor.slotsentry_suppressed
      to: "on"
    action:
      service: notify.admin
      data:
        message: "SlotSentry: Keypad lockout activated"
```

## Architecture

SlotSentry is a custom Home Assistant integration with a modern JavaScript/LitElement frontend:

**Backend:**
- Standard HA integration structure with config flow
- WebSocket API for sidebar panel communication
- Commit state machine for robust code synchronization
- Verification logic with code readback (where supported)
- AES-256 encryption for secure mode
- Extensible `LockBackend` protocol supporting multiple lock protocols (Z-Wave JS now, Schlage cloud and others planned)

**Frontend:**
- LitElement web component (`slotsentry-panel.js`)
- Real-time push status updates via WebSocket
- Responsive grid layout for code management
- Password and reveal controls for secure mode

**Storage:**
- `.storage/slotsentry` — Disk state (plain or encrypted)
- Lock commit arrays for per-lock synchronization tracking
- Audit trail with configurable depth

## FAQ

**Q: Can I manage codes remotely while away from home?**

A: Yes. The sidebar panel is accessible from Home Assistant's web UI or mobile app. SlotSentry pushes codes to locks via Z-Wave JS, which runs locally. Ensure your HA instance is accessible (mobile app, VPN, or trusted network access) and your locks are on the Z-Wave mesh.

**Q: What if a lock goes offline during a push?**

A: SlotSentry marks the slot as `Out of Sync` on that lock and continues with other locks. When the lock comes back online, open the sidebar panel or press the `button.slotsentry_retry` button to retry. Automatic retry is on the roadmap.

**Q: How do I recover if I lose my secure mode password?**

A: Data is encrypted with your password as the key. If you forget the password:
1. The integration detects repeated failed password attempts
2. A reconfiguration option appears: "Reset Password (Data Loss Warning)"
3. You set a new password and SlotSentry reinitializes all slots (data is lost)

Always back up your config before enabling secure mode, or use the integration reconfiguration export feature.

**Q: Can SlotSentry manage codes on HomeKit/cloud locks?**

A: No. SlotSentry requires the Z-Wave JS integration. Cloud-only locks (e.g., Schlage Sense) must be managed via their native apps. Hybrid locks that support Z-Wave work with SlotSentry.

**Q: How is keypad lockout different from just disabling codes?**

A: **Keypad Lockout** disables the lock's keypad input entirely (the lock ignores PIN entries), but the codes stay on the lock. Useful for "alarm armed" scenarios where you want to prevent PIN entry even though codes exist. **Disabling codes** clears them from the lock, so even if the keypad were active, the codes wouldn't work. Use both for maximum security. SlotSentry never issues lock or unlock commands — it only controls code slots and keypad enable/disable.

**Q: How many slot rows will I see in the panel?**

A: The slot count is determined at integration setup by the lock with the smallest slot capacity among your selected locks. For example, if you have one lock with 30 slots and three locks with 19 slots, you will see 19 rows.

**Q: Can I use SlotSentry with non-Z-Wave locks in the future?**

A: Yes, SlotSentry is designed with extensibility in mind. A `LockBackend` protocol allows support for other lock APIs (Zigbee, Bluetooth, HomeKit). This is planned for v2.

**Q: Does SlotSentry expose codes in Home Assistant logs?**

A: No. SlotSentry explicitly avoids logging codes. The audit trail records slot numbers, labels, and actions (enable/disable, push success/failure) but never the actual codes themselves.

**Q: Why do some locks show asterisks in the Z-Wave JS UI?**

A: Some lock firmware (e.g., FE599) masks user codes for security—the Z-Wave JS UI shows `****`. SlotSentry's frontend also masks codes in secure mode. Open mode (secure mode disabled) shows codes in the panel while editing; they're re-masked after save.

**Q: Can I import codes from Keymaster?**

A: Not directly. However, if you export Keymaster's codes manually, you can re-enter them into SlotSentry one slot at a time. A migration tool is a future enhancement.

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request with a clear description

For major features, please open an issue first to discuss the design.

## License

This project is licensed under the MIT License—see [LICENSE](LICENSE) for details.

## Credits

**SlotSentry** was created by [Chris Caho](https://github.com/ChrisCaho) with development assistance from [Claude Code](https://claude.com/claude-code).

Inspired by the excellent work of [Keymaster](https://github.com/FutureTense/keymaster) and [Lock Code Manager](https://github.com/raman325/lock_code_manager).

Z-Wave research and lock testing powered by the Home Assistant community and the [zwave-js](https://github.com/zwave-js/zwave-js) project.

---

Have questions? Open an [issue](https://github.com/ChrisCaho/SlotSentry/issues) on GitHub.
