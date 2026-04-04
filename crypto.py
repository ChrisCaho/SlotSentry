"""SlotSentry cryptography — password hashing, PIN encryption, session tokens.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Provides:
  - PBKDF2-based password hashing and verification.
  - AES-GCM encryption/decryption of PIN code strings.
  - In-memory session token management with TTL expiry.

Revision: 1.0
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from base64 import b64decode, b64encode
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from .const import (
    MAX_PASSWORD_ATTEMPTS,
    PBKDF2_ITERATIONS,
    SESSION_TOKEN_TTL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

# AES-256 key length
_KEY_LENGTH = 32
# Salt length for PBKDF2
_SALT_LENGTH = 16
# Nonce length for AES-GCM (96 bits recommended)
_NONCE_LENGTH = 12


# ---------------------------------------------------------------------------
# Password hashing (for verification — stored in config entry data)
# ---------------------------------------------------------------------------


def hash_password(password: str, salt: bytes | None = None) -> dict[str, str]:
    """Hash a password with PBKDF2-SHA256 and return storable components.

    Args:
        password: The plaintext password.
        salt:     Optional salt bytes. Generated randomly if not provided.

    Returns:
        Dict with ``"salt"`` and ``"hash"`` as base64-encoded strings,
        plus ``"iterations"`` as an integer.
    """
    if salt is None:
        salt = os.urandom(_SALT_LENGTH)

    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    return {
        "salt": b64encode(salt).decode("ascii"),
        "hash": b64encode(pw_hash).decode("ascii"),
        "iterations": PBKDF2_ITERATIONS,
    }


def verify_password(password: str, stored: dict[str, Any]) -> bool:
    """Verify a password against a stored hash.

    Args:
        password: The plaintext password to verify.
        stored:   Dict with ``"salt"``, ``"hash"``, ``"iterations"``
                  as returned by ``hash_password()``.

    Returns:
        True if the password matches.
    """
    salt = b64decode(stored["salt"])
    iterations = int(stored.get("iterations", PBKDF2_ITERATIONS))

    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )

    expected = b64decode(stored["hash"])
    return hmac.compare_digest(pw_hash, expected)


# ---------------------------------------------------------------------------
# Encryption key derivation (separate from password hash)
# ---------------------------------------------------------------------------


def derive_encryption_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from the password using PBKDF2.

    Uses a different context than password hashing to ensure the
    verification hash and encryption key are independent.

    Args:
        password: The plaintext password.
        salt:     Salt bytes (stored alongside encrypted data).

    Returns:
        32-byte AES-256 key.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


# ---------------------------------------------------------------------------
# AES-GCM encryption / decryption of individual PIN codes
# ---------------------------------------------------------------------------


def encrypt_code(code: str, key: bytes) -> str:
    """Encrypt a PIN code string with AES-256-GCM.

    Args:
        code: The plaintext PIN code.
        key:  32-byte AES key from ``derive_encryption_key()``.

    Returns:
        Base64-encoded string in the format ``nonce:ciphertext``
        (both parts base64-encoded, colon-separated).
    """
    if not code:
        return ""

    nonce = os.urandom(_NONCE_LENGTH)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, code.encode("utf-8"), None)

    return (
        b64encode(nonce).decode("ascii")
        + ":"
        + b64encode(ciphertext).decode("ascii")
    )


def decrypt_code(encrypted: str, key: bytes) -> str:
    """Decrypt a PIN code string encrypted with ``encrypt_code()``.

    Args:
        encrypted: Base64 ``nonce:ciphertext`` string.
        key:       32-byte AES key from ``derive_encryption_key()``.

    Returns:
        The plaintext PIN code string.

    Raises:
        ValueError: If the encrypted string is malformed.
        cryptography.exceptions.InvalidTag: If the key is wrong or data
            is corrupted.
    """
    if not encrypted:
        return ""

    parts = encrypted.split(":", 1)
    if len(parts) != 2:
        raise ValueError("Malformed encrypted code — expected nonce:ciphertext")

    nonce = b64decode(parts[0])
    ciphertext = b64decode(parts[1])

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# Session token management (in-memory, per-entry)
# ---------------------------------------------------------------------------


class SecureSession:
    """Manages session tokens for secure mode unlock.

    One instance per config entry. Tokens are stored in memory only —
    never persisted to disk. Each token has a TTL after which it expires.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, float] = {}  # token → expiry timestamp
        self._encryption_key: bytes | None = None
        self._failed_attempts: int = 0

    @property
    def is_unlocked(self) -> bool:
        """True if there is at least one valid (non-expired) session token."""
        now = time.time()
        # Clean expired tokens
        self._tokens = {
            t: exp for t, exp in self._tokens.items() if exp > now
        }
        return bool(self._tokens)

    @property
    def encryption_key(self) -> bytes | None:
        """Return the derived encryption key, or None if locked."""
        if not self.is_unlocked:
            self._encryption_key = None
            return None
        return self._encryption_key

    @property
    def failed_attempts(self) -> int:
        """Return the number of consecutive failed unlock attempts."""
        return self._failed_attempts

    @property
    def is_locked_out(self) -> bool:
        """True if too many failed attempts have occurred."""
        return self._failed_attempts >= MAX_PASSWORD_ATTEMPTS

    def unlock(self, key: bytes) -> str:
        """Create a new session token and store the encryption key.

        Args:
            key: The derived encryption key (from ``derive_encryption_key``).

        Returns:
            A new session token string.
        """
        token = secrets.token_urlsafe(32)
        ttl_seconds = SESSION_TOKEN_TTL_HOURS * 3600
        self._tokens[token] = time.time() + ttl_seconds
        self._encryption_key = key
        self._failed_attempts = 0
        _LOGGER.info("Secure mode session unlocked (token TTL: %dh)", SESSION_TOKEN_TTL_HOURS)
        return token

    def validate_token(self, token: str) -> bool:
        """Check if a session token is valid and not expired."""
        expiry = self._tokens.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._tokens[token]
            return False
        return True

    def lock(self) -> None:
        """Invalidate all session tokens and wipe the encryption key."""
        self._tokens.clear()
        self._encryption_key = None
        _LOGGER.info("Secure mode session locked")

    def record_failed_attempt(self) -> None:
        """Record a failed password attempt."""
        self._failed_attempts += 1
        _LOGGER.warning(
            "Secure mode: failed unlock attempt %d/%d",
            self._failed_attempts,
            MAX_PASSWORD_ATTEMPTS,
        )

    def reset_lockout(self) -> None:
        """Reset the failed attempt counter."""
        self._failed_attempts = 0
