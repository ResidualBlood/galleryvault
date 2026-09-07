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


@pytest.mark.asyncio
async def test_download_repository_progress_archive_fallback():
    class FakeRow:
        def __init__(self):
            self.current_page = 0
            self.total_pages = 0
            self.archive_fallback = False
            self.updated_at = None

    fake_row = FakeRow()

    class FakeSession:
        async def get(self, model, task_id):
            return fake_row

        async def flush(self):
            pass

    repo = DownloadRepository(FakeSession())

    # Update progress without archive_fallback -> remains False
    await repo.progress(1, 2, 10)
    assert fake_row.current_page == 2
    assert fake_row.total_pages == 10
    assert fake_row.archive_fallback is False

    # Update progress with archive_fallback=True -> updates to True
    await repo.progress(1, 3, 10, archive_fallback=True)
    assert fake_row.current_page == 3
    assert fake_row.archive_fallback is True

    # Update progress with archive_fallback=None -> keeps True
    await repo.progress(1, 4, 10, archive_fallback=None)
    assert fake_row.current_page == 4
    assert fake_row.archive_fallback is True


@pytest.mark.asyncio
async def test_download_repository_list_page_archive_fallback():
    task = DownloadTask(
        id=1,
        gid=1001,
        token="tok",
        title="Test Title",
        status="downloading",
        quality="resample",
        archive_fallback=True,
    )

    class FakeResult:
        def all(self):
            return [(task, "Test Title", None)]

    class FakeSession:
        async def scalar(self, stmt):
            return 1

        async def execute(self, stmt):
            return FakeResult()

    repo = DownloadRepository(FakeSession())
    total, items = await repo.list_page(1, 24)
    assert total == 1
    assert len(items) == 1
    assert items[0]["archive_fallback"] is True
    assert items[0].archive_fallback is True


@pytest.mark.asyncio
async def test_download_worker_progress_archive_fallback(monkeypatch):
    from galleryvault.app.state import app_state
    from galleryvault.services.download_worker import download_progress

    progress_calls = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def progress(self, task_id, current, total, archive_fallback=None):
            progress_calls.append((task_id, current, total, archive_fallback))

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

    monkeypatch.setattr("galleryvault.services.download_worker.DownloadRepository", FakeRepo)
    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: FakeSession()
    try:
        await download_progress(42, 5, 20, archive_fallback=True)
        assert len(progress_calls) == 1
        assert progress_calls[0] == (42, 5, 20, True)
    finally:
        app_state.session_factory = orig_factory

