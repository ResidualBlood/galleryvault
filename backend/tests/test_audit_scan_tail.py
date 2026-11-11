"""T11: scan tail must survive series rebuild failures and stay deterministic.

Covers:
- a failing series rebuild is logged as a warning and does not skip the
  cross-gid dedup scan or mark the scan ``last`` as errored;
- a rebuild already running (HTTP route) makes the scan tail skip series
  rebuild while still running dedup;
- the service-level guard is released on failure;
- ``get_auto_series`` is ordered by id;
- ``_existing_page_file`` picks the same file when ``.jpg``/``.webp`` coexist.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.db.repositories.series import SeriesRepository
from galleryvault.services import duplicates as duplicates_module
from galleryvault.services import scan_worker
from galleryvault.services import series as series_module
from galleryvault.services.downloader import _existing_page_file
from galleryvault.services.scan_worker import run_scan
from galleryvault.services.tasks import TaskManager

VALID_JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20
VALID_WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return self

    async def flush(self):
        return None


class _FakeRepo:
    def __init__(self, session):
        self.session = session

    async def existing_rows(self, roots):
        return {}

    async def expunge_missing(self, roots, seen_hashes):
        return 0

    async def sync_duplicates(self, duplicates):
        return 0


class _FakeIngestService:
    def __init__(self, session):
        pass

    async def ingest(self, batch):
        pass


class _FakeLibraryService:
    scan_incomplete = False

    def __init__(self, *args, **kwargs):
        self.seen_path_hashes = set()
        self.last_duplicates = []
        self.last_counters = SimpleNamespace(added=0, updated=0, unchanged=0)

    def scan_batches(self, should_stop):
        return iter(())


async def _run_scan_with_fakes(monkeypatch, tmp_path) -> TaskManager:
    tm = TaskManager()
    monkeypatch.setattr(app_state, "task_manager", tm)
    monkeypatch.setattr(app_state, "session_factory", lambda: _FakeSession())
    monkeypatch.setattr(
        app_state,
        "settings",
        Settings(
            library_roots=[str(tmp_path)],
            download_root=str(tmp_path / "downloads"),
            scan_batch_size=10,
            auto_sync_tags=False,
        ),
    )
    monkeypatch.setattr(scan_worker, "GalleryRepository", _FakeRepo)
    monkeypatch.setattr(scan_worker, "GalleryIngestService", _FakeIngestService)
    monkeypatch.setattr(scan_worker, "LibraryService", _FakeLibraryService)
    monkeypatch.setattr(scan_worker, "backfill_image_quality", AsyncMock(return_value=0))

    await run_scan()
    return tm


@pytest.mark.asyncio
async def test_series_rebuild_failure_keeps_scan_ok_and_runs_dedup(
    monkeypatch, tmp_path, caplog
) -> None:
    rebuild = AsyncMock(side_effect=RuntimeError("series exploded"))
    dedup = AsyncMock(return_value=[])
    monkeypatch.setattr(series_module, "rebuild_series_groups_guarded", rebuild)
    monkeypatch.setattr(
        duplicates_module, "scan_library_cross_gid_duplicates_locked", dedup
    )

    with caplog.at_level("INFO", logger="galleryvault.services.scan_worker"):
        tm = await _run_scan_with_fakes(monkeypatch, tmp_path)

    assert rebuild.await_count == 1
    assert dedup.await_count == 1, "series failure must not skip the dedup scan"
    assert dedup.await_args.kwargs["wait"] is True
    assert tm.scan_state["last"].get("error") is None
    assert tm.scan_state.get("last_error") is None
    assert "series rebuild failed" in caplog.text
    failures = [
        record
        for record in caplog.records
        if (record.__dict__.get("context") or {}).get("error") == "RuntimeError"
    ]
    assert failures, "series failure must be logged at warning level"


@pytest.mark.asyncio
async def test_scan_tail_skips_series_rebuild_when_route_holds_guard(
    monkeypatch, tmp_path, caplog
) -> None:
    monkeypatch.setattr(series_module, "series_rebuild_state", {"running": True})
    rebuild = AsyncMock(return_value={"created": 1, "merged": 1})
    dedup = AsyncMock(return_value=[])
    monkeypatch.setattr(series_module, "rebuild_series_groups", rebuild)
    monkeypatch.setattr(
        duplicates_module, "scan_library_cross_gid_duplicates_locked", dedup
    )

    with caplog.at_level("INFO", logger="galleryvault.services.scan_worker"):
        tm = await _run_scan_with_fakes(monkeypatch, tmp_path)

    assert rebuild.await_count == 0
    assert dedup.await_count == 1
    assert "series rebuild skipped" in caplog.text
    assert tm.scan_state["last"].get("error") is None


@pytest.mark.asyncio
async def test_guarded_rebuild_releases_state_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(series_module, "series_rebuild_state", {"running": False})
    monkeypatch.setattr(
        series_module,
        "rebuild_series_groups",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await series_module.rebuild_series_groups_guarded()

    assert series_module.series_rebuild_state["running"] is False


@pytest.mark.asyncio
async def test_guarded_rebuild_returns_none_while_running(monkeypatch) -> None:
    monkeypatch.setattr(series_module, "series_rebuild_state", {"running": True})
    rebuild = AsyncMock(return_value={"created": 0})
    monkeypatch.setattr(series_module, "rebuild_series_groups", rebuild)

    assert await series_module.rebuild_series_groups_guarded() is None
    assert rebuild.await_count == 0
    assert series_module.series_rebuild_state["running"] is True


class _RecordingRows:
    def all(self):
        return []


class _RecordingSession:
    def __init__(self) -> None:
        self.sql: list[str] = []

    async def scalars(self, statement):
        self.sql.append(
            str(
                statement.compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
        )
        return _RecordingRows()


@pytest.mark.asyncio
async def test_get_auto_series_orders_by_id() -> None:
    session = _RecordingSession()

    rows = await SeriesRepository(session).get_auto_series()

    assert rows == []
    assert session.sql, "get_auto_series must issue a query"
    assert "order by series.id asc" in session.sql[0].lower()


def test_existing_page_file_prefers_sorted_extension(tmp_path) -> None:
    (tmp_path / "00000001.webp").write_bytes(VALID_WEBP_BYTES)
    (tmp_path / "00000001.jpg").write_bytes(VALID_JPG_BYTES)

    assert _existing_page_file(tmp_path, 0) == tmp_path / "00000001.jpg"
    assert _existing_page_file(tmp_path, 0, quality="resample") == tmp_path / "00000001.jpg"

    # original quality ignores webp, so the jpg still wins.
    assert _existing_page_file(tmp_path, 0, quality="original") == tmp_path / "00000001.jpg"


def test_existing_page_file_skips_invalid_sorted_candidate(tmp_path) -> None:
    (tmp_path / "00000001.jpg").write_bytes(b"not-an-image-payload")
    (tmp_path / "00000001.webp").write_bytes(VALID_WEBP_BYTES)

    assert _existing_page_file(tmp_path, 0) == tmp_path / "00000001.webp"
