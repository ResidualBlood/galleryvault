"""FastAPI application factory and module-level app instance."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI

from ..config import Settings, get_settings
from ..db.session import create_database
from ..logging import configure_logging
from ..observability import request_id_middleware
from ..services.tasks import default_task_manager
from .lifespan import lifespan
from .middleware import auth_and_csrf_middleware
from .routers import (
    auth,
    core,
    downloads,
    duplicates,
    eh,
    favorites,
    galleries,
    lists,
    notifications,
    opds,
    series,
    tags,
    tasks,
    updates,
)
from .routers import settings as settings_router
from .state import app_state, sync_state


def _configure_logging(settings: Settings) -> None:
    log_file = settings.log_file or (
        str(Path(settings.thumbnail_cache_dir).parent / "logs" / "galleryvault.log")
        if settings.thumbnail_cache_dir
        else None
    )
    configure_logging(
        settings.log_level,
        settings.log_json,
        log_file=log_file,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
    )


def create_app(*, enable_workers: bool | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if enable_workers is None:
        enable_workers = os.environ.get("GALLERYVAULT_ENABLE_WORKERS", "1") != "0"

    app_state.settings = settings
    app_state.task_manager = default_task_manager
    app_state.engine, app_state.session_factory = create_database(settings)
    default_task_manager.session_factory = app_state.session_factory
    app_state.extra["enable_workers"] = enable_workers
    app_state.extra["spawned_tasks"] = set()

    application = FastAPI(title="GalleryVault", lifespan=lifespan)
    application.state.enable_workers = enable_workers
    application.middleware("http")(auth_and_csrf_middleware)
    application.middleware("http")(request_id_middleware)
    for mod in (
        core,
        auth,
        galleries,
        downloads,
        settings_router,
        favorites,
        tags,
        tasks,
        duplicates,
        updates,
        eh,
        notifications,
        lists,
        opds,
        series,
    ):
        application.include_router(mod.router)
    sync_state(application)
    return application


_configure_logging(get_settings())
logger = logging.getLogger(__name__)
app = create_app()
