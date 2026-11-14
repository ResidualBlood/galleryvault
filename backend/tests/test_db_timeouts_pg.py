"""T6.2: real PostgreSQL applies the configured connection-level timeouts.

Each test builds the production engines through ``create_database`` /
``create_worker_database`` and asks PostgreSQL for the effective GUCs, so a
regression in ``connect_args`` shows up here even when the DB-free test still
passes.  Skipped on the host (no PostgreSQL), required (0 skipped) in the test
container.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from galleryvault.config import Settings
from galleryvault.db.session import create_database, create_worker_database


async def _show(engine, name: str) -> str:
    async with engine.connect() as conn:
        value = await conn.scalar(text(f"SHOW {name}"))
    return str(value)


async def _probe(engine) -> None:
    """Skip the whole test when PostgreSQL is unreachable (host runs)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"Database connection unavailable: {exc}")


@pytest.mark.asyncio
async def test_api_engine_effective_timeouts() -> None:
    engine, _ = create_database(Settings())
    await _probe(engine)
    try:
        assert await _show(engine, "statement_timeout") == "30s"
        assert await _show(engine, "lock_timeout") == "5s"
        assert await _show(engine, "idle_in_transaction_session_timeout") == "1min"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_engine_effective_timeouts() -> None:
    engine, _ = create_worker_database(Settings())
    await _probe(engine)
    try:
        # 0 = disabled: long queued scans/integrity passes are the worker's job.
        assert await _show(engine, "statement_timeout") == "0"
        assert await _show(engine, "lock_timeout") == "10s"
        assert await _show(engine, "idle_in_transaction_session_timeout") == "5min"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_statement_timeout_actually_cancels_a_long_statement() -> None:
    settings = Settings(database_statement_timeout_ms=200)
    engine, _ = create_database(settings)
    await _probe(engine)
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError) as excinfo:
                await conn.execute(text("SELECT pg_sleep(2)"))
            assert "statement timeout" in str(excinfo.value)
    finally:
        await engine.dispose()
