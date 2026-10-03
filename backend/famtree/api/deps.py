"""Request dependencies: storage, the caller's session, CSRF and capabilities."""

from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Depends, Request

from famtree.api.state import AppState
from famtree.domain.errors import DomainError, Forbidden
from famtree.security.permissions import Capability, Viewer
from famtree.security.sessions import resolve_session
from famtree.storage.database import Database

SESSION_COOKIE = "famtree_session"
CSRF_COOKIE = "famtree_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class StorageUnavailableError(DomainError):
    status = 503
    code = "storage_unavailable"


class NotSignedIn(DomainError):
    status = 401
    code = "not_signed_in"


class CsrfRejected(DomainError):
    status = 403
    code = "csrf"


def get_state(request: Request) -> AppState:
    return request.app.state.famtree


def get_db(state: AppState = Depends(get_state)) -> Database:
    if state.database is None:
        # Details go to the operator log only, never to the browser.
        raise StorageUnavailableError(
            "The family tree is temporarily unavailable. The site operator has been told why."
        )
    return state.database


def get_viewer(request: Request, db: Database = Depends(get_db)) -> Viewer:
    """Resolve the session afresh on every request, so revoked codes and role
    changes apply immediately; then enforce CSRF on state-changing requests."""
    with db.read() as conn:
        viewer = resolve_session(conn, request.cookies.get(SESSION_COOKIE))
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        expected = viewer.csrf_token if viewer.session_digest else request.cookies.get(CSRF_COOKIE)
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            raise CsrfRejected("Your session changed. Reload the page and try again.")
    return viewer


def require(capability: Capability) -> Callable[..., Viewer]:
    def dependency(viewer: Viewer = Depends(get_viewer)) -> Viewer:
        if not viewer.can(capability):
            if viewer.session_digest is None:
                raise NotSignedIn("Sign in with an access code that allows this.")
            raise Forbidden("Your access does not allow this.")
        return viewer

    return dependency
