"""Persistence for reading progress of online galleries absent from the library.

Online galleries have no ``galleries`` row, so they cannot use
``reading_progress`` (primary key ``gallery_id`` foreign-keyed to
``galleries.id``). ``online_reading_progress`` is keyed by ExHentai ``gid`` and
stores only the page counter plus identity/thumbnail metadata: resolved
page-image URLs are short-lived per-request values and must never be persisted.

``save`` mirrors ``GalleryProgressMixin.advance_progress`` so the online reader
and the local reader agree on the page rule: the stored page never moves
backwards, which makes late debounced writes harmless. ``updated_at`` is only
refreshed when the incoming page is at least the stored page, so a stale write
cannot reorder the online history list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select

from ..models import OnlineReadingProgress
from .galleries_common import _dialect_insert, _session_dialect


class OnlineProgressRepository:
    """Online reading progress/history backed by ``online_reading_progress``."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def get(self, gid: int) -> OnlineReadingProgress | None:
        return await self.session.get(OnlineReadingProgress, gid)

    async def history(
        self, offset: int, limit: int
    ) -> tuple[list[OnlineReadingProgress], int]:
        rows = (
            await self.session.execute(
                select(OnlineReadingProgress)
                .order_by(
                    OnlineReadingProgress.updated_at.desc(),
                    OnlineReadingProgress.gid.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(OnlineReadingProgress)
            )
        ).scalar_one()
        return list(rows), int(total or 0)

    async def save(
        self,
        gid: int,
        *,
        token: str,
        page: int,
        total_pages: int | None = None,
        title: str | None = None,
        thumb: str | None = None,
    ) -> tuple[OnlineReadingProgress, bool]:
        """Upsert progress without ever moving the stored page backwards.

        Returns the persisted row and whether this request's page was accepted
        (i.e. the stored page is at least the requested one).
        """
        if not callable(getattr(self.session, "execute", None)) or not _session_dialect(
            self.session
        ):
            return await self._save_read_modify_write(
                gid,
                token=token,
                page=page,
                total_pages=total_pages,
                title=title,
                thumb=thumb,
            )

        insert_stmt, greatest = _dialect_insert(self.session, OnlineReadingProgress)
        values = insert_stmt.values(
            gid=gid,
            token=token,
            title=title,
            thumb=thumb,
            current_page=page,
            total_pages=total_pages,
            updated_at=datetime.now(UTC),
        )
        excluded = values.excluded
        advancing = excluded.current_page > OnlineReadingProgress.current_page
        refreshing = excluded.current_page >= OnlineReadingProgress.current_page
        stmt = values.on_conflict_do_update(
            index_elements=[OnlineReadingProgress.gid],
            set_={
                "token": excluded.token,
                "title": func.coalesce(excluded.title, OnlineReadingProgress.title),
                "thumb": func.coalesce(excluded.thumb, OnlineReadingProgress.thumb),
                "current_page": greatest(
                    OnlineReadingProgress.current_page, excluded.current_page
                ),
                "total_pages": case(
                    (
                        advancing,
                        func.coalesce(
                            excluded.total_pages, OnlineReadingProgress.total_pages
                        ),
                    ),
                    else_=OnlineReadingProgress.total_pages,
                ),
                "updated_at": case(
                    (refreshing, excluded.updated_at),
                    else_=OnlineReadingProgress.updated_at,
                ),
            },
        ).returning(
            OnlineReadingProgress.gid,
            OnlineReadingProgress.token,
            OnlineReadingProgress.title,
            OnlineReadingProgress.thumb,
            OnlineReadingProgress.current_page,
            OnlineReadingProgress.total_pages,
            OnlineReadingProgress.updated_at,
        )
        (
            stored_gid,
            stored_token,
            stored_title,
            stored_thumb,
            stored_page,
            stored_total,
            stored_at,
        ) = (await self.session.execute(stmt)).one()
        row = OnlineReadingProgress(
            gid=stored_gid,
            token=stored_token,
            title=stored_title,
            thumb=stored_thumb,
            current_page=stored_page,
            total_pages=stored_total,
            updated_at=stored_at,
        )
        return row, int(stored_page or 0) >= page

    async def _save_read_modify_write(
        self,
        gid: int,
        *,
        token: str,
        page: int,
        total_pages: int | None,
        title: str | None,
        thumb: str | None,
    ) -> tuple[OnlineReadingProgress, bool]:
        """Fallback for fake sessions without a usable bind/dialect.

        Production sessions always take the atomic upsert above; this keeps the
        same monotonic contract for unit-test doubles.
        """
        row = await self.session.get(OnlineReadingProgress, gid)
        now = datetime.now(UTC)
        if row is None:
            row = OnlineReadingProgress(
                gid=gid,
                token=token,
                title=title,
                thumb=thumb,
                current_page=page,
                total_pages=total_pages,
                updated_at=now,
            )
            self.session.add(row)
            await self.session.flush()
            return row, True

        stored = int(row.current_page or 0)
        accepted = page >= stored
        if accepted:
            if page > stored:
                row.current_page = page
                if total_pages is not None:
                    row.total_pages = total_pages
            elif total_pages is not None and row.total_pages is None:
                row.total_pages = total_pages
            row.updated_at = now
        row.token = token
        if title:
            row.title = title
        if thumb:
            row.thumb = thumb
        await self.session.flush()
        return row, accepted
