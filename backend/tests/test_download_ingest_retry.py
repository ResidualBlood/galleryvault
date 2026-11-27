"""B2/T2.2: ingest failures are retryable, visible and observable.

Regression target: after T2.1 an ingest failure leaves ``failed +
ingest_status='failed'`` with the payload and target directory intact, but there
was no retry entry point (a retry redownloaded everything), no notification and
no task-ledger record. These tests pin the retry rule (files on disk -> re-run
ingest only, files gone -> normal re-download), the shared repository method
used by the API, ``retry-all`` and the Telegram bot, and the failure notice.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from galleryvault.app.routers import downloads as downloads_router
from galleryvault.app.state import app_state
from galleryvault.db.repositories.downloads import DownloadRepository
from galleryvault.services.download import ingest_pump as dw


class _Task:
    def __init__(self, **kwargs: object) -> None:
        self.id = 1
        self.gid = 999
        self.token = "tok"
        self.status = "failed"
        self.ingest_status = "failed"
        self.ingest_payload = {"gid": 999, "title": "Test", "path": "/tmp/999-Test"}
        self.target_path = None
        self.retry_count = 3
        self.retry_at = object()
        self.error_message = "ingest: library insert failed"
        self.finished_at = datetime.now(UTC)
        self.max_retries = 0
        self.updated_at = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Session:
    def __init__(self, row: _Task | None) -> None:
        self.row = row

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _Session:
        return self

    async def get(self, _model: object, _pk: int) -> _Task | None:
        return self.row


@pytest.mark.asyncio
async def test_retry_ingest_failed_reruns_ingest_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "999-Test"
    target.mkdir()
    (target / "0001.jpg").write_bytes(b"x")
    row = _Task(target_path=str(target))
    executed: list[object] = []

    async def _execute(*args: object, **_kwargs: object) -> None:
        executed.append(args)

    app_state.downloader = SimpleNamespace(execute=_execute)

    result = await downloads_router.retry_download(1, session=_Session(row))

    assert result == {"id": 1, "status": "downloading"}
    assert row.status == "downloading"
    assert row.ingest_status == "pending"
    assert row.ingest_payload is not None, "only the ingest is re-run, not the download"
    assert row.retry_count == 0
    assert row.error_message is None
    assert row.finished_at is None
    assert row.max_retries == 10
    assert executed == [], "a retry with the files on disk must not download again"


@pytest.mark.asyncio
async def test_retry_ingest_failed_without_files_requeues_download(tmp_path: Path) -> None:
    missing = tmp_path / "999-Test"
    row = _Task(target_path=str(missing))

    result = await downloads_router.retry_download(1, session=_Session(row))

    assert result == {"id": 1, "status": "pending"}
    assert row.status == "pending"
    assert row.ingest_status is None
    assert row.ingest_payload is None, "a fresh download rebuilds the ingest snapshot"


@pytest.mark.asyncio
async def test_retry_all_reingests_ingest_failures_in_place(tmp_path: Path) -> None:
    target = tmp_path / "999-Test"
    target.mkdir()
    candidates = [
        (1, 100, "failed", "failed", str(target)),
        (2, 200, "failed", None, None),
        (3, 300, "pending", None, None),
    ]

    class _Result:
        def __init__(self, rows: list[tuple] | None = None) -> None:
            self._rows = rows or []

        def all(self) -> list[tuple]:
            return self._rows

    class _AllSession:
        def __init__(self) -> None:
            self.stmts: list[object] = []

        async def execute(self, stmt: object) -> _Result:
            self.stmts.append(stmt)
            if len(self.stmts) == 1:
                return _Result(candidates)
            return _Result()

    session = _AllSession()
    retried = await DownloadRepository(session).retry_all()  # type: ignore[arg-type]

    assert retried == [1, 2, 3]
    assert len(session.stmts) == 3, "one select plus one update per retry kind"

    def _values(stmt: object) -> dict[str, object]:
        return {
            col.name: getattr(value, "value", value)
            for col, value in stmt._values.items()  # type: ignore[attr-defined]
        }

    updates = [(stmt, _values(stmt)) for stmt in session.stmts[1:]]
    ingest_stmt, ingest_values = next(
        (stmt, values) for stmt, values in updates if values["status"] == "downloading"
    )
    _plain_stmt, plain_values = next(
        (stmt, values) for stmt, values in updates if values["status"] == "pending"
    )
    assert ingest_values["status"] == "downloading"
    assert ingest_values["ingest_status"] == "pending"
    assert plain_values["status"] == "pending"
    assert plain_values["ingest_status"] is None
    ingest_sql = str(
        ingest_stmt.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "id IN (1)" in ingest_sql


class _PumpRow:
    def __init__(self) -> None:
        self.id = 1
        self.gid = 999
        self.token = "tok"
        self.title = "Test"
        self.status = "downloading"
        self.ingest_status = "pending"
        self.ingest_payload = {"gid": 999, "title": "Test", "path": "/tmp/999-Test"}
        self.target_path = "/tmp/999-Test"
        self.error_message = None
        self.finished_at = None
        self.updated_at = None


class _PumpResult:
    rowcount = 1


class _PumpSession:
    def __init__(self, row: _PumpRow) -> None:
        self.row = row

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _PumpSession:
        return self

    async def get(self, _model: object, _pk: int) -> _PumpRow:
        return self.row

    async def scalar(self, _stmt: object) -> _PumpRow | None:
        if self.row.status == "downloading" and self.row.ingest_status == "pending":
            return self.row
        return None

    async def execute(self, stmt: object) -> _PumpResult:
        compiled = stmt.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
        for key, value in compiled.params.items():
            if hasattr(self.row, key):
                setattr(self.row, key, value)
        return _PumpResult()


class _TaskManagerStub:
    def __init__(self) -> None:
        self.records: list[tuple[tuple, dict]] = []

    def record_task(self, *args: object, **kwargs: object) -> None:
        self.records.append((args, kwargs))


@pytest.mark.asyncio
async def test_ingest_failure_notifies_fail_and_records_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _PumpRow()
    app_state.session_factory = lambda: _PumpSession(row)
    app_state.telegram = SimpleNamespace()
    app_state.settings = SimpleNamespace(telegram_notify_lang="zh")
    tm = _TaskManagerStub()
    monkeypatch.setattr(app_state, "task_manager", tm)

    async def _explode(_result: object, *, strict: bool = False) -> None:
        raise dw.IngestError("library insert exploded")

    notified: list[tuple] = []

    async def _record(kind: str, title: str, detail: str | None = None) -> None:
        notified.append((kind, title, detail))

    monkeypatch.setattr(dw, "ingest_downloaded_gallery", _explode)
    monkeypatch.setattr(dw, "record_download_notification", _record)

    assert await dw.run_pending_ingest_once() is True
    await asyncio.sleep(0)

    assert row.status == "failed"
    assert row.ingest_status == "failed"
    assert notified and notified[0][0] == "fail", "an ingest failure must be reported"
    title, detail = notified[0][1], notified[0][2]
    assert title == "Test"
    assert "入库失败" in str(detail) and "library insert exploded" in str(detail)
    assert tm.records and tm.records[0][0][0] == "download-ingest"
    assert tm.records[0][0][3] == "failed"


@pytest.mark.asyncio
async def test_list_rejects_unknown_status() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await downloads_router.list_downloads(status="bogus", session=object())

    assert excinfo.value.status_code == 422
    assert "invalid status" in str(excinfo.value.detail)
