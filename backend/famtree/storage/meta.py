"""Key/value settings kept in the encrypted `meta` table."""

from __future__ import annotations

from famtree.storage.database import Connection

SCHEMA_VERSION = "schema_version"
INITIALIZED_AT = "initialized_at"
ADMIN_PASSWORD_HASH = "admin_password_hash"
ADMIN_PASSWORD_CHANGED_AT = "admin_password_changed_at"
GUEST_ACCESS = "guest_access"
# The highest revision any deleted tree record had (kept up by triggers).
RETIRED_REVISION = "retired_revision"


def get(conn: Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def put(conn: Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
