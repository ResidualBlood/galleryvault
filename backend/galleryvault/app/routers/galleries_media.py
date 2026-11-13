"""Gallery page streaming, page meta, CBZ export and thumbnail endpoints.

The handlers were moved out of ``galleries`` verbatim; ``galleries`` re-exports
them and includes this router at the end of its own router so URL paths,
response codes, exceptions and authentication are unchanged.

Test-patched helpers (``_invoke_gallery``, ``spawn_task``, ...) stay on the
``galleries`` module and are resolved at call time through ``_gal()``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from ...db.models import Gallery, GalleryPage
from ...logging import log_extra
from ...scanners import registry
from ...scanners.base import GalleryMeta, PageInfo
from ...services.export_cbz import (
    UnsafeExportPath,
    cbz_filename,
    is_cbz_file,
    pack_directory_cbz,
)
from ...services.favorites_worker import ensure_remote_cover
from ...services.thumbnails import JPEG_MIME, ThumbnailError
from ..dependencies import (
    get_current_settings,
    get_session,
    image_content_type,
    release_session,
    resolve_session,
)
from .media_probe import _inspect_image_meta

# Keep the pre-split logger name so log records stay attributed to the router.
logger = logging.getLogger("galleryvault.app.routers.galleries")
router = APIRouter()

_PAGE_STREAM_CHUNK = 256 * 1024


def _gal():
    """Return the ``galleries`` module for runtime attribute lookup (no import cycle)."""
    from . import galleries

    return galleries


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


def _unlink_export(path: str) -> None:
    Path(path).unlink(missing_ok=True)


@router.get("/api/galleries/{identifier}/export.cbz")
async def export_gallery_cbz(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> FileResponse:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _gal()._invoke_gallery(identifier, session=session)
    path = Path(row.storage_path or "")
    now = datetime.now(UTC).isoformat()
    filename = cbz_filename(getattr(row, "title", None), getattr(row, "gid", None), row.id)
    total = len(pages)
    page_pairs = [(p.page_index, p.member_name or "") for p in pages]

    def _log(status: str, reason: str, done: int = 0) -> None:
        tm = _gal().get_task_manager()
        tm.record_task(
            "export-cbz",
            now,
            datetime.now(UTC).isoformat(),
            status,
            reason=reason,
            done=done,
            total=total,
        )
        _gal().spawn_task(tm.persist_history(), "persist task history")

    if not path.exists():
        _log("failed", "missing files")
        raise HTTPException(status_code=404, detail="Gallery files not found")
    if is_cbz_file(path):
        _log("success", path.name, total)
        await release_session(session)
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
    await release_session(session)
    try:
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
    row, pages = await _gal()._invoke_gallery(identifier, session=session)
    page = next((p for p in pages if p.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    media_type = _page_media_type(page.media_type or "jpg")
    page_info = PageInfo(page.page_index, page.member_name or "", page.media_type or "jpg")
    storage_path = Path(row.storage_path or "")
    scanner = registry.for_path(storage_path)
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery storage")
    try:
        stream = await run_in_threadpool(
            scanner.open_page,
            _meta(row, pages),
            page_info,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Streaming starts after this coroutine returns; release the pooled
    # connection now instead of when the response finishes.
    await release_session(session)
    return StreamingResponse(
        _closing_stream(stream),
        media_type=media_type,
    )


@router.get("/api/galleries/{identifier}/pages/{page_index}/meta")
async def get_page_meta(
    identifier: int,
    page_index: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    session = await resolve_session(session, fallback_dep=get_session)
    row, pages = await _gal()._invoke_gallery(identifier, session=session)
    page = next((p for p in pages if p.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    page_info = PageInfo(page.page_index, page.member_name or "", page.media_type or "jpg")
    storage_path = Path(row.storage_path or "")
    scanner = registry.for_path(storage_path)
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery storage")
    # File access happens in a worker thread; the request no longer needs its
    # DB transaction while the page is opened and inspected.
    meta = _meta(row, pages)
    await release_session(session)
    try:
        stream = await run_in_threadpool(scanner.open_page, meta, page_info)
    except FileNotFoundError as exc:
        logger.warning(
            "Page meta file missing",
            extra=log_extra(gallery_id=identifier, page=page_index, error=type(exc).__name__),
        )
        raise HTTPException(status_code=404, detail="Page file not found") from exc
    except ValueError as exc:
        logger.warning(
            "Page meta path rejected",
            extra=log_extra(gallery_id=identifier, page=page_index, error=type(exc).__name__),
        )
        raise HTTPException(status_code=400, detail="Invalid page path") from exc
    except Exception as exc:
        logger.warning(
            "Failed to open page for meta",
            extra=log_extra(gallery_id=identifier, page=page_index, error=type(exc).__name__),
        )
        raise HTTPException(status_code=500, detail="Page could not be read") from exc

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

    gal = _gal()
    # Runtime identity comparison: tests patch ``galleries._gallery``, so this
    # must be read from the module object on every call.
    if gal._gallery is not gal._default_gallery:
        try:
            resolved_session = await resolve_session(session, fallback_dep=get_session)
        except HTTPException:
            resolved_session = None
        row, pages = await gal._invoke_gallery(identifier, session=resolved_session)
    else:
        session = await resolve_session(session, fallback_dep=get_session)
        repo = gal.GalleryRepository(session)
        row = await repo.get_by_identifier(identifier)

    if row is None:
        raise HTTPException(status_code=404, detail="Gallery not found")

    if row.page_count is not None and row.page_count > 0 and page_index >= row.page_count:
        raise HTTPException(status_code=404, detail="Page allowance exceeded" if False else "Page not found")

    service = gal._get_thumb_service()

    is_fallback = False
    if page_index == 0 and row.gid:
        remote_cover = service.cached_remote_cover(row.gid)
        if remote_cover is not None:
            head = await run_in_threadpool(lambda: remote_cover.read_bytes()[:16])
            media_type = image_content_type(head)
            if media_type == "application/octet-stream":
                media_type = JPEG_MIME
            response = _thumb_file_response(
                remote_cover,
                media_type=media_type,
                # Covers are immutable per gid: let browsers/proxies keep them.
                cache_control="public, max-age=604800",
                gallery_id=row.id,
                page_index=page_index,
                request=request,
            )
            await release_session(session)
            return response
        gal.spawn_task(
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
        # Cover not ready yet: only a short cache so the browser retries soon
        # instead of hammering the endpoint on every render.
        "public, max-age=300"
        if is_fallback
        else ("public, max-age=31536000, immutable" if page_index > 0 else "public, max-age=86400")
    )

    cached = service.cached(row.id, page_index)
    if cached is not None:
        response = _thumb_file_response(
            cached,
            media_type=JPEG_MIME,
            cache_control=cache_control,
            gallery_id=row.id,
            page_index=page_index,
            request=request,
        )
        await release_session(session)
        return response

    if pages is None:
        repo = gal.GalleryRepository(session)
        pages = list(await repo.get_pages(row.id))

    page = next((p for p in pages if p.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

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
    response = _thumb_file_response(
        cached,
        media_type=JPEG_MIME,
        cache_control=cache_control,
        gallery_id=row.id,
        page_index=page_index,
        request=request,
    )
    await release_session(session)
    return response
