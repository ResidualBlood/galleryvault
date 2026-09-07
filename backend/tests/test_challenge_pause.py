"""Unit tests for ExHentai 302 anti-abuse challenge handling and auto-resume."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.download_worker import (
    _resume_challenge_pause,
    _run_download_inner,
    _trigger_challenge_pause,
    challenge_probe_loop,
)
from galleryvault.services.downloader import DownloadTask
from galleryvault.services.eh_client import EhChallengeError, EhClient


@pytest.fixture(autouse=True)
def reset_app_state():
    orig_settings = app_state.settings
    orig_telegram = app_state.telegram
    orig_factory = app_state.session_factory
    orig_extra = dict(app_state.extra)
    orig_downloader = app_state.downloader
    orig_eh_client = app_state.eh_client
    yield
    app_state.settings = orig_settings
    app_state.telegram = orig_telegram
    app_state.session_factory = orig_factory
    app_state.downloader = orig_downloader
    app_state.eh_client = orig_eh_client
    app_state.extra.clear()
    app_state.extra.update(orig_extra)


@pytest.mark.asyncio
async def test_eh_challenge_error_fetch_gallery_metadata() -> None:
    settings = Settings(exhentai_base_url="https://exhentai.org")
    client = EhClient(settings)

    mock_resp = MagicMock()
    mock_resp.url.path = "/"
    mock_resp.text = ""

    with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(EhChallengeError):
            await client.fetch_gallery_metadata(12345, "token123")


@pytest.mark.asyncio
async def test_eh_challenge_error_fetch_gallery() -> None:
    settings = Settings(exhentai_base_url="https://exhentai.org")
    client = EhClient(settings)

    mock_resp = MagicMock()
    mock_resp.url.path = "/"
    mock_resp.text = ""

    with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(EhChallengeError):
            await client.fetch_gallery(12345, "token123")


@pytest.mark.asyncio
async def test_eh_probe_challenge() -> None:
    import httpx

    settings = Settings(exhentai_base_url="https://exhentai.org")
    client = EhClient(settings)

    # 1. Challenged response (redirected to remoteapi / poni=no)
    resp_challenged = MagicMock()
    resp_challenged.url = httpx.URL("https://exhentai.org/?poni=no")
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=resp_challenged):
        assert not await client.probe_challenge("/g/123/abc/")

    # 2. Cleared response (remains on /g/ path)
    resp_cleared = MagicMock()
    resp_cleared.url = httpx.URL("https://exhentai.org/g/123/abc/")
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=resp_cleared):
        assert await client.probe_challenge("/g/123/abc/")


@pytest.mark.asyncio
async def test_download_worker_challenge_handling_and_probe_loop() -> None:
    test_settings = Settings(global_paused=False, telegram_bot_token="test_token", telegram_chat_ids=["123"])
    app_state.settings = test_settings
    app_state.extra.clear()
    app_state.session_factory = None

    mock_telegram = MagicMock()
    mock_telegram.send_message = AsyncMock()
    app_state.telegram = mock_telegram

    # Test trigger pause
    await _trigger_challenge_pause("/g/100/tok/")
    assert app_state.settings.global_paused is True
    assert app_state.extra.get("auto_resume_challenge") is True
    assert app_state.extra.get("challenge_sample_path") == "/g/100/tok/"
    mock_telegram.send_message.assert_awaited_once_with("🚨 触发 302 临时挑战，系统自动暂停下载")

    # Test resume pause
    mock_telegram.send_message.reset_mock()
    await _resume_challenge_pause()
    assert app_state.settings.global_paused is False
    assert app_state.extra.get("auto_resume_challenge") is False
    assert "challenge_sample_path" not in app_state.extra
    mock_telegram.send_message.assert_awaited_once_with("✅ 302 临时挑战解除，自动恢复下载")


@pytest.mark.asyncio
async def test_download_worker_handles_challenge_error() -> None:
    test_settings = Settings(global_paused=False, telegram_bot_token="test_token", telegram_chat_ids=["123"])
    app_state.settings = test_settings
    app_state.extra.clear()

    mock_telegram = MagicMock()
    mock_telegram.send_message = AsyncMock()
    app_state.telegram = mock_telegram

    mock_downloader = MagicMock()
    mock_downloader.execute = AsyncMock(side_effect=EhChallengeError("ExHentai 302 challenge"))
    app_state.downloader = mock_downloader

    mock_row = MagicMock()
    mock_row.id = 1
    mock_row.gid = 999
    mock_row.status = "downloading"
    mock_row.retry_count = 0
    mock_row.max_retries = 5

    class MockAsyncContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, model, task_id):
            return mock_row

        def begin(self):
            return self

    app_state.session_factory = lambda: MockAsyncContext()

    task = DownloadTask(999, "token_xyz", "Test Title", id=1)
    with patch("galleryvault.services.download_worker.DownloadRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.record_attempt = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        await _run_download_inner(task)

    assert mock_row.status == "pending"
    assert mock_row.retry_count == 0  # not incremented
    assert "302 临时挑战" in mock_row.error_message
    assert app_state.settings.global_paused is True
    assert app_state.extra.get("auto_resume_challenge") is True


@pytest.mark.asyncio
async def test_challenge_probe_loop_clears_pause() -> None:
    test_settings = Settings(global_paused=True, telegram_bot_token="test_token", telegram_chat_ids=["123"])
    app_state.settings = test_settings
    app_state.extra["auto_resume_challenge"] = True
    app_state.extra["challenge_sample_path"] = "/g/999/tok/"
    app_state.session_factory = None

    mock_telegram = MagicMock()
    mock_telegram.send_message = AsyncMock()
    app_state.telegram = mock_telegram

    mock_client = MagicMock()
    mock_client.probe_challenge = AsyncMock(return_value=True)
    app_state.eh_client = mock_client

    with patch("galleryvault.services.download_worker._CHALLENGE_PROBE_INTERVAL", 0.01):
        task = asyncio.create_task(challenge_probe_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert app_state.settings.global_paused is False
    assert app_state.extra.get("auto_resume_challenge") is False
    mock_telegram.send_message.assert_awaited_once_with("✅ 302 临时挑战解除，自动恢复下载")
