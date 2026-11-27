"""T6.1/T6.1b: release-before-network integration against real PostgreSQL.

These tests need the test container (real asyncpg).  Host runs without a
database skip them; ``ctest.sh test`` must report them as passed, not skipped.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from galleryvault.app.state import app_state
from galleryvault.config import get_settings
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.services import eh_metadata, favorites_worker


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


async def test_favorites_worker_metadata_no_idle_in_transaction_pg() -> None:
    """The real favorites_worker callsite must not hold a connection over gdata.

    ``favorites_metadata`` opens a plain session (no explicit ``begin()``); on
    the baseline that session sat "idle in transaction" for the whole network
    call.  The client probes ``pg_stat_activity`` for the session's backend PID
    while it is "fetching".
    """
    gid = 992_000_000 + uuid.uuid4().int % 1_000_000
    title = "favorites-worker-shape"
    engine, factory = await _pg_factory()
    await _pg_cleanup(factory, gid)
    captured: dict[str, int] = {}
    states: list[str | None] = []

    class _Client:
        async def fetch_gmetadata(
            self, pairs: list[tuple[int, str]]
        ) -> dict[int, dict[str, object]]:
            async with engine.connect() as conn:
                state = await conn.scalar(
                    text("SELECT state FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": captured["pid"]},
                )
            states.append(state)
            return {
                gid: {
                    "title": title,
                    "category": "manga",
                    "tags": [{"namespace": "artist", "name": "pg-test"}],
                    "posted_at": None,
                }
            }

    @asynccontextmanager
    async def _capturing_factory():
        async with factory() as session:
            # This read autobegins a transaction, exactly like refresh_gdata's
            # own cache read; refresh_gdata must release it before the network.
            captured["pid"] = int(
                await session.scalar(text("SELECT pg_backend_pid()"))
            )
            yield session

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    try:
        app_state.session_factory = _capturing_factory
        app_state.eh_client = _Client()
        result = await favorites_worker.favorites_metadata([(gid, "tok")])
        persisted = await _pg_title(factory, gid)
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        await _pg_cleanup(factory, gid)
        await engine.dispose()

    assert result[gid]["title"] == title
    assert states and states[0] != "idle in transaction"
    assert persisted == title


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
