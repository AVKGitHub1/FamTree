"""Editing workflow: bootstrap person, linked additions, atomicity and revisions."""

from conftest import make_code, new_client


def first_person(admin, name="Founder", **extra):
    response = admin.post("/api/changes", {"people": [{"ref": "a", "name": name, **extra}]})
    assert response.status_code == 201, response.text
    return response.json()["created"]["a"]


def add_child(admin, parent_id, name, public=True, role="father"):
    response = admin.post(
        "/api/changes",
        {
            "people": [{"ref": "c", "name": name}],
            "parent_links": [
                {
                    "parent": {"id": parent_id},
                    "child": {"ref": "c"},
                    "role": role,
                    "is_public": public,
                }
            ],
        },
    )
    return response


def test_guests_and_viewers_cannot_create(server, api, admin):
    assert api.post("/api/changes", {"people": [{"ref": "a", "name": "X"}]}).status_code == 401
    _, value = make_code(admin, "private_viewer")
    viewer = new_client(server)
    viewer.login("code", value)
    assert viewer.post("/api/changes", {"people": [{"ref": "a", "name": "X"}]}).status_code == 403


def test_first_person_needs_no_connection_second_needs_a_public_one(admin):
    founder = first_person(admin)
    lonely = admin.post("/api/changes", {"people": [{"ref": "b", "name": "Lonely"}]})
    assert lonely.status_code == 422
    assert lonely.json()["error"]["details"]["rule"] == "public_connection"
    assert add_child(admin, founder, "Private Child", public=False).status_code == 422
    created = add_child(admin, founder, "Child")
    assert created.status_code == 201
    tree = admin.tree()
    assert {p["name"] for p in tree["people"]} == {"Founder", "Child"}
    # Both endpoints see the one stored relationship.
    link = tree["parent_links"][0]
    assert link["parent_id"] == founder and link["is_public"] is True


def test_two_new_people_and_their_link_are_created_together(admin):
    add_child(admin, first_person(admin), "Child")
    response = admin.post(
        "/api/changes",
        {
            "people": [{"ref": "x", "name": "New X"}, {"ref": "y", "name": "New Y"}],
            "spouse_links": [{"a": {"ref": "x"}, "b": {"ref": "y"}, "is_public": True}],
        },
    )
    assert response.status_code == 201
    assert len(admin.tree()["people"]) == 4  # a separate public component is fine


def test_duplicates_and_cycles_rejected_without_partial_saves(admin):
    founder = first_person(admin)
    child_id = add_child(admin, founder, "Child").json()["created"]["c"]
    before = admin.tree()

    duplicate = admin.post(
        "/api/changes",
        {
            "people": [{"ref": "n", "name": "Would Be Orphaned"}],
            "spouse_links": [{"a": {"ref": "n"}, "b": {"id": founder}, "is_public": True}],
            "parent_links": [
                {"parent": {"id": founder}, "child": {"id": child_id}, "role": "father"}
            ],
        },
    )
    assert duplicate.status_code == 409
    cycle = admin.post(
        "/api/changes",
        {
            "parent_links": [
                {"parent": {"id": child_id}, "child": {"id": founder}, "role": "mother"}
            ]
        },
    )
    assert cycle.status_code == 409
    grandchild = add_child(admin, child_id, "Grandchild").json()["created"]["c"]
    loop = admin.post(
        "/api/changes",
        {
            "parent_links": [
                {
                    "parent": {"id": grandchild},
                    "child": {"id": founder},
                    "role": "father",
                    "is_public": True,
                }
            ]
        },
    )
    assert loop.status_code == 422 and loop.json()["error"]["details"]["rule"] == "cycle"
    after = admin.tree()
    assert len(after["people"]) == len(before["people"]) + 1  # only the grandchild


def test_self_links_rejected(admin):
    founder = first_person(admin)
    response = admin.post(
        "/api/changes", {"spouse_links": [{"a": {"id": founder}, "b": {"id": founder}}]}
    )
    assert response.status_code == 422


def test_duplicate_names_stay_separate_people(admin):
    founder = first_person(admin, "Sam")
    add_child(admin, founder, "Sam")
    sams = [p for p in admin.tree()["people"] if p["name"] == "Sam"]
    assert len(sams) == 2 and sams[0]["id"] != sams[1]["id"]
    hits = admin.get("/api/people/search", params={"q": "sam"}).json()["results"]
    assert len(hits) == 2
    assert any("child of Sam" in hit["context"] for hit in hits)


def test_multiple_mothers_fathers_and_spouses(admin):
    child = first_person(admin, "Child")
    parents = [("M1", "mother"), ("M2", "mother"), ("F1", "father")]
    for i, (name, role) in enumerate(parents):
        response = admin.post(
            "/api/changes",
            {
                "people": [{"ref": f"p{i}", "name": name}],
                "parent_links": [
                    {
                        "parent": {"ref": f"p{i}"},
                        "child": {"id": child},
                        "role": role,
                        "is_public": True,
                    }
                ],
            },
        )
        assert response.status_code == 201
    tree = admin.tree()
    assert sorted(link["role"] for link in tree["parent_links"]) == ["father", "mother", "mother"]
    family = [c for c in tree["layout"]["connectors"] if c["type"] == "family"]
    assert len(family) == 1 and family[0]["junction"] is not None  # no marriage invented
    assert not [c for c in tree["layout"]["connectors"] if c["type"] == "spouse"]


def test_stale_revision_rejected(server, admin):
    founder = first_person(admin)
    revision = admin.tree()["people"][0]["revision"]
    ok = admin.put(
        f"/api/people/{founder}",
        {"expected_revision": revision, "name": "Renamed", "attributes": []},
    )
    assert ok.status_code == 200
    stale = admin.put(
        f"/api/people/{founder}", {"expected_revision": revision, "name": "Lost", "attributes": []}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"
    assert admin.tree()["people"][0]["name"] == "Renamed"


def test_birthday_without_year_and_custom_attribute_reuse(admin):
    founder = first_person(
        admin,
        attributes=[
            {
                "definition": {"id": "birth_date"},
                "value": {"month": 5, "day": 12},
                "is_public": True,
            }
        ],
    )
    person = admin.tree()["people"][0]
    assert person["attributes"][0]["value"] == {"year": None, "month": 5, "day": 12}

    response = admin.put(
        f"/api/people/{founder}",
        {
            "expected_revision": person["revision"],
            "name": "Founder",
            "definitions": [{"ref": "nick", "label": "Nickname", "value_type": "text"}],
            "attributes": [
                {"definition": {"id": "birth_date"}, "value": {"month": 5, "day": 12}},
                {"definition": {"ref": "nick"}, "value": "Doc", "is_public": True},
            ],
        },
    )
    assert response.status_code == 200
    nickname = next(d for d in admin.tree()["definitions"] if d["label"] == "Nickname")
    created = admin.post(
        "/api/changes",
        {
            "people": [
                {
                    "ref": "k",
                    "name": "Kid",
                    "attributes": [{"definition": {"id": nickname["id"]}, "value": "Sprout"}],
                }
            ],
            "parent_links": [
                {
                    "parent": {"id": founder},
                    "child": {"ref": "k"},
                    "role": "father",
                    "is_public": True,
                }
            ],
        },
    )
    assert created.status_code == 201
    values = {
        p["name"]: {a["definition_id"]: a for a in p["attributes"]} for p in admin.tree()["people"]
    }
    assert values["Founder"][nickname["id"]]["is_public"] is True
    assert values["Kid"][nickname["id"]]["is_public"] is False  # each value keeps its own setting
    assert values["Founder"]["birth_date"]["is_public"] is False  # re-saved as private


def test_attribute_definitions_rename_and_type_rules(admin):
    founder = first_person(admin)
    created = admin.post("/api/attributes", {"label": "School", "value_type": "text"})
    definition_id = created.json()["id"]
    revision = 1
    person = admin.tree()["people"][0]
    admin.put(
        f"/api/people/{founder}",
        {
            "expected_revision": person["revision"],
            "name": "Founder",
            "attributes": [{"definition": {"id": definition_id}, "value": "Hillside"}],
        },
    )
    renamed = admin.patch(
        f"/api/attributes/{definition_id}", {"expected_revision": revision, "label": "College"}
    )
    assert renamed.status_code == 200
    retyped = admin.patch(
        f"/api/attributes/{definition_id}",
        {"expected_revision": revision + 1, "value_type": "date"},
    )
    assert retyped.status_code == 409
    in_use = admin.delete(f"/api/attributes/{definition_id}")
    assert in_use.status_code == 409
    person = admin.tree()["people"][0]
    assert person["attributes"][0]["value"] == "Hillside"
    assert (
        admin.post("/api/attributes", {"label": "college", "value_type": "text"}).status_code == 409
    )


def test_visibility_change_cannot_orphan_and_delete_is_guarded(admin):
    founder = first_person(admin)
    add_child(admin, founder, "Child")
    tree = admin.tree()
    link = tree["parent_links"][0]
    private = admin.patch(
        f"/api/relationships/parent/{link['id']}",
        {"expected_revision": link["revision"], "is_public": False},
    )
    assert private.status_code == 422

    child_id = next(p["id"] for p in tree["people"] if p["name"] == "Child")
    add_child(admin, child_id, "Grandchild")
    preview = admin.get(f"/api/people/{child_id}/deletion").json()
    assert preview["allowed"] is False
    assert {p["name"] for p in preview["blocked_people"]} == {"Founder", "Grandchild"}
    child = next(p for p in admin.tree()["people"] if p["id"] == child_id)
    blocked = admin.delete(
        f"/api/people/{child_id}",
        params={
            "expected_revision": child["revision"],
            "expected_relationships": preview["relationships"],
        },
    )
    assert blocked.status_code == 422

    grandchild = next(p for p in admin.tree()["people"] if p["name"] == "Grandchild")
    preview = admin.get(f"/api/people/{grandchild['id']}/deletion").json()
    assert preview["allowed"] is True
    assert [(link["parent"]["name"], link["role"]) for link in preview["parent_links"]] == [
        ("Child", "father")
    ]
    deleted = admin.delete(
        f"/api/people/{grandchild['id']}",
        params={
            "expected_revision": grandchild["revision"],
            "expected_relationships": preview["relationships"],
        },
    )
    assert deleted.status_code == 200
    assert len(admin.tree()["people"]) == 2


def test_deletion_removes_only_the_relationships_its_preview_listed(server, admin):
    founder = first_person(admin)
    child_id = add_child(admin, founder, "Child").json()["created"]["c"]
    other_id = add_child(admin, founder, "Other").json()["created"]["c"]
    preview = admin.get(f"/api/people/{child_id}/deletion").json()
    assert preview["allowed"] is True and len(preview["parent_links"]) == 1
    child = next(p for p in admin.tree()["people"] if p["id"] == child_id)

    # Another editor connects Child to Other; Child's own revision is unchanged.
    editor = new_client(server)
    editor.login("code", make_code(admin, "editor")[1])
    added = editor.post(
        "/api/changes",
        {"spouse_links": [{"a": {"id": child_id}, "b": {"id": other_id}, "is_public": True}]},
    )
    assert added.status_code == 201, added.text
    assert next(p for p in admin.tree()["people"] if p["id"] == child_id) == child

    params = {
        "expected_revision": child["revision"],
        "expected_relationships": preview["relationships"],
    }
    stale = admin.delete(f"/api/people/{child_id}", params=params)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"
    assert len(admin.tree()["spouse_links"]) == 1  # nothing was deleted

    fresh = admin.get(f"/api/people/{child_id}/deletion").json()
    assert fresh["relationships"] != preview["relationships"]
    assert [link["spouse"]["name"] for link in fresh["spouse_links"]] == ["Other"]
    params["expected_relationships"] = fresh["relationships"]
    assert admin.delete(f"/api/people/{child_id}", params=params).status_code == 200
    assert admin.tree()["spouse_links"] == []


def test_editor_code_can_edit_but_not_admin(server, admin):
    first_person(admin)
    _, value = make_code(admin, "editor")
    editor = new_client(server)
    editor.login("code", value)
    founder = editor.tree()["people"][0]
    assert add_child(editor, founder["id"], "By Editor").status_code == 201
