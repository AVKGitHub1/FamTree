"""Encrypted storage: first launch, restarts, wrong keys, backup and restore."""

import hashlib
from dataclasses import replace

import pytest
from conftest import write_key

from famtree import cli
from famtree.domain import changes, repository
from famtree.security import sessions
from famtree.security.passwords import verify_password
from famtree.storage import backup, meta
from famtree.storage.backup import BackupError, create_backup, restore_backup, verify_backup
from famtree.storage.bootstrap import StorageUnavailable, load_settings_key, open_storage
from famtree.storage.database import open_connection
from famtree.storage.migrations import SCHEMA_VERSION


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_person(database, name):
    """Add a person, publicly married to the first person if the tree is not empty."""
    with database.write() as conn:
        existing = repository.load_graph(conn).ordered_people()
        links = []
        if existing:
            ref, first = changes.Ref(ref="p"), changes.Ref(id=existing[0].id)
            links = [changes.NewSpouseLink(ref, first, is_public=True)]
        changes.apply_changes(
            conn, changes.ChangeSet(people=[changes.NewPerson("p", name)], spouse_links=links)
        )


def test_first_launch_creates_encrypted_tree_with_one_password(settings):
    opened = open_storage(settings)
    password = opened.bootstrap_password
    assert password and len(password) >= 20
    add_person(opened.database, "Secret Name")
    with opened.database.read() as conn:
        assert verify_password(meta.get(conn, meta.ADMIN_PASSWORD_HASH), password)
    opened.database.close()

    raw = b"".join(p.read_bytes() for p in settings.data_dir.iterdir() if p.is_file())
    assert b"SQLite format 3" not in raw
    assert b"Secret Name" not in raw
    assert password.encode() not in raw

    reopened = open_storage(settings)
    assert reopened.bootstrap_password is None  # never re-initialized or reprinted
    with reopened.database.read() as conn:
        assert [p.name for p in repository.load_graph(conn).people.values()] == ["Secret Name"]
    reopened.database.close()


def test_wrong_key_refuses_and_leaves_data_untouched(settings, tmp_path):
    open_storage(settings).database.close()
    before = digest(settings.db_path)
    other_key = tmp_path / "other.key"
    write_key(other_key)
    with pytest.raises(StorageUnavailable) as info:
        open_storage(replace(settings, key_file=other_key))
    assert info.value.code == "decrypt_failed"
    assert digest(settings.db_path) == before


def test_missing_key_refuses(settings, tmp_path):
    with pytest.raises(StorageUnavailable) as info:
        open_storage(replace(settings, key_file=tmp_path / "absent.key"))
    assert info.value.code == "key_unavailable"
    assert not settings.db_path.exists()


def test_populated_directory_without_database_is_not_initialized(settings):
    (settings.data_dir / "backups").mkdir()
    with pytest.raises(StorageUnavailable) as info:
        open_storage(settings)
    assert info.value.code == "populated_without_database"
    assert not settings.db_path.exists()


def test_backup_restore_round_trip(settings, tmp_path):
    opened = open_storage(settings)
    add_person(opened.database, "Before Backup")
    summary = create_backup(settings, tmp_path / "backups")
    add_person(opened.database, "After Backup")
    opened.database.close()

    raw = summary.path.read_bytes()
    assert b"Before Backup" not in raw and b"SQLite format 3" not in raw
    assert verify_backup(summary.path, load_settings_key(settings)).people == 1

    _, replaced = restore_backup(settings, summary.path)
    assert replaced is not None and replaced.exists()
    reopened = open_storage(settings)
    with reopened.database.read() as conn:
        names = [p.name for p in repository.load_graph(conn).people.values()]
    reopened.database.close()
    assert names == ["Before Backup"]


def test_restore_signs_everyone_out(settings, tmp_path):
    opened = open_storage(settings)
    add_person(opened.database, "Someone")
    with opened.database.write() as conn:
        sessions.create_session(conn, "admin", None, 24)
    summary = create_backup(settings, tmp_path / "backups")
    opened.database.close()

    restore_backup(settings, summary.path)
    reopened = open_storage(settings)
    with reopened.database.read() as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert len(repository.load_graph(conn).people) == 1
    reopened.database.close()
    # The backup itself is left as it was.
    conn = open_connection(summary.path, load_settings_key(settings), wal=False)
    assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    conn.close()


def live_files(settings):
    return sorted(p.name for p in settings.data_dir.iterdir() if p.name.startswith("famtree.db"))


@pytest.mark.parametrize("failing_step", ["copy", "switch"])
def test_failed_restore_leaves_the_live_database_in_place(
    settings, tmp_path, monkeypatch, failing_step
):
    opened = open_storage(settings)
    add_person(opened.database, "Before Backup")
    summary = create_backup(settings, tmp_path / "backups")
    add_person(opened.database, "Live Only")
    opened.database.close()
    before = digest(settings.db_path)
    files = live_files(settings)

    def disk_full(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    if failing_step == "copy":
        monkeypatch.setattr(backup.shutil, "copyfile", disk_full)
    else:
        real_replace = backup.os.replace

        def replace_failing_at_switch(src, dst):
            if str(src).endswith(".restoring"):
                disk_full()
            real_replace(src, dst)

        monkeypatch.setattr(backup.os, "replace", replace_failing_at_switch)

    with pytest.raises(OSError):
        restore_backup(settings, summary.path)
    assert live_files(settings) == files  # no famtree.db.replaced-* or .restoring left
    assert digest(settings.db_path) == before
    reopened = open_storage(settings)
    with reopened.database.read() as conn:
        names = {p.name for p in repository.load_graph(conn).people.values()}
    reopened.database.close()
    assert names == {"Before Backup", "Live Only"}


def test_backup_from_a_newer_release_is_refused(settings, tmp_path):
    open_storage(settings).database.close()
    summary = create_backup(settings, tmp_path / "b")
    conn = open_connection(summary.path, load_settings_key(settings), wal=False)
    conn.execute(
        "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION + 1),)
    )
    conn.close()
    before = digest(settings.db_path)
    with pytest.raises(BackupError, match="newer than this release"):
        restore_backup(settings, summary.path)
    assert digest(settings.db_path) == before


def test_restore_refuses_while_server_holds_the_lock(settings, tmp_path):
    from famtree.storage.bootstrap import acquire_lock, release_lock

    opened = open_storage(settings)
    summary = create_backup(settings, tmp_path / "b")
    lock = acquire_lock(settings.data_dir)
    try:
        with pytest.raises(StorageUnavailable) as info:
            restore_backup(settings, summary.path)
        assert info.value.code == "locked"
    finally:
        release_lock(lock)
        opened.database.close()


def test_backup_needs_the_same_key(settings, tmp_path):
    open_storage(settings).database.close()
    summary = create_backup(settings, tmp_path / "b")
    other = tmp_path / "other.key"
    write_key(other)
    from famtree.storage.keyfile import load_key

    with pytest.raises(BackupError):
        verify_backup(summary.path, load_key(other))


def test_cli_reset_password_keeps_key_and_data(settings, monkeypatch, capsys):
    opened = open_storage(settings)
    old_password = opened.bootstrap_password
    add_person(opened.database, "Kept")
    opened.database.close()
    key_before = settings.key_file.read_text()

    monkeypatch.setenv("FAMTREE_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("FAMTREE_KEY_FILE", str(settings.key_file))
    assert cli.main(["reset-admin-password"]) == 0
    new_password = capsys.readouterr().out.split("New admin password: ")[1].split()[0]

    assert settings.key_file.read_text() == key_before
    reopened = open_storage(settings)
    with reopened.database.read() as conn:
        stored = meta.get(conn, meta.ADMIN_PASSWORD_HASH)
        assert len(repository.load_graph(conn).people) == 1
    reopened.database.close()
    assert verify_password(stored, new_password)
    assert not verify_password(stored, old_password)
