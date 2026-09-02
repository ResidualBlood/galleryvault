"""Tests for app/lifespan.py helper routines and worker lifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path

from galleryvault.app.lifespan import (
    cleanup_partial_downloads,
    stop_background_tasks,
    warmup_database_pool,
)
from galleryvault.services.eh_client import EXHENTAI_API_CHUNK_SIZE


async def test_warmup_database_pool_success() -> None:
    executed = []

    class MockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def execute(self, stmt):
            executed.append(stmt)

    await warmup_database_pool(lambda: MockSession())
    assert len(executed) == 1


async def test_warmup_database_pool_none_or_failing() -> None:
    # Should not raise when session_factory is None
    await warmup_database_pool(None)

    class FailingSession:
        async def __aenter__(self):
            raise RuntimeError("db connection failed")

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    # Should gracefully catch and log warning without raising
    await warmup_database_pool(lambda: FailingSession())


async def test_cleanup_partial_downloads(tmp_path: Path) -> None:
    # Setup test directory
    active_dir = tmp_path / ".gv-123"
    inactive_dir = tmp_path / ".gv-456"
    other_file = tmp_path / "normal_file.txt"

    active_dir.mkdir()
    inactive_dir.mkdir()
    other_file.write_text("hello")

    class MockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def execute(self, stmt):
            # 123 is currently downloading
            return [(123,)]

    await cleanup_partial_downloads(tmp_path, lambda: MockSession())

    # Active download directory and normal files should remain; inactive should be removed
    assert active_dir.exists()
    assert not inactive_dir.exists()
    assert other_file.exists()


async def test_stop_background_tasks() -> None:
    loop = asyncio.get_running_loop()

    async def _dummy():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            pass

    t1 = loop.create_task(_dummy())
    t2 = loop.create_task(_dummy())
    t3 = loop.create_task(_dummy())

    spawned = {t1, t2}
    specific = [t3, None]

    await stop_background_tasks(spawned, specific)

    assert t1.cancelled() or t1.done()
    assert t2.cancelled() or t2.done()
    assert t3.cancelled() or t3.done()


def test_exhentai_chunk_size_constant() -> None:
    assert EXHENTAI_API_CHUNK_SIZE == 25
