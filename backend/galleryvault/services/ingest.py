from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repository import GalleryRepository
from ..scanners.base import GalleryMeta


class GalleryIngestService:
    def __init__(self, session: AsyncSession, batch_size: int = 500) -> None:
        self.repository = GalleryRepository(session)
        self.batch_size = max(1, batch_size)

    async def ingest(self, galleries: Sequence[GalleryMeta]) -> None:
        # Reuse cached gdata metadata: galleries the favorites monitor already
        # saw (gid known) get tags/title/category/posted filled in here, so no
        # per-gallery ExHentai fetch is needed after ingest.
        cached = await self.repository.metadata_map(
            [g.gid for g in galleries if g.gid is not None and not g.tags]
        )
        for gallery in galleries:
            if gallery.gid is None or gallery.tags or gallery.gid not in cached:
                continue
            meta = cached[gallery.gid]
            gallery.tags = [{"namespace": t["namespace"], "name": t["name"]} for t in meta["tags"]]
            gallery.category = gallery.category or meta["category"]
            gallery.title_jpn = gallery.title_jpn or meta["title_jpn"]
            gallery.rating = gallery.rating or meta["rating"]
            gallery.posted_at = gallery.posted_at or meta["posted_at"]
        for start in range(0, len(galleries), self.batch_size):
            await self.repository.upsert_many(galleries[start : start + self.batch_size])
