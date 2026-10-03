"""Salted admin password hashing (Argon2id)."""

from __future__ import annotations

import threading

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256

_hasher = PasswordHasher()  # Argon2id with the library's recommended parameters
# Each verification allocates ~64 MiB; cap concurrency on small hosts.
_verify_slots = threading.BoundedSemaphore(2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    if not password or len(password) > MAX_PASSWORD_LENGTH:
        return False
    with _verify_slots:
        try:
            return _hasher.verify(stored_hash, password)
        except (VerificationError, InvalidHashError):
            return False


def validate_new_password(password: str) -> str | None:
    """Return a problem description, or None if the password is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Use at most {MAX_PASSWORD_LENGTH} characters."
    if password.strip() != password:
        return "Remove leading or trailing spaces."
    return None
