"""A single download attempt, retry policy, cancellation and challenge pause."""

from __future__ import annotations

import asyncio
import logging
import os
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ...app.state import app_state
from ...config import get_settings
from ...db.models import DownloadTask as DownloadTaskModel
from ...db.repository import DownloadRepository
from ...logging import bind_log_context, log_extra
from ..downloader import (
    ArchiveNotRetryableError,
    DownloadCancelledError,
    DownloadTask,
)
from ..eh_client import (  # noqa: F401  # kept for backoff classification docs
    EhChallengeError,
    EhClientError,
    GalleryGoneError,
    GalleryReplacedError,
)
from ..messages import GONE_DETAIL, HOPS_DETAIL
from . import wake
from .ingest_pump import _resolve_notify_old_gid, serialize_ingest_payload
from .notify import download_progress, record_download_notification
from .wake import notify_new_task

logger = logging.getLogger("galleryvault.services.download_worker")

_RETRY_BACKOFFS = (
    30, 120, 480, 1800, 3600, 7200, 10800, 14400, 18000, 21600,
)
_PROGRESS_FLUSH_STEP = 20
_PROGRESS_FLUSH_INTERVAL = 5.0


def retry_backoff(retry_count: int) -> int:
    """Return the backoff delay (seconds) for the given failed attempt count."""
    return _RETRY_BACKOFFS[min(max(1, retry_count) - 1, len(_RETRY_BACKOFFS) - 1)]


def is_download_cancelled(task_id: int | None) -> bool:
    if task_id is None:
        return False
    tm = app_state.task_manager
    return bool(tm and tm.is_cancelled(task_id))


def clear_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.clear_cancelled(task_id)


def mark_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.request_cancel(task_id)


async def run_download(task: DownloadTask) -> None:
    if task.id is None:
        logger.warning("download task missing id; skipping", extra=log_extra(gid=task.gid))
        return
    with bind_log_context(worker="download", task_id=task.id, gid=task.gid):
        await _run_download_inner(task)


async def _apply_replacement(task: DownloadTask, exc: GalleryReplacedError) -> DownloadTask | None:
    session_cm = wake._get_background_session_factory()
    if session_cm is None or task.id is None:
        return None
    from ..download_prepare import _local_gids

    local = await _local_gids([exc.new_gid])
    if exc.new_gid in local:
        logger.info(
            "download retarget skipped; newer gid already in library",
            extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
        )
        try:
            async with session_cm() as session, session.begin():
                await DownloadRepository(session).cancel(task.id)
        except SQLAlchemyError:
            pass
        return None
    ok = False
    try:
        async with session_cm() as session, session.begin():
            ok = await DownloadRepository(session).retarget(
                task.id, exc.new_gid, exc.new_token, exc.title, exc.title_jpn
            )
    except IntegrityError:
        ok = False
    if not ok:
        logger.info(
            "download retarget skipped; newer gid already queued",
            extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
        )
        return None
    settings = app_state.settings or get_settings()
    try:
        temp = Path(settings.download_root) / f".gv-{task.gid}"
        if temp.exists():
            import shutil

            from ..storage_usage import safe_stat_size, storage_tracker

            sz = safe_stat_size(temp)
            shutil.rmtree(temp, ignore_errors=True)
            if sz > 0:
                storage_tracker.record_download_delta(-sz)
    except OSError:
        pass
    title = exc.title or str(exc.new_gid)
    tm = app_state.task_manager
    if tm:
        now = datetime.now(UTC).isoformat()
        tm.record_task(
            "download-updated",
            now,
            now,
            "success",
            reason=f"gid {exc.old_gid} -> {exc.new_gid}",
            done=1,
            total=1,
        )
    return DownloadTask(
        exc.new_gid,
        exc.new_token,
        title,
        task.id,
        task.max_retries,
        task.mode,
        task.category,
        max_pages=task.max_pages,
        quality=task.quality,
    )


async def _finalize_replacement_skip(task: DownloadTask, exc: GalleryReplacedError) -> None:
    """Write a terminal state when a replaced gallery could not be retargeted.

    Without this the row stays ``downloading`` forever and keeps occupying the
    unique active-gid index, blocking any later enqueue for the same gid.
    """
    session_cm = wake._get_background_session_factory()
    if session_cm is None or task.id is None:
        return
    message = f"替换链未能重定向：gid {exc.old_gid} -> {exc.new_gid}"
    try:
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None:
                return
            now = datetime.now(UTC)
            if row.status == "cancelled":
                row.finished_at = row.finished_at or now
            else:
                row.status = "failed"
                row.error_message = message
                row.retry_at = None
                row.finished_at = now
                row.updated_at = now
                # The source gid no longer exists on ExHentai, so requeueing it
                # is pointless: consume the budget so it stays terminal.
                row.retry_count = max(row.retry_count or 0, row.max_retries)
            await DownloadRepository(session).record_attempt(
                task.id, max(1, row.retry_count or 1), "failed", "GalleryReplacedError"
            )
    except SQLAlchemyError as db_exc:
        logger.error(
            "download replacement skip state persistence failed",
            extra=log_extra(
                task_id=task.id,
                gid=task.gid,
                error=str(db_exc) or type(db_exc).__name__,
            ),
        )


def _extract_http_meta(exc: BaseException) -> dict[str, Any]:
    resp = getattr(exc, "response", None)
    if resp is None:
        return {}
    meta: dict[str, Any] = {}
    status_code = getattr(resp, "status_code", None)
    if status_code is not None:
        meta["status_code"] = status_code
    headers = getattr(resp, "headers", None)
    if headers and hasattr(headers, "items"):
        summary = {
            str(k): str(v)
            for k, v in headers.items()
            if str(k).lower() in {"location", "server", "cf-ray", "content-type", "retry-after"}
        }
        if summary:
            meta["headers"] = summary
    return meta


_CHALLENGE_PROBE_INTERVAL = float(os.getenv("GV_CHALLENGE_PROBE_INTERVAL", "600"))
_MAX_CHALLENGE_PAUSES = max(1, int(os.getenv("GV_MAX_CHALLENGE_PAUSES", "5")))
# 302 challenges have their own per-task budget: pausing must not burn the
# retry budget, but an endless pause/resume/challenge loop must still
# terminate.
_challenge_counts: dict[int, int] = {}
# Created lazily on first use instead of at import time: asyncio primitives
# bind to the loop of their first waiter, and module import happens before any
# loop exists (report 01 P3-10).
_challenge_lock: asyncio.Lock | None = None
_challenge_lock_loop: asyncio.AbstractEventLoop | None = None
_last_resume_time = 0.0
_RESUME_DEBOUNCE_SECONDS = float(os.getenv("GV_RESUME_DEBOUNCE_SECONDS", "1.0"))


def _get_challenge_lock() -> asyncio.Lock:
    """Return a challenge lock bound to the current event loop."""
    global _challenge_lock, _challenge_lock_loop
    loop = asyncio.get_running_loop()
    if _challenge_lock is None or _challenge_lock_loop is not loop:
        _challenge_lock = asyncio.Lock()
        _challenge_lock_loop = loop
    return _challenge_lock


def challenge_count(task_id: int | None) -> int:
    if task_id is None:
        return 0
    return _challenge_counts.get(int(task_id), 0)


def reset_challenge_count(task_id: int | None) -> None:
    if task_id is None:
        return
    _challenge_counts.pop(int(task_id), None)


def _bump_challenge_count(task_id: int | None) -> int:
    if task_id is None:
        return 1
    count = _challenge_counts.get(int(task_id), 0) + 1
    _challenge_counts[int(task_id)] = count
    return count


async def _trigger_challenge_pause(
    sample_path: str | None = None,
    *,
    task_id: int | None = None,
    gid: int | None = None,
    response_meta: dict[str, Any] | None = None,
) -> None:
    """Trigger global pause due to ExHentai 302 anti-abuse challenge."""
    async with _get_challenge_lock():
        if app_state.extra.get("auto_resume_challenge") and getattr(
            app_state.settings or get_settings(), "global_paused", False
        ):
            if sample_path and not app_state.extra.get("challenge_sample_path"):
                app_state.extra["challenge_sample_path"] = sample_path
            return
        app_state.extra["auto_resume_challenge"] = True
        if sample_path:
            app_state.extra["challenge_sample_path"] = sample_path

        from ..settings_service import update_runtime_settings

        update_runtime_settings({"global_paused": True})

        session_factory = wake._get_background_session_factory()
        if session_factory:
            try:
                from ...db.repositories.settings import patch_settings
                from ...db.repository import SettingsRepository

                async with session_factory() as session, session.begin():
                    await patch_settings(SettingsRepository(session), {"global_paused": True})
            except Exception as exc:
                err_extra: dict[str, Any] = {"error": str(exc)}
                if task_id is not None:
                    err_extra["task_id"] = task_id
                if gid is not None:
                    err_extra["gid"] = gid
                if response_meta:
                    err_extra.update(response_meta)
                logger.exception(
                    "failed to persist global_paused setting on challenge",
                    extra=log_extra(**err_extra),
                )

        if app_state.telegram is not None:
            try:
                await app_state.telegram.send_message("🚨 触发 302 临时挑战，系统自动暂停下载")
            except Exception as exc:  # noqa: BLE001
                alert_extra: dict[str, Any] = {"error": type(exc).__name__}
                if task_id is not None:
                    alert_extra["task_id"] = task_id
                if gid is not None:
                    alert_extra["gid"] = gid
                logger.warning(
                    "failed to send challenge telegram alert",
                    extra=log_extra(**alert_extra),
                )


async def _resume_challenge_pause() -> None:
    """Resume global pause after ExHentai 302 anti-abuse challenge clears."""
    global _last_resume_time
    async with _get_challenge_lock():
        if not app_state.extra.get("auto_resume_challenge") and not getattr(
            app_state.settings or get_settings(), "global_paused", False
        ):
            return
        now_ts = _time.monotonic()
        if now_ts - _last_resume_time < _RESUME_DEBOUNCE_SECONDS and not app_state.extra.get("auto_resume_challenge"):
            return
        _last_resume_time = now_ts
        app_state.extra["auto_resume_challenge"] = False
        app_state.extra.pop("challenge_sample_path", None)

        from ..settings_service import update_runtime_settings

        update_runtime_settings({"global_paused": False})

        session_factory = wake._get_background_session_factory()
        if session_factory:
            try:
                from ...db.repositories.settings import patch_settings
                from ...db.repository import SettingsRepository

                async with session_factory() as session, session.begin():
                    await patch_settings(SettingsRepository(session), {"global_paused": False})
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to persist global_paused setting on resume",
                    extra=log_extra(error=str(exc)),
                )

        notify_new_task()

        if app_state.telegram is not None:
            try:
                await app_state.telegram.send_message("✅ 302 临时挑战解除，自动恢复下载")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "failed to send challenge resume telegram alert",
                    extra=log_extra(error=type(exc).__name__),
                )


async def challenge_probe_loop() -> None:
    """Periodically probe ExHentai if paused due to anti-abuse challenge."""
    while True:
        try:
            await asyncio.sleep(_CHALLENGE_PROBE_INTERVAL)
            settings = app_state.settings or get_settings()
            if not getattr(settings, "global_paused", False) or not app_state.extra.get(
                "auto_resume_challenge"
            ):
                continue

            client = app_state.eh_client
            if client is None and app_state.downloader is not None:
                client = getattr(app_state.downloader, "client", None)
            if client is None:
                continue

            sample_path = app_state.extra.get("challenge_sample_path", "/")
            cleared = await client.probe_challenge(sample_path)
            if cleared:
                logger.info("ExHentai anti-abuse challenge has cleared; resuming downloads")
                await _resume_challenge_pause()
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("challenge probe failed", extra=log_extra(error=type(exc).__name__))



def _classify_error(exc: BaseException) -> dict[str, Any]:
    """Classify a failed attempt for handler ordering and retry decisions."""
    gone = isinstance(exc, GalleryGoneError) or "does not exist on ExHentai" in str(exc)
    if isinstance(exc, GalleryReplacedError):
        kind = "replaced"
    elif isinstance(exc, DownloadCancelledError):
        kind = "cancelled"
    elif isinstance(exc, EhChallengeError):
        kind = "challenge"
    else:
        kind = "error"
    return {
        "kind": kind,
        "auth_failure": "authenticat" in str(exc),
        "gone": gone,
        "not_retryable": isinstance(exc, (ArchiveNotRetryableError, GalleryGoneError)) or gone,
        "message": GONE_DETAIL if gone else f"{type(exc).__name__}: {exc}",
    }


def _handle_archive_fallback(target: Any | None, exec_task: DownloadTask | None) -> bool:
    """Propagate the archive-fallback flag onto a row or update-values mapping."""
    if exec_task is None or not getattr(exec_task, "archive_fallback", False):
        return False
    if target is not None:
        if isinstance(target, dict):
            target["archive_fallback"] = True
        else:
            target.archive_fallback = True
    return True


async def _record_progress(
    task: DownloadTask,
    exec_task: DownloadTask | None,
    progress_state: dict[str, Any],
    current: int,
    total: int,
) -> None:
    """Throttle progress persistence and forward the archive-fallback marker."""
    if is_download_cancelled(task.id):
        raise DownloadCancelledError("download was cancelled")
    now = _time.monotonic()
    if (
        current >= total
        or progress_state["last_persisted"] == 0
        or current - progress_state["last_persisted"] >= _PROGRESS_FLUSH_STEP
        or now - progress_state["last_flush"] >= _PROGRESS_FLUSH_INTERVAL
    ):
        if task.id is not None:
            is_fb = _handle_archive_fallback(None, exec_task)
            await download_progress(
                task.id,
                current,
                total,
                archive_fallback=True if is_fb else None,
                gid=getattr(task, "gid", None),
            )
        progress_state["last_persisted"] = current
        progress_state["last_flush"] = now


async def _apply_retry_policy(
    session_cm: Any,
    task: DownloadTask,
    exc: BaseException,
    *,
    exec_task: DownloadTask | None = None,
) -> None:
    """Persist the retry/pause decision for a failed or challenged attempt."""
    info = _classify_error(exc)
    if info["kind"] == "challenge":
        http_meta = _extract_http_meta(exc)
        challenge_extra: dict[str, Any] = {
            "task_id": task.id,
            "gid": task.gid,
            "error": str(exc),
        }
        challenge_extra.update(http_meta)
        logger.warning(
            "download challenge encountered; auto-pausing downloads",
            extra=log_extra(**challenge_extra),
        )
        now = datetime.now(UTC)
        count = _bump_challenge_count(task.id)
        over_budget = count >= _MAX_CHALLENGE_PAUSES
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    if over_budget:
                        # Stop the pause/resume/challenge loop, but keep the
                        # remaining retry budget so a manual retry can still
                        # pick the task up later.
                        row.status = "failed"
                        row.retry_at = None
                        row.finished_at = now
                        row.retry_count = min(
                            max(0, row.retry_count or 0), max(0, row.max_retries - 1)
                        )
                        row.error_message = (
                            f"自动暂停失败：302 临时挑战已达上限 "
                            f"({count}/{_MAX_CHALLENGE_PAUSES})"
                        )
                    else:
                        row.status = "pending"
                        row.retry_at = now + timedelta(seconds=retry_backoff(max(1, count)))
                        row.error_message = (
                            f"自动暂停：检测到 ExHentai 302 临时挑战 "
                            f"({count}/{_MAX_CHALLENGE_PAUSES})"
                        )
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0,
                        max(1, row.retry_count or 1),
                        "challenged",
                        "EhChallengeError",
                    )
        except SQLAlchemyError as db_exc:
            logger.exception(
                "download status persistence failed on challenge",
                extra=log_extra(
                    task_id=task.id,
                    gid=task.gid,
                    error=str(db_exc) or type(db_exc).__name__,
                ),
            )
        if over_budget:
            logger.error(
                "302 challenge budget exhausted; failing task",
                extra=log_extra(
                    task_id=task.id,
                    gid=task.gid,
                    challenges=count,
                    limit=_MAX_CHALLENGE_PAUSES,
                ),
            )
        sample_path = f"/g/{task.gid}/{task.token}/" if task.token else "/"
        await _trigger_challenge_pause(
            sample_path,
            task_id=task.id,
            gid=task.gid,
            response_meta=http_meta,
        )
        return

    http_meta = _extract_http_meta(exc)
    fail_extra: dict[str, Any] = {
        "task_id": task.id,
        "gid": task.gid,
        "error": type(exc).__name__,
        "message": str(exc),
    }
    fail_extra.update(http_meta)
    logger.exception(
        "download task failed",
        extra=log_extra(**fail_extra),
    )
    row = None
    try:
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row and row.status != "cancelled":
                now = datetime.now(UTC)
                row.retry_count += 1
                if (
                    info["auth_failure"]
                    or info["not_retryable"]
                    or row.retry_count >= row.max_retries
                ):
                    row.status = "failed"
                    row.retry_at = None
                    row.finished_at = now
                    row.retry_count = max(row.retry_count, row.max_retries)
                else:
                    row.status = "pending"
                    # Always apply exponential backoff for transient errors so a
                    # just-failed task in not re-claimed immediately. The old
                    # `challenge ? backoff : now` caused non-challenge
                    # EhClientError to be retried in <1s, burning the retry budget.
                    row.retry_at = now + timedelta(seconds=retry_backoff(row.retry_count))
                _handle_archive_fallback(row, exec_task)
                row.error_message = info["message"]
                row.updated_at = now
                await DownloadRepository(session).record_attempt(
                    task.id or 0, row.retry_count, "failed", type(exc).__name__
                )
        if row is not None and row.status == "failed":
            await record_download_notification(
                "fail",
                task.title or str(task.gid),
                GONE_DETAIL if info["gone"] else type(exc).__name__,
            )
    except SQLAlchemyError as db_exc:
        logger.error(
            "download status persistence failed",
            extra=log_extra(error=str(db_exc) or type(db_exc).__name__),
        )


async def _run_download_inner(
    task: DownloadTask,
    *,
    follow_hops: int = 0,
    replaced_from_gid: int | None = None,
) -> None:
    session_cm = wake._get_background_session_factory()
    if session_cm is None:
        return
    downloader = app_state.downloader
    if downloader is None:
        return

    row = None
    exec_task: DownloadTask | None = None
    try:
        if is_download_cancelled(task.id):
            raise DownloadCancelledError("download was cancelled")

        attempt_no = 1
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None or row.status == "cancelled" or is_download_cancelled(task.id):
                if row is not None and row.status != "cancelled":
                    row.status = "cancelled"
                    row.finished_at = datetime.now(UTC)
                clear_download_cancelled(task.id)
                return
            row.status = "downloading"
            # ``started_at`` is the first start of the task, not of the latest
            # retry: overwriting it on every attempt loses that (report 01 P3-3).
            if getattr(row, "started_at", None) is None:
                row.started_at = datetime.now(UTC)
            attempt_no = (getattr(row, "retry_count", 0) or 0) + 1

        exec_task = DownloadTask(
            task.gid,
            task.token,
            task.title,
            task.id,
            1,
            task.mode,
            task.category,
            max_pages=task.max_pages,
            quality=task.quality,
            archive_fallback=bool(getattr(task, "archive_fallback", False)),
        )

        progress_state = {"last_persisted": 0, "last_flush": 0.0}

        async def _on_progress(current: int, total: int) -> None:
            await _record_progress(task, exec_task, progress_state, current, total)

        if is_download_cancelled(task.id):
            raise DownloadCancelledError("download was cancelled")

        result = await downloader.execute(
            exec_task,
            progress=_on_progress,
        )
        if is_download_cancelled(task.id):
            if result and hasattr(result, "path") and Path(result.path).exists():
                import shutil

                p = Path(result.path)
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            raise DownloadCancelledError("download was cancelled")
        now = datetime.now(UTC)
        # Files are on disk: the task stays ``downloading`` until the ingest
        # pump has actually inserted the gallery (INV-DL-1). ``success`` is
        # written by the pump only after a successful import.
        update_values: dict[str, Any] = {
            "target_path": str(result.path),
            "category": result.category,
            "error_message": None,
            "retry_count": 0,
            "retry_at": None,
            "ingest_status": "pending",
            "ingest_payload": serialize_ingest_payload(result),
            "updated_at": now,
        }
        _handle_archive_fallback(update_values, exec_task)
        if result.title:
            update_values["title"] = result.title
        if getattr(result, "title_jpn", None):
            update_values["title_jpn"] = result.title_jpn
        if getattr(result, "pages", None):
            update_values["current_page"] = func.coalesce(
                DownloadTaskModel.total_pages, result.pages
            )
            update_values["total_pages"] = func.coalesce(
                DownloadTaskModel.total_pages, result.pages
            )

        async with session_cm() as session, session.begin():
            # Resolve the notification wording *before* the library insert: the
            # gallery does not exist yet, so a fresh download stays ``ok``.
            ingest_payload = update_values["ingest_payload"]
            ingest_payload["notify_old_gid"] = await _resolve_notify_old_gid(
                session, task.gid, replaced_from_gid
            )
            if hasattr(session, "execute"):
                stmt = (
                    update(DownloadTaskModel)
                    .where(
                        DownloadTaskModel.id == task.id,
                        DownloadTaskModel.status == "downloading",
                    )
                    .values(**update_values)
                )
                update_result = await session.execute(stmt)
                is_cancelled = bool(update_result.rowcount == 0)
            else:
                row = await session.get(DownloadTaskModel, task.id)
                if (
                    row is None
                    or row.status != "downloading"
                    or is_download_cancelled(task.id)
                ):
                    is_cancelled = True
                else:
                    is_cancelled = False
                    row.status = "downloading"
                    row.target_path = update_values.get("target_path")
                    row.category = update_values.get("category")
                    row.error_message = None
                    row.retry_count = 0
                    row.retry_at = None
                    row.ingest_status = "pending"
                    row.ingest_payload = update_values.get("ingest_payload")
                    _handle_archive_fallback(row, exec_task)
                    if "title" in update_values:
                        row.title = update_values["title"]
                    if "title_jpn" in update_values:
                        row.title_jpn = update_values["title_jpn"]
                    if getattr(result, "pages", None):
                        row.current_page = getattr(row, "total_pages", None) or result.pages
                        row.total_pages = getattr(row, "total_pages", None) or result.pages

            if is_cancelled:
                if result and hasattr(result, "path") and Path(result.path).exists():
                    import shutil

                    p = Path(result.path)
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                raise DownloadCancelledError("download was cancelled")

            await DownloadRepository(session).record_attempt(
                task.id or 0, attempt_no, "success"
            )

        clear_download_cancelled(task.id)
        reset_challenge_count(task.id)
        logger.info(
            "download finished; queued for ingest",
            extra=log_extra(task_id=task.id, gid=task.gid, path=str(result.path)),
        )
    except GalleryReplacedError as exc:
        from ..download_prepare import MAX_FOLLOW_HOPS

        if follow_hops >= MAX_FOLLOW_HOPS:
            logger.warning(
                "download replacement hop limit",
                extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
            )
            try:
                async with session_cm() as session, session.begin():
                    row = await session.get(DownloadTaskModel, task.id)
                    if row is not None and row.status != "cancelled":
                        row.status = "failed"
                        row.error_message = HOPS_DETAIL
                        row.retry_count = row.max_retries
                        row.finished_at = datetime.now(UTC)
            except SQLAlchemyError:
                pass
            return
        rewritten = await _apply_replacement(task, exc)
        if rewritten is None:
            await _finalize_replacement_skip(task, exc)
            return
        await _run_download_inner(
            rewritten,
            follow_hops=follow_hops + 1,
            replaced_from_gid=replaced_from_gid or exc.old_gid,
        )
    except DownloadCancelledError:
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row is not None and row.status != "cancelled":
                    row.status = "cancelled"
                    row.finished_at = datetime.now(UTC)
        except SQLAlchemyError:
            pass
        settings = app_state.settings or get_settings()
        try:
            temp = Path(settings.download_root) / f".gv-{task.gid}"
            if temp.exists():
                import shutil

                from ..storage_usage import safe_stat_size, storage_tracker

                sz = safe_stat_size(temp)
                shutil.rmtree(temp, ignore_errors=True)
                if sz > 0:
                    storage_tracker.record_download_delta(-sz)
        except OSError:
            pass
        clear_download_cancelled(task.id)
        logger.info("download cancelled", extra=log_extra(gid=task.gid))
    except EhChallengeError as exc:
        await _apply_retry_policy(session_cm, task, exc)
    except Exception as exc:  # noqa: BLE001
        await _apply_retry_policy(session_cm, task, exc, exec_task=exec_task)
