"""SQL access for family data. Functions take an open connection; callers own
the transaction (see `Database.read`/`Database.write`)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from famtree import clock
from famtree.domain.attributes import ValueType, label_key
from famtree.domain.model import (
    AttributeDefinition,
    AttributeValue,
    FamilyGraph,
    ParentLink,
    ParentRole,
    Person,
    SpouseLink,
)
from famtree.security.tokens import new_id
from famtree.storage.database import Connection, Row

if TYPE_CHECKING:
    from famtree.domain.pictures import Picture


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# --- reading -----------------------------------------------------------------


def load_definitions(conn: Connection) -> dict[str, AttributeDefinition]:
    rows = conn.execute(
        "SELECT id, seq, label, value_type, builtin, revision "
        "FROM attribute_definitions ORDER BY seq"
    )
    return {
        row["id"]: AttributeDefinition(
            id=row["id"],
            seq=row["seq"],
            label=row["label"],
            value_type=ValueType(row["value_type"]),
            builtin=bool(row["builtin"]),
            revision=row["revision"],
        )
        for row in rows
    }


def _parent_link(row: Row) -> ParentLink:
    return ParentLink(
        id=row["id"],
        seq=row["seq"],
        parent_id=row["parent_id"],
        child_id=row["child_id"],
        role=ParentRole(row["role"]),
        is_public=bool(row["is_public"]),
        revision=row["revision"],
    )


def _spouse_link(row: Row) -> SpouseLink:
    return SpouseLink(
        id=row["id"],
        seq=row["seq"],
        person_a=row["person_a"],
        person_b=row["person_b"],
        is_public=bool(row["is_public"]),
        revision=row["revision"],
    )


def load_graph(conn: Connection) -> FamilyGraph:
    values: dict[str, dict[str, AttributeValue]] = {}
    for row in conn.execute(
        "SELECT person_id, definition_id, value, is_public FROM attribute_values"
    ):
        values.setdefault(row["person_id"], {})[row["definition_id"]] = AttributeValue(
            definition_id=row["definition_id"],
            value=json.loads(row["value"]),
            is_public=bool(row["is_public"]),
        )
    people = {
        row["id"]: Person(
            id=row["id"],
            seq=row["seq"],
            name=row["name"],
            revision=row["revision"],
            attributes=values.get(row["id"], {}),
        )
        for row in conn.execute("SELECT id, seq, name, revision FROM people ORDER BY seq")
    }
    parent_links = [
        _parent_link(row) for row in conn.execute("SELECT * FROM parent_links ORDER BY seq")
    ]
    spouse_links = [
        _spouse_link(row) for row in conn.execute("SELECT * FROM spouse_links ORDER BY seq")
    ]
    return FamilyGraph(people, parent_links, spouse_links, load_definitions(conn))


def person_revision(conn: Connection, person_id: str) -> int | None:
    row = conn.execute("SELECT revision FROM people WHERE id = ?", (person_id,)).fetchone()
    return None if row is None else row["revision"]


def get_parent_link(conn: Connection, link_id: str) -> ParentLink | None:
    row = conn.execute("SELECT * FROM parent_links WHERE id = ?", (link_id,)).fetchone()
    return None if row is None else _parent_link(row)


def get_spouse_link(conn: Connection, link_id: str) -> SpouseLink | None:
    row = conn.execute("SELECT * FROM spouse_links WHERE id = ?", (link_id,)).fetchone()
    return None if row is None else _spouse_link(row)


def find_parent_link(conn: Connection, parent_id: str, child_id: str) -> ParentLink | None:
    row = conn.execute(
        "SELECT * FROM parent_links WHERE parent_id = ? AND child_id = ?", (parent_id, child_id)
    ).fetchone()
    return None if row is None else _parent_link(row)


def find_spouse_link(conn: Connection, a: str, b: str) -> SpouseLink | None:
    a, b = sorted((a, b))
    row = conn.execute(
        "SELECT * FROM spouse_links WHERE person_a = ? AND person_b = ?", (a, b)
    ).fetchone()
    return None if row is None else _spouse_link(row)


def values_for_definition(conn: Connection, definition_id: str) -> list[Any]:
    return [
        json.loads(row["value"])
        for row in conn.execute(
            "SELECT value FROM attribute_values WHERE definition_id = ?", (definition_id,)
        )
    ]


def value_counts(conn: Connection) -> dict[str, int]:
    return {
        row["definition_id"]: row["n"]
        for row in conn.execute(
            "SELECT definition_id, count(*) AS n FROM attribute_values GROUP BY definition_id"
        )
    }


def count_people(conn: Connection) -> int:
    return conn.execute("SELECT count(*) FROM people").fetchone()[0]


# --- writing -----------------------------------------------------------------


def insert_person(conn: Connection, name: str) -> str:
    person_id = new_id()
    now = clock.now_iso()
    conn.execute(
        "INSERT INTO people (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (person_id, name, now, now),
    )
    return person_id


def touch_person(conn: Connection, person_id: str, name: str | None = None) -> None:
    """Bump a person's revision, optionally renaming them."""
    if name is None:
        conn.execute(
            "UPDATE people SET revision = revision + 1, updated_at = ? WHERE id = ?",
            (clock.now_iso(), person_id),
        )
    else:
        conn.execute(
            "UPDATE people SET name = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
            (name, clock.now_iso(), person_id),
        )


def replace_attribute_values(
    conn: Connection, person_id: str, values: list[AttributeValue]
) -> None:
    conn.execute("DELETE FROM attribute_values WHERE person_id = ?", (person_id,))
    conn.executemany(
        "INSERT INTO attribute_values (person_id, definition_id, value, is_public) "
        "VALUES (?, ?, ?, ?)",
        [(person_id, v.definition_id, _dump(v.value), int(v.is_public)) for v in values],
    )


def delete_person(conn: Connection, person_id: str) -> None:
    # Attribute values and incident relationships cascade.
    conn.execute("DELETE FROM people WHERE id = ?", (person_id,))


def insert_parent_link(
    conn: Connection, parent_id: str, child_id: str, role: ParentRole, is_public: bool
) -> str:
    link_id = new_id()
    now = clock.now_iso()
    conn.execute(
        "INSERT INTO parent_links (id, parent_id, child_id, role, is_public, created_at, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (link_id, parent_id, child_id, role.value, int(is_public), now, now),
    )
    return link_id


def insert_spouse_link(conn: Connection, a: str, b: str, is_public: bool) -> str:
    link_id = new_id()
    now = clock.now_iso()
    a, b = sorted((a, b))
    conn.execute(
        "INSERT INTO spouse_links (id, person_a, person_b, is_public, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (link_id, a, b, int(is_public), now, now),
    )
    return link_id


def update_parent_link(conn: Connection, link_id: str, role: ParentRole, is_public: bool) -> None:
    conn.execute(
        "UPDATE parent_links SET role = ?, is_public = ?, revision = revision + 1, "
        "updated_at = ? WHERE id = ?",
        (role.value, int(is_public), clock.now_iso(), link_id),
    )


def update_spouse_link(conn: Connection, link_id: str, is_public: bool) -> None:
    conn.execute(
        "UPDATE spouse_links SET is_public = ?, revision = revision + 1, updated_at = ? "
        "WHERE id = ?",
        (int(is_public), clock.now_iso(), link_id),
    )


def delete_parent_link(conn: Connection, link_id: str) -> None:
    conn.execute("DELETE FROM parent_links WHERE id = ?", (link_id,))


def delete_spouse_link(conn: Connection, link_id: str) -> None:
    conn.execute("DELETE FROM spouse_links WHERE id = ?", (link_id,))


def insert_definition(conn: Connection, label: str, value_type: ValueType) -> str:
    definition_id = new_id()
    conn.execute(
        "INSERT INTO attribute_definitions (id, label, label_key, value_type, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (definition_id, label, label_key(label), value_type.value, clock.now_iso()),
    )
    return definition_id


def update_definition(
    conn: Connection, definition_id: str, label: str, value_type: ValueType
) -> None:
    conn.execute(
        "UPDATE attribute_definitions SET label = ?, label_key = ?, value_type = ?, "
        "revision = revision + 1 WHERE id = ?",
        (label, label_key(label), value_type.value, definition_id),
    )


def delete_definition(conn: Connection, definition_id: str) -> None:
    conn.execute("DELETE FROM attribute_definitions WHERE id = ?", (definition_id,))


def label_in_use(conn: Connection, label: str, except_id: str | None = None) -> bool:
    row = conn.execute(
        "SELECT id FROM attribute_definitions WHERE label_key = ?", (label_key(label),)
    ).fetchone()
    return row is not None and row["id"] != except_id


# --- pictures ----------------------------------------------------------------

# An upload is kept this long before a person's details are saved with it.
UNSAVED_PICTURE_HOURS = 1


def insert_image(conn: Connection, picture: Picture) -> str:
    image_id = new_id()
    conn.execute(
        "INSERT INTO images (id, full, thumb, width, height, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (image_id, picture.full, picture.thumb, picture.width, picture.height, clock.now_iso()),
    )
    return image_id


def image_exists(conn: Connection, image_id: str) -> bool:
    return conn.execute("SELECT 1 FROM images WHERE id = ?", (image_id,)).fetchone() is not None


def load_image(conn: Connection, image_id: str, variant: str = "full") -> bytes | None:
    column = {"full": "full", "thumb": "thumb"}[variant]
    row = conn.execute(f"SELECT {column} FROM images WHERE id = ?", (image_id,)).fetchone()
    return None if row is None else bytes(row[0])


IMAGES_IN_USE = (
    "SELECT json_extract(v.value, '$.id') FROM attribute_values v"
    " JOIN attribute_definitions d ON d.id = v.definition_id"
    " WHERE d.value_type = 'image' AND json_extract(v.value, '$.id') IS NOT NULL"
)


def delete_unused_images(conn: Connection) -> int:
    """Drop pictures neither a value nor a snapshot refers to (removed,
    replaced, their person deleted, or uploaded but never saved) once they are
    past an unsaved upload's grace period. Until then they are kept but never
    served: serving needs a value."""
    cursor = conn.execute(
        f"DELETE FROM images WHERE id NOT IN ({IMAGES_IN_USE})"
        " AND id NOT IN (SELECT image_id FROM snapshot_images) AND created_at < ?",
        (clock.iso_after(-UNSAVED_PICTURE_HOURS),),
    )
    return cursor.rowcount
