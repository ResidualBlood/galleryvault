"""Tests for Phase 2 & 3 modular architecture, task state machine, and histograms."""

from __future__ import annotations

import time

from galleryvault.observability import (
    measure_duration,
    observe_histogram,
    render_metrics,
    set_gauge,
)
from galleryvault.services.download_worker import infer_image_quality, retry_backoff
from galleryvault.services.settings_service import (
    decrypt_user_settings,
    is_public_site,
)
from galleryvault.services.tasks import TaskManager, TaskProgress


def test_task_progress_model() -> None:
    prog = TaskProgress(task="scan", running=True, done=5, total=10, stage="indexing")
    d = prog.to_dict()
    assert d["task"] == "scan"
    assert d["running"] is True
    assert d["done"] == 5
    assert d["total"] == 10
    assert d["stage"] == "indexing"


def test_task_manager_cancellation_and_recording() -> None:
    tm = TaskManager()
    assert tm.is_cancelled("scan") is False
    tm.request_cancel("scan")
    assert tm.is_cancelled("scan") is True
    tm.clear_cancelled("scan")
    assert tm.is_cancelled("scan") is False

    tm.record_task("scan", "2026-08-31T00:00:00Z", "2026-08-31T00:01:00Z", "success", done=10, total=10)
    assert len(tm.task_history) == 1
    assert tm.task_history[0]["task"] == "scan"
    assert tm.task_history[0]["status"] == "success"

    # Test running summary
    tm.scan_state["running"] = True
    tm.scan_state["started_at"] = "2026-08-31T00:00:00Z"
    summary = tm.get_running_summary()
    assert any(item["task"] == "scan" for item in summary)


def test_histogram_metrics_observation_and_render() -> None:
    observe_histogram("gv_test_duration_seconds", 0.05, {"handler": "test"})
    observe_histogram("gv_test_duration_seconds", 0.15, {"handler": "test"})

    with measure_duration("gv_test_measure_seconds", {"op": "work"}):
        time.sleep(0.01)

    set_gauge("gv_test_gauge", 42.0)

    output = render_metrics()
    assert "gv_test_duration_seconds_bucket" in output
    assert "gv_test_duration_seconds_sum" in output
    assert "gv_test_duration_seconds_count" in output
    assert "gv_test_measure_seconds_bucket" in output
    assert "gv_test_gauge 42.0" in output


def test_settings_service_helpers() -> None:
    assert is_public_site("https://e-hentai.org") is True
    assert is_public_site("https://exhentai.org") is False
    assert is_public_site("") is False
    assert is_public_site(None) is False

    dec = decrypt_user_settings({"exhentai_cookies": '{"ipb_member_id": "123"}'})
    assert dec["exhentai_cookies"] == {"ipb_member_id": "123"}


def test_download_worker_helpers() -> None:
    assert retry_backoff(1) == 30
    assert retry_backoff(2) == 120
    assert retry_backoff(10) == 21600

    assert infer_image_quality(1000, 1000) == "original"
    assert infer_image_quality(500, 1000) == "resample"
    assert infer_image_quality(None, 1000) is None
