"""Creating, editing and deleting people (edit capability)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from famtree.api.deps import get_db, get_state, require
from famtree.api.schemas import ChangeSetIn, PersonUpdate
from famtree.api.state import AppState
from famtree.domain import changes
from famtree.domain.visibility import Audience
from famtree.security.permissions import Capability, Viewer
from famtree.storage.database import Database

router = APIRouter(tags=["editing"])
editor = require(Capability.EDIT)


@router.post("/changes", status_code=201)
def apply_changes(
    body: ChangeSetIn, _: Viewer = Depends(editor), db: Database = Depends(get_db)
) -> dict:
    """New people, attribute definitions and relationships, saved atomically."""
    change_set = body.to_domain()
    with db.write() as conn:
        created = changes.apply_changes(conn, change_set)
    return {"created": created}


@router.put("/people/{person_id}")
def update_person(
    person_id: str, body: PersonUpdate, _: Viewer = Depends(editor), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        changes.update_person(
            conn,
            person_id,
            body.expected_revision,
            body.name,
            [a.to_domain() for a in body.attributes],
            [d.to_domain() for d in body.definitions],
        )
    return {"ok": True}


@router.get("/people/{person_id}/deletion")
def deletion_preview(
    person_id: str, _: Viewer = Depends(editor), state: AppState = Depends(get_state)
) -> dict:
    graph = state.views.graph(Audience.FULL)
    preview = changes.preview_person_deletion(graph, person_id)
    return {
        "allowed": preview.allowed,
        "parent_links": preview.parent_links,
        "spouse_links": preview.spouse_links,
        "blocked_people": [
            {"id": pid, "name": graph.people[pid].name} for pid in preview.blocked_people
        ],
    }


@router.delete("/people/{person_id}")
def delete_person(
    person_id: str,
    expected_revision: int = Query(),
    _: Viewer = Depends(editor),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        changes.delete_person(conn, person_id, expected_revision)
    return {"ok": True}
