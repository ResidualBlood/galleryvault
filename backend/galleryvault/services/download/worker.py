"""Download worker pool: claim loop, concurrency adjustment and shutdown."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from ...app.state import app_state
from ...config import get_settings
from ...db.models import DownloadTask as DownloadTaskModel
from ...db.repository import DownloadRepository
from ...logging import log_extra
from ..downloader import DownloadTask
from . import wake
from .attempt import challenge_probe_loop, retry_backoff, run_download
from .wake import notify_new_task

logger = logging.getLogger("galleryvault.services.download_worker")

_WORKER_POLL_MIN_SECONDS = 1.0
_WORKER_POLL_MAX_SECONDS = 60.0

_worker_tasks: list[asyncio.Task] = []
_target_download_concurrency: int = 2


def _idle_poll_timeout(next_retry_at: datetime | None) -> float:
    """Bounded idle wait: wake for the earliest scheduled retry, else poll."""
    if next_retry_at is None:
        return _WORKER_POLL_MAX_SECONDS
    if next_retry_at.tzinfo is None:
        # SQLite drops the timezone; retry_at is always stored as UTC.
        next_retry_at = next_retry_at.replace(tzinfo=UTC)
    remaining = (next_retry_at - datetime.now(UTC)).total_seconds()
    return min(max(remaining, _WORKER_POLL_MIN_SECONDS), _WORKER_POLL_MAX_SECONDS)


def _effective_download_concurrency(concurrency: int | None = None) -> int:
    if concurrency is None:
        settings = app_state.settings or get_settings()
        concurrency = getattr(settings, "download_concurrency", 2)
    c = max(1, int(concurrency))
    try:
        engine = app_state.engine
        if engine is not None and getattr(engine.dialect, "name", "") == "sqlite":
            c = 1
    except Exception:  # noqa: BLE001, S110
        pass
    return c


async def _download_worker() -> None:
    global _worker_tasks
    my_event = asyncio.Event()
    wake._worker_events.add(my_event)
    try:
        while True:
            my_event.clear()
            try:
                # Cooperative drain: if target concurrency decreased, exit after completing current gallery
                current_task = asyncio.current_task()
                _worker_tasks = [t for t in _worker_tasks if not t.done()]
                if current_task is not None and current_task not in _worker_tasks:
                    return
                if len(_worker_tasks) > _target_download_concurrency:
                    if current_task in _worker_tasks:
                        _worker_tasks.remove(current_task)
                    logger.info(
                        "Download worker exiting cooperatively for concurrency drain",
                        extra=log_extra(current=len(_worker_tasks), target=_target_download_concurrency),
                    )
                    return

                # Global pause: stop claiming new galleries (current page finishes)
                try:
                    _settings = app_state.settings or get_settings()
                    if getattr(_settings, "global_paused", False):
                        await asyncio.sleep(5)
                        continue
                except Exception:  # noqa: BLE001, S110
                    pass
                row = None
                poll_timeout = _WORKER_POLL_MAX_SECONDS
                session_factory = wake._get_background_session_factory()
                if not session_factory:
                    await asyncio.sleep(0.5)
                    continue
                async with session_factory() as session, session.begin():
                    repo = DownloadRepository(session)
                    row = await repo.claim_pending()
                    if row is None:
                        poll_timeout = _idle_poll_timeout(await repo.next_retry_at())
                    if row is not None:
                        task = DownloadTask(
                            row.gid,
                            row.token,
                            row.title or str(row.gid),
                            row.id,
                            row.max_retries,
                            row.mode,
                            row.category or "other",
                            max_pages=row.max_pages,
                            quality=row.quality,
                        )
                if row is not None:
                    try:
                        await run_download(task)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.exception(
                            "run_download unhandled exception",
                            extra=log_extra(task_id=task.id, gid=task.gid, error=str(exc) or type(exc).__name__),
                        )
                        if session_factory and task.id:
                            try:
                                async with session_factory() as session, session.begin():
                                    r = await session.get(DownloadTaskModel, task.id)
                                    if r and r.status not in ("cancelled", "failed"):
                                        now = datetime.now(UTC)
                                        r.retry_count += 1
                                        if r.retry_count >= r.max_retries:
                                            r.status = "failed"
                                            r.retry_at = None
                                            r.finished_at = now
                                        else:
                                            r.status = "pending"
                                            r.retry_at = now + timedelta(seconds=retry_backoff(r.retry_count))
                                        r.error_message = f"UnhandledWorkerError: {exc}"
                                        r.updated_at = now
                            except Exception:  # noqa: BLE001, S110
                                pass
                else:
                    # Bounded wait: the event only short-circuits the timeout, so
                    # a retry whose retry_at becomes due is re-claimed without any
                    # external wakeup (and with no retry scheduled we still poll
                    # at least once per _WORKER_POLL_MAX_SECONDS).
                    try:
                        await asyncio.wait_for(my_event.wait(), timeout=poll_timeout)
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "download worker iteration failed",
                    extra=log_extra(error=str(exc) or type(exc).__name__),
                )
                await asyncio.sleep(2)
    finally:
        wake._worker_events.discard(my_event)


def adjust_download_concurrency(new_concurrency: int | None = None) -> None:
    global _worker_tasks, _target_download_concurrency
    target = _effective_download_concurrency(new_concurrency)
    _target_download_concurrency = target
    # Keep the downloader's in-flight limit in sync too: it was fixed when the
    # instance was built, so extra workers used to claim a row and then block
    # on the old limit (report 01 P3-5).
    downloader = app_state.downloader
    if downloader is not None and hasattr(downloader, "set_concurrency"):
        downloader.set_concurrency(target)
    _worker_tasks = [t for t in _worker_tasks if not t.done()]
    current = len(_worker_tasks)
    if target > current:
        for _ in range(target - current):
            _worker_tasks.append(asyncio.create_task(_download_worker()))
        logger.info(
            "Adjusted download concurrency",
            extra=log_extra(previous=current, target=target, current=len(_worker_tasks)),
        )
    elif target < current:
        logger.info(
            "Set target download concurrency for cooperative drain",
            extra=log_extra(previous=current, target=target, current=len(_worker_tasks)),
        )
        notify_new_task()


async def stop_download_workers() -> None:
    """Cancel supervisor-owned download workers and wait for them to stop.

    Called on shutdown (before engines are disposed) and whenever the
    supervisor exits, so child workers never outlive their owner.
    """
    global _worker_tasks
    pending = [t for t in _worker_tasks if not t.done()]
    _worker_tasks = [t for t in _worker_tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _worker_tasks = []
    wake._worker_events.clear()


async def download_worker_loop() -> None:
    """Recover and claim persisted jobs continuously."""
    global _worker_tasks, _target_download_concurrency
    session_factory = wake._get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session, session.begin():
            await DownloadRepository(session).recover_orphans()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "download recovery failed",
            extra=log_extra(error=str(exc) or type(exc).__name__),
        )

    adjust_download_concurrency()

    probe_task = asyncio.create_task(challenge_probe_loop())

    try:
        while True:
            await asyncio.sleep(10)
            _worker_tasks = [t for t in _worker_tasks if not t.done()]
            settings = app_state.settings or get_settings()
            target = _effective_download_concurrency(settings.download_concurrency)
            _target_download_concurrency = target
            downloader = app_state.downloader
            if downloader is not None and hasattr(downloader, "set_concurrency"):
                downloader.set_concurrency(target)
            if len(_worker_tasks) < target:
                for _ in range(target - len(_worker_tasks)):
                    _worker_tasks.append(asyncio.create_task(_download_worker()))
    finally:
        # Runs on cancellation *and* on an unexpected crash of the supervisor:
        # without this, orphaned page writers keep running after engine dispose.
        probe_task.cancel()
        await asyncio.gather(probe_task, return_exceptions=True)
        await stop_download_workers()
