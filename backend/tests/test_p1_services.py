import asyncio
import json
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


def test_gdata_tag_normalization_from_cache_dicts() -> None:
    from galleryvault.app.main import _parse_gdata_tags, _tags_to_gdata_strings

    # metadata_map returns {"namespace": ..., "name": ...} dicts; the favorites
    # metadata builder must NOT unpack the dict keys as the tag values.
    dict_tags = [
        {"namespace": "artist", "name": "alice"},
        {"namespace": "misc", "name": "twintails"},
        {"namespace": "", "name": ""},
    ]
    gtags = _tags_to_gdata_strings(dict_tags)
    assert gtags == ["artist:alice", "misc:twintails"]
    assert _parse_gdata_tags(gtags) == [
        ("artist", "alice"),
        ("misc", "twintails"),
    ]

    # The DB-pair shape must also round-trip.
    assert _tags_to_gdata_strings([["language", "chinese"]]) == ["language:chinese"]
    assert _tags_to_gdata_strings(None) == []


class FakeDownloadClient:
    def __init__(self) -> None:
        self.calls = 0
        self.last_max_pages = None

    async def fetch_gallery(
        self, gid: int, token: str, max_pages: int | None = None
    ) -> GalleryData:
        self.calls += 1
        self.last_max_pages = max_pages
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
    assert metadata[1:8] == ["00000000", "1", "tok", "1", "1", "20", "2"]
    assert (result.path / ".ehviewer").read_text().splitlines()[-2:] == ["0 p1", "1 p2"]
    assert sorted(p.name for p in result.path.glob("*.jpg")) == ["00000001.jpg", "00000002.jpg"]
    assert "/" not in result.path.name


@pytest.mark.asyncio
async def test_downloader_passes_max_pages_to_fetch_gallery(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    client.calls = 3  # succeed immediately
    await Downloader(client, tmp_path).execute(
        DownloadTask(1, "tok", "title", max_pages=1)
    )
    assert client.last_max_pages == 1


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


@pytest.mark.asyncio
async def test_downloader_speed_stats() -> None:
    client = FakeDownloadClient()
    client.calls = 3
    downloader = Downloader(client, "/tmp/gv-speed-test")
    await downloader._record_bytes(42, 2048, 1)
    await asyncio.sleep(0.05)
    stats = await downloader.speed_stats(42, current_page=1, total_pages=10)
    assert stats is not None
    assert stats["speed"] > 0
    assert stats["eta_seconds"] > 0
    assert await downloader.speed_stats(999) is None
    downloader._clear_stats(42)
    assert await downloader.speed_stats(42) is None


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
        self.local = set()
        self.pruned = []

    async def known_gids(self, favcat: int) -> set[int]:
        return self.known

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        return self.local & set(gids)

    async def remember(self, favcat: int, item: FavoriteData) -> None:
        self.known.add(item.gid)
        self.remembered.append(item.gid)

    async def remember_many(self, favcat: int, items) -> None:
        for item in items:
            await self.remember(favcat, item)

    async def prune(self, favcat: int, current_gids: set[int]) -> int:
        self.pruned.append((favcat, set(current_gids)))
        removed = {gid for gid in self.known if gid not in current_gids}
        self.known -= removed
        return len(removed)

    async def checked(self, favcat: int, success: bool) -> None:
        pass


class FakeFetcher:
    async def fetch_favorites(self, favcat: int, progress=None) -> list[FavoriteData]:
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
async def test_favorites_prunes_stale_items_after_full_check() -> None:
    repo = FakeFavoritesRepo()
    repo.known = {1, 99}  # 99 was unfavorited / expunged on the cloud
    queue = type("Queue", (), {"enqueue": lambda self, item: True})()
    result = await FavoritesService(FakeFetcher(), repo, queue).check_category(
        0, mode="incremental"
    )
    assert result.new == 0 and result.downloaded == 0
    assert repo.pruned[-1] == (0, {1})
    assert repo.known == {1}  # the stale gid 99 is gone


@pytest.mark.asyncio
async def test_telegram_without_token_is_noop() -> None:
    assert not await TelegramNotifier(Settings(telegram_bot_token=None)).send_message("x", "1")


@pytest.mark.asyncio
async def test_favorites_skip_galleries_already_in_local_library() -> None:
    repo = FakeFavoritesRepo()
    repo.local = {1}  # gid 1 already exists locally (e.g. under /Ehviewer)
    queued = []

    async def enqueue(item):
        queued.append(item.gid)
        return True

    queue = type("Queue", (), {"enqueue": enqueue})()
    result = await FavoritesService(FakeFetcher(), repo, queue).check_category(
        0, mode="incremental"
    )
    assert result.new == 0
    assert result.downloaded == 0
    assert queued == []


@pytest.mark.asyncio
async def test_telegram_auto_notification_fans_out_to_all_allowed_chats() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    settings = Settings(telegram_bot_token="secret", telegram_chat_ids=["8", "7"])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notifier = TelegramNotifier(settings, client=client)
        assert await notifier.send_message("auto notice")
        assert len(bodies) == 2
        assert {"chat_id": "7", "text": "auto notice"} in bodies
        assert {"chat_id": "8", "text": "auto notice"} in bodies


@pytest.mark.asyncio
async def test_telegram_auto_notification_without_chats_is_noop() -> None:
    settings = Settings(telegram_bot_token="secret")
    notifier = TelegramNotifier(settings)
    assert not await notifier.send_message("auto notice")


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

        async def send_message(self, text, chat_id=None, force=False):
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
        # Any further gallery sub-page is empty: the gallery has only 2 pages.
        if request.url.path == "/g/7/token/" and request.url.params:
            return httpx.Response(200, text="<html>no more</html>")
        if request.url.path == "/g/7/token/":
            return httpx.Response(
                200,
                text="""<h1 class="gm">A title</h1><div class="gt">artist: alice</div>
                <a href="/s/91ea4b6d89/7-1">one</a><a href="/s/f12f15c685/7-2">two</a>""",
            )
        # Current viewer URL format: /s/<pToken>/<gid>-<page>
        if request.url.path == "/s/91ea4b6d89/7-1":
            return httpx.Response(
                200,
                text='<html><img src="https://img.test/a.jpg" id="img" style="x">'
                '<a href="https://img.test/fullimg-a.jpg">fullimg</a>'
                "<script>var showkey=\"abc123def456\";</script>"
                '<script>onclick="return nl(\'skipkey1\')"</script></html>',
            )
        if request.url.path == "/api.php" and request.method == "POST":
            payload = request.read().decode(errors="replace")
            # gdata sizes the page enumeration; the remaining pages then use the
            # lightweight showpage API.
            if '"gdata"' in payload:
                return httpx.Response(
                    200,
                    json={
                        "gmetadata": [
                            {"gid": 7, "filecount": "2", "token": "token", "title": ""}
                        ]
                    },
                )
            if '"showpage"' in payload and '"page":2' in payload:
                return httpx.Response(
                    200,
                    json={
                        "i3": '<img src="https://img.test/b.jpg" style="width: 1px; height: 1px;">',
                        "i6": '<a href="#" onclick="prompt(\'Copy the URL below.\', \'https://img.test/orig-b.jpg\')">'
                        "<div onclick=\"return nl('skipkey2')\">",
                        "i7": '<a href="https://img.test/fullimg-b.jpg">fullimg</a>',
                    },
                )
            raise AssertionError(request.url)
        raise AssertionError(request.url)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        gallery = await client.fetch_gallery(7, "token")
    assert gallery.title == "A title"
    assert [page.url for page in gallery.pages] == [
        "https://exhentai.org/s/91ea4b6d89/7-1",
        "https://exhentai.org/s/f12f15c685/7-2",
    ]
    # pTokens must be the 10-hex viewer keys written into .ehviewer (fixes the
    # broken legacy regex that left them empty and broke Ehviewer interop).
    assert [page.token for page in gallery.pages] == [
        "91ea4b6d89",
        "f12f15c685",
    ]
    assert [page.image_url for page in gallery.pages] == [
        "https://img.test/a.jpg",
        "https://img.test/b.jpg",
    ]
    assert [page.origin_url for page in gallery.pages] == [
        "https://img.test/fullimg-a.jpg",
        "https://img.test/fullimg-b.jpg",
    ]
    assert [page.skip_hath_key for page in gallery.pages] == ["skipkey1", "skipkey2"]
    assert gallery.tags == [{"namespace": "artist", "name": "alice"}]


@pytest.mark.asyncio
async def test_fetch_gallery_falls_back_to_html_when_showpage_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/g/7/token/":
            if request.url.params:
                return httpx.Response(200, text="<html>no more</html>")
            return httpx.Response(
                200,
                text="""<h1 class="gm">Title</h1>
                <a href="/s/91ea4b6d89/7-1">one</a><a href="/s/f12f15c685/7-2">two</a>""",
            )
        if request.url.path == "/s/91ea4b6d89/7-1":
            return httpx.Response(
                200,
                text='<img src="https://img.test/a.jpg" id="img">'
                "<script>var showkey=\"abc123def456\";</script>",
            )
        if request.url.path == "/s/f12f15c685/7-2":
            return httpx.Response(200, text='<img id="img" src="/images/b.jpg">')
        if request.url.path == "/api.php" and request.method == "POST":
            payload = request.read().decode(errors="replace")
            if '"gdata"' in payload:
                return httpx.Response(
                    200,
                    json={
                        "gmetadata": [
                            {"gid": 7, "filecount": "2", "token": "token", "title": ""}
                        ]
                    },
                )
            # showpage is throttled / stale: the client must degrade to HTML.
            return httpx.Response(200, json={"error": "Key mismatch"})
        raise AssertionError(request.url)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        gallery = await client.fetch_gallery(7, "token")
    assert [page.image_url for page in gallery.pages] == [
        "https://img.test/a.jpg",
        "https://exhentai.org/images/b.jpg",
    ]
    assert [page.token for page in gallery.pages] == ["91ea4b6d89", "f12f15c685"]


@pytest.mark.asyncio
async def test_download_image_streams_with_content_length_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\xff\xd8\xff" + b"x" * 500, headers={"content-type": "image/jpeg"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        eh = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=client)
        data, ctype = await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")
        assert data.startswith(b"\xff\xd8\xff") and ctype == "image/jpeg"


@pytest.mark.asyncio
async def test_download_image_rejects_truncated_and_hijacked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "redirect.jpg" in request.url.path:
            return httpx.Response(302, headers={"location": "https://evil.example/x.jpg"})
        if request.url.host == "evil.example":
            return httpx.Response(200, content=b"\xff\xd8\xff" + b"y" * 100)
        # Content-Length promises 500 bytes but only 10 arrive.
        return httpx.Response(
            200,
            content=b"\xff\xd8\xff" + b"x" * 7,
            headers={"content-type": "image/jpeg", "content-length": "500"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        eh = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=client)
        from galleryvault.services.eh_client import EhClientError

        with pytest.raises(EhClientError, match="redirected to unexpected host"):
            await eh.download_image_with_metadata(
                "https://node.hath.network/h/redirect.jpg"
            )
        with pytest.raises(EhClientError, match="incomplete"):
            await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")


@pytest.mark.asyncio
async def test_fetch_gallery_enumerates_long_galleries_concurrently() -> None:
    """A 40-page gallery spans 2 gallery sub-pages; both must be collected."""
    page1 = "".join(f'<a href="/s/{pt:010x}/7-{i}">x</a>' for i, pt in enumerate(range(20), 1))
    page2 = "".join(f'<a href="/s/{pt:010x}/7-{i}">x</a>' for i, pt in enumerate(range(20, 40), 21))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/g/7/token/":
            if request.url.params.get("p") == "1":
                return httpx.Response(200, text=page2)
            if request.url.params:
                return httpx.Response(200, text="<html>no more</html>")
            return httpx.Response(200, text='<h1 class="gm">Long</h1>' + page1)
        if request.url.path.startswith("/s/"):
            return httpx.Response(
                200,
                text='<img src="https://img.test/x.jpg" id="img">'
                "<script>var showkey=\"abc123def456\";</script>",
            )
        if request.url.path == "/api.php" and request.method == "POST":
            payload = request.read().decode(errors="replace")
            if '"gdata"' in payload:
                return httpx.Response(
                    200,
                    json={
                        "gmetadata": [
                            {"gid": 7, "filecount": "40", "token": "token", "title": ""}
                        ]
                    },
                )
            if '"showpage"' in payload:
                return httpx.Response(
                    200,
                    json={
                        "i3": '<img src="https://img.test/p.jpg" style="x">',
                        "i6": "<div onclick=\"return nl('skipkey')\">",
                        "i7": '<a href="https://img.test/full.jpg">fullimg</a>',
                    },
                )
            raise AssertionError(request.url)
        raise AssertionError(request.url)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        gallery = await client.fetch_gallery(7, "token")
    assert len(gallery.pages) == 40
    assert len({p.token for p in gallery.pages}) == 40
    assert [p.image_url for p in gallery.pages][-1] == "https://img.test/p.jpg"


@pytest.mark.asyncio
async def test_tag_sync_deduplicates_and_replaces_relations() -> None:
    gallery = type("Gallery", (), {"id": 3, "gid": 7, "token": "token"})()

    class Repo:
        async def get_for_tag_sync(self, identifier: int):
            assert identifier == 3
            return gallery

        async def metadata_for_gid(self, gid: int):
            return None  # cold cache: fall through to a live fetch

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

        async def fetch_gallery(
            self, gid: int, token: str, max_pages: int | None = None
        ):
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
async def test_tag_sync_uses_cached_metadata_without_network() -> None:
    gallery = SimpleNamespace(
        id=9, gid=7, token="token", title="Local title", tags_synced_at=None, category=None
    )

    class Repo:
        async def get_for_tag_sync(self, identifier: int):
            return gallery

        async def metadata_for_gid(self, gid: int):
            assert gid == 7
            return {
                "title": "Cached title",
                "category": "doujinshi",
                "tags": [
                    {"namespace": "artist", "name": "alice"},
                    {"namespace": "female", "name": "fox"},
                ],
            }

        async def replace_tags(self, row, tags, synced_at, category=None):
            assert row is gallery and category == "doujinshi"
            assert {(item["namespace"], item["name"]) for item in tags} == {
                ("artist", "alice"),
                ("female", "fox"),
            }
            gallery.tags_synced_at = synced_at
            return 2

    class Client:
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_gallery(
            self, gid: int, token: str, max_pages: int | None = None
        ):  # pragma: no cover
            self.calls += 1
            raise AssertionError("cached metadata must avoid a network fetch")

    client = Client()
    result = await TagSyncService(client, Repo()).sync(9)
    assert result.gid == 7 and result.title == "Cached title" and result.count == 2
    assert gallery.tags_synced_at == result.synced_at
    assert client.calls == 0


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
            # just record the delete statement and capture any GalleryTag
            # inserts (replace_tags now uses a bulk ON CONFLICT insert instead
            # of session.add) for the assertions below.
            from sqlalchemy.sql.expression import Insert

            if isinstance(statement, Insert):
                if getattr(statement.table, "name", "") == "gallery_tags":
                    multi = getattr(statement, "_multi_values", None)
                    single = getattr(statement, "_values", None)
                    rows = multi[0] if multi else ([single] if single else [])
                    for row in rows:
                        vals = {col.name: val for col, val in row.items()}
                        self.added.append(
                            GalleryTag(
                                gallery_id=vals["gallery_id"],
                                tag_id=vals["tag_id"],
                            )
                        )
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


@pytest.mark.asyncio
async def test_pending_category_refresh_returns_ids() -> None:
    class Rows:
        def __iter__(self):
            return iter([(7,), (11,)])

    class Session:
        async def execute(self, statement):
            return Rows()

    result = await GalleryRepository(Session()).pending_category_refresh_ids()
    assert result == [7, 11]


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


def test_thumbnail_service_renders_static_jpeg(tmp_path: Path) -> None:
    from PIL import Image

    from galleryvault.services.thumbnails import ThumbnailService

    buf = _make_jpeg_bytes(640, 900)
    service = ThumbnailService(tmp_path / "thumbs")
    path = service.get_or_create(7, 0, buf)
    assert path.is_file()
    assert service.cached(7, 0) == path
    with Image.open(path) as img:
        assert img.format == "JPEG"
        assert img.size[0] <= 240
    assert service.missing_pages(7, 3) == [1, 2]
    # A second call returns the same cached file without re-rendering.
    path2 = service.get_or_create(7, 0, b"")
    assert path2 == path


def _make_jpeg_bytes(width: int, height: int) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (width, height), (120, 30, 90)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_thumbnail_service_rejects_corrupt_input(tmp_path: Path) -> None:
    import pytest

    from galleryvault.services.thumbnails import ThumbnailError, ThumbnailService

    service = ThumbnailService(tmp_path / "thumbs")
    with pytest.raises(ThumbnailError):
        service.get_or_create(1, 0, b"not-an-image")
