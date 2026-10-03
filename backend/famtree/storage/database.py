"""SQLCipher connections and transactions.

Every page of the database, its write-ahead log and any backups made with
`export_encrypted` are encrypted with the mounted key. Temporary tables are
kept in memory so no plaintext scratch files reach the disk.
"""

from __future__ import annotations

import contextlib
import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlcipher3 import dbapi2 as sqlite

from famtree.storage.keyfile import DatabaseKey

Connection = sqlite.Connection
Row = sqlite.Row
IntegrityError = sqlite.IntegrityError
DatabaseError = sqlite.DatabaseError


class DecryptionError(RuntimeError):
    """The database file exists but cannot be opened with the configured key."""


def open_connection(path: Path, key: DatabaseKey, *, wal: bool = True) -> Connection:
    """Open and unlock one connection, verifying the key by reading the schema."""
    conn = sqlite.connect(str(path), isolation_level=None, check_same_thread=False, timeout=15)
    try:
        conn.execute("PRAGMA cipher_log_level = NONE")
        conn.execute(f'PRAGMA key = "{key.pragma_value}"')
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except DatabaseError as exc:
            raise DecryptionError(f"{path} cannot be decrypted with the configured key") from exc
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 15000")
        if wal:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.row_factory = Row
        return conn
    except BaseException:
        conn.close()
        raise


class Database:
    """A small connection pool with serialized writers.

    Readers run in deferred transactions (a consistent WAL snapshot); writers
    are serialized in-process and use BEGIN IMMEDIATE so validation and the
    mutation it guards happen atomically.
    """

    def __init__(self, path: Path, key: DatabaseKey, pool_size: int = 4) -> None:
        self.path = path
        self._key = key
        self._pool: queue.LifoQueue[Connection] = queue.LifoQueue()
        self._all: list[Connection] = []
        self._pool_size = pool_size
        self._pool_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._closed = False
        # Bumped after every committed write; caches key derived data on it.
        self.version = 0
        # Verify eagerly so a bad key fails at startup rather than on first use.
        self._release(self._new_connection())

    @property
    def key(self) -> DatabaseKey:
        return self._key

    def _new_connection(self) -> Connection:
        conn = open_connection(self.path, self._key)
        with self._pool_lock:
            self._all.append(conn)
        return conn

    def _acquire(self) -> Connection:
        if self._closed:
            raise RuntimeError("database is closed")
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            pass
        with self._pool_lock:
            can_grow = len(self._all) < self._pool_size
        if can_grow:
            return self._new_connection()
        return self._pool.get(timeout=30)

    def _release(self, conn: Connection) -> None:
        if self._closed:
            conn.close()
        else:
            self._pool.put(conn)

    @contextmanager
    def read(self) -> Iterator[Connection]:
        conn = self._acquire()
        try:
            conn.execute("BEGIN")
            try:
                yield conn
            finally:
                conn.execute("ROLLBACK")
        finally:
            self._release(conn)

    @contextmanager
    def write(self) -> Iterator[Connection]:
        with self._write_lock:
            conn = self._acquire()
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    yield conn
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                conn.execute("COMMIT")
                self.version += 1
            finally:
                self._release(conn)

    def close(self) -> None:
        with self._pool_lock:
            if self._closed:
                return
            self._closed = True
            conns, self._all = self._all, []
        for conn in conns:
            with contextlib.suppress(DatabaseError):
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()


def export_encrypted(conn: Connection, target: Path, key: DatabaseKey) -> None:
    """Write a complete, standalone copy of the database encrypted with `key`."""
    escaped = str(target).replace("'", "''")
    conn.execute(f"ATTACH DATABASE '{escaped}' AS export_target KEY \"{key.pragma_value}\"")
    try:
        conn.execute("SELECT sqlcipher_export('export_target')").fetchone()
    finally:
        conn.execute("DETACH DATABASE export_target")
