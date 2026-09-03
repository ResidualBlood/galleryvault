from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Gallery, LocalList, LocalListItem


class LocalListRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[tuple[LocalList, int]]:
        rows = (
            await self.session.execute(
                select(LocalList, func.count(LocalListItem.gallery_id))
                .outerjoin(LocalListItem, LocalListItem.list_id == LocalList.id)
                .group_by(LocalList.id)
                .order_by(LocalList.id.desc())
            )
        ).all()
        return [(row[0], int(row[1] or 0)) for row in rows]

    async def get(self, list_id: int) -> LocalList | None:
        return await self.session.get(LocalList, list_id)

    async def create(self, name: str) -> LocalList:
        row = LocalList(name=name.strip(), created_at=datetime.now(UTC))
        self.session.add(row)
        await self.session.flush()
        return row

    async def rename(self, list_id: int, name: str) -> LocalList | None:
        row = await self.get(list_id)
        if row is None:
            return None
        row.name = name.strip()
        await self.session.flush()
        return row

    async def delete_list(self, list_id: int) -> bool:
        row = await self.get(list_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def add_items(self, list_id: int, gallery_ids: list[int]) -> int:
        ids = sorted({int(gid) for gid in gallery_ids if gid})
        if not ids:
            return 0
        existing = set(
            (
                await self.session.scalars(select(Gallery.id).where(Gallery.id.in_(ids)))
            ).all()
        )
        rows = [{"list_id": list_id, "gallery_id": gid} for gid in ids if gid in existing]
        if not rows:
            return 0
        await self.session.execute(
            pg_insert(LocalListItem)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["list_id", "gallery_id"])
        )
        await self.session.flush()
        return len(rows)

    async def remove_items(self, list_id: int, gallery_ids: list[int]) -> int:
        ids = [int(gid) for gid in gallery_ids if gid]
        if not ids:
            return 0
        result = await self.session.execute(
            delete(LocalListItem).where(
                LocalListItem.list_id == list_id, LocalListItem.gallery_id.in_(ids)
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def lists_for_gallery(self, gallery_id: int) -> list[LocalList]:
        rows = (
            await self.session.scalars(
                select(LocalList)
                .join(LocalListItem, LocalListItem.list_id == LocalList.id)
                .where(LocalListItem.gallery_id == gallery_id)
                .order_by(LocalList.id)
            )
        ).all()
        return list(rows)
