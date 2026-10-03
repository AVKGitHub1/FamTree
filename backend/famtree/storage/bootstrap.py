"""Opening the data directory: first-launch initialization or decrypting an
existing tree. A populated directory is never re-initialized."""

from __future__ import annotations

import contextlib
import fcntl
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from famtree import clock
from famtree.config import Settings
from famtree.security.passwords import hash_password
from famtree.security.tokens import generate_admin_password
from famtree.storage import meta
from famtree.storage.database import Database, DecryptionError, open_connection
from famtree.storage.keyfile import DatabaseKey, KeyFileError, load_key
from famtree.storage.migrations import migrate

log = logging.getLogger(__name__)

LOCK_NAME = "famtree.lock"
INIT_SUFFIX = ".init"


class StorageUnavailable(RuntimeError):
    """Storage cannot be used. `code` is a short machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class OpenedStorage:
    database: Database
    # Set only on the start that created the tree; printed once, never stored.
    bootstrap_password: str | None


def check_data_dir(settings: Settings) -> None:
    data_dir = settings.data_dir
    if not data_dir.is_dir():
        raise StorageUnavailable(
            "data_dir_missing",
            f"data directory {data_dir} does not exist; mount the host directory there",
        )
    if settings.require_data_mount and not os.path.ismount(data_dir):
        raise StorageUnavailable(
            "data_dir_not_mounted",
            f"{data_dir} is not a mounted volume, so data would be lost when the container "
            "is replaced. Mount the host data directory (see docker-compose.yml.example).",
        )
    if not os.access(data_dir, os.W_OK | os.X_OK):
        raise StorageUnavailable(
            "data_dir_not_writable",
            f"data directory {data_dir} is not writable by uid {os.getuid()}; "
            "set the compose file's user: to the host directory's owner",
        )
    with contextlib.suppress(OSError):
        if data_dir.stat().st_mode & 0o077:
            data_dir.chmod(0o700)


def acquire_lock(data_dir: Path) -> IO[bytes]:
    """Hold an exclusive lock on the data directory for the process lifetime."""
    try:
        handle = open(data_dir / LOCK_NAME, "ab")  # noqa: SIM115 - held until release_lock
    except OSError as exc:
        raise StorageUnavailable(
            "data_dir_not_writable", f"cannot create {data_dir / LOCK_NAME}: {exc.strerror}"
        ) from exc
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise StorageUnavailable(
            "locked", f"another FamTree process is already using {data_dir}"
        ) from None
    return handle


def release_lock(handle: IO[bytes] | None) -> None:
    if handle is not None:
        with contextlib.suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def load_settings_key(settings: Settings) -> DatabaseKey:
    try:
        return load_key(settings.key_file)
    except KeyFileError as exc:
        raise StorageUnavailable("key_unavailable", str(exc)) from exc


def _unexpected_entries(data_dir: Path, db_name: str) -> list[str]:
    return sorted(
        entry.name
        for entry in data_dir.iterdir()
        if entry.name != LOCK_NAME and not entry.name.startswith(db_name + INIT_SUFFIX)
    )


def open_storage(settings: Settings) -> OpenedStorage:
    """Open the tree, initializing it only when the data directory is empty."""
    check_data_dir(settings)
    key = load_settings_key(settings)
    db_path = settings.db_path

    password = None
    if not db_path.exists():
        leftovers = _unexpected_entries(settings.data_dir, db_path.name)
        if leftovers:
            raise StorageUnavailable(
                "populated_without_database",
                f"{settings.data_dir} has no {db_path.name} but is not empty "
                f"({', '.join(leftovers[:5])}). Refusing to create a new tree over existing "
                "data; restore a backup (docs/operations.md) or empty the directory.",
            )
        password = _initialize(db_path, key)
        log.info("Initialized a new, empty family tree in %s", settings.data_dir)

    try:
        database = Database(db_path, key)
    except DecryptionError as exc:
        raise StorageUnavailable(
            "decrypt_failed",
            f"{db_path} exists but cannot be decrypted with the key at {settings.key_file}. "
            "The data was NOT modified. Mount the original key (docs/operations.md).",
        ) from exc

    try:
        with database.write() as conn:
            migrate(conn)
            if meta.get(conn, meta.INITIALIZED_AT) is None:
                raise StorageUnavailable(
                    "not_initialized", f"{db_path} is missing its initialization record"
                )
    except BaseException:
        database.close()
        raise
    return OpenedStorage(database=database, bootstrap_password=password)


def _initialize(db_path: Path, key: DatabaseKey) -> str:
    """Create the database under a temporary name, then atomically rename it so
    a crash never leaves a half-initialized tree in place."""
    init_path = db_path.with_name(db_path.name + INIT_SUFFIX)
    for stale in (init_path, init_path.with_name(init_path.name + "-journal")):
        stale.unlink(missing_ok=True)

    password = generate_admin_password()
    conn = open_connection(init_path, key, wal=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        migrate(conn)
        now = clock.now_iso()
        meta.put(conn, meta.INITIALIZED_AT, now)
        meta.put(conn, meta.ADMIN_PASSWORD_HASH, hash_password(password))
        meta.put(conn, meta.ADMIN_PASSWORD_CHANGED_AT, now)
        conn.execute("COMMIT")
    finally:
        conn.close()

    _fsync_path(init_path)
    os.replace(init_path, db_path)
    _fsync_path(db_path.parent)
    return password


def _fsync_path(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
