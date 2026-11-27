"""S4 fixes: sidecar title_jpn provenance and thumbnail seeding without page rows.

Covers batch-1 leftovers of review items 05/P2-11 (scanner directory-name guesses
must not be persisted as ``title_jpn``) and 05/P2-9 (galleries whose
``gallery_pages`` rows are missing must not be re-seeded hourly).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Self

import pytest

from galleryvault.app.state import app_state
from galleryvault.scanners.base import GalleryMeta, PageInfo
from galleryvault.services import thumbnail_worker
from galleryvault.services.ingest import GalleryIngestService


def _meta(path: Path, **kwargs: Any) -> GalleryMeta:
    defaults: dict[str, Any] = {
        "title": path.name,
        "path": path,
        "storage_type": "folder",
        "pages": [PageInfo(0, "0001.jpg", "jpg", 5, 0)],
    }
    defaults.update(kwargs)
    return GalleryMeta(**defaults)


def _read_sidecar(path: Path) -> dict[str, Any]:
    return json.loads((path / ".galleryvault.json").read_text(encoding="utf-8"))


def test_sidecar_does_not_persist_guessed_title_jpn(tmp_path: Path) -> None:
    """A directory-name guess must not become an authoritative title_jpn."""
    gallery_dir = tmp_path / "12345-作者名"
    gallery_dir.mkdir()

    # BareImageDirScanner falls back to the stripped directory name for both
    # title and title_jpn; source_meta has no explicit title_jpn here.
    meta = _meta(
        gallery_dir,
        gid=12345,
        token="tok",
        title="作者名",
        title_jpn="作者名",
        source_meta={},
    )
    GalleryIngestService.sync_directory_sidecars([meta])

    data = _read_sidecar(gallery_dir)
    assert data["title_jpn"] == ""
    # Non-title_jpn fields keep the previous behaviour.
    assert data["title"] == "作者名"
    assert data["gid"] == 12345


def test_sidecar_keeps_explicit_title_jpn_from_existing_sidecar(tmp_path: Path) -> None:
    """An explicit sidecar value wins and is never overwritten by a guess."""
    gallery_dir = tmp_path / "200-作者名"
    gallery_dir.mkdir()
    (gallery_dir / ".galleryvault.json").write_text(
        json.dumps({"gid": 200, "title_jpn": "真・タイトル"}), encoding="utf-8"
    )

    meta = _meta(gallery_dir, gid=200, title="作者名", title_jpn="作者名", source_meta={})
    GalleryIngestService.sync_directory_sidecars([meta])

    data = _read_sidecar(gallery_dir)
    assert data["title_jpn"] == "真・タイトル"


def test_sidecar_writes_title_jpn_supplied_by_scanner_source_meta(tmp_path: Path) -> None:
    """A scanner-provided (non-guess) title_jpn is still written."""
    gallery_dir = tmp_path / "300-Some Title"
    gallery_dir.mkdir()

    meta = _meta(
        gallery_dir,
        gid=300,
        title="Some Title",
        title_jpn="明示タイトル",
        source_meta={"title_jpn": "明示タイトル"},
    )
    GalleryIngestService.sync_directory_sidecars([meta])

    assert _read_sidecar(gallery_dir)["title_jpn"] == "明示タイトル"


class _FakeSession:
    def __init__(self, pairs: list[tuple[int, int]], page_rows: list[int], gallery: Any = None):
        self._pairs = pairs
        self._page_rows = page_rows
        self._gallery = gallery

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def begin(self) -> _FakeSession:
        return self

    async def execute(self, _stmt: object) -> list[tuple[int, int]]:
        return list(self._pairs)

    async def scalars(self, _stmt: object) -> list[int]:
        return list(self._page_rows)

    async def get(self, _model: object, _pk: int) -> Any:
        return self._gallery


@pytest.mark.asyncio
async def test_galleries_with_page_rows_filters_missing_rows() -> None:
    session = _FakeSession(pairs=[], page_rows=[1, 3, 99])
    with_rows = await thumbnail_worker._galleries_with_page_rows(session, [1, 2, 3])
    assert with_rows == {1, 3}


@pytest.mark.asyncio
async def test_seed_skips_galleries_without_page_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Galleries missing gallery_pages rows are not enqueued (no hourly spin)."""
    pairs = [(1, 2), (2, 3)]
    fake_session = _FakeSession(pairs=pairs, page_rows=[1])
    enqueued: list[list[int]] = []

    class _FakeJobs:
        def __init__(self, _session: object) -> None:
            pass

        async def enqueue_many(self, _job_type: str, gallery_ids: list[int]) -> int:
            enqueued.append(list(gallery_ids))
            return len(gallery_ids)

    class _FakeThumbService:
        def has_missing_pages(self, _gallery_id: int, _page_count: int) -> bool:
            return True

    async def _fake_jobs_count(_job_type: str) -> int:
        return 0

    monkeypatch.setattr(app_state, "session_factory", lambda: fake_session)
    monkeypatch.setattr(thumbnail_worker, "BackgroundJobsRepository", _FakeJobs)
    monkeypatch.setattr(thumbnail_worker, "jobs_count", _fake_jobs_count)
    monkeypatch.setattr(thumbnail_worker, "_thumb_service", lambda: _FakeThumbService())

    await thumbnail_worker.seed_thumbnails()

    assert enqueued == [[1]]
    tm = app_state.task_manager
    thumb_state = tm.thumb_state if tm else {}
    if thumb_state:
        assert thumb_state.get("total") == 1


@pytest.mark.asyncio
async def test_seed_enqueues_nothing_when_no_page_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession(pairs=[(7, 4)], page_rows=[])
    enqueued: list[list[int]] = []

    class _FakeJobs:
        def __init__(self, _session: object) -> None:
            pass

        async def enqueue_many(self, _job_type: str, gallery_ids: list[int]) -> int:
            enqueued.append(list(gallery_ids))
            return len(gallery_ids)

    class _FakeThumbService:
        def has_missing_pages(self, _gallery_id: int, _page_count: int) -> bool:
            return True

    async def _fake_jobs_count(_job_type: str) -> int:
        return 0

    monkeypatch.setattr(app_state, "session_factory", lambda: fake_session)
    monkeypatch.setattr(thumbnail_worker, "BackgroundJobsRepository", _FakeJobs)
    monkeypatch.setattr(thumbnail_worker, "jobs_count", _fake_jobs_count)
    monkeypatch.setattr(thumbnail_worker, "_thumb_service", lambda: _FakeThumbService())

    await thumbnail_worker.seed_thumbnails()

    assert enqueued == []


@pytest.mark.asyncio
async def test_thumbnail_gallery_skips_missing_page_rows(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    row = type("Row", (), {"page_count": 5, "storage_path": "/library/x"})()
    fake_session = _FakeSession(pairs=[], page_rows=[], gallery=row)

    class _FakeThumbService:
        def cached(self, _gallery_id: int, _page_index: int) -> None:
            return None

    monkeypatch.setattr(app_state, "session_factory", lambda: fake_session)
    monkeypatch.setattr(thumbnail_worker, "_thumb_service", lambda: _FakeThumbService())

    caplog.set_level(logging.DEBUG, logger="galleryvault.services.thumbnail_worker")
    assert await thumbnail_worker.thumbnail_gallery(42) == (0, 0)
    assert any("no page rows" in record.getMessage() for record in caplog.records)
