"""T8.5: supervised worker registry and bounded shutdown."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from galleryvault.app.workers import WorkerRegistry


async def test_always_worker_restarts_after_normal_return(caplog: pytest.LogCaptureFixture) -> None:
    """A long-lived loop that returns must be restarted and warned about."""
    caplog.set_level(logging.WARNING)
    registry = WorkerRegistry()
    calls = 0
    restarted = asyncio.Event()
    blocker = asyncio.Event()

    async def factory() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        restarted.set()
        await blocker.wait()

    registry.register(
        "always_worker",
        factory,
        restart_policy="always",
        initial_delay=0,
        max_delay=0,
    )
    task = registry.start("always_worker")
    assert task is not None

    await asyncio.wait_for(restarted.wait(), timeout=1)
    assert calls == 2, "a normally returned always-worker must be restarted"
    assert "returned unexpectedly" in caplog.text

    blocker.set()
    await registry.shutdown(timeout=1)


async def test_favorites_poll_restarts_after_exception(caplog: pytest.LogCaptureFixture) -> None:
    """A crashed favorites poll loop must not stay permanently stopped."""
    caplog.set_level(logging.WARNING)
    registry = WorkerRegistry()
    calls = 0
    restarted = asyncio.Event()
    blocker = asyncio.Event()

    async def factory() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("poll exploded")
        restarted.set()
        await blocker.wait()

    registry.register(
        "favorites_poll",
        factory,
        restart_policy="always",
        initial_delay=0,
        max_delay=0,
    )
    task = registry.start("favorites_poll")
    assert task is not None

    await asyncio.wait_for(restarted.wait(), timeout=1)
    assert calls == 2, "a crashed always-worker must be restarted"
    assert "crashed; restarting with backoff" in caplog.text

    blocker.set()
    await registry.shutdown(timeout=1)


async def test_once_worker_is_not_restarted() -> None:
    registry = WorkerRegistry()
    calls = 0

    async def factory() -> None:
        nonlocal calls
        calls += 1

    registry.register("one_shot", factory, restart_policy="once")
    task = registry.start("one_shot")
    assert task is not None

    await asyncio.wait_for(task, timeout=1)
    assert calls == 1
    assert not registry.is_running("one_shot")


async def test_cancel_swallowing_worker_does_not_restart(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A loop that swallows CancelledError and returns must not be restarted."""
    caplog.set_level(logging.WARNING)
    registry = WorkerRegistry()
    started = asyncio.Event()

    async def swallowing() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    registry.register("swallowing", swallowing, restart_policy="always")
    task = registry.start("swallowing")
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    began = time.monotonic()
    await asyncio.wait_for(registry.shutdown(timeout=1), timeout=2)
    elapsed = time.monotonic() - began

    assert elapsed < 1.0, "a cancel-swallowing worker must not delay shutdown"
    assert task.done()
    assert "returned unexpectedly" not in caplog.text
    assert "did not stop within shutdown timeout" not in caplog.text


async def test_backoff_resets_after_healthy_run(caplog: pytest.LogCaptureFixture) -> None:
    """A long healthy run resets the restart delay to the initial value."""
    caplog.set_level(logging.WARNING)
    registry = WorkerRegistry()
    calls = 0
    restarted = asyncio.Event()
    blocker = asyncio.Event()

    async def factory() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("first crash")
        if calls == 2:
            await asyncio.sleep(0.05)
            raise RuntimeError("second crash after healthy run")
        restarted.set()
        await blocker.wait()

    registry.register(
        "healthy",
        factory,
        restart_policy="always",
        initial_delay=0.01,
        max_delay=0.02,
    )
    task = registry.start("healthy")
    assert task is not None

    await asyncio.wait_for(restarted.wait(), timeout=2)
    retry_delays = [
        record.context["retry_in"]
        for record in caplog.records
        if getattr(record, "context", {}).get("worker") == "healthy"
        and "crashed; restarting with backoff" in record.getMessage()
    ]
    assert retry_delays[0] == pytest.approx(0.01)
    assert retry_delays[1] == pytest.approx(0.01), "healthy run must reset backoff"

    blocker.set()
    await registry.shutdown(timeout=1)


async def test_shutdown_returns_within_timeout_when_worker_hangs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A worker that ignores cancellation cannot block shutdown forever."""
    caplog.set_level(logging.WARNING)
    registry = WorkerRegistry()
    started = asyncio.Event()

    async def stubborn() -> None:
        started.set()
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                # Ignore the first cancellation; the registry must stop waiting.
                await asyncio.sleep(3600)

    registry.register(
        "stubborn",
        stubborn,
        restart_policy="always",
        shutdown_timeout=0.05,
    )
    task = registry.start("stubborn")
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    began = time.monotonic()
    await asyncio.wait_for(registry.shutdown(timeout=0.05), timeout=2)
    elapsed = time.monotonic() - began

    assert elapsed < 1.0, "shutdown must return once the bounded wait expires"
    assert "did not stop within shutdown timeout" in caplog.text

    # Clean up the stubborn task; the second cancellation is not swallowed.
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
