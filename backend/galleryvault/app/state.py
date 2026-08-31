"""Application runtime state container."""

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
