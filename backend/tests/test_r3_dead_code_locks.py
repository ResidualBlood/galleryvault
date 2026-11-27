"""R3 cleanup: dead download retry-sweep helpers and import-time asyncio primitives."""

from __future__ import annotations

import asyncio

from galleryvault.db.repositories.downloads import DownloadRepository
from galleryvault.services import integrity_worker, scan_worker


def test_failed_retry_sweep_helpers_removed() -> None:
    """Failed tasks are no longer auto-rescanned, so the helpers must be gone."""
    assert not hasattr(DownloadRepository, "rearm_failed")
    assert not hasattr(DownloadRepository, "sweep_auto_retry")


def test_no_import_time_locks() -> None:
    assert not hasattr(scan_worker, "scan_lock")
    assert not hasattr(integrity_worker, "integrity_scan_lock")


def _lock_after_contention(get_lock):
    """Acquire ``get_lock()`` on a fresh loop with a real waiter, then release."""

    async def _main():
        lock = get_lock()

        async def _waiter() -> None:
            async with lock:
                await asyncio.sleep(0)

        task = asyncio.create_task(_waiter())
        async with lock:
            await asyncio.sleep(0)
        await task
        return lock

    return asyncio.run(_main())


def test_scan_lock_survives_new_event_loop() -> None:
    """A different loop must get its own lock instead of raising RuntimeError."""
    first = _lock_after_contention(scan_worker._get_scan_lock)
    second = _lock_after_contention(scan_worker._get_scan_lock)
    assert first is not second


def test_integrity_lock_survives_new_event_loop() -> None:
    first = _lock_after_contention(integrity_worker._get_integrity_scan_lock)
    second = _lock_after_contention(integrity_worker._get_integrity_scan_lock)
    assert first is not second


def test_locks_are_stable_within_one_loop() -> None:
    async def _main() -> None:
        assert scan_worker._get_scan_lock() is scan_worker._get_scan_lock()
        assert integrity_worker._get_integrity_scan_lock() is (
            integrity_worker._get_integrity_scan_lock()
        )

    asyncio.run(_main())
