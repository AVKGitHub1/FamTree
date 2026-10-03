"""Snapshots: one a day while the tree changes, loading one (after saving the
tree it replaces), deleting, only the latest kept, the pictures they keep, and
who may use them."""

from datetime import UTC, datetime, time, timedelta

import pytest
from conftest import make_code, new_client
from test_pictures import add_person, upload

from famtree import clock
from famtree.daily import DailySnapshots
from famtree.domain import repository, snapshots
from famtree.storage import migrations
from famtree.storage.bootstrap import open_storage


@pytest.fixture
def db(server):
    return server["app"].state.famtree.database


class Today:
    """Moves the clock to 09:00 UTC on a day counted from the real today."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._start = datetime.combine(clock.utcnow().date(), time(9), UTC)

    def set(self, days: int, hours: float = 0) -> str:
        moment = self._start + timedelta(days=days, hours=hours)
        self._monkeypatch.setattr(clock, "utcnow", lambda: moment)
        return clock.to_iso(moment)[:10]


@pytest.fixture
def today(monkeypatch):
    return Today(monkeypatch)


def grow(admin) -> dict[str, str]:
    """Founder -> Child, publicly."""
    response = admin.post(
        "/api/changes",
        {
            "people": [{"ref": "f", "name": "Founder"}, {"ref": "c", "name": "Child"}],
            "parent_links": [
                {"parent": {"ref": "f"}, "child": {"ref": "c"}, "role": "father", "is_public": True}
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["created"]


def person(client, person_id: str) -> dict:
    return next(p for p in client.tree()["people"] if p["id"] == person_id)


def edit(client, person_id: str, name: str, attributes=()):
    return client.put(
        f"/api/people/{person_id}",
        {
            "expected_revision": person(client, person_id)["revision"],
            "name": name,
            "attributes": list(attributes),
        },
    )


def names(client) -> set[str]:
    return {p["name"] for p in client.tree()["people"]}


def listed(admin) -> list[dict]:
    response = admin.get("/api/admin/snapshots")
    assert response.status_code == 200, response.text
    return response.json()["snapshots"]


def test_one_snapshot_a_day_kept_once_while_the_tree_is_unchanged(admin, db, today):
    job = DailySnapshots(db)
    first = today.set(0)
    assert job.run_once() is None  # an empty tree: nothing to go back to
    ids = grow(admin)
    assert job.run_once() == "created"
    assert job.run_once() is None  # today's is taken

    second = today.set(1)
    assert edit(admin, ids["c"], "Kid").status_code == 200
    assert edit(admin, ids["c"], "Child").status_code == 200  # and back: the same tree
    assert job.run_once() == "renewed"
    [kept] = listed(admin)
    assert (kept["first_taken"][:10], kept["taken_at"][:10]) == (first, second)
    assert kept == kept | {"kind": "daily", "people": 2, "relationships": 1, "loadable": True}

    third = today.set(2)
    assert edit(admin, ids["c"], "Kid").status_code == 200
    assert job.run_once() == "created"
    assert [s["taken_at"][:10] for s in listed(admin)] == [third, second]  # newest first


def test_loading_saves_the_current_tree_first_and_leaves_access_alone(server, admin, db):
    ids = grow(admin)
    _, code = make_code(admin, "editor")
    editor = new_client(server)
    assert editor.login("code", code).status_code == 200
    DailySnapshots(db).run_once()
    [old] = listed(admin)
    assert edit(admin, ids["c"], "Renamed").status_code == 200
    seen_by_editor = person(editor, ids["c"])

    loaded = admin.post(f"/api/admin/snapshots/{old['id']}/load")
    assert loaded.status_code == 200, loaded.text
    assert names(admin) == {"Founder", "Child"}
    saved = next(s for s in listed(admin) if s["id"] == loaded.json()["saved"])
    assert saved["kind"] == "before_load" and saved["people"] == 2

    # Sign-ins and codes are untouched, but an edit made from the replaced
    # tree is refused rather than saved over the loaded one.
    assert editor.refresh()["role"] == "editor"
    stale = editor.put(
        f"/api/people/{ids['c']}",
        {"expected_revision": seen_by_editor["revision"], "name": "Overwritten", "attributes": []},
    )
    assert stale.status_code == 409
    assert edit(editor, ids["c"], "Edited after loading").status_code == 200

    # The saved snapshot takes the tree back to how it was before loading.
    assert admin.post(f"/api/admin/snapshots/{saved['id']}/load").status_code == 200
    assert names(admin) == {"Founder", "Renamed"}
    assert [s["kind"] for s in listed(admin)].count("before_load") == 2


def test_bringing_back_a_deleted_person_refuses_edits_from_before(admin, db):
    created = admin.post(
        "/api/changes",
        {
            "people": [{"ref": "p", "name": "Partner"}, {"ref": "q", "name": "Other"}],
            "spouse_links": [{"a": {"ref": "p"}, "b": {"ref": "q"}, "is_public": True}],
        },
    )
    assert created.status_code == 201, created.text
    p = created.json()["created"]["p"]
    DailySnapshots(db).run_once()
    [old] = listed(admin)

    # Edit forms left open on Partner and their marriage, which (by cascade)
    # end up deleted with a revision above anything left in the tree.
    assert edit(admin, p, "Partner").status_code == 200
    form = person(admin, p)
    for _ in range(2):
        [link] = admin.tree()["spouse_links"]
        changed = admin.patch(
            f"/api/relationships/spouse/{link['id']}",
            {"expected_revision": link["revision"], "is_public": True},
        )
        assert changed.status_code == 200, changed.text
    [link] = admin.tree()["spouse_links"]
    preview = admin.get(f"/api/people/{p}/deletion").json()
    deleted = admin.delete(
        f"/api/people/{p}",
        params={
            "expected_revision": form["revision"],
            "expected_relationships": preview["relationships"],
        },
    )
    assert deleted.status_code == 200, deleted.text

    assert admin.post(f"/api/admin/snapshots/{old['id']}/load").status_code == 200
    assert names(admin) == {"Partner", "Other"}
    stale_person = admin.put(
        f"/api/people/{p}",
        {"expected_revision": form["revision"], "name": "Overwritten", "attributes": []},
    )
    assert stale_person.status_code == 409
    stale_link = admin.patch(
        f"/api/relationships/spouse/{link['id']}",
        {"expected_revision": link["revision"], "is_public": True},
    )
    assert stale_link.status_code == 409
    assert names(admin) == {"Partner", "Other"}


def test_upgrading_keeps_snapshots_loadable_and_remembers_deleted_revisions(settings, monkeypatch):
    with monkeypatch.context() as old_release:
        old_release.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS[:3])
        old_release.setattr(migrations, "SCHEMA_VERSION", 3)
        old_release.setattr(snapshots, "SCHEMA_VERSION", 3)
        database = open_storage(settings).database
        with database.write() as conn:
            person_id = repository.insert_person(conn, "Before Upgrade")
            snapshot_id = snapshots.take(conn, snapshots.SnapshotKind.DAILY)
        database.close()

    database = open_storage(settings).database
    try:
        with database.write() as conn:
            assert migrations.current_version(conn) == migrations.SCHEMA_VERSION
            assert [s.loadable for s in snapshots.list_snapshots(conn)] == [True]
            repository.touch_person(conn, person_id)
            repository.touch_person(conn, person_id)
            repository.delete_person(conn, person_id)
            snapshots.load(conn, snapshot_id)
            assert repository.person_revision(conn, person_id) == 4  # above the deleted 3
    finally:
        database.close()


def test_snapshots_keep_their_pictures(admin, db, today):
    today.set(0)
    picture = upload(admin).json()["id"]
    assert add_person(admin, "Pictured", picture).status_code == 201
    pictured = next(p["id"] for p in admin.tree()["people"])
    DailySnapshots(db).run_once()
    [daily] = listed(admin)
    assert edit(admin, pictured, "Pictured").status_code == 200  # picture removed

    today.set(0, hours=repository.UNSAVED_PICTURE_HOURS + 1)  # past an upload's grace period
    with db.write() as conn:
        repository.delete_unused_images(conn)
        assert repository.image_exists(conn, picture)  # the snapshot still uses it

    saved = admin.post(f"/api/admin/snapshots/{daily['id']}/load").json()["saved"]
    assert admin.get(f"/api/people/{pictured}/picture").status_code == 200
    assert admin.post(f"/api/admin/snapshots/{saved}/load").status_code == 200  # without it again
    assert admin.get(f"/api/people/{pictured}/picture").status_code == 404

    for snapshot in listed(admin):
        assert admin.delete(f"/api/admin/snapshots/{snapshot['id']}").status_code == 200
    with db.read() as conn:
        assert not repository.image_exists(conn, picture)


def picture_person(admin) -> tuple[str, str]:
    """The first person in the tree, with a profile picture: (person, picture)."""
    picture = upload(admin).json()["id"]
    assert add_person(admin, "Pictured", picture).status_code == 201
    return admin.tree()["people"][0]["id"], picture


def test_only_the_latest_snapshots_are_kept(admin, db, today, monkeypatch):
    monkeypatch.setattr(snapshots, "KEEP", 3)
    job = DailySnapshots(db)
    days = [today.set(0)]
    pictured, picture = picture_person(admin)
    assert job.run_once() == "created"
    assert edit(admin, pictured, "Day 0").status_code == 200  # without the picture
    for day in range(1, 4):
        days.append(today.set(day))
        assert edit(admin, pictured, f"Day {day}").status_code == 200
        assert job.run_once() == "created"

    response = admin.get("/api/admin/snapshots").json()
    assert response["keep"] == 3
    assert [s["taken_at"][:10] for s in response["snapshots"]] == days[:0:-1]  # day 0 dropped
    with db.read() as conn:
        assert not repository.image_exists(conn, picture)  # only that snapshot used it


def test_loading_the_oldest_snapshot_keeps_its_pictures(admin, db, today, monkeypatch):
    monkeypatch.setattr(snapshots, "KEEP", 2)
    job = DailySnapshots(db)
    today.set(0)
    pictured, _ = picture_person(admin)
    job.run_once()
    today.set(1)  # long past the picture's grace period as an unsaved upload
    assert edit(admin, pictured, "Without a picture").status_code == 200
    job.run_once()
    oldest = listed(admin)[-1]

    loaded = admin.post(f"/api/admin/snapshots/{oldest['id']}/load")
    assert loaded.status_code == 200
    # Saving the replaced tree pushed the loaded snapshot out; its tree is the
    # current one now, pictures included.
    assert [s["kind"] for s in listed(admin)] == ["before_load", "daily"]
    assert oldest["id"] not in {s["id"] for s in listed(admin)}
    assert names(admin) == {"Pictured"}
    assert admin.get(f"/api/people/{pictured}/picture").status_code == 200


def test_only_the_admin_sees_and_uses_snapshots(server, admin, db):
    grow(admin)
    DailySnapshots(db).run_once()
    [snapshot] = listed(admin)
    path = f"/api/admin/snapshots/{snapshot['id']}"
    _, code = make_code(admin, "editor")
    editor = new_client(server)
    editor.login("code", code)
    assert editor.get("/api/admin/snapshots").status_code == 403
    assert editor.post(f"{path}/load").status_code == 403
    assert editor.delete(path).status_code == 403

    assert admin.delete(path).status_code == 200
    assert listed(admin) == []
    assert admin.delete(path).status_code == 404
    assert admin.post(f"{path}/load").status_code == 404


def test_a_snapshot_of_another_schema_version_is_listed_but_not_loaded(admin, db, today):
    today.set(0)
    grow(admin)
    job = DailySnapshots(db)
    job.run_once()
    with db.write() as conn:
        conn.execute("UPDATE snapshots SET schema_version = schema_version - 1")
    [snapshot] = listed(admin)
    assert snapshot["loadable"] is False
    response = admin.post(f"/api/admin/snapshots/{snapshot['id']}/load")
    assert response.status_code == 422
    assert names(admin) == {"Founder", "Child"}
    today.set(1)
    assert job.run_once() == "created"  # not a renewal of the old one


def test_the_server_runs_the_daily_job(server, admin, db):
    assert server["app"].state.famtree.daily_snapshots is not None
    grow(admin)
    job = DailySnapshots(db, interval=0.01)
    job.start()  # takes today's at once
    job.stop()
    assert len(listed(admin)) == 1
