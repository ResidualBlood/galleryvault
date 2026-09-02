"""Download task endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ...db.models import DownloadTask as DownloadTaskModel
from ...db.repository import DownloadRepository, GalleryUpdatesRepository
from ...services.download_worker import (
    clear_download_cancelled,
    mark_download_cancelled,
)
from ...services.downloader import DownloadTask
from ..dependencies import (
    db_error,
    get_current_settings,
    get_session,
    get_task_manager,
    spawn_task,
)
from ..schemas import DownloadRequest
from ..state import app_state

router = APIRouter()


@router.post("/api/downloads", status_code=202)
async def create_download(body: DownloadRequest) -> dict[str, object]:
    task_data = None
    try:
        async for session in get_session():
            async with session.begin():
                task = await DownloadRepository(session).create(
                    body.gid,
                    body.token,
                    body.title,
                    body.mode,
                    body.max_pages,
                    body.quality,
                )
                if task is None:
                    raise HTTPException(
                        status_code=409, detail="An active download already exists for this gid"
                    )
                task_data = DownloadTask(
                    task.gid,
                    task.token,
                    task.title or str(task.gid),
                    task.id,
                    max_retries=task.max_retries,
                    mode=task.mode,
                    max_pages=body.max_pages,
                    quality=task.quality,
                )
            break
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="An active download already exists for this gid"
        ) from exc
    except Exception as exc:
        raise db_error(exc) from exc

    downloader = app_state.downloader
    if downloader is None:
        raise HTTPException(status_code=503, detail="Downloader is unavailable")
    assert task_data is not None
    return {"id": task_data.id, "gid": task_data.gid, "status": "pending"}


@router.get("/api/downloads")
async def list_downloads(
    page: int = 1, page_size: int = 24, status: str | None = None
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        async for session in get_session():
            total, rows = await DownloadRepository(session).list_page(page, page_size, status)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    downloader = app_state.downloader
    items: list[dict[str, Any]] = []
    for x in rows:
        item: dict[str, Any] = {
            "id": x.id,
            "gid": x.gid,
            "title": x.title,
            "status": x.status,
            "retry_count": x.retry_count,
            "max_retries": x.max_retries,
            "current_page": x.current_page or 0,
            "total_pages": x.total_pages,
            "error_message": x.error_message,
            "mode": x.mode,
            "quality": x.quality,
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
