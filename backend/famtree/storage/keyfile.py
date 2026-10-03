"""Loading the database encryption key from a separately mounted secret file."""

from __future__ import annotations

import logging
import re
import secrets
import stat
from pathlib import Path

log = logging.getLogger(__name__)

_HEX_KEY = re.compile(r"^[0-9a-fA-F]{64}$")


class KeyFileError(RuntimeError):
    """The key file is missing, unreadable, or malformed."""


class DatabaseKey:
    """A 256-bit raw SQLCipher key. The value never appears in repr or logs."""

    __slots__ = ("_hex",)

    def __init__(self, hex_key: str) -> None:
        if not _HEX_KEY.match(hex_key):
            raise KeyFileError("encryption key must be exactly 64 hexadecimal characters")
        self._hex = hex_key.lower()

    @property
    def pragma_value(self) -> str:
        """The `PRAGMA key` argument for a raw key (skips passphrase derivation)."""
        return f"x'{self._hex}'"

    def __repr__(self) -> str:
        return "DatabaseKey(<redacted>)"

    @classmethod
    def generate(cls) -> DatabaseKey:
        return cls(secrets.token_hex(32))

    def to_file_text(self) -> str:
        return self._hex + "\n"


def load_key(path: Path) -> DatabaseKey:
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise KeyFileError(
            f"encryption key file not found at {path}. Mount the key as a secret "
            "(see docs/operations.md, 'Encryption key')."
        ) from exc
    except OSError as exc:
        raise KeyFileError(f"cannot access encryption key file {path}: {exc.strerror}") from exc

    if not stat.S_ISREG(info.st_mode):
        raise KeyFileError(f"encryption key path {path} is not a regular file")
    if info.st_mode & 0o077:
        log.warning(
            "Encryption key file %s is readable by group or others; restrict it with chmod 600.",
            path,
        )
    try:
        text = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise KeyFileError(f"cannot read encryption key file {path}") from exc
    try:
        return DatabaseKey(text)
    except KeyFileError as exc:
        raise KeyFileError(f"{path}: {exc}") from None
