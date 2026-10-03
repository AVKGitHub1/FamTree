"""Access and visibility changes that land while other work is in flight: the
cached graph/layout, exports that outlive a revocation, and HTTPS-only sessions."""

import threading
from dataclasses import replace

import pytest
from conftest import Api, make_code, new_client
from fastapi.testclient import TestClient

from famtree import app as app_module
from famtree.api.routes import export as export_routes
from famtree.api.state import GraphViews
from famtree.app import create_app
from famtree.domain import changes, repository
from famtree.domain.model import ParentRole
from famtree.domain.visibility import Audience
from famtree.export.render import Rendered
from famtree.security import access_codes, sessions
from famtree.storage.bootstrap import open_storage

SECRET = "Secret profession"


# --- cached graph and layout ---------------------------------------------------


class InterleavingLock:
    """A lock that lets another request run, once, the first time the code under
    test lets go of it: the worst moment for a write to land."""

    def __init__(self, interleave) -> None:
        self._lock = threading.Lock()
        self._interleave = interleave
        self.armed = False

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(self, *_) -> None:
        self._lock.release()
        if self.armed:
            self.armed = False
            other = threading.Thread(target=self._interleave)
            other.start()
            other.join()


def link_ids(layout) -> set[str]:
    return {link for connector in layout.connectors for link in connector.links}


def test_layout_is_never_cached_against_a_newer_graph(settings):
    database = open_storage(settings).database
    try:
        with database.write() as conn:
            changes.apply_changes(
                conn,
                changes.ChangeSet(
                    people=[changes.NewPerson(r, r.upper()) for r in ("a", "b", "c")],
                    parent_links=[
                        changes.NewParentLink(
                            changes.Ref(ref=p), changes.Ref(ref="c"), role, is_public=True
                        )
                        for p, role in (("a", ParentRole.FATHER), ("b", ParentRole.MOTHER))
                    ],
                    spouse_links=[
                        changes.NewSpouseLink(changes.Ref(ref="a"), changes.Ref(ref="b"), True)
                    ],
                ),
            )
            link = repository.load_graph(conn).parent_links[0]
        views = GraphViews(database)

        def make_link_private_then_read() -> None:
            with database.write() as conn:
                changes.update_parent_link(conn, link.id, link.revision, None, False)
            views.graph(Audience.PUBLIC)  # another request refreshes the cache

        lock = InterleavingLock(make_link_private_then_read)
        views._lock = lock
        lock.armed = True
        graph, layout = views.layout(Audience.PUBLIC)
        assert not lock.armed  # the other request did run
        # Whatever was returned is one consistent snapshot...
        graph_links = {k.id for k in graph.parent_links} | {k.id for k in graph.spouse_links}
        assert link_ids(layout) <= graph_links
        # ...and what is cached from now on no longer shows the private link.
        graph, layout = views.layout(Audience.PUBLIC)
        assert link.id not in {k.id for k in graph.parent_links}
        assert link.id not in link_ids(layout)
    finally:
        database.close()


# --- exports -------------------------------------------------------------------


@pytest.fixture
def family(admin):
    """Founder (with a private profession) -> Child, publicly."""
    response = admin.post(
        "/api/changes",
        {
            "people": [
                {
                    "ref": "f",
                    "name": "Founder",
                    "attributes": [{"definition": {"id": "profession"}, "value": SECRET}],
                },
                {"ref": "c", "name": "Child"},
            ],
            "parent_links": [
                {"parent": {"ref": "f"}, "child": {"ref": "c"}, "role": "father", "is_public": True}
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["created"]


EXPORT = {"format": "png", "png_width": 800, "attributes": ["profession"]}


def scene_text(scene) -> str:
    return " ".join([c.name for c in scene.cards] + [line for c in scene.cards for line in c.lines])


@pytest.fixture
def renders(monkeypatch):
    """Replace rendering (it needs Pango) with a stand-in that records each
    scene and runs `during` while "rendering"."""
    calls = {"scenes": [], "during": lambda: None}

    def fake_render(scene, options):
        calls["scenes"].append(scene)
        calls["during"]()
        return Rendered(b"PNG:" + scene_text(scene).encode(), "image/png", 800, 600, "px", 1.0)

    def fake_preview(scene, options):
        rendered = fake_render(scene, options)
        return rendered.data, rendered

    monkeypatch.setattr(export_routes, "render", fake_render)
    monkeypatch.setattr(export_routes, "render_preview", fake_preview)
    monkeypatch.setattr(export_routes, "shortened_cards", lambda scene: 0)
    return calls


def private_viewer(server, admin) -> tuple[Api, str]:
    code_id, value = make_code(admin, "private_viewer")
    holder = new_client(server)
    assert holder.login("code", value).status_code == 200
    return holder, code_id


def revoke(server, code_id) -> None:
    with server["app"].state.famtree.database.write() as conn:
        access_codes.update_code(conn, code_id, revoked=True)


@pytest.mark.parametrize("path", ["/api/export", "/api/export/preview"])
def test_export_is_discarded_if_access_is_revoked_while_rendering(
    server, admin, family, renders, path
):
    holder, code_id = private_viewer(server, admin)
    renders["during"] = lambda: revoke(server, code_id)
    response = holder.post(path, EXPORT)
    assert SECRET in scene_text(renders["scenes"][0])  # it was being made privately...
    assert response.status_code == 409  # ...but is not delivered
    assert response.json()["error"]["code"] == "export_stale"
    assert SECRET.encode() not in response.content
    assert holder.refresh()["role"] == "guest"


def test_export_waits_for_a_slot_then_uses_the_access_held_at_that_time(
    server, admin, family, renders
):
    holder, code_id = private_viewer(server, admin)
    state = server["app"].state.famtree
    slots = state.export_slots

    class RevokedWhileQueued:
        def acquire(self, timeout):
            revoke(server, code_id)
            return slots.acquire(timeout=timeout)

        def release(self):
            slots.release()

    state.export_slots = RevokedWhileQueued()
    try:
        response = holder.post("/api/export", EXPORT)
    finally:
        state.export_slots = slots
    assert response.status_code == 200
    assert SECRET not in scene_text(renders["scenes"][0])
    assert SECRET.encode() not in response.content


def test_export_is_discarded_if_the_callers_view_changes_while_rendering(
    server, admin, family, renders
):
    guest = Api(TestClient(server["app"]))
    db = server["app"].state.famtree.database

    def rename():
        with db.write() as conn:
            person = repository.load_graph(conn).people[family["c"]]
            repository.touch_person(conn, person.id, "Renamed")

    renders["during"] = rename
    response = guest.post("/api/export", EXPORT)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "export_stale"

    def sign_in_elsewhere():
        with db.write() as conn:
            sessions.create_session(conn, "admin", None, 1)

    # A write that does not change what the caller sees does not matter.
    renders["during"] = sign_in_elsewhere
    assert guest.post("/api/export", EXPORT).status_code == 200


# --- FAMTREE_COOKIE_SECURE=true --------------------------------------------------


@pytest.fixture
def https_only(settings, monkeypatch):
    printed: list[str] = []
    monkeypatch.setattr(app_module, "print_bootstrap_password", printed.append)
    application = create_app(replace(settings, cookie_secure="true"))
    with TestClient(application, base_url="https://testserver") as secure:
        yield application, secure, printed[0]


def test_secure_mode_refuses_sign_in_over_plain_http(https_only):
    application, _, password = https_only
    plain = Api(TestClient(application))  # http://testserver
    response = plain.login("admin", password)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "https_required"
    assert "famtree_session" not in response.cookies


def test_secure_mode_ignores_session_cookies_over_plain_http(https_only):
    application, secure, password = https_only
    signed_in = Api(secure)
    response = signed_in.login("admin", password)
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    token = response.cookies["famtree_session"]
    assert signed_in.refresh()["role"] == "admin"

    plain = TestClient(application)
    session = plain.get("/api/session", headers={"Cookie": f"famtree_session={token}"})
    assert session.json()["role"] == "guest"
    admin_only = plain.get("/api/admin/codes", headers={"Cookie": f"famtree_session={token}"})
    assert admin_only.status_code == 401


def test_secure_mode_still_serves_guests_over_plain_http(https_only):
    application, _, _ = https_only
    plain = TestClient(application)
    session = plain.get("/api/session")
    assert "secure" not in session.headers["set-cookie"].lower()  # guest CSRF cookie
    guest = Api(plain)
    assert guest.get("/api/tree").status_code == 200
    # A guest's POST (relation, export) passes CSRF over plain HTTP.
    assert guest.post("/api/relation", {"a": "x", "b": "y"}).status_code == 404
