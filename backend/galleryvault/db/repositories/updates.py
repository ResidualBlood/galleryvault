from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DownloadTask, FavoriteItem, Gallery, GalleryMetadata, GalleryUpdate
from .base import count_select

#: ``list_page`` status marker for "everything the user still has to act on",
#: i.e. every row except ``ignored``.  Kept separate from the real row statuses
#: so the filter stays in SQL instead of being applied after pagination.
ACTIVE_STATE = "active"


def _build_list_query(status: str | None):
    """SELECT backing both the count and the page of ``list_page``."""
    query = select(GalleryUpdate)
    if status == ACTIVE_STATE:
        query = query.where(GalleryUpdate.status != "ignored")
    elif status:
        query = query.where(GalleryUpdate.status == status)
    return query


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
                error_message=e.get("error_message"),
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
        query = _build_list_query(status)
        total = await count_select(self.session, query)
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
                Gallery.trashed.is_(False),
            )
        )
        return {int(gid) for gid in rows.all() if gid is not None}

    async def gallery_gids(self, gallery_ids: Sequence[int]) -> dict[int, int]:
        """Map ``galleries.id`` to the ExHentai gid for the given local rows."""
        if not gallery_ids:
            return {}
        rows = await self.session.execute(
            select(Gallery.id, Gallery.gid).where(
                Gallery.id.in_(list(dict.fromkeys(int(i) for i in gallery_ids)))
            )
        )
        return {int(row_id): int(gid) for row_id, gid in rows.all() if gid is not None}

    async def replacement_chain_pairs(
        self, pairs: Sequence[tuple[int, int]]
    ) -> set[tuple[int, int]]:
        """Return the ``(old_gid, new_gid)`` pairs backed by an official link.

        ExHentai records re-uploads as ``parent`` (new -> old) and ``replaces``
        (old -> new) relations in the cached gdata metadata (``parent_gid`` /
        ``newer_gid``).  Only those links are evidence that a title match is a
        real replacement; a normalized-title match alone is not.
        """
        if not pairs:
            return set()
        gids = {int(gid) for pair in pairs for gid in pair}
        rows = await self.session.execute(
            select(
                GalleryMetadata.gid,
                GalleryMetadata.parent_gid,
                GalleryMetadata.newer_gid,
            ).where(GalleryMetadata.gid.in_(list(gids)))
        )
        meta = {int(gid): (parent, newer) for gid, parent, newer in rows.all()}
        chained: set[tuple[int, int]] = set()
        for old_gid, new_gid in pairs:
            old_gid, new_gid = int(old_gid), int(new_gid)
            parent, _ = meta.get(new_gid, (None, None))
            _, newer = meta.get(old_gid, (None, None))
            if (parent is not None and int(parent) == old_gid) or (
                newer is not None and int(newer) == new_gid
            ):
                chained.add((old_gid, new_gid))
        return chained

    async def match_evidence(self, rows: Sequence[GalleryUpdate]) -> dict[int, dict[str, Any]]:
        """Explain *why* each update row matched, for the updates page.

        The list endpoint only stores ``old_gid``/``new_gid``; the evidence is
        derived on read so no schema migration is needed:

        * ``match_source`` — ``parent_chain`` when ExHentai records an official
          ``parent``/``replaces`` link, ``title`` for a normalized-title match.
        * ``new_title`` — the current title of the re-uploaded gid (favorites
          first, then cached gdata metadata, then an already ingested copy).
        * ``old_page_count`` / ``new_page_count`` — local page counts for the
          old copy and (when ingested) the new one, falling back to the cached
          gdata ``file_count`` for a not-yet-downloaded re-upload.
        * ``ambiguous`` — the same new gid matched more than one local gallery,
          the N→1 hazard that must never be bulk-updated unattended.

        Returns a mapping keyed by update row id; rows without any lookup data
        still get a default ``title`` source.
        """
        if not rows:
            return {}
        gallery_ids = sorted({int(r.gallery_id) for r in rows})
        new_gids = sorted({int(r.new_gid) for r in rows})

        old_page_rows = await self.session.execute(
            select(Gallery.id, Gallery.page_count).where(Gallery.id.in_(gallery_ids))
        )
        old_pages = {int(row_id): pages for row_id, pages in old_page_rows.all()}

        new_local_rows = await self.session.execute(
            select(Gallery.gid, Gallery.title, Gallery.page_count).where(
                Gallery.gid.in_(new_gids),
                Gallery.expunged.is_(False),
                Gallery.trashed.is_(False),
            )
        )
        local_new: dict[int, tuple[str | None, int | None]] = {}
        for gid, title, page_count in new_local_rows.all():
            if gid is not None:
                local_new.setdefault(int(gid), (title, page_count))

        fav_rows = await self.session.execute(
            select(FavoriteItem.gid, FavoriteItem.title)
            .where(FavoriteItem.gid.in_(new_gids))
            .order_by(FavoriteItem.last_seen_at.desc())
        )
        fav_titles: dict[int, str] = {}
        for gid, title in fav_rows.all():
            if title and int(gid) not in fav_titles:
                fav_titles[int(gid)] = str(title)

        meta_rows = await self.session.execute(
            select(GalleryMetadata.gid, GalleryMetadata.title, GalleryMetadata.file_count).where(
                GalleryMetadata.gid.in_(new_gids)
            )
        )
        meta_titles: dict[int, str] = {}
        meta_pages: dict[int, int | None] = {}
        for gid, title, file_count in meta_rows.all():
            gid = int(gid)
            if title and gid not in meta_titles:
                meta_titles[gid] = str(title)
            meta_pages[gid] = file_count

        count_rows = await self.session.execute(
            select(GalleryUpdate.new_gid, func.count())
            .where(GalleryUpdate.new_gid.in_(new_gids))
            .group_by(GalleryUpdate.new_gid)
        )
        match_counts = {int(gid): int(total) for gid, total in count_rows.all()}

        chained = await self.replacement_chain_pairs(
            [(int(r.old_gid), int(r.new_gid)) for r in rows]
        )

        evidence: dict[int, dict[str, Any]] = {}
        for row in rows:
            new_gid = int(row.new_gid)
            local_title, local_pages = local_new.get(new_gid, (None, None))
            new_page_count = local_pages if local_pages is not None else meta_pages.get(new_gid)
            match_count = match_counts.get(new_gid, 0)
            evidence[int(row.id)] = {
                "match_source": (
                    "parent_chain"
                    if (int(row.old_gid), new_gid) in chained
                    else "title"
                ),
                "new_title": fav_titles.get(new_gid) or meta_titles.get(new_gid) or local_title,
                "old_page_count": old_pages.get(int(row.gallery_id)),
                "new_page_count": new_page_count,
                "ambiguous": match_count > 1,
                "ambiguous_count": match_count,
            }
        return evidence

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

    async def mark_ambiguous(self, ids: Sequence[int], error: str) -> int:
        """Park rows back in ``pending`` when a match cannot be auto-finalized.

        Used when one new gid matches several local galleries without an
        official replacement link: the user has to pick which copies to update,
        so nothing may be deleted unattended.
        """
        if not ids:
            return 0
        result = await self.session.execute(
            update(GalleryUpdate)
            .where(
                GalleryUpdate.id.in_(list(ids)),
                GalleryUpdate.status.in_(["pending", "downloading", "failed"]),
            )
            .values(status="pending", error_message=error, updated_at=datetime.now(UTC))
        )
        return int(result.rowcount or 0)

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


