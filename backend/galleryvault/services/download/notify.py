"""Download and archive outcome notifications plus the Telegram flush loop."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from ...app.state import app_state
from ...config import get_settings
from ...db.repository import DownloadRepository
from ...logging import log_extra
from . import wake

logger = logging.getLogger("galleryvault.services.download_worker")

_TELEGRAM_FLUSH_INTERVAL = 60.0


async def download_progress(
    task_id: int | None,
    current_page: int,
    total_pages: int,
    archive_fallback: bool | None = None,
    gid: int | None = None,
) -> None:
    session_factory = wake._get_background_session_factory()
    if task_id is None or not session_factory:
        return
    try:
        async def _persist() -> None:
            async with session_factory() as session, session.begin():
                await DownloadRepository(session).progress(
                    task_id, current_page, total_pages, archive_fallback=archive_fallback
                )

        await asyncio.wait_for(_persist(), timeout=2.0)
    except TimeoutError:
        logger.warning(
            "download progress persistence timed out, skipping [task_id=%s gid=%s]",
            task_id,
            gid,
            extra=log_extra(task_id=task_id, gid=gid),
        )
    except SQLAlchemyError as exc:
        logger.warning(
            "download progress persistence failed",
            extra=log_extra(task_id=task_id, error=type(exc).__name__),
        )


async def record_download_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    notifier = app_state.telegram
    if notifier is None:
        return
    await notifier.record_download_outcome(kind, title, detail)
    settings = app_state.settings or get_settings()
    if settings.telegram_notify_level != "summary" or not notifier.pending_events:
        return
    session_factory = wake._get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            active = await DownloadRepository(session).count_active()
        if active == 0:
            await notifier.flush_summary()
    except SQLAlchemyError as exc:
        logger.warning(
            "telegram summary flush check failed", extra=log_extra(error=type(exc).__name__)
        )


async def record_archive_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    from ..notifications import notify_archive

    notify_archive(kind, title, detail)
    notifier = app_state.telegram
    if notifier is None:
        return
    await notifier.record_archive_outcome(kind, title, detail, ring=False)
    settings = app_state.settings or get_settings()
    if (
        getattr(settings, "telegram_notify_level", "summary") != "summary"
        or not notifier.pending_archive_events
    ):
        return
    session_factory = wake._get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            active = await DownloadRepository(session).count_active()
        tm = app_state.task_manager
        archive_running = bool(tm.archive_state.get("running")) if tm else False
        if active == 0 and not archive_running:
            await notifier.flush_archive_summary()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telegram archive summary flush check failed",
            extra=log_extra(error=type(exc).__name__),
        )


async def telegram_flush_loop() -> None:
    while True:
        await asyncio.sleep(_TELEGRAM_FLUSH_INTERVAL)
        notifier = app_state.telegram
        if notifier is not None:
            try:
                if notifier.events_stale(_TELEGRAM_FLUSH_INTERVAL):
                    await notifier.flush_summary()
                if hasattr(notifier, "archive_events_stale") and notifier.archive_events_stale(
                    _TELEGRAM_FLUSH_INTERVAL
                ):
                    await notifier.flush_archive_summary()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "telegram summary flush failed",
                    extra=log_extra(error=str(exc) or type(exc).__name__),
                )

