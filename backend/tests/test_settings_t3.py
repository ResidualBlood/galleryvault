"""T3 regressions: settings save must fail closed and only then apply runtime state."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.auth import create_session, hash_password


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


@pytest.fixture
def settings_client() -> TestClient:
    original = app_state.settings
    base = original or app.state.settings
    updated = base.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "unit-test-secret",
            "auth_password_hash": hash_password("admin-pass"),
            "auth_password": None,
            "page_concurrency": 4,
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    orig_factory = app_state.session_factory
    try:
        with TestClient(app) as client:
            app_state.session_factory = lambda: _FakeSession()
            client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
            yield client
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = original
        app.state.settings = original


class _Repo:
    """Settings repository double; ``get`` can be made to fail."""

    def __init__(self, session: object, *, stored=None, get_error=None, save_error=None):
        self.session = session
        self.stored = dict(stored or {})
        self.get_error = get_error
        self.save_error = save_error
        self.saved: dict[str, object] | None = None

    async def get(self) -> dict[str, object]:
        if self.get_error is not None:
            raise self.get_error
        return dict(self.stored)

    async def save(self, values: dict[str, object]) -> None:
        if self.save_error is not None:
            raise self.save_error
        self.saved = dict(values)


def test_settings_read_failure_is_5xx_and_writes_nothing(
    settings_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import settings as settings_router

    repo = _Repo(None, get_error=RuntimeError("connection reset"))

    def factory(session: object) -> _Repo:
        return repo

    monkeypatch.setattr(settings_router, "SettingsRepository", factory)
    before = app_state.settings.model_dump()

    response = settings_client.post("/api/settings", json={"page_concurrency": 9})

    assert response.status_code >= 500
    assert "connection reset" not in response.text
    assert repo.saved is None
    # Runtime settings must not be mutated when persistence was impossible.
    assert app_state.settings.model_dump() == before


def test_settings_save_failure_does_not_apply_runtime(
    settings_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import settings as settings_router

    repo = _Repo(None, stored={"page_concurrency": 4}, save_error=RuntimeError("disk full"))
    monkeypatch.setattr(settings_router, "SettingsRepository", lambda session: repo)

    response = settings_client.post("/api/settings", json={"page_concurrency": 8})

    assert response.status_code >= 500
    assert repo.saved is None
    assert app_state.settings.page_concurrency == 4


def test_settings_save_keeps_keys_missing_from_request(
    settings_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial POST must not wipe unrelated persisted keys."""
    from galleryvault.app.routers import settings as settings_router

    stored = {
        "telegram_bot_token": "token-value",
        "saved_searches": [{"q": "keep-me"}],
        "page_concurrency": 4,
    }
    repo = _Repo(None, stored=stored)
    monkeypatch.setattr(settings_router, "SettingsRepository", lambda session: repo)
    monkeypatch.setattr(settings_router, "refresh_services", _noop_async)

    response = settings_client.post("/api/settings", json={"page_concurrency": 8})

    assert response.status_code == 200
    assert repo.saved is not None
    assert repo.saved["page_concurrency"] == 8
    assert repo.saved["saved_searches"] == [{"q": "keep-me"}]
    assert repo.saved["telegram_bot_token"]


async def _noop_async() -> None:
    return None
