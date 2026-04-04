"""SlotSentry storage layer.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Manages persistent JSON storage via HA's homeassistant.helpers.storage.Store,
which provides atomic writes and built-in file locking.

Storage file: .storage/slotsentry.<entry_id>
Schema version: 2

Revision: 1.3 — rename long_code/short_code to code_1/code_2.
"""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORAGE_KEY,
    STORAGE_VERSION,
    SYNC_OUT_OF_SYNC,
    SYNC_SYNCED,
    SYNC_UNCERTAIN,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def hash_code(code: str) -> str:
    """Return a SHA-256 hex digest of *code*, prefixed with 'sha256:'.

    Used to compare the code that was last pushed to a lock against the
    current in-memory value without storing the code itself in the commit
    record.
    """
    return f"sha256:{hashlib.sha256(code.encode()).hexdigest()}"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SlotData:
    """A single code slot as held in memory and persisted to storage.

    Slot numbers are 1-based integers (matching Z-Wave slot numbers).
    String keys ("1", "2", …) are used only in the raw JSON on disk.

    Empty slots are represented by empty strings for label/codes rather
    than None, so that the JSON schema is uniform across all slots.
    """

    slot_number: int
    label: str
    code_1: str           # Primary code (empty string if not set)
    code_2: str           # Secondary code (empty string if not set)
    enabled: bool
    created_at: str       # ISO 8601 timestamp; empty string if never written
    updated_at: str       # ISO 8601 timestamp; empty string if never written

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def is_empty(self) -> bool:
        """Return True if neither code_1 nor code_2 is populated."""
        return not self.code_1 and not self.code_2

    def get_active_code(self) -> str | None:
        """Return the code that should be pushed to a lock.

        Prefers code_1; falls back to code_2.  Returns None when
        the slot carries no code at all.
        """
        if self.code_1:
            return self.code_1
        if self.code_2:
            return self.code_2
        return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the storage JSON format (string keys, no slot_number)."""
        return {
            "label": self.label,
            "code_1": self.code_1,
            "code_2": self.code_2,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, slot_number: int, data: dict[str, Any]) -> SlotData:
        """Deserialise from a storage JSON dict, injecting the slot number.

        Supports both v2 field names (code_1/code_2) and legacy v1 names
        (long_code/short_code) for backward compatibility during migration.
        """
        return cls(
            slot_number=slot_number,
            label=data.get("label", ""),
            code_1=data.get("code_1", data.get("long_code", "")),
            code_2=data.get("code_2", data.get("short_code", "")),
            enabled=data.get("enabled", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @classmethod
    def empty(cls, slot_number: int) -> SlotData:
        """Return a brand-new, never-used slot."""
        return cls(
            slot_number=slot_number,
            label="",
            code_1="",
            code_2="",
            enabled=False,
            created_at="",
            updated_at="",
        )


@dataclass
class LockSlotCommit:
    """Per-lock per-slot commit tracking.

    Tracks whether the code that was last pushed to a specific lock
    matches the current in-storage code for a given slot.

    Attributes:
        slot_number:        1-based slot index.
        state:              One of SYNC_SYNCED / SYNC_OUT_OF_SYNC /
                            SYNC_UNCERTAIN (see const.py).
        pushed_at:          ISO 8601 timestamp of the last push attempt,
                            or None if never pushed.
        code_hash:          SHA-256 of the code at the time of the last
                            successful push (``hash_code()`` format), or
                            None if never pushed.
        last_pushed_label:  The slot label at the time of the last push.
                            Z-Wave backends set this to None because the
                            slot number addresses the lock.  Name-based
                            backends (e.g., Schlage cloud) set this so
                            that a subsequent label rename is detected as
                            out_of_sync even when the code itself has not
                            changed.
    """

    slot_number: int
    state: str
    pushed_at: str | None
    code_hash: str | None
    last_pushed_label: str | None

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def needs_retry(self) -> bool:
        """True when the slot requires a push or re-verification."""
        return self.state in (SYNC_OUT_OF_SYNC, SYNC_UNCERTAIN)

    @property
    def is_synced(self) -> bool:
        """True when the slot is confirmed to match the lock."""
        return self.state == SYNC_SYNCED

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the storage JSON format (no slot_number key)."""
        return {
            "state": self.state,
            "pushed_at": self.pushed_at,
            "code_hash": self.code_hash,
            "last_pushed_label": self.last_pushed_label,
        }

    @classmethod
    def from_dict(cls, slot_number: int, data: dict[str, Any]) -> LockSlotCommit:
        """Deserialise from a storage JSON dict, injecting the slot number."""
        return cls(
            slot_number=slot_number,
            state=data.get("state", SYNC_OUT_OF_SYNC),
            pushed_at=data.get("pushed_at"),
            code_hash=data.get("code_hash"),
            last_pushed_label=data.get("last_pushed_label"),
        )

    @classmethod
    def initial(cls, slot_number: int) -> LockSlotCommit:
        """Return a brand-new commit entry in out_of_sync state."""
        return cls(
            slot_number=slot_number,
            state=SYNC_OUT_OF_SYNC,
            pushed_at=None,
            code_hash=None,
            last_pushed_label=None,
        )


# ---------------------------------------------------------------------------
# Storage manager
# ---------------------------------------------------------------------------


class SlotSentryStore:
    """Async storage manager for a single SlotSentry config entry.

    Wraps ``homeassistant.helpers.storage.Store``, which handles atomic
    writes, directory creation, and JSON serialisation transparently.

    A single ``SlotSentryStore`` instance is created per config entry and
    held on the coordinator.  Callers mutate data via the ``set_slot``,
    ``delete_slot``, and ``set_lock_commit`` methods, then call
    ``async_save()`` to flush changes to disk.

    The in-memory cache (``self._data``) is always a plain Python dict
    matching the JSON schema below.  Higher-level helpers surface
    ``SlotData`` / ``LockSlotCommit`` dataclass objects for type safety.

    Storage file: ``.storage/slotsentry.<entry_id>``

    JSON schema::

        {
            "version": 2,
            "slot_count": 19,
            "code_length_mode": "dual",
            "slots": {
                "1": {
                    "label": "",
                    "code_1": "",
                    "code_2": "",
                    "enabled": false,
                    "created_at": "",
                    "updated_at": ""
                },
                ...
            },
            "lock_commit": {
                "lock.entity_id": {
                    "1": {
                        "state": "out_of_sync",
                        "pushed_at": null,
                        "code_hash": null,
                        "last_pushed_label": null
                    },
                    ...
                }
            },
            "config": {
                "dont_show_test_popup": false
            }
        }
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the store for the given config entry.

        Args:
            hass:     The Home Assistant instance.
            entry_id: The config entry ID, used to namespace the storage
                      file so that multiple SlotSentry entries do not
                      share state.
        """
        self._store: Store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}.{entry_id}",
            private=True,   # Not exposed via the storage debug panel
            atomic_writes=True,
        )
        self._data: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    async def async_load(self) -> dict[str, Any]:
        """Load stored data from disk, or return an empty default schema.

        On first run the file does not exist; ``Store.async_load()``
        returns ``None`` in that case and we fall back to
        ``_default_data()``.  The loaded data is cached in
        ``self._data`` for subsequent in-memory access.

        Migration is applied before the cache is populated, ensuring
        that all callers always see the current schema version.

        Returns:
            The loaded (and migrated) storage dict.  Also available
            afterwards via ``self._data``.
        """
        raw: dict[str, Any] | None = await self._store.async_load()

        if raw is None:
            _LOGGER.debug(
                "No existing SlotSentry storage found; using empty schema"
            )
            self._data = self._default_data(slot_count=0)
        else:
            self._data = self._migrate(raw)

        return self._data

    async def async_save(self) -> None:
        """Persist the current in-memory data to disk atomically.

        ``Store.async_save()`` writes to a temporary file and renames it
        into place, so partial writes are impossible.

        Raises:
            RuntimeError: If ``async_load()`` has not been called yet.
        """
        if self._data is None:
            raise RuntimeError(
                "SlotSentryStore.async_save() called before async_load()"
            )
        await self._store.async_save(self._data)
        _LOGGER.debug("SlotSentry storage saved to disk")

    async def async_remove(self) -> None:
        """Delete the storage file from disk permanently.

        Called during ``async_remove_entry`` when the user fully removes
        the integration. After this call the store instance is unusable.
        """
        await self._store.async_remove()
        self._data = None
        _LOGGER.info("SlotSentry storage file removed from disk")

    # ------------------------------------------------------------------
    # Secure mode: encryption at rest
    # ------------------------------------------------------------------

    @property
    def is_encrypted(self) -> bool:
        """True if the on-disk data has encrypted codes.

        The ``"encrypted"`` flag is set in the root of the storage dict
        when codes are saved with encryption.  It is cleared when codes
        are saved in plaintext.
        """
        self._require_loaded()
        assert self._data is not None
        return bool(self._data.get("encrypted", False))

    def decrypt_codes(self, key: bytes) -> None:
        """Decrypt all PIN codes in memory using the given AES key.

        After this call, ``code_1`` and ``code_2`` fields in every
        slot contain plaintext values.  Safe to call on already-decrypted
        data (encrypted strings contain a ``:`` separator; digit-only
        strings are assumed to already be plaintext).

        Args:
            key: 32-byte AES-256 key from ``crypto.derive_encryption_key``.
        """
        self._require_loaded()
        assert self._data is not None

        from .crypto import decrypt_code  # noqa: E402

        slots = self._data.get("slots", {})
        decrypted_count = 0
        for slot_key, slot_data in slots.items():
            for code_field in ("code_1", "code_2"):
                raw = slot_data.get(code_field, "")
                if raw and ":" in raw:
                    # Looks like an encrypted value (nonce:ciphertext).
                    try:
                        slot_data[code_field] = decrypt_code(raw, key)
                        decrypted_count += 1
                    except Exception:  # noqa: BLE001
                        _LOGGER.error(
                            "Failed to decrypt %s for slot %s",
                            code_field,
                            slot_key,
                        )
                        slot_data[code_field] = ""

        self._data["encrypted"] = False
        _LOGGER.info("Decrypted %d code field(s) in memory", decrypted_count)

    def encrypt_codes(self, key: bytes) -> None:
        """Encrypt all PIN codes in memory using the given AES key.

        After this call, ``code_1`` and ``code_2`` fields contain
        AES-GCM encrypted values.  Safe to call on already-encrypted data.

        Args:
            key: 32-byte AES-256 key from ``crypto.derive_encryption_key``.
        """
        self._require_loaded()
        assert self._data is not None

        from .crypto import encrypt_code  # noqa: E402

        slots = self._data.get("slots", {})
        encrypted_count = 0
        for slot_key, slot_data in slots.items():
            for code_field in ("code_1", "code_2"):
                raw = slot_data.get(code_field, "")
                if raw and ":" not in raw:
                    # Plaintext — encrypt it.
                    slot_data[code_field] = encrypt_code(raw, key)
                    encrypted_count += 1

        self._data["encrypted"] = True
        _LOGGER.info("Encrypted %d code field(s) in memory", encrypted_count)

    async def async_save_encrypted(self, key: bytes) -> None:
        """Save to disk with codes encrypted, then restore plaintext in memory.

        This is the secure-mode save path.  It:
          1. Makes a deep copy of ``_data``.
          2. Encrypts codes in the copy.
          3. Writes the encrypted copy to disk.
          4. Leaves ``_data`` in its original (plaintext) state.

        Args:
            key: 32-byte AES-256 key.
        """
        if self._data is None:
            raise RuntimeError(
                "SlotSentryStore.async_save_encrypted() called before async_load()"
            )

        from .crypto import encrypt_code  # noqa: E402

        # Deep copy so we don't mutate the live data.
        disk_data = copy.deepcopy(self._data)
        slots = disk_data.get("slots", {})
        for slot_data in slots.values():
            for code_field in ("code_1", "code_2"):
                raw = slot_data.get(code_field, "")
                if raw and ":" not in raw:
                    slot_data[code_field] = encrypt_code(raw, key)

        disk_data["encrypted"] = True
        await self._store.async_save(disk_data)
        _LOGGER.debug("SlotSentry storage saved (encrypted) to disk")

    # ------------------------------------------------------------------
    # Slot accessors
    # ------------------------------------------------------------------

    def get_slots(self) -> dict[int, SlotData]:
        """Return all slots as a mapping of slot_number → SlotData.

        Returns:
            Dict with integer keys 1 … slot_count.

        Raises:
            RuntimeError: If ``async_load()`` has not been called yet.
        """
        self._require_loaded()
        assert self._data is not None  # for type narrowing

        result: dict[int, SlotData] = {}
        for key, raw_slot in self._data.get("slots", {}).items():
            try:
                slot_number = int(key)
            except ValueError:
                _LOGGER.warning(
                    "Skipping slot with non-integer key %r in storage", key
                )
                continue
            result[slot_number] = SlotData.from_dict(slot_number, raw_slot)
        return result

    def get_slot(self, slot_number: int) -> SlotData | None:
        """Return a single slot by number, or None if it does not exist.

        Args:
            slot_number: 1-based slot index.
        """
        self._require_loaded()
        assert self._data is not None

        raw_slot = self._data.get("slots", {}).get(str(slot_number))
        if raw_slot is None:
            return None
        return SlotData.from_dict(slot_number, raw_slot)

    def set_slot(self, slot: SlotData) -> None:
        """Write a slot into the in-memory cache.

        The ``updated_at`` timestamp is set to now.  ``created_at`` is
        preserved if the slot already existed; otherwise it is also set
        to now.

        Call ``async_save()`` after all mutations to flush to disk.

        Args:
            slot: The SlotData to persist.  ``slot.slot_number`` is used
                  as the storage key.
        """
        self._require_loaded()
        assert self._data is not None

        key = str(slot.slot_number)
        existing = self._data["slots"].get(key, {})

        now = _utcnow_iso()
        created_at = existing.get("created_at") or now

        self._data["slots"][key] = {
            "label": slot.label,
            "code_1": slot.code_1,
            "code_2": slot.code_2,
            "enabled": slot.enabled,
            "created_at": created_at,
            "updated_at": now,
        }
        _LOGGER.debug("Slot %d updated in memory", slot.slot_number)

    def delete_slot(self, slot_number: int) -> None:
        """Reset a slot to its empty default state.

        The slot entry is kept in storage (to maintain the slot_count
        invariant) but all user-supplied fields are cleared.  Commit
        state for all locks is set to out_of_sync so that the next push
        will clear the code from the physical lock.

        Args:
            slot_number: 1-based slot index to clear.
        """
        self._require_loaded()
        assert self._data is not None

        key = str(slot_number)
        if key in self._data["slots"]:
            self._data["slots"][key] = SlotData.empty(slot_number).to_dict()
            _LOGGER.debug("Slot %d cleared in memory", slot_number)

        # Mark out_of_sync on every lock so the commit engine knows to
        # clear the code from the physical hardware.
        for lock_entity, slots in self._data.get("lock_commit", {}).items():
            if key in slots:
                slots[key]["state"] = SYNC_OUT_OF_SYNC
                _LOGGER.debug(
                    "Lock commit for %s slot %d → out_of_sync after delete",
                    lock_entity,
                    slot_number,
                )

    # ------------------------------------------------------------------
    # Lock commit accessors
    # ------------------------------------------------------------------

    def get_lock_commit(
        self, lock_entity: str, slot_number: int
    ) -> LockSlotCommit:
        """Return the commit state for a specific lock + slot combination.

        If no record exists (e.g., the lock was added after initial
        setup), a fresh ``initial()`` entry is returned (but not
        persisted until ``set_lock_commit`` is called).

        Args:
            lock_entity: Full entity ID, e.g. ``"lock.back_door"``.
            slot_number: 1-based slot index.
        """
        self._require_loaded()
        assert self._data is not None

        key = str(slot_number)
        raw = (
            self._data.get("lock_commit", {})
            .get(lock_entity, {})
            .get(key)
        )
        if raw is None:
            _LOGGER.debug(
                "No commit record for %s slot %d; returning initial state",
                lock_entity,
                slot_number,
            )
            return LockSlotCommit.initial(slot_number)
        return LockSlotCommit.from_dict(slot_number, raw)

    def set_lock_commit(
        self, lock_entity: str, commit: LockSlotCommit
    ) -> None:
        """Update the commit state for a lock + slot in the in-memory cache.

        Creates the per-lock dict if it does not yet exist.  Call
        ``async_save()`` afterwards to persist.

        Args:
            lock_entity: Full entity ID, e.g. ``"lock.back_door"``.
            commit:      The updated LockSlotCommit to store.
        """
        self._require_loaded()
        assert self._data is not None

        if "lock_commit" not in self._data:
            self._data["lock_commit"] = {}

        if lock_entity not in self._data["lock_commit"]:
            self._data["lock_commit"][lock_entity] = {}

        self._data["lock_commit"][lock_entity][str(commit.slot_number)] = (
            commit.to_dict()
        )
        _LOGGER.debug(
            "Lock commit for %s slot %d → %s",
            lock_entity,
            commit.slot_number,
            commit.state,
        )

    def get_all_lock_commits(
        self, lock_entity: str
    ) -> dict[int, LockSlotCommit]:
        """Return every commit record for the specified lock.

        Returns an empty dict if no records exist for this lock (e.g., it
        was just added to the config).

        Args:
            lock_entity: Full entity ID, e.g. ``"lock.back_door"``.

        Returns:
            Mapping of slot_number (int) → LockSlotCommit.
        """
        self._require_loaded()
        assert self._data is not None

        raw_lock = self._data.get("lock_commit", {}).get(lock_entity, {})
        result: dict[int, LockSlotCommit] = {}
        for key, raw_commit in raw_lock.items():
            try:
                slot_number = int(key)
            except ValueError:
                _LOGGER.warning(
                    "Skipping lock commit with non-integer key %r for %s",
                    key,
                    lock_entity,
                )
                continue
            result[slot_number] = LockSlotCommit.from_dict(slot_number, raw_commit)
        return result

    def remove_lock(self, lock_entity: str) -> None:
        """Remove all commit records for a lock that has been de-configured.

        The slot data itself is untouched; only the per-lock commit array
        is removed.  Call ``async_save()`` afterwards.

        Args:
            lock_entity: Full entity ID of the lock to remove.
        """
        self._require_loaded()
        assert self._data is not None

        removed = self._data.get("lock_commit", {}).pop(lock_entity, None)
        if removed is not None:
            _LOGGER.info(
                "Removed lock commit records for %s from storage", lock_entity
            )

    def initialise_lock_commits(
        self, lock_entity: str, slot_count: int
    ) -> None:
        """Populate out_of_sync commit entries for a newly added lock.

        Existing entries for the lock are preserved; only missing slot
        numbers are added.  This ensures that adding a lock mid-lifecycle
        does not reset slots that were already pushed.

        Args:
            lock_entity: Full entity ID of the new lock.
            slot_count:  Number of slots to initialise (1 … slot_count).
        """
        self._require_loaded()
        assert self._data is not None

        if "lock_commit" not in self._data:
            self._data["lock_commit"] = {}

        if lock_entity not in self._data["lock_commit"]:
            self._data["lock_commit"][lock_entity] = {}

        lock_data = self._data["lock_commit"][lock_entity]
        added = 0
        for n in range(1, slot_count + 1):
            key = str(n)
            if key not in lock_data:
                lock_data[key] = LockSlotCommit.initial(n).to_dict()
                added += 1

        if added:
            _LOGGER.debug(
                "Initialised %d commit entries for %s", added, lock_entity
            )

    # ------------------------------------------------------------------
    # Convenience: config sub-key
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Return the ``config`` sub-dict (UI preferences, etc.)."""
        self._require_loaded()
        assert self._data is not None
        return self._data.get("config", {})

    def set_config_value(self, key: str, value: Any) -> None:
        """Set a single value in the ``config`` sub-dict.

        Args:
            key:   Config key (e.g. ``"dont_show_test_popup"``).
            value: Serialisable value to store.
        """
        self._require_loaded()
        assert self._data is not None

        if "config" not in self._data:
            self._data["config"] = {}
        self._data["config"][key] = value

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_data(slot_count: int) -> dict[str, Any]:
        """Generate a blank storage schema for *slot_count* slots.

        All slots are initialised to empty / disabled.  No lock commit
        entries are created here; call ``initialise_lock_commits()`` once
        the configured locks are known.

        Args:
            slot_count: Number of slots to pre-populate (0 is valid for a
                        freshly created, not-yet-configured entry).

        Returns:
            A fully-formed storage dict at ``STORAGE_VERSION``.
        """
        slots: dict[str, Any] = {}
        for n in range(1, slot_count + 1):
            slots[str(n)] = SlotData.empty(n).to_dict()

        return {
            "version": STORAGE_VERSION,
            "slot_count": slot_count,
            "code_length_mode": "dual",
            "slots": slots,
            "lock_commit": {},
            "config": {
                "dont_show_test_popup": False,
            },
        }

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    @staticmethod
    def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
        """Migrate storage schema v1 → v2: rename long_code/short_code to code_1/code_2."""
        slots = data.get("slots", {})
        for slot_key, slot_data in slots.items():
            if "long_code" in slot_data:
                slot_data["code_1"] = slot_data.pop("long_code")
            if "short_code" in slot_data:
                slot_data["code_2"] = slot_data.pop("short_code")
            slot_data.setdefault("code_1", "")
            slot_data.setdefault("code_2", "")
        return data

    @staticmethod
    def _migrate(data: dict[str, Any]) -> dict[str, Any]:
        """Apply schema migrations from the stored version to STORAGE_VERSION.

        Migrations are applied sequentially so that each step only needs
        to know about the immediately preceding version.

        Args:
            data: Raw dict loaded from disk.

        Returns:
            Migrated dict at STORAGE_VERSION.
        """
        stored_version: int = data.get("version", 0)

        if stored_version == STORAGE_VERSION:
            return data

        if stored_version > STORAGE_VERSION:
            _LOGGER.warning(
                "SlotSentry storage version %d is newer than this "
                "integration supports (%d).  Data will be loaded as-is; "
                "update the integration to avoid data loss.",
                stored_version,
                STORAGE_VERSION,
            )
            return data

        while data.get("version", 0) < STORAGE_VERSION:
            v = data.get("version", 0)
            if v == 1:
                _LOGGER.info("Migrating SlotSentry storage v1 → v2")
                data = SlotSentryStore._migrate_v1_to_v2(data)
                data["version"] = 2
            else:
                _LOGGER.warning(
                    "SlotSentry storage version %d is unknown (expected %d); "
                    "no migration applied.",
                    v,
                    STORAGE_VERSION,
                )
                break

        return data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_loaded(self) -> None:
        """Raise RuntimeError if async_load() has not been called yet."""
        if self._data is None:
            raise RuntimeError(
                "SlotSentryStore has not been loaded. "
                "Call await store.async_load() before accessing data."
            )
