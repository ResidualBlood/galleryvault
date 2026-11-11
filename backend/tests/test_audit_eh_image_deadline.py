"""``image_download_timeout_seconds`` is an end-to-end image download deadline.

The per-chunk budget check can only fire after bytes arrive, so a node that
never answers the request (or stalls mid-body) used to hold a download worker
far beyond the configured budget.  These tests pin the wall-clock deadline
around the whole ``client.stream`` call, including the response-header wait.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest

from galleryvault.config import Settings
from galleryvault.services.eh_client import EhClient, EhImageSlowError

IMAGE_URL = "https://node.hath.network/h/0123456789abcdef.jpg"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "exhentai_base_url": "https://exhentai.org",
        "exhentai_cookies": {"ipb_member_id": "1"},
    }
    values.update(overrides)
    return Settings(**values)


def _client(handler: Any, settings: Settings) -> EhClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return EhClient(settings, client=http_client)


class _StallingStream(httpx.AsyncByteStream):
    """Yields a few chunks, then hangs until the deadline cancels the read."""

    def __init__(self, chunks: int = 2, chunk_size: int = 64) -> None:
        self._chunks = chunks
        self._chunk_size = chunk_size
        self.closed = False

    async def __aiter__(self) -> Any:
        for _ in range(self._chunks):
            yield b"\xff\xd8\xff" + b"x" * self._chunk_size
            await asyncio.sleep(0.02)
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


class _ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: int = 4, chunk_size: int = 1024, delay: float = 0.05) -> None:
        self._chunks = chunks
        self._chunk_size = chunk_size
        self._delay = delay

    async def __aiter__(self) -> Any:
        for _ in range(self._chunks):
            await asyncio.sleep(self._delay)
            yield b"\xff\xd8\xff" + b"x" * self._chunk_size


async def _download_expecting_deadline(eh: EhClient) -> float:
    """Call the download and fail fast (3s) if no deadline is enforced.

    The outer ``wait_for`` keeps the regression test bounded on code without
    the end-to-end deadline, where the download would otherwise hang forever.
    """
    started = time.monotonic()
    with pytest.raises(EhImageSlowError, match="deadline"):
        await asyncio.wait_for(eh.download_image_with_metadata(IMAGE_URL), 3.0)
    return time.monotonic() - started


@pytest.mark.asyncio
async def test_deadline_covers_response_header_wait() -> None:
    """A request that never returns headers must fail at the deadline."""
    hang = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await hang.wait()
        return httpx.Response(200, content=b"never reached")

    settings = _settings()
    # 0.3s is below ``Settings`` validation (>= 1) on purpose: production
    # values are whole seconds, the test needs a sub-second deadline.  The
    # in-loop budget keeps its own ``max(1, ...)`` clamp, so only the new
    # end-to-end deadline sees this value.
    settings.image_download_timeout_seconds = 0.3
    eh = _client(handler, settings)

    elapsed = await _download_expecting_deadline(eh)

    assert elapsed <= 1.0
    # Cancellation must release the in-flight accounting.
    assert eh.in_flight_requests == 0


@pytest.mark.asyncio
async def test_deadline_covers_stalled_body_after_chunks() -> None:
    """A body that stalls after a few chunks fails at the deadline, closed."""
    stream = _StallingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=stream, headers={"content-type": "image/jpeg"}
        )

    settings = _settings(image_slow_warmup_seconds=30, image_min_speed_kb_s=1)
    settings.image_download_timeout_seconds = 0.3
    eh = _client(handler, settings)

    elapsed = await _download_expecting_deadline(eh)

    assert elapsed <= 1.0
    assert stream.closed is True
    assert eh.in_flight_requests == 0


@pytest.mark.asyncio
async def test_small_image_within_deadline_still_succeeds() -> None:
    payload = b"\xff\xd8\xff" + b"y" * 500

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=payload, headers={"content-type": "image/jpeg"}
        )

    eh = _client(handler, _settings())

    data, content_type = await eh.download_image_with_metadata(IMAGE_URL)

    assert data == payload
    assert content_type == "image/jpeg"
    assert eh.in_flight_requests == 0


@pytest.mark.asyncio
async def test_chunked_body_within_deadline_still_succeeds() -> None:
    """Normal chunk delivery across the read window is not cut short."""
    stream = _ChunkedStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=stream, headers={"content-type": "image/jpeg"}
        )

    settings = _settings(image_slow_warmup_seconds=1, image_min_speed_kb_s=1)
    settings.image_download_timeout_seconds = 2.0
    eh = _client(handler, settings)

    data, content_type = await eh.download_image_with_metadata(IMAGE_URL)

    assert len(data) == 4 * (1024 + 3)
    assert content_type == "image/jpeg"
    assert eh.in_flight_requests == 0
