"""Application runtime state container and service factory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
    downloader: Downloader | None = None
    favorites_service: FavoritesService | None = None
    eh_client: EhClient | None = None
    telegram: TelegramNotifier | None = None
    library_service: LibraryService | None = None
    tag_service: TagSyncService | None = None
    thumbnail_service: ThumbnailService | None = None
    task_manager: TaskManager = default_task_manager
    extra: dict[str, Any] = field(default_factory=dict)


# Global singleton app state reference
app_state = AppState(task_manager=default_task_manager)


def sync_state(app: Any = None) -> None:
    """Mirror app_state -> app.state for middleware / debug inspection."""
    if app is None:
        try:
            from .main import app as main_app

            app = main_app
        except ImportError:
            return
    if not hasattr(app, "state"):
        return

    for attr in (
        "settings",
        "engine",
        "session_factory",
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
