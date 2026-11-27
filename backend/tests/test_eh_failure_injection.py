"""Failure injection for the split EhClient session/feature modules.

Pins two invariants that the composition split must not weaken:

* an upstream ``httpx`` transport failure inside ``_get`` still surfaces as
  ``EhClientError`` and returns the page budget;
* a mid-stream image timeout surfaces as ``EhClientError``, writes no file and
  returns the image budget, leaving ``_stream_count`` at zero.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from galleryvault.config import Settings
from galleryvault.services.eh_client import EhClient, EhClientError

IMAGE_URL = "https://node.hath.network/h/0123456789abcdef.jpg"


def _settings() -> Settings:
    return Settings(
        exhentai_base_url="https://exhentai.org",
        exhentai_cookies={"ipb_member_id": "1"},
    )


def _client(handler) -> tuple[EhClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return EhClient(_settings(), client=http_client), http_client


class _TimeoutStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"\xff\xd8\xff" + b"x" * 64
        raise httpx.ReadTimeout("upstream read timed out")


@pytest.mark.asyncio
async def test_get_read_timeout_maps_to_ehclient_error_and_releases_page_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream read timed out", request=request)

    client, http_client = _client(handler)
    try:
        with pytest.raises(EhClientError):
            await client._get("/g/1/abcdef/")
        assert client._semaphore._value == 6
        assert client._stream_count == 0
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_image_stream_timeout_returns_budget_and_writes_nothing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            stream=_TimeoutStream(),
        )

    client, http_client = _client(handler)
    dest = tmp_path / "page.jpg"
    try:
        with pytest.raises(EhClientError):
            await client.download_image_with_metadata(IMAGE_URL)
        assert client._image_semaphore._value == 12
        assert client._stream_count == 0
        assert not dest.exists()
        assert list(tmp_path.iterdir()) == []
    finally:
        await http_client.aclose()
