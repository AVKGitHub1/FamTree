"""Exchanging an access code or the admin password for a session cookie."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response

from famtree.api import serializers
from famtree.api.deps import CSRF_COOKIE, SESSION_COOKIE, get_db, get_state, get_viewer
from famtree.api.errors import RateLimited
from famtree.api.schemas import LoginRequest
from famtree.api.state import AppState
from famtree.domain.errors import DomainError
from famtree.security import sessions
from famtree.security.access_codes import find_active_code
from famtree.security.passwords import verify_password
from famtree.security.permissions import Viewer
from famtree.security.proxy import client_ip, is_https
from famtree.security.tokens import new_csrf_token
from famtree.storage import meta
from famtree.storage.database import Database

log = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


class InvalidCredentials(DomainError):
    status = 401
    code = "invalid_credentials"


def _secure(request: Request, state: AppState) -> bool:
    mode = state.settings.cookie_secure
    if mode == "auto":
        return is_https(request, state.settings.trusted_proxies)
    return mode == "true"


def _guest_csrf(request: Request, response: Response, state: AppState) -> str:
    token = request.cookies.get(CSRF_COOKIE)
    if not token or len(token) > 100:
        token = new_csrf_token()
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=_secure(request, state),
            path="/api",
        )
    return token


@router.get("/session")
def get_session(
    request: Request,
    response: Response,
    viewer: Viewer = Depends(get_viewer),
    state: AppState = Depends(get_state),
) -> dict:
    csrf = viewer.csrf_token if viewer.session_digest else _guest_csrf(request, response, state)
    if request.cookies.get(SESSION_COOKIE) and viewer.session_digest is None:
        # Expired or revoked: drop the stale cookie so the browser is a clean guest.
        response.delete_cookie(SESSION_COOKIE, path="/")
    return serializers.session(viewer, csrf)


@router.post("/auth/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    viewer: Viewer = Depends(get_viewer),
    db: Database = Depends(get_db),
    state: AppState = Depends(get_state),
) -> dict:
    settings = state.settings
    retry = state.throttle.check(client_ip(request, settings.trusted_proxies))
    if retry:
        log.warning("Sign-in rate limit reached")
        raise RateLimited(retry)

    failure = InvalidCredentials("That code or password is not valid.")
    if body.kind == "admin":
        with db.read() as conn:
            stored = meta.get(conn, meta.ADMIN_PASSWORD_HASH)
        if not stored or not verify_password(stored, body.secret):
            log.info("Failed admin sign-in")
            raise failure
        principal, code_id, ttl = "admin", None, settings.admin_session_ttl_hours
    else:
        with db.read() as conn:
            code_id = find_active_code(conn, body.secret)
        if code_id is None:
            log.info("Failed access-code sign-in")
            raise failure
        principal, ttl = "code", settings.session_ttl_hours

    with db.write() as conn:
        sessions.purge_expired(conn)
        if viewer.session_digest:
            sessions.delete_session(conn, viewer.session_digest)
        issued = sessions.create_session(conn, principal, code_id, ttl)
        current = sessions.resolve_session(conn, issued.token)
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=ttl * 3600,
        httponly=True,
        samesite="strict",
        secure=_secure(request, state),
        path="/",
    )
    log.info("Signed in as %s", current.role.value)
    return serializers.session(current, issued.csrf_token)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    viewer: Viewer = Depends(get_viewer),
    db: Database = Depends(get_db),
    state: AppState = Depends(get_state),
) -> dict:
    if viewer.session_digest:
        with db.write() as conn:
            sessions.delete_session(conn, viewer.session_digest)
    with db.read() as conn:
        guest = sessions.guest(conn)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return serializers.session(guest, _guest_csrf(request, response, state))
