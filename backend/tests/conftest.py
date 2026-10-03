"""Shared fixtures: a real encrypted data directory and an API client."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from famtree import app as app_module
from famtree.app import create_app
from famtree.config import Settings
from famtree.storage.keyfile import DatabaseKey


def _cairo_text_available() -> bool:
    try:
        import gi

        gi.require_foreign("cairo")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import PangoCairo  # noqa: F401
    except (ImportError, ValueError):
        return False
    return True


requires_rendering = pytest.mark.skipif(
    not _cairo_text_available(), reason="cairo/Pango bindings not installed (run in Docker)"
)


def write_key(path: Path, key: DatabaseKey | None = None) -> DatabaseKey:
    key = key or DatabaseKey.generate()
    path.write_text(key.to_file_text())
    os.chmod(path, 0o600)
    return key


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    data.mkdir()
    key_file = tmp_path / "secrets" / "famtree.key"
    key_file.parent.mkdir()
    write_key(key_file)
    return replace(
        Settings.from_env({}),
        data_dir=data,
        key_file=key_file,
        static_dir=None,
        cookie_secure="false",
    )


class Api:
    """TestClient wrapper that sends the CSRF token the way the SPA does."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.csrf = ""
        self.refresh()

    def refresh(self) -> dict[str, Any]:
        session = self.client.get("/api/session").json()
        self.csrf = session["csrf_token"]
        return session

    def _headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}

    def get(self, path: str, **kw: Any):
        return self.client.get(path, **kw)

    def post(self, path: str, json: Any = None, **kw: Any):
        return self.client.post(path, json=json, headers=self._headers(), **kw)

    def put(self, path: str, json: Any = None, **kw: Any):
        return self.client.put(path, json=json, headers=self._headers(), **kw)

    def patch(self, path: str, json: Any = None, **kw: Any):
        return self.client.patch(path, json=json, headers=self._headers(), **kw)

    def delete(self, path: str, **kw: Any):
        return self.client.delete(path, headers=self._headers(), **kw)

    def login(self, kind: str, secret: str):
        response = self.post("/api/auth/login", {"kind": kind, "secret": secret})
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    def logout(self):
        response = self.post("/api/auth/logout")
        self.csrf = response.json()["csrf_token"]
        return response

    def tree(self) -> dict[str, Any]:
        response = self.get("/api/tree")
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def server(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """A running app on a fresh tree. Yields the app, settings and admin password."""
    printed: list[str] = []
    monkeypatch.setattr(app_module, "print_bootstrap_password", printed.append)
    application = create_app(settings)
    with TestClient(application) as client:
        yield {
            "app": application,
            "client": client,
            "settings": settings,
            "password": printed[0] if printed else None,
            "printed": printed,
        }


@pytest.fixture
def api(server: dict[str, Any]) -> Api:
    return Api(server["client"])


def new_client(server: dict[str, Any]) -> Api:
    """An independent browser (own cookie jar) against the same running server."""
    return Api(TestClient(server["app"]))


@pytest.fixture
def admin(server: dict[str, Any]) -> Api:
    client = new_client(server)
    assert client.login("admin", server["password"]).status_code == 200
    return client


def make_code(admin: Api, role: str, label: str = "") -> tuple[str, str]:
    response = admin.post("/api/admin/codes", {"label": label, "role": role})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["code"]["id"], body["value"]
