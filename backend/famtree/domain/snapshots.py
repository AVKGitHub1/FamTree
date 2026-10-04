"""Snapshots of the family tree, kept inside the encrypted database so the
admin can look back at earlier versions of the tree and load one.

A snapshot holds the tree alone: people, their details, relationships and
attribute definitions, plus references to the pictures it uses (kept for as
long as a snapshot refers to them). Access codes, sessions, guest access and
the admin password are not part of it; loading a snapshot leaves them as
they are.

Once a day the tree is compared with the latest daily snapshot. A changed
tree is saved as a new snapshot; an unchanged one renews the latest instead,
so a run of identical days is kept once. Only the latest `KEEP` snapshots
are kept: taking another deletes the oldest.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from famtree import clock
from famtree.domain import repository
from famtree.domain.errors import InvalidInput, NotFound
from famtree.security.tokens import new_id
from famtree.storage import meta
from famtree.storage.database import Connection
from famtree.storage.migrations import SCHEMA_VERSION


class SnapshotKind(StrEnum):
    DAILY = "daily"
    BEFORE_LOAD = "before_load"  # the tree as it was when another snapshot was loaded


# The tree tables in insertion order (each refers only to those before it),
# with what makes two trees the same: not ordering numbers, revisions or times.
TREE_TABLES: dict[str, tuple[str, ...]] = {
    "attribute_definitions": ("id", "label", "value_type", "builtin"),
    "people": ("id", "name", "sibling_order"),
    "attribute_values": ("person_id", "definition_id", "value", "is_public"),
    "parent_links": ("parent_id", "child_id", "role", "is_public"),
    "spouse_links": ("person_a", "person_b", "is_public"),
}
_ORDER = {"attribute_values": "person_id, definition_id"}  # the others by seq
# Tables whose rows carry a revision for optimistic edits.
_REVISED = ("attribute_definitions", "people", "parent_links", "spouse_links")

Tree = dict[str, list[dict[str, Any]]]

KEEP = 20  # snapshots kept, newest (by when they were last taken) first


@dataclass(frozen=True)
class SnapshotInfo:
    id: str
    kind: SnapshotKind
    first_taken: str  # when the tree was first seen like this
    taken_at: str  # when it was last seen like this
    people: int
    relationships: int
    size: int  # bytes stored
    loadable: bool  # taken with the current schema


def _capture(conn: Connection) -> Tree:
    return {
        table: [
            dict(row)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY {_ORDER.get(table, 'seq')}")
        ]
        for table in TREE_TABLES
    }


def _digest(tree: Tree) -> str:
    content = {
        table: sorted([row[column] for column in columns] for row in tree[table])
        for table, columns in TREE_TABLES.items()
    }
    text = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _encode(tree: Tree) -> bytes:
    return zlib.compress(json.dumps(tree, ensure_ascii=False, separators=(",", ":")).encode(), 9)


def _counts(tree: Tree) -> tuple[int, int]:
    return len(tree["people"]), len(tree["parent_links"]) + len(tree["spouse_links"])


def _keep_images(conn: Connection, snapshot_id: str) -> None:
    """Record the pictures the tree uses now as the snapshot's."""
    conn.execute("DELETE FROM snapshot_images WHERE snapshot_id = ?", (snapshot_id,))
    conn.execute(
        "INSERT INTO snapshot_images (snapshot_id, image_id) "
        f"SELECT ?, id FROM images WHERE id IN ({repository.IMAGES_IN_USE})",
        (snapshot_id,),
    )


def _insert(conn: Connection, kind: SnapshotKind, tree: Tree) -> str:
    snapshot_id = new_id()
    now = clock.now_iso()
    people, relationships = _counts(tree)
    conn.execute(
        "INSERT INTO snapshots (id, kind, schema_version, digest, first_taken, taken_at, "
        "people, relationships, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            snapshot_id,
            kind.value,
            SCHEMA_VERSION,
            _digest(tree),
            now,
            now,
            people,
            relationships,
            _encode(tree),
        ),
    )
    _keep_images(conn, snapshot_id)
    return snapshot_id


def _prune(conn: Connection) -> None:
    """Delete all but the latest `KEEP` snapshots. Their pictures go with the
    caller's `repository.delete_unused_images`, once the tree is final."""
    conn.execute(
        "DELETE FROM snapshots WHERE id NOT IN "
        "(SELECT id FROM snapshots ORDER BY taken_at DESC, seq DESC LIMIT ?)",
        (KEEP,),
    )


def take(conn: Connection, kind: SnapshotKind) -> str:
    """Save the current tree as a new snapshot, dropping the oldest beyond
    `KEEP`; returns its id."""
    snapshot_id = _insert(conn, kind, _capture(conn))
    _prune(conn)
    return snapshot_id


def _latest_daily(conn: Connection):
    return conn.execute(
        "SELECT id, digest, schema_version, taken_at FROM snapshots WHERE kind = 'daily' "
        "ORDER BY taken_at DESC, seq DESC LIMIT 1"
    ).fetchone()


def daily_due(conn: Connection) -> bool:
    """Whether today (UTC) has no daily snapshot yet."""
    latest = _latest_daily(conn)
    return latest is None or latest["taken_at"][:10] < clock.now_iso()[:10]


def take_daily(conn: Connection) -> Literal["created", "renewed"] | None:
    """Today's snapshot: a new one if the tree differs from the latest daily
    snapshot, or that one renewed if it does not. Nothing if today's is taken
    already or the tree is empty."""
    if not daily_due(conn):
        return None
    tree = _capture(conn)
    if not tree["people"]:
        return None
    latest = _latest_daily(conn)
    same = latest is not None and latest["schema_version"] == SCHEMA_VERSION
    if not same or latest["digest"] != _digest(tree):
        _insert(conn, SnapshotKind.DAILY, tree)
        _prune(conn)
        repository.delete_unused_images(conn)
        return "created"
    people, relationships = _counts(tree)
    conn.execute(
        "UPDATE snapshots SET taken_at = ?, people = ?, relationships = ?, data = ? WHERE id = ?",
        (clock.now_iso(), people, relationships, _encode(tree), latest["id"]),
    )
    _keep_images(conn, latest["id"])
    return "renewed"


def upgrade_stored(
    conn: Connection, old_version: int, new_version: int, upgrade: Callable[[Tree], None]
) -> None:
    """For a migration: bring snapshots taken with schema `old_version` to
    `new_version`, changing each stored tree in place with `upgrade`.

    `_digest` describes the latest schema's tree, so it is recomputed only by
    the last migration. A digest left behind costs at most one daily snapshot
    of an unchanged tree."""
    rows = conn.execute(
        "SELECT id, digest, data FROM snapshots WHERE schema_version = ?", (old_version,)
    ).fetchall()
    for row in rows:
        tree: Tree = json.loads(zlib.decompress(row["data"]))
        upgrade(tree)
        digest = _digest(tree) if new_version == SCHEMA_VERSION else row["digest"]
        conn.execute(
            "UPDATE snapshots SET schema_version = ?, digest = ?, data = ? WHERE id = ?",
            (new_version, digest, _encode(tree), row["id"]),
        )


def list_snapshots(conn: Connection) -> list[SnapshotInfo]:
    rows = conn.execute(
        "SELECT id, kind, schema_version, first_taken, taken_at, people, relationships, "
        "length(data) AS size FROM snapshots ORDER BY taken_at DESC, seq DESC"
    )
    return [
        SnapshotInfo(
            id=row["id"],
            kind=SnapshotKind(row["kind"]),
            first_taken=row["first_taken"],
            taken_at=row["taken_at"],
            people=row["people"],
            relationships=row["relationships"],
            size=row["size"],
            loadable=row["schema_version"] == SCHEMA_VERSION,
        )
        for row in rows
    ]


def delete(conn: Connection, snapshot_id: str) -> None:
    if conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,)).rowcount == 0:
        raise NotFound("That snapshot no longer exists.")
    repository.delete_unused_images(conn)


def load(conn: Connection, snapshot_id: str) -> str:
    """Replace the tree with the snapshot's, after saving the current tree as a
    snapshot of its own. Returns the id of that saved snapshot."""
    row = conn.execute(
        "SELECT schema_version, data FROM snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    if row is None:
        raise NotFound("That snapshot no longer exists.")
    if row["schema_version"] != SCHEMA_VERSION:
        raise InvalidInput(
            "This snapshot was taken by a different version of FamTree and cannot be loaded."
        )
    tree: Tree = json.loads(zlib.decompress(row["data"]))
    # This may drop the snapshot being loaded, if it is the oldest; its tree
    # becomes the current one, which is snapshotted again before it is ever
    # replaced. Unused pictures are cleaned up only once it is in place.
    saved = take(conn, SnapshotKind.BEFORE_LOAD)

    for table in reversed(TREE_TABLES):
        conn.execute(f"DELETE FROM {table}")
    # Every loaded record gets a revision above any a record has had, deleted
    # ones included (the delete triggers keep the highest, the replaced tree's
    # too), so a browser still showing an earlier tree gets a conflict on its
    # next edit instead of saving over the loaded tree.
    retired = int(meta.get(conn, meta.RETIRED_REVISION) or 0)
    loaded = [record["revision"] for table in _REVISED for record in tree[table]]
    revision = 1 + max([retired, *loaded])

    for table in TREE_TABLES:
        columns = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
        insert = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})"
        )
        for record in tree[table]:
            if table in _REVISED:
                record = {**record, "revision": revision}
            conn.execute(insert, [record[column] for column in columns])
    repository.delete_unused_images(conn)
    return saved
