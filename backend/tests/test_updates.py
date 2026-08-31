"""Gallery-updates tracking: re-uploaded (new-gid) ExHentai versions.

Tests the title normalization, the detection scan (idempotent, gid-in-fav
excluded), the download enqueue, and the API surface.
"""

from types import SimpleNamespace

import pytest

from galleryvault.app import main
from galleryvault.app.routers import updates as updates_router


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return self._rows


@pytest.fixture(autouse=True)
def reset_updates_state() -> None:
    main.gallery_updates_state.update(
        {"detecting": False, "found": 0, "last_error": None, "last_run": None, "last_detected_at": None}
    )
    yield


# --- title normalization ----------------------------------------------------


def test_normalize_update_title_strips_prefix_variants_punctuation():
    n = main._normalize_update_title
    assert n("123-[Circle] Title (Date) [中国翻訳] [DL版]") == "circletitledate"
    assert n("[高嶋しょあ] 押しかけヴァンプ - My little vamp (COMIC 2024年12月号)") == (
        "高嶋しょあ押しかけヴァンプmylittlevampcomic2024年12月号"
    )
    assert n("AI generated large insertions and size difference") == "aigeneratedlargeinsertionsandsizedifference"
    assert n("  101-gid prefix title  ") == "gidprefixtitle"


# --- detection scan ---------------------------------------------------------


async def test_detect_gallery_updates_finds_old_versions(monkeypatch):
    fav_rows = [
        (200, "tokb", "Title A", 0),
        (201, "tokc", "Title B", 1),
    ]
    gallery_rows = [
        (1, 100, "100-Title A [中国翻訳]"),  # old version of fav 200 (title matches, gid not favorited)
        (2, 101, "Title B"),  # title matches fav 201, gid not favorited
        (3, 200, "Title A"),  # gid IS favorited -> excluded
        (4, 999, "Completely Different Title"),
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

        async def tracked_gallery_ids(self):
            return set()

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(main, "GalleryUpdatesRepository", FakeRepo)

    await main._detect_gallery_updates()

    assert len(seen) == 2
    assert {e["gallery_id"] for e in seen} == {1, 2}
    assert all(e["old_gid"] != 200 for e in seen)
    by_gid = {e["old_gid"]: e for e in seen}
    assert by_gid[100]["new_gid"] == 200 and by_gid[100]["new_token"] == "tokb"
    assert by_gid[101]["new_gid"] == 201
    assert main.gallery_updates_state["found"] == 2
    assert main.gallery_updates_state["last_error"] is None


async def test_detect_gallery_updates_skips_already_tracked(monkeypatch):
    fav_rows = [(200, "tok", "Title A", 0)]
    gallery_rows = [(1, 100, "Title A")]

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

        async def tracked_gallery_ids(self):
            return {1}  # already pending/failed/ignored

        async def detect_many(self, entries, *, known_gallery_ids):
            seen.extend(entries)
            return len(entries)

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(main, "GalleryUpdatesRepository", FakeRepo)

    await main._detect_gallery_updates()

    assert seen == []


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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(main, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(main.DownloadRepository, "create", fake_create)

    result = await main._run_gallery_updates([1, 1])

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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(main, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(main.DownloadRepository, "create", fake_create)

    result = await main._run_gallery_updates([3], archive=True, quality="original")

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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(main, "GalleryUpdatesRepository", FakeRepo)
    called = []

    async def fake_create(self, gid, token, title, mode, max_pages=None, quality=None):
        called.append(gid)
        return SimpleNamespace(id=77)

    monkeypatch.setattr(main.DownloadRepository, "create", fake_create)

    result = await main._run_gallery_updates([2])

    assert result == {"started": 0, "skipped": 1}
    assert called == []


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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(main, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(main, "asyncio", SimpleNamespace(sleep=fake_sleep))

    with pytest.raises(RuntimeError, match="stop-loop"):
        await main._gallery_updates_finalize_loop()

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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)
    main.gallery_updates_state["last_detected_at"] = "2026-01-01T00:00:00+00:00"
    main.gallery_updates_state["found"] = 3

    body = await updates_router.gallery_updates_status()

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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_router, "FavoritesRepository", FakeFavRepo)

    body = await updates_router.gallery_updates_list(page=1, page_size=24, state="active")

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

    monkeypatch.setattr(main, "_spawn", fake_spawn)

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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)

    body = await updates_router.gallery_updates_ignore(updates_router.UpdateIdsRequest(ids=[1, 2]))

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

    monkeypatch.setattr(main, "_settings_session", lambda: Sess())
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)

    body = await updates_router.gallery_updates_delete(updates_router.UpdateIdsRequest(ids=[1, 2]))

    assert body == {"deleted": 2}
