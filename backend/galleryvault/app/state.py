"""Application runtime state container and service factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from ..config import Settings
    from ..services.downloader import Downloader
    from ..services.eh_client import EhClient
    from ..services.favorites import FavoritesService
    from ..services.library import LibraryService
    from ..services.tag_sync import TagSyncService
    from ..services.tasks import TaskManager
    from ..services.telegram import TelegramNotifier
    from ..services.thumbnails import ThumbnailService


from ..services.tasks import default_task_manager

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Central container holding singleton services and configuration."""

    settings: Settings | None = None
    engine: AsyncEngine | None = None
    session_factory: Callable[[], AsyncSession] | None = None
    worker_engine: AsyncEngine | None = None
    worker_session_factory: Callable[[], AsyncSession] | None = None
    _worker_bound_loop: Any = None
    downloader: Downloader | None = None
    favorites_service: FavoritesService | None = None
    eh_client: EhClient | None = None
    telegram: TelegramNotifier | None = None
    library_service: LibraryService | None = None
    tag_service: TagSyncService | None = None
    thumbnail_service: ThumbnailService | None = None
    task_manager: TaskManager = default_task_manager
    cross_gid_duplicates: list[dict[str, Any]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def background_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the background session factory, (re)bound to the running loop.

        The worker engine is created outside any loop (``main.py``/``startup``),
        so the first access binds it to the then-current loop. If it is later
        used from another (or a closed) loop it must be rebuilt; falling back to
        the API pool permanently defeated the whole point of worker isolation
        (report 01 P2-6). A rebuild failure still falls back to the API pool, but
        is logged and not sticky: the next access retries the rebuild.
        """
        if self.worker_session_factory is None:
            return self.session_factory  # type: ignore[return-value]
        if self.worker_engine is None:
            return self.worker_session_factory  # type: ignore[return-value]

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return self.worker_session_factory  # type: ignore[return-value]

        engine_loop = self._worker_bound_loop
        if engine_loop is not None and (engine_loop is not current_loop or engine_loop.is_closed()):
            rebuilt = self._rebuild_worker_engine(current_loop)
            if rebuilt is not None:
                return rebuilt
            return self.session_factory  # type: ignore[return-value]
        if engine_loop is None:
            self._worker_bound_loop = current_loop
        return self.worker_session_factory  # type: ignore[return-value]

    def _rebuild_worker_engine(
        self, loop: asyncio.AbstractEventLoop
    ) -> async_sessionmaker[AsyncSession] | None:
        """Recreate the worker engine for ``loop``; returns None when impossible."""
        settings = self.settings
        if settings is None:
            logger.warning(
                "worker database engine bound to another event loop and settings are "
                "unavailable; falling back to the API pool for this call"
            )
            return None
        old_engine = self.worker_engine
        try:
            from ..db.session import create_worker_database

            engine, factory = create_worker_database(settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to rebuild worker database engine; falling back to the API pool "
                "for this call",
                extra={"error": type(exc).__name__, "detail": str(exc)},
            )
            return None
        self.worker_engine = engine
        self.worker_session_factory = factory
        self._worker_bound_loop = loop
        if old_engine is not None:
            with contextlib.suppress(Exception):
                old_engine.sync_engine.dispose()
        logger.warning(
            "worker database engine was bound to another event loop; rebuilt for the "
            "current loop",
        )
        return factory

    def reset(self) -> None:
        """Reset internal state containers and dispose engine pools if open."""
        if self.worker_engine is not None:
            with contextlib.suppress(Exception):
                self.worker_engine.sync_engine.dispose()
        self.worker_engine = None
        self.worker_session_factory = None
        self._worker_bound_loop = None
        if self.engine is not None:
            with contextlib.suppress(Exception):
                self.engine.sync_engine.dispose()
        self.engine = None
        self.session_factory = None
        self.settings = None
        self.downloader = None
        self.favorites_service = None
        self.eh_client = None
        self.telegram = None
        self.library_service = None
        self.tag_service = None
        self.thumbnail_service = None
        self.cross_gid_duplicates = None
        self.extra.clear()


# Global singleton app state reference
app_state = AppState(task_manager=default_task_manager)


def sync_state(app: Any = None) -> None:
    """Mirror app_state -> app.state for middleware / debug inspection."""
    if app is not None:
        app_state.extra["app"] = app
    else:
        app = app_state.extra.get("app")

    if app is None or not hasattr(app, "state"):
        return

    for attr in (
        "settings",
        "engine",
        "session_factory",
        "worker_engine",
        "worker_session_factory",
        "eh_client",
        "downloader",
        "telegram",
        "favorites_service",
        "library_service",
        "tag_service",
        "thumbnail_service",
        "task_manager",
    ):
        val = getattr(app_state, attr, None)
        if val is not None or not hasattr(app.state, attr):
            setattr(app.state, attr, val)

    spawned = app_state.extra.get("spawned_tasks")
    if spawned is None or not isinstance(spawned, set):
        spawned = set()
        app_state.extra["spawned_tasks"] = spawned
    app.state.spawned_tasks = spawned
    if "enable_workers" in app_state.extra:
        app.state.enable_workers = app_state.extra["enable_workers"]
    if "telegram_bot_task" in app_state.extra:
        app.state.telegram_bot_task = app_state.extra["telegram_bot_task"]


def create_services(settings_obj: Settings) -> dict[str, object]:
    """Instantiate core services directly from their source classes."""
    from ..config import normalize_library_roots
    from ..services.downloader import Downloader
    from ..services.eh_client import EhClient
    from ..services.favorites import FavoritesService
    from ..services.favorites_worker import FavoriteDownloadQueue, FavoritesRepositoryProxy
    from ..services.library import LibraryService
    from ..services.telegram import TelegramNotifier
    from ..services.thumbnails import ThumbnailService

    client = EhClient(settings_obj, max_concurrency=settings_obj.exhentai_max_concurrency)
    downloader = Downloader(
        client,
        settings_obj.download_root,
        concurrency=settings_obj.download_concurrency,
        page_concurrency=settings_obj.page_concurrency,
    )
    telegram = TelegramNotifier(settings_obj)
    favorites_service = FavoritesService(
        client, FavoritesRepositoryProxy(), FavoriteDownloadQueue(), telegram
    )
    roots = list(settings_obj.library_roots)
    if settings_obj.download_root not in roots:
        roots.append(settings_obj.download_root)
    library_service = LibraryService(normalize_library_roots(roots))
    thumbnail_service = ThumbnailService(settings_obj.thumbnail_cache_dir)
    return {
        "eh_client": client,
        "downloader": downloader,
        "telegram": telegram,
        "favorites_service": favorites_service,
        "library_service": library_service,
        "thumbnail_service": thumbnail_service,
    }
