"""Admin-managed access codes. Full values are kept (inside the encrypted
database) so the admin can reveal them later; lookups use a digest."""

from __future__ import annotations

from dataclasses import dataclass

from famtree import clock
from famtree.domain.errors import InvalidInput, NotFound
from famtree.security.permissions import CODE_ROLES, Role
from famtree.security.sessions import delete_code_sessions
from famtree.security.tokens import code_digest, generate_access_code, new_id, normalize_code
from famtree.storage.database import Connection

MAX_LABEL = 80


@dataclass(frozen=True)
class AccessCode:
    id: str
    label: str
    role: Role
    created_at: str
    revoked_at: str | None


def _clean_label(label: str) -> str:
    label = " ".join(label.split())
    if len(label) > MAX_LABEL:
        raise InvalidInput(f"Labels can be at most {MAX_LABEL} characters.")
    return label


def _check_role(role: Role) -> Role:
    if role not in CODE_ROLES:
        raise InvalidInput("Codes can grant public viewer, private viewer or editor access.")
    return role


def list_codes(conn: Connection) -> list[AccessCode]:
    return [
        AccessCode(r["id"], r["label"], Role(r["role"]), r["created_at"], r["revoked_at"])
        for r in conn.execute(
            "SELECT id, label, role, created_at, revoked_at FROM access_codes ORDER BY seq DESC"
        )
    ]


def create_code(conn: Connection, label: str, role: Role) -> tuple[AccessCode, str]:
    value = generate_access_code()
    code = AccessCode(new_id(), _clean_label(label), _check_role(role), clock.now_iso(), None)
    conn.execute(
        "INSERT INTO access_codes (id, label, role, code_value, code_digest, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code.id, code.label, code.role.value, value, code_digest(value), code.created_at),
    )
    return code, value


def reveal_code(conn: Connection, code_id: str) -> str:
    row = conn.execute("SELECT code_value FROM access_codes WHERE id = ?", (code_id,)).fetchone()
    if row is None:
        raise NotFound("That code no longer exists.")
    return row["code_value"]


def update_code(
    conn: Connection,
    code_id: str,
    label: str | None = None,
    role: Role | None = None,
    revoked: bool | None = None,
) -> None:
    row = conn.execute("SELECT revoked_at FROM access_codes WHERE id = ?", (code_id,)).fetchone()
    if row is None:
        raise NotFound("That code no longer exists.")
    if label is not None:
        conn.execute(
            "UPDATE access_codes SET label = ? WHERE id = ?", (_clean_label(label), code_id)
        )
    if role is not None:
        conn.execute(
            "UPDATE access_codes SET role = ? WHERE id = ?", (_check_role(role).value, code_id)
        )
    if revoked is True and row["revoked_at"] is None:
        conn.execute(
            "UPDATE access_codes SET revoked_at = ? WHERE id = ?", (clock.now_iso(), code_id)
        )
        delete_code_sessions(conn, code_id)
    elif revoked is False:
        conn.execute("UPDATE access_codes SET revoked_at = NULL WHERE id = ?", (code_id,))


def delete_code(conn: Connection, code_id: str) -> None:
    # Sessions issued from the code cascade with it.
    if conn.execute("DELETE FROM access_codes WHERE id = ?", (code_id,)).rowcount == 0:
        raise NotFound("That code no longer exists.")


def find_active_code(conn: Connection, raw: str) -> str | None:
    """ID of the unrevoked code matching `raw`, if any."""
    if not normalize_code(raw):
        return None
    row = conn.execute(
        "SELECT id FROM access_codes WHERE code_digest = ? AND revoked_at IS NULL",
        (code_digest(raw),),
    ).fetchone()
    return None if row is None else row["id"]
