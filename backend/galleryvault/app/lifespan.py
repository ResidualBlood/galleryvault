"""Lifespan, startup preparation, and background worker lifecycle management."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..db.models import DownloadTask as DownloadTaskModel
from ..logging import log_extra

logger = logging.getLogger(__name__)


async def warmup_database_pool(session_factory: Any) -> None:
    """Warm up the async engine connection pool."""
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            await session.execute(select(1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("database pool warmup failed", extra=log_extra(error=type(exc).__name__))


async def cleanup_partial_downloads(download_root: str | Path, session_factory: Any) -> None:
    """Sweep temporary partial download folders (.gv-*) that are no longer active."""
    try:
        keep_gids: set[int] = set()
        if session_factory:
            try:
                async with session_factory() as session:
                    rows = await session.execute(
                        select(DownloadTaskModel.gid).where(
                            DownloadTaskModel.status.in_(["pending", "downloading"])
                        )
                    )
                    keep_gids = {int(row[0]) for row in rows}
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "could not read active downloads for temp sweep",
                    extra=log_extra(error=type(exc).__name__),
                )
        root = Path(download_root)
        if not root.exists():
            return
        for child in root.glob(".gv-*"):
            gid_text = child.name[len(".gv-") :] if child.name.startswith(".gv-") else ""
            if gid_text.isdigit() and int(gid_text) in keep_gids:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("partial download cleanup failed", extra=log_extra(error=type(exc).__name__))


async def stop_background_tasks(
    spawned_tasks: set[asyncio.Task] | None = None,
    specific_tasks: list[asyncio.Task | None] | None = None,
) -> None:
    """Gracefully cancel and await background tasks during shutdown."""
    tasks_to_cancel: set[asyncio.Task] = set(spawned_tasks or set())
    for t in specific_tasks or []:
        if t is not None:
            tasks_to_cancel.add(t)
    for task in list(tasks_to_cancel):
        task.cancel()
    for task in list(tasks_to_cancel):
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


def hydrate_startup_logs(max_lines: int = 500) -> None:
    """Hydrate memory ring buffer from historical log files during startup."""
    try:
        from ..logging import hydrate_recent_logs

        hydrate_recent_logs(max_lines=max_lines)
    except Exception as exc:
        logger.debug("startup log hydration skipped", exc_info=exc)
