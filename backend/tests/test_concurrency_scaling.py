from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import get_settings
from galleryvault.services import download_worker, tag_sync_worker
from galleryvault.services.download_worker import (
    adjust_download_concurrency,
)
from galleryvault.services.settings_service import refresh_services
from galleryvault.services.tag_sync_worker import (
    adjust_tag_sync_concurrency,
)


@pytest.mark.asyncio
async def test_adjust_download_concurrency_scaling():
    # Reset tasks
    for t in download_worker._worker_tasks:
        t.cancel()
    download_worker._worker_tasks.clear()

    # Scale to 2
    adjust_download_concurrency(2)
    assert len(download_worker._worker_tasks) == 2
    tasks_initial = list(download_worker._worker_tasks)

    # Scale up to 4
    adjust_download_concurrency(4)
    assert len(download_worker._worker_tasks) == 4
    # The first 2 tasks should still be the initial tasks
    assert download_worker._worker_tasks[0] == tasks_initial[0]
    assert download_worker._worker_tasks[1] == tasks_initial[1]

    # Scale down to 1
    adjust_download_concurrency(1)
    assert download_worker._target_download_concurrency == 1
    # Cooperative drain: tasks are NOT forcibly cancelled immediately
    assert not tasks_initial[1].cancelled()

    # Yield loop so cooperatively draining tasks wake up, exit, and remove themselves
    await asyncio.sleep(0.05)
    assert len(download_worker._worker_tasks) == 1
    # Drained task exited normally without being cancelled
    assert tasks_initial[1].done()
    assert not tasks_initial[1].cancelled()
    assert tasks_initial[1].exception() is None

    # Cleanup
    for t in download_worker._worker_tasks:
        t.cancel()
    download_worker._worker_tasks.clear()


@pytest.mark.asyncio
async def test_adjust_tag_sync_concurrency_scaling():
    for t in tag_sync_worker._worker_tasks:
        t.cancel()
    tag_sync_worker._worker_tasks.clear()

    # Scale to 2
    adjust_tag_sync_concurrency(2)
    assert len(tag_sync_worker._worker_tasks) == 2
    tasks_initial = list(tag_sync_worker._worker_tasks)

    # Scale up to 3
    adjust_tag_sync_concurrency(3)
    assert len(tag_sync_worker._worker_tasks) == 3

    # Scale down to 1
    adjust_tag_sync_concurrency(1)
    assert tag_sync_worker._target_tag_sync_concurrency == 1
    # Cooperative drain: tasks are NOT forcibly cancelled immediately
    assert not tasks_initial[1].cancelled()

    # Yield loop so cooperatively draining tasks wake up, exit, and remove themselves
    await asyncio.sleep(0.05)
    assert len(tag_sync_worker._worker_tasks) == 1
    # Drained task exited normally without being cancelled
    assert tasks_initial[1].done()
    assert not tasks_initial[1].cancelled()
    assert tasks_initial[1].exception() is None

    # Cleanup
    for t in tag_sync_worker._worker_tasks:
        t.cancel()
    tag_sync_worker._worker_tasks.clear()


@pytest.mark.asyncio
async def test_refresh_services_triggers_concurrency_adjustment(monkeypatch: pytest.MonkeyPatch):
    from galleryvault.services import settings_service

    dl_adjusted = []
    ts_adjusted = []

    monkeypatch.setattr(
        download_worker, "adjust_download_concurrency", lambda c=None: dl_adjusted.append(c)
    )
    monkeypatch.setattr(
        tag_sync_worker, "adjust_tag_sync_concurrency", lambda c=None: ts_adjusted.append(c)
    )

    class FakeClient:
        async def aclose(self):
            pass

    class FakeNotifier:
        async def aclose(self):
            pass

        async def flush_summary(self) -> bool:
            return False

    monkeypatch.setattr(settings_service, "start_telegram_bot", lambda: None)
    monkeypatch.setattr(settings_service, "EhClient", lambda *a, **k: FakeClient())
    monkeypatch.setattr(settings_service, "Downloader", lambda *a, **k: object())
    monkeypatch.setattr(settings_service, "TelegramNotifier", lambda *a, **k: FakeNotifier())
    monkeypatch.setattr(settings_service, "FavoritesService", lambda *a, **k: object())
    monkeypatch.setattr(settings_service, "FavoriteDownloadQueue", lambda: object())

    # Case 1: background worker tasks are not active -> no adjustment called
    app_state.extra["download_worker_task"] = None
    app_state.extra["tag_sync_worker_task"] = None

    await refresh_services()
    assert dl_adjusted == []
    assert ts_adjusted == []

    # Case 2: background worker tasks are active -> adjustments called with settings values
    mock_dl_task = MagicMock()
    mock_dl_task.done.return_value = False
    mock_ts_task = MagicMock()
    mock_ts_task.done.return_value = False

    app_state.extra["download_worker_task"] = mock_dl_task
    app_state.extra["tag_sync_worker_task"] = mock_ts_task

    await refresh_services()
    assert len(dl_adjusted) == 1
    assert len(ts_adjusted) == 1
    current_settings = app_state.settings or get_settings()
    assert dl_adjusted[0] == current_settings.download_concurrency
    assert ts_adjusted[0] == current_settings.tag_sync_concurrency
