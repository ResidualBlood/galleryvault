"""
Gallery endpoints.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from galleryvault.app import main
from galleryvault.db.models import Gallery
from galleryvault.db.repository import GalleryRepository
from galleryvault.logging import log_extra
from galleryvault.scanners import registry
from galleryvault.scanners.base import CATEGORIES, PageInfo
from galleryvault.services.tag_sync import GalleryGidMissing, GalleryNotFound, GalleryTokenMissing
from galleryvault.services.tag_translation import translated_tag
from galleryvault.services.thumbnails import JPEG_MIME, ThumbnailError

router = APIRouter()

@router.get("/api/galleries")
async def gallery_list(
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
            status_code=422, detail="page must be >= 1 and page_size must be between 1 and 100"
        )
    if tag_mode not in {"and", "or"} or tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    if category == "":
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
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
    try:
        async with main._settings_session() as session:
            total, rows = await GalleryRepository(session).list_page(
                page, page_size, q, parsed_tags, tag_mode, tag_match, category
            )
            tag_map = await GalleryRepository(session).tags_for_galleries([row.id for row in rows])
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "q": q or "",
        "tags": tags or "",
        "tag_mode": tag_mode,
        "tag_match": tag_match,
        "category": category or "",
        "items": [
            {
                "id": row.id,
                "gid": row.gid,
                "title": main.display_title(row),
                "title_english": row.title,
                "title_jpn": row.title_jpn,
                "storage_type": row.storage_type,
                "category": row.category or "other",
                "page_count": row.page_count or 0,
                "cover_url": f"/api/galleries/{row.id}/thumb/0" if row.page_count else None,
                "tags": [
                    {"namespace": namespace, "name": name, "display": translated_tag(namespace, name)[1]}
                    for namespace, name in tag_map.get(row.id, [])
                ],
            }
            for row in rows
        ],
    }


@router.get("/api/galleries/random")
async def gallery_random() -> dict[str, object]:
    try:
        async with main._settings_session() as session:
            gallery_id = await GalleryRepository(session).random_id()
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    if gallery_id is None:
        raise HTTPException(status_code=404, detail="No galleries available")
    return {"id": gallery_id}


@router.get("/api/galleries/{identifier}/next")
async def gallery_next(identifier: int) -> dict[str, object]:
    try:
        async with main._settings_session() as session:
            next_id = await GalleryRepository(session).next_gallery_id(identifier)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    if next_id is None:
        raise HTTPException(status_code=404, detail="No next gallery")
    return {"id": next_id}


@router.get("/api/galleries/{identifier}")
async def gallery_detail(identifier: int) -> dict[str, object]:
    row, pages = await main._gallery(identifier)
    tags = await main._gallery_tags(row.id)
    source_meta = row.source_meta or {}
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
        "title": main.display_title(row),
        "title_english": row.title,
        "title_jpn": row.title_jpn,
        "storage_type": row.storage_type,
        "category": row.category or "other",
        "page_count": len(pages),
        "file_size": row.file_size,
        "pages": [
            {"index": p.page_index, "name": p.member_name, "media_type": p.media_type}
            for p in pages
        ],
        "warnings": source_meta.get("warnings", []),
        "spider_info": {key: source_meta[key] for key in spider_keys if key in source_meta},
        "tags": [
            {"namespace": namespace, "name": name, "display": translated_tag(namespace, name)[1]}
            for namespace, name in tags
        ],
        "tags_synced_at": row.tags_synced_at,
    }


@router.get("/api/galleries/{identifier}/progress")
async def gallery_progress(identifier: int) -> dict[str, object]:
    row, pages = await main._gallery(identifier)
    async with main._settings_session() as session:
        progress = await GalleryRepository(session).progress(row.id)
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else 0,
        "total_pages": progress.total_pages if progress else len(pages),
        "updated_at": progress.updated_at if progress else None,
    }


@router.put("/api/galleries/{identifier}/progress")
async def save_gallery_progress(identifier: int, body: main.ProgressRequest) -> dict[str, object]:
    row, pages = await main._gallery(identifier)
    if body.current_page >= len(pages):
        raise HTTPException(status_code=422, detail="current_page is outside gallery")
    async with main._settings_session() as session, session.begin():
        progress = await GalleryRepository(session).upsert_progress(
            row.id, body.current_page, body.total_pages or len(pages)
        )
        await GalleryRepository(session).record_history(
            row.id, body.current_page, body.total_pages or len(pages)
        )
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page,
        "total_pages": progress.total_pages,
    }


@router.get("/api/history")
async def history(page: int = 1, page_size: int = 24) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    async with main._settings_session() as session:
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
    async with main._settings_session() as session, session.begin():
        await GalleryRepository(session).clear_history()


@router.delete("/api/galleries/{identifier}", status_code=204)
async def delete_gallery(identifier: int, delete_files: bool = False) -> None:
    try:
        async with main._settings_session() as session, session.begin():
            gallery = await GalleryRepository(session).delete_by_identifier(identifier)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    if gallery is None:
        raise HTTPException(status_code=404, detail="Gallery not found")
    if delete_files:
        main._remove_gallery_files(gallery)


@router.post("/api/galleries/delete-bulk")
async def delete_galleries_bulk(body: main.BulkDeleteRequest) -> dict[str, object]:
    if not body.ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        async with main._settings_session() as session, session.begin():
            rows = await session.scalars(
                select(Gallery).where(Gallery.id.in_(body.ids))
            )
            galleries = list(rows)
            removed = await GalleryRepository(session).delete_ids([g.id for g in galleries])
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    if body.delete_files:
        for gallery in galleries:
            main._remove_gallery_files(gallery)
    return {"deleted": removed}


@router.post("/api/galleries/{identifier}/sync-tags")
async def sync_gallery_tags(identifier: int, redirect: bool = False):
    try:
        async with main._settings_session() as session, session.begin():
            # Referenced via main so tests that monkeypatch main.TagSyncService
            # take effect.
            result = await main.TagSyncService(
                main.app.state.eh_client, GalleryRepository(session)
            ).sync(identifier)
    except GalleryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (GalleryGidMissing, GalleryTokenMissing) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    except Exception as exc:
        main.logger.warning(
            "ExHentai tag synchronization failed", extra=log_extra(error=type(exc).__name__)
        )
        raise HTTPException(status_code=502, detail="ExHentai metadata request failed") from exc
    if redirect:
        return RedirectResponse(f"/galleries/{identifier}", status_code=303)
    return result


@router.get("/api/galleries/{identifier}/pages/{page_index}")
async def gallery_page(identifier: int, page_index: int) -> StreamingResponse:
    row, pages = await main._gallery(identifier)
    page = next((item for item in pages if item.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    scanner = registry.for_path(Path(row.storage_path))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery")
    stream = await run_in_threadpool(
        scanner.open_page,
        main._meta(row, pages),
        PageInfo(page.page_index, page.member_name, page.media_type),
    )
    return StreamingResponse(
        main._closing_stream(stream), media_type=main._page_media_type(page.media_type)
    )


@router.get("/api/galleries/{identifier}/thumb/{page_index}")
async def gallery_thumbnail(identifier: int, page_index: int) -> FileResponse:
    row, pages = await main._gallery(identifier)
    page = next((item for item in pages if item.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    scanner = registry.for_path(Path(row.storage_path))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery")
    service = main._thumb_service()
    cached = service.cached(row.id, page_index)
    if cached is None:
        stream = await run_in_threadpool(
            scanner.open_page,
            main._meta(row, pages),
            PageInfo(page.page_index, page.member_name, page.media_type),
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
                service.get_or_create, row.id, page_index, data
            )
        except ThumbnailError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        cached,
        media_type=JPEG_MIME,
        headers={"Cache-Control": "public, max-age=86400"},
    )

