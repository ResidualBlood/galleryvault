"""FastAPI application factory and module-level app instance."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..db.session import create_database, create_worker_database
from ..logging import configure_logging, log_extra
from ..observability import request_id_middleware
from ..services.tasks import default_task_manager
from .core.eh_client_manager import EhClientManager
from .core.task_dispatcher import TaskDispatcher
from .exceptions import GalleryVaultError
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

try:
    from . import schemas as _schemas_mod

    _schemas_subpkg = Path(_schemas_mod.__file__).parent / "schemas"
    if hasattr(_schemas_mod, "__path__"):
        if str(_schemas_subpkg) not in _schemas_mod.__path__:
            _schemas_mod.__path__.append(str(_schemas_subpkg))
    else:
        _schemas_mod.__path__ = [str(_schemas_subpkg)]
except Exception:  # noqa: BLE001, S110
    pass


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
    app_state.worker_engine, app_state.worker_session_factory = create_worker_database(settings)
    default_task_manager.session_factory = app_state.background_session_factory
    app_state.extra["enable_workers"] = enable_workers
    app_state.extra["spawned_tasks"] = set()

    # Initialize core infrastructure components
    dispatcher = TaskDispatcher(task_manager_getter=lambda: app_state.task_manager)
    eh_manager = EhClientManager(
        client_getter=lambda: app_state.eh_client,
        settings_getter=lambda: app_state.settings,
    )
    app_state.extra["task_dispatcher"] = dispatcher
    app_state.extra["eh_client_manager"] = eh_manager

    application = FastAPI(title="GalleryVault", lifespan=lifespan)
    application.state.enable_workers = enable_workers
    application.state.task_dispatcher = dispatcher
    application.state.eh_client_manager = eh_manager

    # Register global exception handlers
    @application.exception_handler(GalleryVaultError)
    async def galleryvault_error_handler(request: Request, exc: GalleryVaultError) -> JSONResponse:
        logger.warning(
            "Application error encountered: %s",
            exc,
            extra=log_extra(error_code=exc.code, path=request.url.path, status_code=exc.status_code),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

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
