from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    DuplicateIgnore,
    FavoriteItem,
    FavoritesCheckLog,
    FavoritesMonitor,
    Gallery,
    GalleryTag,
    GalleryUpdate,
    Tag,
)
from .base import _chunked, escape_like_wildcards


class FavoritesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def categories(self) -> list[FavoritesMonitor]:
        return list(
            (
                await self.session.scalars(
                    select(FavoritesMonitor).order_by(FavoritesMonitor.favcat)
                )
            ).all()
        )

    async def counts_and_sizes(self) -> dict[int, tuple[int, int, int]]:
        """Per-favcat stats: (cloud items, local galleries, local bytes).

        ``cloud`` counts every favorite item recorded for the folder; ``local``
        counts the ones present locally (galleries table, not expunged) and
        ``local bytes`` is the sum of their file_size.  The API derives an
        estimated cloud size from these.
        """
        rows = await self.session.execute(
            select(
                FavoriteItem.favcat,
                func.count(FavoriteItem.id),
                func.count(Gallery.id).filter(
                    and_(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
                ),
                func.coalesce(
                    func.sum(Gallery.file_size).filter(
                        and_(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
                    ),
                    0,
                ),
            )
            .outerjoin(Gallery, Gallery.gid == FavoriteItem.gid)
            .group_by(FavoriteItem.favcat)
        )
        return {int(favcat): (int(cloud), int(local), int(size)) for favcat, cloud, local, size in rows}

    async def cloud_size_breakdown(self, favcat: int) -> tuple[int, int]:
        """Exact-ish cloud size for a folder: ``(known bytes, unknown count)``.

        ``known`` sums local gallery file_size for galleries already on disk and
        the recorded ``favorite_items.file_size`` for the missing ones that have
        been fetched; ``unknown`` counts missing galleries whose size has not
        been fetched yet (the API fills those with the local average).
        """
        row = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(func.coalesce(Gallery.file_size, FavoriteItem.file_size)), 0
                ),
                func.count().filter(
                    and_(Gallery.id.is_(None), FavoriteItem.file_size.is_(None))
                ),
            )
            .select_from(FavoriteItem)
            .outerjoin(
                Gallery,
                and_(
                    Gallery.gid == FavoriteItem.gid,
                    Gallery.expunged.is_(False),
                    Gallery.trashed.is_(False),
                ),
            )
            .where(FavoriteItem.favcat == favcat)
        )
        result = row.one()
        return int(result[0]), int(result[1])

    async def pending_size_gids(self, favcat: int, limit: int = 200) -> list[tuple[int, str]]:
        """``(gid, token)`` of folder galleries missing a size and not local."""
        rows = await self.session.execute(
            select(FavoriteItem.gid, FavoriteItem.token)
            .select_from(FavoriteItem)
            .outerjoin(
                Gallery,
                and_(
                    Gallery.gid == FavoriteItem.gid,
                    Gallery.expunged.is_(False),
                    Gallery.trashed.is_(False),
                ),
            )
            .where(
                FavoriteItem.favcat == favcat,
                Gallery.id.is_(None),
                FavoriteItem.file_size.is_(None),
            )
            .limit(limit)
        )
        return [(int(row[0]), str(row[1])) for row in rows]

    async def set_file_size(self, favcat: int, gid: int, size: int | None) -> None:
        await self.session.execute(
            update(FavoriteItem)
            .where(FavoriteItem.favcat == favcat, FavoriteItem.gid == gid)
            .values(file_size=size)
        )

    async def category(self, favcat: int) -> FavoritesMonitor | None:
        return await self.session.scalar(
            select(FavoritesMonitor).where(FavoritesMonitor.favcat == favcat)
        )

    async def known_gids(self, favcat: int) -> set[int]:
        rows = await self.session.scalars(
            select(FavoriteItem.gid).where(FavoriteItem.favcat == favcat)
        )
        return set(rows.all())

    async def count_known_gids(self, favcat: int) -> int:
        """Number of favorite items recorded locally for a folder."""
        return int(
            await self.session.scalar(
                select(func.count()).select_from(FavoriteItem).where(
                    FavoriteItem.favcat == favcat
                )
            )
            or 0
        )

    async def all_gids_for_favcat(self, favcat: int) -> list[tuple[int, str, str | None]]:
        """``(gid, token, thumb)`` for every item in a favorite folder."""
        rows = await self.session.execute(
            select(FavoriteItem.gid, FavoriteItem.token, FavoriteItem.thumb).where(
                FavoriteItem.favcat == favcat
            )
        )
        return [(int(row[0]), str(row[1]), row[2]) for row in rows]

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        """gids that already exist in the local library (galleries table).

        Used to skip favorite downloads for galleries that are already on disk
        (e.g. an Ehviewer export mounted under a library root), so they are not
        downloaded a second time into the downloads directory.  Expunged rows
        (directory removed and the scan expired them) count as missing, so the
        favorite monitor re-downloads them.
        """
        if not gids:
            return set()
        found: set[int] = set()
        for chunk in _chunked(list(dict.fromkeys(gids))):
            rows = await self.session.scalars(
                select(Gallery.gid).where(
                    Gallery.gid.is_not(None),
                    Gallery.expunged.is_(False),
                    Gallery.gid.in_(chunk),
                )
            )
            found.update(int(gid) for gid in rows if gid is not None)
        return found

    async def remember(self, favcat: int, item) -> None:
        now = datetime.now(UTC)
        row = await self.session.scalar(
            select(FavoriteItem).where(FavoriteItem.favcat == favcat, FavoriteItem.gid == item.gid)
        )
        if row is None:
            self.session.add(
                FavoriteItem(
                    favcat=favcat,
                    gid=item.gid,
                    token=item.token,
                    title=item.title,
                    url=item.url,
                    thumb=getattr(item, "thumb", None),
                    note=getattr(item, "note", None),
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.token, row.title, row.url, row.last_seen_at = item.token, item.title, item.url, now
            thumb = getattr(item, "thumb", None)
            if thumb:
                row.thumb = thumb
            note = getattr(item, "note", None)
            if note is not None:
                row.note = note
        await self.session.flush()

    async def remember_many(self, favcat: int, items: list[object]) -> None:
        """Bulk upsert favorite items, batched for large folders.

        PostgreSQL/asyncpg cap the number of bound parameters per statement, so
        a folder with thousands of galleries must be inserted in chunks.
        """
        if not items:
            return
        now = datetime.now(UTC)
        batch_size = 500
        for start in range(0, len(items), batch_size):
            chunk = items[start : start + batch_size]
            rows = [
                {
                    "favcat": favcat,
                    "gid": item.gid,
                    "token": item.token,
                    "title": item.title,
                    "url": item.url,
                    "thumb": getattr(item, "thumb", None),
                    "note": getattr(item, "note", None),
                    "first_seen_at": now,
                    "last_seen_at": now,
                }
                for item in chunk
            ]
            statement = pg_insert(FavoriteItem).values(rows)
            statement = statement.on_conflict_do_update(
                constraint="favorite_items_favcat_gid_key",
                set_={
                    "token": statement.excluded.token,
                    "title": statement.excluded.title,
                    "url": statement.excluded.url,
                    "thumb": func.coalesce(
                        func.nullif(statement.excluded.thumb, ""),
                        FavoriteItem.thumb,
                    ),
                    "note": func.coalesce(statement.excluded.note, FavoriteItem.note),
                    "last_seen_at": statement.excluded.last_seen_at,
                },
            )
            await self.session.execute(statement)

    async def checked(self, favcat: int, success: bool) -> None:
        row = await self.category(favcat)
        if row is None:
            row = FavoritesMonitor(favcat=favcat)
            self.session.add(row)
        row.last_checked_at = datetime.now(UTC)
        if success:
            row.last_success_at = row.last_checked_at
        await self.session.flush()

    async def prune(self, favcat: int, current_gids: set[int]) -> int:
        """Drop recorded folder items that are no longer in the ExHentai folder.

        Galleries that were unfavorited or expunged vanish from the cloud
        listing, so a successful full check must remove their recorded rows.
        Otherwise ``count_known_gids`` drifts above the live cloud count (the
        scheduled "cloud count unchanged → skip" heuristic never fires again)
        and phantom cloud-only items linger in the folder list forever.
        """
        if current_gids:
            result = await self.session.execute(
                delete(FavoriteItem).where(
                    FavoriteItem.favcat == favcat,
                    FavoriteItem.gid.not_in(current_gids),
                )
            )
        else:
            # An empty folder on the cloud means every recorded row is stale.
            result = await self.session.execute(
                delete(FavoriteItem).where(FavoriteItem.favcat == favcat)
            )
        return result.rowcount or 0

    async def log_check(
        self, favcat: int, gids: list[int], attempts: int, success: bool, error: str | None = None
    ) -> None:

        self.session.add(
            FavoritesCheckLog(
                favcat=favcat,
                discovered_gids=gids,
                attempts=attempts,
                success=success,
                error_message=error,
            )
        )
        await self.session.flush()

    async def list_items(
        self,
        favcat: int,
        page: int,
        page_size: int,
        state: str = "all",
        q: str | None = None,
        order_by: str = "last_seen_desc",
    ) -> tuple[int, list[tuple[object, object | None]]]:
        """Paginated favorite items for a folder, joined with the local gallery.

        ``state`` filters by whether the item exists on disk: ``local`` (has a
        gallery row), ``cloud`` (cloud-only) or ``all``.  Returns ``(total,
        [(FavoriteItem, Gallery|None)])``.
        """
        query = (
            select(FavoriteItem, Gallery)
            .outerjoin(
                Gallery,
                and_(
                    Gallery.gid == FavoriteItem.gid,
                    Gallery.expunged.is_(False),
                    Gallery.trashed.is_(False),
                ),
            )
            .where(FavoriteItem.favcat == favcat)
        )
        if state == "local":
            query = query.where(Gallery.id.is_not(None))
        elif state == "cloud":
            query = query.where(Gallery.id.is_(None))
        if q and q.strip():
            for token in q.split():
                pattern = f"%{escape_like_wildcards(token)}%"
                query = query.where(
                    FavoriteItem.title.ilike(pattern)
                    | Gallery.title.ilike(pattern)
                    | Gallery.title_jpn.ilike(pattern)
                )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        order_map = {
            "last_seen_desc": [FavoriteItem.last_seen_at.desc()],
            "first_seen_desc": [FavoriteItem.first_seen_at.desc()],
            "first_seen_asc": [FavoriteItem.first_seen_at.asc()],
            "title_asc": [FavoriteItem.title.asc()],
            "title_desc": [FavoriteItem.title.desc()],
            "posted_at_desc": [
                Gallery.posted_at.desc().nullslast(),
                FavoriteItem.last_seen_at.desc(),
            ],
            "file_size_desc": [
                func.coalesce(Gallery.file_size, FavoriteItem.file_size).desc().nullslast(),
                FavoriteItem.last_seen_at.desc(),
            ],
        }
        order_clauses = order_map.get(order_by, [FavoriteItem.last_seen_at.desc()])
        rows = (
            await self.session.execute(
                query.order_by(*order_clauses)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, [(row[0], row[1]) for row in rows]

    async def all_items(self) -> list[tuple]:
        """Every recorded favorite item joined with the local gallery.

        Returns ``(favcat, gid, token, title, url, gallery_id, file_size,
        first_seen_at, posted_at)`` where ``file_size`` prefers the on-disk
        gallery's real size and falls back to the recorded favorite size.
        """
        rows = await self.session.execute(
            select(
                FavoriteItem.favcat,
                FavoriteItem.gid,
                FavoriteItem.token,
                FavoriteItem.title,
                FavoriteItem.url,
                Gallery.id,
                func.coalesce(Gallery.file_size, FavoriteItem.file_size),
                FavoriteItem.first_seen_at,
                Gallery.posted_at,
            ).outerjoin(Gallery, Gallery.gid == FavoriteItem.gid)
        )
        return [
            (
                int(r[0]),
                int(r[1]),
                str(r[2]),
                str(r[3]),
                str(r[4]),
                int(r[5]) if r[5] is not None else None,
                int(r[6]) if r[6] is not None else None,
                r[7],
                r[8],
            )
            for r in rows
        ]

    async def tags_for_gallery_ids(
        self, gallery_ids: list[int]
    ) -> dict[int, list[tuple[str, str]]]:
        if not gallery_ids:
            return {}
        result: dict[int, list[tuple[str, str]]] = {}
        for chunk in _chunked(list(dict.fromkeys(gallery_ids))):
            rows = await self.session.execute(
                select(GalleryTag.gallery_id, Tag.namespace, Tag.name)
                .join(Tag, Tag.id == GalleryTag.tag_id)
                .where(GalleryTag.gallery_id.in_(chunk))
            )
            for gallery_id, namespace, name in rows:
                result.setdefault(int(gallery_id), []).append((namespace, name))
        return result

    async def remove_gids(self, gids: list[int]) -> int:
        if not gids:
            return 0
        removed = 0
        for chunk in _chunked(list(dict.fromkeys(gids))):
            result = await self.session.execute(
                delete(FavoriteItem).where(FavoriteItem.gid.in_(chunk))
            )
            removed += result.rowcount or 0
        return removed

    async def move_gids(self, gids: list[int], target_favcat: int) -> int:
        if not gids:
            return 0
        unique_gids = list(dict.fromkeys(gids))
        moved = 0
        for chunk in _chunked(unique_gids):
            existing_target = await self.session.scalars(
                select(FavoriteItem.gid).where(
                    FavoriteItem.gid.in_(chunk),
                    FavoriteItem.favcat == target_favcat,
                )
            )
            target_gids = set(existing_target.all())
            other_gids = [g for g in chunk if g not in target_gids]

            if target_gids:
                await self.session.execute(
                    delete(FavoriteItem).where(
                        FavoriteItem.gid.in_(list(target_gids)),
                        FavoriteItem.favcat != target_favcat,
                    )
                )
            if other_gids:
                rows = await self.session.execute(
                    select(FavoriteItem.id, FavoriteItem.gid).where(
                        FavoriteItem.gid.in_(other_gids)
                    )
                )
                keep_ids: list[int] = []
                drop_ids: list[int] = []
                seen_gids: set[int] = set()
                for row_id, gid in rows:
                    if gid not in seen_gids:
                        seen_gids.add(gid)
                        keep_ids.append(row_id)
                    else:
                        drop_ids.append(row_id)

                if drop_ids:
                    await self.session.execute(
                        delete(FavoriteItem).where(FavoriteItem.id.in_(drop_ids))
                    )
                if keep_ids:
                    result = await self.session.execute(
                        update(FavoriteItem)
                        .where(FavoriteItem.id.in_(keep_ids))
                        .values(favcat=target_favcat, last_seen_at=func.now())
                    )
                    moved += result.rowcount or 0
            moved += len(target_gids)
        return moved

    async def favcats_for_gid(
        self, gid: int | None, gallery_id: int | None = None
    ) -> list[int]:
        if gid is None:
            return []
        rows = await self.session.scalars(
            select(FavoriteItem.favcat).where(FavoriteItem.gid == gid)
        )
        direct = {int(f) for f in rows.all()}
        if direct or gallery_id is None:
            return sorted(direct)
        update_favs = await self.session.scalars(
            select(FavoriteItem.favcat)
            .join(GalleryUpdate, GalleryUpdate.new_gid == FavoriteItem.gid)
            .where(
                GalleryUpdate.gallery_id == gallery_id,
                GalleryUpdate.status != "ignored",
            )
        )
        return sorted({int(f) for f in update_favs.all()})

    async def update_note(self, gid: int, note: str, favcat: int | None = None) -> int:
        query = update(FavoriteItem).where(FavoriteItem.gid == gid)
        if favcat is not None:
            query = query.where(FavoriteItem.favcat == favcat)
        result = await self.session.execute(query.values(note=note))
        await self.session.flush()
        return int(result.rowcount or 0)

    async def item_for_gid(self, gid: int) -> FavoriteItem | None:
        return await self.session.scalar(
            select(FavoriteItem).where(FavoriteItem.gid == gid).limit(1)
        )

    async def category_names(self, favcats: list[int]) -> dict[int, str]:
        if not favcats:
            return {}
        rows = await self.session.scalars(
            select(FavoritesMonitor).where(FavoritesMonitor.favcat.in_(favcats))
        )
        return {int(r.favcat): r.name or "" for r in rows}

    async def galleries_for_gids(self, gids: list[int]) -> dict[int, int]:
        """Map gid -> local gallery.id for galleries on disk (not expunged)."""
        if not gids:
            return {}
        result: dict[int, int] = {}
        for chunk in _chunked(list(dict.fromkeys(gids))):
            rows = await self.session.execute(
                select(Gallery.gid, Gallery.id).where(
                    Gallery.gid.is_not(None),
                    Gallery.expunged.is_(False),
                    Gallery.gid.in_(chunk),
                )
            )
            for gid, gid_local in rows:
                if gid is not None:
                    result[int(gid)] = int(gid_local)
        return result

    async def gallery_titles_by_gid(self, gids: list[int]) -> dict[int, tuple[str | None, str | None]]:
        """Map gid -> (title, title_jpn) for galleries on disk."""
        if not gids:
            return {}
        result: dict[int, tuple[str | None, str | None]] = {}
        for chunk in _chunked(list(dict.fromkeys(gids))):
            rows = await self.session.execute(
                select(Gallery.gid, Gallery.title, Gallery.title_jpn).where(
                    Gallery.gid.is_not(None), Gallery.gid.in_(chunk)
                )
            )
            for gid, title, title_jpn in rows:
                if gid is not None:
                    result[int(gid)] = (title, title_jpn)
        return result

    async def ignored_duplicate_keys(self) -> set[str]:
        rows = await self.session.scalars(select(DuplicateIgnore.key))
        return set(rows.all())

    async def favorite_items_detail_by_gids(self, gids: list[int]) -> dict[int, dict]:
        """Duplicate-scan style item detail for favorite gids (local-join aware)."""
        if not gids:
            return {}
        pairs: list[tuple[FavoriteItem, Gallery | None]] = []
        for chunk in _chunked(list(dict.fromkeys(gids))):
            rows = (
                await self.session.execute(
                    select(FavoriteItem, Gallery)
                    .outerjoin(
                        Gallery,
                        and_(
                            Gallery.gid == FavoriteItem.gid,
                            Gallery.expunged.is_(False),
                            Gallery.trashed.is_(False),
                        ),
                    )
                    .where(FavoriteItem.gid.in_(chunk))
                )
            ).all()
            pairs.extend((item, gallery) for item, gallery in rows)
        local_ids = [
            int(gallery.id)
            for _, gallery in pairs
            if gallery is not None and gallery.id is not None
        ]
        tag_map: dict[int, list[tuple[str, str]]] = {}
        if local_ids:
            for chunk in _chunked(list(dict.fromkeys(local_ids))):
                tag_rows = await self.session.execute(
                    select(GalleryTag.gallery_id, Tag.namespace, Tag.name)
                    .join(Tag, Tag.id == GalleryTag.tag_id)
                    .where(GalleryTag.gallery_id.in_(chunk))
                )
                for gallery_id, namespace, name in tag_rows:
                    tag_map.setdefault(int(gallery_id), []).append((namespace, name))
        result: dict[int, dict] = {}
        for item, gallery in pairs:
            if gallery is not None:
                result[int(item.gid)] = {
                    "gid": item.gid,
                    "favcat": item.favcat,
                    "token": item.token,
                    "title": item.title or gallery.title or "",
                    "url": item.url,
                    "gallery_id": gallery.id,
                    "category": gallery.category or "other",
                    "page_count": gallery.page_count or 0,
                    "cover_url": f"/api/galleries/{gallery.id}/thumb/0" if gallery.page_count else None,
                    "file_size": gallery.file_size,
                    "first_seen_at": item.first_seen_at,
                    "posted_at": gallery.posted_at,
                    "tags": [
                        {"namespace": ns, "name": name}
                        for ns, name in tag_map.get(gallery.id, [])
                    ],
                }
            else:
                result[int(item.gid)] = {
                    "gid": item.gid,
                    "favcat": item.favcat,
                    "token": item.token,
                    "title": item.title,
                    "url": item.url,
                    "gallery_id": None,
                    "category": None,
                    "page_count": None,
                    "cover_url": None,
                    "file_size": item.file_size,
                    "first_seen_at": item.first_seen_at,
                    "posted_at": None,
                    "tags": [],
                }
        return result

    async def ignored_duplicates(self) -> list[dict[str, object]]:
        rows = await self.session.scalars(
            select(DuplicateIgnore).order_by(DuplicateIgnore.created_at.desc())
        )
        return [
            {
                "key": row.key,
                "title": row.title,
                "gids": row.gids or [],
            }
            for row in rows
        ]

    async def add_duplicate_ignore(
        self, key: str, title: str | None, gids: list[int]
    ) -> None:
        self.session.add(
            DuplicateIgnore(
                key=key,
                title=title or None,
                gids=gids or None,
            )
        )

    async def remove_duplicate_ignore(self, key: str) -> None:
        row = await self.session.get(DuplicateIgnore, key)
        if row is not None:
            await self.session.delete(row)

    async def update_posted_at(self, gid_to_posted: dict[int, datetime]) -> None:
        """Persist ExHentai posted timestamps onto on-disk galleries."""
        if not gid_to_posted:
            return
        for gid, posted in gid_to_posted.items():
            await self.session.execute(
                update(Gallery)
                .where(Gallery.gid.is_not(None), Gallery.gid == gid)
                .values(posted_at=posted)
            )


