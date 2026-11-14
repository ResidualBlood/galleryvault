"""T3.4: ``favorites_cloud_open`` user setting (app vs external).

Invariants J6 x J5: favourites cloud rows open the in-app online detail by
default so reading progress and enqueue context stay continuous; opening on the
ExHentai site remains an explicit preference.

Each test pins one step of the settings plumbing (PLAN Batch 3 / T3.4):

* the runtime ``Settings`` model accepts only ``app`` / ``external``
* ``settings_public()`` exposes the value with the ``app`` default
* ``update_runtime_settings`` keeps it in its whitelist
* ``POST /api/settings`` persists it, echoes it back, and rejects junk with 422
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.auth import create_session, hash_password
from galleryvault.config import Settings
from galleryvault.services.settings_service import (
    settings_public,
    update_runtime_settings,
)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    def add(self, _obj: object) -> None:
        pass

    def in_transaction(self) -> bool:
        return False

    def begin(self):
        return self


class _Repo:
    """Settings repository double recording what a save would persist."""

    def __init__(self, session: object, *, stored: dict | None = None) -> None:
        self.session = session
        self.stored = dict(stored or {})
        self.saved: dict | None = None

    async def get(self) -> dict:
        return dict(self.stored)

    async def save(self, values: dict) -> None:
        self.saved = dict(values)
        self.stored = dict(values)


async def _noop_async() -> None:
    return None


class _Dispatcher:
    def spawn(self, coro: object, _name: str) -> None:
        close = getattr(coro, "close", None)
        if callable(close):
            close()


def _patch_settings_repo(monkeypatch: pytest.MonkeyPatch, repo: _Repo) -> None:
    from galleryvault.app.routers import settings as settings_router

    monkeypatch.setattr(settings_router, "SettingsRepository", lambda session: repo)
    monkeypatch.setattr(settings_router, "refresh_services", _noop_async)
    monkeypatch.setattr(settings_router, "_resolve_dispatcher", lambda _d: _Dispatcher())


@pytest.fixture
def settings_client() -> TestClient:
    original = app_state.settings
    base = original or app.state.settings
    updated = base.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "t34-unit-test-secret",
            "auth_password_hash": hash_password("admin-pass"),
            "auth_password": None,
            "download_root": "/downloads",
            "library_roots": ["/library"],
            "trusted_proxies": [],
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    orig_factory = app_state.session_factory
    try:
        with TestClient(app) as client:
            app_state.session_factory = lambda: _FakeSession()
            client.cookies.set(
                "galleryvault_session", create_session("t34-unit-test-secret", 60)
            )
            yield client
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = original
        app.state.settings = original


# --- settings model + public projection ------------------------------------


def test_settings_model_enforces_favorites_cloud_open_choices() -> None:
    assert Settings(favorites_cloud_open="app").favorites_cloud_open == "app"
    assert Settings(favorites_cloud_open="external").favorites_cloud_open == "external"
    with pytest.raises(ValidationError):
        Settings(favorites_cloud_open="bogus")


def test_settings_public_exposes_favorites_cloud_open_default_app() -> None:
    original = app_state.settings
    base = original or app.state.settings
    app_state.settings = base.model_copy(update={"favorites_cloud_open": "app"})
    try:
        public = settings_public()
    finally:
        app_state.settings = original
    assert public["favorites_cloud_open"] == "app"


def test_update_runtime_settings_whitelists_favorites_cloud_open() -> None:
    original = app_state.settings
    base = original or app.state.settings
    app_state.settings = base.model_copy(update={"favorites_cloud_open": "app"})
    try:
        update_runtime_settings({"favorites_cloud_open": "external"})
        assert app_state.settings.favorites_cloud_open == "external"
    finally:
        app_state.settings = original


# --- POST /api/settings ----------------------------------------------------


def test_favorites_cloud_open_roundtrip(
    settings_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo(None, stored={"favorites_cloud_open": "app"})
    _patch_settings_repo(monkeypatch, repo)

    response = settings_client.post("/api/settings", json={"favorites_cloud_open": "external"})

    assert response.status_code == 200
    assert repo.saved is not None
    assert repo.saved["favorites_cloud_open"] == "external"
    assert response.json()["favorites_cloud_open"] == "external"
    assert app_state.settings.favorites_cloud_open == "external"


def test_invalid_favorites_cloud_open_rejected(
    settings_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo(None, stored={"favorites_cloud_open": "app"})
    _patch_settings_repo(monkeypatch, repo)

    response = settings_client.post("/api/settings", json={"favorites_cloud_open": "bogus"})

    assert response.status_code == 422
    assert repo.saved is None
    assert "favorites_cloud_open" in str(response.json()["detail"])
