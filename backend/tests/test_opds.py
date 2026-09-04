import base64
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from galleryvault.app.main import app
from galleryvault.app.routers.opds import opds_catalog
from galleryvault.app.state import app_state
from galleryvault.auth import create_session, hash_password
from galleryvault.config import get_settings
from galleryvault.db.models import Gallery


@pytest.fixture
def opds_test_client():
    original = app_state.settings
    base = (
        original
        if hasattr(original, "model_copy")
        else (app.state.settings if hasattr(app.state.settings, "model_copy") else get_settings())
    )
    updated = base.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "unit-test-secret",
            "auth_password_hash": hash_password("opds-pass"),
            "auth_password": None,
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app_state.settings = original
        app.state.settings = original


def _make_basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


@pytest.mark.asyncio
async def test_opds_feed_links_export_cbz(monkeypatch) -> None:
    from galleryvault.app.routers import opds as opds_mod

    gallery = Gallery(
        id=7,
        title="Demo",
        storage_type="cbz",
        storage_path="/x/7",
        created_at=datetime.now(UTC),
    )

    class Repo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size):
            return 1, [gallery]

    async def fake_session():
        yield object()

    monkeypatch.setattr(opds_mod, "get_session", fake_session)
    monkeypatch.setattr(opds_mod, "GalleryRepository", Repo)
    monkeypatch.setattr(opds_mod, "display_title", lambda row: row.title)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/opds",
        "raw_path": b"/api/opds",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    response = await opds_catalog(request)
    body = response.body.decode()
    assert response.media_type.startswith("application/atom+xml")
    assert "/api/galleries/7/export.cbz" in body
    assert "Demo" in body
    assert "application/vnd.comicbook+zip" in body


def test_opds_unauthenticated_returns_401_with_realm(opds_test_client: TestClient) -> None:
    resp = opds_test_client.get("/api/opds")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == 'Basic realm="GalleryVault OPDS"'
    assert resp.json() == {"detail": "Authentication required"}


def test_opds_invalid_basic_auth_returns_401_with_realm(opds_test_client: TestClient) -> None:
    # 错用户名
    resp_bad_user = opds_test_client.get(
        "/api/opds",
        headers={"authorization": _make_basic_auth("wrong-user", "opds-pass")},
    )
    assert resp_bad_user.status_code == 401
    assert resp_bad_user.headers.get("www-authenticate") == 'Basic realm="GalleryVault OPDS"'

    # 错密码
    resp_bad_pass = opds_test_client.get(
        "/api/opds",
        headers={"authorization": _make_basic_auth("galleryvault", "wrong-pass")},
    )
    assert resp_bad_pass.status_code == 401
    assert resp_bad_pass.headers.get("www-authenticate") == 'Basic realm="GalleryVault OPDS"'

    # 格式错：缺少冒号
    token_no_colon = base64.b64encode(b"invalidformat").decode()
    resp_no_colon = opds_test_client.get(
        "/api/opds",
        headers={"authorization": f"Basic {token_no_colon}"},
    )
    assert resp_no_colon.status_code == 401
    assert resp_no_colon.headers.get("www-authenticate") == 'Basic realm="GalleryVault OPDS"'

    # 格式错：非 basic
    resp_bearer = opds_test_client.get(
        "/api/opds",
        headers={"authorization": "Bearer something"},
    )
    assert resp_bearer.status_code == 401
    assert resp_bearer.headers.get("www-authenticate") == 'Basic realm="GalleryVault OPDS"'


def test_opds_valid_basic_auth_returns_atom(
    opds_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import opds as opds_mod

    class Repo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size):
            return 0, []

    async def fake_session():
        yield object()

    monkeypatch.setattr(opds_mod, "get_session", fake_session)
    monkeypatch.setattr(opds_mod, "GalleryRepository", Repo)

    # 带 query
    resp = opds_test_client.get(
        "/api/opds?page=1",
        headers={"authorization": _make_basic_auth("galleryvault", "opds-pass")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/atom+xml")
    assert "<feed" in resp.text


def test_opds_valid_cookie_without_basic_returns_atom(
    opds_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import opds as opds_mod

    class Repo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size):
            return 0, []

    async def fake_session():
        yield object()

    monkeypatch.setattr(opds_mod, "get_session", fake_session)
    monkeypatch.setattr(opds_mod, "GalleryRepository", Repo)

    opds_test_client.cookies.set(
        "galleryvault_session", create_session("unit-test-secret", 60)
    )
    resp = opds_test_client.get("/api/opds")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/atom+xml")

