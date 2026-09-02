"""Regression tests for the 2026-09-03 review-fix batch."""

from __future__ import annotations

from types import SimpleNamespace

from galleryvault.db.repositories.favorites import FavoritesRepository
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.db.repositories.updates import GalleryUpdatesRepository
from galleryvault.services.download_prepare import MAX_FOLLOW_HOPS, _resolve_one
from galleryvault.services.downloader import DownloadTask, raise_if_replaced
from galleryvault.services.eh_client import GalleryData, GalleryGoneError, GalleryReplacedError


class _ScalarResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _CaptureSession:
    def __init__(self):
        self.statements = []

    async def scalars(self, stmt):
        self.statements.append(stmt)
        return _ScalarResult()

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(rowcount=0, all=list)

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return 0

    async def flush(self):
        return None


def _sql(stmt) -> str:
    try:
        return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    except Exception:  # noqa: BLE001
        return str(stmt).lower()


async def test_local_new_gids_excludes_trashed() -> None:
    session = _CaptureSession()
    await GalleryUpdatesRepository(session).local_new_gids([1, 2])
    sql = _sql(session.statements[0])
    assert "trashed" in sql
    assert "expunged" in sql


async def test_list_items_join_excludes_trashed_and_expunged() -> None:
    session = _CaptureSession()
    await FavoritesRepository(session).list_items(1, 1, 10)
    sql = _sql(session.statements[0])
    assert "trashed" in sql
    assert "expunged" in sql


async def test_restore_galleries_only_trashed() -> None:
    session = _CaptureSession()
    await GalleryRepository(session).restore_galleries([1, 2])
    sql = _sql(session.statements[0])
    assert "trashed" in sql
    assert "expunged" not in sql or "expunged = false" not in sql


async def test_list_integrity_does_not_hide_via_max_pages_task() -> None:
    session = _CaptureSession()
    await GalleryRepository(session).list_integrity_issues(1, 10)
    joined = " ".join(_sql(s) for s in session.statements)
    assert "download_tasks" not in joined
    assert "max_pages" not in joined


async def test_gallery_mode_replaced_empty_pages_fails() -> None:
    gallery = GalleryData(1, "old", "t", [], replaced_by=(2, "new"))
    try:
        raise_if_replaced(DownloadTask(1, "old", "t", mode="gallery"), gallery)
        raise AssertionError("expected GalleryGoneError")
    except GalleryGoneError:
        pass
    try:
        raise_if_replaced(DownloadTask(1, "old", "t", mode="archive"), gallery)
        raise AssertionError("expected GalleryReplacedError")
    except GalleryReplacedError:
        pass


async def test_resolve_one_stops_at_max_follow_hops() -> None:
    prepared = await _resolve_one(None, 1, "tok", cache={}, gdata={}, hops=MAX_FOLLOW_HOPS)
    assert prepared.gid == 1
    assert prepared.old_gid is None


async def test_resolve_one_html_banner_despite_gdata_and_cache_titles() -> None:
    from galleryvault.services.eh_client import GalleryData

    html_gids: list[int] = []

    class Client:
        async def fetch_gallery_metadata(self, gid, token):
            html_gids.append(gid)
            if gid == 1:
                return GalleryData(1, token, "Old", [], replaced_by=(2, "newtok"))
            return GalleryData(2, "newtok", "New Title", [])

    prepared = await _resolve_one(
        Client(),
        1,
        "tok",
        cache={1: {"title": "cached-old"}},
        gdata={1: {"title": "gdata-old"}},
        hops=0,
    )
    assert prepared.gid == 2
    assert prepared.old_gid == 1
    assert prepared.title == "New Title"
    assert html_gids == [1, 2]


async def test_prepare_html_banner_cached_per_gid(monkeypatch) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.services.download_prepare import prepare_galleries
    from galleryvault.services.eh_client import GalleryData

    html_gids: list[int] = []
    gdata_calls: list[list[tuple[int, str]]] = []

    class Client:
        async def fetch_gmetadata(self, pairs):
            gdata_calls.append(list(pairs))
            return {int(gid): {"title": f"gdata-{gid}"} for gid, _tok in pairs}

        async def fetch_gallery_metadata(self, gid, token):
            html_gids.append(gid)
            if gid == 10:
                return GalleryData(10, token, "Old", [], replaced_by=(20, "newtok"))
            return GalleryData(20, "newtok", "New Title", [])

    async def fake_cache(gids):
        return {10: {"title": "cached-10", "token": "tok"}}

    async def fake_local(gids):
        return set()

    monkeypatch.setattr(
        "galleryvault.services.download_prepare._cached_map", fake_cache
    )
    monkeypatch.setattr(
        "galleryvault.services.download_prepare._local_gids", fake_local
    )
    orig_client = app_state.eh_client
    try:
        app_state.eh_client = Client()
        results = await prepare_galleries([(10, "tok"), (10, "tok")])
        assert len(results) == 2
        assert results[0].gid == 20
        assert results[0].old_gid == 10
        assert html_gids.count(10) == 1
        assert html_gids.count(20) == 1
        assert gdata_calls == []
    finally:
        app_state.eh_client = orig_client


async def test_prepare_gdata_only_when_html_fails(monkeypatch) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.services.download_prepare import prepare_galleries
    from galleryvault.services.eh_client import EhClientError

    html_gids: list[int] = []
    gdata_calls: list[list[tuple[int, str]]] = []

    class Client:
        async def fetch_gmetadata(self, pairs):
            gdata_calls.append(list(pairs))
            return {int(gid): {"title": f"gdata-{gid}"} for gid, _tok in pairs}

        async def fetch_gallery_metadata(self, gid, token):
            html_gids.append(gid)
            raise EhClientError("html down")

    async def fake_cache(gids):
        return {}

    async def fake_local(gids):
        return set()

    monkeypatch.setattr(
        "galleryvault.services.download_prepare._cached_map", fake_cache
    )
    monkeypatch.setattr(
        "galleryvault.services.download_prepare._local_gids", fake_local
    )
    orig_client = app_state.eh_client
    try:
        app_state.eh_client = Client()
        results = await prepare_galleries([(10, "tok"), (11, "tok2")])
        assert html_gids == [10, 11]
        assert gdata_calls == [[(10, "tok"), (11, "tok2")]]
        assert results[0].title == "gdata-10"
        assert results[1].title == "gdata-11"
    finally:
        app_state.eh_client = orig_client


async def test_read_status_completed_requires_progress() -> None:
    session = _CaptureSession()
    await GalleryRepository(session).list_page(1, 10, read_status="unread")
    unread_sql = " ".join(_sql(s) for s in session.statements)
    session.statements.clear()
    await GalleryRepository(session).list_page(1, 10, read_status="completed")
    completed_sql = " ".join(_sql(s) for s in session.statements)
    assert "reading_progress" in unread_sql
    assert "current_page > 0" in completed_sql or "current_page > :current_page" in completed_sql


def test_hops_detail_distinct_from_gone() -> None:
    from galleryvault.services.messages import GONE_DETAIL, HOPS_DETAIL

    assert HOPS_DETAIL != GONE_DETAIL
    assert "hop" in HOPS_DETAIL.lower()
