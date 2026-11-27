"""Transfer user-owned rows when a gallery is replaced by a newer gid (T3.1).

``finalize_gallery_update`` deletes the old ``galleries`` row; nine child tables
reference it with ``ON DELETE CASCADE``, so without an explicit transfer the
user's reading progress, history, list membership, series membership and series
exclusions vanish with it.  ``online_reading_progress`` is keyed by ExHentai
``gid`` and has no foreign key, so its old row would silently become a dead row.

Every statement below is a set-based ``INSERT ... SELECT`` upsert so that:

* the transfer is one round trip per table and stays inside the caller's
  transaction (finalize wraps it together with the delete), and
* N old galleries -> one new gallery is order independent: ``GREATEST`` keeps the
  furthest page and the newest timestamp regardless of the order the old rows are
  visited in.

Content that belongs to the old version (``gallery_tags``, ``gallery_pages``,
``gallery_updates``, ``background_jobs``, ``duplicate_records``) is deliberately
not migrated.  ``favorite_items.note`` is a cloud mirror and is not migrated
either (decision Q7).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Gallery,
    LocalListItem,
    OnlineReadingProgress,
    ReadingHistory,
    ReadingProgress,
    SeriesExclusion,
    SeriesItem,
)
from .galleries_common import _dialect_insert, _session_dialect

logger = logging.getLogger(__name__)


def _least(session: AsyncSession, left: Any, right: Any) -> Any:
    """``LEAST`` on PostgreSQL, ``MIN`` on SQLite (unit-test doubles)."""
    if _session_dialect(session) == "sqlite":
        return func.min(left, right)
    return func.least(left, right)


def _max_page(new_page_count: int) -> int:
    return max(int(new_page_count) - 1, 0)


def reading_progress_transfer_stmt(
    session: AsyncSession,
    *,
    old_gallery_id: int,
    new_gallery_id: int,
    new_page_count: int,
) -> Any:
    """Carry the old progress onto the new gallery, clamped to its page count.

    ``current_page`` is clamped with ``LEAST(old, new_page_count - 1)`` and then
    combined with ``GREATEST(existing, clamped)`` so the replacement never loses
    the furthest page already recorded for it.  ``total_pages`` follows the new
    version (it is what the reader will show) and ``updated_at`` is the newest of
    the two.
    """
    insert_stmt, greatest = _dialect_insert(session, ReadingProgress)
    ins = insert_stmt.from_select(
        ["gallery_id", "current_page", "total_pages", "updated_at"],
        select(
            literal(new_gallery_id, type_=ReadingProgress.gallery_id.type),
            _least(
                session,
                ReadingProgress.current_page,
                literal(
                    _max_page(new_page_count),
                    type_=ReadingProgress.current_page.type,
                ),
            ),
            literal(new_page_count, type_=ReadingProgress.total_pages.type),
            ReadingProgress.updated_at,
        ).where(ReadingProgress.gallery_id == old_gallery_id),
    )
    return ins.on_conflict_do_update(
        index_elements=[ReadingProgress.gallery_id],
        set_={
            "current_page": greatest(
                ReadingProgress.current_page, ins.excluded.current_page
            ),
            "total_pages": ins.excluded.total_pages,
            "updated_at": greatest(ReadingProgress.updated_at, ins.excluded.updated_at),
        },
    )


def reading_history_transfer_stmt(
    session: AsyncSession,
    *,
    old_gallery_id: int,
    new_gallery_id: int,
    new_page_count: int,
) -> Any:
    """Carry history rows over; ``reading_history`` is unique per ``gallery_id``."""
    insert_stmt, greatest = _dialect_insert(session, ReadingHistory)
    ins = insert_stmt.from_select(
        ["gallery_id", "current_page", "total_pages", "last_read_at"],
        select(
            literal(new_gallery_id, type_=ReadingHistory.gallery_id.type),
            _least(
                session,
                ReadingHistory.current_page,
                literal(
                    _max_page(new_page_count),
                    type_=ReadingHistory.current_page.type,
                ),
            ),
            literal(new_page_count, type_=ReadingHistory.total_pages.type),
            ReadingHistory.last_read_at,
        ).where(ReadingHistory.gallery_id == old_gallery_id),
    )
    return ins.on_conflict_do_update(
        index_elements=[ReadingHistory.gallery_id],
        set_={
            "current_page": greatest(
                ReadingHistory.current_page, ins.excluded.current_page
            ),
            "total_pages": ins.excluded.total_pages,
            "last_read_at": greatest(
                ReadingHistory.last_read_at, ins.excluded.last_read_at
            ),
        },
    )


def local_list_items_transfer_stmt(
    session: AsyncSession, *, old_gallery_id: int, new_gallery_id: int
) -> Any:
    """Keep the gallery in every local list it belonged to."""
    insert_stmt, _greatest = _dialect_insert(session, LocalListItem)
    ins = insert_stmt.from_select(
        ["list_id", "gallery_id"],
        select(
            LocalListItem.list_id,
            literal(new_gallery_id, type_=LocalListItem.gallery_id.type),
        ).where(LocalListItem.gallery_id == old_gallery_id),
    )
    return ins.on_conflict_do_nothing(index_elements=["list_id", "gallery_id"])


def series_items_transfer_stmt(
    session: AsyncSession, *, old_gallery_id: int, new_gallery_id: int
) -> Any:
    """Keep series membership, preferring a manual assignment over an auto one.

    * new gallery has no row -> the old row is copied verbatim (``source`` kept);
    * new gallery has an ``auto`` row and the old one is ``manual`` -> the manual
      row wins (series and source are replaced);
    * otherwise the existing new row is kept.
    """
    insert_stmt, _greatest = _dialect_insert(session, SeriesItem)
    ins = insert_stmt.from_select(
        ["series_id", "gallery_id", "source"],
        select(
            SeriesItem.series_id,
            literal(new_gallery_id, type_=SeriesItem.gallery_id.type),
            SeriesItem.source,
        ).where(SeriesItem.gallery_id == old_gallery_id),
    )
    return ins.on_conflict_do_update(
        index_elements=[SeriesItem.gallery_id],
        set_={"series_id": ins.excluded.series_id, "source": ins.excluded.source},
        where=(SeriesItem.source == "auto") & (ins.excluded.source == "manual"),
    )


def series_exclusions_transfer_stmt(
    session: AsyncSession, *, old_gallery_id: int, new_gallery_id: int
) -> Any:
    """Keep a user's "not part of this series" marker; never override a new one."""
    insert_stmt, _greatest = _dialect_insert(session, SeriesExclusion)
    ins = insert_stmt.from_select(
        ["gallery_id"],
        select(literal(new_gallery_id, type_=SeriesExclusion.gallery_id.type)).where(
            SeriesExclusion.gallery_id == old_gallery_id
        ),
    )
    return ins.on_conflict_do_nothing(index_elements=[SeriesExclusion.gallery_id])


def online_progress_merge_stmt(
    session: AsyncSession,
    *,
    old_gid: int,
    new_gid: int,
    token: str,
    title: str | None,
    thumb: str | None,
    new_page_count: int,
) -> Any:
    """Merge the old gid's online progress into the new gid (new metadata wins).

    ``token``/``title``/``thumb`` come from the new version; the page is clamped
    like ``reading_progress`` and the timestamp is the newest of the two.
    """
    insert_stmt, greatest = _dialect_insert(session, OnlineReadingProgress)
    ins = insert_stmt.from_select(
        ["gid", "token", "title", "thumb", "current_page", "total_pages", "updated_at"],
        select(
            literal(new_gid, type_=OnlineReadingProgress.gid.type),
            literal(token, type_=OnlineReadingProgress.token.type),
            literal(title, type_=OnlineReadingProgress.title.type),
            literal(thumb, type_=OnlineReadingProgress.thumb.type),
            _least(
                session,
                OnlineReadingProgress.current_page,
                literal(
                    _max_page(new_page_count),
                    type_=OnlineReadingProgress.current_page.type,
                ),
            ),
            literal(new_page_count, type_=OnlineReadingProgress.total_pages.type),
            func.coalesce(OnlineReadingProgress.updated_at, func.now()),
        ).where(OnlineReadingProgress.gid == old_gid),
    )
    return ins.on_conflict_do_update(
        index_elements=[OnlineReadingProgress.gid],
        set_={
            "token": ins.excluded.token,
            "title": ins.excluded.title,
            "thumb": ins.excluded.thumb,
            "current_page": greatest(
                OnlineReadingProgress.current_page, ins.excluded.current_page
            ),
            "total_pages": ins.excluded.total_pages,
            "updated_at": greatest(
                OnlineReadingProgress.updated_at, ins.excluded.updated_at
            ),
        },
    )


def online_progress_delete_stmt(session: AsyncSession, *, old_gid: int) -> Any:
    """Drop the dead old-gid row once it has been merged."""
    del session  # signature symmetry with the builders; DELETE needs no dialect
    return delete(OnlineReadingProgress).where(OnlineReadingProgress.gid == old_gid)


async def transfer_user_data(
    session: AsyncSession,
    old_gallery_id: int,
    new_gallery_id: int,
    old_gid: int | None,
    new_gid: int | None,
) -> dict[str, int]:
    """Move every user-owned row from the old gallery to the new one.

    Must run in the same transaction as, and before, deleting the old
    ``galleries`` row.  Returns a per-table count of what was transferred
    (used for logging).

    Sessions without ``execute`` are test doubles that cannot run set-based SQL;
    they get an empty result instead of an attribute error (same idiom as
    :mod:`galleries_progress`).
    """
    if not callable(getattr(session, "execute", None)):
        return {}

    moved: dict[str, int] = {}
    new_gallery = await session.get(Gallery, new_gallery_id)
    page_count = getattr(new_gallery, "page_count", None)
    page_count_ok = page_count is not None and int(page_count) > 0

    if page_count_ok:
        if await session.get(ReadingProgress, old_gallery_id) is not None:
            await session.execute(
                reading_progress_transfer_stmt(
                    session,
                    old_gallery_id=old_gallery_id,
                    new_gallery_id=new_gallery_id,
                    new_page_count=int(page_count),
                )
            )
            moved["reading_progress"] = 1
        if await _reading_history_exists(session, old_gallery_id):
            await session.execute(
                reading_history_transfer_stmt(
                    session,
                    old_gallery_id=old_gallery_id,
                    new_gallery_id=new_gallery_id,
                    new_page_count=int(page_count),
                )
            )
            moved["reading_history"] = 1
    else:
        logger.warning(
            "skipping reading progress/history transfer: no new page count",
            extra={
                "old_gallery_id": old_gallery_id,
                "new_gallery_id": new_gallery_id,
                "page_count": page_count,
            },
        )

    list_count = await _local_list_item_count(session, old_gallery_id)
    if list_count:
        await session.execute(
            local_list_items_transfer_stmt(
                session,
                old_gallery_id=old_gallery_id,
                new_gallery_id=new_gallery_id,
            )
        )
        moved["local_list_items"] = list_count

    if await session.get(SeriesItem, old_gallery_id) is not None:
        await session.execute(
            series_items_transfer_stmt(
                session,
                old_gallery_id=old_gallery_id,
                new_gallery_id=new_gallery_id,
            )
        )
        moved["series_items"] = 1

    if await session.get(SeriesExclusion, old_gallery_id) is not None:
        await session.execute(
            series_exclusions_transfer_stmt(
                session,
                old_gallery_id=old_gallery_id,
                new_gallery_id=new_gallery_id,
            )
        )
        moved["series_exclusions"] = 1

    if page_count_ok and old_gid is not None and new_gid is not None:
        old_online = await session.get(OnlineReadingProgress, old_gid)
        if old_online is not None:
            await session.execute(
                online_progress_merge_stmt(
                    session,
                    old_gid=old_gid,
                    new_gid=new_gid,
                    token=getattr(new_gallery, "token", None) or old_online.token,
                    title=getattr(new_gallery, "title", None) or old_online.title,
                    thumb=old_online.thumb,
                    new_page_count=int(page_count),
                )
            )
            if old_gid != new_gid:
                await session.execute(
                    online_progress_delete_stmt(session, old_gid=old_gid)
                )
            moved["online_reading_progress"] = 1

    return moved


async def _reading_history_exists(session: AsyncSession, gallery_id: int) -> bool:
    row = await session.scalar(
        select(ReadingHistory.id).where(ReadingHistory.gallery_id == gallery_id)
    )
    return row is not None


async def _local_list_item_count(session: AsyncSession, gallery_id: int) -> int:
    rows = (
        await session.scalars(
            select(LocalListItem.list_id).where(LocalListItem.gallery_id == gallery_id)
        )
    ).all()
    return len(rows)
