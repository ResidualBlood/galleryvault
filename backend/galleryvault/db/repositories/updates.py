from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DownloadTask, Gallery, GalleryUpdate


class GalleryUpdatesRepository:
    """Tracking for local galleries superseded by re-uploaded ExHentai versions.

    Rows cascade-delete with their gallery, so a finished update (old local copy
    deleted) disappears from the page automatically.  ``failed`` / ``ignored``
    rows keep re-scans idempotent for that gallery.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def detect_many(
        self, entries: Sequence[dict], *, known_gallery_ids: set[int]
    ) -> int:
        """Insert detected updates, skipping galleries that already have a row.

        ``known_gallery_ids`` are gallery_ids that already have any pending /
        failed / ignored row (fetched by the caller); they are not re-inserted
        so repeated scans stay idempotent.
        """
        rows = [
            GalleryUpdate(
                gallery_id=e["gallery_id"],
                old_gid=e["old_gid"],
                new_gid=e["new_gid"],
                new_token=e["new_token"],
                title=e["title"],
                favcat=e["favcat"],
                status=e.get("status") or "pending",
                download_task_id=e.get("download_task_id"),
            )
            for e in entries
            if e["gallery_id"] not in known_gallery_ids
        ]
        if not rows:
            return 0
        self.session.add_all(rows)
        return len(rows)

    async def list_page(
        self,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[int, list[GalleryUpdate]]:
        query = select(GalleryUpdate)
        if status:
            query = query.where(GalleryUpdate.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(GalleryUpdate.detected_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def tracked_gallery_ids(self) -> set[int]:
        """gallery_ids with any pending/failed/ignored row (skip re-detect)."""
        rows = await self.session.scalars(select(GalleryUpdate.gallery_id))
        return {int(r) for r in rows.all()}

    async def tracking_by_gallery_id(self) -> dict[int, GalleryUpdate]:
        rows = await self.session.scalars(select(GalleryUpdate))
        return {int(r.gallery_id): r for r in rows.all()}

    async def local_new_gids(self, gids: list[int]) -> set[int]:
        if not gids:
            return set()
        rows = await self.session.scalars(
            select(Gallery.gid).where(
                Gallery.gid.in_(list(dict.fromkeys(int(g) for g in gids))),
                Gallery.expunged.is_(False),
            )
        )
        return {int(gid) for gid in rows.all() if gid is not None}

    async def active_task_ids_for_gids(self, gids: list[int]) -> dict[int, int]:
        if not gids:
            return {}
        rows = await self.session.execute(
            select(DownloadTask.gid, DownloadTask.id).where(
                DownloadTask.gid.in_(list(dict.fromkeys(int(g) for g in gids))),
                DownloadTask.status.in_(["pending", "downloading"]),
            )
        )
        return {int(gid): int(task_id) for gid, task_id in rows.all()}

    async def attach_download(self, new_gid: int, task_id: int) -> int:
        result = await self.session.execute(
            update(GalleryUpdate)
            .where(
                GalleryUpdate.new_gid == int(new_gid),
                GalleryUpdate.status.in_(["pending", "failed"]),
            )
            .values(
                status="downloading",
                download_task_id=int(task_id),
                error_message=None,
                updated_at=datetime.now(UTC),
            )
        )
        return int(result.rowcount or 0)

    async def actionable_by_new_gid(self, new_gid: int) -> list[GalleryUpdate]:
        rows = await self.session.scalars(
            select(GalleryUpdate).where(
                GalleryUpdate.new_gid == int(new_gid),
                GalleryUpdate.status.in_(["pending", "downloading", "failed"]),
            )
        )
        return list(rows.all())

    async def get(self, update_id: int) -> GalleryUpdate | None:
        return await self.session.get(GalleryUpdate, update_id)

    async def by_new_gids(self, gids: list[int]) -> list[GalleryUpdate | None]:
        """Update rows keyed by their new (re-uploaded) gid."""
        if not gids:
            return []
        rows = await self.session.execute(
            select(GalleryUpdate).where(GalleryUpdate.new_gid.in_(list(dict.fromkeys(gids))))
        )
        by_gid = {int(row.new_gid): row for row in rows.scalars()}
        return [by_gid.get(int(g)) for g in gids]

    async def mark_downloading(self, update_id: int, task_id: int) -> bool:
        row = await self.session.get(GalleryUpdate, update_id)
        if row is None or row.status != "pending":
            return False
        row.status = "downloading"
        row.download_task_id = task_id
        row.updated_at = datetime.now(UTC)
        return True

    async def mark_failed(self, update_id: int, error: str | None) -> bool:
        row = await self.session.get(GalleryUpdate, update_id)
        if row is None:
            return False
        row.status = "failed"
        row.error_message = error
        row.updated_at = datetime.now(UTC)
        return True

    async def mark_failed_by_task(self, task_id: int, error: str | None) -> int:
        """Fail gallery-update rows referencing a removed download task.

        Deleting a download task leaves the ``gallery_updates`` row stuck in
        ``downloading`` (the finalize loop would never see the task).  Mark
        them failed so the user can retry or ignore the update.
        """
        result = await self.session.execute(
            update(GalleryUpdate)
            .where(
                GalleryUpdate.download_task_id == task_id,
                GalleryUpdate.status == "downloading",
            )
            .values(status="failed", error_message=error, updated_at=datetime.now(UTC))
        )
        return int(result.rowcount or 0)

    async def mark_ignored(self, ids: Sequence[int]) -> int:
        if not ids:
            return 0
        result = await self.session.execute(
            update(GalleryUpdate)
            .where(
                GalleryUpdate.id.in_(list(ids)),
                GalleryUpdate.status.in_(["pending", "downloading", "failed"]),
            )
            .values(status="ignored", updated_at=datetime.now(UTC))
        )
        return int(result.rowcount or 0)

    async def unignore(self, ids: Sequence[int]) -> int:
        if not ids:
            return 0
        result = await self.session.execute(
            update(GalleryUpdate)
            .where(GalleryUpdate.id.in_(list(ids)), GalleryUpdate.status == "ignored")
            .values(status="pending", updated_at=datetime.now(UTC))
        )
        return int(result.rowcount or 0)

    async def delete_many(self, ids: Sequence[int]) -> int:
        """Permanently remove gallery-update rows.

        Only rows that are not mid-download are deletable: a ``downloading``
        row has a live download task whose finalize loop would look the row up
        by id, so removing it would orphan that task.  The frontend only shows
        the delete action for failed rows; this guard also protects against
        future callers.
        """
        if not ids:
            return 0
        result = await self.session.execute(
            delete(GalleryUpdate).where(
                GalleryUpdate.id.in_(list(ids)),
                GalleryUpdate.status.in_(["failed", "ignored", "pending"]),
            )
        )
        return int(result.rowcount or 0)

    async def downloading(self) -> list[GalleryUpdate]:
        rows = await self.session.scalars(
            select(GalleryUpdate).where(GalleryUpdate.status == "downloading")
        )
        return list(rows.all())


