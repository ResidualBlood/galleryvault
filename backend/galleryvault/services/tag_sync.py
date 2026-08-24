"""Explicit synchronization of gallery tags from ExHentai metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ..db.models import Gallery
from .eh_client import EhClient


class TagSyncRepository(Protocol):
    async def get_for_tag_sync(self, identifier: int) -> Gallery | None: ...

    async def replace_tags(
        self,
        gallery: Gallery,
        tags: list[dict[str, str]],
        synced_at: datetime,
        category: str | None = None,
    ) -> int: ...

    async def refresh_category(self, gallery_id: int, category: str) -> None: ...

    async def pending_category_refresh_ids(
        self, limit: int = 500, last_id: int = 0
    ) -> list[int]: ...


class TagSyncError(ValueError):
    """The local gallery cannot be synchronized with its current metadata."""


class GalleryNotFound(TagSyncError):
    pass


class GalleryGidMissing(TagSyncError):
    pass


class GalleryTokenMissing(TagSyncError):
    pass


@dataclass(frozen=True)
class TagSyncResult:
    gid: int
    title: str
    count: int
    synced_at: datetime


class TagSyncService:
    def __init__(self, client: EhClient, repository: TagSyncRepository) -> None:
        self.client = client
        self.repository = repository

    async def sync(self, identifier: int) -> TagSyncResult:
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None:
            raise GalleryNotFound("Gallery not found")
        if gallery.gid is None:
            raise GalleryGidMissing("Gallery has no ExHentai gid")
        if not gallery.token:
            raise GalleryTokenMissing("Gallery has no ExHentai token")

        metadata_fetcher = getattr(self.client, "fetch_gallery_metadata", None)
        if metadata_fetcher is None:
            metadata = await self.client.fetch_gallery(gallery.gid, gallery.token)
        else:
            metadata = await metadata_fetcher(gallery.gid, gallery.token)
        unique_tags: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for tag in metadata.tags:
            namespace = str(tag.get("namespace", "misc")).strip() or "misc"
            name = str(tag.get("name", "")).strip()
            if name and (namespace, name) not in seen:
                seen.add((namespace, name))
                unique_tags.append({"namespace": namespace, "name": name})
        synced_at = datetime.now(UTC)
        count = await self.repository.replace_tags(
            gallery, unique_tags, synced_at, category=metadata.category
        )
        return TagSyncResult(metadata.gid, metadata.title, count, synced_at)

    async def refresh_category(self, identifier: int) -> str | None:
        """Re-fetch a gallery's metadata and refresh only its 大分类.

        Used by the one-time backfill for galleries that were tag-synced before
        category refresh existed (their real category stayed ``other``).  Returns
        the corrected category, or ``None`` if the gallery is gone.
        """
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None or gallery.gid is None or not gallery.token:
            return None
        metadata_fetcher = getattr(self.client, "fetch_gallery_metadata", None)
        if metadata_fetcher is None:
            metadata = await self.client.fetch_gallery(gallery.gid, gallery.token)
        else:
            metadata = await metadata_fetcher(gallery.gid, gallery.token)
        await self.repository.refresh_category(identifier, metadata.category)
        return metadata.category
