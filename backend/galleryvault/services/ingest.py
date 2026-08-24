from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repository import GalleryRepository
from ..scanners.base import GalleryMeta


class GalleryIngestService:
    def __init__(self, session: AsyncSession, batch_size: int = 500) -> None:
        self.repository = GalleryRepository(session)
        self.batch_size = max(1, batch_size)

    async def ingest(self, galleries: Sequence[GalleryMeta]) -> None:
        for start in range(0, len(galleries), self.batch_size):
            await self.repository.upsert_many(galleries[start : start + self.batch_size])
