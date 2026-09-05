from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services import scan_worker
from galleryvault.services.scan_worker import (
    _scan_roots,
    backfill_image_quality,
    run_scan,
    scan_summary_message,
)
from galleryvault.services.tasks import TaskManager


def test_scan_roots_returns_library_and_download_roots():
    orig_settings = app_state.settings
    try:
        app_state.settings = Settings(
            library_roots=["/lib1", "/lib2"],
            download_root="/downloads",
            cold_storage_root="/cold",
        )
        roots = _scan_roots()
        assert "/lib1" in roots
        assert "/lib2" in roots
        assert "/downloads" in roots
        assert "/cold" in roots

        # Duplicate download root and cold root are not added twice
        app_state.settings = Settings(
            library_roots=["/lib1", "/downloads", "/cold"],
            download_root="/downloads",
            cold_storage_root="/cold",
        )
        assert _scan_roots() == ["/lib1", "/downloads", "/cold"]

        # Empty cold root is ignored
        app_state.settings = Settings(
            library_roots=["/lib1"],
            download_root="/downloads",
            cold_storage_root="",
        )
        assert _scan_roots() == ["/lib1", "/downloads"]
    finally:
        app_state.settings = orig_settings


def test_scan_summary_message():
    last = {"persisted": 12, "expunged": 1}
    msg_zh = scan_summary_message(last, duplicates=2, duplicate_gids=[101, 102], lang="zh")
    assert "12" in msg_zh
    assert "101" in msg_zh

    msg_en = scan_summary_message(last, duplicates=0, duplicate_gids=[], lang="en")
    assert "12" in msg_en


@pytest.mark.asyncio
async def test_backfill_image_quality_no_client_or_session():
    orig_client = app_state.eh_client
    orig_session = app_state.session_factory
    try:
        app_state.eh_client = None
        assert await backfill_image_quality() == 0

        app_state.eh_client = object()
        app_state.session_factory = None
        assert await backfill_image_quality() == 0
    finally:
        app_state.eh_client = orig_client
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_backfill_image_quality_processes_batches():
    orig_client = app_state.eh_client
    orig_session = app_state.session_factory
    orig_settings = app_state.settings
    try:
        fake_client = MagicMock()
        fake_client.fetch_gmetadata = AsyncMock(return_value={
            123: {"file_size": 1000000},
        })
        app_state.eh_client = fake_client

        row = SimpleNamespace(
            id=1,
            gid=123,
            token="abc",
            storage_size=1000000,
            storage_type="zip",
        )

        class FakeRepo:
            def __init__(self, session):
                self.session = session

            async def pending_image_quality_gids(self, limit, last_id):
                if last_id == 0:
                    return [row]
                return []

            async def metadata_map(self, gids):
                return {}

            async def upsert_metadata(self, metadata):
                pass

            async def set_image_qualities(self, qualities):
                return len(qualities)

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

        app_state.session_factory = lambda: FakeSession()

        with patch("galleryvault.services.scan_worker.GalleryRepository", FakeRepo):
            count = await backfill_image_quality()
            assert count == 1
            fake_client.fetch_gmetadata.assert_called_once_with([(123, "abc")])
    finally:
        app_state.eh_client = orig_client
        app_state.session_factory = orig_session
        app_state.settings = orig_settings


@pytest.mark.asyncio
async def test_run_scan_happy_path(monkeypatch):
    orig_tm = app_state.task_manager
    orig_session = app_state.session_factory
    orig_settings = app_state.settings
    try:
        tm = TaskManager()
        app_state.task_manager = tm
        app_state.settings = Settings(
            library_roots=["/lib"],
            download_root="/downloads",
            scan_batch_size=10,
            auto_sync_tags=False,
        )

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

        app_state.session_factory = lambda: FakeSession()

        class FakeRepo:
            def __init__(self, session):
                pass

            async def existing_rows(self, roots):
                return {}

            async def expunge_missing(self, roots, seen_hashes):
                return 0

            async def sync_duplicates(self, duplicates):
                pass

        monkeypatch.setattr(scan_worker, "GalleryRepository", FakeRepo)

        fake_batch = [SimpleNamespace(gid=1, title="Test", storage_path="/lib/1")]

        class FakeIngest:
            def __init__(self, session):
                pass

            async def ingest(self, batch):
                pass

        monkeypatch.setattr(scan_worker, "GalleryIngestService", FakeIngest)

        class FakeLibraryService:
            def __init__(self, roots, batch_size, existing, duplicate_policy):
                self.seen_path_hashes = set()
                self.last_duplicates = []
                self.last_counters = SimpleNamespace(added=1, updated=0, unchanged=0)

            def scan_batches(self, should_stop):
                yield fake_batch

        monkeypatch.setattr(scan_worker, "LibraryService", FakeLibraryService)
        monkeypatch.setattr(scan_worker, "backfill_image_quality", AsyncMock(return_value=0))

        await run_scan()

        assert tm.scan_state["scanned"] == 1
        assert tm.scan_state["persisted"] == 1
        assert tm.scan_state["running"] is False
    finally:
        app_state.task_manager = orig_tm
        app_state.session_factory = orig_session
        app_state.settings = orig_settings


@pytest.mark.asyncio
async def test_run_scan_cancellation(monkeypatch):
    orig_tm = app_state.task_manager
    orig_session = app_state.session_factory
    try:
        tm = TaskManager()
        app_state.task_manager = tm
        tm.request_cancel("scan")

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        app_state.session_factory = lambda: FakeSession()

        class FakeRepo:
            def __init__(self, session):
                pass

            async def existing_rows(self, roots):
                return {}

        monkeypatch.setattr(scan_worker, "GalleryRepository", FakeRepo)

        class FakeLibraryService:
            def __init__(self, *args, **kwargs):
                self.seen_path_hashes = set()
                self.last_duplicates = []
                self.last_counters = SimpleNamespace()

            def scan_batches(self, should_stop):
                return iter([])

        monkeypatch.setattr(scan_worker, "LibraryService", FakeLibraryService)

        await run_scan()
        assert tm.scan_state["running"] is False
    finally:
        app_state.task_manager = orig_tm
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_duplicate_resolver_import_and_sync_duplicates_no_module_error():
    from galleryvault.db.repositories.galleries import GalleryRepository
    from galleryvault.services.duplicate_resolver import ResolvedGroup

    assert ResolvedGroup is not None

    mock_session = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_session.scalars = AsyncMock(return_value=mock_scalars)
    mock_session.flush = AsyncMock()

    repo = GalleryRepository(mock_session)
    changed = await repo.sync_duplicates([])
    assert changed == 0


@pytest.mark.asyncio
async def test_run_scan_duplicate_sync_not_module_not_found(caplog, monkeypatch):
    orig_tm = app_state.task_manager
    orig_session = app_state.session_factory
    orig_settings = app_state.settings
    try:
        tm = TaskManager()
        app_state.task_manager = tm
        app_state.settings = Settings(
            library_roots=["/lib"],
            download_root="/downloads",
            scan_batch_size=10,
            auto_sync_tags=False,
        )

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

            async def scalars(self, query):
                mock = MagicMock()
                mock.all.return_value = []
                return mock

            async def flush(self):
                pass

        app_state.session_factory = lambda: FakeSession()

        from galleryvault.db.repositories.galleries import GalleryRepository

        monkeypatch.setattr(GalleryRepository, "existing_rows", AsyncMock(return_value={}))
        monkeypatch.setattr(GalleryRepository, "expunge_missing", AsyncMock(return_value=0))

        class FakeIngest:
            def __init__(self, session):
                pass

            async def ingest(self, batch):
                pass

        monkeypatch.setattr(scan_worker, "GalleryIngestService", FakeIngest)

        class FakeLibraryService:
            def __init__(self, roots, batch_size, existing, duplicate_policy):
                self.seen_path_hashes = set()
                self.last_duplicates = []
                self.last_counters = SimpleNamespace(added=0, updated=0, unchanged=0)

            def scan_batches(self, should_stop):
                return iter([])

        monkeypatch.setattr(scan_worker, "LibraryService", FakeLibraryService)
        monkeypatch.setattr(scan_worker, "backfill_image_quality", AsyncMock(return_value=0))

        with caplog.at_level("WARNING"):
            await run_scan()

        for record in caplog.records:
            if "duplicate sync failed" in record.message:
                assert "ModuleNotFoundError" not in getattr(record, "error", "")
                assert "ModuleNotFoundError" not in record.message
            assert "ModuleNotFoundError" not in record.message
    finally:
        app_state.task_manager = orig_tm
        app_state.session_factory = orig_session
        app_state.settings = orig_settings
