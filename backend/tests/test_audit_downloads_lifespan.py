"""Audit regressions: download-task delete order and partial-sweep fail-closed.

T8:
- ``DELETE /api/downloads/{id}`` must mark linked gallery-update rows failed
  *before* deleting the task. The FK is ``ON DELETE SET NULL``, so a delete
  first (flushed by autoflush) leaves the update stuck in ``downloading``.
- ``cleanup_partial_downloads`` must skip the sweep when it cannot read the
  active download set (no session factory / query error), instead of treating
  every ``.gv-*`` directory as inactive and ``rmtree``-ing it.
"""

from __future__ import annotations

from pathlib import Path

from galleryvault.app import lifespan as lifespan_module
from galleryvault.app.routers import downloads as downloads_router
from galleryvault.app.state import app_state


class _Row:
    id = 555
    gid = 7
    status = "downloading"


class _OrderSession:
    """Minimal async session double; enough for ``safe_transaction``."""

    def __init__(self) -> None:
        self.in_transaction = lambda: False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def begin(self):
        return self

    async def commit(self):
        return None

    async def get(self, model, task_id):
        return _Row() if task_id == 555 else None


async def test_delete_marks_update_failed_before_deleting(monkeypatch):
    calls: list[str] = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def delete(self, task_id):
            calls.append(f"delete:{task_id}")
            return True

    class FakeUpdatesRepo:
        def __init__(self, session):
            pass

        async def mark_failed_by_task(self, task_id, error):
            calls.append(f"mark_failed:{task_id}")
            return 1

    cleaned: list[int] = []

    async def fake_cleanup(gid):
        cleaned.append(gid)

    monkeypatch.setattr(downloads_router, "DownloadRepository", FakeRepo)
    monkeypatch.setattr(downloads_router, "GalleryUpdatesRepository", FakeUpdatesRepo)
    monkeypatch.setattr(downloads_router, "_cleanup_download_temp", fake_cleanup)
    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: _OrderSession()

    try:
        await downloads_router.delete_download_task(555)
    finally:
        app_state.session_factory = orig_factory

    assert calls == ["mark_failed:555", "delete:555"]
    assert cleaned == [7]


class _FailingQuerySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, stmt):
        raise RuntimeError("database is unavailable")


class _FailingEnterSession:
    async def __aenter__(self):
        raise RuntimeError("cannot connect")


class _ActiveSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, stmt):
        return [(123,)]


async def test_cleanup_skips_when_active_query_fails(tmp_path: Path):
    partial = tmp_path / ".gv-123"
    partial.mkdir()
    (partial / "0001.jpg").write_bytes(b"data")

    await lifespan_module.cleanup_partial_downloads(tmp_path, lambda: _FailingQuerySession())

    assert partial.exists()
    assert (partial / "0001.jpg").exists()


async def test_cleanup_skips_when_session_cannot_be_opened(tmp_path: Path):
    partial = tmp_path / ".gv-123"
    partial.mkdir()

    await lifespan_module.cleanup_partial_downloads(tmp_path, lambda: _FailingEnterSession())

    assert partial.exists()


async def test_cleanup_skips_when_session_factory_missing(tmp_path: Path):
    partial = tmp_path / ".gv-123"
    partial.mkdir()

    await lifespan_module.cleanup_partial_downloads(tmp_path, None)

    assert partial.exists()


async def test_cleanup_still_removes_inactive_partials(tmp_path: Path):
    active = tmp_path / ".gv-123"
    stale = tmp_path / ".gv-456"
    active.mkdir()
    stale.mkdir()

    await lifespan_module.cleanup_partial_downloads(tmp_path, lambda: _ActiveSession())

    assert active.exists()
    assert not stale.exists()
