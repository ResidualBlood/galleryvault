"""FastAPI dependency injection providers and common helpers."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db.uow import UnitOfWork
from ..logging import log_extra
from .state import app_state

if TYPE_CHECKING:
    from ..services.downloader import Downloader
    from ..services.eh_client import EhClient
    from ..services.favorites import FavoritesService
    from ..services.library import LibraryService
    from ..services.tag_sync import TagSyncService
    from ..services.tasks import TaskManager
    from ..services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)

_LEADING_NUMBER = re.compile(r"^\s*\d+[\s\-]+")


def get_current_settings() -> Settings:
    """Return runtime settings or fallback to env settings."""
    from . import main
    if hasattr(main, "_settings"):
        try:
            return main._settings()
        except Exception:  # noqa: S110, BLE001
            pass
    if hasattr(main, "app") and hasattr(main.app, "state") and getattr(main.app.state, "settings", None) is not None:
        return main.app.state.settings
    if app_state.settings is not None:
        return app_state.settings
    return get_settings()


def get_session_factory() -> Any:
    from . import main
    session_cm = getattr(main, "_settings_session", None)
    if session_cm is not None:
        return session_cm
    if app_state.session_factory is not None:
        return app_state.session_factory
    raise HTTPException(status_code=503, detail="Database session factory not initialized")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session for request scope."""
    from . import main
    session_cm = getattr(main, "_settings_session", None)
    if session_cm is not None:
        async with session_cm() as session:
            yield session
            return
    if app_state.session_factory:
        async with app_state.session_factory() as session:
            yield session
            return
    raise HTTPException(status_code=503, detail="Database session factory not initialized")


async def get_uow(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AsyncIterator[UnitOfWork]:
    """Yield a UnitOfWork wrapper over the active session."""
    async with UnitOfWork(session) as uow:
        yield uow


def get_eh_client() -> EhClient:
    from . import main
    state = getattr(getattr(main, "app", None), "state", None)
    if state and getattr(state, "eh_client", None) is not None:
        return state.eh_client
    if app_state.eh_client is not None:
        return app_state.eh_client
    raise HTTPException(status_code=503, detail="ExHentai client is unavailable")


def get_downloader() -> Downloader:
    from . import main
    state = getattr(getattr(main, "app", None), "state", None)
    if state and getattr(state, "downloader", None) is not None:
        return state.downloader
    if app_state.downloader is not None:
        return app_state.downloader
    raise HTTPException(status_code=503, detail="Downloader is unavailable")


def get_favorites_service() -> FavoritesService:
    from . import main
    state = getattr(getattr(main, "app", None), "state", None)
    if state and getattr(state, "favorites_service", None) is not None:
        return state.favorites_service
    if app_state.favorites_service is not None:
        return app_state.favorites_service
    raise HTTPException(status_code=503, detail="Favorites service is unavailable")


def get_library_service() -> LibraryService:
    if app_state.library_service is None:
        raise HTTPException(status_code=503, detail="Library service is not initialized")
    return app_state.library_service


def get_tag_service() -> TagSyncService:
    if app_state.tag_service is None:
        raise HTTPException(status_code=503, detail="Tag service is not initialized")
    return app_state.tag_service


def get_thumbnail_service() -> ThumbnailService:
    if app_state.thumbnail_service is None:
        raise HTTPException(status_code=503, detail="Thumbnail service is not initialized")
    return app_state.thumbnail_service


def get_task_manager() -> TaskManager:
    if app_state.task_manager is None:
        from ..services.tasks import default_task_manager
        return default_task_manager
    return app_state.task_manager


def db_error(exc: Exception) -> HTTPException:
    logger.error("database operation failed", extra=log_extra(error=type(exc).__name__))
    return HTTPException(status_code=503, detail="Database is unavailable")


def resolve_display_title(
    title: str | None,
    title_jpn: str | None,
    directory: str = "",
) -> str:
    """Resolve a display title according to title_display setting preference."""
    settings = get_current_settings()
    mode = (settings.title_display or "japanese").lower()
    title = title or ""
    title_jpn = title_jpn or ""
    if mode == "english":
        source = title or title_jpn or directory
    elif mode == "directory":
        source = directory or title_jpn or title
    else:
        source = title_jpn or title or directory
    if not source:
        source = title or title_jpn or directory
    stripped = _LEADING_NUMBER.sub("", source).lstrip("-").strip()
    return stripped or source


def display_title(gallery: Any) -> str:
    """Resolve the gallery title shown in the UI from the configured preference."""
    storage_path = getattr(gallery, "storage_path", "") or ""
    directory = Path(storage_path).name if storage_path else ""
    return resolve_display_title(
        getattr(gallery, "title", None),
        getattr(gallery, "title_jpn", None),
        directory=directory,
    )


def image_content_type(data: bytes) -> str:
    """Infer HTTP image Content-Type header from raw magic bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF89a", b"GIF87a"):
        return "image/gif"
    return "application/octet-stream"


def spawn_task(coroutine: Any, operation: str) -> asyncio.Task | None:
    """Safely spawn a fire-and-forget background coroutine with error logging."""
    async def guarded() -> None:
        try:
            await coroutine
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "background task failed",
                extra=log_extra(operation=operation, error=type(exc).__name__),
            )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        if hasattr(coroutine, "close"):
            coroutine.close()
        return None

    task = loop.create_task(guarded())
    spawned = app_state.extra.get("spawned_tasks")
    if isinstance(spawned, set):
        spawned.add(task)
        task.add_done_callback(spawned.discard)
    return task
