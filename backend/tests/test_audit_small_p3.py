"""Regression tests for the P3 backend batch (favorites worker / downloader / test isolation).

Covers three audit findings:

* ``favorites_worker._write_cover_file`` used a fixed ``<name>.tmp`` path, so two
  concurrent cache fillers for the same gid could ``replace()`` the same temp file
  and the loser raised ``FileNotFoundError``; the temp path must be per-call unique.
* ``Downloader.page_concurrency`` defaulted to 8 while ``Settings``/docs default to
  4; the constructor default must match the configured default.
* ``TaskManager.task_history`` is a process singleton mutated in place, so records
  written by one test leaked into the next one; the conftest autouse fixture must
  isolate it per test.
"""

from __future__ import annotations

import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from galleryvault.config import Settings
from galleryvault.services import favorites_worker
from galleryvault.services.downloader import Downloader
from galleryvault.services.tasks import default_task_manager


def test_downloader_default_page_concurrency_matches_settings_default() -> None:
    assert inspect.signature(Downloader).parameters["page_concurrency"].default == 4
    assert Settings.model_fields["page_concurrency"].default == 4


def test_concurrent_cover_writes_do_not_share_a_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two writers racing on the same cover path must both succeed.

    The original implementation wrote ``<name>.tmp`` on every call, so a concurrent
    writer could rename the shared temp file away and the other writer raised
    ``FileNotFoundError``. The barrier widens the window between writing the temp
    file and renaming it, which makes that collision deterministic.
    """
    target = tmp_path / "remote-covers" / "42.img"
    payloads = [b"a" * (256 * 1024), b"b" * (256 * 1024)]

    original_write_bytes = Path.write_bytes
    both_written = threading.Barrier(2, timeout=10)

    def write_bytes_then_wait(self: Path, data: bytes) -> int:
        written = original_write_bytes(self, data)
        # Only the shared-temp-path implementation calls this; the per-call
        # unique temp files released before rename.
        both_written.wait()
        return written

    monkeypatch.setattr(Path, "write_bytes", write_bytes_then_wait)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(favorites_worker._write_cover_file, target, payload)
            for payload in payloads
        ]
        errors = [exc for fut in futures if (exc := fut.exception()) is not None]

    assert errors == [], f"concurrent cover writes raised: {errors!r}"
    assert target.read_bytes() in payloads
    assert sorted(p.name for p in target.parent.glob("*.tmp")) == []


def test_task_history_is_cleared_before_each_test_case_1() -> None:
    """Pollutes the process-level history; the next test must not see it."""
    assert default_task_manager.task_history == []
    default_task_manager.task_history.append({"task": "leak", "status": "success"})
    assert default_task_manager.task_history == [{"task": "leak", "status": "success"}]


def test_task_history_is_cleared_before_each_test_case_2() -> None:
    assert default_task_manager.task_history == []
