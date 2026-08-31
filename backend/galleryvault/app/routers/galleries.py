"""Gallery endpoints."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from ...db.models import Gallery, GalleryPage, GalleryTag, Tag
from ...db.repository import DownloadRepository, GalleryRepository
from ...logging import log_extra
from ...scanners import registry
from ...scanners.base import CATEGORIES, GalleryMeta, PageInfo
from ...services.deletion import delete_galleries_local
from ...services.tag_sync import (
    GalleryGidMissing,
    GalleryNotFound,
    GalleryTokenMissing,
    TagSyncService,
)
from ...services.tag_translation import translated_tag
from ...services.thumbnails import JPEG_MIME, ThumbnailError, ThumbnailService
from ..dependencies import (
    db_error,
    display_title,
    get_current_settings,
    get_eh_client,
    get_session,
    get_task_manager,
    spawn_task,
)
from ..schemas import (
    BulkDeleteRequest,
    DownloadOriginalRequest,
    FilteredDeleteRequest,
    ProgressRequest,
)
from ..state import app_state

logger = logging.getLogger(__name__)
router = APIRouter()

_PAGE_STREAM_CHUNK = 256 * 1024


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


async def _gallery_lookup(identifier: int) -> tuple[Gallery, list[GalleryPage]]:
    try:
        async for session in get_session():
            row = await session.scalar(select(Gallery).where(Gallery.id == identifier))
            if row is None:
                row = await session.scalar(select(Gallery).where(Gallery.gid == identifier))
            if row is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            pages = (
                await session.scalars(
                    select(GalleryPage)
                    .where(GalleryPage.gallery_id == row.id)
                    .order_by(GalleryPage.page_index)
                )
            ).all()
            return row, list(pages)
        raise HTTPException(status_code=503, detail="Database is unavailable")
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


async def _gallery_tags_lookup(gallery_id: int) -> list[tuple[str, str]]:
    try:
        async for session in get_session():
            rows = await session.execute(
                select(Tag.namespace, Tag.name)
                .join(GalleryTag, GalleryTag.tag_id == Tag.id)
                .where(GalleryTag.gallery_id == gallery_id)
                .order_by(Tag.namespace, Tag.name)
            )
            return [(namespace, name) for namespace, name in rows]
        return []
    except Exception as exc:
        raise db_error(exc) from exc


async def _gallery(identifier: int) -> tuple[Gallery, list[GalleryPage]]:
    from .. import main
    fn = getattr(main, "_gallery", _gallery_lookup)
    return await fn(identifier)


async def _gallery_tags(gallery_id: int) -> list[tuple[str, str]]:
    from .. import main
    fn = getattr(main, "_gallery_tags", _gallery_tags_lookup)
    return await fn(gallery_id)


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


def _parse_tag_filter(tags: str | None) -> list[tuple[str | None, str]]:
    parsed_tags: list[tuple[str | None, str]] = []
    for value in (tags or "").split(","):
        value = value.strip()
        if not value:
            continue
        if ":" in value:
            namespace, name = value.split(":", 1)
            namespace = namespace.strip() or None
        else:
            namespace, name = None, value
        if not name.strip() or len(name) > 200 or (namespace and len(namespace) > 32):
            raise HTTPException(status_code=422, detail="invalid tag")
        parsed_tags.append((namespace, name.strip()))
    return parsed_tags


async def _resolve_search_tokens(
    q: str,
) -> tuple[list[tuple[str | None, str]], str, bool]:
    tokens = q.split()
    if not tokens:
        return [], "", False
    explicit: list[tuple[str | None, str]] = []
    keywords: list[str] = []
    for token in tokens:
        if ":" in token:
            namespace, name = token.split(":", 1)
            namespace = namespace.strip() or None
            name = name.strip()
            if name:
                explicit.append((namespace, name))
            else:
                keywords.append(token)
        else:
            keywords.append(token)
    return explicit, " ".join(keywords), False


@router.get("/api/galleries")
async def list_galleries(
    page: int = 1,
    page_size: int = 24,
    order: str = "id_desc",
    category: str | None = None,
    q: str | None = None,
    tags: str | None = None,
    uploader: str | None = None,
    min_rating: float | None = None,
    favorite: bool | None = None,
    read: bool | None = None,
    expunged: bool | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
    media_type: str | None = None,
    storage_type: str | None = None,
    min_posted_at: str | None = None,
    max_posted_at: str | None = None,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="page_size must be between 1 and 500")

    category_filter = category
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category_filter = None
    elif category and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {', '.join(CATEGORIES)}")

    parsed_tags = _parse_tag_filter(tags)
    search_keywords = q or None
    query_modified = False
    if q and q.strip():
        inferred_tags, remaining_keywords, query_modified = await _resolve_search_tokens(q)
        if inferred_tags:
            parsed_tags = _dedupe_tags(parsed_tags + inferred_tags)
        search_keywords = remaining_keywords or None
    try:
        async for session in get_session():
            from .. import main
            repo_cls = getattr(main, "GalleryRepository", GalleryRepository)
            total, rows = await repo_cls(session).list_page(
                page,
                page_size,
                q=search_keywords,
                tags=parsed_tags if parsed_tags else (),
                category=category_filter,
                exclude_favorited=exclude_favorited,
            )
            tag_map = await repo_cls(session).tags_for_galleries([r.id for r in rows if getattr(r, "id", None)])
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "category": category,
        "query_tags": (
            [
                {
                    "namespace": ns,
                    "name": name,
                    "display": translated_tag(ns or "misc", name)[1],
                }
                for ns, name in parsed_tags
            ]
            if query_modified
            else []
        ),
        "items": [
            {
                "id": row.id,
                "gid": getattr(row, "gid", None),
                "token": getattr(row, "token", None),
                "title": display_title(row),
                "title_jpn": getattr(row, "title_jpn", None),
                "category": getattr(row, "category", "other"),
                "uploader": getattr(row, "uploader", None),
                "posted_at": row.posted_at.isoformat() if getattr(row, "posted_at", None) else None,
                "page_count": getattr(row, "page_count", 0),
                "storage_size": getattr(row, "storage_size", 0),
                "rating": getattr(row, "rating", None),
                "favorite": getattr(row, "favorite", False),
                "favorite_category": getattr(row, "favorite_category", None),
                "reading_progress": getattr(row, "reading_progress", None),
                "expunged": getattr(row, "expunged", False),
                "cover_url": f"/api/galleries/{row.id}/thumb/0",
                "image_quality": getattr(row, "image_quality", None),
                "storage_type": getattr(row, "storage_type", "ehviewer_dir"),
                "tags": [
                    {
                        "namespace": ns,
                        "name": name,
                        "display": translated_tag(ns, name)[1],
                    }
                    for ns, name in tag_map.get(row.id, [])
                ],
            }
            for row in rows
        ],
    }


gallery_list = list_galleries


@router.get("/api/galleries/categories")
async def list_categories() -> dict[str, object]:
    try:
        async for session in get_session():
            counts = await GalleryRepository(session).category_counts()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "categories": [
            {"name": cat, "count": counts.get(cat, 0)}
            for cat in CATEGORIES
        ]
    }


@router.get("/api/galleries/random")
async def random_gallery() -> dict[str, object]:
    try:
        async for session in get_session():
            row = await GalleryRepository(session).random_gallery()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="No galleries found")
    return {"id": row.id}


@router.get("/api/galleries/{identifier}")
async def get_gallery(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    tags = await _gallery_tags(row.id)
    settings = get_current_settings()
    return {
        "id": row.id,
        "gid": row.gid,
        "token": row.token,
        "title": display_title(row),
        "title_jpn": getattr(row, "title_jpn", None),
        "category": getattr(row, "category", "other"),
        "uploader": getattr(row, "uploader", None),
        "posted_at": row.posted_at.isoformat() if getattr(row, "posted_at", None) else None,
        "page_count": getattr(row, "page_count", len(pages)),
        "storage_size": getattr(row, "storage_size", 0),
        "rating": getattr(row, "rating", None),
        "favorite": getattr(row, "favorite", False),
        "favorite_category": getattr(row, "favorite_category", None),
        "reading_progress": getattr(row, "reading_progress", None),
        "expunged": getattr(row, "expunged", False),
        "image_quality": getattr(row, "image_quality", None),
        "storage_type": getattr(row, "storage_type", "ehviewer_dir"),
        "storage_path": getattr(row, "storage_path", ""),
        "exhentai_url": (
            f"{settings.exhentai_base_url.rstrip('/')}/g/{row.gid}/{row.token}/"
            if row.gid and row.token
            else None
        ),
        "tags": [
            {
                "namespace": ns,
                "name": name,
                "display": translated_tag(ns, name)[1],
            }
            for ns, name in tags
        ],
        "tags_synced_at": getattr(row, "tags_synced_at", None),
        "spider_info": getattr(row, "source_meta", None) or {},
        "source_meta": getattr(row, "source_meta", None) or {},
        "pages": [
            {
                "page_index": p.page_index,
                "media_type": p.media_type,
                "image_url": f"/api/galleries/{row.id}/pages/{p.page_index}",
                "thumb_url": f"/api/galleries/{row.id}/thumb/{p.page_index}",
            }
            for p in pages
        ],
    }


gallery_detail = get_gallery


@router.post("/api/galleries/{identifier}/download-original", status_code=202)
async def download_gallery_original(
    identifier: int, body: DownloadOriginalRequest
) -> dict[str, object]:
    """Enqueue an original-quality download for a local gallery."""
    row, _ = await _gallery(identifier)
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
        async for session in get_session():
            async with session.begin():
                task = await DownloadRepository(session).create(
                    row.gid, row.token, row.title, mode, None, "original"
                )
                if task is None:
                    raise HTTPException(
                        status_code=409, detail="An active download already exists for this gid"
                    )
            break
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return {"id": task.id, "gid": task.gid, "status": "pending"}


@router.post("/api/galleries/{identifier}/favorite")
async def toggle_gallery_favorite(
    identifier: int, favcat: int = 0
) -> dict[str, object]:
    row, _ = await _gallery(identifier)
    target_state = not row.favorite
    if row.gid and row.token:
        client = app_state.eh_client
        if client is not None:
            try:
                if target_state:
                    await client.add_favorite(row.gid, row.token, favcat)
                else:
                    await client.remove_favorite(row.gid)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ExHentai cloud favorite sync failed",
                    extra=log_extra(gid=row.gid, error=type(exc).__name__),
                )
    try:
        async for session in get_session():
            async with session.begin():
                await GalleryRepository(session).set_favorite(
                    row.id, target_state, favcat if target_state else None
                )
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"favorite": target_state, "favorite_category": favcat if target_state else None}


@router.post("/api/galleries/{identifier}/read")
async def mark_gallery_read(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    async for session in get_session():
        async with session.begin():
            await GalleryRepository(session).update_progress(row.id, len(pages))
        break
    return {"reading_progress": len(pages)}


@router.post("/api/galleries/{identifier}/progress")
async def save_gallery_progress(identifier: int, body: ProgressRequest) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    current = min(body.page, len(pages))
    async for session in get_session():
        async with session.begin():
            await GalleryRepository(session).update_progress(row.id, current)
        break
    return {"reading_progress": current}


@router.post("/api/galleries/{identifier}/redownload", status_code=202)
async def redownload_gallery(
    identifier: int, quality: str | None = None, archive: bool = False
) -> dict[str, object]:
    if quality is not None and quality not in {"original", "resample"}:
        raise HTTPException(status_code=422, detail="quality must be 'original' or 'resample'")
    row, _ = await _gallery(identifier)
    if not row.gid or not row.token:
        raise HTTPException(status_code=422, detail="Gallery lacks ExHentai gid/token")
    mode = "archive" if archive else "gallery"
    try:
        async for session in get_session():
            async with session.begin():
                task = await DownloadRepository(session).create(
                    row.gid, row.token, row.title or str(row.gid), mode, quality=quality
                )
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if task is None:
        raise HTTPException(status_code=409, detail="An active download already exists for this gid")
    return {"status": "pending", "task_id": task.id, "gid": row.gid}


@router.delete("/api/galleries/{identifier}", status_code=200)
async def delete_gallery(
    identifier: int, delete_files: bool = False, delete_all_copies: bool = False
) -> dict[str, object]:
    try:
        async for session in get_session():
            row = await session.get(Gallery, identifier)
            if row is None:
                row = await session.scalar(select(Gallery).where(Gallery.gid == identifier))
            if row is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            async with session.begin():
                results = await delete_galleries_local(
                    session, [row], delete_files=delete_files, delete_all_copies=delete_all_copies
                )
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    _record_gallery_delete_log(results, delete_files)
    return {"results": results}


@router.post("/api/galleries/delete-bulk", status_code=200)
async def delete_galleries_bulk(body: BulkDeleteRequest) -> dict[str, object]:
    if not body.gallery_ids:
        return {"results": []}
    try:
        async for session in get_session():
            async with session.begin():
                galleries = (
                    await session.scalars(
                        select(Gallery).where(Gallery.id.in_(body.gallery_ids))
                    )
                ).all()
                results = await delete_galleries_local(
                    session,
                    list(galleries),
                    delete_files=body.delete_files,
                    delete_all_copies=body.delete_all_copies,
                )
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    _record_gallery_delete_log(results, body.delete_files)
    return {"results": results}


@router.post("/api/galleries/delete-filtered", status_code=200)
async def delete_galleries_filtered(body: FilteredDeleteRequest) -> dict[str, object]:
    category_filter = body.category
    exclude_favorited = False
    if body.category == "__not_fav__":
        exclude_favorited = True
        category_filter = None

    all_results: list[dict[str, object]] = []
    page = 1
    page_size = 500
    matched = 0
    try:
        async for session in get_session():
            from .. import main
            delete_fn = getattr(main, "delete_galleries_local", delete_galleries_local)
            while True:
                total, batch = await GalleryRepository(session).list_page(
                    page,
                    page_size,
                    body.q or "",
                    body.tag or "",
                    getattr(body, "tag_mode", "or"),
                    getattr(body, "tag_match", "exact"),
                    category_filter,
                    exclude_favorited=exclude_favorited,
                )
                if page == 1:
                    matched = total
                if not batch:
                    break
                async with session.begin():
                    batch_results = await delete_fn(
                        session,
                        batch,
                        delete_files=body.delete_files,
                        delete_all_copies=body.delete_all_copies,
                    )
                all_results.extend(batch_results)
                if len(batch) < page_size:
                    break
                page += 1
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in all_results if r.get("db_removed"))
    _record_gallery_delete_log(all_results, body.delete_files)
    return {"matched": matched, "deleted": deleted, "results": all_results}


def _record_gallery_delete_log(results: list[dict[str, object]], delete_files: bool) -> None:
    now = datetime.now(UTC).isoformat()
    deleted = sum(1 for r in results if r.get("db_removed"))
    failed = [p for r in results for p in r.get("failed_paths", [])]
    status = "failed" if failed else "success"
    mode_text = "database record + files" if delete_files else "database record only"
    reason = f"deleted {deleted}/{len(results)} galleries ({mode_text})"
    if failed:
        reason += f", file deletion failed: {', '.join(str(p) for p in failed[:3])}"
    tm = get_task_manager()
    tm.record_task("gallery-delete", now, now, status, reason=reason, done=deleted, total=len(results))
    spawn_task(tm.persist_history(), "persist task history")


@router.post("/api/galleries/{identifier}/sync-tags")
async def sync_gallery_tags(identifier: int) -> dict[str, object]:
    from .. import main
    try:
        async for session in get_session():
            async with session.begin():
                service_cls = getattr(main, "TagSyncService", TagSyncService)
                client = get_eh_client()
                result = await service_cls(client, GalleryRepository(session)).sync(identifier)
            break
    except (GalleryNotFound, GalleryGidMissing, GalleryTokenMissing) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    except Exception as exc:
        logger.warning("tag sync failed", extra=log_extra(gallery_id=identifier, error=type(exc).__name__))
        raise HTTPException(status_code=502, detail="ExHentai upstream tag sync request failed") from exc
    return {
        "id": identifier,
        "gid": getattr(result, "gid", None),
        "title": getattr(result, "title", None),
        "count": getattr(result, "count", getattr(result, "tags_added", 0)),
        "tags_added": getattr(result, "tags_added", getattr(result, "count", 0)),
    }


@router.get("/api/galleries/{identifier}/pages/{page_index}")
async def get_page(identifier: int, page_index: int) -> StreamingResponse:
    row, pages = await _gallery(identifier)
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


@router.get("/api/galleries/{identifier}/thumb/{page_index}")
async def get_thumbnail(identifier: int, page_index: int) -> FileResponse:
    row, pages = await _gallery(identifier)
    if not 0 <= page_index < len(pages):
        raise HTTPException(status_code=404, detail="Page not found")
    page = pages[page_index]
    service = _get_thumb_service()
    cached = service.cached(row.id, page.page_index)
    if cached is None:
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
    return FileResponse(
        cached,
        media_type=JPEG_MIME,
        headers={"Cache-Control": "public, max-age=86400"},
    )
