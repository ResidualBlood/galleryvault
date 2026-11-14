"""G4: the EhClient facade and its feature modules share one session budget.

``EhSession`` owns the loop-wide page/image/archive semaphores; the facade
exposes them through properties, so every feature module and every rebuilt
client in the same event loop resolves the very same objects.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from galleryvault.config import Settings
from galleryvault.services.eh.session import _shared_limiter
from galleryvault.services.eh_client import EhClient


def _settings() -> Settings:
    return Settings(
        exhentai_base_url="https://exhentai.org",
        exhentai_cookies={"ipb_member_id": "1"},
    )


def _client() -> tuple[EhClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(base_url="https://exhentai.org")
    return EhClient(_settings(), client=http_client), http_client


@pytest.mark.asyncio
async def test_rebuilt_clients_share_all_three_loop_limiters() -> None:
    first, first_http = _client()
    second, second_http = _client()
    try:
        assert first._semaphore is second._semaphore
        assert first._semaphore is _shared_limiter("page", 6)
        assert first._semaphore._value == 6

        assert first._image_semaphore is second._image_semaphore
        assert first._image_semaphore is _shared_limiter("image", 12)
        assert first._image_semaphore._value == 12

        assert first._archive_semaphore is second._archive_semaphore
        assert first._archive_semaphore is _shared_limiter("archive", 2)
        assert first._archive_semaphore._value == 2
    finally:
        await first_http.aclose()
        await second_http.aclose()


@pytest.mark.asyncio
async def test_features_resolve_the_facade_limiters() -> None:
    client, http_client = _client()
    try:
        # Feature modules call ``client._semaphore`` / ``client._image_semaphore``
        # at request time; the facade properties forward to the one session.
        assert client._session._semaphore is client._semaphore
        assert client._session._image_semaphore is client._image_semaphore
        assert client._session._archive_semaphore is client._archive_semaphore
        assert client._session._stream_count == client._stream_count == 0
    finally:
        await http_client.aclose()


def test_different_event_loops_get_distinct_limiters() -> None:
    seen: list[asyncio.Semaphore] = []

    async def _run() -> None:
        client, http_client = _client()
        seen.append(client._semaphore)
        await http_client.aclose()

    asyncio.run(_run())
    asyncio.run(_run())

    assert seen[0] is not seen[1]
