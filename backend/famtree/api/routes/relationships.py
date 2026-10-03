"""Changing and removing relationships (edit capability). New relationships
are created through POST /api/changes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from famtree.api.deps import get_db, require
from famtree.api.schemas import ParentLinkUpdate, SpouseLinkUpdate
from famtree.domain import changes
from famtree.security.permissions import Capability, Viewer
from famtree.storage.database import Database

router = APIRouter(prefix="/relationships", tags=["editing"])
editor = require(Capability.EDIT)


@router.patch("/parent/{link_id}")
def update_parent_link(
    link_id: str,
    body: ParentLinkUpdate,
    _: Viewer = Depends(editor),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        changes.update_parent_link(conn, link_id, body.expected_revision, body.role, body.is_public)
    return {"ok": True}


@router.patch("/spouse/{link_id}")
def update_spouse_link(
    link_id: str,
    body: SpouseLinkUpdate,
    _: Viewer = Depends(editor),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        changes.update_spouse_link(conn, link_id, body.expected_revision, body.is_public)
    return {"ok": True}


@router.delete("/parent/{link_id}")
def delete_parent_link(
    link_id: str,
    expected_revision: int = Query(),
    _: Viewer = Depends(editor),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        changes.delete_parent_link(conn, link_id, expected_revision)
    return {"ok": True}


@router.delete("/spouse/{link_id}")
def delete_spouse_link(
    link_id: str,
    expected_revision: int = Query(),
    _: Viewer = Depends(editor),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        changes.delete_spouse_link(conn, link_id, expected_revision)
    return {"ok": True}
