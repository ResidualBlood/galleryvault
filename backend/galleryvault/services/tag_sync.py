"""Explicit synchronization of gallery tags from ExHentai metadata."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ..db.models import Gallery
from ..logging import log_extra
from .eh_client import EhClient

logger = logging.getLogger(__name__)


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

    async def metadata_for_gid(self, gid: int) -> dict | None: ...

    async def upsert_metadata(self, entries: list[dict]) -> int: ...


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
    source: str = "network"


class TagSyncService:
    def __init__(self, client: EhClient, repository: TagSyncRepository) -> None:
        self.client = client
        self.repository = repository

    async def fetch_plan(self, identifier: int) -> dict[str, object]:
        """Read the gallery row and fetch its metadata WITHOUT writing anything.

        Network I/O happens here so callers can keep it outside any DB
        transaction — a transaction must not be held open across an ExHentai
        round-trip, which pins a connection-pool slot for seconds.
        """
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None:
            raise GalleryNotFound("Gallery not found")
        if gallery.gid is None:
            raise GalleryGidMissing("Gallery has no ExHentai gid")
        if not gallery.token:
            raise GalleryTokenMissing("Gallery has no ExHentai token")

        cached = await self.repository.metadata_for_gid(gallery.gid)
        if cached and cached.get("tags"):
            return {
                "source": "cache",
                "gid": gallery.gid,
                "token": gallery.token,
                "title": cached.get("title") or gallery.title,
                "category": cached.get("category"),
                "tags": cached["tags"],
            }

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
        return {
            "source": "network",
            "gid": metadata.gid,
            "token": gallery.token,
            "title": metadata.title,
            "title_jpn": metadata.title_jpn,
            "category": metadata.category,
            "file_size": metadata.file_size,
            "tags": unique_tags,
        }

    async def apply_plan(self, gallery_id: int, plan: dict[str, object]) -> int:
        """Persist a fetched metadata plan (call inside a short transaction)."""
        gallery = await self.repository.get_for_tag_sync(gallery_id)
        if gallery is None:
            return 0
        synced_at = datetime.now(UTC)
        count = await self.repository.replace_tags(
            gallery,
            plan["tags"],  # type: ignore[arg-type]
            synced_at,
            category=plan.get("category"),
        )
        if plan.get("source") == "network":
            # Backfill the cache so sibling galleries with the same gid (or a
            # later folder check / duplicate scan) need no further ExHentai fetch.
            try:
                await self.repository.upsert_metadata(
                    [
                        {
                            "gid": plan["gid"],
                            "token": plan.get("token"),
                            "title": plan.get("title"),
                            "title_jpn": plan.get("title_jpn"),
                            "category": plan.get("category"),
                            "file_size": plan.get("file_size"),
                            "tags": [
                                f"{tag['namespace']}:{tag['name']}"
                                for tag in plan["tags"]  # type: ignore[union-attr]
                                if tag.get("name")
                            ],
                        }
                    ]
                )
            except Exception as exc:  # noqa: BLE001 - cache write must not fail the sync
                logger.warning(
                    "tag sync cache write failed", extra=log_extra(error=type(exc).__name__)
                )
        return count

    async def sync(self, identifier: int) -> TagSyncResult:
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None:
            raise GalleryNotFound("Gallery not found")
        if gallery.gid is None:
            raise GalleryGidMissing("Gallery has no ExHentai gid")
        if not gallery.token:
            raise GalleryTokenMissing("Gallery has no ExHentai token")

        # Prefer cached gdata metadata (written by the favorites monitor); only
        # fall back to a per-gallery ExHentai fetch when the cache is cold.
        cached = await self.repository.metadata_for_gid(gallery.gid)
        if cached and cached.get("tags"):
            synced_at = datetime.now(UTC)
            count = await self.repository.replace_tags(
                gallery, cached["tags"], synced_at, category=cached.get("category")
            )
            return TagSyncResult(
                gallery.gid, cached.get("title") or gallery.title, count, synced_at, "cache"
            )

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
        # Backfill the cache so sibling galleries with the same gid (or a later
        # folder check / duplicate scan) need no further ExHentai fetch.
        try:
            await self.repository.upsert_metadata(
                [
                    {
                        "gid": metadata.gid,
                        "token": gallery.token,
                        "title": metadata.title,
                        "title_jpn": metadata.title_jpn,
                        "category": metadata.category,
                        "file_size": metadata.file_size,
                        "tags": [
                            f"{tag['namespace']}:{tag['name']}"
                            for tag in unique_tags
                            if tag.get("name")
                        ],
                    }
                ]
            )
        except Exception as exc:  # noqa: BLE001 - cache write must not fail the sync
            logger.warning(
                "tag sync cache write failed", extra=log_extra(error=type(exc).__name__)
            )
        return TagSyncResult(metadata.gid, metadata.title, count, synced_at, "network")

    async def refresh_category(self, identifier: int) -> str | None:
        """Re-fetch a gallery's metadata and refresh only its 大分类.

        Used by the one-time backfill for galleries that were tag-synced before
        category refresh existed (their real category stayed ``other``).  Uses
        the cached metadata when available; returns the corrected category, or
        ``None`` if the gallery is gone.
        """
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None or gallery.gid is None or not gallery.token:
            return None
        cached = await self.repository.metadata_for_gid(gallery.gid)
        if cached and cached.get("category"):
            await self.repository.refresh_category(identifier, cached["category"])
            return cached["category"]
        metadata_fetcher = getattr(self.client, "fetch_gallery_metadata", None)
        if metadata_fetcher is None:
            metadata = await self.client.fetch_gallery(gallery.gid, gallery.token)
        else:
            metadata = await metadata_fetcher(gallery.gid, gallery.token)
        await self.repository.refresh_category(identifier, metadata.category)
        return metadata.category
