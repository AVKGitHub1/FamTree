"""Server-side sessions. Only a digest of each session token is stored, and the
role is re-read from the access code on every request, so revocation and
role changes take effect on the holder's next request."""

from __future__ import annotations

from dataclasses import dataclass, replace

from famtree import clock
from famtree.security.permissions import GUEST, Role, Viewer
from famtree.security.tokens import new_csrf_token, new_session_token, token_digest
from famtree.storage import meta
from famtree.storage.database import Connection


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    expires_at: str


def create_session(
    conn: Connection, principal: str, code_id: str | None, ttl_hours: int
) -> IssuedSession:
    token, csrf = new_session_token(), new_csrf_token()
    expires = clock.iso_after(ttl_hours)
    conn.execute(
        "INSERT INTO sessions (token_digest, principal, code_id, csrf_token, created_at, "
        "expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (token_digest(token), principal, code_id, csrf, clock.now_iso(), expires),
    )
    return IssuedSession(token, csrf, expires)


def guest_access_enabled(conn: Connection) -> bool:
    """Whether visitors without a code may read the public tree (the default)."""
    return meta.get(conn, meta.GUEST_ACCESS) != "off"


def set_guest_access(conn: Connection, enabled: bool) -> None:
    meta.put(conn, meta.GUEST_ACCESS, "on" if enabled else "off")


def guest(conn: Connection) -> Viewer:
    return GUEST if guest_access_enabled(conn) else replace(GUEST, guest_access=False)


def resolve_session(conn: Connection, token: str | None) -> Viewer:
    """The caller's current permissions; a guest for no, expired or revoked sessions."""
    if not token or len(token) > 200:
        return guest(conn)
    digest = token_digest(token)
    row = conn.execute(
        "SELECT s.principal, s.code_id, s.csrf_token, s.expires_at, c.role, c.revoked_at "
        "FROM sessions s LEFT JOIN access_codes c ON c.id = s.code_id "
        "WHERE s.token_digest = ?",
        (digest,),
    ).fetchone()
    if row is None or row["expires_at"] <= clock.now_iso():
        return guest(conn)
    if row["principal"] == "admin":
        return Viewer(Role.ADMIN, digest, None, row["csrf_token"])
    if row["role"] is None or row["revoked_at"] is not None:
        return guest(conn)
    return Viewer(Role(row["role"]), digest, row["code_id"], row["csrf_token"])


def delete_session(conn: Connection, digest: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_digest = ?", (digest,))


def delete_admin_sessions(conn: Connection, keep_digest: str | None = None) -> int:
    cursor = conn.execute(
        "DELETE FROM sessions WHERE principal = 'admin' AND token_digest IS NOT ?",
        (keep_digest,),
    )
    return cursor.rowcount


def delete_code_sessions(conn: Connection, code_id: str) -> None:
    conn.execute("DELETE FROM sessions WHERE code_id = ?", (code_id,))


def purge_expired(conn: Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (clock.now_iso(),))
