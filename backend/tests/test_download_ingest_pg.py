"""B2/T2.1: real-PostgreSQL ingest pump state machine.

Requires the test PostgreSQL; skipped on the host where it is unreachable.
"""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from galleryvault.app.routers import downloads as downloads_router
from galleryvault.app.state import app_state
from galleryvault.config import get_settings
from galleryvault.db.models import DownloadTask
from galleryvault.services.download import ingest_pump as dw


async def _arm(factory, *task_ids: int) -> None:
    """Flip rows to ``pending`` immediately before the pump call.

    This database is shared with the running test backend, whose ingest pump
    polls every couple of seconds.  A row left ``pending`` during setup can be
    claimed by that foreign pump first (it marks it failed with its own scanner
    error).  Arming at the last moment keeps the claim deterministic without
    weakening any assertion.
    """
    async with factory() as session, session.begin():
        await session.execute(
            update(DownloadTask)
            .where(DownloadTask.id.in_(task_ids))
            .values(ingest_status="pending")
        )


class _FakeScanner:
    storage_type = "folder"

    def storage_signature(self, _path: Path) -> str:
        return "sig"


def _payload(gid: int, path: Path) -> dict:
    return {
        "path": str(path),
        "quality": "resample",
        "new_files": [],
        "tags": [],
        "file_size": 1,
        "title": f"T{gid}",
        "gid": gid,
        "token": "tok",
        "title_jpn": None,
        "category": "manga",
        "uploader": None,
        "rating": None,
        "pages": 1,
    }


@pytest.mark.asyncio
async def test_ingest_pump_failure_and_restart_resume(tmp_path: Path, monkeypatch):
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    gid_fail = 8_100_000 + uuid.uuid4().int % 10_000
    gid_ok = gid_fail + 20_000
    gallery_dir = tmp_path / f"{gid_fail}-fail"
    gallery_dir.mkdir()
    (gallery_dir / "0001.jpg").write_bytes(b"x")
    ok_dir = tmp_path / f"{gid_ok}-ok"
    ok_dir.mkdir()
    (ok_dir / "0001.jpg").write_bytes(b"x")

    original_factory = app_state.session_factory
    original_settings = app_state.settings
    original_telegram = app_state.telegram
    app_state.session_factory = factory
    app_state.settings = SimpleNamespace(auto_archive_downloads=False)
    app_state.telegram = None
    monkeypatch.setattr(
        dw, "registry", SimpleNamespace(for_path=lambda _path: _FakeScanner())
    )

    notified: list[tuple] = []

    async def _record(kind: str, title: str, detail: str | None = None) -> None:
        notified.append((kind, title, detail))

    monkeypatch.setattr(dw, "record_download_notification", _record)
    # The ledger is covered by the host test; keep this DB test free of a
    # second AppConfig writer racing other pytest workers.
    monkeypatch.setattr(dw, "_record_ingest_history", lambda *a, **k: None)
    class _FailingIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, _galleries):
            raise RuntimeError("library insert exploded")

    class _OkIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, _galleries):
            return None

    try:
        async with factory() as session, session.begin():
            fail_row = DownloadTask(
                gid=gid_fail,
                token="tok",
                title=f"T{gid_fail}",
                status="downloading",
                ingest_status=None,
                ingest_payload=_payload(gid_fail, gallery_dir),
                target_path=str(gallery_dir),
            )
            session.add(fail_row)
            await session.flush()
            fail_id = fail_row.id
            # Second row seeds the restart case: a fresh pump instance must pick
            # it up from the database, not from process memory.
            ok_row = DownloadTask(
                gid=gid_ok,
                token="tok",
                title=f"T{gid_ok}",
                status="downloading",
                ingest_status=None,
                ingest_payload=_payload(gid_ok, ok_dir),
                target_path=str(ok_dir),
            )
            session.add(ok_row)
            await session.flush()
            ok_id = ok_row.id

        monkeypatch.setattr(dw, "GalleryIngestService", _FailingIngest)
        await _arm(factory, fail_id)
        assert await dw.run_pending_ingest_once() is True

        async with factory() as session:
            fail_state = await session.scalar(
                select(DownloadTask).where(DownloadTask.id == fail_id)
            )
            assert fail_state.status == "failed"
            assert fail_state.ingest_status == "failed"
            assert "ingest:" in (fail_state.error_message or "")
            assert fail_state.ingest_payload is not None, "retry needs the payload"
            assert notified == [], "a failed ingest must not send an ok notification"

        # Rebuilt pump (new session + real success path) resumes the other row.
        monkeypatch.setattr(dw, "GalleryIngestService", _OkIngest)
        await _arm(factory, ok_id)
        assert await dw.run_pending_ingest_once() is True

        async with factory() as session:
            ok_state = await session.scalar(
                select(DownloadTask).where(DownloadTask.id == ok_id)
            )
            assert ok_state.status == "success", ok_state.error_message
            assert ok_state.ingest_status == "done"
            assert ok_state.ingest_payload is None
            assert ok_state.finished_at is not None
        assert notified and notified[0][0] == "ok"

        # T2.2: the failed ingest still has its directory -> the retry endpoint
        # puts the row back into the pump without touching the downloader.
        execute_calls: list[object] = []

        async def _execute(*args: object, **_kwargs: object) -> None:
            execute_calls.append(args)

        app_state.downloader = SimpleNamespace(execute=_execute)
        async with factory() as session:
            retry_result = await downloads_router.retry_download(fail_id, session=session)
        assert retry_result == {"id": fail_id, "status": "downloading"}

        async with factory() as session:
            pending_state = await session.scalar(
                select(DownloadTask).where(DownloadTask.id == fail_id)
            )
            assert pending_state.status == "downloading"
            assert pending_state.ingest_status == "pending"
            assert pending_state.ingest_payload is not None

        await _arm(factory, fail_id)
        assert await dw.run_pending_ingest_once() is True
        async with factory() as session:
            retried_state = await session.scalar(
                select(DownloadTask).where(DownloadTask.id == fail_id)
            )
            assert retried_state.status == "success"
            assert retried_state.ingest_status == "done"
        assert execute_calls == [], "re-running the ingest must not redownload"
        assert notified[-1][0] == "ok"
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(DownloadTask).where(DownloadTask.id.in_([fail_id, ok_id]))
            )
        app_state.session_factory = original_factory
        app_state.settings = original_settings
        app_state.telegram = original_telegram
        await engine.dispose()
