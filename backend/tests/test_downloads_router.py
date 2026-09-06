from unittest.mock import AsyncMock

import pytest

from galleryvault.app.dependencies import resolve_display_title
from galleryvault.app.routers import downloads as downloads_router
from galleryvault.db.models import DownloadTask
from galleryvault.db.repositories.downloads import DownloadRepository
from galleryvault.services.eh_client import EhClient


@pytest.mark.asyncio
async def test_download_repository_create_cleans_html_entities_and_prefix():
    added = []

    class FakeSession:
        async def scalar(self, stmt):
            return None

        def add(self, instance):
            added.append(instance)

        async def flush(self):
            pass

    repo = DownloadRepository(FakeSession())
    task = await repo.create(
        gid=3969839,
        token="abcdef1234",
        title="3969839-[Nyako] 2026.4.18 &lt;AI生成&gt; [无修正]",
        title_jpn="3969839-[Nyako] 2026.4.18 &lt;AI生成&gt; [無修正]",
    )
    assert task is not None
    assert task.title == "[Nyako] 2026.4.18 <AI生成> [无修正]"
    assert task.title_jpn == "[Nyako] 2026.4.18 <AI生成> [無修正]"


@pytest.mark.asyncio
async def test_download_repository_create_numeric_fallback():
    added = []

    class FakeSession:
        async def scalar(self, stmt):
            return None

        def add(self, instance):
            added.append(instance)

        async def flush(self):
            pass

    repo = DownloadRepository(FakeSession())
    task = await repo.create(
        gid=12345,
        token="tok",
        title="123456",
        title_jpn="123456-789",
    )
    assert task is not None
    assert task.title == "123456"
    assert task.title_jpn == "123456-789"


def test_resolve_display_title_unescapes_and_strips_prefix():
    # Japanese mode by default
    res = resolve_display_title(
        title="3969839-English &lt;Title&gt;",
        title_jpn="3969839-Japanese &amp; &lt;Title&gt;",
    )
    assert res == "Japanese & <Title>"

    # Fallback to English when jpn empty
    res_en = resolve_display_title(
        title="4119033-NFFA&lt; Ai generated &gt;",
        title_jpn="",
    )
    assert res_en == "NFFA< Ai generated >"


@pytest.mark.asyncio
async def test_eh_client_fetch_gmetadata_unescapes_titles():
    import httpx

    client = EhClient()
    fake_response = httpx.Response(
        200,
        json={
            "gmetadata": [
                {
                    "gid": 4119033,
                    "token": "tok1",
                    "thumb": "https://ehgt.org/t/ab/cd.jpg",
                    "title": "NFFA&lt; Ai generated &gt;",
                    "title_jpn": "&lt;日本語タイトル&gt; &amp; test",
                }
            ]
        },
        request=httpx.Request("POST", "https://api.e-hentai.org/api.php"),
    )
    client._request = AsyncMock(return_value=fake_response)

    res = await client.fetch_gmetadata([(4119033, "tok1")])
    assert 4119033 in res
    assert res[4119033]["title"] == "NFFA< Ai generated >"
    assert res[4119033]["title_jpn"] == "<日本語タイトル> & test"


@pytest.mark.asyncio
async def test_downloads_router_list_downloads_cleans_titles(monkeypatch):
    task = DownloadTask(
        id=6602,
        gid=3969839,
        token="tok",
        title="3969839-[Nyako] 2026.4.18 &lt;AI生成&gt;",
        title_jpn=None,
        status="pending",
        retry_count=0,
        max_retries=10,
    )

    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size, status):
            return 1, [task]

    async def fake_get_session():
        yield None

    monkeypatch.setattr(downloads_router, "get_session", fake_get_session)
    monkeypatch.setattr(downloads_router, "DownloadRepository", FakeRepo)
    monkeypatch.setattr(downloads_router.app_state, "downloader", None)

    res = await downloads_router.list_downloads(page=1, page_size=24, status="pending")
    assert len(res["items"]) == 1
    assert res["items"][0]["title"] == "[Nyako] 2026.4.18 <AI生成>"
