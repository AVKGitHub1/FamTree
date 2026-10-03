"""Reusable attribute definitions (edit capability)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from famtree.api import serializers
from famtree.api.deps import get_db, require
from famtree.api.schemas import DefinitionCreate, DefinitionUpdate
from famtree.domain import changes, repository
from famtree.security.permissions import Capability, Viewer
from famtree.storage.database import Database

router = APIRouter(prefix="/attributes", tags=["editing"])
editor = require(Capability.EDIT)


@router.get("")
def list_definitions(viewer: Viewer = Depends(editor), db: Database = Depends(get_db)) -> dict:
    with db.read() as conn:
        definitions = repository.load_definitions(conn)
        usage = repository.value_counts(conn)
    return {"definitions": [serializers.definition(d, viewer, usage) for d in definitions.values()]}


@router.post("", status_code=201)
def create_definition(
    body: DefinitionCreate, _: Viewer = Depends(editor), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        definition_id = changes.create_definition(conn, body.label, body.value_type)
    return {"id": definition_id}


@router.patch("/{definition_id}")
def update_definition(
    definition_id: str,
    body: DefinitionUpdate,
    _: Viewer = Depends(editor),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        changes.update_definition(
            conn, definition_id, body.expected_revision, body.label, body.value_type
        )
    return {"ok": True}


@router.delete("/{definition_id}")
def delete_definition(
    definition_id: str, _: Viewer = Depends(editor), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        changes.delete_definition(conn, definition_id)
    return {"ok": True}
