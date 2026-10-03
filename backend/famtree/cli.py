"""Operator commands (`famtree-admin ...`). They need host/container access and
the mounted key; none of them prints family data."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from famtree import clock
from famtree.config import ConfigError, Settings
from famtree.security.passwords import hash_password
from famtree.security.sessions import delete_admin_sessions
from famtree.security.tokens import generate_admin_password
from famtree.storage import meta
from famtree.storage.backup import BackupError, create_backup, restore_backup, verify_backup
from famtree.storage.bootstrap import StorageUnavailable, load_settings_key
from famtree.storage.database import DecryptionError, open_connection
from famtree.storage.keyfile import DatabaseKey
from famtree.storage.migrations import current_version


def _open_live(settings: Settings):
    if not settings.db_path.exists():
        raise BackupError(f"no database at {settings.db_path}")
    try:
        return open_connection(settings.db_path, load_settings_key(settings))
    except DecryptionError as exc:
        raise BackupError(f"{exc}. Is the right key mounted?") from exc


def _describe(summary) -> str:
    return (
        f"{summary.people} people, {summary.relationships} relationships, "
        f"schema v{summary.schema_version}"
    )


def cmd_status(settings: Settings, _: argparse.Namespace) -> int:
    conn = _open_live(settings)
    try:
        people = conn.execute("SELECT count(*) FROM people").fetchone()[0]
        initialized = meta.get(conn, meta.INITIALIZED_AT)
        version = current_version(conn)
    finally:
        conn.close()
    print(f"Database:        {settings.db_path} (decrypts with the mounted key)")
    print(f"Schema version:  {version}")
    print(f"Initialized at:  {initialized}")
    print(f"People:          {people}")
    return 0


def cmd_reset_admin_password(settings: Settings, _: argparse.Namespace) -> int:
    """Replaces only the admin password hash; the encryption key is untouched."""
    password = generate_admin_password()
    conn = _open_live(settings)
    try:
        conn.execute("BEGIN IMMEDIATE")
        meta.put(conn, meta.ADMIN_PASSWORD_HASH, hash_password(password))
        meta.put(conn, meta.ADMIN_PASSWORD_CHANGED_AT, clock.now_iso())
        signed_out = delete_admin_sessions(conn)
        conn.execute("COMMIT")
    finally:
        conn.close()
    print(f"New admin password: {password}")
    print(f"Signed out {signed_out} admin session(s). The encryption key was not changed.")
    return 0


def cmd_backup(settings: Settings, args: argparse.Namespace) -> int:
    summary = create_backup(settings, Path(args.output_dir) if args.output_dir else None)
    print(f"Backup written: {summary.path}")
    print(f"  {_describe(summary)}")
    print("It is encrypted with the current key; keep a copy of the key separately.")
    return 0


def cmd_verify(settings: Settings, args: argparse.Namespace) -> int:
    summary = verify_backup(Path(args.path), load_settings_key(settings))
    print(f"OK: {summary.path} decrypts and passes the integrity check")
    print(f"  {_describe(summary)}")
    return 0


def cmd_restore(settings: Settings, args: argparse.Namespace) -> int:
    if not args.yes:
        print("Restoring replaces the live tree (it is kept aside, not deleted).")
        print("Stop the FamTree service first, then re-run with --yes.")
        return 1
    summary, replaced = restore_backup(settings, Path(args.path))
    print(f"Restored {summary.people} people from {summary.path}")
    if replaced:
        print(f"The previous database was kept as {replaced}")
    print("Start the service again to use the restored tree.")
    return 0


def cmd_generate_key(_: Settings, __: argparse.Namespace) -> int:
    sys.stdout.write(DatabaseKey.generate().to_file_text())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="famtree-admin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="check that the database opens with the mounted key")
    sub.add_parser("reset-admin-password", help="print a new admin password")
    backup = sub.add_parser("backup", help="write an encrypted backup (safe while running)")
    backup.add_argument("--output-dir", help="default: <data dir>/backups")
    verify = sub.add_parser("verify", help="check that a backup decrypts and is intact")
    verify.add_argument("path")
    restore = sub.add_parser("restore", help="replace the tree with a backup (service stopped)")
    restore.add_argument("path")
    restore.add_argument("--yes", action="store_true", help="confirm the replacement")
    sub.add_parser("generate-key", help="print a new random encryption key")
    return parser


COMMANDS = {
    "status": cmd_status,
    "reset-admin-password": cmd_reset_admin_password,
    "backup": cmd_backup,
    "verify": cmd_verify,
    "restore": cmd_restore,
    "generate-key": cmd_generate_key,
}


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        return COMMANDS[args.command](settings, args)
    except (ConfigError, StorageUnavailable, BackupError) as exc:
        print(f"famtree-admin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
