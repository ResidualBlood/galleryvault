"""Reading progress / history methods of ``GalleryRepository`` (mixins split).

Pure move out of ``db.repositories.galleries``: the eight reading-state methods
now live on ``GalleryProgressMixin`` so the repository can be assembled from
focused mixins while keeping a single concrete class (class-attribute
monkeypatches such as ``GalleryRepository.clear_history`` keep working).

The mixin only relies on ``self.session`` (an ``AsyncSession`` or a test
double); it never touches ``model_cls`` or other repository state, so it can be
mixed into any repository exposing a session.
"""

from datetime import UTC, datetime

from sqlalchemy import case, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ReadingHistory, ReadingProgress
from .galleries_common import _dialect_insert


class GalleryProgressMixin:
    """Reading progress and history persistence (requires ``self.session``)."""

    session: AsyncSession

    async def upsert_progress(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> ReadingProgress:
        row = await self.session.get(ReadingProgress, gallery_id)
        if row is None:
            row = ReadingProgress(
                gallery_id=gallery_id, current_page=current_page, total_pages=total_pages
            )
            self.session.add(row)
        else:
            row.current_page, row.total_pages, row.updated_at = (
                current_page,
                total_pages,
                datetime.now(UTC),
            )
        await self.session.flush()
        return row

    async def advance_progress(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> tuple[ReadingProgress, bool]:
        """Upsert reading progress without ever moving it backwards.

        Late-arriving requests (debounced writer, first-render save, webtoon
        observer) can carry a page older than the stored one; keeping the
        furthest page makes those writes harmless.  The write is one
        ``INSERT .. ON CONFLICT DO UPDATE`` using ``GREATEST`` so two concurrent
        requests cannot lose the furthest page the way read-then-write can.
        Returns the persisted row and whether the caller's page was accepted.
        """
        if not callable(getattr(self.session, "execute", None)):
            return await self._advance_progress_read_modify_write(
                gallery_id, current_page, total_pages
            )
        insert_stmt, greatest = _dialect_insert(self.session, ReadingProgress)
        insert_stmt = insert_stmt.values(
            gallery_id=gallery_id,
            current_page=current_page,
            total_pages=total_pages,
            updated_at=datetime.now(UTC),
        )
        advancing = insert_stmt.excluded.current_page > ReadingProgress.current_page
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[ReadingProgress.gallery_id],
            set_={
                "current_page": greatest(
                    ReadingProgress.current_page, insert_stmt.excluded.current_page
                ),
                "total_pages": case(
                    (advancing, insert_stmt.excluded.total_pages),
                    else_=ReadingProgress.total_pages,
                ),
                "updated_at": case(
                    (advancing, insert_stmt.excluded.updated_at),
                    else_=ReadingProgress.updated_at,
                ),
            },
        ).returning(
            ReadingProgress.gallery_id,
            ReadingProgress.current_page,
            ReadingProgress.total_pages,
            ReadingProgress.updated_at,
        )
        stored_gid, stored_page, stored_total, stored_updated = (
            await self.session.execute(stmt)
        ).one()
        row = ReadingProgress(
            gallery_id=stored_gid,
            current_page=stored_page,
            total_pages=stored_total,
            updated_at=stored_updated,
        )
        return row, int(stored_page or 0) <= current_page

    async def _advance_progress_read_modify_write(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> tuple[ReadingProgress, bool]:
        """Fallback for fake sessions implementing only ``get``/``add``/``flush``.

        Production sessions always expose ``execute`` and take the atomic path
        above; this keeps the read-modify-write contract for unit-test doubles.
        """
        row = await self.session.get(ReadingProgress, gallery_id)
        advanced = False
        if row is None:
            row = ReadingProgress(
                gallery_id=gallery_id, current_page=current_page, total_pages=total_pages
            )
            self.session.add(row)
            advanced = True
        elif current_page > int(row.current_page or 0):
            row.current_page, row.total_pages, row.updated_at = (
                current_page,
                total_pages,
                datetime.now(UTC),
            )
            advanced = True
        await self.session.flush()
        return row, advanced

    async def record_history(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> ReadingHistory:
        """Upsert the single history row for a gallery.

        ``reading_history`` has a unique ``gallery_id`` constraint, so two
        concurrent first saves used to race between the SELECT and the INSERT.
        The upsert keeps that race in the same transaction as the progress
        write (and never moves the recorded page backwards).
        """
        if not callable(getattr(self.session, "execute", None)):
            return await self._record_history_read_modify_write(
                gallery_id, current_page, total_pages
            )
        insert_stmt, greatest = _dialect_insert(self.session, ReadingHistory)
        insert_stmt = insert_stmt.values(
            gallery_id=gallery_id,
            current_page=current_page,
            total_pages=total_pages,
            last_read_at=datetime.now(UTC),
        )
        advancing = insert_stmt.excluded.current_page > ReadingHistory.current_page
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[ReadingHistory.gallery_id],
            set_={
                "current_page": greatest(
                    ReadingHistory.current_page, insert_stmt.excluded.current_page
                ),
                "total_pages": case(
                    (advancing, insert_stmt.excluded.total_pages),
                    else_=ReadingHistory.total_pages,
                ),
                "last_read_at": insert_stmt.excluded.last_read_at,
            },
        ).returning(
            ReadingHistory.id,
            ReadingHistory.gallery_id,
            ReadingHistory.current_page,
            ReadingHistory.total_pages,
            ReadingHistory.last_read_at,
        )
        stored = (await self.session.execute(stmt)).one()
        return ReadingHistory(
            id=stored.id,
            gallery_id=stored.gallery_id,
            current_page=stored.current_page,
            total_pages=stored.total_pages,
            last_read_at=stored.last_read_at,
        )

    async def _record_history_read_modify_write(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> ReadingHistory:
        """Fallback for fake sessions without ``execute`` (see above)."""
        row = await self.session.scalar(
            select(ReadingHistory).where(ReadingHistory.gallery_id == gallery_id)
        )
        if row is None:
            row = ReadingHistory(
                gallery_id=gallery_id, current_page=current_page, total_pages=total_pages
            )
            self.session.add(row)
        else:
            row.current_page, row.total_pages, row.last_read_at = (
                current_page,
                total_pages,
                datetime.now(UTC),
            )
        await self.session.flush()
        return row

    async def clear_history(self) -> None:
        await self.session.execute(delete(ReadingHistory))

    async def clear_progress(self) -> None:
        await self.session.execute(delete(ReadingProgress))

    async def delete_progress(self, gallery_id: int) -> bool:
        deleted = False
        row = await self.session.get(ReadingProgress, gallery_id)
        if row is not None:
            await self.session.delete(row)
            deleted = True
        hist = await self.session.scalar(
            select(ReadingHistory).where(ReadingHistory.gallery_id == gallery_id)
        )
        if hist is not None:
            await self.session.delete(hist)
            deleted = True
        return deleted
