"""Tests for Phase 2 & 3 modular architecture, task state machine, and histograms."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from galleryvault.app.main import app
from galleryvault.app.routers.galleries import _resolve_search_tokens
from galleryvault.app.schemas import (
    BulkDeleteRequest,
    FavoritesRemoveRequest,
    FilteredDeleteRequest,
    ProgressRequest,
)
from galleryvault.auth import client_ip, is_trusted_proxy
from galleryvault.db.uow import UnitOfWork
from galleryvault.observability import (
    measure_duration,
    observe_histogram,
    render_metrics,
    set_gauge,
)
from galleryvault.services.download_worker import (
    clear_download_cancelled,
    infer_image_quality,
    is_download_cancelled,
    mark_download_cancelled,
    retry_backoff,
)
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


@pytest.mark.asyncio
async def test_resolve_search_tokens_changed_flag() -> None:
    explicit, keywords, changed = await _resolve_search_tokens("female:maid big_breasts")
    assert changed is True
    assert explicit == [("female", "maid")]
    assert keywords == "big_breasts"

    explicit, keywords, changed = await _resolve_search_tokens("plain keywords only")
    assert changed is False
    assert explicit == []
    assert keywords == "plain keywords only"


def test_request_schemas_compatibility() -> None:
    fav_req = FavoritesRemoveRequest(gids=[101, 102], delete_local=True)
    assert fav_req.gids == [101, 102]
    assert fav_req.delete_files is True
    assert fav_req.delete_local is True

    fav_req2 = FavoritesRemoveRequest(items=[{"gid": 201}, {"gid": "202"}], delete_files=True)
    assert fav_req2.gids == [201, 202]
    assert fav_req2.delete_local is True

    prog_req = ProgressRequest(page=5)
    assert prog_req.current_page == 5
    prog_req2 = ProgressRequest(current_page=12)
    assert prog_req2.page == 12

    bulk_req = BulkDeleteRequest(ids=[1, 2, 3])
    assert bulk_req.gallery_ids == [1, 2, 3]

    filt_req = FilteredDeleteRequest(tag="artist:abc", tag_mode="and", tag_match="fuzzy")
    assert filt_req.tags == "artist:abc"
    assert filt_req.tag_mode == "and"
    assert filt_req.tag_match == "fuzzy"


def test_download_cancellation_tracking() -> None:
    mark_download_cancelled(9999)
    assert is_download_cancelled(9999) is True
    clear_download_cancelled(9999)
    assert is_download_cancelled(9999) is False
    assert is_download_cancelled(None) is False


def test_auth_client_ip_and_proxy_defense() -> None:
    assert is_trusted_proxy("127.0.0.1") is True
    assert is_trusted_proxy("192.168.1.50") is True
    assert is_trusted_proxy("8.8.8.8") is False

    scope = {
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.195, 70.41.3.18, 150.172.238.178"),
        ],
    }
    req = Request(scope)
    assert client_ip(req) == "203.0.113.195"


@pytest.mark.asyncio
async def test_uow_with_existing_session() -> None:
    class MockSession:
        def __init__(self):
            self.tx_begun = False
            self.closed = False

        def in_transaction(self):
            return self.tx_begun

        async def begin(self):
            self.tx_begun = True

        async def commit(self):
            pass

        async def close(self):
            self.closed = True

    mock_sess = MockSession()
    uow = UnitOfWork(mock_sess)
    async with uow:
        assert uow.session is mock_sess
        assert mock_sess.tx_begun is True

    # External session should not be auto-closed by uow exit
    assert mock_sess.closed is False


def test_api_route_contracts_with_client(monkeypatch) -> None:
    from galleryvault.app import main
    from galleryvault.config import Settings

    monkeypatch.setattr(
        main,
        "_settings",
        lambda: Settings(auth_required=False, exhentai_base_url="https://exhentai.org"),
    )
    client = TestClient(app)

    # Test /api/logs
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "finished" in data

    # Test /api/logs/{task}/cancel
    resp = client.post("/api/logs/metadata/cancel")
    assert resp.status_code == 202
    assert resp.json()["status"] == "cancelling"

    # Test invalid cancel task 404
    resp = client.post("/api/logs/nonexistent_task/cancel")
    assert resp.status_code == 404


def test_gallery_router_aliases() -> None:
    from galleryvault.app.routers import galleries

    assert getattr(galleries, "gallery_page", None) is not None
    assert getattr(galleries, "gallery_thumbnail", None) is not None
    assert getattr(galleries, "gallery_list", None) is not None
    assert getattr(galleries, "gallery_detail", None) is not None
    assert getattr(galleries, "gallery_random", None) is not None
