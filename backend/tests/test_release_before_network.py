"""T6.1: the four read -> EH network -> write sites must release the pooled DB
connection after the last read and before the first network call.

The fake session records transaction boundaries; the fake clients record the
network call.  Every test asserts that ``rollback`` happens before the network
event, and that ORM-ish rows are only read before the release (a real rollback
expires loaded instances).
"""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from galleryvault.app.routers import galleries
from galleryvault.config import get_settings
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.services import eh_metadata, tag_sync
from galleryvault.services.download_prepare import PreparedGallery
from galleryvault.services.favorites_mutations import add_favorites


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
# Real-PG integration (the container runs these; plain host pytest skips).
# Regression: a caller using ``session.begin()`` crashed with
# ``InvalidRequestError: Can't operate on closed transaction inside context
# manager`` after refresh_gdata released the transaction.
# ---------------------------------------------------------------------------


class _PgClient:
    def __init__(self, gid: int, title: str) -> None:
        self.gid = gid
        self.title = title

    async def fetch_gmetadata(self, pairs: list[tuple[int, str]]) -> dict[int, dict[str, object]]:
        assert (self.gid, "tok") in pairs
        return {
            self.gid: {
                "title": self.title,
                "category": "manga",
                "tags": [{"namespace": "artist", "name": "pg-test"}],
                "posted_at": None,
            }
        }


async def _pg_factory():
    try:
        engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _pg_cleanup(factory, *gids: int) -> None:
    async with factory() as session:
        await session.execute(
            text("DELETE FROM gallery_metadata WHERE gid = ANY(:gids)"),
            {"gids": list(gids)},
        )
        await session.commit()


async def _pg_title(factory, gid: int) -> str | None:
    async with factory() as session:
        meta = await GalleryRepository(session).metadata_for_gid(gid)
    return (meta or {}).get("title")


async def test_refresh_gdata_plain_session_persists_pg() -> None:
    """favorites_worker / download_prepare shape: plain session, release + commit."""
    gid = 990_000_000 + uuid.uuid4().int % 1_000_000
    title = "plain-session"
    engine, factory = await _pg_factory()
    await _pg_cleanup(factory, gid)
    try:
        async with factory() as session:
            result = await eh_metadata.refresh_gdata(
                session, [(gid, "tok")], client=_PgClient(gid, title), force=True
            )
        assert result[gid]["title"] == title
        assert await _pg_title(factory, gid) == title
    finally:
        await _pg_cleanup(factory, gid)
        await engine.dispose()


async def test_refresh_gdata_explicit_begin_keeps_prior_write_pg() -> None:
    """Out-of-scope callers still on ``session.begin()`` must not crash.

    The uncommitted gallery_metadata row written before the network call must
    survive: refresh_gdata detects the explicit transaction context and skips
    the release instead of rolling it back.
    """
    gid = 991_000_000 + uuid.uuid4().int % 1_000_000
    prior_gid = gid + 1
    title = "explicit-begin"
    prior_title = "prior-uncommitted"
    engine, factory = await _pg_factory()
    await _pg_cleanup(factory, gid, prior_gid)
    try:
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO gallery_metadata (gid, token, title, tags, updated_at) "
                    "VALUES (:gid, :token, :title, '[]'::jsonb, NOW())"
                ),
                {"gid": prior_gid, "token": "prior", "title": prior_title},
            )
            result = await eh_metadata.refresh_gdata(
                session, [(gid, "tok")], client=_PgClient(gid, title), force=True
            )
            assert result[gid]["title"] == title

        assert await _pg_title(factory, gid) == title
        assert await _pg_title(factory, prior_gid) == prior_title
    finally:
        await _pg_cleanup(factory, gid, prior_gid)
        await engine.dispose()
