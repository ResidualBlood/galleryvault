"""Download task endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import DownloadTask as DownloadTaskModel
from ...db.repository import DownloadRepository, GalleryUpdatesRepository
from ...db.session import safe_transaction
from ...services.download_prepare import PreparedGallery, prepare_galleries
from ...services.download_worker import (
    clear_download_cancelled,
    mark_download_cancelled,
    notify_new_task,
)
from ...services.messages import GONE_DETAIL
from ..dependencies import (
    db_error,
    get_current_settings,
    get_session,
    get_task_manager,
    resolve_display_title,
    resolve_session,
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
    session: AsyncSession | None = None,
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
    if not quality:
        quality = get_current_settings().download_quality or "resample"
    if session is None:
        if not app_state.session_factory:
            raise HTTPException(status_code=503, detail="Database session factory not initialized")
        async with app_state.session_factory() as s:
            return await _create_from_prepared(
                prepared,
                mode=mode,
                max_pages=max_pages,
                quality=quality,
                fallback_title=fallback_title,
                session=s,
            )
    try:
        async with safe_transaction(session):
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
async def create_download(
    body: DownloadRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
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
        session=session,
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
async def create_downloads_batch(
    body: DownloadBatchRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
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
                session=session,
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


def _row_val(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


@router.get("/api/downloads")
async def list_downloads(
    page: int = 1,
    page_size: int = 24,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        total, rows = await DownloadRepository(session).list_page(page, page_size, status)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    downloader = app_state.downloader
    items: list[dict[str, Any]] = []
    for x in rows:
        title = _row_val(x, "title")
        title_jpn = _row_val(x, "title_jpn")
        gid = _row_val(x, "gid")
        is_fallback = bool(_row_val(x, "archive_fallback", False))
        item: dict[str, Any] = {
            "id": _row_val(x, "id"),
            "gid": gid,
            "title": resolve_display_title(title, title_jpn) or title,
            "status": _row_val(x, "status"),
            "retry_count": _row_val(x, "retry_count", 0),
            "max_retries": _row_val(x, "max_retries", 10),
            "current_page": _row_val(x, "current_page", 0) or 0,
            "total_pages": _row_val(x, "total_pages"),
            "error_message": _row_val(x, "error_message"),
            "mode": _row_val(x, "mode"),
            "quality": _row_val(x, "quality"),
            "archive_fallback": is_fallback,
            "archive_status": _row_val(x, "archive_status"),
            "archive_error": _row_val(x, "archive_error"),
        }
        items.append(item)

    downloading_items = [item for item in items if item.get("status") == "downloading"]
    if downloading_items and downloader is not None:
        async def _fetch_speed(target_item: dict[str, Any]) -> None:
            try:
                stats = await downloader.speed_stats(
                    target_item["gid"],
                    current_page=target_item.get("current_page", 0),
                    total_pages=target_item.get("total_pages"),
                )
                if stats:
                    target_item["speed"] = stats.get("speed")
                    target_item["eta_seconds"] = stats.get("eta_seconds")
            except Exception:  # noqa: BLE001, S110
                pass

        await asyncio.gather(*(_fetch_speed(it) for it in downloading_items))

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.post("/api/downloads/clear-success")
async def clear_success_downloads(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    deleted = 0
    try:
        async with safe_transaction(session):
            deleted = await DownloadRepository(session).delete_success()
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


@router.post("/api/downloads/retry-all")
async def retry_all_downloads(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        async with safe_transaction(session):
            retried_ids = await DownloadRepository(session).retry_all()
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    for task_id in retried_ids:
        clear_download_cancelled(task_id)
    if retried_ids:
        notify_new_task()

    return {
        "retried_count": len(retried_ids),
        "count": len(retried_ids),
        "task_ids": retried_ids,
    }


@router.post("/api/downloads/{task_id}/retry")
async def retry_download(
    task_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        async with safe_transaction(session):
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
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    clear_download_cancelled(task_id)
    notify_new_task()
    return {"id": task_id, "status": "pending"}


@router.post("/api/downloads/{task_id}/cancel")
async def cancel_download(
    task_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    was_active = False
    try:
        async with safe_transaction(session):
            row = await session.get(DownloadTaskModel, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Download task not found")
            was_active = row.status in {"pending", "downloading"}
            if not await DownloadRepository(session).cancel(task_id):
                raise HTTPException(status_code=404, detail="Download task not found")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    if was_active:
        mark_download_cancelled(task_id)
    return {"id": task_id, "status": "cancelled"}


@router.delete("/api/downloads/{task_id}", status_code=204)
async def delete_download_task(
    task_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    session = await resolve_session(session, fallback_dep=get_session)
    gid: int | None = None
    was_downloading = False
    try:
        async with safe_transaction(session):
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
