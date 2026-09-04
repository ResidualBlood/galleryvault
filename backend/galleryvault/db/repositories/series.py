from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import Gallery, GalleryTag, Series, SeriesExclusion, SeriesItem, Tag

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SeriesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[tuple[Series, int, list[Gallery]]]:
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
                select(SeriesItem.series_id, Gallery)
                .join(Gallery, Gallery.id == SeriesItem.gallery_id)
                .order_by(SeriesItem.series_id.desc(), Gallery.id.asc())
            )
        ).all()

        galleries_by_series: dict[int, list[Gallery]] = {}
        for sid, gallery in item_rows:
            galleries_by_series.setdefault(sid, []).append(gallery)

        return [
            (s, len(galleries_by_series.get(s.id, [])), galleries_by_series.get(s.id, []))
            for s in series_rows
        ]

    async def get(self, series_id: int) -> Series | None:
        return await self.session.get(Series, series_id)

    async def get_with_galleries(self, series_id: int) -> tuple[Series, list[Gallery]] | None:
        row = await self.get(series_id)
        if row is None:
            return None
        galleries = list(
            (
                await self.session.scalars(
                    select(Gallery)
                    .join(SeriesItem, SeriesItem.gallery_id == Gallery.id)
                    .where(SeriesItem.series_id == series_id)
                    .order_by(Gallery.id.asc())
                )
            ).all()
        )
        return row, galleries

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
        await self.session.flush()

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
