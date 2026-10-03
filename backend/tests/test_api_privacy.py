"""Guests and public viewers never receive private data through any read path."""

import pytest
from conftest import make_code, new_client

SECRETS = ("Secret profession", "Hidden town", "Medical", "Allergic to cats")


@pytest.fixture
def family(admin):
    """Founder -> Child (public); Founder -> Hidden (private); Child = Hidden (public)."""
    response = admin.post(
        "/api/changes",
        {
            "definitions": [{"ref": "med", "label": "Medical", "value_type": "text"}],
            "people": [
                {
                    "ref": "f",
                    "name": "Founder",
                    "attributes": [
                        {
                            "definition": {"id": "birth_date"},
                            "value": {"year": 1950},
                            "is_public": True,
                        },
                        {"definition": {"id": "profession"}, "value": "Secret profession"},
                    ],
                },
                {
                    "ref": "c",
                    "name": "Child",
                    "attributes": [
                        {"definition": {"id": "location"}, "value": "Hidden town"},
                        {"definition": {"ref": "med"}, "value": "Allergic to cats"},
                    ],
                },
                {"ref": "h", "name": "Hidden"},
            ],
            "parent_links": [
                {
                    "parent": {"ref": "f"},
                    "child": {"ref": "c"},
                    "role": "father",
                    "is_public": True,
                },
                {
                    "parent": {"ref": "f"},
                    "child": {"ref": "h"},
                    "role": "father",
                    "is_public": False,
                },
            ],
            "spouse_links": [{"a": {"ref": "c"}, "b": {"ref": "h"}, "is_public": True}],
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()["created"]
    private_link = next(
        link["id"] for link in admin.tree()["parent_links"] if link["child_id"] == created["h"]
    )
    return created | {"private_link": private_link}


def assert_public_only(client, family):
    tree_text = client.get("/api/tree").text
    for secret in SECRETS:
        assert secret not in tree_text
    assert family["private_link"] not in tree_text
    tree = client.get("/api/tree").json()
    assert {d["id"] for d in tree["definitions"]} == {"birth_date"}
    assert all("is_public" not in a for p in tree["people"] for a in p["attributes"])
    assert all("revision" not in p for p in tree["people"])
    # Names are public: everyone is identifiable.
    assert {p["name"] for p in tree["people"]} == {"Founder", "Child", "Hidden"}
    # The private parent link leaves no connector, dangling or otherwise.
    for connector in tree["layout"]["connectors"]:
        assert family["private_link"] not in connector["links"]
        assert not (family["f"] in connector["people"] and family["h"] in connector["people"])

    hits = client.get("/api/people/search", params={"q": "hidden"}).json()["results"]
    assert hits[0]["context"] == ["spouse of Child"]
    for hit in client.get("/api/people/search", params={"q": "o"}).json()["results"]:
        assert not any(secret in " ".join(hit["context"]) for secret in SECRETS)

    relation = client.post("/api/relation", {"a": family["f"], "b": family["h"]}).json()
    assert relation["results"] == []
    assert relation["message"] == "No relationship found in the available data."


def test_guest_sees_only_public_data(server, family):
    assert_public_only(new_client(server), family)


def test_public_viewer_code_matches_guest(server, admin, family):
    _, value = make_code(admin, "public_viewer")
    viewer = new_client(server)
    viewer.login("code", value)
    assert_public_only(viewer, family)


def test_private_viewer_sees_everything_but_cannot_edit(server, admin, family):
    _, value = make_code(admin, "private_viewer")
    viewer = new_client(server)
    viewer.login("code", value)
    text = viewer.get("/api/tree").text
    for secret in SECRETS:
        assert secret in text
    relation = viewer.post("/api/relation", {"a": family["f"], "b": family["h"]}).json()
    assert [r["statement"] for r in relation["results"]] == ["Founder is Hidden’s father."]
    assert [r["marathi"] for r in relation["results"]] == [["वडील", "बाबा"]]
    assert (
        viewer.patch(
            f"/api/relationships/parent/{family['private_link']}",
            {"expected_revision": 1, "is_public": True},
        ).status_code
        == 403
    )
    assert viewer.get(f"/api/people/{family['f']}/deletion").status_code == 403


def test_revoked_code_falls_back_to_public_data(server, admin, family):
    code_id, value = make_code(admin, "private_viewer")
    viewer = new_client(server)
    viewer.login("code", value)
    assert "Hidden town" in viewer.get("/api/tree").text
    admin.patch(f"/api/admin/codes/{code_id}", {"revoked": True})
    assert "Hidden town" not in viewer.get("/api/tree").text


def test_unknown_people_in_relation_are_not_found(server, family):
    guest = new_client(server)
    response = guest.post("/api/relation", {"a": family["f"], "b": "nobody"})
    assert response.status_code == 404
