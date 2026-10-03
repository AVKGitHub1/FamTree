"""Schema definition and forward-only migrations."""

from __future__ import annotations

from collections.abc import Callable

from famtree.storage.database import Connection

Migration = str | Callable[[Connection], None]


def _add_pictures(conn: Connection) -> None:
    """Version 2: the built-in Profile Pic attribute and the pictures it refers to."""
    # SQLite cannot alter a CHECK constraint. Widening one changes no stored
    # data, so it is edited in place, the procedure SQLite documents for this
    # case (https://sqlite.org/lang_altertable.html#otheralter); the bumped
    # schema_version makes every open connection reload the schema.
    old = "'number', 'url')"
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'attribute_definitions'"
    ).fetchone()
    if row["sql"].count(old) != 1:
        raise RuntimeError("attribute_definitions does not have the expected type constraint")
    schema_version = conn.execute("PRAGMA schema_version").fetchone()[0]
    conn.execute("PRAGMA writable_schema = ON")
    try:
        conn.execute(
            "UPDATE sqlite_master SET sql = ? "
            "WHERE type = 'table' AND name = 'attribute_definitions'",
            (row["sql"].replace(old, "'number', 'url', 'image')"),),
        )
        conn.execute(f"PRAGMA schema_version = {schema_version + 1}")
    finally:
        conn.execute("PRAGMA writable_schema = OFF")

    # Pictures are re-encoded JPEGs, referenced by attribute values as {"id": ...}.
    conn.execute(
        """
        CREATE TABLE images (
            id         TEXT PRIMARY KEY,
            full       BLOB NOT NULL,
            thumb      BLOB NOT NULL,
            width      INTEGER NOT NULL,
            height     INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO attribute_definitions (id, label, label_key, value_type, builtin, created_at) "
        "SELECT 'profile_pic', 'Profile Pic', 'profile pic', 'image', 1, '1970-01-01T00:00:00Z' "
        "WHERE NOT EXISTS (SELECT 1 FROM attribute_definitions WHERE label_key = 'profile pic')"
    )


# Each entry upgrades the schema by one version: SQL statements, or a function
# for steps SQL alone cannot express. Never edit a released entry; append a new
# one instead.
MIGRATIONS: tuple[Migration, ...] = (
    """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE people (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        id         TEXT NOT NULL UNIQUE,
        name       TEXT NOT NULL CHECK (length(trim(name)) > 0),
        revision   INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE attribute_definitions (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        id         TEXT NOT NULL UNIQUE,
        label      TEXT NOT NULL,
        label_key  TEXT NOT NULL UNIQUE,
        value_type TEXT NOT NULL
                   CHECK (value_type IN ('text', 'long_text', 'date', 'number', 'url')),
        builtin    INTEGER NOT NULL DEFAULT 0,
        revision   INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE attribute_values (
        person_id     TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        definition_id TEXT NOT NULL REFERENCES attribute_definitions(id) ON DELETE RESTRICT,
        value         TEXT NOT NULL,
        is_public     INTEGER NOT NULL DEFAULT 0 CHECK (is_public IN (0, 1)),
        PRIMARY KEY (person_id, definition_id)
    );
    CREATE INDEX attribute_values_definition ON attribute_values(definition_id);

    CREATE TABLE parent_links (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        id         TEXT NOT NULL UNIQUE,
        parent_id  TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        child_id   TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        role       TEXT NOT NULL CHECK (role IN ('mother', 'father')),
        is_public  INTEGER NOT NULL DEFAULT 0 CHECK (is_public IN (0, 1)),
        revision   INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (parent_id <> child_id),
        UNIQUE (parent_id, child_id)
    );
    CREATE INDEX parent_links_child ON parent_links(child_id);

    CREATE TABLE spouse_links (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        id         TEXT NOT NULL UNIQUE,
        person_a   TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        person_b   TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        is_public  INTEGER NOT NULL DEFAULT 0 CHECK (is_public IN (0, 1)),
        revision   INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (person_a < person_b),
        UNIQUE (person_a, person_b)
    );
    CREATE INDEX spouse_links_b ON spouse_links(person_b);

    CREATE TABLE access_codes (
        seq         INTEGER PRIMARY KEY AUTOINCREMENT,
        id          TEXT NOT NULL UNIQUE,
        label       TEXT NOT NULL DEFAULT '',
        role        TEXT NOT NULL CHECK (role IN ('public_viewer', 'private_viewer', 'editor')),
        code_value  TEXT NOT NULL,
        code_digest TEXT NOT NULL UNIQUE,
        created_at  TEXT NOT NULL,
        revoked_at  TEXT
    );

    CREATE TABLE sessions (
        token_digest TEXT PRIMARY KEY,
        principal    TEXT NOT NULL CHECK (principal IN ('admin', 'code')),
        code_id      TEXT REFERENCES access_codes(id) ON DELETE CASCADE,
        csrf_token   TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        expires_at   TEXT NOT NULL,
        CHECK ((principal = 'code') = (code_id IS NOT NULL))
    );
    CREATE INDEX sessions_code ON sessions(code_id);

    INSERT INTO attribute_definitions (id, label, label_key, value_type, builtin, created_at)
    VALUES
        ('birth_date',  'Birth date',  'birth date',  'date',      1, '1970-01-01T00:00:00Z'),
        ('location',    'Location',    'location',    'text',      1, '1970-01-01T00:00:00Z'),
        ('profession',  'Profession',  'profession',  'text',      1, '1970-01-01T00:00:00Z'),
        ('description', 'Description', 'description', 'long_text', 1, '1970-01-01T00:00:00Z');
    """,
    _add_pictures,
    # Version 3: snapshots of the tree (see famtree.domain.snapshots). A
    # migration that changes the tree tables must also upgrade the stored
    # snapshot data, or snapshots taken before it can no longer be loaded.
    """
    CREATE TABLE snapshots (
        seq            INTEGER PRIMARY KEY AUTOINCREMENT,
        id             TEXT NOT NULL UNIQUE,
        kind           TEXT NOT NULL CHECK (kind IN ('daily', 'before_load')),
        schema_version INTEGER NOT NULL,
        digest         TEXT NOT NULL,
        first_taken    TEXT NOT NULL,
        taken_at       TEXT NOT NULL,
        people         INTEGER NOT NULL,
        relationships  INTEGER NOT NULL,
        data           BLOB NOT NULL
    );
    CREATE INDEX snapshots_taken ON snapshots(kind, taken_at);

    CREATE TABLE snapshot_images (
        snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
        image_id    TEXT NOT NULL REFERENCES images(id),
        PRIMARY KEY (snapshot_id, image_id)
    );
    CREATE INDEX snapshot_images_image ON snapshot_images(image_id);
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)


def current_version(conn: Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if row is None:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return int(row["value"]) if row else 0


def migrate(conn: Connection) -> int:
    """Apply pending migrations inside the caller's transaction. Returns the new version."""
    version = current_version(conn)
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"database schema version {version} is newer than this release supports "
            f"({SCHEMA_VERSION}); upgrade FamTree instead of downgrading"
        )
    for step in MIGRATIONS[version:]:
        if callable(step):
            step(conn)
            continue
        for statement in _split_statements(step):
            conn.execute(statement)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(SCHEMA_VERSION),),
    )
    return SCHEMA_VERSION


def _split_statements(script: str) -> list[str]:
    # executescript() would commit the surrounding transaction, so statements
    # are run one at a time. The schema contains no semicolons inside literals.
    return [part.strip() for part in script.split(";") if part.strip()]
