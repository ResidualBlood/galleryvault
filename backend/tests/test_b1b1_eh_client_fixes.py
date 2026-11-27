"""Regression tests for the batch-1 EH client consistency fixes.

Covers (review 02-eh-consistency):
- P2-5  ``parse_login_state`` requires a positive settings-page marker
- P2-6  ``fetch_favorites`` verifies the favorites page and both quote styles
- P2-9  limiter sharing across client rebuilds + drain before closing a
        retired client
- P2-12 ``download_archive`` uses an archive budget and the throughput watchdog
- P3-2  cookie-health tracking keys off ``ok`` (not ``valid``/``expired``)
- P3-4  ``fetch_gmetadata`` keeps already-fetched chunks when one fails
- P3-6  ``parse_gallery_url`` validates schemeless absolute hosts
- P3-10 ``retire_client`` logs instead of silently dropping the close task
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from galleryvault.app.core.eh_client_manager import EhClientManager
from galleryvault.config import Settings
from galleryvault.services import eh_client as eh_client_module
from galleryvault.services.eh_client import (
    EhClient,
    EhClientError,
    parse_gallery_url,
    parse_login_state,
)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "exhentai_base_url": "https://exhentai.org",
        "exhentai_cookies": {"ipb_member_id": "1"},
    }
    values.update(overrides)
    return Settings(**values)


def _client(handler: Any, **settings_overrides: Any) -> EhClient:
    http_client = httpx.AsyncClient(
        base_url="https://exhentai.org",
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return EhClient(_settings(**settings_overrides), client=http_client)


# --------------------------------------------------------------------------
# P2-5: check_login / parse_login_state positive classification
# --------------------------------------------------------------------------


def test_login_state_requires_settings_page_marker() -> None:
    assert parse_login_state("<form action='uconfig.php'>...</form>") == "ok"
    assert parse_login_state("<html><h1>User Control Panel</h1></html>") == "ok"
    # Previously any non-empty body that was not "expired login session"
    # counted as logged in.
    assert parse_login_state("<html>Just a moment...</html>") == "failed"
    assert parse_login_state("<html>Gallery listing</html>") == "failed"
    assert parse_login_state("<p>You are not logged in.</p>") == "not_logged_in"
    assert parse_login_state("expired login session") == "not_logged_in"


async def test_check_login_reports_failed_for_challenge_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Checking your browser…</html>")

    client = _client(handler)
    state, detail = await client.check_login()
    assert state == "failed"
    assert detail == "HTTP 200"


# --------------------------------------------------------------------------
# P2-6: fetch_favorites page identity + quote styles
# --------------------------------------------------------------------------


async def test_fetch_favorites_rejects_non_favorites_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Session expired: ExHentai bounces /favorites.php to the front page,
        # which is full of /g/ links that must NOT be imported as favorites.
        if request.url.path == "/favorites.php":
            return httpx.Response(302, headers={"Location": "https://exhentai.org/"})
        return httpx.Response(200, text='<a href="/g/1/aaaaaa/">Front page gallery</a>')

    client = _client(handler)
    with pytest.raises(EhClientError, match="left the favorites page"):
        await client.fetch_favorites(0)


async def test_fetch_favorites_rejects_login_body_on_favorites_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>You must be logged in</html>")

    client = _client(handler)
    with pytest.raises(EhClientError, match="authentication"):
        await client.fetch_favorites(0)


async def test_fetch_favorites_accepts_single_quoted_nexturl() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.params.get("next"):
            body = '<a href="/g/2000/bbbbbb/">Second</a>'
        else:
            body = (
                '<a href="/g/1000/aaaaaa/">First</a>'
                "<script>var nexturl='https://exhentai.org/favorites.php?"
                "favcat=0&amp;next=1000-1770000000';</script>"
            )
        return httpx.Response(200, text=body)

    client = _client(handler)
    items = await client.fetch_favorites(0)
    assert [item.gid for item in items] == [1000, 2000]
    assert "next=1000-1770000000" in requests[1]


# --------------------------------------------------------------------------
# P2-9: shared limiters and drain-before-close
# --------------------------------------------------------------------------


async def test_rebuilt_clients_share_limiters_in_same_loop() -> None:
    http_client = httpx.AsyncClient(base_url="https://exhentai.org")
    first = EhClient(_settings(), client=http_client)
    second = EhClient(_settings(), client=http_client)
    assert first._semaphore is second._semaphore
    assert first._image_semaphore is second._image_semaphore
    assert first._archive_semaphore is second._archive_semaphore
    # A different budget is a different limiter (explicit config change).
    third = EhClient(_settings(), client=http_client, max_concurrency=3)
    assert third._semaphore is not first._semaphore


class _InFlightClient:
    def __init__(self) -> None:
        self.closed = False
        self.in_flight_requests = 3

    async def aclose(self) -> None:
        self.closed = True


async def test_retire_client_waits_for_in_flight_transfers() -> None:
    manager = EhClientManager()
    client = _InFlightClient()

    async def _finish_soon() -> None:
        await asyncio.sleep(0)
        client.in_flight_requests = 0

    manager.retire_client(client, delay=0)
    assert client not in manager._retiring_clients or not client.closed
    asyncio.get_running_loop().create_task(_finish_soon())
    for _ in range(100):
        if client.closed:
            break
        await asyncio.sleep(0.01)
    assert client.closed is True
    assert client not in manager.retiring_clients


# --------------------------------------------------------------------------
# P2-12: archive downloads take a budget and enforce the throughput watchdog
# --------------------------------------------------------------------------


class _SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"a" * 64
        await asyncio.sleep(1.2)
        yield b"b" * 64


async def test_download_archive_uses_archive_semaphore(tmp_path: Path) -> None:
    release = asyncio.Event()

    class _BlockingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await release.wait()
            yield b"z" * 16

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-length": "16"}, stream=_BlockingStream()
        )

    client = _client(handler)
    dest = tmp_path / "archive.zip"
    task = asyncio.create_task(
        client.download_archive("https://e-hentai.org/archiver.php?x=1", dest)
    )
    for _ in range(100):
        if client.in_flight_requests:
            break
        await asyncio.sleep(0.01)
    assert client.in_flight_requests == 1
    assert client._archive_semaphore._value == 1  # budget of 2, one taken
    release.set()
    await task
    assert client.in_flight_requests == 0
    assert client._archive_semaphore._value == 2
    assert dest.read_bytes() == b"z" * 16


async def test_download_archive_aborts_throttled_transfer(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-length": "128"}, stream=_SlowStream()
        )

    client = _client(
        handler, image_slow_warmup_seconds=1, image_min_speed_kb_s=1024
    )
    dest = tmp_path / "archive.zip"
    with pytest.raises(EhClientError, match="throttled"):
        await client.download_archive("https://e-hentai.org/archiver.php?x=1", dest)
    assert client.in_flight_requests == 0
    assert client._archive_semaphore._value == 2


# --------------------------------------------------------------------------
# P3-2: cookie-health tracker state names
# --------------------------------------------------------------------------


class _Tracker:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


def test_cookie_health_tracker_keys_off_ok_state() -> None:
    tracker = _Tracker()
    eh_client_module._report_cookie_health(
        tracker, {"state": "ok", "detail": "HTTP 200"}
    )
    assert tracker.updates == [{"done": 1, "total": 1, "stage": "ok"}]

    failing = _Tracker()
    eh_client_module._report_cookie_health(
        failing, {"state": "not_logged_in", "detail": "HTTP 200"}
    )
    assert failing.updates[0] == {"done": 0, "total": 1, "stage": "not_logged_in"}
    assert failing.updates[1] == {"last_error": "HTTP 200"}


# --------------------------------------------------------------------------
# P3-4: fetch_gmetadata partial results
# --------------------------------------------------------------------------


async def test_fetch_gmetadata_keeps_successful_chunks() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "gmetadata": [
                        {"gid": 1000 + i, "token": "tok", "title": f"T{i}"}
                        for i in range(25)
                    ]
                },
            )
        return httpx.Response(500, text="boom")

    client = _client(handler)
    pairs = [(1000 + i, "tok") for i in range(30)]
    result = await client.fetch_gmetadata(pairs)
    assert len(result) == 25
    assert result[1000]["title"] == "T0"


async def test_fetch_gmetadata_raises_when_every_chunk_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _client(handler)
    with pytest.raises(EhClientError):
        await client.fetch_gmetadata([(1, "tok")])


# --------------------------------------------------------------------------
# P3-6: schemeless absolute URLs are host-checked
# --------------------------------------------------------------------------


def test_parse_gallery_url_rejects_schemeless_foreign_host() -> None:
    with pytest.raises(ValueError, match="exhentai.org"):
        parse_gallery_url("evil.com/g/1/abcdef/")
    # Relative paths and bare gid/token pairs keep working.
    assert parse_gallery_url("/g/1/abcdef/") == (1, "abcdef")
    assert parse_gallery_url("123/abcdef") == (123, "abcdef")
    assert parse_gallery_url("exhentai.org/g/1/abcdef/") == (1, "abcdef")


# --------------------------------------------------------------------------
# P3-10: retirement failures are logged, not swallowed
# --------------------------------------------------------------------------


def test_retire_client_logs_when_no_task_can_be_started(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = EhClientManager()
    client = _InFlightClient()
    with caplog.at_level(logging.WARNING):
        # Sync context: no running loop, so the close task cannot be scheduled.
        manager.retire_client(client, delay=0)
    messages = [record.getMessage() for record in caplog.records]
    assert any("retired EhClient" in message for message in messages)
    assert client.closed is False
