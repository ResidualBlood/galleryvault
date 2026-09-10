"""Application runtime state container and service factory."""

from __future__ import annotations

import asyncio
import contextlib
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
        """Return the background session factory, falling back to session_factory if absent."""
        if self.worker_session_factory is not None:
            if self.worker_engine is not None:
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    current_loop = None

                if current_loop is not None:
                    engine_loop = self._worker_bound_loop
                    if engine_loop is not None and (engine_loop is not current_loop or engine_loop.is_closed()):
                        with contextlib.suppress(Exception):
                            self.worker_engine.sync_engine.dispose()
                        return self.session_factory  # type: ignore[return-value]
                    if engine_loop is None:
                        self._worker_bound_loop = current_loop
            return self.worker_session_factory  # type: ignore[return-value]
        return self.session_factory  # type: ignore[return-value]

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
