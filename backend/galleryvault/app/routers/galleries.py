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
from ...db.repository import (
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    _chunked,
)
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
    return await _gallery_lookup(identifier)


async def _gallery_tags(gallery_id: int) -> list[tuple[str, str]]:
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
    return explicit, " ".join(keywords), bool(explicit)


@router.get("/api/galleries")
async def list_galleries(
    page: int = 1,
    page_size: int = 24,
    q: str | None = None,
    tags: str | None = None,
    tag_mode: str = "or",
    tag_match: str = "exact",
    category: str | None = None,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(
            status_code=422, detail="page must be >= 1 and page_size must be between 1 and 500"
        )
    if tag_mode not in {"and", "or"} or tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    if category == "":
        category = None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    elif category and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {', '.join(CATEGORIES)}")

    parsed_tags = _parse_tag_filter(tags)
    resolved_q = q or ""
    resolved = False
    if q and q.strip():
        auto_tags, keywords, changed = await _resolve_search_tokens(q)
        resolved = changed
        if changed:
            parsed_tags.extend(auto_tags)
            parsed_tags = _dedupe_tags(parsed_tags)
            resolved_q = keywords
    try:
        async for session in get_session():
            repo_cls = GalleryRepository
            total, rows = await repo_cls(session).list_page(
                page,
                page_size,
                q=resolved_q,
                tags=parsed_tags if parsed_tags else (),
                tag_mode=tag_mode,
                tag_match=tag_match,
                category=category,
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
        "q": resolved_q,
        "tags": ",".join(f"{namespace}:{name}" if namespace else name for namespace, name in parsed_tags),
        "resolved": resolved,
        "tag_mode": tag_mode,
        "tag_match": tag_match,
        "category": "__not_fav__" if exclude_favorited else (category or ""),
        "query_tags": (
            [
                {
                    "namespace": ns,
                    "name": name,
                    "display": translated_tag(ns or "misc", name)[1],
                }
                for ns, name in parsed_tags
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
                "reading_progress": getattr(row, "reading_progress", None),
                "expunged": getattr(row, "expunged", False),
                "image_quality": getattr(row, "image_quality", None),
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
            gallery_id = await GalleryRepository(session).random_id()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if gallery_id is None:
        raise HTTPException(status_code=404, detail="No galleries available")
    return {"id": gallery_id}


gallery_random = random_gallery


@router.get("/api/galleries/{identifier}/next")
async def gallery_next(identifier: int) -> dict[str, object]:
    try:
        async for session in get_session():
            next_id = await GalleryRepository(session).next_gallery_id(identifier)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if next_id is None:
        raise HTTPException(status_code=404, detail="No next gallery")
    return {"id": next_id}


@router.get("/api/galleries/{identifier}")
async def get_gallery(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    tags = await _gallery_tags(row.id)
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


@router.get("/api/galleries/{identifier}/favorite")
async def gallery_favorite_status(identifier: int) -> dict[str, object]:
    try:
        async for session in get_session():
            row, _ = await _gallery(identifier)
            favcats = await FavoritesRepository(session).favcats_for_gid(row.gid, gallery_id=row.id)
            names = await FavoritesRepository(session).category_names(favcats)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "gid": row.gid,
        "favorite": bool(favcats),
        "favcats": favcats,
        "favcat_names": [{"favcat": f, "name": names.get(f, "")} for f in favcats],
    }


@router.post("/api/galleries/{identifier}/favorite")
async def toggle_gallery_favorite(
    identifier: int, favcat: int = 0
) -> dict[str, object]:
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="favcat must be between 0 and 9")
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


@router.get("/api/galleries/{identifier}/progress")
async def gallery_progress(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    async for session in get_session():
        progress = await GalleryRepository(session).progress(row.id)
        break
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else 0,
        "total_pages": progress.total_pages if progress else len(pages),
        "updated_at": progress.updated_at if progress else None,
    }


@router.put("/api/galleries/{identifier}/progress")
@router.post("/api/galleries/{identifier}/progress")
async def save_gallery_progress(identifier: int, body: ProgressRequest) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    current = body.current_page if body.current_page is not None else (body.page or 0)
    total_pages = body.total_pages or len(pages)
    if current < 0 or (current > len(pages) and len(pages) > 0):
        raise HTTPException(status_code=422, detail="current_page is outside gallery")
    async for session in get_session():
        async with session.begin():
            progress = await GalleryRepository(session).upsert_progress(
                row.id, current, total_pages
            )
            await GalleryRepository(session).record_history(
                row.id, current, total_pages
            )
        break
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else current,
        "total_pages": progress.total_pages if progress else total_pages,
        "reading_progress": current,
    }


@router.post("/api/galleries/{identifier}/read")
async def mark_gallery_read(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    async for session in get_session():
        async with session.begin():
            await GalleryRepository(session).update_progress(row.id, len(pages))
        break
    return {"reading_progress": len(pages)}


@router.get("/api/history")
async def history(page: int = 1, page_size: int = 24) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    async for session in get_session():
        total, rows = await GalleryRepository(session).history_page(page, page_size)
        galleries = (
            {
                row.id: row
                for row in (
                    await session.scalars(
                        select(Gallery).where(Gallery.id.in_({x.gallery_id for x in rows}))
                    )
                ).all()
            }
            if rows
            else {}
        )
        break
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
                "title": galleries[x.gallery_id].title if x.gallery_id in galleries else None,
                "url": f"/galleries/{x.gallery_id}",
            }
            for x in rows
        ],
    }


@router.delete("/api/history", status_code=204)
async def clear_history() -> None:
    async for session in get_session():
        async with session.begin():
            await GalleryRepository(session).clear_history()
        break


@router.delete("/api/galleries/progress", status_code=204)
async def clear_all_gallery_progress() -> None:
    async for session in get_session():
        async with session.begin():
            await GalleryRepository(session).clear_progress()
        break


@router.delete("/api/galleries/{identifier}/progress", status_code=204)
async def clear_gallery_progress(identifier: int) -> None:
    row, _ = await _gallery(identifier)
    async for session in get_session():
        async with session.begin():
            await GalleryRepository(session).delete_progress(row.id)
        break


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


@router.delete("/api/galleries/{identifier}", status_code=204)
async def delete_gallery(
    identifier: int, delete_files: bool = False, delete_all_copies: bool = False
) -> None:
    try:
        async for session in get_session():
            async with session.begin():
                row = await session.get(Gallery, identifier)
                if row is None:
                    row = await session.scalar(select(Gallery).where(Gallery.gid == identifier))
                if row is None:
                    raise HTTPException(status_code=404, detail="Gallery not found")
                results = await delete_galleries_local(
                    session, [row], delete_files=delete_files, delete_all_copies=delete_all_copies
                )
            _record_gallery_delete_log(results, delete_files)
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


@router.post("/api/galleries/delete-bulk", status_code=200)
async def delete_galleries_bulk(body: BulkDeleteRequest) -> dict[str, object]:
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        async for session in get_session():
            async with session.begin():
                galleries: list[Gallery] = []
                for chunk in _chunked(list(dict.fromkeys(ids))):
                    rows = await session.scalars(
                        select(Gallery).where(Gallery.id.in_(chunk))
                    )
                    galleries.extend(rows.all())
                results = await delete_galleries_local(
                    session,
                    galleries,
                    delete_files=body.delete_files,
                    delete_all_copies=body.delete_all_copies,
                )
            _record_gallery_delete_log(results, body.delete_files)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in results if r.get("db_removed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {"deleted": deleted, "failed_deletions": failed_deletions, "results": results}


@router.post("/api/galleries/delete-filtered", status_code=200)
async def delete_galleries_filtered(body: FilteredDeleteRequest) -> dict[str, object]:
    if body.tag_mode not in {"and", "or"} or body.tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    category = body.category or None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    parsed_tags = _parse_tag_filter(body.tags or body.tag)
    _MAX_FILTERED_DELETE = 5000
    try:
        resolved_q = body.q or ""
        if body.q and body.q.strip():
            auto_tags, keywords, changed = await _resolve_search_tokens(body.q)
            if changed:
                parsed_tags.extend(auto_tags)
                parsed_tags = _dedupe_tags(parsed_tags)
                resolved_q = keywords
        matching_ids: list[int] = []
        async for session in get_session():
            repo = GalleryRepository(session)
            page = 1
            while True:
                _, rows = await repo.list_page(
                    page,
                    500,
                    q=resolved_q,
                    tags=parsed_tags,
                    tag_mode=body.tag_mode,
                    tag_match=body.tag_match,
                    category=category,
                    exclude_favorited=exclude_favorited,
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
            break

        results: list[dict] = []
        if matching_ids:
            async for session in get_session():
                async with session.begin():
                    for chunk in _chunked(list(dict.fromkeys(matching_ids))):
                        batch = await session.scalars(select(Gallery).where(Gallery.id.in_(chunk)))
                        res = await delete_galleries_local(
                            session, list(batch), delete_files=body.delete_files, delete_all_copies=body.delete_all_copies
                        )
                        results.extend(res)
                break
        _record_gallery_delete_log(results, body.delete_files)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in results if r.get("db_removed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {"deleted": deleted, "matched": len(matching_ids), "failed_deletions": failed_deletions, "results": results}


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
async def sync_gallery_tags(identifier: int, redirect: bool = False) -> dict[str, object]:
    from fastapi.responses import RedirectResponse

    try:
        async for session in get_session():
            async with session.begin():
                client = get_eh_client()
                result = await TagSyncService(client, GalleryRepository(session)).sync(identifier)
            break
    except GalleryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (GalleryGidMissing, GalleryTokenMissing) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    except Exception as exc:
        logger.warning("tag sync failed", extra=log_extra(gallery_id=identifier, error=type(exc).__name__))
        raise HTTPException(status_code=502, detail="ExHentai metadata request failed") from exc
    if redirect:
        return RedirectResponse(f"/galleries/{identifier}", status_code=303)
    return {
        "id": identifier,
        "gid": getattr(result, "gid", None),
        "title": getattr(result, "title", None),
        "count": getattr(result, "count", getattr(result, "tags_added", 0)),
        "tags_added": getattr(result, "tags_added", getattr(result, "count", 0)),
        "synced_at": getattr(result, "synced_at", None),
        "source": getattr(result, "source", None),
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


gallery_page = get_page
gallery_thumbnail = get_thumbnail
