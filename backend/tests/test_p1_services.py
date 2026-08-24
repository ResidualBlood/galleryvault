from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from galleryvault.config import Settings
from galleryvault.db.models import GalleryTag, Tag
from galleryvault.db.repository import GalleryRepository
from galleryvault.services.downloader import Downloader, DownloadTask
from galleryvault.services.eh_client import (
    EhClient,
    FavoriteData,
    GalleryData,
    GalleryPageData,
    _parse_tags,
    parse_gallery_url,
)
from galleryvault.services.favorites import FavoritesService
from galleryvault.services.tag_sync import TagSyncService
from galleryvault.services.telegram import TelegramNotifier
from galleryvault.services.telegram_bot import TelegramBotService


def test_gallery_url_forms() -> None:
    assert parse_gallery_url("https://exhentai.org/g/123/abcdef/") == (123, "abcdef")
    assert parse_gallery_url("123/abcdef") == (123, "abcdef")


def test_exhentai_tag_link_markup_is_parsed() -> None:
    tags = _parse_tags(
        '<div id="td_artist:alice" class="gt"><a id="ta_artist:alice" href="#">Alice</a></div>'
        '<div id="td_language:chinese" class="gtl"><a id="ta_language:chinese" href="#">Chinese</a></div>'
    )
    assert tags == [
        {"namespace": "artist", "name": "Alice"},
        {"namespace": "language", "name": "Chinese"},
    ]


class FakeDownloadClient:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch_gallery(self, gid: int, token: str) -> GalleryData:
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("temporary")
        return GalleryData(
            gid,
            token,
            "safe/title",
            [GalleryPageData(0, "one", "p1"), GalleryPageData(1, "two", "p2")],
        )

    async def download_image(self, url: str) -> bytes:
        return b"image"


@pytest.mark.asyncio
async def test_downloader_retries_and_writes_version2(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    result = await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title"))
    assert client.calls == 3
    metadata = (result.path / ".ehviewer").read_text().splitlines()
    assert metadata[1:8] == ["00000000", "1", "tok", "1", "1", "2", "2"]
    assert (result.path / ".ehviewer").read_text().splitlines()[-2:] == ["0 p1", "1 p2"]
    assert sorted(p.name for p in result.path.glob("*.jpg")) == ["00000001.jpg", "00000002.jpg"]
    assert "/" not in result.path.name


@pytest.mark.asyncio
async def test_downloader_reports_progress(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    client.calls = 3  # succeed on the first call
    progress: list[tuple[int, int]] = []

    async def on_progress(current: int, total: int) -> None:
        progress.append((current, total))

    await Downloader(client, tmp_path).execute(
        DownloadTask(1, "tok", "title"), progress=on_progress
    )
    assert (0, 2) in progress
    assert (2, 2) in progress
    assert progress[0] == (0, 2) and progress[-1] == (2, 2)


class CountingDownloadClient(FakeDownloadClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 3  # succeed immediately
        self.image_calls = 0

    async def download_image(self, url: str) -> bytes:
        self.image_calls += 1
        return b"image"


@pytest.mark.asyncio
async def test_downloader_resumes_without_refetching_existing_pages(tmp_path: Path) -> None:
    client = CountingDownloadClient()
    downloader = Downloader(client, tmp_path)
    await downloader.execute(DownloadTask(1, "tok", "title"))
    assert client.image_calls == 2  # both pages fetched on first run
    # Retry: existing pages are kept, nothing is re-downloaded.
    result2 = await downloader.execute(DownloadTask(1, "tok", "title"))
    assert client.image_calls == 2  # no new image requests
    assert (result2.path / "00000001.jpg").exists()
    assert (result2.path / "00000002.jpg").exists()


class FakeFavoritesRepo:
    def __init__(self) -> None:
        self.known = set()
        self.remembered = []

    async def known_gids(self, favcat: int) -> set[int]:
        return self.known

    async def remember(self, favcat: int, item: FavoriteData) -> None:
        self.known.add(item.gid)
        self.remembered.append(item.gid)

    async def checked(self, favcat: int, success: bool) -> None:
        pass


class FakeFetcher:
    async def fetch_favorites(self, favcat: int) -> list[FavoriteData]:
        return [FavoriteData(1, "a", "one", "u"), FavoriteData(1, "a", "one", "u")]


@pytest.mark.asyncio
async def test_favorites_deduplicates_and_monitor_only_does_not_enqueue() -> None:
    repo = FakeFavoritesRepo()
    queue = type("Queue", (), {"enqueue": lambda self, item: pytest.fail("must not enqueue")})()
    result = await FavoritesService(FakeFetcher(), repo, queue).check_category(
        0, mode="monitor_only"
    )
    assert result.new == 1 and result.downloaded == 0
    assert repo.remembered == [1]


@pytest.mark.asyncio
async def test_telegram_without_token_is_noop() -> None:
    assert not await TelegramNotifier(Settings(telegram_bot_token=None)).send_message("x", "1")


@pytest.mark.asyncio
async def test_telegram_shared_client_survives_send_message() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"ok": True})

    settings = Settings(telegram_bot_token="secret", telegram_chat_ids=["7"])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notifier = TelegramNotifier(settings, client=client)
        # First send uses the shared client and must NOT close it.
        assert await notifier.send_message("hello", chat_id="7")
        # The same shared client must still be usable afterwards (the Telegram
        # bot polls through this same client; closing it would raise).
        assert notifier.client is client
        assert await notifier.send_message("again", chat_id="7")
        assert len(calls) == 2


@pytest.mark.asyncio
async def test_persistent_downloader_does_not_retry_inside_downloader(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    with pytest.raises(RuntimeError):
        await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title", id=9))
    assert client.calls == 1


@pytest.mark.asyncio
async def test_telegram_bot_uses_mock_transport_and_allowed_user() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": []})

    class Queue:
        async def enqueue(self, item):
            self.item = item
            return True

    class Notifier:
        def __init__(self):
            self.messages = []

        async def send_message(self, text, chat_id=None):
            self.messages.append((text, chat_id))

    queue, notifier = Queue(), Notifier()
    settings = Settings(telegram_bot_token="secret", telegram_allowed_user_ids=[7])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bot = TelegramBotService(settings, client=client, queue=queue, notifier=notifier)
        await bot.handle_update(
            {"message": {"from": {"id": 8}, "text": "/status", "chat": {"id": 8}}}
        )
        await bot.handle_update(
            {"message": {"from": {"id": 7}, "text": "/pause", "chat": {"id": 7}}}
        )
        assert not requests
        assert notifier.messages == [("Downloads paused", 7)]


@pytest.mark.asyncio
async def test_fetch_gallery_resolves_viewer_images_and_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/g/7/token/":
            return httpx.Response(
                200,
                text="""<h1 class="gm">A title</h1><div class="gt">artist: alice</div>
                <a href="/s/7/token/page-a/">one</a><a href="/s/7/token/page-b/">two</a>""",
            )
        if request.url.path.endswith("page-a/"):
            return httpx.Response(
                200, text='<html><img src="https://img.test/a.jpg" id="img"></html>'
            )
        if request.url.path.endswith("page-b/"):
            return httpx.Response(200, text='<img id="img" src="/images/b.jpg">')
        raise AssertionError(request.url)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.test"), client=http_client)
        gallery = await client.fetch_gallery(7, "token")
    assert gallery.title == "A title"
    assert [page.url for page in gallery.pages] == [
        "https://exhentai.test/s/7/token/page-a/",
        "https://exhentai.test/s/7/token/page-b/",
    ]
    assert [page.image_url for page in gallery.pages] == [
        "https://img.test/a.jpg",
        "https://exhentai.test/images/b.jpg",
    ]
    assert gallery.tags == [{"namespace": "artist", "name": "alice"}]


@pytest.mark.asyncio
async def test_tag_sync_deduplicates_and_replaces_relations() -> None:
    gallery = type("Gallery", (), {"id": 3, "gid": 7, "token": "token"})()

    class Repo:
        async def get_for_tag_sync(self, identifier: int):
            assert identifier == 3
            return gallery

        async def replace_tags(self, row, tags, synced_at, category=None):
            assert row is gallery
            assert category == "manga"
            assert {(item["namespace"], item["name"]) for item in tags} == {
                ("artist", "alice"),
                ("female", "fox"),
            }
            gallery.tags_synced_at = synced_at
            gallery.category = category
            return 2

    class Client:
        downloads = 0

        async def fetch_gallery(self, gid: int, token: str):
            assert (gid, token) == (7, "token")
            return GalleryData(
                7,
                token,
                "Remote title",
                [],
                [
                    {"namespace": "artist", "name": "alice"},
                    {"namespace": "artist", "name": "alice"},
                    {"namespace": "female", "name": "fox"},
                ],
                category="manga",
            )

        async def download_image(self, url: str) -> bytes:
            self.downloads += 1
            raise AssertionError("tag sync must not download images")

    client = Client()
    result = await TagSyncService(client, Repo()).sync(3)
    assert result.gid == 7 and result.title == "Remote title" and result.count == 2
    assert gallery.tags_synced_at == result.synced_at
    assert gallery.category == "manga"  # sync refreshes the category too
    assert client.downloads == 0


@pytest.mark.asyncio
async def test_repository_replaces_tag_rows_and_reuses_tag_names() -> None:
    existing = Tag(namespace="artist", name="alice")
    existing.id = 11

    class Session:
        def __init__(self):
            self.deleted = []
            self.added = []
            self.lookups = 0

        async def execute(self, statement):
            # pg_insert ... ON CONFLICT DO NOTHING: the fake has no real DB, so
            # just record the delete statement and ignore the upsert.
            from sqlalchemy.sql.expression import Insert

            if isinstance(statement, Insert):
                return
            self.deleted.append(statement)

        async def scalar(self, statement):
            self.lookups += 1

        async def scalars(self, statement):
            # After the upsert, return the existing artist tag plus a new one.
            fox = Tag(namespace="female", name="fox")
            fox.id = 22
            result = _RowResult([existing, fox])
            return result

        def add(self, value):
            if isinstance(value, Tag):
                value.id = 22
            self.added.append(value)

        async def flush(self):
            pass

    session = Session()
    gallery = SimpleNamespace(id=3, tags_synced_at=None)
    timestamp = datetime.now(UTC)
    count = await GalleryRepository(session).replace_tags(
        gallery,
        [
            {"namespace": "artist", "name": "alice"},
            {"namespace": "artist", "name": "alice"},
            {"namespace": "female", "name": "fox"},
        ],
        timestamp,
    )
    relations = [item for item in session.added if isinstance(item, GalleryTag)]
    assert count == 2 and len(session.deleted) == 1
    assert {(item.gallery_id, item.tag_id) for item in relations} == {(3, 11), (3, 22)}
    assert gallery.tags_synced_at == timestamp


class _RowResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return list(self._rows)


class _SelectSession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        return _RowResult(self.rows)


class _KeysetSession:
    """Emulates pending_tag_sync_ids keyset pagination off an in-memory id list."""

    def __init__(self, ids):
        self.ids = sorted(ids)

    async def execute(self, statement):
        import re

        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        last_id = int(re.search(r"id > (\d+)", sql).group(1))
        limit = int(re.search(r"LIMIT (\d+)", sql).group(1))
        rows = [(i,) for i in self.ids if i > last_id][:limit]
        return _RowResult(rows)


@pytest.mark.asyncio
async def test_pending_tag_sync_ids_returns_only_unsynced() -> None:
    session = _SelectSession([(7,), (8,)])
    ids = await GalleryRepository(session).pending_tag_sync_ids(1000, 0)
    assert ids == [7, 8]


@pytest.mark.asyncio
async def test_pending_tag_sync_ids_keyset_advances() -> None:
    session = _KeysetSession([3, 1, 9, 5, 7])
    page1 = await GalleryRepository(session).pending_tag_sync_ids(2, 0)
    assert page1 == [1, 3]
    page2 = await GalleryRepository(session).pending_tag_sync_ids(2, page1[-1])
    assert page2 == [5, 7]
    page3 = await GalleryRepository(session).pending_tag_sync_ids(2, page2[-1])
    assert page3 == [9]


@pytest.mark.asyncio
async def test_tag_sync_status_for_gids_maps_gid_to_synced_at() -> None:
    session = _SelectSession([(100, None), (200, datetime(2026, 1, 1, tzinfo=UTC))])
    status = await GalleryRepository(session).tag_sync_status_for_gids([100, 200])
    assert status == {100: None, 200: datetime(2026, 1, 1, tzinfo=UTC)}
