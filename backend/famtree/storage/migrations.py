"""Schema definition and forward-only migrations."""

from __future__ import annotations

from famtree.storage.database import Connection

# Each entry upgrades the schema by one version. Never edit a released entry;
# append a new one instead.
MIGRATIONS: tuple[str, ...] = (
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
    for script in MIGRATIONS[version:]:
        for statement in _split_statements(script):
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
