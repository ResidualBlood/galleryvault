"""Download task endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ...db.models import DownloadTask as DownloadTaskModel
from ...db.models import Gallery
from ...db.repository import DownloadRepository, GalleryRepository, GalleryUpdatesRepository
from ...services.download_prepare import PreparedGallery, prepare_galleries
from ...services.download_worker import (
    clear_download_cancelled,
    mark_download_cancelled,
)
from ...services.downloader import Downloader
from ...services.messages import GONE_DETAIL
from ..dependencies import (
    db_error,
    get_current_settings,
    get_session,
    get_task_manager,
    resolve_display_title,
    spawn_task,
)
from ..schemas import DownloadBatchRequest, DownloadRequest
from ..state import app_state

router = APIRouter()


async def _create_from_prepared(
    prepared: PreparedGallery,
    *,
    mode: str | None,
    max_pages: int | None,
    quality: str | None,
    fallback_title: str | None = None,
) -> tuple[str, dict[str, object]]:
    if prepared.gone:
        return "gone", {
            "gid": prepared.gid,
            "old_gid": prepared.old_gid,
            "title": prepared.title or str(prepared.gid),
            "detail": GONE_DETAIL,
        }
    if prepared.already_local:
        return "skipped", {
            "gid": prepared.gid,
            "old_gid": prepared.old_gid,
            "title": prepared.title or str(prepared.gid),
            "detail": "newer version already in library",
        }
    title = prepared.title or fallback_title
    try:
        async for session in get_session():
            async with session.begin():
                task = await DownloadRepository(session).create(
                    prepared.gid,
                    prepared.token,
                    title,
                    mode,
                    max_pages,
                    quality,
                    title_jpn=prepared.title_jpn,
                )
                if task is None:
                    return "skipped", {
                        "gid": prepared.gid,
                        "old_gid": prepared.old_gid,
                        "title": title or str(prepared.gid),
                        "detail": "already queued",
                    }
                payload = {
                    "id": task.id,
                    "gid": task.gid,
                    "old_gid": prepared.old_gid,
                    "title": resolve_display_title(task.title, task.title_jpn) or str(task.gid),
                    "status": "pending",
                }
            break
    except IntegrityError:
        return "skipped", {
            "gid": prepared.gid,
            "old_gid": prepared.old_gid,
            "title": title or str(prepared.gid),
            "detail": "already queued",
        }
    except Exception as exc:
        raise db_error(exc) from exc
    status = "updated" if prepared.old_gid else "queued"
    return status, payload


@router.post("/api/downloads", status_code=202)
async def create_download(body: DownloadRequest) -> dict[str, object]:
    if app_state.downloader is None:
        raise HTTPException(status_code=503, detail="Downloader is unavailable")
    prepared = (
        await prepare_galleries([(int(body.gid), str(body.token))])
    )[0]
    if body.title and not prepared.title:
        prepared.title = body.title
    status, payload = await _create_from_prepared(
        prepared,
        mode=body.mode,
        max_pages=body.max_pages,
        quality=body.quality,
        fallback_title=body.title,
    )
    if status == "gone":
        raise HTTPException(status_code=404, detail=GONE_DETAIL)
    if status == "skipped":
        raise HTTPException(
            status_code=409,
            detail=str(payload.get("detail") or "An active download already exists for this gid"),
        )
    return payload


@router.post("/api/downloads/batch", status_code=202)
async def create_downloads_batch(body: DownloadBatchRequest) -> dict[str, object]:
    if app_state.downloader is None:
        raise HTTPException(status_code=503, detail="Downloader is unavailable")
    pairs = [(int(item.gid), str(item.token)) for item in body.items]
    prepared_list = await prepare_galleries(pairs)
    queued = skipped = gone = updated = failed = 0
    results: list[dict[str, object]] = []
    for item, prepared in zip(body.items, prepared_list, strict=True):
        mode = body.mode or item.mode
        quality = body.quality if body.quality is not None else item.quality
        max_pages = body.max_pages if body.max_pages is not None else item.max_pages
        if item.title and not prepared.title:
            prepared.title = item.title
        try:
            status, payload = await _create_from_prepared(
                prepared,
                mode=mode,
                max_pages=max_pages,
                quality=quality,
                fallback_title=item.title,
            )
        except Exception:  # noqa: BLE001
            failed += 1
            results.append({"gid": prepared.gid, "status": "failed"})
            continue
        payload["status"] = status
        results.append(payload)
        if status == "queued":
            queued += 1
        elif status == "updated":
            updated += 1
            queued += 1
        elif status == "gone":
            gone += 1
        else:
            skipped += 1
    now = datetime.now(UTC).isoformat()
    tm = get_task_manager()
    tm.record_task(
        "download-enqueue",
        now,
        now,
        "success" if not failed else "failed",
        reason=f"queued {queued}, updated {updated}, gone {gone}, skipped {skipped}",
        done=queued,
        total=len(body.items),
    )
    spawn_task(tm.persist_history(), "persist task history")
    return {
        "queued": queued,
        "skipped": skipped,
        "gone": gone,
        "updated": updated,
        "failed": failed,
        "items": results,
    }


@router.get("/api/downloads")
async def list_downloads(
    page: int = 1, page_size: int = 24, status: str | None = None
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        async for session in get_session():
            total, rows = await DownloadRepository(session).list_page(page, page_size, status)
            missing = [x.gid for x in rows if not x.title and not getattr(x, "title_jpn", None)]
            meta: dict[int, dict] = {}
            if missing:
                meta = await GalleryRepository(session).metadata_map(missing)
                still = [g for g in missing if g not in meta]
                if still:
                    gal_rows = (
                        await session.scalars(select(Gallery).where(Gallery.gid.in_(still)))
                    ).all()
                    for gal in gal_rows:
                        meta[int(gal.gid)] = {
                            "title": gal.title,
                            "title_jpn": getattr(gal, "title_jpn", None),
                        }
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    downloader = app_state.downloader
    items: list[dict[str, Any]] = []
    for x in rows:
        title = x.title
        title_jpn = getattr(x, "title_jpn", None)
        if not title and not title_jpn:
            cached = meta.get(int(x.gid)) or {}
            title = cached.get("title")
            title_jpn = cached.get("title_jpn")
        mode = x.mode or ""
        is_fallback = False
        if "archive" in mode:
            if downloader is not None:
                is_fallback = downloader.is_archive_fallback(x.gid)
            else:
                s = app_state.settings or get_current_settings()
                is_fallback = Downloader.check_archive_fallback(Path(s.download_root), x.gid)
        item: dict[str, Any] = {
            "id": x.id,
            "gid": x.gid,
            "title": resolve_display_title(title, title_jpn) or title,
            "status": x.status,
            "retry_count": x.retry_count,
            "max_retries": x.max_retries,
            "current_page": x.current_page or 0,
            "total_pages": x.total_pages,
            "error_message": x.error_message,
            "mode": x.mode,
            "quality": x.quality,
            "archive_fallback": is_fallback,
        }
        if x.status == "downloading" and downloader is not None:
            try:
                stats = await downloader.speed_stats(
                    x.gid, current_page=x.current_page or 0, total_pages=x.total_pages
                )
            except Exception:  # noqa: BLE001
                stats = None
            if stats:
                item["speed"] = stats["speed"]
                item["eta_seconds"] = stats["eta_seconds"]
        items.append(item)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.post("/api/downloads/clear-success")
async def clear_success_downloads() -> dict[str, object]:
    deleted = 0
    try:
        async for session in get_session():
            async with session.begin():
                deleted = await DownloadRepository(session).delete_success()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    now = datetime.now(UTC).isoformat()
    tm = get_task_manager()
    tm.record_task(
        "download-clear-success",
        now,
        now,
        "success",
        reason=f"cleared {deleted} successful download tasks",
        done=deleted,
        total=deleted,
    )
    spawn_task(tm.persist_history(), "persist task history")
    return {"deleted": deleted}


@router.post("/api/downloads/{task_id}/retry")
async def retry_download(task_id: int) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                row = await session.get(DownloadTaskModel, task_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="Download task not found")
                if row.status not in {"failed", "cancelled", "success"}:
                    raise HTTPException(status_code=409, detail="Task is still active")
                row.status = "pending"
                row.retry_count = 0
                row.retry_at = None
                row.error_message = None
                row.finished_at = None
                row.max_retries = 10
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    clear_download_cancelled(task_id)
    return {"id": task_id, "status": "pending"}


@router.post("/api/downloads/{task_id}/cancel")
async def cancel_download(task_id: int) -> dict[str, object]:
    was_downloading = False
    try:
        async for session in get_session():
            async with session.begin():
                row = await session.get(DownloadTaskModel, task_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="Download task not found")
                was_downloading = row.status == "downloading"
                if not await DownloadRepository(session).cancel(task_id):
                    raise HTTPException(status_code=404, detail="Download task not found")
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    if was_downloading:
        mark_download_cancelled(task_id)
    return {"id": task_id, "status": "cancelled"}


@router.delete("/api/downloads/{task_id}", status_code=204)
async def delete_download_task(task_id: int) -> None:
    gid: int | None = None
    was_downloading = False
    try:
        async for session in get_session():
            async with session.begin():
                row = await session.get(DownloadTaskModel, task_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="Download task not found")
                gid = row.gid
                was_downloading = row.status == "downloading"
                if not await DownloadRepository(session).delete(task_id):
                    raise HTTPException(status_code=404, detail="Download task not found")
                await GalleryUpdatesRepository(session).mark_failed_by_task(
                    task_id, "download task removed"
                )
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    if was_downloading:
        mark_download_cancelled(task_id)
    else:
        clear_download_cancelled(task_id)
    if gid is not None:
        await _cleanup_download_temp(gid)


async def _cleanup_download_temp(gid: int) -> None:
    """Remove a partial download directory (.gv-{gid}) if present."""
    import shutil
    try:
        settings = get_current_settings()
        temp = Path(settings.download_root) / f".gv-{gid}"
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
    except OSError:
        pass
