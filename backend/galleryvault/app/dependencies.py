"""FastAPI dependency injection providers and common helpers."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings, normalize_library_roots
from ..db.uow import UnitOfWork
from ..logging import log_extra
from .core.eh_client_manager import EhClientManager
from .core.task_dispatcher import TaskDispatcher
from .core.uow import AbstractUnitOfWork, SqlAlchemyUnitOfWork
from .state import app_state

try:
    from . import schemas as _schemas_mod

    _schemas_subpkg = Path(_schemas_mod.__file__).parent / "schemas"
    if hasattr(_schemas_mod, "__path__"):
        if str(_schemas_subpkg) not in _schemas_mod.__path__:
            _schemas_mod.__path__.append(str(_schemas_subpkg))
    else:
        _schemas_mod.__path__ = [str(_schemas_subpkg)]

    from .schemas.common import (
        BatchOperationResult,
        EntityIdResponse,
        MessageResponse,
        PageParams,
        PageResponse,
        SortDirection,
        SortParams,
        StatusResponse,
    )

    for _cls_name in (
        "BatchOperationResult",
        "EntityIdResponse",
        "MessageResponse",
        "PageParams",
        "PageResponse",
        "SortDirection",
        "SortParams",
        "StatusResponse",
    ):
        if not hasattr(_schemas_mod, _cls_name):
            setattr(_schemas_mod, _cls_name, locals()[_cls_name])
except Exception:  # noqa: BLE001, S110
    pass

if TYPE_CHECKING:
    from ..services.downloader import Downloader
    from ..services.eh_client import EhClient
    from ..services.favorite_service import FavoriteService
    from ..services.favorites import FavoritesService
    from ..services.gallery_service import GalleryService
    from ..services.library import LibraryService
    from ..services.tag_sync import TagSyncService
    from ..services.tasks import TaskManager
    from ..services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)

_LEADING_NUMBER = re.compile(r"^\s*\d+[\s\-]+")


def get_current_settings() -> Settings:
    """Return runtime settings or fallback to env settings."""
    if app_state.settings is not None:
        return app_state.settings
    return get_settings()


def get_scan_roots() -> list[str]:
    """Return normalized scan root paths derived from runtime settings."""
    s = get_current_settings()
    roots = list(s.library_roots)
    if s.download_root not in roots:
        roots.append(s.download_root)
    for ar in getattr(s, "archive_roots", []) or []:
        if ar and ar not in roots:
            roots.append(ar)
    archive_root = getattr(s, "archive_root", None)
    if archive_root and archive_root not in roots:
        roots.append(archive_root)
    if getattr(s, "cold_storage_root", None) and s.cold_storage_root not in roots:
        roots.append(s.cold_storage_root)
    return normalize_library_roots(roots)


def get_session_factory() -> Any:
    if app_state.session_factory is not None:
        return app_state.session_factory
    raise HTTPException(status_code=503, detail="Database session factory not initialized")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session for request scope."""
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


async def get_unit_of_work(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AsyncIterator[AbstractUnitOfWork]:
    """Yield a SqlAlchemyUnitOfWork managing the request's active session."""
    async with SqlAlchemyUnitOfWork(session) as uow:
        yield uow


def get_eh_client() -> EhClient:
    if app_state.eh_client is not None:
        return app_state.eh_client
    raise HTTPException(status_code=503, detail="ExHentai client is unavailable")


_default_eh_client_manager: EhClientManager | None = None


def get_eh_client_manager() -> EhClientManager:
    """Return the application's EhClientManager instance."""
    global _default_eh_client_manager
    mgr = app_state.extra.get("eh_client_manager")
    if isinstance(mgr, EhClientManager):
        return mgr
    if _default_eh_client_manager is None:
        _default_eh_client_manager = EhClientManager(
            client_getter=lambda: app_state.eh_client,
            settings_getter=get_current_settings,
        )
    return _default_eh_client_manager


async def get_leased_eh_client(
    manager: EhClientManager = Depends(get_eh_client_manager),  # noqa: B008
) -> AsyncIterator[Any]:
    """Dependency yielding an EhClient from the managed lease scope."""
    async with manager.client_context() as client:
        yield client


def get_downloader() -> Downloader:
    if app_state.downloader is not None:
        return app_state.downloader
    raise HTTPException(status_code=503, detail="Downloader is unavailable")


def get_favorites_service() -> FavoritesService:
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


_default_task_dispatcher: TaskDispatcher | None = None


def get_task_dispatcher() -> TaskDispatcher:
    """Return the application's TaskDispatcher instance."""
    global _default_task_dispatcher
    dispatcher = app_state.extra.get("task_dispatcher")
    if isinstance(dispatcher, TaskDispatcher):
        return dispatcher
    if _default_task_dispatcher is None:
        _default_task_dispatcher = TaskDispatcher(task_manager_getter=get_task_manager)
    return _default_task_dispatcher


def get_page_params(
    page: int = 1,
    page_size: int = 50,
) -> PageParams:
    """Dependency extracting pagination query parameters."""
    return PageParams(page=page, page_size=page_size)


def get_favorite_service(
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
    task_dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
    eh_client_manager: EhClientManager = Depends(get_eh_client_manager),  # noqa: B008
) -> FavoriteService:
    """Dependency providing a configured FavoriteService."""
    from ..services.favorite_service import FavoriteService

    return FavoriteService(
        uow=uow,
        task_dispatcher=task_dispatcher,
        eh_client_manager=eh_client_manager,
    )


def get_gallery_service(
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
    task_dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
    eh_client_manager: EhClientManager = Depends(get_eh_client_manager),  # noqa: B008
) -> GalleryService:
    """Dependency providing a configured GalleryService."""
    from ..services.gallery_service import GalleryService

    svc = GalleryService(uow=uow, task_dispatcher=task_dispatcher)
    svc.eh_client_manager = eh_client_manager
    return svc


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
    mode = (getattr(settings, "title_display", "japanese") or "japanese").lower()
    t = title or ""
    tj = title_jpn or ""
    d = directory or ""
    if mode == "english":
        candidates = [t, tj, d]
    elif mode == "directory":
        candidates = [d, tj, t]
    else:
        candidates = [tj, t, d]

    for cand in candidates:
        raw = cand.strip()
        if not raw or raw.isdigit():
            continue
        raw = html.unescape(raw)
        stripped = _LEADING_NUMBER.sub("", raw).lstrip("-").strip()
        if stripped and not stripped.isdigit():
            return stripped
    return ""


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


from fastapi.params import Depends as DependsType


class _ManagedSessionWrapper:
    """Wraps an AsyncSession obtained from an async generator, ensuring aclose() on completion or GC."""

    def __init__(self, session: Any, gen: AsyncIterator[Any] | None = None) -> None:
        self._session = session
        self._gen = gen
        self._closed = False
        try:
            task = asyncio.current_task()
            if task is not None:
                task.add_done_callback(lambda _t: self._schedule_close())
        except RuntimeError:
            pass

    def _schedule_close(self) -> None:
        if self._closed or self._gen is None:
            return
        self._closed = True
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._gen.aclose())
        except RuntimeError:
            pass

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self._session, "aclose"):
                await self._session.aclose()
            elif hasattr(self._session, "close"):
                res = self._session.close()
                if hasattr(res, "__await__"):
                    await res
        finally:
            if self._gen is not None:
                await self._gen.aclose()

    async def close(self) -> None:
        await self.aclose()

    async def __aenter__(self) -> Any:
        if hasattr(self._session, "__aenter__"):
            return await self._session.__aenter__()
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Any:
        try:
            if hasattr(self._session, "__aexit__"):
                return await self._session.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            await self.aclose()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    @property
    def __class__(self) -> Any:  # type: ignore[override]
        return self._session.__class__

    def __del__(self) -> None:
        self._schedule_close()


async def resolve_session(session: Any, fallback_dep: Any = None) -> AsyncSession:
    """Resolve session parameter if endpoint was called directly in tests without FastAPI DI."""
    if not isinstance(session, DependsType) and session is not None:
        return session
    dep = fallback_dep or getattr(session, "dependency", None) or get_session
    gen = dep()
    if hasattr(gen, "__anext__"):
        try:
            raw_session = await gen.__anext__()
        except StopAsyncIteration:
            raise HTTPException(status_code=503, detail="Database session factory not initialized")
        return _ManagedSessionWrapper(raw_session, gen=gen)  # type: ignore[return-value]
    elif hasattr(gen, "__await__"):
        return await gen
    elif callable(gen):
        return gen()
    return session


__all__ = [
    "AbstractUnitOfWork",
    "BatchOperationResult",
    "EhClientManager",
    "EntityIdResponse",
    "MessageResponse",
    "PageParams",
    "PageResponse",
    "SortDirection",
    "SortParams",
    "SqlAlchemyUnitOfWork",
    "StatusResponse",
    "TaskDispatcher",
    "UnitOfWork",
    "db_error",
    "display_title",
    "get_current_settings",
    "get_downloader",
    "get_eh_client",
    "get_eh_client_manager",
    "get_favorite_service",
    "get_favorites_service",
    "get_gallery_service",
    "get_leased_eh_client",
    "get_library_service",
    "get_page_params",
    "get_scan_roots",
    "get_session",
    "get_session_factory",
    "get_tag_service",
    "get_task_dispatcher",
    "get_task_manager",
    "get_thumbnail_service",
    "get_unit_of_work",
    "get_uow",
    "image_content_type",
    "resolve_display_title",
    "resolve_session",
    "spawn_task",
]
