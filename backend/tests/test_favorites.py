"""Unified favorites test suite: worker helpers, sync, skip heuristic, add, move, remove, and notes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self

import httpx
import pytest
from pydantic import ValidationError

from galleryvault.app.schemas import (
    FavoriteNoteRequest,
    FavoritesAddRequest,
    FavoritesMoveRequest,
)
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services import favorites_worker as fw
from galleryvault.services.eh_client import EhClient, EhClientError
from galleryvault.services.favorites_worker import (
    FAVORITES_SKIP_LIMIT,
    FavoriteDownloadQueue,
    FavoritesRepositoryProxy,
    _cover_cache_file,
    _cover_cache_write_path,
    _fav_counts_cache,
    _img_data_uri,
    _parse_gdata_tags,
    _unix_to_iso,
    favorite_counts_cached,
    favorite_size_sync,
    favorites_skip_decision,
    remote_cover_data_batch,
    run_favorites_check,
)

# ==============================================================================
# 1. Pure Helper & Tag Parsing Tests
# ==============================================================================


def test_unix_to_iso() -> None:
    assert _unix_to_iso(None) is None
    assert _unix_to_iso("invalid") is None
    res = _unix_to_iso(1600000000)
    assert res is not None
    assert "2020" in res


def test_parse_gdata_tags() -> None:
    tags = ["artist:michiking", "group:circle", "female:sole female", "nonamespace"]
    parsed = _parse_gdata_tags(tags)
    assert parsed == [
        ("artist", "michiking"),
        ("group", "circle"),
        ("female", "sole female"),
        ("misc", "nonamespace"),
    ]


def test_parse_gdata_tags_accepts_metadata_map_dicts() -> None:
    parsed = _parse_gdata_tags(
        [
            {"namespace": "artist", "name": "alice"},
            {"namespace": "misc", "name": "twintails"},
            {"namespace": "", "name": ""},
            ["language", "chinese"],
            ("group", "circle"),
            "female:sole female",
            "nonamespace",
            None,
            123,
        ]
    )
    assert parsed == [
        ("artist", "alice"),
        ("misc", "twintails"),
        ("language", "chinese"),
        ("group", "circle"),
        ("female", "sole female"),
        ("misc", "nonamespace"),
    ]


def test_cover_cache_file_prefers_img(tmp_path: Path) -> None:
    gid = 42
    jpg = tmp_path / f"{gid}.jpg"
    img = tmp_path / f"{gid}.img"
    jpg.write_bytes(b"jpg")
    assert _cover_cache_file(tmp_path, gid) == jpg
    img.write_bytes(b"img")
    assert _cover_cache_file(tmp_path, gid) == img
    assert _cover_cache_write_path(tmp_path, gid) == img
    assert _cover_cache_file(tmp_path, 99) is None


@pytest.mark.asyncio
async def test_remote_cover_batch_uses_img_or_jpg_without_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    (tmp_path / "1.img").write_bytes(b"\xff\xd8\xff" + b"a" * 8)
    (tmp_path / "2.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    orig = app_state.eh_client
    app_state.eh_client = object()
    try:
        result = await remote_cover_data_batch(
            [(1, "tok"), (2, "tok"), (3, "tok")],
            {1: {"thumb": "http://x/1"}, 2: {"thumb": "http://x/2"}, 3: {"thumb": "http://x/3"}},
            download=False,
        )
        assert 1 in result and result[1].startswith("data:image/jpeg")
        assert 2 in result and result[2].startswith("data:image/png")
        assert 3 not in result
        assert not (tmp_path / "3.img").exists()
    finally:
        app_state.eh_client = orig


@pytest.mark.asyncio
async def test_remote_cover_batch_writes_img_not_jpg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    downloaded = []

    class Client:
        async def download_image(self, url: str) -> bytes:
            downloaded.append(url)
            return b"\xff\xd8\xff" + b"x" * 20

    orig = app_state.eh_client
    app_state.eh_client = Client()
    try:
        result = await remote_cover_data_batch(
            [(9, "tok")],
            {9: {"thumb": "http://ehgt.org/9"}},
            download=True,
            encode=False,
        )
        assert result == {}
        assert downloaded == ["http://ehgt.org/9"]
        assert (tmp_path / "9.img").is_file()
        assert not (tmp_path / "9.jpg").exists()
    finally:
        app_state.eh_client = orig


def test_img_data_uri() -> None:
    assert _img_data_uri(b"") is None
    png_data = b"\x89PNG\r\n\x1a\n" + b"rest"
    assert _img_data_uri(png_data).startswith("data:image/png;base64,")
    jpg_data = b"\xff\xd8\xff\xe0" + b"rest"
    assert _img_data_uri(jpg_data).startswith("data:image/jpeg;base64,")
    gif_data = b"GIF89a" + b"rest"
    assert _img_data_uri(gif_data).startswith("data:image/gif;base64,")


# ==============================================================================
# 2. Worker Repositories, Proxy & Download Queue
# ==============================================================================


@pytest.mark.asyncio
async def test_favorites_repo_proxy_methods() -> None:
    orig_session = app_state.session_factory
    try:

        class FakeRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def known_gids(self, favcat: int) -> set[int]:
                return {1, 2}

            async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
                return {1}

            async def remember(self, favcat: int, item: Any) -> bool:
                return True

            async def remember_many(self, favcat: int, items: list[Any]) -> int:
                return len(items)

            async def prune(self, favcat: int, current_gids: set[int]) -> int:
                return 0

            async def checked(self, favcat: int, success: bool) -> None:
                pass

            async def category(self, favcat: int) -> SimpleNamespace:
                return SimpleNamespace(favcat=favcat, name="Fav")

        class FakeSession:
            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

            def begin(self) -> FakeSession:
                return self

        app_state.session_factory = lambda: FakeSession()
        from unittest.mock import patch

        with patch("galleryvault.services.favorites_worker.FavoritesRepository", FakeRepo):
            proxy = FavoritesRepositoryProxy()
            assert await proxy.known_gids(0) == {1, 2}
            assert await proxy.existing_gallery_gids([1, 2, 3]) == {1}
            assert await proxy.remember(0, SimpleNamespace(gid=1)) is True
            assert await proxy.remember_many(0, [SimpleNamespace(gid=1)]) == 1
            assert await proxy.prune(0, {1}) == 0
            assert (await proxy.category(0)).name == "Fav"
    finally:
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_favorite_download_queue() -> None:
    orig_session = app_state.session_factory
    try:

        class FakeDownloadRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def create(self, gid: int, token: str, title: str, mode: str, quality: Any = None, title_jpn: Any = None) -> SimpleNamespace:
                return SimpleNamespace(id=42)

        class FakeSession:
            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

            def begin(self) -> FakeSession:
                return self

        app_state.session_factory = lambda: FakeSession()
        attached = []

        class FakeUpdatesRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def attach_download(self, new_gid: int, task_id: int) -> int:
                attached.append((new_gid, task_id))
                return 1

        from unittest.mock import patch

        with (
            patch("galleryvault.services.favorites_worker.DownloadRepository", FakeDownloadRepo),
            patch("galleryvault.services.favorites_worker.GalleryUpdatesRepository", FakeUpdatesRepo),
        ):
            queue = FavoriteDownloadQueue()
            item = SimpleNamespace(gid=123, token="tok", title="Title")
            assert await queue.enqueue(item) is True
            assert attached == [(123, 42)]
    finally:
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_favorite_counts_cached_wait_on_cold_concurrent() -> None:
    call_count = 0

    class FakeEhClient:
        async def fetch_favorite_counts(self) -> dict[int, int]:
            nonlocal call_count
            call_count += 1
            return {0: 10, 1: 20}

    orig_client = app_state.eh_client
    app_state.eh_client = FakeEhClient()
    _fav_counts_cache["ts"] = 0.0
    _fav_counts_cache["counts"] = {}
    try:
        import asyncio

        results = await asyncio.gather(
            favorite_counts_cached(wait_on_cold=True),
            favorite_counts_cached(wait_on_cold=True),
            favorite_counts_cached(wait_on_cold=True),
        )
        assert call_count == 1
        assert results == [{0: 10, 1: 20}, {0: 10, 1: 20}, {0: 10, 1: 20}]
    finally:
        app_state.eh_client = orig_client
        _fav_counts_cache["ts"] = 0.0
        _fav_counts_cache["counts"] = {}


@pytest.mark.asyncio
async def test_favorite_counts_cached_cancelled_caller_shares_task() -> None:
    call_count = 0

    class FakeEhClient:
        async def fetch_favorite_counts(self) -> dict[int, int]:
            nonlocal call_count
            call_count += 1
            import asyncio

            await asyncio.sleep(0.08)
            return {0: 99}

    orig_client = app_state.eh_client
    app_state.eh_client = FakeEhClient()
    _fav_counts_cache["ts"] = 0.0
    _fav_counts_cache["counts"] = {}
    try:
        import asyncio

        t1 = asyncio.create_task(favorite_counts_cached(wait_on_cold=True))
        await asyncio.sleep(0.01)
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1

        res2 = await favorite_counts_cached(wait_on_cold=True)
        assert res2 == {0: 99}
        assert call_count == 1
    finally:
        app_state.eh_client = orig_client
        _fav_counts_cache["ts"] = 0.0
        _fav_counts_cache["counts"] = {}


@pytest.mark.asyncio
async def test_favorite_size_sync_heals_missing_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    (tmp_path / "2.img").write_bytes(b"cached")
    downloaded: list[str] = []

    class Client:
        async def fetch_gmetadata(self, pairs: Any) -> dict[int, Any]:
            return {}

        async def download_image(self, url: str) -> bytes:
            downloaded.append(url)
            return b"\xff\xd8\xff" + b"x" * 20

    class FavRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def all_gids_for_favcat(self, favcat: int) -> list[tuple[int, str, str | None]]:
            return [
                (1, "tok1", "http://ehgt.org/1"),
                (2, "tok2", "http://ehgt.org/2"),
                (3, "tok3", None),
            ]

        async def set_file_size(self, *args: Any, **kwargs: Any) -> None:
            pass

    class GalRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def seed_metadata_from_galleries(self, favcat: int) -> int:
            return 0

        async def metadata_map(self, gids: Any) -> dict[int, Any]:
            return {}

        async def null_image_quality_gids(self, gids: Any) -> set[int]:
            return set()

        async def upsert_metadata(self, entries: Any) -> int:
            return 0

        async def storage_size_map(self, gids: Any) -> dict[int, Any]:
            return {}

        async def set_image_qualities(self, mapping: Any) -> int:
            return 0

        async def apply_metadata_to_galleries(self, favcat: int, limit: int = 200) -> int:
            return 0

    class Session:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def begin(self) -> Session:
            return self

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    try:
        app_state.session_factory = lambda: Session()
        app_state.eh_client = Client()
        monkeypatch.setattr(fw, "FavoritesRepository", FavRepo)
        monkeypatch.setattr(fw, "GalleryRepository", GalRepo)
        fw._size_sync_inflight.clear()
        await favorite_size_sync(4)
        assert downloaded == ["http://ehgt.org/1"]
        assert (tmp_path / "1.img").is_file()
        assert not (tmp_path / "3.img").exists()
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()


@pytest.mark.asyncio
async def test_favorite_size_sync_applies_metadata_infers_quality_and_records_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    qualities: dict[int, str] = {}
    applied_calls: list[int] = []

    class Client:
        async def fetch_gmetadata(self, pairs: Any) -> dict[int, Any]:
            return {int(gid): {"file_size": 1000, "thumb": ""} for gid, _tok in pairs}

        async def download_image(self, url: str) -> bytes:
            return b""

    class FavRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def all_gids_for_favcat(self, favcat: int) -> list[tuple[int, str, None]]:
            return [(10, "tok", None)]

        async def set_file_size(self, *args: Any, **kwargs: Any) -> None:
            pass

    class GalRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def seed_metadata_from_galleries(self, favcat: int) -> int:
            return 0

        async def metadata_map(self, gids: Any) -> dict[int, Any]:
            return {}

        async def null_image_quality_gids(self, gids: Any) -> set[int]:
            return set()

        async def upsert_metadata(self, entries: Any) -> int:
            return len(entries)

        async def storage_size_map(self, gids: Any) -> dict[int, Any]:
            return {10: (950, None)}

        async def set_image_qualities(self, mapping: dict[int, str]) -> int:
            qualities.update(mapping)
            return len(mapping)

        async def apply_metadata_to_galleries(self, favcat: int, limit: int = 200) -> int:
            applied_calls.append(limit)
            return 3 if len(applied_calls) == 1 else 0

    class Session:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def begin(self) -> Session:
            return self

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    tm = app_state.task_manager
    before = len(tm.task_history)
    try:
        app_state.session_factory = lambda: Session()
        app_state.eh_client = Client()
        monkeypatch.setattr(fw, "FavoritesRepository", FavRepo)
        monkeypatch.setattr(fw, "GalleryRepository", GalRepo)
        fw._size_sync_inflight.clear()
        tm.metadata_sync_state["history_recorded"] = False
        await favorite_size_sync(1)
        assert qualities == {10: "original"}
        assert applied_calls == [200, 200]
        assert tm.task_history[0]["task"] == "metadata"
        assert tm.task_history[0]["status"] == "success"
        assert len(tm.task_history) == before + 1
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()
        if tm.task_history and tm.task_history[0].get("task") == "metadata":
            tm.task_history.pop(0)


@pytest.mark.asyncio
async def test_favorite_size_sync_fetches_gdata_when_seeded_metadata_lacks_file_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    fetched_pairs: list[tuple[int, str]] = []
    qualities: dict[int, str] = {}

    class Client:
        async def fetch_gmetadata(self, pairs: Any) -> dict[int, Any]:
            fetched_pairs.extend((int(gid), tok) for gid, tok in pairs)
            return {int(gid): {"file_size": 1000, "thumb": ""} for gid, tok in pairs}

        async def download_image(self, url: str) -> bytes:
            return b""

    class FavRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def all_gids_for_favcat(self, favcat: int) -> list[tuple[int, str, None]]:
            return [(10, "tok", None)]

        async def set_file_size(self, *args: Any, **kwargs: Any) -> None:
            pass

    class GalRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def seed_metadata_from_galleries(self, favcat: int) -> int:
            return 1

        async def metadata_map(self, gids: Any) -> dict[int, Any]:
            return {10: {"file_size": None, "title": "seeded"}}

        async def null_image_quality_gids(self, gids: Any) -> set[int]:
            return {10}

        async def upsert_metadata(self, entries: Any) -> int:
            return len(entries)

        async def storage_size_map(self, gids: Any) -> dict[int, Any]:
            return {10: (950, None)}

        async def set_image_qualities(self, mapping: dict[int, str]) -> int:
            qualities.update(mapping)
            return len(mapping)

        async def apply_metadata_to_galleries(self, favcat: int, limit: int = 200) -> int:
            return 0

    class Session:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def begin(self) -> Session:
            return self

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    tm = app_state.task_manager
    try:
        app_state.session_factory = lambda: Session()
        app_state.eh_client = Client()
        monkeypatch.setattr(fw, "FavoritesRepository", FavRepo)
        monkeypatch.setattr(fw, "GalleryRepository", GalRepo)
        fw._size_sync_inflight.clear()
        tm.metadata_sync_state["history_recorded"] = False
        await favorite_size_sync(1)
        assert fetched_pairs == [(10, "tok")]
        assert qualities == {10: "original"}
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()
        if tm.task_history and tm.task_history[0].get("task") == "metadata":
            tm.task_history.pop(0)


# ==============================================================================
# 3. Skip Heuristics Tests
# ==============================================================================


def test_skip_decision_skips_until_limit_then_forces_full() -> None:
    counter = 0
    for _ in range(FAVORITES_SKIP_LIMIT - 1):
        should_skip, counter = favorites_skip_decision(
            counter, scheduled=True, category_ready=True, live_count=10, known=10
        )
        assert should_skip is True
    should_skip, counter = favorites_skip_decision(
        counter, scheduled=True, category_ready=True, live_count=10, known=10
    )
    assert should_skip is False and counter == 0


@pytest.mark.parametrize(
    "start_counter, scheduled, category_ready, live_count, known",
    [
        (3, False, True, 10, 10),
        (0, True, False, 10, 10),
        (4, True, True, 11, 10),
        (2, True, True, 0, 0),
    ],
)
def test_skip_decision_never_skips_on_condition(
    start_counter: int, scheduled: bool, category_ready: bool, live_count: int, known: int
) -> None:
    should_skip, next_count = favorites_skip_decision(
        start_counter,
        scheduled=scheduled,
        category_ready=category_ready,
        live_count=live_count,
        known=known,
    )
    assert should_skip is False
    assert next_count == 0


class _FakeFavoritesSession:
    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    def begin(self) -> _FakeFavoritesSession:
        return self

    async def scalar(self, statement: Any) -> int | None:
        from sqlalchemy.dialects import postgresql

        sql = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        if "categories" in sql:
            return 10
        return None

    async def execute(self, statement: Any) -> Any:
        class _Result:
            def scalars(self) -> _Result:
                return self

            def first(self) -> None:
                return None

            def all(self) -> list[Any]:
                return []

        return _Result()

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_run_favorites_check_forces_full_pass_after_five_skips() -> None:
    monkeypatch = pytest.MonkeyPatch()
    tm = app_state.task_manager
    original_state = tm.favorites_check_state
    tm.favorites_check_state = {
        "running": False,
        "categories": {},
        "last_error": None,
        "started_at": None,
        "completed_at": None,
        "history_recorded": False,
        "skip_counts": {},
    }

    full_checks = []

    class Repo:
        async def category(self, favcat: int) -> SimpleNamespace:
            return SimpleNamespace(
                favcat=favcat,
                last_success_at=object(),
                enabled=True,
                mode="incremental",
                poll_interval_seconds=3600,
                last_checked_at=None,
            )

        async def count_known_gids(self, favcat: int) -> int:
            return 10

        async def checked(self, favcat: int, success: bool) -> None:
            pass

    class Service:
        async def check_category(
            self,
            favcat: int,
            mode: str = "incremental",
            progress: Any = None,
            archive_enabled: bool = False,
            archive_max_pages: int = 0,
            archive_quality: str = "resample",
        ) -> None:
            full_checks.append(favcat)

    orig_factory = app_state.session_factory
    spawned: list[str] = []

    def fake_spawn(coro: Any, operation: str) -> None:
        spawned.append(operation)
        if hasattr(coro, "close"):
            coro.close()

    try:
        async def _fake_counts(*a: Any, **k: Any) -> dict[int, int]:
            return {3: 10}

        app_state.session_factory = lambda: _FakeFavoritesSession(Repo())
        app_state.favorites_service = Service()
        monkeypatch.setattr(fw, "FavoritesRepository", lambda session: session._repo)
        monkeypatch.setattr(fw, "favorite_counts_cached", _fake_counts)
        monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", fake_spawn)
        monkeypatch.setattr(tm, "record_task", lambda *a, **k: None)

        for _ in range(5):
            await run_favorites_check(3, Service(), scheduled=True)
        assert full_checks == [3], "the 5th scheduled poll must run a full pass"
        assert tm.favorites_check_state["skip_counts"] == {"3": 0}
        assert "favorite size sync 3" in spawned
    finally:
        tm.favorites_check_state = original_state
        app_state.session_factory = orig_factory
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_favorites_check_failure_checked_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    checked_calls = []

    class FailingService:
        async def check_category(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("upstream network failure")

    class MockRepo:
        async def checked(self, favcat: int, success: bool) -> None:
            checked_calls.append((favcat, success))

    async def _fake_counts_1(*a: Any, **k: Any) -> dict[int, int]:
        return {1: 10}

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: _FakeFavoritesSession(MockRepo())

    try:
        monkeypatch.setattr(fw, "FavoritesRepository", lambda session: session._repo)
        monkeypatch.setattr(fw, "favorite_counts_cached", _fake_counts_1)
        await fw._run_favorites_check_inner(
            favcat=1,
            service=FailingService(),
            scheduled=False,
        )
        assert checked_calls == [(1, False)]
    finally:
        app_state.session_factory = orig_factory


# ==============================================================================
# 4. Add Favorites (Client + API Endpoint)
# ==============================================================================


def _add_handler(*, fail_gids: set[int] | None = None, auth_fail: bool = False) -> tuple[Any, list[Any]]:
    if fail_gids is None:
        fail_gids = set()
    requests: list[tuple[str, str, dict[str, list[str]]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        parsed = parse_qs(request.content.decode(errors="replace"))
        url_path = str(request.url)
        requests.append((request.method, url_path, parsed))

        if auth_fail:
            return httpx.Response(401, text="Must be logged in")

        import re

        match = re.search(r"gid=(\d+)", url_path)
        gid = int(match.group(1)) if match else None
        if gid and gid in fail_gids:
            return httpx.Response(500, text="cloud error")
        return httpx.Response(200, text="<html><body>Updated</body></html>")

    return handler, requests


@pytest.mark.asyncio
async def test_add_favorite_sends_correct_payload() -> None:
    handler, requests = _add_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        await client.add_favorite(12345, "abcdef", 3, note="test note")

    assert len(requests) == 1
    method, url, form = requests[0]
    assert method == "POST"
    assert "gid=12345" in url
    assert "t=abcdef" in url
    assert "act=addfav" in url
    assert form["favcat"] == ["3"]
    assert form["favnote"] == ["test note"]
    assert form["update"] == ["1"]
    assert form["submit"] == ["Apply Changes"]


@pytest.mark.asyncio
async def test_add_favorites_batch_returns_failed_gids() -> None:
    handler, requests = _add_handler(fail_gids={200})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.add_favorites([(100, "tok1"), (200, "tok2"), (300, "tok3")], favcat=2)

    assert failed == [200]
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_add_favorites_auth_keeps_prior_successes() -> None:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import re

        match = re.search(r"gid=(\d+)", str(request.url))
        gid = int(match.group(1)) if match else 0
        seen.append(gid)
        if gid == 100:
            return httpx.Response(200, text="<html><body>Updated</body></html>")
        return httpx.Response(401, text="Must be logged in")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.add_favorites([(100, "tok1"), (200, "tok2"), (300, "tok3")], favcat=2)
    assert failed == [200, 300]
    assert seen == [100, 200]


@pytest.mark.asyncio
async def test_add_favorites_mid_loop_abort_keeps_successes() -> None:
    seen: list[int] = []

    class BoomItems(list):
        def __iter__(self) -> Any:
            for i, item in enumerate(list.__iter__(self)):
                if i == 1:
                    raise RuntimeError("loop boom")
                yield item

    def handler(request: httpx.Request) -> httpx.Response:
        import re

        match = re.search(r"gid=(\d+)", str(request.url))
        gid = int(match.group(1)) if match else 0
        seen.append(gid)
        return httpx.Response(200, text="<html><body>Updated</body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.add_favorites(
            BoomItems([(100, "tok1"), (200, "tok2"), (300, "tok3")]), favcat=2
        )
    assert failed == [200, 300]
    assert 100 not in failed
    assert seen == [100]


@pytest.mark.asyncio
async def test_add_favorite_auth_failure_raises() -> None:
    handler, _ = _add_handler(auth_fail=True)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        with pytest.raises(EhClientError):
            await client.add_favorite(100, "tok", 1)


def test_favorites_add_request_schema() -> None:
    req = FavoritesAddRequest(gid=123, token="abc", target_favcat=4, note="hello")
    assert req.items == [{"gid": 123, "token": "abc", "note": "hello"}]

    req_multi = FavoritesAddRequest(
        target_favcat=5,
        items=[{"gid": 1, "token": "t1"}, {"gid": 2, "token": "t2"}],
    )
    assert len(req_multi.items) == 2

    with pytest.raises(ValidationError):
        FavoritesAddRequest(target_favcat=10)


@pytest.mark.asyncio
async def test_favorites_add_endpoint_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers.favorites import favorites_add

    class DummySession:
        def begin(self) -> DummySession:
            return self

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def scalars(self, stmt: Any) -> DummySession:
            return self

        def all(self) -> list[Any]:
            return []

    async def dummy_get_session() -> Any:
        yield DummySession()

    remembered: list[Any] = []

    class DummyRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def remember_many(self, favcat: int, items: list[Any]) -> None:
            remembered.extend((favcat, items))

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            return len(gids)

    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    # 1. Happy path
    class HappyClient:
        async def add_favorites(self, pairs: Any, target_favcat: int, note: str = "") -> list[int]:
            return []

    monkeypatch.setattr("galleryvault.app.routers.favorites.app_state.eh_client", HappyClient())
    res = await favorites_add(FavoritesAddRequest(gid=999, token="tok999", target_favcat=3))
    assert res["target_favcat"] == 3
    assert res["cloud_ok"] is True
    assert res["successful_gids"] == [999]
    assert res["local_added"] == 1
    assert len(remembered) == 2

    # 2. Cloud failure does not mutate DB
    remembered.clear()

    class FailClient:
        async def add_favorites(self, pairs: Any, target_favcat: int, note: str = "") -> list[int]:
            return [999]

    monkeypatch.setattr("galleryvault.app.routers.favorites.app_state.eh_client", FailClient())
    res_fail = await favorites_add(FavoritesAddRequest(gid=999, token="tok999", target_favcat=3))
    assert res_fail["cloud_ok"] is False
    assert res_fail["cloud_failed"] == [999]
    assert res_fail["successful_gids"] == []
    assert res_fail["local_added"] == 0
    assert len(remembered) == 0

    # 3. Exception does not treat unconfirmed as success
    class BoomClient:
        async def add_favorites(self, pairs: Any, target_favcat: int, note: str = "") -> list[int]:
            raise RuntimeError("boom")

    monkeypatch.setattr("galleryvault.app.routers.favorites.app_state.eh_client", BoomClient())
    res_boom = await favorites_add(FavoritesAddRequest(gid=999, token="tok999", target_favcat=3))
    assert res_boom["cloud_ok"] is False
    assert res_boom["cloud_failed"] == [999]
    assert res_boom["successful_gids"] == []
    assert res_boom["local_added"] == 0
    assert len(remembered) == 0


def test_record_favorites_add_log(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_add_log

    entries: list[dict[str, Any]] = []

    class DummyTM:
        def record_task(
            self,
            kind: str,
            start: Any,
            finish: Any,
            status: str,
            reason: str = "",
            done: int = 0,
            total: int = 0,
        ) -> None:
            entries.append(
                {"kind": kind, "status": status, "reason": reason, "done": done, "total": total}
            )

        async def persist_history(self) -> None:
            pass

    monkeypatch.setattr("galleryvault.app.routers.favorites.get_task_manager", lambda: DummyTM())

    _record_favorites_add_log([1, 2], 3, [], 2)
    assert len(entries) == 1
    assert entries[0]["kind"] == "favorites-add"
    assert entries[0]["status"] == "success"
    assert "added 2 to #3" in entries[0]["reason"]

    _record_favorites_add_log([1, 2, 3], 4, [3], 2)
    assert len(entries) == 2
    assert entries[1]["status"] == "failed"
    assert "cloud add failed 1" in entries[1]["reason"]


# ==============================================================================
# 5. Move Favorites (Client + API Endpoint)
# ==============================================================================


def _move_handler(*, fail_gids: tuple[int, ...] = (), bad_batch: tuple[int, ...] = ()) -> tuple[Any, list[Any]]:
    requests: list[tuple[str, str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        parsed = parse_qs(request.content.decode(errors="replace"))
        modify = [v for v in parsed.get("modifygids[]", [])]
        ddact = parsed.get("ddact", [""])[0]
        requests.append((request.method, ddact, modify))
        if any(g in bad_batch for g in [int(g) for g in modify]):
            return httpx.Response(500, text="boom")
        if any(int(g) in fail_gids for g in modify):
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text="ok")

    return handler, requests


@pytest.mark.asyncio
async def test_move_favorites_sends_correct_payload() -> None:
    handler, requests = _move_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites([10, 20], target_favcat=3)

    assert failed == []
    assert len(requests) == 1
    method, ddact, modify = requests[0]
    assert method == "POST"
    assert ddact == "fav3"
    assert modify == ["10", "20"]


@pytest.mark.asyncio
async def test_move_favorites_chunks_over_25() -> None:
    handler, requests = _move_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites(list(range(1, 60)), target_favcat=5)

    assert failed == []
    assert len(requests) == 3
    assert [len(r[2]) for r in requests] == [25, 25, 9]
    assert all(r[1] == "fav5" for r in requests)


@pytest.mark.asyncio
async def test_move_favorites_returns_failed_gids() -> None:
    handler, requests = _move_handler(fail_gids=(7,))
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites([1, 7, 9], target_favcat=2)

    assert failed == [7]
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_move_favorites_bad_batch_degrades_to_per_gid() -> None:
    handler, _requests = _move_handler(bad_batch=(1, 7, 9))
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites([1, 7, 9], target_favcat=1)

    assert failed == [1, 7, 9]


@pytest.mark.asyncio
async def test_move_favorites_empty_is_noop() -> None:
    handler, requests = _move_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        assert await client.move_favorites([], target_favcat=0) == []
    assert requests == []


@pytest.mark.asyncio
async def test_move_favorites_validation_and_auth() -> None:
    client = EhClient(Settings(exhentai_base_url="https://exhentai.org"))
    with pytest.raises(ValueError):
        await client.move_favorites([1], target_favcat=-1)
    with pytest.raises(ValueError):
        await client.move_favorites([1], target_favcat=10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="login required")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        with pytest.raises(EhClientError):
            await client.move_favorites([1], target_favcat=2)


def test_favorites_move_request_schema() -> None:
    req = FavoritesMoveRequest(gids=[1, 2, 3], target_favcat=4)
    assert req.gids == [1, 2, 3]
    assert req.target_favcat == 4

    req2 = FavoritesMoveRequest(items=[{"gid": "123"}, {"gid": 456}], target_favcat=0)
    assert req2.gids == [123, 456]
    assert req2.target_favcat == 0

    with pytest.raises(ValidationError):
        FavoritesMoveRequest(gids=[1], target_favcat=-1)
    with pytest.raises(ValidationError):
        FavoritesMoveRequest(gids=[1], target_favcat=10)


@pytest.mark.asyncio
async def test_favorites_move_endpoint_happy_and_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers.favorites import favorites_move

    class DummySession:
        def begin(self) -> DummySession:
            return self

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    async def dummy_get_session() -> Any:
        yield DummySession()

    moved_locally: list[int] = []

    class DummyRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            moved_locally.extend(gids)
            return len(gids)

    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    # 1. Happy path
    class HappyClient:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            return []

    monkeypatch.setattr(app_state, "eh_client", HappyClient())
    res = await favorites_move(FavoritesMoveRequest(gids=[100, 200], target_favcat=3))
    assert res["cloud_ok"] is True
    assert res["cloud_moved"] == 2
    assert res["cloud_failed"] == []
    assert res["local_moved"] == 2
    assert res["target_favcat"] == 3

    # 2. Partial cloud failure
    moved_locally.clear()

    class PartialClient:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            return [200]

    monkeypatch.setattr(app_state, "eh_client", PartialClient())
    res_partial = await favorites_move(FavoritesMoveRequest(gids=[100, 200], target_favcat=3))
    assert res_partial["cloud_ok"] is False
    assert res_partial["cloud_moved"] == 1
    assert res_partial["cloud_failed"] == [200]
    assert res_partial["local_moved"] == 1
    assert moved_locally == [100]


def test_record_favorites_move_log(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_move_log

    entries: list[dict[str, object]] = []

    def record(kind: str, start: Any, end: Any, status: str, *, reason: str = "", done: int = 0, total: int = 0) -> None:
        entries.append(
            {"kind": kind, "status": status, "reason": reason, "done": done, "total": total}
        )

    monkeypatch.setattr(app_state.task_manager, "record_task", record)

    _record_favorites_move_log([1, 2], 3, [], 2)
    assert entries[0]["kind"] == "favorites-move"
    assert entries[0]["status"] == "success"
    assert entries[0]["reason"] == "moved 2 to #3"
    assert entries[0]["done"] == 2
    assert entries[0]["total"] == 2

    _record_favorites_move_log([1, 2, 3], 4, [3], 2)
    assert entries[1]["status"] == "failed"
    assert "moved 2 to #4" in str(entries[1]["reason"])
    assert "cloud move failed 1: 3" in str(entries[1]["reason"])


# ==============================================================================
# 6. Remove Favorites
# ==============================================================================


def _remove_handler(*, fail_gids: tuple[int, ...] = (), bad_batch: tuple[int, ...] = ()) -> tuple[Any, list[Any]]:
    requests: list[tuple[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        parsed = parse_qs(request.content.decode(errors="replace"))
        modify = [v for v in parsed.get("modifygids[]", [])]
        requests.append((request.method, modify))
        if any(g in bad_batch for g in [int(g) for g in modify]):
            return httpx.Response(500, text="boom")
        if any(int(g) in fail_gids for g in modify):
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text="ok")

    return handler, requests


@pytest.mark.asyncio
async def test_remove_favorites_chunks_over_25() -> None:
    handler, requests = _remove_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.remove_favorites(list(range(1, 60)))

    assert failed == []
    assert len(requests) == 3
    assert [len(r[1]) for r in requests] == [25, 25, 9]
    assert all(g in r[1] for r in requests for g in r[1])


@pytest.mark.asyncio
async def test_remove_favorites_returns_failed_gids() -> None:
    handler, requests = _remove_handler(fail_gids=(7,))
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.remove_favorites([1, 7, 9])

    assert failed == [7]
    assert len(requests) == 4
    assert requests[0][1] == ["1", "7", "9"]
    assert [g for _, batch in requests[1:] for g in batch] == ["1", "7", "9"]


@pytest.mark.asyncio
async def test_remove_favorites_bad_batch_degrades_to_per_gid() -> None:
    handler, requests = _remove_handler(bad_batch=(1, 7, 9))
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.remove_favorites([1, 7, 9])

    assert failed == [1, 7, 9]
    assert requests[0][1] == ["1", "7", "9"]
    assert [r[1][0] for r in requests[1:]] == ["1", "7", "9"]


@pytest.mark.asyncio
async def test_remove_favorites_empty_and_auth_failure() -> None:
    handler, requests = _remove_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        assert await client.remove_favorites([]) == []
    assert requests == []

    def auth_fail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="login required")

    transport_fail = httpx.MockTransport(auth_fail_handler)
    async with httpx.AsyncClient(base_url="https://exhentai.org", transport=transport_fail) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        with pytest.raises(EhClientError):
            await client.remove_favorites([1])


def test_record_favorites_remove_log(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_remove_log

    entries: list[dict[str, object]] = []

    def record(kind: str, start: Any, end: Any, status: str, *, reason: str = "", done: int = 0, total: int = 0) -> None:
        entries.append(
            {"kind": kind, "status": status, "reason": reason, "done": done, "total": total}
        )

    monkeypatch.setattr(app_state.task_manager, "record_task", record)

    _record_favorites_remove_log([1, 2, 3], 2, [], [3])
    assert entries[0]["kind"] == "favorites-remove"
    assert entries[0]["status"] == "failed"
    assert "cloud remove failed 1: 3" in str(entries[0]["reason"])
    assert entries[0]["total"] == 3

    _record_favorites_remove_log([1, 2, 3], 3, [], [])
    assert entries[1]["status"] == "success"
    assert "cloud remove failed" not in str(entries[1]["reason"])

    reasons: list[str] = []

    def record_reason(kind: str, start: Any, end: Any, status: str, *, reason: str = "", done: int = 0, total: int = 0) -> None:
        reasons.append(reason)

    monkeypatch.setattr(app_state.task_manager, "record_task", record_reason)
    _record_favorites_remove_log([], 0, [], list(range(1, 20)))
    assert "cloud remove failed 19: 1, 2, 3, 4, 5" in reasons[0]
    assert "(+14 more)" in reasons[0]


# ==============================================================================
# 7. Favorite Notes
# ==============================================================================


@pytest.mark.asyncio
async def test_favorite_note_cloud_failure_does_not_write_local(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class BoomClient:
        async def add_favorite(self, *args: Any, **kwargs: Any) -> None:
            raise EhClientError("cloud down")

    class Repo:
        def __init__(self, session: Any) -> None:
            self.session = session
            self.updated = 0

        async def item_for_gid(self, gid: int) -> SimpleNamespace:
            return SimpleNamespace(token="tok", favcat=2, gid=gid)

        async def update_note(self, gid: int, note: str, favcat: Any = None) -> int:
            self.updated += 1
            return 1

    updates = {"n": 0}

    class Session:
        async def begin(self) -> Session:
            return self

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def scalar(self, statement: Any) -> None:
            return None

    async def fake_session() -> Any:
        yield Session()

    orig = app_state.eh_client
    app_state.eh_client = BoomClient()
    monkeypatch.setattr(fav_mod, "get_session", fake_session)
    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)

    def fake_record(*args: Any, **kwargs: Any) -> None:
        updates["n"] += 1

    monkeypatch.setattr(
        fav_mod,
        "get_task_manager",
        lambda: SimpleNamespace(record_task=fake_record, persist_history=lambda: None),
    )
    monkeypatch.setattr(fav_mod, "spawn_task", lambda *a, **k: None)
    try:
        result = await fav_mod.favorites_set_note(
            FavoriteNoteRequest(gid=11, note="secret", token="tok", favcat=2)
        )
        assert result["cloud_ok"] is False
        assert result["local_updated"] == 0
        assert result["note"] is None
    finally:
        app_state.eh_client = orig
