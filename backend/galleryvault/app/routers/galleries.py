"""Gallery endpoints."""

from __future__ import annotations

import inspect
import io
import logging
import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, ImageSequence
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from ...db.models import Gallery, GalleryPage
from ...db.repository import (
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    _chunked,
)
from ...db.session import safe_transaction
from ...logging import log_extra
from ...scanners import registry
from ...scanners.base import CATEGORIES, GalleryMeta, PageInfo
from ...services.deletion import delete_galleries_local
from ...services.download_prepare import prepare_galleries
from ...services.eh_client import FavoriteData
from ...services.export_cbz import (
    UnsafeExportPath,
    cbz_filename,
    is_cbz_file,
    pack_directory_cbz,
)
from ...services.favorites_worker import ensure_remote_cover
from ...services.gallery_service import GalleryService
from ...services.tag_sync import (
    GalleryGidMissing,
    GalleryNotFound,
    GalleryTokenMissing,
    TagSyncService,
)
from ...services.tag_translation import translated_tag
from ...services.thumbnails import JPEG_MIME, ThumbnailError, ThumbnailService
from ..core.eh_client_manager import EhClientManager
from ..dependencies import (
    db_error,
    display_title,
    get_current_settings,
    get_eh_client,
    get_eh_client_manager,
    get_gallery_service,
    get_session,
    get_task_manager,
    image_content_type,
    resolve_session,
    spawn_task,
)
from ..schemas import (
    BulkDeleteRequest,
    DownloadOriginalRequest,
    FilteredDeleteRequest,
    GalleryLocalRequest,
    ProgressRequest,
)
from ..state import app_state
from .downloads import _create_from_prepared

logger = logging.getLogger(__name__)
router = APIRouter()

_PAGE_STREAM_CHUNK = 256 * 1024
_IMAGE_QUALITY = frozenset({"original", "resample"})


def _parse_posted(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid posted date") from exc


def _page_media_type(ext: str) -> str:
    """Map a page file extension to a standards-compliant media type."""
    return {"jpg": "image/jpeg", "jpe": "image/jpeg", "jpeg": "image/jpeg"}.get(
        (ext or "").lower(), f"image/{ext}"
    )


def _closing_stream(stream: BinaryIO) -> Iterator[bytes]:
    """Yield a sync page stream in 256KB chunks, closing the file when exhausted."""
    try:
        while True:
            chunk = stream.read(_PAGE_STREAM_CHUNK)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _meta(row: Gallery, pages: list[GalleryPage]) -> GalleryMeta:
    return GalleryMeta(
        title=row.title,
        path=Path(row.storage_path or ""),
        storage_type=row.storage_type or "ehviewer_dir",
        pages=[
            PageInfo(
                p.page_index,
                p.member_name or f"{p.page_index:04d}",
                p.media_type or "jpg",
                (p.manifest or {}).get("size"),
                (p.manifest or {}).get("mtime_ns"),
            )
            for p in pages
        ],
        gid=row.gid,
        token=row.token,
        storage_signature=row.storage_signature,
    )


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


def _dedupe_tags(tags: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    seen: set[tuple[str | None, str]] = set()
    out: list[tuple[str | None, str]] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _parse_tag_filter(
    tags: str | None,
) -> tuple[list[tuple[str | None, str]], list[tuple[str | None, str]]]:
    include_tags: list[tuple[str | None, str]] = []
    exclude_tags: list[tuple[str | None, str]] = []
    for value in (tags or "").split(","):
        value = value.strip()
        if not value:
            continue
        is_exclude = False
        if value.startswith("-") and len(value) > 1:
            is_exclude = True
            value = value[1:].strip()
        if ":" in value:
            namespace, name = value.split(":", 1)
            namespace = namespace.strip() or None
        else:
            namespace, name = None, value
        if not name.strip() or len(name) > 200 or (namespace and len(namespace) > 32):
            raise HTTPException(status_code=422, detail="invalid tag")
        tag_tuple = (namespace, name.strip())
        if is_exclude:
            exclude_tags.append(tag_tuple)
        else:
            include_tags.append(tag_tuple)
    return include_tags, exclude_tags


async def _resolve_search_tokens(
    q: str,
) -> tuple[list[tuple[str | None, str]], list[tuple[str | None, str]], str, bool]:
    tokens = q.split()
    if not tokens:
        return [], [], "", False
    explicit_inc: list[tuple[str | None, str]] = []
    explicit_exc: list[tuple[str | None, str]] = []
    keywords: list[str] = []
    for token in tokens:
        # "-ns:name" or "-name" is an exclude tag, not a keyword
        if token.startswith("-") and len(token) > 1 and not token.startswith("--"):
            inner = token[1:]
            if ":" in inner:
                namespace, name = inner.split(":", 1)
                namespace = namespace.strip() or None
                name = name.strip()
                if name:
                    explicit_exc.append((namespace, name))
                    continue
            else:
                name = inner.strip()
                if name:
                    explicit_exc.append((None, name))
                    continue
        if ":" in token:
            namespace, name = token.split(":", 1)
            namespace = namespace.strip() or None
            name = name.strip()
            if name:
                explicit_inc.append((namespace, name))
            else:
                keywords.append(token)
        else:
            keywords.append(token)
    return explicit_inc, explicit_exc, " ".join(keywords), bool(explicit_inc or explicit_exc)


@router.get("/api/galleries")
async def list_galleries(
    page: int = 1,
    page_size: int = 24,
    q: str | None = None,
    tags: str | None = None,
    exclude_tags: str | None = None,
    tag_mode: str = "or",
    tag_match: str = "exact",
    category: str | None = None,
    order_by: str = "id_desc",
    read_status: str | None = None,
    min_rating: float | None = None,
    page_min: int | None = None,
    page_max: int | None = None,
    size_min: int | None = None,
    size_max: int | None = None,
    posted_from: str | None = None,
    posted_to: str | None = None,
    uploader: str | None = None,
    image_quality: str | None = None,
    min_local_rating: int | None = Query(default=None, ge=1, le=5),
    list_id: int | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(
            status_code=422, detail="page must be >= 1 and page_size must be between 1 and 500"
        )
    if tag_mode not in {"and", "or"} or tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    if read_status and read_status not in {"all", "unread", "reading", "completed", "read"}:
        raise HTTPException(status_code=422, detail="invalid read_status")
    if image_quality:
        image_quality = image_quality.strip().lower()
        if image_quality not in _IMAGE_QUALITY:
            raise HTTPException(status_code=422, detail="invalid image_quality")
    else:
        image_quality = None
    posted_from_dt = _parse_posted(posted_from)
    posted_to_dt = _parse_posted(posted_to)
    if category == "":
        category = None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    elif category and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {', '.join(CATEGORIES)}")

    parsed_inc_tags, parsed_exc_tags = _parse_tag_filter(tags)
    if exclude_tags:
        extra_inc, extra_exc = _parse_tag_filter(exclude_tags)
        parsed_exc_tags.extend(extra_inc)
        parsed_exc_tags.extend(extra_exc)

    resolved_q = q or ""
    resolved = False
    if q and q.strip():
        auto_inc, auto_exc, keywords, changed = await _resolve_search_tokens(q)
        resolved = changed
        if changed:
            parsed_inc_tags.extend(auto_inc)
            parsed_exc_tags.extend(auto_exc)
            resolved_q = keywords

    parsed_inc_tags = _dedupe_tags(parsed_inc_tags)
    parsed_exc_tags = _dedupe_tags(parsed_exc_tags)
    try:
        repo_cls = GalleryRepository
        repo = repo_cls(session)
        tag_id_map: dict[tuple[str | None, str], int] = {}
        if tag_match == "exact":
            candidates = parsed_inc_tags + parsed_exc_tags
            if candidates:
                tag_id_map = await repo.resolve_exact_tags(candidates)
        total, rows = await repo.list_page(
            page,
            page_size,
            q=resolved_q,
            tags=parsed_inc_tags if parsed_inc_tags else (),
            exclude_tags=parsed_exc_tags if parsed_exc_tags else (),
            tag_mode=tag_mode,
            tag_match=tag_match,
            tag_id_map=tag_id_map,
            category=category,
            exclude_favorited=exclude_favorited,
            order_by=order_by,
            read_status=read_status,
            min_rating=min_rating,
            page_min=page_min,
            page_max=page_max,
            size_min=size_min,
            size_max=size_max,
            posted_from=posted_from_dt,
            posted_to=posted_to_dt,
            uploader=uploader,
            image_quality=image_quality,
            min_local_rating=min_local_rating,
            list_id=list_id,
        )
        g_ids = [r.id for r in rows if getattr(r, "id", None)]
        tag_map = await repo_cls(session).tags_for_galleries(g_ids)
        progress_map = await repo_cls(session).progress_for_galleries(g_ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    tag_str_parts = []
    if parsed_inc_tags:
        tag_str_parts.extend(
            f"{namespace}:{name}" if namespace else name
            for namespace, name in parsed_inc_tags
        )
    if parsed_exc_tags:
        tag_str_parts.extend(
            f"-{namespace}:{name}" if namespace else f"-{name}"
            for namespace, name in parsed_exc_tags
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "q": resolved_q,
        "tags": ",".join(tag_str_parts),
        "resolved": resolved,
        "tag_mode": tag_mode,
        "tag_match": tag_match,
        "order_by": order_by,
        "read_status": read_status or "all",
        "category": "__not_fav__" if exclude_favorited else (category or ""),
        "query_tags": (
            [
                {
                    "namespace": ns,
                    "name": name,
                    "display": translated_tag(ns or "misc", name)[1],
                }
                for ns, name in parsed_inc_tags
            ]
            if resolved
            else []
        ),
        "items": [
            {
                "id": row.id,
                "gid": getattr(row, "gid", None),
                "token": getattr(row, "token", None),
                "title": display_title(row),
                "title_english": getattr(row, "title", None),
                "title_jpn": getattr(row, "title_jpn", None),
                "storage_type": getattr(row, "storage_type", "ehviewer_dir"),
                "category": getattr(row, "category", "other") or "other",
                "page_count": getattr(row, "page_count", 0) or 0,
                "cover_url": f"/api/galleries/{row.id}/thumb/0" if getattr(row, "page_count", 0) else None,
                "tags": [
                    {
                        "namespace": ns,
                        "name": name,
                        "display": translated_tag(ns, name)[1],
                    }
                    for ns, name in tag_map.get(row.id, [])
                ],
                "uploader": getattr(row, "uploader", None),
                "posted_at": row.posted_at.isoformat() if getattr(row, "posted_at", None) else None,
                "file_size": getattr(row, "file_size", None),
                "storage_size": getattr(row, "storage_size", 0),
                "rating": getattr(row, "rating", None),
                "favorite": getattr(row, "favorite", False),
                "favorite_category": getattr(row, "favorite_category", None),
                "reading_progress": progress_map.get(row.id, getattr(row, "reading_progress", None)),
                "expunged": getattr(row, "expunged", False),
                "image_quality": getattr(row, "image_quality", None),
                "local_rating": getattr(row, "local_rating", None),
                "local_note": getattr(row, "local_note", None),
            }
            for row in rows
        ],
    }


gallery_list = list_galleries


@router.get("/api/galleries/trash")
async def list_trash(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        total, rows = await GalleryRepository(session).list_trashed(page, page_size)
        g_ids = [r.id for r in rows]
        tag_map = await GalleryRepository(session).tags_for_galleries(g_ids)
        progress_map = await GalleryRepository(session).progress_for_galleries(g_ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": row.id,
                "gid": getattr(row, "gid", None),
                "token": getattr(row, "token", None),
                "title": display_title(row),
                "title_jpn": getattr(row, "title_jpn", None),
                "category": getattr(row, "category", "other") or "other",
                "page_count": getattr(row, "page_count", 0) or 0,
                "cover_url": f"/api/galleries/{row.id}/thumb/0" if getattr(row, "page_count", 0) else None,
                "trashed_at": row.trashed_at.isoformat() if getattr(row, "trashed_at", None) else None,
                "storage_path": getattr(row, "storage_path", ""),
                "tags": [
                    {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                    for ns, name in tag_map.get(row.id, [])
                ],
                "reading_progress": progress_map.get(row.id),
            }
            for row in rows
        ],
    }


@router.get("/api/galleries/expunged")
async def list_expunged(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        total, rows = await GalleryRepository(session).list_expunged(page, page_size)
        g_ids = [r.id for r in rows]
        tag_map = await GalleryRepository(session).tags_for_galleries(g_ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": row.id,
                "gid": getattr(row, "gid", None),
                "token": getattr(row, "token", None),
                "title": display_title(row),
                "page_count": getattr(row, "page_count", 0) or 0,
                "cover_url": f"/api/galleries/{row.id}/thumb/0" if getattr(row, "page_count", 0) else None,
                "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
                "storage_path": getattr(row, "storage_path", ""),
                "tags": [
                    {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                    for ns, name in tag_map.get(row.id, [])
                ],
            }
            for row in rows
        ],
    }


class ExpungedRedownloadRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


@router.post("/api/galleries/expunged/redownload", status_code=200)
async def redownload_expunged(
    body: ExpungedRedownloadRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    ids = body.ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    unique_ids = list(dict.fromkeys(ids))
    galleries: list[Gallery] = []
    try:
        repo = GalleryRepository(session)
        for chunk in _chunked(unique_ids):
            rows = await repo.find_by_ids(chunk)
            galleries.extend(rows)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    gallery_map = {row.id: row for row in galleries}
    queued = 0
    skipped_no_gid = 0
    skipped_no_token = 0
    valid_targets: list[tuple[Gallery, int, str]] = []

    for gid_id in unique_ids:
        row = gallery_map.get(gid_id)
        if row is None or not row.gid:
            skipped_no_gid += 1
            continue
        token = getattr(row, "token", None)
        if not token:
            skipped_no_token += 1
            continue
        valid_targets.append((row, int(row.gid), str(token)))

    if valid_targets:
        pairs = [(gid, token) for _, gid, token in valid_targets]
        prepared_list = await prepare_galleries(pairs)
        default_quality = get_current_settings().download_quality or "resample"
        for (row, _, _), prepared in zip(valid_targets, prepared_list, strict=True):
            if row.title and not prepared.title:
                prepared.title = row.title
            try:
                status, _ = await _create_from_prepared(
                    prepared,
                    mode="gallery",
                    max_pages=None,
                    quality=default_quality,
                    fallback_title=row.title,
                )
            except Exception:  # noqa: BLE001, S112
                continue
            if status in ("queued", "updated"):
                queued += 1

        now = datetime.now(UTC).isoformat()
        tm = get_task_manager()
        tm.record_task(
            "download-enqueue",
            now,
            now,
            "success",
            reason=f"expunged redownload queued {queued}",
            done=queued,
            total=len(valid_targets),
        )
        spawn_task(tm.persist_history(), "persist task history")

    return {
        "queued": queued,
        "skipped_no_gid": skipped_no_gid,
        "skipped_no_token": skipped_no_token,
    }


@router.get("/api/galleries/integrity")
async def list_integrity(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")

    tm = get_task_manager()
    integrity_state = tm.integrity_state
    extra_ids = list(integrity_state.get("corrupt_ids") or [])

    try:
        repo = GalleryRepository(session)
        total, rows = await repo.list_integrity_issues(
            page, page_size, extra_ids=extra_ids
        )
        g_ids = [r.id for r in rows]
        tag_map = await repo.tags_for_galleries(g_ids)
        counts = {}
        if g_ids:
            if hasattr(repo, "page_counts_for_galleries"):
                counts = await repo.page_counts_for_galleries(g_ids)
            else:
                for gid in g_ids:
                    pgs = await repo.get_pages(gid)
                    counts[gid] = len(pgs)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    magic_scan_summary = {
        "running": bool(integrity_state.get("running")),
        "started_at": integrity_state.get("started_at"),
        "completed_at": integrity_state.get("completed_at"),
        "scanned": int(integrity_state.get("scanned", 0) or 0),
        "total": int(integrity_state.get("total", 0) or 0),
        "corrupt": len(extra_ids),
    }

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "magic_scan": magic_scan_summary,
        "items": [
            {
                "id": row.id,
                "gid": getattr(row, "gid", None),
                "title": display_title(row),
                "page_count": getattr(row, "page_count", 0) or 0,
                "actual_pages": counts.get(row.id, 0),
                "file_count": getattr(row, "file_count", None),
                "cover_url": f"/api/galleries/{row.id}/thumb/0" if getattr(row, "page_count", 0) else None,
                "storage_path": getattr(row, "storage_path", ""),
                "tags": [
                    {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                    for ns, name in tag_map.get(row.id, [])
                ],
            }
            for row in rows
        ],
    }


@router.post("/api/galleries/integrity/scan", status_code=202)
async def trigger_integrity_scan() -> dict[str, object]:
    settings = get_current_settings()
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: integrity scan is disabled"}
    tm = get_task_manager()
    integrity_state = tm.integrity_state
    if not integrity_state.get("running"):
        from ...services.integrity_worker import run_integrity_magic_scan

        integrity_state["running"] = True
        integrity_state["started_at"] = datetime.now(UTC).isoformat()
        spawn_task(run_integrity_magic_scan(), "integrity magic scan")

    corrupt_ids = list(integrity_state.get("corrupt_ids") or [])
    magic_scan_summary = {
        "running": bool(integrity_state.get("running")),
        "started_at": integrity_state.get("started_at"),
        "completed_at": integrity_state.get("completed_at"),
        "scanned": int(integrity_state.get("scanned", 0) or 0),
        "total": int(integrity_state.get("total", 0) or 0),
        "corrupt": len(corrupt_ids),
    }
    return magic_scan_summary


@router.post("/api/galleries/restore", status_code=200)
async def restore_galleries(
    body: BulkDeleteRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        async with safe_transaction(session):
            restored = await GalleryRepository(session).restore_galleries(ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"restored": restored}


@router.post("/api/galleries/purge", status_code=200)
async def purge_galleries(
    body: BulkDeleteRequest,
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        unique_ids = list(dict.fromkeys(ids))
        results: list[dict] = []
        for chunk in _chunked(unique_ids):
            batch_results = await delete_galleries_local(
                chunk,
                delete_files=body.delete_files,
                delete_all_copies=body.delete_all_copies,
                trash=False,
            )
            results.extend(batch_results)
        purged = sum(1 for r in results if r.get("db_removed"))
        failed = [p for r in results for p in r.get("failed_paths", [])]
        _record_gallery_delete_log(results, body.delete_files)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"purged": purged, "failed_deletions": failed, "results": results}


@router.get("/api/galleries/categories")
async def list_categories(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        counts = await GalleryRepository(session).category_counts()
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "categories": [
            {"name": cat, "count": counts.get(cat, 0)}
            for cat in CATEGORIES
        ]
    }


@router.get("/api/galleries/random")
async def random_gallery(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        gallery_id = await GalleryRepository(session).random_id()
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if gallery_id is None:
        raise HTTPException(status_code=404, detail="No galleries available")
    return {"id": gallery_id}


gallery_random = random_gallery


@router.get("/api/galleries/{identifier}/next")
async def gallery_next(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        next_id = await GalleryRepository(session).next_gallery_id(identifier)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if next_id is None:
        raise HTTPException(status_code=404, detail="No next gallery")
    return {"id": next_id}


@router.get("/api/galleries/{identifier}")
async def get_gallery(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    tags = await _gallery_tags(row.id, session=session)
    settings = get_current_settings()
    source_meta = getattr(row, "source_meta", None) or {}
    spider_keys = (
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
    return {
        "id": row.id,
        "gid": row.gid,
        "token": getattr(row, "token", None),
        "title": display_title(row),
        "title_english": getattr(row, "title", None),
        "title_jpn": getattr(row, "title_jpn", None),
        "storage_type": getattr(row, "storage_type", "ehviewer_dir"),
        "category": getattr(row, "category", "other") or "other",
        "page_count": len(pages),
        "file_size": getattr(row, "file_size", None),
        "storage_size": getattr(row, "storage_size", 0),
        "uploader": getattr(row, "uploader", None),
        "posted_at": row.posted_at.isoformat() if getattr(row, "posted_at", None) else None,
        "rating": getattr(row, "rating", None),
        "favorite": getattr(row, "favorite", False),
        "favorite_category": getattr(row, "favorite_category", None),
        "reading_progress": getattr(row, "reading_progress", None),
        "expunged": getattr(row, "expunged", False),
        "image_quality": getattr(row, "image_quality", None),
        "local_rating": getattr(row, "local_rating", None),
        "local_note": getattr(row, "local_note", None),
        "storage_path": getattr(row, "storage_path", ""),
        "eh_url": (
            f"{settings.exhentai_base_url.rstrip('/')}/g/{row.gid}/{row.token}/"
            if row.gid and row.token
            else ""
        ),
        "exhentai_url": (
            f"{settings.exhentai_base_url.rstrip('/')}/g/{row.gid}/{row.token}/"
            if row.gid and row.token
            else None
        ),
        "warnings": source_meta.get("warnings", []),
        "spider_info": {key: source_meta[key] for key in spider_keys if key in source_meta},
        "source_meta": source_meta,
        "tags": [
            {
                "namespace": ns,
                "name": name,
                "display": translated_tag(ns, name)[1],
            }
            for ns, name in tags
        ],
        "tags_synced_at": getattr(row, "tags_synced_at", None),
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


gallery_detail = get_gallery


@router.patch("/api/galleries/{identifier}/local")
async def patch_gallery_local(
    identifier: int,
    body: GalleryLocalRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, _ = await _invoke_gallery(identifier, session=session)
    if body.local_rating is not None and not (1 <= body.local_rating <= 5):
        raise HTTPException(status_code=422, detail="local_rating must be 1-5")
    try:
        async with safe_transaction(session):
            gallery = await session.get(Gallery, row.id)
            if gallery is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            if "local_rating" in body.model_fields_set:
                gallery.local_rating = body.local_rating
            if "local_note" in body.model_fields_set:
                gallery.local_note = body.local_note
            if body.local_tags is not None:
                await GalleryRepository(session).set_local_tags(gallery.id, body.local_tags)
            tags = await GalleryRepository(session).tags_for_galleries([gallery.id])
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    tm = get_task_manager()
    now = datetime.now(UTC).isoformat()
    tm.record_task("gallery-local", now, now, "success", reason=f"id {row.id}", done=1, total=1)
    spawn_task(tm.persist_history(), "persist task history")
    local_tags = [
        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
        for ns, name in tags.get(row.id, [])
        if ns == "local"
    ]
    return {
        "id": row.id,
        "local_rating": body.local_rating if "local_rating" in body.model_fields_set else row.local_rating,
        "local_note": body.local_note if "local_note" in body.model_fields_set else row.local_note,
        "local_tags": local_tags,
    }


@router.post("/api/galleries/{identifier}/download-original", status_code=202)
async def download_gallery_original(
    identifier: int,
    body: DownloadOriginalRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """Enqueue an original-quality download for a local gallery."""
    session = await resolve_session(session, fallback_dep=get_session)
    row, _ = await _invoke_gallery(identifier, session=session)
    if not row.gid or not row.token:
        raise HTTPException(status_code=422, detail="Gallery has no ExHentai gid/token")
    mode = "gallery_archive" if body.archive else "gallery"
    if not body.archive:
        client = get_eh_client()
        try:
            preview = await client.fetch_gallery(
                row.gid, row.token, max_pages=1, resolve_urls=True
            )
        except Exception as exc:
            logger.warning(
                "original availability check failed",
                extra=log_extra(gid=row.gid, error=type(exc).__name__),
            )
            raise HTTPException(
                status_code=502, detail="ExHentai metadata request failed"
            ) from exc
        if not preview.pages or not preview.pages[0].origin_url:
            raise HTTPException(
                status_code=422, detail="No original images available for this gallery"
            )
    try:
        async with safe_transaction(session):
            task = await DownloadRepository(session).create(
                row.gid,
                row.token,
                row.title,
                mode,
                None,
                "original",
                title_jpn=getattr(row, "title_jpn", None),
            )
            if task is None:
                raise HTTPException(
                    status_code=409, detail="An active download already exists for this gid"
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return {"id": task.id, "gid": task.gid, "status": "pending"}


@router.get("/api/galleries/{identifier}/favorite")
async def gallery_favorite_status(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        row, _ = await _invoke_gallery(identifier, session=session)
        fav_repo = FavoritesRepository(session)
        favcats = await fav_repo.favcats_for_gid(row.gid, gallery_id=row.id)
        names = await fav_repo.category_names(favcats)
        fav_item = await fav_repo.item_for_gid(row.gid) if row.gid else None
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "gid": row.gid,
        "token": row.token,
        "favorite": bool(favcats),
        "favcats": favcats,
        "favcat_names": [{"favcat": f, "name": names.get(f, "")} for f in favcats],
        "note": getattr(fav_item, "note", None) if fav_item else None,
    }


@router.post("/api/galleries/{identifier}/favorite")
async def toggle_gallery_favorite(
    identifier: int,
    favcat: int = 0,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    eh_client_mgr: EhClientManager = Depends(get_eh_client_manager),  # noqa: B008
) -> dict[str, object]:
    """Deprecated: prefer POST /api/favorites/add for single/batch adds.

    Kept for backward compat (single gallery toggle). Batch adds MUST use
    /api/favorites/add which batches via successful_gids and respects cloud
    success before writing favorite_items.
    """
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="favcat must be between 0 and 9")
    session = await resolve_session(session, fallback_dep=get_session)
    row, _ = await _invoke_gallery(identifier, session=session)
    if not row.gid:
        raise HTTPException(
            status_code=400, detail="Gallery lacks gid for ExHentai favorites"
        )
    try:
        favcats = await FavoritesRepository(session).favcats_for_gid(
            row.gid, gallery_id=row.id
        )
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    target_state = not bool(favcats)
    settings = get_current_settings()

    if target_state:
        if not row.token:
            raise HTTPException(
                status_code=400, detail="Gallery lacks token for ExHentai favorites"
            )
        try:
            async with eh_client_mgr.client_context(settings=settings) as client:
                await client.add_favorite(row.gid, row.token, favcat)
        except Exception as exc:
            logger.warning(
                "ExHentai cloud favorite sync failed",
                extra=log_extra(gid=row.gid, error=type(exc).__name__),
            )
            raise HTTPException(
                status_code=502, detail="ExHentai cloud favorite sync failed"
            ) from exc

        base_url = str(
            getattr(settings, "exhentai_base_url", "https://exhentai.org")
            or "https://exhentai.org"
        ).rstrip("/")
        fav_item = FavoriteData(
            gid=row.gid,
            token=row.token,
            title=row.title or str(row.gid),
            url=f"{base_url}/g/{row.gid}/{row.token}/",
            thumb=None,
        )
        try:
            async with safe_transaction(session):
                await FavoritesRepository(session).remember(favcat, fav_item)
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc
    else:
        try:
            async with eh_client_mgr.client_context(settings=settings) as client:
                failed = await client.remove_favorites([row.gid])
            if failed:
                raise HTTPException(
                    status_code=502, detail="ExHentai cloud favorite remove failed"
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "ExHentai cloud favorite remove failed",
                extra=log_extra(gid=row.gid, error=type(exc).__name__),
            )
            raise HTTPException(
                status_code=502, detail="ExHentai cloud favorite remove failed"
            ) from exc

        try:
            async with safe_transaction(session):
                await FavoritesRepository(session).remove_gids([row.gid])
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc

    return {"favorite": target_state, "favorite_category": favcat if target_state else None}


@router.get("/api/galleries/{identifier}/progress")
async def gallery_progress(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    progress = await GalleryRepository(session).progress(row.id)
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else 0,
        "total_pages": progress.total_pages if progress else len(pages),
        "updated_at": progress.updated_at if progress else None,
    }


@router.put("/api/galleries/{identifier}/progress")
@router.post("/api/galleries/{identifier}/progress")
async def save_gallery_progress(
    identifier: int,
    body: ProgressRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    current = body.current_page if body.current_page is not None else (body.page or 0)
    total_pages = body.total_pages or len(pages)
    if current < 0 or (current > len(pages) and len(pages) > 0):
        raise HTTPException(status_code=422, detail="current_page is outside gallery")
    async with safe_transaction(session):
        progress = await GalleryRepository(session).upsert_progress(
            row.id, current, total_pages
        )
        await GalleryRepository(session).record_history(
            row.id, current, total_pages
        )
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else current,
        "total_pages": progress.total_pages if progress else total_pages,
        "reading_progress": current,
    }


@router.post("/api/galleries/{identifier}/read")
async def mark_gallery_read(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    async with safe_transaction(session):
        await GalleryRepository(session).upsert_progress(
            row.id, max(len(pages) - 1, 0), len(pages)
        )
    return {"reading_progress": len(pages)}


@router.get("/api/history")
async def history(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    session = await resolve_session(session, fallback_dep=get_session)
    repo = GalleryRepository(session)
    total, rows = await repo.history_page(page, page_size)
    galleries = {}
    if rows:
        g_ids = list({x.gallery_id for x in rows})
        found_galleries = await repo.find_by_ids(g_ids)
        galleries = {g.id: g for g in found_galleries}
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "gallery_id": x.gallery_id,
                "current_page": x.current_page,
                "total_pages": x.total_pages,
                "last_read_at": x.last_read_at,
                "title": (
                    display_title(galleries[x.gallery_id])
                    if x.gallery_id in galleries
                    else None
                ),
                "display_title": (
                    display_title(galleries[x.gallery_id])
                    if x.gallery_id in galleries
                    else None
                ),
                "raw_title": (
                    galleries[x.gallery_id].title if x.gallery_id in galleries else None
                ),
                "title_jpn": (
                    galleries[x.gallery_id].title_jpn if x.gallery_id in galleries else None
                ),
                "gid": galleries[x.gallery_id].gid if x.gallery_id in galleries else None,
                "category": (
                    galleries[x.gallery_id].category if x.gallery_id in galleries else None
                ),
                "url": f"/galleries/{x.gallery_id}",
            }
            for x in rows
        ],
    }


@router.delete("/api/history", status_code=204)
async def clear_history(
    confirm: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm=true is required to clear all history",
        )
    session = await resolve_session(session, fallback_dep=get_session)
    async with safe_transaction(session):
        await GalleryRepository(session).clear_history()


@router.delete("/api/galleries/progress", status_code=204)
async def clear_all_gallery_progress(
    confirm: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm=true is required to clear all progress",
        )
    session = await resolve_session(session, fallback_dep=get_session)
    async with safe_transaction(session):
        await GalleryRepository(session).clear_progress()


@router.delete("/api/galleries/{identifier}/progress", status_code=204)
async def clear_gallery_progress(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    session = await resolve_session(session, fallback_dep=get_session)
    row, _ = await _invoke_gallery(identifier, session=session)
    async with safe_transaction(session):
        await GalleryRepository(session).delete_progress(row.id)


@router.post("/api/galleries/{identifier}/redownload", status_code=202)
async def redownload_gallery(
    identifier: int,
    quality: str | None = None,
    archive: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if quality is not None and quality not in {"original", "resample"}:
        raise HTTPException(status_code=422, detail="quality must be 'original' or 'resample'")
    row, _ = await _invoke_gallery(identifier, session=session)
    if not row.gid or not row.token:
        raise HTTPException(status_code=422, detail="Gallery lacks ExHentai gid/token")
    if not quality:
        quality = (
            row.image_quality
            if getattr(row, "image_quality", None) in _IMAGE_QUALITY
            else (get_current_settings().download_quality or "resample")
        )
    mode = "gallery_archive" if archive else "gallery"
    try:
        async with safe_transaction(session):
            task = await DownloadRepository(session).create(
                row.gid,
                row.token,
                row.title or str(row.gid),
                mode,
                quality=quality,
                title_jpn=getattr(row, "title_jpn", None),
            )
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if task is None:
        raise HTTPException(status_code=409, detail="An active download already exists for this gid")
    return {"status": "pending", "task_id": task.id, "gid": row.gid}


@router.delete("/api/galleries/{identifier}", status_code=204)
async def delete_gallery(
    identifier: int,
    delete_files: bool = False,
    delete_all_copies: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> None:
    session = await resolve_session(session, fallback_dep=get_session)
    results: list[dict] = []
    try:
        target_id: int | None = None
        repo = GalleryRepository(session)
        row = await repo.get_by_id(identifier)
        if row is None:
            row = await repo.get_by_gid(identifier)
        if row is not None:
            target_id = row.id

        if target_id is None:
            raise HTTPException(status_code=404, detail="Gallery not found")

        results = await delete_galleries_local(
            [target_id], delete_files=delete_files, delete_all_copies=delete_all_copies
        )
        _record_gallery_delete_log(results, delete_files)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    if results and results[0].get("failed_paths"):
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to delete some gallery files",
                "failed_paths": results[0]["failed_paths"],
                "deleted_paths": results[0].get("deleted_paths", []),
            },
        )


@router.post("/api/galleries/delete-bulk", status_code=200)
async def delete_galleries_bulk(
    body: BulkDeleteRequest,
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    results: list[dict] = []
    try:
        unique_ids = list(dict.fromkeys(ids))
        for chunk in _chunked(unique_ids):
            batch_results = await delete_galleries_local(
                chunk,
                delete_files=body.delete_files,
                delete_all_copies=body.delete_all_copies,
            )
            results.extend(batch_results)
        _record_gallery_delete_log(results, body.delete_files)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {"deleted": deleted, "trashed": trashed, "failed_deletions": failed_deletions, "results": results}


@router.post("/api/galleries/delete-filtered", status_code=200)
async def delete_galleries_filtered(
    body: FilteredDeleteRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    gallery_service: GalleryService = Depends(get_gallery_service),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if body.tag_mode not in {"and", "or"} or body.tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    category = body.category or None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    if body.read_status and body.read_status not in {"all", "unread", "reading", "completed", "read"}:
        raise HTTPException(status_code=422, detail="invalid read_status")
    parsed_tags, parsed_exc_tags = _parse_tag_filter(body.tags or body.tag)
    if body.exclude_tags:
        extra_inc, extra_exc = _parse_tag_filter(body.exclude_tags)
        parsed_exc_tags.extend(extra_inc)
        parsed_exc_tags.extend(extra_exc)
    _MAX_FILTERED_DELETE = 5000
    try:
        resolved_q = body.q or ""
        order_by = body.order_by or "id_desc"
        read_status = body.read_status
        min_rating = body.min_rating
        page_min = body.min_pages
        page_max = body.max_pages
        if body.q and body.q.strip():
            auto_inc, auto_exc, keywords, changed = await _resolve_search_tokens(body.q)
            if changed:
                parsed_tags.extend(auto_inc)
                parsed_exc_tags.extend(auto_exc)
                parsed_tags = _dedupe_tags(parsed_tags)
                parsed_exc_tags = _dedupe_tags(parsed_exc_tags)
                resolved_q = keywords
        parsed_tags = _dedupe_tags(parsed_tags)
        parsed_exc_tags = _dedupe_tags(parsed_exc_tags)
        has_filters = any(
            (
                bool(resolved_q and resolved_q.strip()),
                bool(parsed_tags),
                bool(parsed_exc_tags),
                bool(category),
                exclude_favorited,
                bool(read_status and read_status != "all"),
                min_rating is not None,
                page_min is not None,
                page_max is not None,
                body.size_min is not None,
                body.size_max is not None,
                bool(body.posted_from or body.min_posted_at),
                bool(body.posted_to or body.max_posted_at),
                bool(body.uploader and body.uploader.strip()),
                bool(body.image_quality and body.image_quality in _IMAGE_QUALITY),
                body.min_local_rating is not None,
                body.list_id is not None,
                body.favorite is not None,
                body.read is not None,
                body.expunged is not None,
                bool(body.media_type),
                bool(body.storage_type),
            )
        )
        if not has_filters:
            raise HTTPException(
                status_code=400,
                detail="Empty filter condition is not allowed for filtered deletion",
            )
        matching_ids: list[int] = []
        repo = GalleryRepository(session)
        tag_id_map: dict[tuple[str | None, str], int] = {}
        if body.tag_match == "exact":
            candidates = parsed_tags + parsed_exc_tags
            if candidates and hasattr(repo, "resolve_exact_tags"):
                tag_id_map = await repo.resolve_exact_tags(candidates)
        page = 1
        while True:
            _, rows = await repo.list_page(
                page,
                500,
                q=resolved_q,
                tags=parsed_tags,
                exclude_tags=parsed_exc_tags,
                tag_mode=body.tag_mode,
                tag_match=body.tag_match,
                tag_id_map=tag_id_map,
                category=category,
                exclude_favorited=exclude_favorited,
                order_by=order_by,
                read_status=read_status,
                 min_rating=min_rating,
                 page_min=page_min,
                 page_max=page_max,
                 size_min=body.size_min,
                 size_max=body.size_max,
                 posted_from=_parse_posted(body.posted_from or body.min_posted_at),
                 posted_to=_parse_posted(body.posted_to or body.max_posted_at),
                 uploader=body.uploader,
                 image_quality=(
                     body.image_quality
                     if body.image_quality in _IMAGE_QUALITY
                     else None
                 ),
                 min_local_rating=body.min_local_rating,
                 list_id=body.list_id,
             )
            if not rows:
                break
            matching_ids.extend(r.id for r in rows)
            if len(matching_ids) > _MAX_FILTERED_DELETE:
                raise HTTPException(
                    status_code=409,
                    detail=f"matched {len(matching_ids)} galleries exceeds safe limit {_MAX_FILTERED_DELETE}; refine filter or delete in batches",
                )
            if len(rows) < 500:
                break
            page += 1

        results: list[dict] = []
        if matching_ids:
            for chunk in _chunked(list(dict.fromkeys(matching_ids))):
                res = await delete_galleries_local(
                    chunk, delete_files=body.delete_files, delete_all_copies=body.delete_all_copies
                )
                results.extend(res)
        _record_gallery_delete_log(results, body.delete_files)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {"deleted": deleted, "trashed": trashed, "matched": len(matching_ids), "failed_deletions": failed_deletions, "results": results}


def _record_gallery_delete_log(results: list[dict[str, object]], delete_files: bool) -> None:
    now = datetime.now(UTC).isoformat()
    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed = [p for r in results for p in r.get("failed_paths", [])]
    status = "failed" if failed else "success"
    mode_text = "database record + files" if delete_files else "database record only"
    if trashed:
        mode_text += f", trashed {trashed}"
    reason = f"deleted {deleted}/{len(results)} galleries ({mode_text})"
    if failed:
        reason += f", file deletion failed: {', '.join(str(p) for p in failed[:3])}"
    tm = get_task_manager()
    tm.record_task("gallery-delete", now, now, status, reason=reason, done=deleted, total=len(results))
    spawn_task(tm.persist_history(), "persist task history")


@router.post("/api/galleries/{identifier}/sync-tags")
async def sync_gallery_tags(
    identifier: int,
    redirect: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    from fastapi.responses import RedirectResponse

    session = await resolve_session(session, fallback_dep=get_session)
    plan: dict[str, object] | None = None
    result: object | None = None
    count = 0
    synced_at = datetime.now(UTC)
    try:
        client = get_eh_client()
        service = TagSyncService(client, GalleryRepository(session))
        if callable(getattr(service, "fetch_plan", None)) and callable(
            getattr(service, "apply_plan", None)
        ):
            plan = await service.fetch_plan(identifier)
        else:
            async with safe_transaction(session):
                result = await service.sync(identifier)

        if plan is not None:
            async with safe_transaction(session):
                count = await TagSyncService(client, GalleryRepository(session)).apply_plan(
                    identifier, plan
                )
        elif result is None:
            raise HTTPException(status_code=404, detail="Gallery not found")
    except GalleryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (GalleryGidMissing, GalleryTokenMissing) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    except Exception as exc:
        logger.warning("tag sync failed", extra=log_extra(gallery_id=identifier, error=type(exc).__name__))
        raise HTTPException(status_code=502, detail="ExHentai metadata request failed") from exc
    if redirect:
        return RedirectResponse(f"/galleries/{identifier}", status_code=303)
    if result is not None:
        return {
            "id": identifier,
            "gid": getattr(result, "gid", None),
            "title": getattr(result, "title", None),
            "count": getattr(result, "count", getattr(result, "tags_added", 0)),
            "tags_added": getattr(result, "tags_added", getattr(result, "count", 0)),
            "synced_at": getattr(result, "synced_at", None),
            "source": getattr(result, "source", None),
        }
    return {
        "id": identifier,
        "gid": plan.get("gid") if plan else None,
        "title": plan.get("title") if plan else None,
        "count": count,
        "tags_added": count,
        "synced_at": synced_at,
        "source": plan.get("source") if plan else None,
    }


def _unlink_export(path: str) -> None:
    Path(path).unlink(missing_ok=True)


@router.get("/api/galleries/{identifier}/export.cbz")
async def export_gallery_cbz(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> FileResponse:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    path = Path(row.storage_path or "")
    now = datetime.now(UTC).isoformat()
    filename = cbz_filename(getattr(row, "title", None), getattr(row, "gid", None), row.id)
    total = len(pages)

    def _log(status: str, reason: str, done: int = 0) -> None:
        tm = get_task_manager()
        tm.record_task(
            "export-cbz",
            now,
            datetime.now(UTC).isoformat(),
            status,
            reason=reason,
            done=done,
            total=total,
        )
        spawn_task(tm.persist_history(), "persist task history")

    if not path.exists():
        _log("failed", "missing files")
        raise HTTPException(status_code=404, detail="Gallery files not found")
    if is_cbz_file(path):
        _log("success", path.name, total)
        return FileResponse(path, filename=filename, media_type="application/zip")
    if not path.is_dir() or not pages:
        _log("failed", "not exportable")
        raise HTTPException(status_code=404, detail="Gallery files not found")
    settings = get_current_settings()
    export_dir = Path(settings.download_root) / ".exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".cbz", dir=export_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        page_pairs = [(p.page_index, p.member_name or "") for p in pages]
        await run_in_threadpool(pack_directory_cbz, path, page_pairs, tmp_path)
    except UnsafeExportPath as exc:
        tmp_path.unlink(missing_ok=True)
        _log("failed", "path escape")
        raise HTTPException(
            status_code=400, detail="Page path escapes gallery directory"
        ) from exc
    except FileNotFoundError as exc:
        tmp_path.unlink(missing_ok=True)
        _log("failed", "missing page")
        raise HTTPException(status_code=404, detail="Page file not found") from exc
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    _log("success", filename, total)
    return FileResponse(
        tmp_path,
        filename=filename,
        media_type="application/zip",
        background=BackgroundTask(_unlink_export, str(tmp_path)),
    )


@router.get("/api/galleries/{identifier}/pages/{page_index}")
async def get_page(
    identifier: int,
    page_index: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> StreamingResponse:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    if not 0 <= page_index < len(pages):
        raise HTTPException(status_code=404, detail="Page not found")
    page = pages[page_index]
    scanner = registry.for_path(Path(row.storage_path or ""))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery storage")
    stream = await run_in_threadpool(
        scanner.open_page,
        _meta(row, pages),
        PageInfo(page.page_index, page.member_name or "", page.media_type or "jpg"),
    )
    return StreamingResponse(
        _closing_stream(stream),
        media_type=_page_media_type(page.media_type or "jpg"),
    )


def _skip_stream_bytes(stream: BinaryIO, num_bytes: int) -> bool:
    if num_bytes <= 0:
        return True
    try:
        stream.seek(num_bytes, 1)
        return True
    except (OSError, AttributeError, io.UnsupportedOperation):
        remaining = num_bytes
        while remaining > 0:
            chunk = stream.read(min(remaining, 65536))
            if not chunk:
                return False
            remaining -= len(chunk)
        return True


def _fast_parse_webp_duration(stream: BinaryIO) -> int | None:
    header = stream.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None

    total_duration = 0
    anmf_count = 0

    while True:
        chunk_header = stream.read(8)
        if len(chunk_header) < 8:
            break
        fourcc = chunk_header[:4]
        chunk_size = int.from_bytes(chunk_header[4:8], "little")
        padding = chunk_size % 2

        if fourcc == b"ANMF":
            if chunk_size < 16:
                return None
            payload_head = stream.read(16)
            if len(payload_head) < 16:
                return None
            dur = int.from_bytes(payload_head[12:15], "little")
            if dur <= 0:
                dur = 100
            total_duration += dur
            anmf_count += 1
            skip = (chunk_size - 16) + padding
        else:
            skip = chunk_size + padding

        if not _skip_stream_bytes(stream, skip):
            break

    if anmf_count > 0:
        return total_duration
    return None


def _inspect_image_meta(stream: BinaryIO) -> dict[str, Any]:
    try:
        start_pos = 0
        try:
            start_pos = stream.tell()
        except (OSError, AttributeError, io.UnsupportedOperation):
            start_pos = 0

        try:
            fast_duration = _fast_parse_webp_duration(stream)
            if fast_duration is not None:
                return {"animated": True, "duration_ms": fast_duration}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fast WebP parsing failed, fallback to Pillow: %s", exc)

        try:
            stream.seek(start_pos)
        except (OSError, AttributeError, io.UnsupportedOperation):
            try:
                stream.seek(0)
            except (OSError, AttributeError, io.UnsupportedOperation):
                pass

        with Image.open(stream) as img:
            is_animated = bool(getattr(img, "is_animated", False))
            if not is_animated:
                return {"animated": False, "duration_ms": 0}
            is_webp = getattr(img, "format", "") == "WEBP"
            total_duration = 0
            for frame in ImageSequence.Iterator(img):
                if is_webp:
                    frame.load()
                dur = frame.info.get("duration", 100)
                if not isinstance(dur, (int, float)) or dur <= 0:
                    dur = 100
                total_duration += int(dur)
            return {"animated": True, "duration_ms": total_duration}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to inspect image meta: %s", exc)
        return {"animated": False, "duration_ms": 0}
    finally:
        try:
            stream.close()
        except OSError:
            pass


@router.get("/api/galleries/{identifier}/pages/{page_index}/meta")
async def get_page_meta(
    identifier: int,
    page_index: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _invoke_gallery(identifier, session=session)
    if not 0 <= page_index < len(pages):
        raise HTTPException(status_code=404, detail="Page not found")
    page = pages[page_index]
    scanner = registry.for_path(Path(row.storage_path or ""))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery storage")
    try:
        stream = await run_in_threadpool(
            scanner.open_page,
            _meta(row, pages),
            PageInfo(page.page_index, page.member_name or "", page.media_type or "jpg"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to open page for meta: %s", exc)
        return {"animated": False, "duration_ms": 0}

    return await run_in_threadpool(_inspect_image_meta, stream)


def _thumb_file_response(
    file_path: Path,
    media_type: str,
    cache_control: str,
    gallery_id: int,
    page_index: int,
    request: Request | None,
) -> Response:
    try:
        stat = file_path.stat()
        etag = f'"{gallery_id}-{page_index}-{int(stat.st_mtime)}-{stat.st_size}"'
    except OSError:
        etag = None

    headers: dict[str, str] = {"Cache-Control": cache_control}
    if etag:
        headers["ETag"] = etag
        if request is not None:
            if_none_match = request.headers.get("if-none-match")
            if if_none_match:
                tokens = [t.strip() for t in if_none_match.split(",")]
                if "*" in tokens or etag in tokens or f"W/{etag}" in tokens:
                    return Response(status_code=304, headers=headers)

    return FileResponse(file_path, media_type=media_type, headers=headers)


@router.get("/api/galleries/{identifier}/thumb/{page_index}")
async def get_thumbnail(
    identifier: int,
    page_index: int,
    request: Request = None,  # type: ignore[assignment]
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    if page_index < 0:
        raise HTTPException(status_code=404, detail="Page not found")

    pages: list[GalleryPage] | None = None
    row: Gallery | None = None

    if _gallery is not _default_gallery:
        try:
            resolved_session = await resolve_session(session, fallback_dep=get_session)
        except HTTPException:
            resolved_session = None
        row, pages = await _invoke_gallery(identifier, session=resolved_session)
    else:
        session = await resolve_session(session, fallback_dep=get_session)
        repo = GalleryRepository(session)
        row = await repo.get_by_identifier(identifier)

    if row is None:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if row.page_count is not None and row.page_count > 0 and page_index >= row.page_count:
        raise HTTPException(status_code=404, detail="Page allowance exceeded" if False else "Page not found")

    service = _get_thumb_service()

    is_fallback = False
    if page_index == 0 and row.gid:
        remote_cover = service.cached_remote_cover(row.gid)
        if remote_cover is not None:
            head = await run_in_threadpool(lambda: remote_cover.read_bytes()[:16])
            media_type = image_content_type(head)
            if media_type == "application/octet-stream":
                media_type = JPEG_MIME
            return _thumb_file_response(
                remote_cover,
                media_type=media_type,
                cache_control="public, max-age=86400",
                gallery_id=row.id,
                page_index=page_index,
                request=request,
            )
        spawn_task(
            ensure_remote_cover(row.gid, row.token, cache_dir=service.remote_cover_dir()),
            f"remote cover {row.gid}",
        )
        logger.info(
            "cover fallback: gid=%s source=thumb0 event=fallback",
            row.gid,
            extra=log_extra(gid=row.gid, source="thumb0", event="fallback"),
        )
        is_fallback = True

    cache_control = (
        "no-cache"
        if is_fallback
        else ("public, max-age=31536000, immutable" if page_index > 0 else "public, max-age=86400")
    )

    cached = service.cached(row.id, page_index)
    if cached is not None:
        return _thumb_file_response(
            cached,
            media_type=JPEG_MIME,
            cache_control=cache_control,
            gallery_id=row.id,
            page_index=page_index,
            request=request,
        )

    if pages is None:
        repo = GalleryRepository(session)
        pages = list(await repo.get_pages(row.id))

    if not 0 <= page_index < len(pages):
        raise HTTPException(status_code=404, detail="Page not found")
    page = pages[page_index]

    scanner = registry.for_path(Path(row.storage_path or ""))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery storage")
    stream = await run_in_threadpool(
        scanner.open_page,
        _meta(row, pages),
        PageInfo(page.page_index, page.member_name or "", page.media_type or "jpg"),
    )
    try:
        data = await run_in_threadpool(stream.read)
    finally:
        try:
            stream.close()
        except OSError:
            pass
    try:
        cached = await run_in_threadpool(
            service.get_or_create, row.id, page.page_index, data
        )
    except ThumbnailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _thumb_file_response(
        cached,
        media_type=JPEG_MIME,
        cache_control=cache_control,
        gallery_id=row.id,
        page_index=page_index,
        request=request,
    )


gallery_page = get_page
gallery_page_meta = get_page_meta
gallery_thumbnail = get_thumbnail
