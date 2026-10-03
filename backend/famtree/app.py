"""FastAPI application factory: storage lifecycle, hardening middleware,
API routes and the single-page app."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from famtree.api.deps import CSRF_HEADER, SAFE_METHODS
from famtree.api.errors import install_error_handlers
from famtree.api.routes import api_router
from famtree.api.state import AppState
from famtree.config import Settings
from famtree.storage.bootstrap import (
    StorageUnavailable,
    acquire_lock,
    check_data_dir,
    open_storage,
    release_lock,
)

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def print_bootstrap_password(password: str) -> None:
    """Shown once on the container's standard output and nowhere else
    (deliberately not through the logging system)."""
    bar = "=" * 64
    sys.stdout.write(
        f"\n{bar}\n"
        "FamTree created a new, empty family tree.\n\n"
        f"    Admin password:  {password}\n\n"
        "This is shown only once. Store it somewhere safe, then change it\n"
        "in Admin > Password. If it is lost, reset it with:\n"
        "    docker compose exec famtree famtree-admin reset-admin-password\n"
        f"{bar}\n\n"
    )
    sys.stdout.flush()


def start_storage(state: AppState) -> None:
    settings = state.settings
    try:
        check_data_dir(settings)
        state.lock_handle = acquire_lock(settings.data_dir)
        opened = open_storage(settings)
    except StorageUnavailable as exc:
        release_lock(state.lock_handle)
        state.lock_handle = None
        state.storage_error = exc
        log.error("STORAGE UNAVAILABLE (%s): %s", exc.code, exc)
        log.error("The server will keep running and report not-ready until this is fixed.")
        return
    state.attach(opened.database)
    if opened.bootstrap_password:
        print_bootstrap_password(opened.bootstrap_password)
    log.info("Storage ready (%s)", settings.db_path)


def stop_storage(state: AppState) -> None:
    if state.database is not None:
        state.database.close()
        state.database = None
    release_lock(state.lock_handle)
    state.lock_handle = None


def create_app(settings: Settings, state: AppState | None = None) -> FastAPI:
    """With `state` given (tests), storage is managed by the caller."""
    manage_storage = state is None
    state = state or AppState(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if manage_storage:
            start_storage(state)
        try:
            yield
        finally:
            if manage_storage:
                stop_storage(state)
                log.info("Shut down cleanly")

    app = FastAPI(
        title="FamTree",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.famtree = state
    install_error_handlers(app)

    @app.middleware("http")
    async def harden(request: Request, call_next) -> Response:
        is_api = request.url.path.startswith("/api/")
        # Cheap first line of CSRF defence; get_viewer then checks the token itself.
        if (
            is_api
            and request.method not in SAFE_METHODS
            and (
                request.headers.get("sec-fetch-site") == "cross-site"
                or not request.headers.get(CSRF_HEADER)
            )
        ):
            return JSONResponse(
                {"error": {"code": "csrf", "message": "Cross-site request refused."}},
                status_code=403,
            )
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if is_api:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(api_router)
    if settings.static_dir and (settings.static_dir / "index.html").is_file():
        _mount_spa(app, settings.static_dir)
    return app


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    if (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    root_files = {p.name: p for p in static_dir.iterdir() if p.is_file()}

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        if path.startswith("api/"):
            return JSONResponse(
                {"error": {"code": "not_found", "message": "Not found."}}, status_code=404
            )
        if path in root_files:
            return FileResponse(root_files[path])
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
