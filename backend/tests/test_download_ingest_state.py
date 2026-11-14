"""B2/T2.1: download success must mean "already in the library".

The downloader only records ``downloading + ingest_status='pending'`` once the
files are on disk; the DB-driven ingest pump writes ``success``/``done`` after
a real import, or ``failed``/``failed`` when the import raises. These tests use
fake sessions (no database) and assert the state machine, the notification
ordering and the restart-safe payload.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.db.repositories.downloads import DownloadRepository
from galleryvault.services import download_worker as dw
from galleryvault.services.downloader import DownloadTask


class _Row:
    def __init__(self, **kwargs: object) -> None:
        self.id = 1
        self.gid = 999
        self.token = "tok"
        self.title = "Test"
        self.title_jpn = None
        self.status = "downloading"
        self.retry_count = 0
        self.max_retries = 5
        self.retry_at = None
        self.error_message = None
        self.updated_at = None
        self.finished_at = None
        self.started_at = None
        self.target_path = None
        self.category = None
        self.current_page = 0
        self.total_pages = None
        self.archive_fallback = False
        self.ingest_status = None
        self.ingest_payload = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Result:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _PumpSession:
    """Applies UPDATE params to the in-memory row (real repository statements)."""

    def __init__(self, row: _Row) -> None:
        self.row = row

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _PumpSession:
        return self

    async def get(self, _model: object, _task_id: int) -> _Row:
        return self.row

    async def scalar(self, _stmt: object) -> _Row | None:
        if self.row.status == "downloading" and self.row.ingest_status == "pending":
            return self.row
        return None

    async def execute(self, stmt: object) -> _Result:
        compiled = stmt.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
        for key, value in compiled.params.items():
            if hasattr(self.row, key):
                setattr(self.row, key, value)
        return _Result(1)


@pytest.fixture(autouse=True)
def _settings() -> None:
    app_state.settings = Settings(global_paused=False)


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "999-Test"
    target.mkdir()
    (target / "0001.jpg").write_bytes(b"x")
    return target


def _result(path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        path=str(path),
        category="manga",
        title="Test",
        title_jpn=None,
        pages=1,
        gid=999,
        token="tok",
        quality="resample",
        tags=[],
        new_files=[],
        file_size=1,
        uploader=None,
        rating=None,
    )


async def _no_previous_gid(_gid: int) -> None:
    return None


@pytest.mark.asyncio
async def test_ingest_failure_is_not_success(monkeypatch, tmp_path: Path) -> None:
    row = _Row()
    app_state.session_factory = lambda: _PumpSession(row)

    async def _execute(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _result(_target(tmp_path))

    app_state.downloader = SimpleNamespace(execute=_execute)

    class _FakeRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def record_attempt(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(dw, "DownloadRepository", _FakeRepo)
    await dw._run_download_inner(DownloadTask(999, "tok", "Test", id=1, max_retries=5))
    monkeypatch.setattr(dw, "DownloadRepository", DownloadRepository)

    assert row.status == "downloading"
    assert row.ingest_status == "pending"
    assert row.finished_at is None

    app_state.session_factory = lambda: _PumpSession(row)

    async def _explode(_result: object, *, strict: bool = False) -> None:
        raise dw.IngestError("library insert failed")

    monkeypatch.setattr(dw, "ingest_downloaded_gallery", _explode)
    monkeypatch.setattr(dw, "_previous_gid_for", _no_previous_gid)
    notified: list[tuple] = []

    async def _record(kind: str, title: str, detail: str | None = None) -> None:
        notified.append((kind, title, detail))

    monkeypatch.setattr(dw, "record_download_notification", _record)

    assert await dw.run_pending_ingest_once() is True

    assert row.status == "failed", "an ingest failure must never report success"
    assert row.ingest_status == "failed"
    assert str(row.error_message).startswith("ingest: ")
    assert "library insert failed" in str(row.error_message)
    assert notified == [], "ok/updated notification must wait for a successful ingest"


@pytest.mark.asyncio
async def test_ok_notification_sent_after_ingest(monkeypatch) -> None:
    row = _Row(
        ingest_status="pending",
        ingest_payload={"gid": 999, "title": "Test", "path": "/tmp/999-Test", "pages": 3},
    )
    app_state.session_factory = lambda: _PumpSession(row)

    order: list[str] = []

    async def _ingest(_result: object, *, strict: bool = False) -> None:
        order.append("ingest")

    async def _record(_kind: str, _title: str, _detail: str | None = None) -> None:
        order.append("notify")

    monkeypatch.setattr(dw, "ingest_downloaded_gallery", _ingest)
    monkeypatch.setattr(dw, "record_download_notification", _record)
    monkeypatch.setattr(dw, "_previous_gid_for", _no_previous_gid)

    assert await dw.run_pending_ingest_once() is True

    assert order == ["ingest", "notify"]
    assert row.status == "success"
    assert row.ingest_status == "done"
    assert row.ingest_payload is None, "payload is only needed until the import succeeds"
    assert row.finished_at is not None


@pytest.mark.asyncio
async def test_no_scanner_is_ingest_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dw, "registry", SimpleNamespace(for_path=lambda _path: None))

    with pytest.raises(dw.IngestError, match="no scanner"):
        await dw.ingest_downloaded_gallery(_result(_target(tmp_path)), strict=True)


@pytest.mark.asyncio
async def test_pending_ingest_survives_restart(monkeypatch) -> None:
    # A previous process died after the files landed: the row is the only state.
    payload = {"gid": 999, "title": "Test", "path": "/tmp/999-Test", "pages": 1}
    row = _Row(ingest_status="pending", ingest_payload=payload)
    app_state.session_factory = lambda: _PumpSession(row)

    ingested: list[object] = []

    async def _ingest(result: object, *, strict: bool = False) -> None:
        ingested.append(result)

    async def _record(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(dw, "ingest_downloaded_gallery", _ingest)
    monkeypatch.setattr(dw, "record_download_notification", _record)
    monkeypatch.setattr(dw, "_previous_gid_for", _no_previous_gid)

    assert await dw.run_pending_ingest_once() is True
    assert getattr(ingested[0], "gid", None) == 999
    assert row.status == "success"
    assert row.ingest_status == "done"
    assert await dw.run_pending_ingest_once() is False


def test_recover_orphans_skips_pending_ingest() -> None:
    captured: dict[str, object] = {}

    class _CaptureSession:
        async def execute(self, stmt: object) -> _Result:
            captured["stmt"] = stmt
            return _Result(0)

    import asyncio

    asyncio.run(
        DownloadRepository(_CaptureSession()).recover_orphans()  # type: ignore[arg-type]
    )

    compiled = captured["stmt"].compile(  # type: ignore[union-attr]
        dialect=postgresql.dialect()
    )
    sql = str(compiled)
    assert "ingest_status IS NULL" in sql
    assert compiled.params.get("status") == "pending"


def test_ingest_payload_round_trip() -> None:
    result = SimpleNamespace(
        path=Path("/tmp/999-Test"),
        quality="original",
        new_files={"0001.jpg", "0002.jpg"},
        tags={"artist": ["someone"]},
        file_size=12,
        title="Test",
        gid=999,
        token="tok",
        title_jpn="テスト",
        category="manga",
        uploader="up",
        rating=4.5,
        pages=2,
    )
    payload = dw.serialize_ingest_payload(result)
    replay = dw.ingest_result_from_payload(payload)

    assert replay.path == "/tmp/999-Test"
    assert sorted(replay.new_files) == ["0001.jpg", "0002.jpg"]
    assert replay.tags == {"artist": ["someone"]}
    assert replay.title_jpn == "テスト"
    assert replay.rating == 4.5
    for field in dw._INGEST_PAYLOAD_FIELDS:
        assert getattr(replay, field) is not None or getattr(result, field) is None
