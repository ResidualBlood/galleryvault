from __future__ import annotations

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
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
        pool_recycle=3600,
        pool_timeout=15,
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
