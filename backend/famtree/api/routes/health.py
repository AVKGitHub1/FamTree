"""Liveness and readiness probes. Readiness fails when storage cannot be
opened or decrypted; the reason is logged, not returned."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from famtree.api.deps import get_state
from famtree.api.state import AppState
from famtree.storage.database import DatabaseError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(state: AppState = Depends(get_state)) -> JSONResponse:
    unavailable = JSONResponse({"status": "unavailable"}, status_code=503)
    if state.database is None:
        return unavailable
    try:
        with state.database.read() as conn:
            conn.execute("SELECT 1 FROM meta LIMIT 1").fetchone()
    except (DatabaseError, RuntimeError):
        return unavailable
    return JSONResponse({"status": "ready"})
