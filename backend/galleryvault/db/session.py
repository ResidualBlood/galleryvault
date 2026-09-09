from __future__ import annotations

import inspect
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import Settings

logger = logging.getLogger(__name__)


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker]:
    pool_size = getattr(settings, "database_pool_size", 20)
    max_overflow = getattr(settings, "database_max_overflow", 10)
    pool_timeout = getattr(settings, "database_pool_timeout", 15)

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=3600,
        pool_timeout=pool_timeout,
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
    "safe_transaction",
]

