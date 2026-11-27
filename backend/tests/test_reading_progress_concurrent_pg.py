"""T9.2d: two concurrent first progress writes on a real PostgreSQL.

``advance_progress`` / ``record_history`` are single ``INSERT .. ON CONFLICT DO
UPDATE`` statements.  With no existing rows both requests race to insert the
same ``gallery_id``; PostgreSQL must resolve the conflict (one waits for the
other's commit) instead of raising ``IntegrityError``, and the furthest page
plus exactly one history row must survive.

Requires the test PostgreSQL; skipped where it is unreachable (host runs).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from galleryvault.config import get_settings
from galleryvault.db.models import Gallery, ReadingHistory, ReadingProgress
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.db.session import safe_transaction

FIRST_PAGE = 3
FURTHEST_PAGE = 7
TOTAL_PAGES = 10


def _gallery(gid: int) -> Gallery:
    return Gallery(
        gid=gid,
        token="t92dtok",
        title="Concurrent progress",
        storage_type="folder",
        storage_path="",
        path_hash=f"t92d-{uuid.uuid4().hex}",
        storage_signature="sig",
        page_count=TOTAL_PAGES,
        expunged=False,
        trashed=False,
    )


async def _first_write(
    factory: async_sessionmaker,
    gallery_id: int,
    page: int,
    ready: asyncio.Event,
    go: asyncio.Event,
) -> int:
    async with factory() as session:
        ready.set()
        await go.wait()
        async with safe_transaction(session):
            repo = GalleryRepository(session)
            progress, _advanced = await repo.advance_progress(
                gallery_id, page, TOTAL_PAGES
            )
            await repo.record_history(
                gallery_id, progress.current_page, progress.total_pages
            )
            return progress.current_page


async def test_concurrent_first_progress_write_keeps_furthest_page_and_one_history():
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    gid = 8_500_000 + uuid.uuid4().int % 100_000
    gallery_id: int | None = None
    try:
        async with factory() as session, session.begin():
            gallery = _gallery(gid)
            session.add(gallery)
            await session.flush()
            gallery_id = gallery.id

        ready = [asyncio.Event(), asyncio.Event()]
        go = asyncio.Event()

        async def run(page: int, index: int) -> int:
            return await _first_write(factory, gallery_id, page, ready[index], go)

        tasks = [
            asyncio.create_task(run(FIRST_PAGE, 0)),
            asyncio.create_task(run(FURTHEST_PAGE, 1)),
        ]
        await ready[0].wait()
        await ready[1].wait()
        go.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        failures = [r for r in results if isinstance(r, BaseException)]
        assert failures == [], failures

        async with factory() as session:
            progress = await session.get(ReadingProgress, gallery_id)
            assert progress is not None
            assert progress.current_page == FURTHEST_PAGE
            assert progress.total_pages == TOTAL_PAGES

            history_count = await session.scalar(
                select(func.count())
                .select_from(ReadingHistory)
                .where(ReadingHistory.gallery_id == gallery_id)
            )
            history = await session.scalar(
                select(ReadingHistory).where(ReadingHistory.gallery_id == gallery_id)
            )
            assert history_count == 1
            assert history.current_page == FURTHEST_PAGE
    finally:
        if gallery_id is not None:
            async with factory() as session, session.begin():
                await session.execute(delete(Gallery).where(Gallery.id == gallery_id))
        await engine.dispose()
