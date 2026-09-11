"""Tests for history and reading progress clear API endpoints."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from galleryvault.app.dependencies import get_current_settings, get_session
from galleryvault.app.main import app
from galleryvault.auth import create_session
from galleryvault.db.repositories.galleries import GalleryRepository


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    """TestClient with valid session token cookie and mocked db session."""
    settings = get_current_settings()
    secret = settings.auth_secret or "test-auth-secret"
    token = create_session(secret, settings.auth_session_ttl)

    mock_session = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app, cookies={settings.auth_cookie_name: token})
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_clear_endpoints_require_auth() -> None:
    """Endpoints require authentication before processing."""
    client = TestClient(app)
    resp_hist = client.delete("/api/history")
    assert resp_hist.status_code == 401

    resp_prog = client.delete("/api/galleries/progress")
    assert resp_prog.status_code == 401


@pytest.mark.parametrize("query_param", ["", "?confirm=false", "?confirm=0"])
def test_clear_history_requires_confirm(auth_client: TestClient, query_param: str) -> None:
    """DELETE /api/history returns 400 when confirm is not true."""
    resp = auth_client.delete(f"/api/history{query_param}")
    assert resp.status_code == 400
    assert "confirm=true is required" in resp.json().get("detail", "")


def test_clear_history_success(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """DELETE /api/history?confirm=true returns 204 and clears history."""
    mock_clear = AsyncMock(return_value=None)
    monkeypatch.setattr(GalleryRepository, "clear_history", mock_clear)

    resp = auth_client.delete("/api/history?confirm=true")
    assert resp.status_code == 204
    assert mock_clear.await_count == 1


@pytest.mark.parametrize("query_param", ["", "?confirm=false", "?confirm=0"])
def test_clear_progress_requires_confirm(auth_client: TestClient, query_param: str) -> None:
    """DELETE /api/galleries/progress returns 400 when confirm is not true."""
    resp = auth_client.delete(f"/api/galleries/progress{query_param}")
    assert resp.status_code == 400
    assert "confirm=true is required" in resp.json().get("detail", "")


def test_clear_progress_success(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """DELETE /api/galleries/progress?confirm=true returns 204 and clears progress."""
    mock_clear = AsyncMock(return_value=None)
    monkeypatch.setattr(GalleryRepository, "clear_progress", mock_clear)

    resp = auth_client.delete("/api/galleries/progress?confirm=true")
    assert resp.status_code == 204
    assert mock_clear.await_count == 1
