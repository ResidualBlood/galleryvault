from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import (
    FavoriteItem,
    Gallery,
    GalleryMetadata,
    GalleryTag,
    Series,
    SeriesCloudExclusion,
    SeriesCloudItem,
    SeriesExclusion,
    SeriesItem,
    Tag,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SeriesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[tuple[Series, int, list[Any]]]:
        """List all series with their gallery count and member galleries."""
        series_rows = list(
            (
                await self.session.scalars(
                    select(Series).order_by(Series.id.desc())
                )
            ).all()
        )
        if not series_rows:
            return []

        item_rows = (
            await self.session.execute(
                select(SeriesItem.series_id, Gallery, FavoriteItem.favcat)
                .join(Gallery, Gallery.id == SeriesItem.gallery_id)
                .outerjoin(FavoriteItem, FavoriteItem.gid == Gallery.gid)
                .order_by(SeriesItem.series_id.desc(), Gallery.id.asc())
            )
        ).all()

        members_by_series: dict[int, list[Any]] = {}
        seen_local: set[tuple[int, int]] = set()
        for sid, gallery, favcat in item_rows:
            if (sid, gallery.id) in seen_local:
                continue
            seen_local.add((sid, gallery.id))
            gallery.favcat = favcat
            gallery.is_local = True
            members_by_series.setdefault(sid, []).append(gallery)

        cloud_rows = (
            await self.session.execute(
                select(
                    SeriesCloudItem.series_id,
                    SeriesCloudItem.gid,
                    FavoriteItem.favcat,
                    FavoriteItem.token,
                    FavoriteItem.title,
                    FavoriteItem.url,
                    FavoriteItem.thumb,
                    GalleryMetadata.category,
                    GalleryMetadata.file_count,
                    GalleryMetadata.tags,
                )
                .outerjoin(FavoriteItem, FavoriteItem.gid == SeriesCloudItem.gid)
                .outerjoin(GalleryMetadata, GalleryMetadata.gid == SeriesCloudItem.gid)
                .order_by(SeriesCloudItem.series_id.desc(), SeriesCloudItem.gid.asc())
            )
        ).all()

        seen_cloud: set[tuple[int, int]] = set()
        for sid, gid, favcat, token, title, url, thumb, category, file_count, tags in cloud_rows:
            if (sid, gid) in seen_cloud:
                continue
            seen_cloud.add((sid, gid))
            c_item = {
                "is_local": False,
                "gallery_id": None,
                "id": None,
                "gid": gid,
                "favcat": favcat,
                "token": token,
                "url": url or (f"https://e-hentai.org/g/{gid}/{token}/" if token else None),
                "title": title or f"gid {gid}",
                "category": category or "other",
                "page_count": file_count or 0,
                "cover_url": thumb,
                "tags": tags or [],
            }
            members_by_series.setdefault(sid, []).append(c_item)

        return [
            (s, len(members_by_series.get(s.id, [])), members_by_series.get(s.id, []))
            for s in series_rows
        ]

    async def list_paged(
        self,
        page: int = 1,
        page_size: int = 25,
        show_all: bool = False,
    ) -> tuple[list[tuple[Series, int, list[Any]]], int]:
        """List series with backend group filtering and pagination.

        Default (show_all=False):
        - Only series with at least one gallery of category doujinshi/manga are returned.
        - Member galleries are filtered to doujinshi/manga only.
        show_all=True:
        - All series and all member gallery categories are returned.
        """
        series_query = select(Series)
        if not show_all:
            valid_local_sids = (
                select(SeriesItem.series_id)
                .join(Gallery, Gallery.id == SeriesItem.gallery_id)
                .where(func.lower(Gallery.category).in_(["doujinshi", "manga"]))
            )
            valid_cloud_sids = (
                select(SeriesCloudItem.series_id)
                .join(GalleryMetadata, GalleryMetadata.gid == SeriesCloudItem.gid)
                .where(func.lower(GalleryMetadata.category).in_(["doujinshi", "manga"]))
            )
            valid_sids_subq = valid_local_sids.union(valid_cloud_sids).subquery()
            series_query = series_query.where(Series.id.in_(select(valid_sids_subq.c.series_id)))

        count_query = select(func.count()).select_from(series_query.subquery())
        total = int((await self.session.scalar(count_query)) or 0)
        if total == 0:
            return [], 0

        offset = (page - 1) * page_size
        series_page_query = (
            series_query.order_by(Series.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        paged_series = list((await self.session.scalars(series_page_query)).all())
        if not paged_series:
            return [], total

        paged_sids = [s.id for s in paged_series]
        local_stmt = (
            select(SeriesItem.series_id, Gallery, FavoriteItem.favcat)
            .join(Gallery, Gallery.id == SeriesItem.gallery_id)
            .outerjoin(FavoriteItem, FavoriteItem.gid == Gallery.gid)
            .where(SeriesItem.series_id.in_(paged_sids))
        )
        if not show_all:
            local_stmt = local_stmt.where(
                func.lower(Gallery.category).in_(["doujinshi", "manga"])
            )
        local_stmt = local_stmt.order_by(SeriesItem.series_id.desc(), Gallery.id.asc())
        local_rows = (await self.session.execute(local_stmt)).all()

        members_by_series: dict[int, list[Any]] = {}
        seen_local_ids: set[tuple[int, int]] = set()
        for sid, gallery, favcat in local_rows:
            if (sid, gallery.id) in seen_local_ids:
                continue
            seen_local_ids.add((sid, gallery.id))
            gallery.favcat = favcat
            gallery.is_local = True
            members_by_series.setdefault(sid, []).append(gallery)

        cloud_stmt = (
            select(
                SeriesCloudItem.series_id,
                SeriesCloudItem.gid,
                FavoriteItem.favcat,
                FavoriteItem.token,
                FavoriteItem.title,
                FavoriteItem.url,
                FavoriteItem.thumb,
                GalleryMetadata.category,
                GalleryMetadata.file_count,
                GalleryMetadata.tags,
            )
            .outerjoin(FavoriteItem, FavoriteItem.gid == SeriesCloudItem.gid)
            .outerjoin(GalleryMetadata, GalleryMetadata.gid == SeriesCloudItem.gid)
            .where(SeriesCloudItem.series_id.in_(paged_sids))
        )
        if not show_all:
            cloud_stmt = cloud_stmt.where(
                func.lower(GalleryMetadata.category).in_(["doujinshi", "manga"])
            )
        cloud_stmt = cloud_stmt.order_by(
            SeriesCloudItem.series_id.desc(), SeriesCloudItem.gid.asc()
        )
        cloud_rows = (await self.session.execute(cloud_stmt)).all()

        seen_cloud_gids: set[tuple[int, int]] = set()
        for sid, gid, favcat, token, title, url, thumb, category, file_count, tags in cloud_rows:
            if (sid, gid) in seen_cloud_gids:
                continue
            seen_cloud_gids.add((sid, gid))
            c_item = {
                "is_local": False,
                "gallery_id": None,
                "id": None,
                "gid": gid,
                "favcat": favcat,
                "token": token,
                "url": url or (f"https://e-hentai.org/g/{gid}/{token}/" if token else None),
                "title": title or f"gid {gid}",
                "category": category or "other",
                "page_count": file_count or 0,
                "cover_url": thumb,
                "tags": tags or [],
            }
            members_by_series.setdefault(sid, []).append(c_item)

        items = [
            (s, len(members_by_series.get(s.id, [])), members_by_series.get(s.id, []))
            for s in paged_series
        ]
        return items, total

    async def get(self, series_id: int) -> Series | None:
        return await self.session.get(Series, series_id)

    async def get_with_galleries(self, series_id: int) -> tuple[Series, list[Any]] | None:
        row = await self.get(series_id)
        if row is None:
            return None
        local_rows = (
            await self.session.execute(
                select(Gallery, FavoriteItem.favcat)
                .join(SeriesItem, SeriesItem.gallery_id == Gallery.id)
                .outerjoin(FavoriteItem, FavoriteItem.gid == Gallery.gid)
                .where(SeriesItem.series_id == series_id)
                .order_by(Gallery.id.asc())
            )
        ).all()
        seen_local_ids = set()
        members: list[Any] = []
        for gallery, favcat in local_rows:
            if gallery.id in seen_local_ids:
                continue
            seen_local_ids.add(gallery.id)
            gallery.favcat = favcat
            gallery.is_local = True
            members.append(gallery)

        cloud_rows = (
            await self.session.execute(
                select(
                    SeriesCloudItem.gid,
                    FavoriteItem.favcat,
                    FavoriteItem.token,
                    FavoriteItem.title,
                    FavoriteItem.url,
                    FavoriteItem.thumb,
                    GalleryMetadata.category,
                    GalleryMetadata.file_count,
                    GalleryMetadata.tags,
                )
                .outerjoin(FavoriteItem, FavoriteItem.gid == SeriesCloudItem.gid)
                .outerjoin(GalleryMetadata, GalleryMetadata.gid == SeriesCloudItem.gid)
                .where(SeriesCloudItem.series_id == series_id)
                .order_by(SeriesCloudItem.gid.asc())
            )
        ).all()
        seen_cloud_gids = set()
        for gid, favcat, token, title, url, thumb, category, file_count, tags in cloud_rows:
            if gid in seen_cloud_gids:
                continue
            seen_cloud_gids.add(gid)
            c_item = {
                "is_local": False,
                "gallery_id": None,
                "id": None,
                "gid": gid,
                "favcat": favcat,
                "token": token,
                "url": url or (f"https://e-hentai.org/g/{gid}/{token}/" if token else None),
                "title": title or f"gid {gid}",
                "category": category or "other",
                "page_count": file_count or 0,
                "cover_url": thumb,
                "tags": tags or [],
            }
            members.append(c_item)

        return row, members

    async def create(
        self, name: str, match_key: str | None = None, name_manual: bool = False
    ) -> Series:
        row = Series(
            name=name.strip(),
            match_key=match_key,
            name_manual=name_manual,
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def rename(self, series_id: int, name: str) -> Series | None:
        row = await self.get(series_id)
        if row is None:
            return None
        row.name = name.strip()
        row.name_manual = True
        await self.session.flush()
        return row

    async def delete_series(self, series_id: int) -> bool:
        row = await self.get(series_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def add_items(
        self, series_id: int, gallery_ids: list[int], source: str = "manual"
    ) -> int:
        ids = sorted({int(gid) for gid in gallery_ids if gid})
        if not ids:
            return 0
        existing = set(
            (
                await self.session.scalars(select(Gallery.id).where(Gallery.id.in_(ids)))
            ).all()
        )
        valid_ids = [gid for gid in ids if gid in existing]
        if not valid_ids:
            return 0

        # Un-exclude if explicitly added back
        await self.session.execute(
            delete(SeriesExclusion).where(SeriesExclusion.gallery_id.in_(valid_ids))
        )

        # Upsert: if already in another series, move to this series
        rows = [
            {"series_id": series_id, "gallery_id": gid, "source": source}
            for gid in valid_ids
        ]
        stmt = (
            pg_insert(SeriesItem)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["gallery_id"],
                set_={"series_id": series_id, "source": source},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return len(valid_ids)

    async def remove_items(self, series_id: int, gallery_ids: list[int]) -> int:
        ids = [int(gid) for gid in gallery_ids if gid]
        if not ids:
            return 0
        result = await self.session.execute(
            delete(SeriesItem).where(
                SeriesItem.series_id == series_id, SeriesItem.gallery_id.in_(ids)
            )
        )
        # Write to series_exclusions (manual removal should prevent rescan from re-adding)
        excl_rows = [{"gallery_id": gid, "created_at": datetime.now(UTC)} for gid in ids]
        await self.session.execute(
            pg_insert(SeriesExclusion)
            .values(excl_rows)
            .on_conflict_do_nothing(index_elements=["gallery_id"])
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def get_existing_auto_groups(self) -> dict[str, Series]:
        rows = list(
            (
                await self.session.scalars(
                    select(Series).where(Series.match_key.is_not(None))
                )
            ).all()
        )
        return {r.match_key: r for r in rows if r.match_key}

    async def get_auto_series(self) -> list[Series]:
        return list(
            (
                await self.session.scalars(
                    select(Series).where(Series.match_key.is_not(None))
                )
            ).all()
        )

    async def get_auto_series_gids(self, series_ids: list[int]) -> dict[int, set[int]]:
        if not series_ids:
            return {}
        rows = (
            await self.session.execute(
                select(SeriesItem.series_id, SeriesItem.gallery_id).where(
                    SeriesItem.series_id.in_(series_ids)
                )
            )
        ).all()
        result: dict[int, set[int]] = {}
        for sid, gid in rows:
            result.setdefault(sid, set()).add(gid)
        return result

    async def get_auto_series_cloud_gids(self, series_ids: list[int]) -> dict[int, set[int]]:
        if not series_ids:
            return {}
        rows = (
            await self.session.execute(
                select(SeriesCloudItem.series_id, SeriesCloudItem.gid).where(
                    SeriesCloudItem.series_id.in_(series_ids)
                )
            )
        ).all()
        result: dict[int, set[int]] = {}
        for sid, gid in rows:
            result.setdefault(sid, set()).add(gid)
        return result

    async def get_rebuild_candidate_galleries(self) -> list[Gallery]:
        """Fetch candidates for series rebuild: unassigned or in auto series,

        excluding manual series members and exclusions.
        """
        manual_subq = (
            select(SeriesItem.gallery_id)
            .join(Series, Series.id == SeriesItem.series_id)
            .where(Series.match_key.is_(None))
        )
        excl_subq = select(SeriesExclusion.gallery_id)

        stmt = (
            select(Gallery)
            .outerjoin(SeriesItem, SeriesItem.gallery_id == Gallery.id)
            .outerjoin(Series, Series.id == SeriesItem.series_id)
            .where(
                Gallery.trashed.is_(False),
                Gallery.id.not_in(excl_subq),
                Gallery.id.not_in(manual_subq),
                or_(
                    SeriesItem.gallery_id.is_(None),
                    Series.match_key.is_not(None),
                ),
            )
            .distinct()
            .order_by(Gallery.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def clear_auto_series_items(self, series_ids: list[int]) -> None:
        if not series_ids:
            return
        await self.session.execute(
            delete(SeriesItem).where(SeriesItem.series_id.in_(series_ids))
        )
        await self.session.execute(
            delete(SeriesCloudItem).where(SeriesCloudItem.series_id.in_(series_ids))
        )
        await self.session.flush()

    async def add_cloud_items(self, series_id: int, gids: list[int]) -> int:
        unique_gids = sorted({int(g) for g in gids if g})
        if not unique_gids:
            return 0
        rows = [{"series_id": series_id, "gid": g} for g in unique_gids]
        stmt = (
            pg_insert(SeriesCloudItem)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["series_id", "gid"],
                set_={"series_id": series_id},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return len(unique_gids)

    async def get_cloud_candidates(
        self, series_id: int, q: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        local_gids_stmt = (
            select(Gallery.gid)
            .join(SeriesItem, SeriesItem.gallery_id == Gallery.id)
            .where(SeriesItem.series_id == series_id, Gallery.gid.is_not(None))
        )
        cloud_gids_stmt = select(SeriesCloudItem.gid).where(
            SeriesCloudItem.series_id == series_id
        )
        existing_gids_subq = local_gids_stmt.union(cloud_gids_stmt).subquery()

        stmt = select(
            FavoriteItem.gid,
            FavoriteItem.title,
            FavoriteItem.favcat,
            FavoriteItem.thumb,
            FavoriteItem.token,
            FavoriteItem.url,
        ).where(FavoriteItem.gid.not_in(select(existing_gids_subq.c.gid)))

        if q and q.strip():
            search_str = f"%{q.strip()}%"
            if q.strip().isdigit():
                stmt = stmt.where(
                    or_(
                        FavoriteItem.title.ilike(search_str),
                        FavoriteItem.gid == int(q.strip()),
                    )
                )
            else:
                stmt = stmt.where(FavoriteItem.title.ilike(search_str))

        stmt = stmt.order_by(FavoriteItem.gid.desc()).limit(max(1, limit) * 2)
        rows = (await self.session.execute(stmt)).all()
        seen = set()
        results: list[dict[str, Any]] = []
        for r in rows:
            if r.gid in seen:
                continue
            seen.add(r.gid)
            results.append(
                {
                    "gid": r.gid,
                    "title": r.title,
                    "favcat": r.favcat,
                    "thumb": r.thumb,
                    "token": r.token,
                    "url": r.url,
                }
            )
            if len(results) >= limit:
                break
        return results

    async def add_cloud_items_flow(
        self, series_id: int, gids: list[int]
    ) -> dict[str, int]:
        unique_gids = sorted({int(g) for g in gids if g and int(g) > 0})
        if not unique_gids:
            return {"added_local": 0, "added_cloud": 0, "skipped": 0}

        local_gallery_rows = (
            await self.session.execute(
                select(Gallery.id, Gallery.gid).where(
                    Gallery.gid.in_(unique_gids),
                    Gallery.trashed.is_(False),
                )
            )
        ).all()
        local_gids = {row.gid for row in local_gallery_rows}
        local_gallery_ids = [row.id for row in local_gallery_rows]

        added_local = 0
        if local_gallery_ids:
            await self.session.execute(
                delete(SeriesExclusion).where(
                    SeriesExclusion.gallery_id.in_(local_gallery_ids)
                )
            )
            await self.session.execute(
                delete(SeriesCloudExclusion).where(
                    SeriesCloudExclusion.series_id == series_id,
                    SeriesCloudExclusion.gid.in_(local_gids),
                )
            )
            rows = [
                {"series_id": series_id, "gallery_id": gid, "source": "manual"}
                for gid in local_gallery_ids
            ]
            stmt = (
                pg_insert(SeriesItem)
                .values(rows)
                .on_conflict_do_update(
                    index_elements=["gallery_id"],
                    set_={"series_id": series_id, "source": "manual"},
                )
            )
            await self.session.execute(stmt)
            await self.session.execute(
                delete(SeriesCloudItem).where(SeriesCloudItem.gid.in_(local_gids))
            )
            added_local = len(local_gallery_ids)

        rem_gids = [g for g in unique_gids if g not in local_gids]
        added_cloud = 0
        skipped = 0

        if rem_gids:
            fav_gids = set(
                (
                    await self.session.scalars(
                        select(FavoriteItem.gid).where(FavoriteItem.gid.in_(rem_gids))
                    )
                ).all()
            )
            valid_cloud_gids = [g for g in rem_gids if g in fav_gids]
            skipped = len(rem_gids) - len(valid_cloud_gids)

            if valid_cloud_gids:
                await self.session.execute(
                    delete(SeriesCloudExclusion).where(
                        SeriesCloudExclusion.series_id == series_id,
                        SeriesCloudExclusion.gid.in_(valid_cloud_gids),
                    )
                )
                cloud_rows = [
                    {"series_id": series_id, "gid": g} for g in valid_cloud_gids
                ]
                cloud_stmt = (
                    pg_insert(SeriesCloudItem)
                    .values(cloud_rows)
                    .on_conflict_do_update(
                        index_elements=["series_id", "gid"],
                        set_={"series_id": series_id},
                    )
                )
                await self.session.execute(cloud_stmt)
                added_cloud = len(valid_cloud_gids)

        await self.session.flush()
        return {
            "added_local": added_local,
            "added_cloud": added_cloud,
            "skipped": skipped,
        }

    async def remove_cloud_items(self, series_id: int, gids: list[int]) -> int:
        clean_gids = sorted({int(g) for g in gids if g and int(g) > 0})
        if not clean_gids:
            return 0
        res = await self.session.execute(
            delete(SeriesCloudItem).where(
                SeriesCloudItem.series_id == series_id,
                SeriesCloudItem.gid.in_(clean_gids),
            )
        )
        excl_rows = [
            {"series_id": series_id, "gid": g, "created_at": datetime.now(UTC)}
            for g in clean_gids
        ]
        await self.session.execute(
            pg_insert(SeriesCloudExclusion)
            .values(excl_rows)
            .on_conflict_do_nothing(index_elements=["series_id", "gid"])
        )
        await self.session.flush()
        return int(res.rowcount or 0)

    async def get_series_cloud_exclusions(self) -> dict[int, set[int]]:
        rows = (
            await self.session.execute(
                select(SeriesCloudExclusion.series_id, SeriesCloudExclusion.gid)
            )
        ).all()
        res: dict[int, set[int]] = {}
        for sid, gid in rows:
            res.setdefault(sid, set()).add(gid)
        return res

    async def delete_cloud_items_for_local_galleries(self) -> int:
        local_gids_subq = select(Gallery.gid).where(
            Gallery.gid.is_not(None), Gallery.trashed.is_(False)
        )
        stmt = delete(SeriesCloudItem).where(SeriesCloudItem.gid.in_(local_gids_subq))
        res = await self.session.execute(stmt)
        await self.session.flush()
        return int(res.rowcount or 0)

    async def get_rebuild_candidate_cloud_items(self) -> list[dict[str, Any]]:
        local_gids_subq = select(Gallery.gid).where(
            Gallery.gid.is_not(None), Gallery.trashed.is_(False)
        )
        stmt = (
            select(
                FavoriteItem.gid,
                FavoriteItem.title,
                GalleryMetadata.category,
                GalleryMetadata.tags,
            )
            .outerjoin(GalleryMetadata, GalleryMetadata.gid == FavoriteItem.gid)
            .where(FavoriteItem.gid.not_in(local_gids_subq))
            .order_by(FavoriteItem.gid.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        seen_gids: set[int] = set()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            if row.gid in seen_gids:
                continue
            seen_gids.add(row.gid)
            candidates.append(
                {
                    "gid": row.gid,
                    "title": row.title,
                    "category": row.category,
                    "tags": row.tags or [],
                }
            )
        return candidates

    async def get_unassigned_galleries(self) -> list[Gallery]:
        stmt = (
            select(Gallery)
            .outerjoin(SeriesItem, SeriesItem.gallery_id == Gallery.id)
            .outerjoin(SeriesExclusion, SeriesExclusion.gallery_id == Gallery.id)
            .where(
                Gallery.trashed.is_(False),
                SeriesItem.gallery_id.is_(None),
                SeriesExclusion.gallery_id.is_(None),
            )
            .order_by(Gallery.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def series_for_gallery(self, gallery_id: int) -> Series | None:
        return (
            await self.session.scalars(
                select(Series)
                .join(SeriesItem, SeriesItem.series_id == Series.id)
                .where(SeriesItem.gallery_id == gallery_id)
            )
        ).first()

    async def get_tags_for_galleries(
        self, gallery_ids: list[int]
    ) -> dict[int, list[tuple[str, str]]]:
        """Fetch tags for candidate galleries, filtered to artist/group/parody/other."""
        if not gallery_ids:
            return {}
        stmt = (
            select(GalleryTag.gallery_id, Tag.namespace, Tag.name)
            .join(Tag, Tag.id == GalleryTag.tag_id)
            .where(
                GalleryTag.gallery_id.in_(list(gallery_ids)),
                Tag.namespace.in_(["artist", "group", "parody", "other"]),
            )
            .order_by(GalleryTag.gallery_id.asc(), Tag.namespace.asc(), Tag.name.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        result: dict[int, list[tuple[str, str]]] = {}
        for gid, ns, name in rows:
            result.setdefault(gid, []).append((ns, name))
        return result
