"""Tests for app/lifespan.py helper routines and worker lifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path

from galleryvault.app.lifespan import (
    cleanup_partial_downloads,
    warmup_database_pool,
)
from galleryvault.app.workers import WorkerRegistry
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


async def test_registry_shutdown_cancels_workers() -> None:
    registry = WorkerRegistry()
    started = asyncio.Event()

    async def _dummy() -> None:
        started.set()
        await asyncio.sleep(100)

    registry.register("dummy", _dummy)
    task = registry.start("dummy")
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)
    await registry.shutdown(timeout=1)
    assert task.done()


def test_exhentai_chunk_size_constant() -> None:
    assert EXHENTAI_API_CHUNK_SIZE == 25
