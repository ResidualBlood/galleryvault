"""Failure injection (library): an existing root that cannot be read.

NFS/volume drop-out shape: the root still exists and ``stat`` succeeds, but
traversing it raises ``OSError(EIO)``.  A scan must treat the root as
unverified instead of "everything under it is gone":

* ``LibraryService.incomplete_roots`` contains the root and
  ``scan_incomplete`` is true;
* ``run_scan`` skips expunge entirely, so no row under that root is expunged.

The already-covered "root missing" (``test_scan_consistency_t5.py``) and
"scan incomplete" (``test_s7_symlink_expunge.py``) cases are intentionally not
duplicated here; this file pins the read-error variant only.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.scanners.base import ExistingGallery
from galleryvault.services import scan_worker
from galleryvault.services.library import LibraryService
from galleryvault.services.scan_worker import run_scan
from galleryvault.services.tasks import TaskManager


def _install_eio_walk(monkeypatch: pytest.MonkeyPatch, failing_root: Path) -> None:
    """Make ``os.walk(failing_root)`` report ``EIO`` through ``onerror``."""
    real_walk = os.walk

    def failing_walk(top, topdown=True, onerror=None, followlinks=False):
        if Path(top) == failing_root:
            def _fail() -> None:
                if onerror is not None:
                    onerror(OSError(errno.EIO, "Input/output error", str(top)))
                return
                yield  # pragma: no cover - makes this a generator

            return _fail()
        return real_walk(top, topdown=topdown, onerror=onerror, followlinks=followlinks)

    monkeypatch.setattr(os, "walk", failing_walk)


def _existing_row(root: Path) -> ExistingGallery:
    return ExistingGallery(
        path=str(root / "123-Some Gallery"),
        signature="sig",
        gid=123,
        gallery_id=1,
        storage_type="folder",
        title="Some Gallery",
    )


def test_unreadable_root_is_incomplete_and_keeps_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "library"
    root.mkdir()
    _install_eio_walk(monkeypatch, root)

    service = LibraryService([root], existing={"known": _existing_row(root)})

    assert list(service.candidates()) == []
    assert service.scan_incomplete is True
    assert str(root) in service.incomplete_roots


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        return self


class _FakeRepo:
    """Repo double that records every expunge attempt."""

    candidates: ClassVar[list[dict]] = []
    mark_calls: ClassVar[list[list[int]]] = []
    find_calls: ClassVar[int] = 0
    find_missing_ids = staticmethod(GalleryRepository.find_missing_ids)

    def __init__(self, session):
        pass

    async def fetch_existing_rows_raw(self, roots):
        return []

    async def fetch_starred_and_custom_tag_metadata(self):
        return set(), set(), set()

    @staticmethod
    def parse_existing_rows(
        raw_rows, roots, *, custom_tag_ids=None, fav_gids=None, local_list_ids=None
    ):
        return {"known": _existing_row(Path(roots[0]))}

    async def fetch_expunge_candidates(self):
        _FakeRepo.find_calls += 1
        return list(_FakeRepo.candidates)

    async def mark_expunged(self, ids):
        _FakeRepo.mark_calls.append(list(ids))
        return len(ids)

    async def sync_duplicates(self, duplicates):
        pass

    async def metadata_map(self, gids):
        return {}


class _FakeIngest:
    def __init__(self, session):
        pass

    async def ingest(self, batch):
        pass


@pytest.mark.asyncio
async def test_run_scan_does_not_expunge_when_root_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "library"
    root.mkdir()
    _install_eio_walk(monkeypatch, root)

    orig_tm = app_state.task_manager
    orig_session = app_state.session_factory
    orig_settings = app_state.settings
    _FakeRepo.candidates = [
        {
            "id": 7,
            "path_hash": "hash-of-row-under-root",
            "storage_path": str(root / "123-Some Gallery"),
        }
    ]
    _FakeRepo.mark_calls = []
    _FakeRepo.find_calls = 0
    tm = TaskManager()
    app_state.task_manager = tm
    app_state.session_factory = lambda: _FakeSession()
    app_state.settings = Settings(
        library_roots=[str(root)],
        download_root="",
        cold_storage_root="",
        scan_batch_size=10,
        auto_sync_tags=False,
    )
    monkeypatch.setattr(scan_worker, "GalleryRepository", _FakeRepo)
    monkeypatch.setattr(scan_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(scan_worker, "backfill_image_quality", AsyncMock(return_value=0))
    monkeypatch.setattr(
        "galleryvault.services.series.rebuild_series_groups", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "galleryvault.services.duplicates.scan_library_cross_gid_groups",
        AsyncMock(return_value=[]),
    )
    try:
        await run_scan()
    finally:
        app_state.task_manager = orig_tm
        app_state.session_factory = orig_session
        app_state.settings = orig_settings

    assert _FakeRepo.find_calls == 0
    assert _FakeRepo.mark_calls == []
    assert tm.scan_state["scan_incomplete"] is True
    assert str(root) in tm.scan_state["incomplete_roots"]
