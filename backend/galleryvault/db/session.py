from __future__ import annotations

import inspect
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import Settings
from ..logging import log_extra

logger = logging.getLogger(__name__)


def _server_settings(
    statement_timeout_ms: int,
    lock_timeout_ms: int,
    idle_in_tx_timeout_ms: int,
) -> dict[str, str]:
    """Build asyncpg ``server_settings`` for the connection-level timeouts.

    asyncpg sends startup parameters as text; PostgreSQL treats ``0`` as
    "disabled" for all three GUCs.
    """
    return {
        "statement_timeout": str(int(statement_timeout_ms)),
        "lock_timeout": str(int(lock_timeout_ms)),
        "idle_in_transaction_session_timeout": str(int(idle_in_tx_timeout_ms)),
    }


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker]:
    # Defaults live in ``Settings`` so the env surface and the engine agree.
    pool_size = settings.database_pool_size
    max_overflow = settings.database_max_overflow
    pool_timeout = settings.database_pool_timeout

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=3600,
        pool_timeout=pool_timeout,
        connect_args={
            "server_settings": _server_settings(
                settings.database_statement_timeout_ms,
                settings.database_lock_timeout_ms,
                settings.database_idle_in_tx_timeout_ms,
            )
        },
    )

    raw_pool = getattr(engine.sync_engine, "pool", None)
    if raw_pool is not None:

        @event.listens_for(raw_pool, "checkout")
        def _on_checkout(dbapi_con, con_record, con_proxy):
            con_record.info["checkout_time"] = time.monotonic()

        @event.listens_for(raw_pool, "checkin")
        def _on_checkin(dbapi_con, con_record):
            start = con_record.info.pop("checkout_time", None)
            if start is not None:
                duration = time.monotonic() - start
                if duration > 5.0:
                    logger.warning(
                        "DB connection held longer than expected: %.2fs (risk of pool exhaustion)",
                        duration,
                    )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


def create_worker_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker]:
    """Create a dedicated database engine and session factory for background workers.

    Uses a separate smaller connection pool (default pool_size=5, max_overflow=5)
    to ensure background jobs and scans cannot exhaust the Web API connection
    pool.  Its statement budget is unlimited by default: full scans, integrity
    passes and archive extraction legitimately run long, while lock waits stay
    bounded and idle transactions are still reaped.
    """
    pool_size = settings.worker_database_pool_size
    max_overflow = settings.worker_database_max_overflow
    pool_timeout = settings.worker_database_pool_timeout

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=3600,
        pool_timeout=pool_timeout,
        connect_args={
            "server_settings": _server_settings(
                settings.worker_database_statement_timeout_ms,
                settings.worker_database_lock_timeout_ms,
                settings.worker_database_idle_in_tx_timeout_ms,
            )
        },
    )

    raw_pool = getattr(engine.sync_engine, "pool", None)
    if raw_pool is not None:

        @event.listens_for(raw_pool, "checkout")
        def _on_worker_checkout(dbapi_con, con_record, con_proxy):
            con_record.info["worker_checkout_time"] = time.monotonic()

        @event.listens_for(raw_pool, "checkin")
        def _on_worker_checkin(dbapi_con, con_record):
            start = con_record.info.pop("worker_checkout_time", None)
            if start is not None:
                duration = time.monotonic() - start
                if duration > 15.0:
                    logger.warning(
                        "Worker DB connection held longer than expected: %.2fs (risk of worker pool exhaustion)",
                        duration,
                    )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


async def release_session(session: Any) -> None:
    """End any open transaction so the pooled connection goes back to the pool.

    FastAPI only tears ``yield`` dependencies down after the response has been
    sent, so endpoints that return a ``StreamingResponse``/``FileResponse`` (or
    that do long network I/O) would keep a request-level connection checked out
    for the whole transfer.  Ending the read transaction before returning hands
    the connection back; the session stays usable and the next statement starts
    a fresh transaction.
    """
    rollback = getattr(session, "rollback", None)
    if rollback is None:
        return
    try:
        result = rollback()
        if result is not None and hasattr(result, "__await__"):
            await result
    except Exception as exc:  # noqa: BLE001
        logger.debug("session release failed", extra=log_extra(error=type(exc).__name__))


@asynccontextmanager
async def safe_transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Safely enter a transaction block without nested begin() errors.

    If session.in_transaction() is True (e.g. prior SELECT triggered autobegin),
    yields the session and commits on clean exit or rolls back on exception.
    If session.in_transaction() is False, delegates to `async with session.begin()`.
    Defensively handles test fake sessions lacking in_transaction or context managers.
    """
    in_tx = False
    in_tx_fn = getattr(session, "in_transaction", None)
    if callable(in_tx_fn):
        in_tx = in_tx_fn()

    if in_tx:
        try:
            yield session
            commit_fn = getattr(session, "commit", None)
            if callable(commit_fn):
                res = commit_fn()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            rollback_fn = getattr(session, "rollback", None)
            if callable(rollback_fn):
                res = rollback_fn()
                if inspect.isawaitable(res):
                    await res
            raise
    else:
        begin_fn = getattr(session, "begin", None)
        if callable(begin_fn):
            begin_ctx = begin_fn()
            if hasattr(begin_ctx, "__aenter__") and hasattr(begin_ctx, "__aexit__"):
                async with begin_ctx:
                    yield session
                return
            if hasattr(begin_ctx, "__enter__") and hasattr(begin_ctx, "__exit__"):
                with begin_ctx:
                    yield session
                return
        try:
            yield session
            commit_fn = getattr(session, "commit", None)
            if callable(commit_fn):
                res = commit_fn()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            rollback_fn = getattr(session, "rollback", None)
            if callable(rollback_fn):
                res = rollback_fn()
                if inspect.isawaitable(res):
                    await res
            raise


@asynccontextmanager
async def brief_session(
    session_factory: async_sessionmaker[AsyncSession],
    timeout: float = 5.0,
) -> AsyncIterator[AsyncSession]:
    """Provide a session context that logs if held longer than timeout."""
    async with session_factory() as session:
        t0 = time.monotonic()
        try:
            yield session
        finally:
            elapsed = time.monotonic() - t0
            if elapsed > timeout:
                logger.warning(
                    "brief_session held for %.2fs (warning threshold %.1fs)",
                    elapsed,
                    timeout,
                )


__all__ = [
    "brief_session",
    "create_database",
    "create_worker_database",
    "release_session",
    "safe_transaction",
]

