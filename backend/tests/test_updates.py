"""Gallery-updates tracking: re-uploaded (new-gid) ExHentai versions.

Tests the title normalization, the detection scan (idempotent, gid-in-fav
excluded), the download enqueue, and the API surface.
"""

from types import SimpleNamespace

import pytest

from galleryvault.app.routers import updates as updates_router
from galleryvault.app.state import app_state
from galleryvault.services import updates_worker
from galleryvault.services.updates_worker import (
    detect_gallery_updates,
    finalize_updates_for_new_gid,
    gallery_updates_finalize_loop,
    normalize_update_title,
    run_gallery_updates,
)


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return self._rows


@pytest.fixture(autouse=True)
def reset_updates_state() -> None:
    app_state.task_manager.gallery_updates_state.update(
        {"detecting": False, "found": 0, "last_error": None, "last_run": None, "last_detected_at": None}
    )
    yield


# --- title normalization ----------------------------------------------------


def test_normalize_update_title_strips_prefix_variants_punctuation():
    n = normalize_update_title
    assert n("123-[Circle] Title (Date) [中国翻訳] [DL版]") == "circletitledate"
    assert n("[高嶋しょあ] 押しかけヴァンプ - My little vamp (COMIC 2024年12月号)") == (
        "高嶋しょあ押しかけヴァンプmylittlevampcomic2024年12月号"
    )
    assert n("AI generated large insertions and size difference") == "aigeneratedlargeinsertionsandsizedifference"
    assert n("  101-gid prefix title  ") == "gidprefixtitle"
    # Serialized chapter/episode range normalization
    assert n("[Kase Daiki] Real o Tsuikyuu 1-4 | 追求真實感 1-4 [Chinese]") == (
        n("[Kase Daiki] Real o Tsuikyuu 1-5 | 追求真實感 1-5 [Chinese]")
    )
    assert n("3240842-[にぎりうさぎ] 呪いのせいでMPが足りません!! ①〜⑨ [中国翻訳]") == (
        n("[にぎりうさぎ] 呪いのせいでMPが足りません!!【全話】[中国翻訳]")
    )
    assert n("3181885-[湊ゆう] えちんぽカード (01-06)") == n("[湊ゆう] えちんぽカード (01-10)")
    assert n("2896212-[雪村] セフレ契約結んじゃいました… 第1-7 話 [中国翻訳]") == (
        n("[雪村] セフレ契約結んじゃいました… 第1-10 話 [中国翻訳]")
    )
    assert n("3037111-[武田] だれでも抱けるキミが好き  喜欢来者不拒的你 [连载中]") == (
        n("[武田] だれでも抱けるキミが好き [進行中]")
    )


# --- detection scan ---------------------------------------------------------


async def test_detect_gallery_updates_finds_old_versions(monkeypatch):
    fav_rows = [
        (200, "tokb", "Title A", 0),
        (201, "tokc", "Title B", 1),
    ]
    gallery_rows = [
        (1, 100, "100-Title A [中国翻訳]", None),  # old version of fav 200 (title matches, gid not favorited)
        (2, 101, "Title B", None),  # title matches fav 201, gid not favorited
        (3, 200, "Title A", None),  # gid IS favorited -> excluded
        (4, 999, "Completely Different Title", None),
    ]

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def execute(self, stmt):
            if "favorite_items" in str(stmt):
                return _Res(fav_rows)
            return _Res(gallery_rows)

    seen = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def tracking_by_gallery_id(self):
            return {}

        async def local_new_gids(self, gids):
            return set()

        async def active_task_ids_for_gids(self, gids):
            return {}

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)

    try:
        await detect_gallery_updates()
    finally:
        app_state.session_factory = orig_factory

    assert len(seen) == 2
    assert {e["gallery_id"] for e in seen} == {1, 2}
    assert all(e["old_gid"] != 200 for e in seen)
    by_gid = {e["old_gid"]: e for e in seen}
    assert by_gid[100]["new_gid"] == 200 and by_gid[100]["new_token"] == "tokb"
    assert by_gid[101]["new_gid"] == 201
    assert app_state.task_manager.gallery_updates_state["found"] == 2
    assert app_state.task_manager.gallery_updates_state["last_error"] is None


async def test_detect_gallery_updates_skips_already_tracked(monkeypatch):
    fav_rows = [(200, "tok", "Title A", 0)]
    gallery_rows = [(1, 100, "Title A", None)]

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def execute(self, stmt):
            if "favorite_items" in str(stmt):
                return _Res(fav_rows)
            return _Res(gallery_rows)

    seen = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def tracking_by_gallery_id(self):
            return {1: SimpleNamespace(id=9, status="pending", gallery_id=1)}

        async def local_new_gids(self, gids):
            return set()

        async def active_task_ids_for_gids(self, gids):
            return {}

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)

    try:
        await detect_gallery_updates()
    finally:
        app_state.session_factory = orig_factory

    assert seen == []


async def test_detect_gallery_updates_finalizes_when_new_gid_local(monkeypatch):
    fav_rows = [(200, "tok", "Title A", 0)]
    gallery_rows = [(1, 100, "Title A", None)]
    finalized = []
    seen = []

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def execute(self, stmt):
            if "favorite_items" in str(stmt):
                return _Res(fav_rows)
            return _Res(gallery_rows)

    class FakeRepo:
        def __init__(self, session):
            pass

        async def tracking_by_gallery_id(self):
            return {1: SimpleNamespace(id=9, status="pending", gallery_id=1)}

        async def local_new_gids(self, gids):
            return {200}

        async def active_task_ids_for_gids(self, gids):
            return {}

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    async def fake_finalize(row):
        finalized.append(row.gallery_id)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker, "finalize_gallery_update", fake_finalize)

    try:
        await detect_gallery_updates()
    finally:
        app_state.session_factory = orig_factory

    assert seen == []
    assert finalized == [1]


async def test_detect_gallery_updates_skips_ignored_even_if_new_local(monkeypatch):
    fav_rows = [(200, "tok", "Title A", 0)]
    gallery_rows = [(1, 100, "Title A", None)]
    finalized = []
    seen = []

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def execute(self, stmt):
            if "favorite_items" in str(stmt):
                return _Res(fav_rows)
            return _Res(gallery_rows)

    class FakeRepo:
        def __init__(self, session):
            pass

        async def tracking_by_gallery_id(self):
            return {1: SimpleNamespace(id=9, status="ignored", gallery_id=1)}

        async def local_new_gids(self, gids):
            return {200}

        async def active_task_ids_for_gids(self, gids):
            return {}

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    async def fake_finalize(row):
        finalized.append(row.gallery_id)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker, "finalize_gallery_update", fake_finalize)

    try:
        await detect_gallery_updates()
    finally:
        app_state.session_factory = orig_factory

    assert seen == []
    assert finalized == []


async def test_detect_gallery_updates_pins_active_download(monkeypatch):
    fav_rows = [(200, "tok", "Title A", 0)]
    gallery_rows = [(1, 100, "Title A", None)]
    seen = []

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def execute(self, stmt):
            if "favorite_items" in str(stmt):
                return _Res(fav_rows)
            return _Res(gallery_rows)

    class FakeRepo:
        def __init__(self, session):
            pass

        async def tracking_by_gallery_id(self):
            return {}

        async def local_new_gids(self, gids):
            return set()

        async def active_task_ids_for_gids(self, gids):
            return {200: 77}

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)

    try:
        await detect_gallery_updates()
    finally:
        app_state.session_factory = orig_factory

    assert len(seen) == 1
    assert seen[0]["new_gid"] == 200
    assert seen[0]["status"] == "downloading"
    assert seen[0]["download_task_id"] == 77


# --- update execution -------------------------------------------------------


async def test_run_gallery_updates_enqueues_download(monkeypatch):
    created = []

    class FakeUpdate:
        status = "pending"
        id = 1
        new_gid = 500
        new_token = "tok"
        title = "New version"
        download_task_id = None

    class FakeRepo:
        def __init__(self, session):
            pass

        async def get(self, update_id):
            return FakeUpdate()

        async def local_new_gids(self, gids):
            return set()

        async def mark_downloading(self, update_id, task_id):
            return True

    class Sess:
        def __init__(self):
            self._entered = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    async def fake_create(
        self, gid, token, title, mode, max_pages=None, quality=None
    ):
        created.append((gid, token, title, mode, quality))
        return SimpleNamespace(id=77)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker.DownloadRepository, "create", fake_create)

    try:
        result = await run_gallery_updates([1, 1])
    finally:
        app_state.session_factory = orig_factory

    assert result == {"started": 1, "skipped": 0}
    assert created == [(500, "tok", "New version", "favorite", None)]


async def test_run_gallery_updates_archives(monkeypatch):
    created = []

    class FakeUpdate:
        status = "pending"
        id = 3
        new_gid = 501
        new_token = "tok2"
        title = "Archive version"
        download_task_id = None

    class FakeRepo:
        def __init__(self, session):
            pass

        async def get(self, update_id):
            return FakeUpdate()

        async def local_new_gids(self, gids):
            return set()

        async def mark_downloading(self, update_id, task_id):
            return True

    class Sess:
        def __init__(self):
            self._entered = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    async def fake_create(
        self, gid, token, title, mode, max_pages=None, quality=None
    ):
        created.append((gid, token, title, mode, quality))
        return SimpleNamespace(id=78)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker.DownloadRepository, "create", fake_create)

    try:
        result = await run_gallery_updates([3], archive=True, quality="original")
    finally:
        app_state.session_factory = orig_factory

    assert result == {"started": 1, "skipped": 0}
    assert created == [(501, "tok2", "Archive version", "archive", "original")]


async def test_run_gallery_updates_skips_non_pending(monkeypatch):
    class FakeUpdate:
        status = "failed"  # not pending -> skipped
        id = 2
        new_gid = 500
        new_token = "tok"
        title = "New version"
        download_task_id = None

    class FakeRepo:
        def __init__(self, session):
            pass

        async def get(self, update_id):
            return FakeUpdate()

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    called = []

    async def fake_create(self, gid, token, title, mode, max_pages=None, quality=None):
        called.append(gid)
        return SimpleNamespace(id=77)

    monkeypatch.setattr(updates_worker.DownloadRepository, "create", fake_create)

    try:
        result = await run_gallery_updates([2])
    finally:
        app_state.session_factory = orig_factory

    assert result == {"started": 0, "skipped": 1}
    assert called == []


async def test_run_gallery_updates_finalizes_when_already_local(monkeypatch):
    created = []
    finalized = []

    class FakeUpdate:
        status = "pending"
        id = 4
        gallery_id = 12
        new_gid = 500
        new_token = "tok"
        title = "New version"
        download_task_id = None

    class FakeRepo:
        def __init__(self, session):
            pass

        async def get(self, update_id):
            return FakeUpdate()

        async def local_new_gids(self, gids):
            return {500}

        async def mark_downloading(self, update_id, task_id):
            raise AssertionError("should not enqueue")

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    async def fake_create(self, gid, token, title, mode, max_pages=None, quality=None):
        created.append(gid)
        return SimpleNamespace(id=77)

    async def fake_finalize(row):
        finalized.append((row.id, row.gallery_id))

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker.DownloadRepository, "create", fake_create)
    monkeypatch.setattr(updates_worker, "finalize_gallery_update", fake_finalize)

    try:
        result = await run_gallery_updates([4])
    finally:
        app_state.session_factory = orig_factory

    assert result == {"started": 1, "skipped": 0}
    assert created == []
    assert finalized == [(4, 12)]


async def test_finalize_updates_for_new_gid_skips_ignored(monkeypatch):
    class FakeRepo:
        def __init__(self, session):
            pass

        async def actionable_by_new_gid(self, new_gid):
            return [
                SimpleNamespace(id=1, gallery_id=10, status="pending"),
                SimpleNamespace(id=2, gallery_id=11, status="downloading"),
            ]

    finalized = []

    async def fake_finalize(row):
        finalized.append(row.gallery_id)

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker, "finalize_gallery_update", fake_finalize)

    try:
        done = await finalize_updates_for_new_gid(200)
    finally:
        app_state.session_factory = orig_factory

    assert done == 2
    assert finalized == [10, 11]


# --- API surface ------------------------------------------------------------


async def test_finalize_loop_marks_removed_task_failed(monkeypatch):
    """A downloading update whose task row vanished must not stay stuck.

    Regression: the loop used to ``continue`` on ``task is None``, so an
    update whose download task was deleted (downloads page) stayed
    ``downloading`` forever.
    """
    marked = []

    class FakeRow:
        id = 99
        download_task_id = 555  # task was deleted
        status = "downloading"

    class FakeRepo:
        def __init__(self, session):
            pass

        async def downloading(self):
            return [FakeRow()]

        async def mark_failed(self, update_id, error):
            marked.append((update_id, error))
            return True

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def get(self, model, task_id):
            return None  # the download task no longer exists

    sleeps = {"n": 0}

    async def fake_sleep(_):
        sleeps["n"] += 1
        if sleeps["n"] > 1:
            raise RuntimeError("stop-loop")

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_worker.asyncio, "sleep", fake_sleep)

    try:
        with pytest.raises(RuntimeError, match="stop-loop"):
            await gallery_updates_finalize_loop()
    finally:
        app_state.session_factory = orig_factory

    assert marked == [(99, "download task removed")]


async def test_updates_status_reports_counts(monkeypatch):
    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size, status=None):
            counts = {"pending": 3, "downloading": 1, "failed": 2, "ignored": 5}
            return counts.get(status, 0), []

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)
    tm = app_state.task_manager
    tm.gallery_updates_state["last_detected_at"] = "2026-01-01T00:00:00+00:00"
    tm.gallery_updates_state["found"] = 3

    try:
        body = await updates_router.gallery_updates_status()
    finally:
        app_state.session_factory = orig_factory

    assert body["counts"]["pending"] == 3
    assert body["counts"]["ignored"] == 5
    assert body["detecting"] is False
    assert body["last_found"] == 3


async def test_updates_list_shapes_rows(monkeypatch):
    row = SimpleNamespace(
        id=9,
        gallery_id=12,
        old_gid=100,
        new_gid=200,
        title="Old title",
        favcat=3,
        status="pending",
        error_message=None,
        detected_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00"),
        updated_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:01"),
    )

    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size, status=None):
            return 1, [row]

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    class FakeFavRepo:
        def __init__(self, session):
            pass

        async def category_names(self, favcats):
            return {3: "Wonderful"}

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_router, "FavoritesRepository", FakeFavRepo)

    try:
        body = await updates_router.gallery_updates_list(page=1, page_size=24, state="active")
    finally:
        app_state.session_factory = orig_factory

    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == 9 and item["old_gid"] == 100 and item["new_gid"] == 200
    assert item["favcat_name"] == "Wonderful"
    assert item["cover_url"] == "/api/galleries/12/thumb/0"


async def test_updates_scan_spawns_detect(monkeypatch):
    spawned = []

    def fake_spawn(coro, op):
        spawned.append(op)
        coro.close()

    monkeypatch.setattr(updates_router, "spawn_task", fake_spawn)

    body = await updates_router.gallery_updates_scan()

    assert body == {"status": "started"}
    assert "gallery update" in spawned[0]


async def test_updates_ignore_marks_ignored(monkeypatch):
    class FakeRepo:
        def __init__(self, session):
            pass

        async def mark_ignored(self, ids):
            return len(ids)

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)

    try:
        body = await updates_router.gallery_updates_ignore(updates_router.UpdateIdsRequest(ids=[1, 2]))
    finally:
        app_state.session_factory = orig_factory

    assert body == {"ignored": 2}


async def test_updates_delete_deletes_rows(monkeypatch):
    class FakeRepo:
        def __init__(self, session):
            pass

        async def delete_many(self, ids):
            return len(ids)

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)

    try:
        body = await updates_router.gallery_updates_delete(updates_router.UpdateIdsRequest(ids=[1, 2]))
    finally:
        app_state.session_factory = orig_factory

    assert body == {"deleted": 2}


async def test_favcats_for_gid_with_update_fallback(monkeypatch):
    from galleryvault.db.repository import FavoritesRepository

    class FakeSession:
        async def scalars(self, stmt):
            sql = str(stmt).lower()
            if "gallery_updates" in sql:
                return _Res([6])
            return _Res([])

    repo = FavoritesRepository(FakeSession())
    favcats = await repo.favcats_for_gid(100, gallery_id=1)
    assert favcats == [6]
