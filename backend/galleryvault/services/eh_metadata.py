"""Unified ExHentai metadata service.

Single source of truth for:
- Batch gdata querying and caching (refresh_gdata)
- HTML replacement banner resolution (enrich_html_newer)
- Applying cached metadata to local galleries or ingest items (apply_cached_metadata)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.state import app_state
from ..db.models import Gallery, GalleryMetadata
from ..db.repositories.galleries import GalleryRepository
from ..logging import log_extra
from .eh_client import EhChallengeError, EhClient, EhClientError, GalleryGoneError

if TYPE_CHECKING:
    from ..scanners.base import GalleryMeta

logger = logging.getLogger(__name__)

EXHENTAI_API_CHUNK_SIZE = 25


def is_metadata_complete(meta: dict[str, Any] | None) -> bool:
    """Check if cached metadata has all core fields so network gdata can be skipped."""
    if not meta:
        return False
    if meta.get("expunged"):
        return True
    return bool(
        meta.get("category")
        and meta.get("uploader")
        and meta.get("posted_at") is not None
    )


async def refresh_gdata(
    session: AsyncSession,
    pairs: Sequence[tuple[int, str]],
    client: EhClient | None = None,
    *,
    force: bool = False,
    batch_size: int = EXHENTAI_API_CHUNK_SIZE,
) -> dict[int, dict[str, Any]]:
    """Batch refresh metadata from gdata API into gallery_metadata cache.

    If cached and complete, network fetch is skipped unless force=True.
    Fetches missing or incomplete entries in chunks of 25 and persists them.
    Returns metadata dict for all requested gids: {gid: {...}}.
    """
    if not pairs:
        return {}

    repo = GalleryRepository(session)
    gids = [int(gid) for gid, _ in pairs]
    cached = await repo.metadata_map(gids)

    if force:
        missing = [(int(gid), str(token)) for gid, token in pairs if token]
    else:
        missing = [
            (int(gid), str(token))
            for gid, token in pairs
            if token and (int(gid) not in cached or not is_metadata_complete(cached[int(gid)]))
        ]

    if not missing:
        return cached

    active_client = client or app_state.eh_client
    if active_client is None or not hasattr(active_client, "fetch_gmetadata"):
        return cached

    fetched: dict[int, dict[str, Any]] = {}
    for start in range(0, len(missing), batch_size):
        chunk = missing[start : start + batch_size]
        try:
            chunk_meta = await active_client.fetch_gmetadata(chunk)
            fetched.update(chunk_meta)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gdata batch failed during metadata resolution",
                extra=log_extra(error=type(exc).__name__, count=len(chunk)),
            )

    if fetched:
        entries = [{"gid": gid, **meta} for gid, meta in fetched.items()]
        await repo.upsert_metadata(entries)
        # Reload fully formatted metadata rows from repository
        refreshed = await repo.metadata_map(list(fetched.keys()))
        cached.update(refreshed)

    return cached


async def enrich_html_newer(
    session: AsyncSession,
    gid: int,
    token: str,
    client: EhClient | None = None,
) -> tuple[int, str] | None:
    """Check HTML /g/ banner for newer replacement version.

    Only invoked when caller explicitly needs replacement tracking or
    gdata reported expunged=True. Persists newer_gid and is_replaced to
    gallery_metadata without overwriting gdata tags or titles.
    Returns (newer_gid, newer_token) if replaced, or None.
    """
    active_client = client or app_state.eh_client
    if active_client is None:
        return None

    fetch_meta = getattr(active_client, "fetch_gallery_metadata", None)
    if fetch_meta is None:
        fetch_meta = getattr(active_client, "fetch_gallery", None)
    if fetch_meta is None:
        return None

    try:
        data = await fetch_meta(gid, token)
        replaced = getattr(data, "replaced_by", None)
        newer_gid = int(replaced[0]) if replaced else None
        is_replaced = replaced is not None

        now = datetime.now(UTC)
        stmt = (
            pg_insert(GalleryMetadata)
            .values(
                gid=int(gid),
                token=str(token),
                newer_gid=newer_gid,
                is_replaced=is_replaced,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["gid"],
                set_={
                    "newer_gid": newer_gid,
                    "is_replaced": is_replaced,
                },
            )
        )
        await session.execute(stmt)
        return replaced
    except GalleryGoneError:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(GalleryMetadata)
            .values(
                gid=int(gid),
                token=str(token),
                expunged=True,
                is_replaced=False,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["gid"],
                set_={
                    "expunged": True,
                    "is_replaced": False,
                },
            )
        )
        await session.execute(stmt)
        return None
    except (EhChallengeError, EhClientError) as exc:
        logger.warning(
            "enrich_html_newer failed",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )
        raise


async def apply_cached_metadata(
    session: AsyncSession,
    galleries: Sequence[Gallery] | None = None,
    *,
    favcat: int | None = None,
    limit: int = 200,
) -> int:
    """Apply cached metadata from gallery_metadata to local Gallery records.

    Delegates to GalleryRepository.apply_cached_metadata.
    """
    repo = GalleryRepository(session)
    return await repo.apply_cached_metadata(galleries, favcat=favcat, limit=limit)


def apply_cached_metadata_to_meta(
    gallery: GalleryMeta | Any,
    meta: dict[str, Any],
) -> None:
    """Apply cached metadata dict to an in-memory GalleryMeta object (used during ingest)."""
    tags = getattr(gallery, "tags", None)
    if not tags and meta.get("tags"):
        gallery.tags = [
            {"namespace": str(t.get("namespace") or "misc"), "name": str(t.get("name") or "")}
            for t in meta["tags"]
            if str(t.get("name") or "").strip()
        ]
    if hasattr(gallery, "category"):
        gallery.category = getattr(gallery, "category", None) or meta.get("category")
    if hasattr(gallery, "title_jpn"):
        gallery.title_jpn = getattr(gallery, "title_jpn", None) or meta.get("title_jpn")
    if hasattr(gallery, "rating") and meta.get("rating") is not None and getattr(gallery, "rating", None) is None:
        gallery.rating = meta["rating"]
    if hasattr(gallery, "posted_at"):
        gallery.posted_at = getattr(gallery, "posted_at", None) or meta.get("posted_at")
    if hasattr(gallery, "uploader"):
        gallery.uploader = getattr(gallery, "uploader", None) or meta.get("uploader")
    if hasattr(gallery, "file_count"):
        gallery.file_count = getattr(gallery, "file_count", None) or meta.get("file_count")
    if hasattr(gallery, "source_meta") and meta.get("parent_gid") is not None:
        source_meta = dict(getattr(gallery, "source_meta", None) or {})
        source_meta["parent_gid"] = meta["parent_gid"]
        gallery.source_meta = source_meta
