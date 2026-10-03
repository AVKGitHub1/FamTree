"""Admin-only: password change, guest access, access codes and tree snapshots."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response

from famtree import clock
from famtree.api import serializers
from famtree.api.deps import get_db, require
from famtree.api.routes.auth import InvalidCredentials
from famtree.api.schemas import CodeCreate, CodeUpdate, PasswordChange, SettingsUpdate
from famtree.domain import snapshots
from famtree.domain.errors import InvalidInput
from famtree.security import access_codes, sessions
from famtree.security.passwords import hash_password, validate_new_password, verify_password
from famtree.security.permissions import Capability, Role, Viewer
from famtree.storage import meta
from famtree.storage.database import Database

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require(Capability.ADMIN)


@router.post("/password")
def change_password(
    body: PasswordChange, viewer: Viewer = Depends(admin_only), db: Database = Depends(get_db)
) -> dict:
    with db.read() as conn:
        stored = meta.get(conn, meta.ADMIN_PASSWORD_HASH)
    if not stored or not verify_password(stored, body.current_password):
        raise InvalidCredentials("The current password is not correct.")
    problem = validate_new_password(body.new_password)
    if problem:
        raise InvalidInput(problem)
    new_hash = hash_password(body.new_password)
    with db.write() as conn:
        meta.put(conn, meta.ADMIN_PASSWORD_HASH, new_hash)
        meta.put(conn, meta.ADMIN_PASSWORD_CHANGED_AT, clock.now_iso())
        signed_out = sessions.delete_admin_sessions(conn, keep_digest=viewer.session_digest)
    log.info("Admin password changed; %d other admin session(s) signed out", signed_out)
    return {"ok": True}


@router.get("/settings")
def get_settings(_: Viewer = Depends(admin_only), db: Database = Depends(get_db)) -> dict:
    with db.read() as conn:
        enabled = sessions.guest_access_enabled(conn)
    return {"guest_access": enabled}


@router.patch("/settings")
def update_settings(
    body: SettingsUpdate, _: Viewer = Depends(admin_only), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        if body.guest_access is not None:
            sessions.set_guest_access(conn, body.guest_access)
        enabled = sessions.guest_access_enabled(conn)
    log.info("Guest access is %s", "on" if enabled else "off")
    return {"guest_access": enabled}


@router.get("/codes")
def list_codes(_: Viewer = Depends(admin_only), db: Database = Depends(get_db)) -> dict:
    with db.read() as conn:
        codes = access_codes.list_codes(conn)
    return {"codes": [serializers.access_code(c) for c in codes]}


@router.post("/codes", status_code=201)
def create_code(
    body: CodeCreate,
    response: Response,
    _: Viewer = Depends(admin_only),
    db: Database = Depends(get_db),
) -> dict:
    with db.write() as conn:
        code, value = access_codes.create_code(conn, body.label, Role(body.role))
    response.headers["Cache-Control"] = "no-store"
    log.info("Access code %s created with role %s", code.id, code.role.value)
    return {"code": serializers.access_code(code), "value": value}


@router.post("/codes/{code_id}/reveal")
def reveal_code(
    code_id: str,
    response: Response,
    _: Viewer = Depends(admin_only),
    db: Database = Depends(get_db),
) -> dict:
    with db.read() as conn:
        value = access_codes.reveal_code(conn, code_id)
    response.headers["Cache-Control"] = "no-store"
    return {"value": value}


@router.patch("/codes/{code_id}")
def update_code(
    code_id: str, body: CodeUpdate, _: Viewer = Depends(admin_only), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        access_codes.update_code(
            conn,
            code_id,
            label=body.label,
            role=Role(body.role) if body.role else None,
            revoked=body.revoked,
        )
    log.info("Access code %s updated", code_id)
    return {"ok": True}


@router.delete("/codes/{code_id}")
def delete_code(
    code_id: str, _: Viewer = Depends(admin_only), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        access_codes.delete_code(conn, code_id)
    log.info("Access code %s deleted", code_id)
    return {"ok": True}


@router.get("/snapshots")
def list_snapshots(_: Viewer = Depends(admin_only), db: Database = Depends(get_db)) -> dict:
    with db.read() as conn:
        found = snapshots.list_snapshots(conn)
    return {"snapshots": [serializers.snapshot(s) for s in found], "keep": snapshots.KEEP}


@router.post("/snapshots/{snapshot_id}/load")
def load_snapshot(
    snapshot_id: str, _: Viewer = Depends(admin_only), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        saved = snapshots.load(conn, snapshot_id)
    log.info("Snapshot %s loaded; the tree it replaced is saved as snapshot %s", snapshot_id, saved)
    return {"saved": saved}


@router.delete("/snapshots/{snapshot_id}")
def delete_snapshot(
    snapshot_id: str, _: Viewer = Depends(admin_only), db: Database = Depends(get_db)
) -> dict:
    with db.write() as conn:
        snapshots.delete(conn, snapshot_id)
    log.info("Snapshot %s deleted", snapshot_id)
    return {"ok": True}
