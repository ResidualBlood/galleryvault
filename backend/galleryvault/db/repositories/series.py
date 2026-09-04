from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import Gallery, Series, SeriesExclusion, SeriesItem

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
