"""Bearer API token: generation, whitelist enforcement and cookie CSRF parity."""

from __future__ import annotations

import json
from typing import Any, Self

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.app.middleware import auth_and_csrf_middleware
from galleryvault.app.state import app_state
from galleryvault.auth import create_session, hash_password
from galleryvault.services.api_token import hash_token

KNOWN_TOKEN = "known-companion-token"
SESSION_SECRET = "unit-test-secret"
COOKIE_NAME = "galleryvault_session"


class _Row:
    def __init__(self, store: dict[str, Any], key: str) -> None:
        self._store = store
        self._key = key

    @property
    def value(self) -> Any:
        return self._store[self._key]

    @value.setter
    def value(self, new_value: Any) -> None:
        self._store[self._key] = new_value


class FakeSession:
    """Minimal AsyncSession double for the ``runtime_auth`` settings row."""

    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def get(self, _model: object, key: str) -> _Row | None:
        return _Row(self.store, key) if key in self.store else None

    def add(self, obj: Any) -> None:
        self.store[str(obj.key)] = obj.value

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def in_transaction(self) -> bool:
        return False


def _store_with_token() -> dict[str, Any]:
    return {
        "runtime_auth": {
            "api_token_hash": hash_token(KNOWN_TOKEN),
            "api_token_created_at": "2026-11-12T00:00:00+00:00",
        }
    }


@pytest.fixture
def token_store() -> dict[str, Any]:
    return _store_with_token()


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch, token_store: dict[str, Any]):
    original = app_state.settings or app.state.settings
    updated = original.model_copy(
        update={
            "auth_required": True,
            "auth_secret": SESSION_SECRET,
            "auth_password_hash": hash_password("admin-pass"),
            "auth_password": None,
            "auth_cookie_name": COOKIE_NAME,
        }
    )
    monkeypatch.setattr(app_state, "settings", updated)
    app.state.settings = updated
    yield token_store
    app.state.settings = original


@pytest.fixture
def client(auth_settings: dict[str, Any]) -> TestClient:
    with TestClient(app) as test_client:
        app_state.session_factory = lambda: FakeSession(auth_settings)
        try:
            yield test_client
        finally:
            app_state.session_factory = None


def _login_cookie(test_client: TestClient) -> None:
    test_client.cookies.set(COOKIE_NAME, create_session(SESSION_SECRET, 60))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_generate_returns_plaintext_once_and_stores_only_hash(client: TestClient) -> None:
    _login_cookie(client)
    response = client.post("/api/auth/api-token")
    assert response.status_code == 200
    token = response.json()["token"]
    assert token

    state = client.get("/api/auth/api-token")
    assert state.status_code == 200
    body = state.json()
    assert body["configured"] is True
    assert "token" not in body
    assert token not in state.text
    assert body["created_at"]


def test_storage_is_hash_not_plaintext(
    client: TestClient, token_store: dict[str, Any]
) -> None:
    _login_cookie(client)
    token = client.post("/api/auth/api-token").json()["token"]
    stored = token_store["runtime_auth"]
    assert stored["api_token_hash"] == hash_token(token)
    assert token not in json.dumps(stored)
    assert token not in stored["api_token_hash"]


def test_get_never_returns_plaintext(client: TestClient) -> None:
    _login_cookie(client)
    token = client.post("/api/auth/api-token").json()["token"]
    response = client.get("/api/auth/api-token")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"configured", "created_at"}
    assert token not in response.text
    assert token not in json.dumps(body)


def test_generate_requires_session_and_rejects_bearer(client: TestClient) -> None:
    assert client.post("/api/auth/api-token").status_code == 401

    response = client.post("/api/auth/api-token", headers=_bearer(KNOWN_TOKEN))
    assert response.status_code == 403


def test_revoke_invalidates_token(client: TestClient, token_store: dict[str, Any]) -> None:
    _login_cookie(client)
    token = client.post("/api/auth/api-token").json()["token"]
    client.cookies.clear()

    assert client.get("/api/auth/session", headers=_bearer(token)).status_code == 200

    _login_cookie(client)
    assert client.delete("/api/auth/api-token").status_code == 204
    assert client.get("/api/auth/api-token").json()["configured"] is False
    client.cookies.clear()

    assert client.get("/api/auth/session", headers=_bearer(token)).status_code == 401


def test_regenerate_invalidates_previous_token(client: TestClient) -> None:
    _login_cookie(client)
    first = client.post("/api/auth/api-token").json()["token"]
    second = client.post("/api/auth/api-token").json()["token"]
    assert first != second
    client.cookies.clear()

    assert client.get("/api/auth/session", headers=_bearer(first)).status_code == 401
    assert client.get("/api/auth/session", headers=_bearer(second)).status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/session"),
        ("GET", "/api/eh/status"),
        ("GET", "/api/favorites/categories"),
        ("POST", "/api/favorites/add"),
        ("POST", "/api/favorites/remove"),
        ("POST", "/api/downloads"),
        ("GET", "/api/downloads"),
    ],
)
def test_bearer_whitelisted_endpoints(
    auth_settings: dict[str, Any], method: str, path: str
) -> None:
    mini = _mini_app()
    with TestClient(mini) as mini_client:
        app_state.session_factory = lambda: FakeSession(auth_settings)
        response = mini_client.request(
            method, path, headers=_bearer(KNOWN_TOKEN), json={} if method == "POST" else None
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/settings"),
        ("POST", "/api/auth/change-password"),
        ("GET", "/api/auth/api-token"),
        ("POST", "/api/auth/api-token"),
        ("GET", "/api/galleries"),
    ],
)
def test_bearer_outside_whitelist_is_forbidden(
    auth_settings: dict[str, Any], method: str, path: str
) -> None:
    mini = _mini_app()
    with TestClient(mini) as mini_client:
        app_state.session_factory = lambda: FakeSession(auth_settings)
        response = mini_client.request(method, path, headers=_bearer(KNOWN_TOKEN), json={})
        assert response.status_code == 403


@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_missing_or_wrong_bearer_is_unauthorized(
    auth_settings: dict[str, Any], token: str
) -> None:
    mini = _mini_app()
    with TestClient(mini) as mini_client:
        app_state.session_factory = lambda: FakeSession(auth_settings)
        headers = {} if not token else _bearer(token)
        assert mini_client.get("/api/auth/session", headers=headers).status_code == 401


def test_bearer_skips_csrf_and_origin_checks(auth_settings: dict[str, Any]) -> None:
    mini = _mini_app()
    with TestClient(
        mini, client=("192.168.1.50", 50000), base_url="http://galleryvault.local"
    ) as external:
        app_state.session_factory = lambda: FakeSession(auth_settings)
        response = external.post("/api/downloads", headers=_bearer(KNOWN_TOKEN), json={})
        assert response.status_code == 200, response.text

        cross = external.post(
            "/api/favorites/add",
            headers={
                **_bearer(KNOWN_TOKEN),
                "Origin": "http://evil.example",
                "Sec-Fetch-Site": "cross-site",
            },
            json={},
        )
        assert cross.status_code == 200, cross.text


def test_cookie_post_without_csrf_still_blocked(auth_settings: dict[str, Any]) -> None:
    mini = _mini_app()
    with TestClient(
        mini, client=("192.168.1.50", 50000), base_url="http://galleryvault.local"
    ) as external:
        app_state.session_factory = lambda: FakeSession(auth_settings)
        external.cookies.set(COOKIE_NAME, create_session(SESSION_SECRET, 60))

        blocked = external.post("/api/downloads", json={})
        assert blocked.status_code == 403
        assert blocked.json() == {"detail": "CSRF token required"}

        external.cookies.set("galleryvault_csrf", "csrf-value")
        allowed = external.post(
            "/api/downloads", headers={"X-CSRF-Token": "csrf-value"}, json={}
        )
        assert allowed.status_code == 200


def _mini_app() -> FastAPI:
    """Stand-in routes for every whitelist entry, to test only the middleware."""

    mini = FastAPI()
    mini.middleware("http")(auth_and_csrf_middleware)

    @mini.get("/api/auth/session")
    async def _session() -> dict[str, bool]:
        return {"authenticated": True}

    @mini.get("/api/eh/status")
    async def _eh_status() -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/api/favorites/categories")
    async def _categories() -> dict[str, bool]:
        return {"ok": True}

    @mini.post("/api/favorites/add")
    async def _favorites_add() -> dict[str, bool]:
        return {"ok": True}

    @mini.post("/api/favorites/remove")
    async def _favorites_remove() -> dict[str, bool]:
        return {"ok": True}

    @mini.post("/api/downloads")
    async def _downloads_create() -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/api/downloads")
    async def _downloads_list() -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/api/settings")
    async def _settings() -> dict[str, bool]:
        return {"ok": True}

    @mini.post("/api/auth/change-password")
    async def _change_password(_request: Request) -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/api/auth/api-token")
    async def _token_get() -> dict[str, bool]:
        return {"ok": True}

    @mini.post("/api/auth/api-token")
    async def _token_post() -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/api/galleries")
    async def _galleries() -> dict[str, bool]:
        return {"ok": True}

    return mini
