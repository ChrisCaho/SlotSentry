# Contributing to SlotSentry

Thank you for your interest in contributing to SlotSentry! This document outlines the process and expectations for contributing code, documentation, and bug reports.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Code Style](#code-style)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Feature Requests](#feature-requests)

## Code of Conduct

Be respectful and constructive in all interactions. We aim to create a welcoming environment for all contributors regardless of background or experience level.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a feature branch** from `main`
4. **Set up your development environment** (see below)
5. **Make your changes** following code style guidelines
6. **Test thoroughly** before submitting a pull request
7. **Submit a pull request** with a clear description

## Development Environment

### Prerequisites

- Home Assistant OS or Core installation (2024.12 or later)
- Python 3.12 or later
- Node.js 18+ and npm (for frontend development)
- Git

### Backend Setup

1. Clone the repository to your Home Assistant `custom_components` directory:
   ```bash
   cd ~/.homeassistant/custom_components
   git clone https://github.com/yourusername/slotsentry.git
   cd slotsentry
   ```

2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. Restart Home Assistant to load the custom component

4. Add the integration through the HA UI (Settings > Devices & Services > Create Automation > Custom Integration)

### Frontend Setup

1. Install dependencies:
   ```bash
   cd www
   npm install
   ```

2. Start the development server for hot-reloading:
   ```bash
   npm run dev
   ```

3. Build for production:
   ```bash
   npm run build
   ```

### Z-Wave Testing Environment

To test with real locks:

- Ensure Z-Wave JS add-on is running and accessible
- Configure at least one Z-Wave lock entity in Home Assistant
- Review NOTES.md for lock models and slot configurations used in development

For mock testing without hardware:

- Use Home Assistant mock integrations
- Create sensor entities manually for testing door sensors and keypad lockout triggers

## Code Style

### Python Code

We follow PEP 8 with automatic formatting. Configure your editor:

1. **Black** (code formatter):
   ```bash
   black slotsentry/
   ```

2. **isort** (import sorting):
   ```bash
   isort slotsentry/
   ```

3. **mypy** (static type checking):
   ```bash
   mypy slotsentry/
   ```

4. **Linting**:
   ```bash
   pylint slotsentry/
   ```

#### Python Style Guidelines

- Type hints are mandatory for all function signatures
- Docstrings required for all public classes and functions (Google style)
- Use `_LOGGER` for all logging (never print)
- Use `_LOGGER.debug()` for verbose output (invisible unless logger level is debug)
- Use `_LOGGER.info()` for important events that should always appear
- Never log sensitive data (codes, passwords, raw config)
- Maximum line length: 100 characters
- Use 4-space indentation
- Single underscore prefix for internal methods/attributes

Example:
```python
async def push_codes_to_lock(
    self, lock_entity_id: str, slots: list[Slot]
) -> bool:
    """Push codes to a specific lock and verify.

    Args:
        lock_entity_id: The Z-Wave lock entity ID
        slots: List of Slot objects to push

    Returns:
        True if all slots pushed successfully

    Raises:
        PushTimeoutError: If operation exceeds timeout
    """
```

### JavaScript Code

We use Prettier for consistent formatting:

1. **Prettier** (code formatter):
   ```bash
   npm run format
   ```

2. **ESLint** (linting):
   ```bash
   npm run lint
   ```

#### JavaScript Style Guidelines

- Use modern ES6+ syntax
- Type annotations via JSDoc comments for clarity
- LitElement best practices (reactive properties, computed properties)
- Web components must be self-contained and reusable
- CSS must be scoped (no global styles)
- Maximum line length: 100 characters
- No console.log in production code (use proper error handling)

Example:
```javascript
/**
 * Slot manager sidebar panel
 * @element slotsentry-panel
 */
class SlotSentryPanel extends LitElement {
  static properties = {
    hass: {},
    narrow: { type: Boolean },
    route: {},
  };

  /**
   * Push a single slot to all locks
   * @param {number} slotNumber - The slot number to push
   * @param {Slot} slot - The slot data
   * @returns {Promise<boolean>}
   */
  async pushSlot(slotNumber, slot) {
    // implementation
  }
}
```

## Testing

### Python Testing

Write unit tests for all new Python modules:

```bash
pytest slotsentry/tests/ -v
```

Test coverage expectations:

- Core logic (config flow, coordinator, entity creation): minimum 80% coverage
- Integrations with HA (services, WebSocket): minimum 70% coverage
- Error handling and edge cases: required for all push/pull operations

Example test:
```python
async def test_push_codes_marks_synced(hass, slotsentry):
    """Test that successful push marks commit state as synced."""
    slot = Slot(slot_number=1, long_code="123456")
    await slotsentry.push_codes_to_lock("lock.example", [slot])

    commit = slotsentry.get_commit_status()
    assert commit["locks"]["lock.example"][0]["state"] == "synced"
```

### Integration Testing

Before submitting a PR with changes to lock operations:

1. Test with at least one real Z-Wave lock (BE469ZP, FE599, or similar)
2. Test the complete flow: push codes, verify status, handle timeouts
3. Verify codes can be read back where supported
4. Test edge cases: missing locks, timeout scenarios, malformed responses

### Frontend Testing

Test the sidebar panel in your browser:

1. Start development server: `npm run dev`
2. Open the sidebar panel in Home Assistant
3. Test all user interactions:
   - Password validation in secure mode
   - Slot enable/disable
   - Code editing and saving
   - Dirty state tracking
   - Error messages

No formal unit tests required for frontend yet, but visual regression testing is appreciated.

## Commit Messages

Use clear, descriptive commit messages following conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

Scope: `config-flow`, `coordinator`, `websocket`, `frontend`, `storage`, etc.

Example:
```
feat(coordinator): Add timeout handling for lock operations

- Add 60-second timeout per lock push operation
- Mark slots as uncertain if timeout occurs
- Log timeout events for debugging

Fixes #42
```

## Pull Request Process

1. **Ensure all tests pass locally**:
   ```bash
   black slotsentry/
   isort slotsentry/
   mypy slotsentry/
   pylint slotsentry/
   pytest slotsentry/tests/
   ```

2. **Check frontend**:
   ```bash
   npm run format
   npm run lint
   ```

3. **Update documentation** if adding features or changing behavior

4. **Add changelog entry** to CHANGELOG.md (if exists)

5. **Create descriptive PR** with:
   - Clear title explaining the change
   - Detailed description of what changed and why
   - Any testing done (especially for lock operations)
   - Screenshots for UI changes
   - References to related issues

6. **Request review** from maintainers

7. **Address feedback** promptly

8. **Merge** only after approval and CI passes

## Issue Reporting

When reporting bugs, include:

1. **Home Assistant version** (Settings > System Information)
2. **SlotSentry version** (in integration settings)
3. **Z-Wave lock model(s)** (BE469ZP, FE599, etc.)
4. **Steps to reproduce** - be specific
5. **Expected behavior** - what should happen
6. **Actual behavior** - what happens instead
7. **Logs** - relevant error messages (no codes or passwords)
8. **Screenshots** if UI-related

Example:
```
## Home Assistant Version
2024.12.4

## SlotSentry Version
1.0.0

## Z-Wave Lock
Schlage BE469ZP (slot 1)

## Steps to Reproduce
1. Enable slot 1 with code "123456"
2. Click "Save" button
3. Wait for push to complete
4. Disable slot 1

## Expected
Code should be cleared from lock

## Actual
Code remains active on lock

## Logs
[ERROR] Z-Wave push failed: timeout after 60 seconds
```

## Feature Requests

Before proposing a major feature:

1. **Check existing issues** - might already be planned
2. **Review architecture** in DEVELOPER_GUIDE.md to understand constraints
3. **Consider impact** on other systems (keypad lockout, door sensors, audit trail)
4. **Open a discussion issue** first to get feedback
5. **Include rationale** - why is this feature valuable?

Example good feature request:
```
## Feature: Temporary codes with expiration

### Problem
Currently all codes are permanent. Would like to create temporary codes
for contractors/guests that automatically expire after N days.

### Proposed Solution
- Add "Temporary" checkbox on each slot
- Date/time picker for expiration
- Background task checks expiration daily
- Auto-clears expired codes from locks and UI

### Alternative Solutions
Manual reminder to disable + re-enable code

### Additional Context
This would require changes to: storage schema, UI, coordinator
```

## Coding Standards for SlotSentry

Since SlotSentry manages access control codes, we maintain high standards:

1. **Security-first**: Never log codes, passwords, or sensitive data
2. **Reliability**: Lock operations must handle timeouts gracefully
3. **Auditability**: All push/pull operations logged with timestamp and result
4. **Verification**: Always verify after write operations where possible
5. **Atomic updates**: Disk state updated before lock updates to prevent data loss
6. **Clear error messages**: Users need to understand what failed and why

## Questions?

- Check DEVELOPER_GUIDE.md for architecture details
- Check DATA_MODEL.md for storage schema
- Review NOTES.md for design decisions
- Open a discussion issue on GitHub

Thank you for contributing to SlotSentry!
