"""Sign-in, sessions, codes, CSRF and rate limiting."""

from conftest import Api, make_code, new_client

from famtree.security.ratelimit import LoginThrottle


def test_guest_session(api):
    session = api.refresh()
    assert session["role"] == "guest"
    assert session["authenticated"] is False
    assert "calculate_relation" in session["actions"]
    assert "add_connection" not in session["actions"]


def test_bootstrap_password_printed_once_and_works(server, api):
    assert len(server["printed"]) == 1
    assert api.login("admin", server["password"]).json()["role"] == "admin"


def test_wrong_credentials_rejected_uniformly(api):
    for kind in ("admin", "code"):
        response = api.login(kind, "WRONG-WRONG-WRONG")
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "That code or password is not valid."


def test_session_cookie_is_http_only_and_strict(server, api):
    response = api.login("admin", server["password"])
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert server["password"].lower() not in cookie


def test_mutations_require_csrf_token(server, api):
    client = server["client"]
    no_header = client.post("/api/auth/login", json={"kind": "admin", "secret": "x"})
    assert no_header.status_code == 403
    wrong = client.post(
        "/api/auth/login",
        json={"kind": "admin", "secret": "x"},
        headers={"X-CSRF-Token": "forged"},
    )
    assert wrong.status_code == 403
    cross_site = client.post(
        "/api/auth/login",
        json={"kind": "admin", "secret": "x"},
        headers={"X-CSRF-Token": api.csrf, "Sec-Fetch-Site": "cross-site"},
    )
    assert cross_site.status_code == 403


def test_code_roles_revocation_and_role_changes_apply_on_next_request(server, admin):
    code_id, value = make_code(admin, "private_viewer", "Cousin Ann")
    holder = new_client(server)
    assert holder.login("code", value.lower().replace("-", " ")).json()["role"] == "private_viewer"

    assert admin.patch(f"/api/admin/codes/{code_id}", {"role": "editor"}).status_code == 200
    assert holder.refresh()["role"] == "editor"

    assert admin.patch(f"/api/admin/codes/{code_id}", {"revoked": True}).status_code == 200
    assert holder.refresh()["role"] == "guest"  # still sees public data as a guest
    assert holder.get("/api/tree").status_code == 200
    assert holder.login("code", value).status_code == 401


def test_deleting_a_code_ends_its_sessions(server, admin):
    code_id, value = make_code(admin, "editor")
    holder = new_client(server)
    holder.login("code", value)
    assert admin.delete(f"/api/admin/codes/{code_id}").status_code == 200
    assert holder.refresh()["role"] == "guest"


def test_admin_can_list_and_reveal_codes(admin):
    code_id, value = make_code(admin, "public_viewer", "Neighbours")
    listed = admin.get("/api/admin/codes").json()["codes"]
    assert [c["label"] for c in listed] == ["Neighbours"]
    assert "value" not in listed[0]
    assert admin.post(f"/api/admin/codes/{code_id}/reveal").json()["value"] == value


def test_codes_cannot_grant_admin(admin):
    response = admin.post("/api/admin/codes", {"label": "", "role": "admin"})
    assert response.status_code == 422


def test_only_admin_manages_access(server, admin):
    _, value = make_code(admin, "editor")
    editor = new_client(server)
    editor.login("code", value)
    assert editor.get("/api/admin/codes").status_code == 403
    assert editor.post("/api/admin/codes", {"label": "", "role": "editor"}).status_code == 403
    guest = new_client(server)
    assert guest.get("/api/admin/codes").status_code == 401


def test_admin_can_turn_guest_access_off(server, admin):
    _, value = make_code(admin, "public_viewer")
    guest = new_client(server)
    assert admin.get("/api/admin/settings").json() == {"guest_access": True}
    off = admin.patch("/api/admin/settings", {"guest_access": False})
    assert off.json() == {"guest_access": False}

    session = guest.refresh()
    assert session["role"] == "guest"
    assert session["capabilities"] == [] and session["actions"] == []
    reads = [
        guest.get("/api/tree"),
        guest.get("/api/people/search", params={"q": "a"}),
        guest.post("/api/relation", {"a": "x", "b": "y"}),
        guest.post("/api/export", {"format": "png"}),
    ]
    assert [r.status_code for r in reads] == [401] * 4
    assert reads[0].json()["error"]["code"] == "not_signed_in"

    # A public viewer code still opens the public tree; signing out loses it.
    holder = new_client(server)
    assert holder.login("code", value).status_code == 200
    assert holder.get("/api/tree").status_code == 200
    assert holder.logout().json()["capabilities"] == []
    assert holder.get("/api/tree").status_code == 401

    admin.patch("/api/admin/settings", {"guest_access": True})
    assert guest.refresh()["capabilities"] == ["read_public"]
    assert guest.get("/api/tree").status_code == 200


def test_only_admin_changes_settings(server, admin):
    _, value = make_code(admin, "editor")
    editor = new_client(server)
    editor.login("code", value)
    assert editor.get("/api/admin/settings").status_code == 403
    assert editor.patch("/api/admin/settings", {"guest_access": False}).status_code == 403
    guest = new_client(server)
    assert guest.patch("/api/admin/settings", {"guest_access": False}).status_code == 401
    assert admin.get("/api/admin/settings").json() == {"guest_access": True}


def test_password_change_signs_out_other_admin_sessions(server, admin):
    other = new_client(server)
    other.login("admin", server["password"])
    response = admin.post(
        "/api/admin/password",
        {"current_password": server["password"], "new_password": "correct horse battery"},
    )
    assert response.status_code == 200
    assert admin.refresh()["role"] == "admin"
    assert other.refresh()["role"] == "guest"
    fresh = new_client(server)
    assert fresh.login("admin", server["password"]).status_code == 401
    assert fresh.login("admin", "correct horse battery").status_code == 200


def test_weak_new_password_rejected(server, admin):
    response = admin.post(
        "/api/admin/password", {"current_password": server["password"], "new_password": "short"}
    )
    assert response.status_code == 422


def test_logout(server, admin):
    assert admin.logout().json()["role"] == "guest"
    assert admin.refresh()["role"] == "guest"


def test_sign_in_is_rate_limited(server):
    server["app"].state.famtree.throttle = LoginThrottle()
    client = Api(server["client"])
    statuses = [client.login("code", f"NOPE-{i}").status_code for i in range(12)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
