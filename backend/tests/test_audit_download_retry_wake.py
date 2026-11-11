"""Task T2: idle download workers must claim due retries without external events.

Report 01 P1-4: when ``claim_pending`` found nothing, the worker blocked on
``my_event.wait()`` forever. ``retry_at`` becoming due never set that event, so
a transient failure could sit in ``pending`` until an unrelated enqueue or a
restart. The worker now waits with a bounded timeout derived from the earliest
scheduled ``retry_at`` (with a safety-net poll when none is scheduled); the
event is only an early-wakeup hint.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Self

from galleryvault.services import download_worker as dw


class _FakeBegin:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    def __init__(self, repo: _RecordingRepo) -> None:
        self.repo = repo

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def begin(self) -> _FakeBegin:
        return _FakeBegin()


class _FakeFactory:
    def __init__(self, repo: _RecordingRepo) -> None:
        self.repo = repo

    def __call__(self) -> _FakeSession:
        return _FakeSession(self.repo)


class _RecordingRepo:
    """Repository stub: never claims a row, records each claim attempt."""

    def __init__(self, next_retry_at: datetime | None) -> None:
        self._next_retry_at = next_retry_at
        self.claims = 0
        self.second_claim = asyncio.Event()

    async def claim_pending(self) -> None:
        self.claims += 1
        if self.claims >= 2:
            self.second_claim.set()

    async def next_retry_at(self) -> datetime | None:
        return self._next_retry_at


async def _start_worker(monkeypatch, repo: _RecordingRepo) -> asyncio.Task:
    monkeypatch.setattr(dw, "_get_background_session_factory", lambda: _FakeFactory(repo))
    monkeypatch.setattr(dw, "DownloadRepository", lambda session: session.repo)
    # Keep the cooperative-drain check from exiting our sole worker.
    monkeypatch.setattr(dw, "_target_download_concurrency", 8)
    task = asyncio.create_task(dw._download_worker())
    # The worker exits immediately unless it recognises itself as supervised.
    dw._worker_tasks.append(task)
    return task


async def _stop_worker(task: asyncio.Task) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    dw._worker_tasks[:] = [t for t in dw._worker_tasks if t is not task]
    dw._worker_events.clear()


def test_idle_poll_timeout_is_bounded() -> None:
    assert dw._idle_poll_timeout(None) == dw._WORKER_POLL_MAX_SECONDS
    # A retry that is already due (or due in <1s) uses the minimum wait so the
    # worker neither spins nor sleeps past the deadline.
    assert dw._idle_poll_timeout(datetime.now(UTC) + timedelta(seconds=0.2)) == (
        dw._WORKER_POLL_MIN_SECONDS
    )
    # Distant retries and SQLite's naive datetimes are clamped to the cap.
    assert dw._idle_poll_timeout(datetime.now(UTC) + timedelta(hours=3)) == (
        dw._WORKER_POLL_MAX_SECONDS
    )
    naive = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=30)
    assert 20.0 <= dw._idle_poll_timeout(naive) <= 30.0


async def test_idle_worker_reclaims_due_retry_without_event(monkeypatch) -> None:
    repo = _RecordingRepo(datetime.now(UTC) + timedelta(seconds=0.2))
    task = await _start_worker(monkeypatch, repo)
    try:
        started = time.monotonic()
        await asyncio.wait_for(repo.second_claim.wait(), timeout=3)
        elapsed = time.monotonic() - started
    finally:
        await _stop_worker(task)

    assert repo.claims >= 2
    assert not any(ev.is_set() for ev in dw._worker_events), "no external wakeup was sent"
    # retry_at was <1s away, so the bounded wait is the 1s minimum.
    assert elapsed <= 1.5, f"worker re-claimed only after {elapsed:.2f}s"


async def test_idle_worker_keeps_polling_without_scheduled_retry(monkeypatch) -> None:
    monkeypatch.setattr(dw, "_WORKER_POLL_MIN_SECONDS", 0.05)
    monkeypatch.setattr(dw, "_WORKER_POLL_MAX_SECONDS", 0.05)
    repo = _RecordingRepo(None)
    task = await _start_worker(monkeypatch, repo)
    try:
        started = time.monotonic()
        await asyncio.wait_for(repo.second_claim.wait(), timeout=2)
        elapsed = time.monotonic() - started
    finally:
        await _stop_worker(task)

    assert elapsed <= 1.0, f"safety-net poll took {elapsed:.2f}s"
    assert not any(ev.is_set() for ev in dw._worker_events)
