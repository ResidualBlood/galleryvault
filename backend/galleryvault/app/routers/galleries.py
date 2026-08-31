"""
Gallery endpoints.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from galleryvault.app import main
from galleryvault.db.models import Gallery
from galleryvault.db.repository import DownloadRepository, GalleryRepository, _chunked
from galleryvault.logging import log_extra
from galleryvault.scanners import registry
from galleryvault.scanners.base import CATEGORIES, PageInfo
from galleryvault.services.tag_sync import GalleryGidMissing, GalleryNotFound, GalleryTokenMissing
from galleryvault.services.tag_translation import translated_tag
from galleryvault.services.thumbnails import JPEG_MIME, ThumbnailError

router = APIRouter()


def _dedupe_tags(tags: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    seen: set[tuple[str | None, str]] = set()
    out: list[tuple[str | None, str]] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _parse_tag_filter(tags: str | None) -> list[tuple[str | None, str]]:
    """Parse the comma-separated ``tags`` query string into (ns, name) pairs."""
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
    """Split a free-form query into explicit tag filters + title keywords.

    Only explicit ``ns:name`` tokens become tag filters; every other
    whitespace-separated token is a plain title keyword.  Free-form words are
    never auto-promoted to tags (that requires the UI's tag suggestions, which
    the user explicitly clicks).  Returns ``(tags, keywords, changed)``.
    """
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
            status_code=422, detail="page must be >= 1 and page_size must be between 1 and 500"
        )
    if tag_mode not in {"and", "or"} or tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    if category == "":
        category = None
    exclude_favorited = False
    if category == "__not_fav__":
        # Pseudo-category for "local galleries not in any favorite folder".
        exclude_favorited = True
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    parsed_tags = _parse_tag_filter(tags)
    try:
        async with main._settings_session() as session:
            repo = GalleryRepository(session)
            resolved_q = q or ""
            resolved = False
            if q and q.strip():
                auto_tags, keywords, changed = await _resolve_search_tokens(q)
                resolved = changed
                if changed:
                    parsed_tags.extend(auto_tags)
                    parsed_tags = _dedupe_tags(parsed_tags)
                    resolved_q = keywords
            total, rows = await repo.list_page(
                page, page_size, resolved_q, parsed_tags, tag_mode, tag_match, category,
                exclude_favorited,
            )
            tag_map = await repo.tags_for_galleries([row.id for row in rows])
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
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
        "eh_url": (
            f"{main._settings().exhentai_base_url.rstrip('/')}/g/{row.gid}/{row.token}/"
            if row.gid and row.token
            else ""
        ),
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
        "image_quality": getattr(row, "image_quality", None),
    }


class DownloadOriginalRequest(BaseModel):
    archive: bool = False


@router.post("/api/galleries/{identifier}/download-original", status_code=202)
async def download_gallery_original(
    identifier: int, body: DownloadOriginalRequest
) -> dict[str, object]:
    """Enqueue an original-quality download for a local gallery.

    ``archive=False`` downloads page-by-page (no GP); ``archive=True`` goes
    through the ExHentai archive (zip) channel.  For the page-by-page path the
    first page is resolved up front so a resample-only gallery is rejected
    instead of silently downgrading to resample.
    """
    row, _ = await main._gallery(identifier)
    if not row.gid or not row.token:
        raise HTTPException(status_code=422, detail="Gallery has no ExHentai gid/token")
    mode = "gallery_archive" if body.archive else "gallery"
    if not body.archive:
        client = main.app.state.eh_client
        if client is None:
            raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
        try:
            preview = await client.fetch_gallery(
                row.gid, row.token, max_pages=1, resolve_urls=True
            )
        except Exception as exc:
            main.logger.warning(
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
        async with main._settings_session() as session, session.begin():
            task = await DownloadRepository(session).create(
                row.gid, row.token, row.title, mode, None, "original"
            )
            if task is None:
                raise HTTPException(
                    status_code=409, detail="An active download already exists for this gid"
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise main._db_error(exc) from exc
    return {"id": task.id, "gid": task.gid, "status": "pending"}


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
            gallery = await GalleryRepository(session).get_by_identifier(identifier)
            if gallery is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            results = await main.delete_galleries_local(
                session, [gallery], delete_files=delete_files, delete_all_copies=False
            )
            _record_gallery_delete_log(results)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc


@router.post("/api/galleries/delete-bulk")
async def delete_galleries_bulk(body: main.BulkDeleteRequest) -> dict[str, object]:
    if not body.ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        async with main._settings_session() as session, session.begin():
            galleries: list[Gallery] = []
            for chunk in _chunked(list(dict.fromkeys(body.ids))):
                rows = await session.scalars(
                    select(Gallery).where(Gallery.id.in_(chunk))
                )
                galleries.extend(rows.all())
            results = await main.delete_galleries_local(
                session, galleries, delete_files=body.delete_files, delete_all_copies=False
            )
            _record_gallery_delete_log(results)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    deleted = sum(1 for r in results if r["db_removed"])
    failed_deletions = [p for r in results for p in r["failed_paths"]]
    return {"deleted": deleted, "failed_deletions": failed_deletions}


@router.post("/api/galleries/delete-filtered")
async def delete_galleries_filtered(body: main.FilteredDeleteRequest) -> dict[str, object]:
    """Delete every gallery matching the current library filter.

    The SPA used to page through the filter on the client and POST the whole id
    list to ``delete-bulk``.  For big libraries that list can exceed asyncpg's
    ~32767 bound-parameter limit.  Here the backend re-runs the same filter the
    library grid uses, pages it, and deletes in 500-row batches — the client
    only sends the filter itself.
    """
    if body.tag_mode not in {"and", "or"} or body.tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    category = body.category or None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    parsed_tags = _parse_tag_filter(body.tags)
    try:
        async with main._settings_session() as session, session.begin():
            repo = GalleryRepository(session)
            resolved_q = body.q or ""
            if body.q and body.q.strip():
                auto_tags, keywords, changed = await _resolve_search_tokens(body.q)
                if changed:
                    parsed_tags.extend(auto_tags)
                    parsed_tags = _dedupe_tags(parsed_tags)
                    resolved_q = keywords
            matching_ids: list[int] = []
            page = 1
            while True:
                _, rows = await repo.list_page(
                    page, 500, resolved_q, parsed_tags, body.tag_mode, body.tag_match,
                    category, exclude_favorited,
                )
                if not rows:
                    break
                matching_ids.extend(r.id for r in rows)
                if len(rows) < 500:
                    break
                page += 1
            results: list[dict] = []
            for chunk in _chunked(list(dict.fromkeys(matching_ids))):
                batch = await session.scalars(select(Gallery).where(Gallery.id.in_(chunk)))
                results.extend(
                    await main.delete_galleries_local(
                        session, list(batch), delete_files=body.delete_files, delete_all_copies=False
                    )
                )
            _record_gallery_delete_log(results)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    deleted = sum(1 for r in results if r["db_removed"])
    failed_deletions = [p for r in results for p in r["failed_paths"]]
    return {"deleted": deleted, "matched": len(matching_ids), "failed_deletions": failed_deletions}


def _record_gallery_delete_log(results: list[dict]) -> None:
    """Append a gallery-delete entry to the activity log (Logs page)."""
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    deleted = sum(1 for r in results if r["db_removed"])
    failed = [p for r in results for p in r["failed_paths"]]
    reason = f"deleted {deleted}/{len(results)}"
    if failed:
        reason += f", delete failed {len(failed)}: {', '.join(failed[:3])}"
        if len(failed) > 3:
            reason += f" (+{len(failed) - 3} more)"
    status = "failed" if failed else "success"
    main._record_task("gallery-delete", now, now, status, reason=reason, done=deleted, total=len(results))


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
        main._closing_stream(stream),
        media_type=main._page_media_type(page.media_type),
        headers={"Cache-Control": "public, max-age=3600"},
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

