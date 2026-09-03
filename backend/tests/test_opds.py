from datetime import UTC, datetime

import pytest
from starlette.requests import Request

from galleryvault.app.routers.opds import opds_catalog
from galleryvault.db.models import Gallery


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
