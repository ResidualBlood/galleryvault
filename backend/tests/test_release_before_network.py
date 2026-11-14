"""T6.1: the four read -> EH network -> write sites must release the pooled DB
connection after the last read and before the first network call.

The fake session records transaction boundaries; the fake clients record the
network call.  Every test asserts that ``rollback`` happens before the network
event, and that ORM-ish rows are only read before the release (a real rollback
expires loaded instances).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from galleryvault.app.routers import galleries
from galleryvault.app.state import app_state
from galleryvault.services import eh_metadata, tag_sync, tag_sync_worker
from galleryvault.services import favorites as favorites_service
from galleryvault.services import favorites_worker as fw
from galleryvault.services.download_prepare import PreparedGallery
from galleryvault.services.favorites import cover_cache as fav_covers
from galleryvault.services.favorites_mutations import add_favorites
from galleryvault.services.tasks import TaskManager


class _Session:
    """Minimal async session double recording transaction boundaries."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.in_tx = True

    def in_transaction(self) -> bool:
        return self.in_tx

    async def rollback(self) -> None:
        self.in_tx = False
        self.events.append("rollback")

    async def commit(self) -> None:
        self.in_tx = False
        self.events.append("commit")

    async def scalars(self, *args: object, **kwargs: object) -> object:
        return None

    async def execute(self, *args: object, **kwargs: object) -> object:
        return None


class _Row:
    """Attribute access is recorded so we can prove values were copied early."""

    def __init__(self, events: list[str], **values: object) -> None:
        object.__setattr__(self, "_events", events)
        object.__setattr__(self, "_values", values)

    def __getattr__(self, name: str) -> object:
        values = object.__getattribute__(self, "_values")
        if name in values:
            object.__getattribute__(self, "_events").append(f"read-{name}")
            return values[name]
        raise AttributeError(name)


def _first(events: list[str], prefix: str) -> int:
    return next(i for i, event in enumerate(events) if event.startswith(prefix))


async def test_refresh_gdata_releases_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)

    class _Repo:
        def __init__(self, _session: object) -> None:
            self.calls = 0

        async def metadata_map(self, gids: list[int]) -> dict[int, dict[str, object]]:
            events.append("read")
            self.calls += 1
            if self.calls == 1:
                return {}
            return {42: {"title": "Fetched", "category": "manga", "tags": []}}

        async def upsert_metadata(self, entries: list[dict[str, object]]) -> None:
            events.append("write")

    class _Client:
        async def fetch_gmetadata(self, pairs: list[tuple[int, str]]) -> dict[int, dict[str, object]]:
            events.append("network")
            return {42: {"title": "Fetched", "category": "manga", "tags": []}}

    monkeypatch.setattr(eh_metadata, "GalleryRepository", _Repo)

    result = await eh_metadata.refresh_gdata(
        session, [(42, "tok")], client=_Client(), force=True
    )

    assert result[42]["title"] == "Fetched"
    assert _first(events, "rollback") < _first(events, "network")
    assert _first(events, "network") < _first(events, "write")
    assert session.in_tx is False


async def test_fetch_plan_releases_before_gdata_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)
    gallery = _Row(
        events,
        gid=42,
        token="tok",
        title="Local title",
        title_jpn=None,
        category="manga",
    )

    class _Repo:
        def __init__(self) -> None:
            self.session = session

        async def get_for_tag_sync(self, _identifier: int) -> _Row:
            return gallery

        async def metadata_for_gid(self, _gid: int) -> dict[str, object]:
            events.append("read-metadata")
            return {}

    class _Client:
        async def fetch_gmetadata(self, pairs: list[tuple[int, str]]) -> dict[int, dict[str, object]]:
            events.append("network")
            return {}

    async def _fake_refresh(*args: object, **kwargs: object) -> dict[int, dict[str, object]]:
        events.append("network")
        return {42: {"title": "Fetched", "category": "manga", "tags": []}}

    monkeypatch.setattr(tag_sync, "refresh_gdata", _fake_refresh)

    service = tag_sync.TagSyncService(_Client(), _Repo())
    plan = await service.fetch_plan(1)

    assert plan["source"] == "network"
    assert plan["title"] == "Fetched"
    assert _first(events, "rollback") < _first(events, "network")
    # ORM-ish values must have been copied before the release.
    for attr in ("read-title", "read-title_jpn", "read-category"):
        assert _first(events, attr) < _first(events, "rollback")


async def test_fetch_plan_cache_branch_releases_before_enrich(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)
    gallery = _Row(
        events,
        gid=42,
        token="tok",
        title="Local title",
        title_jpn=None,
        category="manga",
    )

    class _Repo:
        def __init__(self) -> None:
            self.session = session

        async def get_for_tag_sync(self, _identifier: int) -> _Row:
            return gallery

        async def metadata_for_gid(self, _gid: int) -> dict[str, object]:
            events.append("read-metadata")
            return {
                "title": "Cached",
                "tags": [{"namespace": "artist", "name": "someone"}],
                "newer_gid": None,
            }

    async def _fake_enrich(*args: object, **kwargs: object) -> None:
        events.append("network-enrich")

    monkeypatch.setattr(tag_sync, "enrich_html_newer", _fake_enrich)

    service = tag_sync.TagSyncService(SimpleNamespace(), _Repo())
    plan = await service.fetch_plan(1, enrich_newer=True)

    assert plan["source"] == "cache"
    assert plan["title"] == "Cached"
    assert _first(events, "rollback") < _first(events, "network-enrich")
    for attr in ("read-title", "read-title_jpn", "read-category"):
        assert _first(events, attr) < _first(events, "rollback")


async def test_add_favorites_releases_before_cloud_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)

    class _Client:
        async def add_favorites(
            self,
            pairs: list[tuple[int, str]],
            favcat: int,
            note: str | None = None,
        ) -> list[int]:
            events.append("network")
            return []

    class _ClientContext:
        async def __aenter__(self) -> _Client:
            return _Client()

        async def __aexit__(self, *exc: object) -> bool:
            return False

    class _Mgr:
        def client_context(self, settings: object = None) -> _ClientContext:
            return _ClientContext()

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def remember_many(self, favcat: int, items: list[object]) -> None:
            events.append("write")

        async def move_gids(self, gids: list[int], favcat: int) -> None:
            events.append("write")

    repo = _Repo(session)
    deps = SimpleNamespace(
        favorites_repo=lambda _session: repo,
        gallery_repo=lambda _session: repo,
        delete_local=lambda *a, **k: [],
        release_session=lambda _session: None,
        db_error=lambda exc: exc,
        logger=logging.getLogger("test"),
        record_task=None,
    )
    body = SimpleNamespace(
        items=[{"gid": 42, "token": "tok", "title": "T"}],
        note="",
        target_favcat=0,
    )

    result = await add_favorites(
        body,
        session=session,
        eh_client_mgr=_Mgr(),
        settings=SimpleNamespace(exhentai_base_url="https://e-hentai.org"),
        deps=deps,
    )

    assert result["cloud_ok"] is True
    assert result["local_added"] == 1
    assert _first(events, "rollback") < _first(events, "network")
    assert _first(events, "network") < _first(events, "write")


async def test_redownload_expunged_releases_before_prepare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)
    row = _Row(events, id=1, gid=1001, token="tok1001", title="G1")

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def find_by_ids(self, ids: list[int]) -> list[_Row]:
            events.append("read")
            return [row]

    async def _fake_prepare(pairs: list[tuple[int, str]]) -> list[PreparedGallery]:
        events.append("network")
        return [PreparedGallery(gid=gid, token=token, title="Prepared") for gid, token in pairs]

    created_titles: list[str | None] = []

    async def _fake_create(prepared: PreparedGallery, **kwargs: object) -> tuple[str, dict]:
        events.append("write")
        created_titles.append(kwargs.get("fallback_title"))
        return "queued", {"status": "queued"}

    monkeypatch.setattr(galleries, "GalleryRepository", _Repo)
    monkeypatch.setattr(galleries, "prepare_galleries", _fake_prepare)
    monkeypatch.setattr(galleries, "_create_from_prepared", _fake_create)

    result = await galleries.redownload_expunged(
        galleries.ExpungedRedownloadRequest(ids=[1]), session=session
    )

    assert result == {"queued": 1, "skipped_no_gid": 0, "skipped_no_token": 0}
    assert created_titles == ["G1"]
    assert _first(events, "read-title") < _first(events, "rollback")
    assert _first(events, "rollback") < _first(events, "network")


# ---------------------------------------------------------------------------
# T6.1b: favorites / tag-sync call sites must not wrap ``refresh_gdata`` in an
# explicit ``session.begin()``.  The fake session models SQLAlchemy's
# ``_trans_context_manager`` attribute, so refresh_gdata takes the same
# release path as with a real AsyncSession: on the baseline it sees the
# caller's explicit transaction and keeps the connection (test fails).
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)

    def scalars(self) -> _FakeResult:
        return self

    def __iter__(self):
        return iter(self._rows)


class _FakeBegin:
    def __init__(self, session: _TxSession) -> None:
        self.session = session

    async def __aenter__(self) -> _TxSession:
        self.session.in_tx = True
        self.session._trans_context_manager = self
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None and self.session.in_tx:
            await self.session.commit()
        self.session._trans_context_manager = None
        return False


class _TxSession:
    """AsyncSession double that emulates explicit ``begin()`` bookkeeping."""

    def __init__(self, events: list[str], rows: list[object] | None = None) -> None:
        self.events = events
        self.in_tx = False
        self.sync_session = self
        self._trans_context_manager = None
        self.identity_map: dict[object, object] = {}
        self.rows = rows or []

    def in_transaction(self) -> bool:
        return self.in_tx

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self)

    async def rollback(self) -> None:
        self.in_tx = False
        self.events.append("rollback")

    async def commit(self) -> None:
        self.in_tx = False
        self.events.append("commit")

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        return _FakeResult(self.rows)

    async def scalars(self, *args: object, **kwargs: object) -> _FakeResult:
        return _FakeResult(self.rows)

    async def scalar(self, *args: object, **kwargs: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> None:
        return None

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass


class _SessionContext:
    def __init__(self, session: _TxSession) -> None:
        self.session = session

    async def __aenter__(self) -> _TxSession:
        return self.session

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _Factory:
    def __init__(self, session: _TxSession) -> None:
        self.session = session

    def __call__(self) -> _SessionContext:
        return _SessionContext(self.session)


class _RecordingClient:
    def __init__(self, events: list[str], result: dict[str, object]) -> None:
        self.events = events
        self.result = result

    async def fetch_gmetadata(self, pairs: list[tuple[int, str]]) -> dict[int, dict[str, object]]:
        self.events.append("network")
        return {int(gid): dict(self.result) for gid, _token in pairs}

    async def download_image(self, url: str) -> bytes:
        self.events.append("download")
        return b"\xff\xd8\xff\xe0cover"


class _RecordingMetaRepo:
    def __init__(self, session: _TxSession, meta: dict[str, object]) -> None:
        self.session = session
        self.meta = meta
        self.calls = 0

    async def metadata_map(self, gids: list[int]) -> dict[int, dict[str, object]]:
        self.session.events.append("read")
        self.calls += 1
        if self.calls == 1:
            return {}
        return {int(gid): dict(self.meta) for gid in gids}

    async def upsert_metadata(self, entries: list[dict[str, object]]) -> None:
        self.session.events.append("write")


def _patch_meta_repo(monkeypatch: pytest.MonkeyPatch, meta: dict[str, object]) -> None:
    monkeypatch.setattr(
        eh_metadata,
        "GalleryRepository",
        lambda session: _RecordingMetaRepo(session, meta),
    )


async def test_favorites_metadata_releases_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _TxSession(events)
    monkeypatch.setattr(fav_covers, "_get_background_session_factory", lambda: _Factory(session))
    _patch_meta_repo(monkeypatch, {"title": "Fetched", "category": "manga", "tags": []})
    orig_client = app_state.eh_client
    app_state.eh_client = _RecordingClient(events, {"title": "Fetched", "category": "manga", "tags": []})
    try:
        result = await fw.favorites_metadata([(42, "tok")])
    finally:
        app_state.eh_client = orig_client

    assert result[42]["title"] == "Fetched"
    assert _first(events, "rollback") < _first(events, "network")


async def test_fill_remote_cover_releases_before_network(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    session = _TxSession(events)
    monkeypatch.setattr(fav_covers, "_get_background_session_factory", lambda: _Factory(session))
    _patch_meta_repo(monkeypatch, {"thumb": "http://thumb"})
    orig_client = app_state.eh_client
    app_state.eh_client = _RecordingClient(events, {"thumb": "http://thumb"})
    fw.clear_remote_cover_negative(42)
    try:
        path = await fw._fill_remote_cover(42, "tok", tmp_path, "test", None)
    finally:
        app_state.eh_client = orig_client
        fw.clear_remote_cover_negative(42)

    assert path is not None
    assert _first(events, "rollback") < _first(events, "network")


async def test_favorite_size_sync_releases_before_network(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    session = _TxSession(events)
    monkeypatch.setattr(fw, "_get_background_session_factory", lambda: _Factory(session))
    _patch_meta_repo(monkeypatch, {"file_size": 1000, "thumb": ""})
    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)

    async def _noop_batch(*args: object, **kwargs: object) -> dict[int, str]:
        return {}

    async def _noop_cover(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(fw, "remote_cover_data_batch", _noop_batch)
    monkeypatch.setattr(fw, "ensure_remote_cover", _noop_cover)

    class _FavRepo:
        def __init__(self, session: object) -> None:
            pass

        async def all_gids_for_favcat(self, favcat: int) -> list[tuple[int, str, str]]:
            return [(10, "tok", "http://thumb")]

        async def set_file_size(self, *args: object, **kwargs: object) -> None:
            events.append("write-size")

    class _GalRepo:
        def __init__(self, session: object) -> None:
            pass

        async def seed_metadata_from_galleries(self, favcat: int) -> int:
            return 0

        async def metadata_map(self, gids: object) -> dict[int, dict[str, object]]:
            return {}

        async def null_image_quality_gids(self, gids: object) -> set[int]:
            return set()

        async def storage_size_map(self, gids: object) -> dict[int, object]:
            return {}

        async def set_image_qualities(self, mapping: object) -> int:
            return 0

        async def apply_cached_metadata(self, *, favcat: int | None = None, limit: int = 200) -> int:
            return 0

    monkeypatch.setattr(fw, "FavoritesRepository", _FavRepo)
    monkeypatch.setattr(fw, "GalleryRepository", _GalRepo)
    orig_client = app_state.eh_client
    app_state.eh_client = _RecordingClient(events, {"file_size": 1000, "thumb": ""})
    fw._size_sync_inflight.clear()
    try:
        await fw.favorite_size_sync(1)
    finally:
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()

    assert _first(events, "rollback") < _first(events, "network")


async def test_duplicates_scan_posted_refresh_releases_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _TxSession(events)
    monkeypatch.setattr(fw, "_get_background_session_factory", lambda: _Factory(session))
    _patch_meta_repo(monkeypatch, {"posted": "2024-01-01T00:00:00+00:00"})

    async def _fake_metadata(pairs: object) -> dict[int, dict[str, object]]:
        return {}

    async def _noop_covers(*args: object, **kwargs: object) -> dict[int, str]:
        return {}

    monkeypatch.setattr(fw, "favorites_metadata", _fake_metadata)
    monkeypatch.setattr(fw, "remote_cover_data_batch", _noop_covers)

    class _FavRepo:
        def __init__(self, session: object) -> None:
            pass

        async def all_items(self) -> list[tuple]:
            return [(1, 1001, "tok", "[Alice] Book", "", None, 1000)]

        async def gallery_titles_by_gid(self, gids: object) -> dict[int, tuple[str, None]]:
            return {1001: ("[Alice] Book", None)}

        async def tags_for_gallery_ids(self, ids: object) -> dict[int, list]:
            return {}

    class _DupRepo:
        def __init__(self, session: object) -> None:
            pass

        async def sync(self, kind: str, groups: list[dict]) -> list:
            return []

    monkeypatch.setattr(fw, "FavoritesRepository", _FavRepo)
    monkeypatch.setattr(fw, "DuplicateGroupRepository", _DupRepo)
    monkeypatch.setattr(
        fw,
        "find_duplicate_groups",
        lambda *args, **kwargs: [
            {
                "key": "alice|book",
                "artist": "alice",
                "items": [
                    {
                        "gallery_id": None,
                        "gid": 1001,
                        "token": "tok",
                        "title": "[Alice] Book",
                        "file_size": None,
                        "posted_at": None,
                    }
                ],
            }
        ],
    )
    tm = TaskManager()
    monkeypatch.setattr(app_state, "task_manager", tm)
    orig_client = app_state.eh_client
    app_state.eh_client = _RecordingClient(
        events, {"posted": "2024-01-01T00:00:00+00:00"}
    )
    try:
        await fw.run_duplicates_scan()
    finally:
        app_state.eh_client = orig_client

    assert _first(events, "rollback") < _first(events, "network")


async def test_check_category_fallback_releases_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _TxSession(events)
    monkeypatch.setattr(app_state, "session_factory", _Factory(session))
    _patch_meta_repo(
        monkeypatch,
        {"file_size": 50, "file_count": 50, "title": "Fetched", "category": "manga", "tags": []},
    )

    class _Fetcher:
        async def fetch_favorites(self, favcat: int, progress: object = None) -> list:
            return [SimpleNamespace(gid=101, token="tok101", title="G101")]

        async def fetch_gmetadata(
            self, pairs: list[tuple[int, str]]
        ) -> dict[int, dict[str, object]]:
            events.append("network")
            return {
                int(gid): {
                    "file_size": 50,
                    "file_count": 50,
                    "title": "Fetched",
                    "category": "manga",
                    "tags": [],
                }
                for gid, _token in pairs
            }

    class _Repo:
        async def category(self, favcat: int) -> object:
            return SimpleNamespace(name="Fav 0")

        async def known_gids(self, favcat: int) -> set[int]:
            return set()

        async def existing_gallery_gids(self, gids: object) -> set[int]:
            return set()

        async def remember_many(self, favcat: int, items: object) -> int:
            return len(items)

        async def prune(self, favcat: int, current: object, allow_empty: bool = False) -> int:
            return 0

        async def checked(self, favcat: int, success: bool) -> None:
            pass

    class _Queue:
        def __init__(self) -> None:
            self.modes: list[str] = []

        async def enqueue(
            self, item: object, mode: str | None = None, quality: str | None = None
        ) -> bool:
            self.modes.append(mode or "gallery")
            return True

    queue = _Queue()
    service = favorites_service.FavoritesService(_Fetcher(), _Repo(), queue)

    result = await service.check_category(
        0, archive_enabled=True, archive_max_pages=20
    )

    assert result.downloaded == 1
    assert queue.modes == ["favorite_archive"]
    assert _first(events, "rollback") < _first(events, "network")


async def test_tag_category_refresh_releases_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _TxSession(events, rows=[(1, 101, "tok101")])
    monkeypatch.setattr(app_state, "session_factory", _Factory(session))
    monkeypatch.setattr(tag_sync_worker, "_get_background_session_factory", lambda: _Factory(session))
    _patch_meta_repo(monkeypatch, {"category": "Manga", "expunged": False})

    class _TagRepo:
        def __init__(self, session: object) -> None:
            pass

        async def pending_category_refresh_ids(self, limit: int, last_id: int) -> list[int]:
            return [1] if last_id == 0 else []

        async def metadata_for_gid(self, gid: int) -> None:
            return None

        async def refresh_category(self, gal_id: int, category: str) -> None:
            events.append("write-category")

        async def mark_tag_synced(self, gal_id: int, category: str | None = None) -> None:
            events.append("write-deleted")

        async def mark_tag_not_visible(self, gal_id: int) -> None:
            events.append("write-deleted")

    monkeypatch.setattr(tag_sync_worker, "GalleryRepository", _TagRepo)
    orig_client = app_state.eh_client
    app_state.eh_client = _RecordingClient(events, {"category": "Manga", "expunged": False})
    try:
        count = await tag_sync_worker.category_refresh_once()
    finally:
        app_state.eh_client = orig_client

    assert count == 1
    assert "write-category" in events
    assert _first(events, "rollback") < _first(events, "network")


async def test_refresh_gdata_keeps_connection_for_live_orm_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documented retention: the one-shot repair script keeps its loaded rows.

    ``scripts/repair_cold_archives.py`` calls refresh_gdata on a long-lived
    session whose ORM instances are written to later in the same pass.  A
    rollback would expire them, so refresh_gdata must skip the release there
    (the script comments this reason at the call site).
    """
    events: list[str] = []
    session = _TxSession(events)
    session.identity_map = {object(): object()}
    _patch_meta_repo(monkeypatch, {"title": "Fetched", "category": "manga", "tags": []})

    result = await eh_metadata.refresh_gdata(
        session,
        [(42, "tok")],
        client=_RecordingClient(events, {"title": "Fetched", "category": "manga", "tags": []}),
        force=True,
    )

    assert result[42]["title"] == "Fetched"
    assert "rollback" not in events
    assert _first(events, "network") < _first(events, "write")
