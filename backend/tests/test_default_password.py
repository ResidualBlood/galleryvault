"""Regression: built-in default password only unlocks a pristine install.

Fresh deployments have neither ``auth_password_hash`` nor ``auth_password``;
the documented default must only be accepted by the interactive ``/login``
form so onboarding can reach ``#/welcome`` and change it.  Basic Auth must
never expose the default, and once a password is configured the default stops
working everywhere.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.auth import DEFAULT_PASSWORD, hash_password, verify_password

BASIC_REALM = 'Basic realm="GalleryVault OPDS"'


def _basic(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


@pytest.fixture
def unconfigured_client() -> TestClient:
    """Client whose runtime settings have no admin password at all."""
    original = app_state.settings or app.state.settings
    updated = original.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "unit-test-secret",
            "auth_password": None,
            "auth_password_hash": None,
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app_state.settings = original
        app.state.settings = original


def test_default_login_works_before_password_is_configured(
    unconfigured_client: TestClient,
) -> None:
    response = unconfigured_client.post(
        "/login", data={"password": DEFAULT_PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "galleryvault_session" in response.headers.get("set-cookie", "")
    # The onboarding flow still demands a password change.
    assert unconfigured_client.get("/api/auth/session").json()["must_change_password"] is True


def test_default_login_rejected_once_password_is_configured(
    unconfigured_client: TestClient,
) -> None:
    configured = app_state.settings.model_copy(
        update={
            "auth_password_hash": hash_password("real-admin-pass"),
            "auth_password": None,
        }
    )
    app_state.settings = configured
    app.state.settings = configured

    response = unconfigured_client.post(
        "/login", data={"password": DEFAULT_PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=1" in response.headers["location"]
    assert "galleryvault_session" not in response.headers.get("set-cookie", "")


def test_basic_auth_rejects_default_before_password_is_configured(
    unconfigured_client: TestClient,
) -> None:
    response = unconfigured_client.get(
        "/api/opds",
        headers={"authorization": _basic("galleryvault", DEFAULT_PASSWORD)},
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == BASIC_REALM


def test_default_password_stops_working_after_change(
    unconfigured_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import auth as auth_router

    class FakeSession:
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

    class FakeRepo:
        def __init__(self, _session: object) -> None:
            self.saved: dict[str, object] | None = None

        async def save_extra(self, value: dict[str, object]) -> None:
            self.saved = dict(value)

    repo = FakeRepo(None)
    monkeypatch.setattr(app_state, "session_factory", lambda: FakeSession())
    monkeypatch.setattr(auth_router, "SettingsRepository", lambda session: repo)

    login = unconfigured_client.post(
        "/login", data={"password": DEFAULT_PASSWORD}, follow_redirects=False
    )
    assert login.status_code == 303

    response = unconfigured_client.post(
        "/api/auth/change-password",
        json={"current": DEFAULT_PASSWORD, "new": "brand-new-pass"},
    )
    assert response.status_code == 204
    assert repo.saved is not None
    assert verify_password("brand-new-pass", app_state.settings.auth_password_hash)

    stale = unconfigured_client.post(
        "/login", data={"password": DEFAULT_PASSWORD}, follow_redirects=False
    )
    assert stale.status_code == 303
    assert "error=1" in stale.headers["location"]

    fresh = unconfigured_client.post(
        "/login", data={"password": "brand-new-pass"}, follow_redirects=False
    )
    assert fresh.status_code == 303
    assert fresh.headers["location"] == "/"
