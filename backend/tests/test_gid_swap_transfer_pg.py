"""T3.1: real-PostgreSQL proof that a gid swap carries user data over.

Requires the test PostgreSQL; skipped on the host where it is unreachable.  The
disposable-copy test would physically delete gallery files, so this test uses a
row-level finalize with an empty ``storage_path`` (no files to remove) and
verifies every user-owned table afterwards.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from galleryvault.app.state import app_state
from galleryvault.config import get_settings
from galleryvault.db.models import (
    Gallery,
    GalleryUpdate,
    LocalList,
    LocalListItem,
    OnlineReadingProgress,
    ReadingHistory,
    ReadingProgress,
    Series,
    SeriesExclusion,
    SeriesItem,
)
from galleryvault.services import updates_worker
from galleryvault.services.updates_worker import finalize_gallery_update

OLD_PAGE = 7
OLD_TOTAL = 10
NEW_TOTAL = 5
OLD_LAST_READ = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


def _gallery(gid: int, *, page_count: int, token: str, title: str) -> Gallery:
    return Gallery(
        gid=gid,
        token=token,
        title=title,
        storage_type="folder",
        # Falsy on purpose: finalize then has no physical copy to delete.
        storage_path="",
        path_hash=f"t31-{uuid.uuid4().hex}",
        storage_signature="sig",
        page_count=page_count,
        expunged=False,
        trashed=False,
    )


@pytest.mark.asyncio
async def test_finalize_transfers_user_data_to_new_gid(monkeypatch):
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    old_gid = 8_400_000 + uuid.uuid4().int % 100_000
    new_gid = old_gid + 200_000
    gallery_ids: list[int] = []
    series_ids: list[int] = []
    list_id: int | None = None

    # The finalize log writes AppConfig/task history; keep the test DB clean.
    monkeypatch.setattr(updates_worker, "record_gallery_update_log", lambda *a, **k: None)

    original_factory = app_state.session_factory
    app_state.session_factory = factory
    try:
        async with factory() as session, session.begin():
            old_gallery = _gallery(
                old_gid, page_count=OLD_TOTAL, token="oldtok", title="Old"
            )
            new_gallery = _gallery(
                new_gid, page_count=NEW_TOTAL, token="newtok", title="New"
            )
            session.add_all([old_gallery, new_gallery])
            await session.flush()
            gallery_ids = [old_gallery.id, new_gallery.id]
            old_id, new_id = old_gallery.id, new_gallery.id

            update_row = GalleryUpdate(
                gallery_id=old_id,
                old_gid=old_gid,
                new_gid=new_gid,
                new_token="newtok",
                title="Old",
                favcat=1,
                status="downloading",
            )
            session.add(update_row)

            session.add(
                ReadingProgress(
                    gallery_id=old_id, current_page=OLD_PAGE, total_pages=OLD_TOTAL
                )
            )
            session.add(
                ReadingHistory(
                    gallery_id=old_id,
                    current_page=OLD_PAGE,
                    total_pages=OLD_TOTAL,
                    last_read_at=OLD_LAST_READ,
                )
            )
            local_list = LocalList(name=f"t31 {uuid.uuid4().hex[:8]}")
            session.add(local_list)
            await session.flush()
            list_id = local_list.id
            session.add(LocalListItem(list_id=list_id, gallery_id=old_id))

            old_series = Series(
                name=f"t31 old {uuid.uuid4().hex[:8]}",
                match_key=f"t31-old-{uuid.uuid4().hex}",
            )
            auto_series = Series(
                name=f"t31 auto {uuid.uuid4().hex[:8]}",
                match_key=f"t31-auto-{uuid.uuid4().hex}",
            )
            session.add_all([old_series, auto_series])
            await session.flush()
            series_ids = [old_series.id, auto_series.id]
            session.add(SeriesItem(series_id=old_series.id, gallery_id=old_id, source="manual"))
            # The new gallery already has an auto assignment in another series:
            # the old manual one must win.
            session.add(SeriesItem(series_id=auto_series.id, gallery_id=new_id, source="auto"))
            session.add(SeriesExclusion(gallery_id=old_id))

            session.add(
                OnlineReadingProgress(
                    gid=old_gid,
                    token="oldtok",
                    title="Old online",
                    thumb="oldthumb",
                    current_page=OLD_PAGE,
                    total_pages=OLD_TOTAL,
                    updated_at=OLD_LAST_READ,
                )
            )
            await session.flush()
            update_id = update_row.id

        reason = await finalize_gallery_update(
            SimpleNamespace(id=update_id, gallery_id=old_id, new_gid=new_gid)
        )
        assert reason is None

        async with factory() as session:
            # Old version gone, new one kept.
            assert await session.get(Gallery, old_id) is None
            assert await session.get(Gallery, new_id) is not None
            # GalleryUpdate row cascades away with the old gallery.
            assert await session.get(GalleryUpdate, update_id) is None

            # reading_progress: clamped 7 -> 4, total follows the new version.
            assert await session.get(ReadingProgress, old_id) is None
            progress = await session.get(ReadingProgress, new_id)
            assert (progress.current_page, progress.total_pages) == (
                NEW_TOTAL - 1,
                NEW_TOTAL,
            )

            history = await session.scalar(
                select(ReadingHistory).where(ReadingHistory.gallery_id == new_id)
            )
            assert history is not None
            assert (history.current_page, history.total_pages) == (
                NEW_TOTAL - 1,
                NEW_TOTAL,
            )
            assert history.last_read_at == OLD_LAST_READ

            memberships = (
                await session.scalars(
                    select(LocalListItem).where(LocalListItem.gallery_id == new_id)
                )
            ).all()
            assert [m.list_id for m in memberships] == [list_id]

            series_item = await session.get(SeriesItem, new_id)
            assert series_item is not None
            assert series_item.series_id == old_series.id, "manual assignment must win"
            assert series_item.source == "manual"

            assert await session.get(SeriesExclusion, new_id) is not None

            merged = await session.get(OnlineReadingProgress, new_gid)
            assert merged is not None
            assert (merged.current_page, merged.total_pages) == (
                NEW_TOTAL - 1,
                NEW_TOTAL,
            )
            assert merged.token == "newtok", "the new version's metadata wins"
            assert merged.title == "New"
            assert merged.thumb == "oldthumb"
            assert await session.get(OnlineReadingProgress, old_gid) is None
    finally:
        app_state.session_factory = original_factory
        async with factory() as session, session.begin():
            if gallery_ids:
                await session.execute(delete(Gallery).where(Gallery.id.in_(gallery_ids)))
            if series_ids:
                await session.execute(delete(Series).where(Series.id.in_(series_ids)))
            if list_id is not None:
                await session.execute(delete(LocalList).where(LocalList.id == list_id))
            await session.execute(
                delete(OnlineReadingProgress).where(
                    OnlineReadingProgress.gid.in_([old_gid, new_gid])
                )
            )
        await engine.dispose()
