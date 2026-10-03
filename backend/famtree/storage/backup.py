"""Encrypted backups and offline restore.

Backups are standalone SQLCipher files encrypted with the same key as the live
database, so the key must be preserved separately to make them usable.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from famtree import clock
from famtree.config import Settings
from famtree.storage.bootstrap import (
    acquire_lock,
    check_data_dir,
    load_settings_key,
    release_lock,
)
from famtree.storage.database import DecryptionError, export_encrypted, open_connection
from famtree.storage.keyfile import DatabaseKey
from famtree.storage.migrations import SCHEMA_VERSION, current_version


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupSummary:
    path: Path
    schema_version: int
    people: int
    relationships: int


def _stamp() -> str:
    return clock.utcnow().strftime("%Y%m%dT%H%M%SZ")


def verify_backup(path: Path, key: DatabaseKey) -> BackupSummary:
    if not path.is_file():
        raise BackupError(f"{path} is not a file")
    try:
        conn = open_connection(path, key, wal=False)
    except DecryptionError as exc:
        raise BackupError(f"{path} cannot be decrypted with the configured key") from exc
    try:
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise BackupError(f"{path} failed the integrity check: {check}")
        version = current_version(conn)
        if version == 0:
            raise BackupError(f"{path} is not a FamTree database")
        if version > SCHEMA_VERSION:
            raise BackupError(
                f"{path} has schema version {version}, newer than this release supports "
                f"({SCHEMA_VERSION}); upgrade FamTree before restoring it"
            )
        people = conn.execute("SELECT count(*) FROM people").fetchone()[0]
        links = conn.execute(
            "SELECT (SELECT count(*) FROM parent_links) + (SELECT count(*) FROM spouse_links)"
        ).fetchone()[0]
    finally:
        conn.close()
    return BackupSummary(path=path, schema_version=version, people=people, relationships=links)


def create_backup(settings: Settings, output_dir: Path | None = None) -> BackupSummary:
    """Snapshot the live database. Safe while the server is running."""
    key = load_settings_key(settings)
    if not settings.db_path.exists():
        raise BackupError(f"no database at {settings.db_path}")
    output_dir = output_dir or settings.data_dir / "backups"
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = output_dir / f"famtree-{_stamp()}.db"
    partial = target.with_name(target.name + ".partial")
    partial.unlink(missing_ok=True)

    conn = open_connection(settings.db_path, key)
    try:
        export_encrypted(conn, partial, key)
    finally:
        conn.close()
    try:
        summary = verify_backup(partial, key)
        _fsync(partial)
        os.replace(partial, target)
        target.chmod(0o600)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return BackupSummary(target, summary.schema_version, summary.people, summary.relationships)


def restore_backup(settings: Settings, source: Path) -> tuple[BackupSummary, Path | None]:
    """Replace the live database with `source`. The server must be stopped; the
    previous database is kept beside it rather than deleted.

    The replacement is copied and synced next to the live database before
    anything live is touched, so a failed copy leaves the live files as they
    were. Sessions are removed from the restored copy: everyone signs in again.
    """
    check_data_dir(settings)
    key = load_settings_key(settings)
    summary = verify_backup(source, key)
    lock = acquire_lock(settings.data_dir)
    try:
        db_path = settings.db_path
        staging = db_path.with_name(db_path.name + ".restoring")
        try:
            shutil.copyfile(source, staging)
            staging.chmod(0o600)
            _end_sessions(staging, key)
            _fsync(staging)
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
        replaced = _swap_in(staging, db_path)
    finally:
        release_lock(lock)
    return summary, replaced


def _end_sessions(path: Path, key: DatabaseKey) -> None:
    """A backup carries the sessions that were open when it was taken; they must
    not come back to life with it."""
    conn = open_connection(path, key, wal=False)
    try:
        conn.execute("DELETE FROM sessions")
    finally:
        conn.close()


def _swap_in(staging: Path, db_path: Path) -> Path | None:
    """Move the live database and its sidecars aside, then the staged copy into
    place. If that fails, the live files get their own names back.

    The database goes first, so an interruption never leaves it without its
    WAL; leftover sidecars are moved too, so none can attach to the copy."""
    replaced = db_path.with_name(f"{db_path.name}.replaced-{_stamp()}")
    moved: list[tuple[Path, Path]] = []
    try:
        for suffix in ("", "-wal", "-shm"):
            live = db_path.with_name(db_path.name + suffix)
            if live.exists():
                aside = replaced.with_name(replaced.name + suffix)
                os.replace(live, aside)
                moved.append((aside, live))
        os.replace(staging, db_path)
    except BaseException:
        for aside, live in reversed(moved):
            os.replace(aside, live)
        staging.unlink(missing_ok=True)
        raise
    _fsync(db_path.parent)
    return replaced if moved else None


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
