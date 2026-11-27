"""Gallery endpoints.

The handlers live in the :mod:`listing`, :mod:`detail`, :mod:`delete`,
``app.routers.reading`` and ``app.routers.maintain.integrity`` submodules; this
module keeps the shared helpers and serialisers and the test patch points.
Every sub-router is included at the registration position its handlers occupied
before the split, so URL paths, route resolution order, the OpenAPI snapshot
and ``monkeypatch.setattr(galleries, ...)`` all keep working.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.models import Gallery, GalleryPage
from ....db.repository import (  # noqa: F401  # tests patch galleries.DownloadRepository
    DownloadRepository,
    GalleryRepository,
)
from ....scanners import registry  # noqa: F401  # tests patch galleries.registry.for_path
from ....scanners.base import CATEGORIES  # noqa: F401  # re-exported for tests
from ....services.deletion import delete_galleries_local  # noqa: F401  # test patch point
from ....services.download_prepare import prepare_galleries  # noqa: F401  # test patch point
from ....services.tag_sync import TagSyncService  # noqa: F401  # test patch point
from ....services.tag_translation import translated_tag
from ....services.thumbnails import ThumbnailService
from ...dependencies import (
    db_error,
    display_title,
    get_current_settings,
    get_eh_client,  # noqa: F401  # test patch point
    get_session,  # noqa: F401  # test patch point
    get_task_manager,  # noqa: F401  # test patch point
    resolve_session,  # noqa: F401  # test patch point
    spawn_task,  # noqa: F401  # test patch point
)
from ...params import (  # noqa: F401  # re-exported; tests patch some of these names
    _IMAGE_QUALITY,
    _dedupe_tags,
    _parse_posted,
    _parse_tag_filter,
    _resolve_search_tokens,
    _tag_count,
    _tags_for_galleries,
)
from ...schemas import DownloadOriginalRequest  # noqa: F401
from ...state import app_state
from .. import galleries_media, maintain, reading
from ..downloads import _create_from_prepared  # noqa: F401  # test patch point
from ..maintain.integrity import (  # noqa: F401  # re-exported handlers
    list_integrity,
    trigger_integrity_scan,
)
from ..reading import (  # noqa: F401  # re-exported handlers
    clear_all_gallery_progress,
    clear_gallery_progress,
    clear_history,
    gallery_progress,
    history,
    save_gallery_progress,
)
from . import delete, detail, listing
from .delete import (  # noqa: F401  # re-exported handlers / test patch point
    _record_gallery_delete_log,
    delete_galleries_bulk,
    delete_galleries_filtered,
    delete_gallery,
)
from .detail import (  # noqa: F401  # re-exported handlers
    archive_gallery,
    download_gallery_original,
    gallery_detail,
    gallery_favorite_status,
    gallery_next,
    get_gallery,
    patch_gallery_local,
    redownload_gallery,
    sync_gallery_tags,
    unarchive_gallery,
)
from .listing import (  # noqa: F401  # re-exported handlers
    ExpungedRedownloadRequest,
    gallery_list,
    gallery_random,
    list_expunged,
    list_galleries,
    list_trash,
    purge_galleries,
    random_gallery,
    redownload_expunged,
    restore_galleries,
)

from ..media_probe import (  # noqa: F401  # isort: skip
    _fast_parse_gif_duration, _fast_parse_webp_duration, _inspect_image_meta,
    _skip_stream_bytes, _skip_subblocks,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _gallery_lookup(
    identifier: int, session: AsyncSession | None = None
) -> tuple[Gallery, list[GalleryPage]]:
    if session is None:
        if not app_state.session_factory:
            raise HTTPException(status_code=503, detail="Database session factory not initialized")
        async with app_state.session_factory() as s:
            return await _gallery_lookup(identifier, session=s)
    try:
        repo = GalleryRepository(session)
        row = await repo.get_by_id(identifier)
        if row is None:
            row = await repo.get_by_gid(identifier)
        if row is None:
            raise HTTPException(status_code=404, detail="Gallery not found")
        pages = await repo.get_pages(row.id)
        return row, list(pages)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


async def _gallery_tags_lookup(
    gallery_id: int, session: AsyncSession | None = None
) -> list[tuple[str, str]]:
    if session is None:
        if not app_state.session_factory:
            raise HTTPException(status_code=503, detail="Database session factory not initialized")
        async with app_state.session_factory() as s:
            return await _gallery_tags_lookup(gallery_id, session=s)
    try:
        repo = GalleryRepository(session)
        if hasattr(repo, "tags_for_gallery"):
            return await repo.tags_for_gallery(gallery_id)
        tag_map = await repo.tags_for_galleries([gallery_id])
        return tag_map.get(gallery_id, [])
    except Exception as exc:
        raise db_error(exc) from exc


async def _gallery(identifier: int, session: AsyncSession | None = None) -> tuple[Gallery, list[GalleryPage]]:
    try:
        return await _gallery_lookup(identifier, session=session)
    except TypeError:
        return await _gallery_lookup(identifier)


_default_gallery = _gallery


async def _invoke_gallery(
    identifier: int, session: AsyncSession | None = None
) -> tuple[Gallery, list[GalleryPage]]:
    target = _gallery
    try:
        sig = inspect.signature(target)
        accepts_session = "session" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (ValueError, TypeError):
        accepts_session = True

    if accepts_session:
        try:
            return await target(identifier, session=session)
        except TypeError as exc:
            if "unexpected keyword argument" in str(exc) and "session" in str(exc):
                return await target(identifier)
            raise
    return await target(identifier)


async def _gallery_tags(
    gallery_id: int, session: AsyncSession | None = None
) -> list[tuple[str, str]]:
    try:
        return await _gallery_tags_lookup(gallery_id, session=session)
    except TypeError:
        return await _gallery_tags_lookup(gallery_id)


def _get_thumb_service() -> ThumbnailService:
    if app_state.thumbnail_service is not None:
        return app_state.thumbnail_service
    settings = get_current_settings()
    service = ThumbnailService(settings.thumbnail_cache_dir)
    app_state.thumbnail_service = service
    return service


# --- Gallery payload serialisers -------------------------------------------
# One definition per payload shape; the endpoint lists below only combine rows
# with the tag/progress maps.  ``_g`` keeps tolerance for older rows and the
# lightweight doubles used by tests instead of repeating ``getattr(row, …)``.

_SPIDER_KEYS = (
    "version",
    "start_page",
    "gid",
    "token",
    "mode",
    "preview_pages",
    "preview_per_page",
    "pages",
    "p_tokens",
    "page_entries",
    "warnings",
)

_TRASH_ITEM_KEYS = (
    "id",
    "gid",
    "token",
    "title",
    "title_jpn",
    "category",
    "page_count",
    "cover_url",
    "trashed_at",
    "storage_path",
    "tags",
    "tag_count",
    "reading_progress",
)

_EXPUNGED_ITEM_KEYS = (
    "id",
    "gid",
    "token",
    "title",
    "page_count",
    "cover_url",
    "updated_at",
    "storage_path",
    "tags",
    "tag_count",
)

_INTEGRITY_ITEM_KEYS = (
    "id",
    "gid",
    "title",
    "page_count",
    "actual_pages",
    "file_count",
    "cover_url",
    "storage_path",
    "tags",
)


def _g(obj: Any, name: str, default: Any = None) -> Any:
    """Read an optional attribute from ORM rows and lightweight test doubles."""
    return getattr(obj, name, default)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _tag_previews(tags: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
        for ns, name in tags
    ]


def serialize_gallery_summary(
    row: Any,
    tag_map: dict[int, list[tuple[str, str]]],
    *,
    reading_progress: int | None = None,
) -> dict[str, Any]:
    """Canonical gallery row shared by the list and the recycle views."""
    page_count = _g(row, "page_count", 0) or 0
    return {
        "id": row.id,
        "gid": _g(row, "gid"),
        "token": _g(row, "token"),
        "title": display_title(row),
        "title_english": _g(row, "title"),
        "title_jpn": _g(row, "title_jpn"),
        "storage_type": _g(row, "storage_type", "ehviewer_dir"),
        "storage_tier": _g(row, "storage_tier", "hot"),
        "cold_at": _iso(_g(row, "cold_at")),
        "category": _g(row, "category", "other") or "other",
        "page_count": page_count,
        "cover_url": f"/api/galleries/{row.id}/thumb/0" if page_count else None,
        "tags": _tag_previews(tag_map.get(row.id, [])),
        "tag_count": _tag_count(tag_map, row.id),
        "uploader": _g(row, "uploader"),
        "posted_at": _iso(_g(row, "posted_at")),
        "file_size": _g(row, "file_size"),
        "storage_size": _g(row, "storage_size", 0),
        "rating": _g(row, "rating"),
        "favorite": _g(row, "favorite", False),
        "favorite_category": _g(row, "favorite_category"),
        "reading_progress": reading_progress,
        "expunged": _g(row, "expunged", False),
        "image_quality": _g(row, "image_quality"),
        "local_rating": _g(row, "local_rating"),
        "local_note": _g(row, "local_note"),
    }


def serialize_gallery_trash_item(
    row: Any,
    tag_map: dict[int, list[tuple[str, str]]],
    progress_map: dict[int, int],
) -> dict[str, Any]:
    item = serialize_gallery_summary(
        row, tag_map, reading_progress=progress_map.get(row.id)
    )
    item["trashed_at"] = _iso(_g(row, "trashed_at"))
    item["storage_path"] = _g(row, "storage_path", "")
    return {key: item[key] for key in _TRASH_ITEM_KEYS}


def serialize_gallery_expunged_item(
    row: Any,
    tag_map: dict[int, list[tuple[str, str]]],
) -> dict[str, Any]:
    item = serialize_gallery_summary(row, tag_map)
    item["updated_at"] = _iso(_g(row, "updated_at"))
    item["storage_path"] = _g(row, "storage_path", "")
    return {key: item[key] for key in _EXPUNGED_ITEM_KEYS}


def serialize_gallery_integrity_item(
    row: Any,
    tag_map: dict[int, list[tuple[str, str]]],
    actual_pages: int,
) -> dict[str, Any]:
    item = serialize_gallery_summary(row, tag_map)
    item["actual_pages"] = actual_pages
    item["file_count"] = _g(row, "file_count")
    item["storage_path"] = _g(row, "storage_path", "")
    return {key: item[key] for key in _INTEGRITY_ITEM_KEYS}


def serialize_gallery_detail(
    row: Any,
    pages: list[Any],
    tags: list[tuple[str, str]],
    settings: Any,
) -> dict[str, Any]:
    source_meta = _g(row, "source_meta") or {}
    gid = _g(row, "gid")
    token = _g(row, "token")
    gallery_url = (
        f"{settings.exhentai_base_url.rstrip('/')}/g/{gid}/{token}/" if gid and token else None
    )
    return {
        "id": row.id,
        "gid": gid,
        "token": token,
        "title": display_title(row),
        "title_english": _g(row, "title"),
        "title_jpn": _g(row, "title_jpn"),
        "storage_type": _g(row, "storage_type", "ehviewer_dir"),
        "storage_tier": _g(row, "storage_tier", "hot"),
        "cold_at": _iso(_g(row, "cold_at")),
        "category": _g(row, "category", "other") or "other",
        "page_count": len(pages),
        "file_size": _g(row, "file_size"),
        "storage_size": _g(row, "storage_size", 0),
        "uploader": _g(row, "uploader"),
        "posted_at": _iso(_g(row, "posted_at")),
        "rating": _g(row, "rating"),
        "favorite": _g(row, "favorite", False),
        "favorite_category": _g(row, "favorite_category"),
        "reading_progress": _g(row, "reading_progress"),
        "expunged": _g(row, "expunged", False),
        "image_quality": _g(row, "image_quality"),
        "local_rating": _g(row, "local_rating"),
        "local_note": _g(row, "local_note"),
        "storage_path": _g(row, "storage_path", ""),
        "eh_url": gallery_url or "",
        "exhentai_url": gallery_url,
        "warnings": source_meta.get("warnings", []),
        "spider_info": {key: source_meta[key] for key in _SPIDER_KEYS if key in source_meta},
        "source_meta": source_meta,
        "tags": _tag_previews(tags),
        "tags_synced_at": _g(row, "tags_synced_at"),
        "pages": [
            {
                "index": p.page_index,
                "page_index": p.page_index,
                "name": p.member_name,
                "member_name": p.member_name,
                "media_type": p.media_type,
                "image_url": f"/api/galleries/{row.id}/pages/{p.page_index}",
                "thumb_url": f"/api/galleries/{row.id}/thumb/{p.page_index}",
            }
            for p in pages
        ],
    }


# Listing handlers (``/api/galleries``, ``/trash``, ``/expunged``, ...) were the
# first routes registered here.
router.include_router(listing.router)


# Integrity handlers live in ``maintain.integrity``; the sub-router is
# included at the exact registration position they occupied.
router.include_router(maintain.integrity.router)


# ``restore``/``purge``/``random`` were registered after the integrity routes.
router.include_router(listing.bulk_router)

# Single-gallery handlers: ``next``, detail, local patch, original download and
# favourite status.
router.include_router(detail.router)


# Local reading progress/history.  The router is included at this exact spot:
# ``DELETE /api/galleries/progress`` must be registered before the deletion
# routes, whose ``DELETE /api/galleries/{identifier}`` would otherwise shadow it.
router.include_router(reading.router)


# Background single-gallery actions: redownload, archive and unarchive.
router.include_router(detail.background_router)

# Deletion routes (``DELETE /api/galleries/{identifier}`` and the batch forms).
router.include_router(delete.router)


# ``sync-tags`` was registered after the delete routes.
router.include_router(detail.sync_router)


# Media endpoints live in ``galleries_media``; include them at the tail so the
# original route registration order is unchanged.
router.include_router(galleries_media.router)

get_page = galleries_media.get_page
get_page_meta = galleries_media.get_page_meta
export_gallery_cbz = galleries_media.export_gallery_cbz
_page_media_type = galleries_media._page_media_type
_closing_stream = galleries_media._closing_stream
_meta = galleries_media._meta
_unlink_export = galleries_media._unlink_export
_thumb_file_response = galleries_media._thumb_file_response
get_thumbnail = galleries_media.get_thumbnail

gallery_page = get_page
gallery_page_meta = get_page_meta
gallery_thumbnail = get_thumbnail
