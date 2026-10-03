"""Generation and digesting of passwords, access codes, session tokens and IDs."""

from __future__ import annotations

import hashlib
import secrets

# Unambiguous uppercase alphabet: no 0/O or 1/I. 32 symbols = 5 bits each.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _grouped(groups: int, size: int = 4) -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(size)) for _ in range(groups))


def generate_admin_password() -> str:
    """100 bits of entropy, e.g. `K7QM-2XRB-...` (5 groups of 4)."""
    return _grouped(5)


def generate_access_code() -> str:
    """80 bits of entropy (4 groups of 4); lookups are rate-limited."""
    return _grouped(4)


def normalize_code(raw: str) -> str:
    """Accept codes typed in any case, with or without separators."""
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def code_digest(raw: str) -> str:
    # Codes are high-entropy random values, so a fast digest is sufficient for
    # lookup; the full value is kept separately (encrypted with the database).
    return hashlib.sha256(normalize_code(raw).encode("ascii", "ignore")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def new_id() -> str:
    """Random, stable record ID. Random rather than sequential so IDs reveal
    nothing about how many private records exist."""
    return secrets.token_hex(8)
