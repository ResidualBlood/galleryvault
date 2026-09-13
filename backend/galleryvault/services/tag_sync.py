"""Explicit synchronization of gallery tags from ExHentai metadata."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ..db.models import Gallery
from ..logging import log_extra
from .eh_client import EhClient
from .eh_metadata import enrich_html_newer, refresh_gdata

logger = logging.getLogger(__name__)


def _parse_tags(raw_tags: Any) -> list[dict[str, str]]:
    unique_tags: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tag in raw_tags or []:
        if isinstance(tag, dict):
            ns = str(tag.get("namespace") or "misc").strip() or "misc"
            name = str(tag.get("name") or "").strip()
        elif isinstance(tag, (list, tuple)) and len(tag) >= 2:
            ns = str(tag[0] or "misc").strip() or "misc"
            name = str(tag[1] or "").strip()
        elif isinstance(tag, str) and tag.strip():
            if ":" in tag:
                ns, name = tag.split(":", 1)
            else:
                ns, name = "misc", tag
            ns = ns.strip() or "misc"
            name = name.strip()
        else:
            continue
        if name and (ns, name) not in seen:
            seen.add((ns, name))
            unique_tags.append({"namespace": ns, "name": name})
    return unique_tags


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

    async def update_titles(
        self,
        gallery_id: int,
        title: str | None,
        title_jpn: str | None,
    ) -> bool: ...


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

    async def _resolve_gdata(
        self, pairs: Sequence[tuple[int, str]], *, force: bool = False
    ) -> dict[int, dict[str, Any]]:
        if not hasattr(self.client, "fetch_gmetadata"):
            return {}
        session = getattr(self.repository, "session", None)
        if session is not None and hasattr(session, "scalars"):
            return await refresh_gdata(session, pairs, client=self.client, force=force)
        from ..app.state import app_state

        sf = getattr(app_state, "background_session_factory", None) or app_state.session_factory
        if sf is not None:
            try:
                async with sf() as sess:
                    if hasattr(sess, "scalars"):
                        async with sess.begin():
                            return await refresh_gdata(sess, pairs, client=self.client, force=force)
            except Exception:  # noqa: BLE001, S110
                pass
        try:
            return await self.client.fetch_gmetadata(pairs)
        except Exception:  # noqa: BLE001
            return {}

    async def _try_enrich_newer(self, gid: int, token: str) -> tuple[int, str] | None:
        session = getattr(self.repository, "session", None)
        if session is not None and hasattr(session, "execute"):
            return await enrich_html_newer(session, gid, token, client=self.client)
        from ..app.state import app_state

        sf = getattr(app_state, "background_session_factory", None) or app_state.session_factory
        if sf is not None:
            try:
                async with sf() as sess:
                    if hasattr(sess, "execute"):
                        async with sess.begin():
                            return await enrich_html_newer(sess, gid, token, client=self.client)
            except Exception:  # noqa: BLE001, S110
                pass
        return None

    async def fetch_plan(
        self, identifier: int, *, force: bool = False, enrich_newer: bool = False
    ) -> dict[str, object]:
        """Read the gallery row and fetch its metadata WITHOUT writing anything to gallery rows.

        Prefers complete cached metadata (from gallery_metadata). If missing or forced,
        fetches full metadata via refresh_gdata. Calls enrich_html_newer only if newer_gid
        banner detection is requested. Falls back to HTML fetcher if gdata client is unavailable.
        """
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None:
            raise GalleryNotFound("Gallery not found")
        gid = getattr(gallery, "gid", None)
        if gid is None:
            raise GalleryGidMissing("Gallery has no ExHentai gid")
        token = getattr(gallery, "token", None)
        if not token:
            raise GalleryTokenMissing("Gallery has no ExHentai token")

        cached = await self.repository.metadata_for_gid(gid)
        if not force and cached and cached.get("tags"):
            if enrich_newer and cached.get("newer_gid") is None:
                try:
                    await self._try_enrich_newer(gid, token)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("enrich_html_newer banner probe failed", extra=log_extra(error=str(exc)))
            return {
                "source": "cache",
                "gid": gid,
                "token": token,
                "title": cached.get("title") or getattr(gallery, "title", None),
                "title_jpn": cached.get("title_jpn") or getattr(gallery, "title_jpn", None),
                "category": cached.get("category") or getattr(gallery, "category", None),
                "tags": _parse_tags(cached.get("tags")),
                "uploader": cached.get("uploader"),
                "posted_at": cached.get("posted_at"),
                "file_size": cached.get("file_size"),
                "file_count": cached.get("file_count"),
                "rating": cached.get("rating"),
                "expunged": cached.get("expunged"),
                "parent_gid": cached.get("parent_gid"),
                "thumb": cached.get("thumb"),
            }

        try:
            gmeta = await self._resolve_gdata([(gid, token)], force=force)
            if gid in gmeta and (gmeta[gid].get("category") or gmeta[gid].get("tags")):
                entry = gmeta[gid]
                if enrich_newer and entry.get("newer_gid") is None:
                    try:
                        await self._try_enrich_newer(gid, token)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("enrich_html_newer probe failed", extra=log_extra(error=str(exc)))
                return {
                    "source": "network",
                    "gid": gid,
                    "token": token,
                    "title": entry.get("title") or getattr(gallery, "title", None),
                    "title_jpn": entry.get("title_jpn") or getattr(gallery, "title_jpn", None),
                    "category": entry.get("category") or getattr(gallery, "category", None),
                    "file_size": entry.get("file_size"),
                    "file_count": entry.get("file_count"),
                    "uploader": entry.get("uploader"),
                    "posted_at": entry.get("posted"),
                    "rating": entry.get("rating"),
                    "expunged": entry.get("expunged"),
                    "parent_gid": entry.get("parent_gid"),
                    "thumb": entry.get("thumb"),
                    "tags": _parse_tags(entry.get("tags")),
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "refresh_gdata failed during tag sync plan, trying fallback",
                extra=log_extra(gid=gid, error=type(exc).__name__),
            )

        metadata_fetcher = getattr(self.client, "fetch_gallery_metadata", None)
        if metadata_fetcher is None:
            metadata = await self.client.fetch_gallery(gid, token)
        else:
            metadata = await metadata_fetcher(gid, token)
        unique_tags = _parse_tags(getattr(metadata, "tags", []))
        return {
            "source": "network",
            "gid": getattr(metadata, "gid", gid),
            "token": token,
            "title": getattr(metadata, "title", None) or getattr(gallery, "title", None),
            "title_jpn": getattr(metadata, "title_jpn", None) or getattr(gallery, "title_jpn", None),
            "category": getattr(metadata, "category", None) or getattr(gallery, "category", None),
            "file_size": getattr(metadata, "file_size", None),
            "file_count": getattr(metadata, "file_count", None),
            "uploader": getattr(metadata, "uploader", None),
            "posted_at": getattr(metadata, "posted", None),
            "rating": getattr(metadata, "rating", None),
            "expunged": getattr(metadata, "expunged", None),
            "parent_gid": getattr(metadata, "parent_gid", None),
            "thumb": getattr(metadata, "thumb", None),
            "tags": unique_tags,
        }

    async def apply_plan(
        self,
        gallery_id: int,
        plan: dict[str, object],
        synced_at: datetime | None = None,
    ) -> int:
        """Persist a fetched metadata plan (call inside a short transaction)."""
        gallery = await self.repository.get_for_tag_sync(gallery_id)
        if gallery is None:
            return 0
        if synced_at is None:
            synced_at = datetime.now(UTC)
        count = await self.repository.replace_tags(
            gallery,
            plan["tags"],  # type: ignore[arg-type]
            synced_at,
            category=plan.get("category"),
        )
        new_title = plan.get("title")
        new_title_jpn = plan.get("title_jpn")
        if (new_title or new_title_jpn) and hasattr(self.repository, "update_titles"):
            await self.repository.update_titles(
                gallery_id,
                str(new_title) if new_title is not None else None,
                str(new_title_jpn) if new_title_jpn is not None else None,
            )
        if plan.get("source") == "network":
            try:
                tags_str = [
                    f"{tag['namespace']}:{tag['name']}"
                    for tag in plan["tags"]  # type: ignore[union-attr]
                    if tag.get("name")
                ]
                await self.repository.upsert_metadata(
                    [
                        {
                            "gid": plan["gid"],
                            "token": plan.get("token"),
                            "title": plan.get("title"),
                            "title_jpn": plan.get("title_jpn"),
                            "category": plan.get("category"),
                            "file_size": plan.get("file_size"),
                            "file_count": plan.get("file_count"),
                            "uploader": plan.get("uploader"),
                            "posted_at": plan.get("posted_at"),
                            "rating": plan.get("rating"),
                            "expunged": plan.get("expunged"),
                            "parent_gid": plan.get("parent_gid"),
                            "thumb": plan.get("thumb"),
                            "tags": tags_str,
                        }
                    ]
                )
            except Exception as exc:  # noqa: BLE001 - cache write must not fail the sync
                logger.warning(
                    "tag sync cache write failed", extra=log_extra(error=type(exc).__name__)
                )
        return count

    async def sync(
        self, identifier: int, *, force: bool = False, enrich_newer: bool = False
    ) -> TagSyncResult:
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None:
            raise GalleryNotFound("Gallery not found")
        gid = getattr(gallery, "gid", None)
        if gid is None:
            raise GalleryGidMissing("Gallery has no ExHentai gid")
        token = getattr(gallery, "token", None)
        if not token:
            raise GalleryTokenMissing("Gallery has no ExHentai token")

        plan = await self.fetch_plan(identifier, force=force, enrich_newer=enrich_newer)
        synced_at = datetime.now(UTC)
        gallery_id = getattr(gallery, "id", identifier)
        count = await self.apply_plan(gallery_id, plan, synced_at=synced_at)
        return TagSyncResult(
            gid,
            str(plan.get("title") or getattr(gallery, "title", None) or ""),
            count,
            synced_at,
            str(plan.get("source") or "network"),
        )

    async def refresh_category(self, identifier: int) -> str | None:
        """Re-fetch a gallery's metadata and refresh only its 大分类.

        Used by the one-time backfill for galleries that were tag-synced before
        category refresh existed (their real category stayed ``other``). Uses
        cached metadata when available; fetches via refresh_gdata (not HTML)
        when missing. Returns the corrected category, or None if gone/unavailable.
        """
        gallery = await self.repository.get_for_tag_sync(identifier)
        if gallery is None:
            return None
        gid = getattr(gallery, "gid", None)
        token = getattr(gallery, "token", None)
        if gid is None or not token:
            return None
        gallery_id = getattr(gallery, "id", identifier)
        cached = await self.repository.metadata_for_gid(gid)
        if cached and cached.get("category"):
            await self.repository.refresh_category(gallery_id, cached["category"])
            return cached["category"]

        category: str | None = None
        try:
            gmeta = await self._resolve_gdata([(gid, token)])
            entry = gmeta.get(gid) or {}
            category = entry.get("category")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "refresh_gdata failed during refresh_category",
                extra=log_extra(gid=gid, error=type(exc).__name__),
            )
        if not category:
            metadata_fetcher = getattr(self.client, "fetch_gallery_metadata", None)
            if metadata_fetcher is not None:
                metadata = await metadata_fetcher(gid, token)
                category = getattr(metadata, "category", None)
            elif hasattr(self.client, "fetch_gallery"):
                metadata = await self.client.fetch_gallery(gid, token)
                category = getattr(metadata, "category", None)
        if category:
            await self.repository.refresh_category(gallery_id, category)
        return category
