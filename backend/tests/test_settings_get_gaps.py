"""``GET /api/settings`` must expose the keys the settings page can save.

``tag_translation_update_interval_minutes`` was POST-writable but absent from the
GET payload, so the settings page always fell back to the default (720).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.auth import create_session, hash_password
from galleryvault.services.settings_service import settings_public


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
    """Settings repository double that persists in memory."""

    def __init__(self, session: object, *, stored: dict | None = None) -> None:
        self.session = session
        self.stored = dict(stored or {})

    async def get(self) -> dict:
        return dict(self.stored)

    async def save(self, values: dict) -> None:
        self.stored = dict(values)


class _Dispatcher:
    def spawn(self, coro: object, _name: str) -> None:
        close = getattr(coro, "close", None)
        if callable(close):
            close()


async def _noop_async() -> None:
    return None


@pytest.fixture
def client() -> TestClient:
    original = app_state.settings
    base = original or app.state.settings
    updated = base.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "settings-get-gaps-secret",
            "auth_secret_ephemeral": False,
            "auth_password_hash": hash_password("admin-pass"),
            "auth_password": None,
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    orig_factory = app_state.session_factory
    try:
        with TestClient(app) as test_client:
            app_state.session_factory = lambda: _FakeSession()
            test_client.cookies.set(
                "galleryvault_session", create_session("settings-get-gaps-secret", 60)
            )
            yield test_client
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = original
        app.state.settings = original


def test_get_settings_returns_saved_tag_translation_interval(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import settings as settings_router

    repo = _Repo(None)
    monkeypatch.setattr(settings_router, "SettingsRepository", lambda session: repo)
    monkeypatch.setattr(settings_router, "refresh_services", _noop_async)
    monkeypatch.setattr(settings_router, "_resolve_dispatcher", lambda _d: _Dispatcher())

    saved = client.post(
        "/api/settings", json={"tag_translation_update_interval_minutes": 1440}
    )
    assert saved.status_code == 200
    assert repo.stored["tag_translation_update_interval_minutes"] == 1440

    class _Service:
        async def get_persisted_settings(self) -> dict:
            return await repo.get()

        def get_public_settings(self) -> dict:
            return settings_public()

    app.dependency_overrides[settings_router.get_settings_service] = lambda: _Service()
    try:
        response = client.get("/api/settings")
    finally:
        app.dependency_overrides.pop(settings_router.get_settings_service, None)

    assert response.status_code == 200
    body = response.json()
    assert "tag_translation_update_interval_minutes" in body
    assert body["tag_translation_update_interval_minutes"] == 1440
