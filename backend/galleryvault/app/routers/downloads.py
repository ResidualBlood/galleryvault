"""Download task endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from galleryvault.app import main
from galleryvault.db.models import DownloadTask as DownloadTaskModel
from galleryvault.db.repository import DownloadRepository
from galleryvault.services.downloader import DownloadTask

router = APIRouter()


@router.post("/api/downloads", status_code=202)
async def create_download(body: main.DownloadRequest) -> dict[str, object]:
    _settings_session = main._settings_session
    try:
        async with _settings_session() as session, session.begin():
            task = await DownloadRepository(session).create(
                body.gid, body.token, body.title, body.mode, body.max_pages
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
                task.max_retries,
                max_pages=body.max_pages,
            )
    except HTTPException:
        raise
    except IntegrityError as exc:
        # Race with a concurrent enqueue of the same active gid (guarded by the
        # partial unique index): report as a conflict, not a 503.
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="An active download already exists for this gid"
        ) from exc
    except Exception as exc:
        raise main._db_error(exc) from exc
    downloader = main.app.state.downloader
    if downloader is None:
        raise HTTPException(status_code=503, detail="Downloader is unavailable")
    return {"id": task_data.id, "gid": task_data.gid, "status": "pending"}


@router.get("/api/downloads")
async def list_downloads(
    page: int = 1, page_size: int = 24, status: str | None = None
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        async with main._settings_session() as session:
            total, rows = await DownloadRepository(session).list_page(page, page_size, status)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": x.id,
                "gid": x.gid,
                "title": x.title,
                "status": x.status,
                "retry_count": x.retry_count,
                "max_retries": x.max_retries,
                "current_page": x.current_page or 0,
                "total_pages": x.total_pages,
                "error_message": x.error_message,
            }
            for x in rows
        ],
    }


@router.post("/api/downloads/{task_id}/retry")
async def retry_download(task_id: int) -> dict[str, object]:
    try:
        async with main._settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Download task not found")
            if row.status not in {"failed", "cancelled", "success"}:
                raise HTTPException(status_code=409, detail="Task is still active")
            row.status = "pending"
            row.retry_count = 0
            row.error_message = None
            row.finished_at = None
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    main._download_cancelled.discard(task_id)
    return {"id": task_id, "status": "pending"}


@router.post("/api/downloads/{task_id}/cancel")
async def cancel_download(task_id: int) -> dict[str, object]:
    was_downloading = False
    try:
        async with main._settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Download task not found")
            was_downloading = row.status == "downloading"
            if not await DownloadRepository(session).cancel(task_id):
                raise HTTPException(status_code=404, detail="Download task not found")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    # Only a mid-flight download needs the in-flight cancel flag; a pending task
    # is simply not claimed.  The worker discards the flag when it handles the
    # cancellation, so the set never grows with dead ids.
    if was_downloading:
        main._download_cancelled.add(task_id)
    return {"id": task_id, "status": "cancelled"}


@router.delete("/api/downloads/{task_id}", status_code=204)
async def delete_download_task(task_id: int) -> None:
    gid: int | None = None
    try:
        async with main._settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Download task not found")
            gid = row.gid
            if not await DownloadRepository(session).delete(task_id):
                raise HTTPException(status_code=404, detail="Download task not found")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    main._download_cancelled.discard(task_id)
    if gid is not None:
        await _cleanup_download_temp(gid)


async def _cleanup_download_temp(gid: int) -> None:
    """Remove a partial download directory (``.gv-{gid}``) if present."""
    import shutil as _shutil

    try:
        temp = Path(main._settings().download_root) / f".gv-{gid}"
        if temp.exists():
            _shutil.rmtree(temp, ignore_errors=True)
    except OSError:
        pass
