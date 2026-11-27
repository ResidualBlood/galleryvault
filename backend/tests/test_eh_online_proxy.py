"""Batch 15: optional server-side image proxy for the online reader.

Covers the fallback contract: a ``(gid, page)`` disk cache with atomic writes,
zero upstream calls on a hit, one shared upstream fetch for concurrent misses,
ETag/304, private caching, host allow-listing, 509 -> 429 without caching,
page-range 404s, mtime-based capacity pruning, and the fact that downloads
still spend the client's image semaphore and share the reader limit.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from galleryvault.app.routers.eh_online_proxy import eh_online_page_image
from galleryvault.config import Settings
from galleryvault.services import online_image_cache, online_resolve
from galleryvault.services.eh_client import EhClient

GID = 4323821
TOKEN = "3e444314f7"
SHOWKEY = "showkeyabc123"
SKIP_KEY = "111-222"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 128


def _ptoken(page: int) -> str:
    return f"{page:010x}"


def _image_url(page: int, *, host: str = "node1.hath.network") -> str:
    return (
        f"https://{host}/h/abc123def456-3456-800-1200-wbp/"
        f"keystamp=1700000000;fileindex={page};xres=1280/{page}.webp"
    )


def _preview_html(total: int, pages: list[int]) -> str:
    links = "".join(
        f'<a href="https://e-hentai.org/s/{_ptoken(page)}/{GID}-{page}">'
        f'<div style="width:200px;height:200px;background:transparent '
        f'url(https://ehgt.org/x.webp) -0px 0 no-repeat"></div></a>'
        for page in pages
    )
    return (
        f"<html><body><table><tr><td>Length:</td><td>{total} pages</td></tr>"
        f"</table><div id=\"gdt\">{links}</div></body></html>"
    )


def _viewer_html(page: int) -> str:
    return (
        "<html><head><script>"
        f'var showkey="{SHOWKEY}";'
        "</script></head><body>"
        f'<div id="i3"><img id="img" src="{_image_url(page)}" '
        'style="height:1200px;width:800px" '
        f'onerror="this.onerror=null; nl(\'{SKIP_KEY}\')" /></div>'
        "</body></html>"
    )


def _showpage_json(page: int) -> dict[str, str]:
    return {
        "i3": f'<img src="{_image_url(page)}" style="height:1200px;width:800px" />',
        "i6": f"<a onclick=\"nl('{SKIP_KEY}')\">reload</a>",
    }


def _seed(pages: list[int], total: int) -> None:
    online_resolve._showkey_set(GID, TOKEN, SHOWKEY)
    online_resolve._ptokens_set(
        GID,
        TOKEN,
        0,
        {"ptokens": {page: _ptoken(page) for page in pages}, "total": total},
    )


class _Upstream:
    """Mock ExHentai page/preview/showpage plus the H@H image host."""

    def __init__(
        self,
        *,
        total: int = 20,
        pages: list[int] | None = None,
        image_status: int = 200,
    ) -> None:
        self.total = total
        self.pages = pages or list(range(1, total + 1))
        self.image_status = image_status
        self.showpage_pages: list[int] = []
        self.image_requests: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api.php":
            page = int(json.loads(request.content.decode("utf-8"))["page"])
            self.showpage_pages.append(page)
            return httpx.Response(200, json=_showpage_json(page))
        if path.startswith(f"/g/{GID}/"):
            return httpx.Response(200, text=_preview_html(self.total, self.pages))
        if path.startswith("/s/"):
            page = int(path.rsplit("-", 1)[-1])
            return httpx.Response(200, text=_viewer_html(page))
        if path.startswith("/h/"):
            self.image_requests.append(str(request.url))
            if self.image_status != 200:
                return httpx.Response(self.image_status)
            return httpx.Response(
                200, content=PNG, headers={"content-type": "image/png"}
            )
        return httpx.Response(404)


class _Manager:
    def __init__(self, client: EhClient) -> None:
        self.client = client

    @asynccontextmanager
    async def client_context(self):
        yield self.client


def _make_client(handler: Any) -> EhClient:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://e-hentai.org",
        follow_redirects=True,
    )
    return EhClient(
        Settings(exhentai_base_url="https://e-hentai.org"), client=http_client
    )


def _request(if_none_match: str | None = None) -> Request:
    headers = []
    if if_none_match:
        headers.append((b"if-none-match", if_none_match.encode()))
    return Request({"type": "http", "method": "GET", "headers": headers})


async def _call(
    client: EhClient, page: int, request: Request | None = None
) -> Any:
    return await eh_online_page_image(
        GID, TOKEN, page, request or _request(), client_mgr=_Manager(client)
    )


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(
        exhentai_base_url="https://e-hentai.org",
        thumbnail_cache_dir=str(tmp_path / "thumbs"),
        **overrides,
    )


def _cache_file(tmp_path: Path, page: int) -> Path:
    return online_image_cache.page_cache_path(
        online_image_cache.online_cache_dir(_settings(tmp_path)), GID, page
    )


# --- cache hit / ETag ------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_makes_no_upstream_calls(tmp_path: Path, runtime: Any) -> None:
    runtime(settings=_settings(tmp_path))
    path = _cache_file(tmp_path, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)

    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)), 20)
    try:
        response = await _call(client, 2)
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == []
    assert upstream.image_requests == []
    assert response.media_type == "image/png"
    assert response.headers["cache-control"] == "private, max-age=86400"
    assert "etag" in response.headers


@pytest.mark.asyncio
async def test_if_none_match_returns_304(tmp_path: Path, runtime: Any) -> None:
    runtime(settings=_settings(tmp_path))
    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)), 20)
    try:
        first = await _call(client, 2)
        etag = first.headers["etag"]
        second = await _call(client, 2, _request(etag))
        weak = await _call(client, 2, _request(f"W/{etag}"))
    finally:
        await client.client.aclose()

    assert first.status_code == 200
    assert second.status_code == 304
    assert weak.status_code == 304
    assert upstream.showpage_pages == [2]
    assert len(upstream.image_requests) == 1


# --- dedupe / caching ------------------------------------------------------


@pytest.mark.asyncio
async def test_five_concurrent_same_page_hit_upstream_once(
    tmp_path: Path, runtime: Any
) -> None:
    runtime(settings=_settings(tmp_path))
    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)), 20)
    try:
        results = await asyncio.gather(*(_call(client, 3) for _ in range(5)))
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == [3]
    assert len(upstream.image_requests) == 1
    assert all(result.status_code == 200 for result in results)
    assert _cache_file(tmp_path, 3).read_bytes() == PNG


# --- failures --------------------------------------------------------------


@pytest.mark.asyncio
async def test_disallowed_host_is_rejected_without_download(
    tmp_path: Path, runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime(settings=_settings(tmp_path))
    upstream = _Upstream()
    client = _make_client(upstream)

    async def _evil_resolve(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"state": "ok", "page": 2, "url": "https://evil.example.com/x.png"}

    monkeypatch.setattr(online_image_cache, "resolve_online_page", _evil_resolve)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await _call(client, 2)
    finally:
        await client.client.aclose()

    assert excinfo.value.status_code == 502
    assert excinfo.value.detail == {"code": "host_not_allowed"}
    assert upstream.image_requests == []
    assert not _cache_file(tmp_path, 2).exists()


@pytest.mark.asyncio
async def test_509_is_429_and_never_cached(tmp_path: Path, runtime: Any) -> None:
    runtime(settings=_settings(tmp_path))
    upstream = _Upstream(image_status=509)
    client = _make_client(upstream)
    _seed(list(range(1, 21)), 20)
    try:
        for _ in range(2):
            with pytest.raises(HTTPException) as excinfo:
                await _call(client, 2)
            assert excinfo.value.status_code == 429
            assert excinfo.value.detail == {"code": "image_limit"}
    finally:
        await client.client.aclose()

    assert len(upstream.image_requests) == 2
    assert not _cache_file(tmp_path, 2).exists()


@pytest.mark.asyncio
async def test_page_out_of_range_is_404_without_download(
    tmp_path: Path, runtime: Any
) -> None:
    runtime(settings=_settings(tmp_path))
    upstream = _Upstream(total=2, pages=[1, 2])
    client = _make_client(upstream)
    _seed([1, 2], 2)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await _call(client, 5)
    finally:
        await client.client.aclose()

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == {"code": "page_out_of_range"}
    assert upstream.image_requests == []


# --- capacity --------------------------------------------------------------


@pytest.mark.asyncio
async def test_capacity_prunes_oldest_file(tmp_path: Path, runtime: Any) -> None:
    settings = _settings(tmp_path, online_cache_max_mb=16)
    runtime(settings=settings)
    root = online_image_cache.online_cache_dir(settings)
    old = root / "1" / "1.img"
    old.parent.mkdir(parents=True, exist_ok=True)
    with old.open("wb") as handle:
        handle.truncate(16 * 1024 * 1024)
    os.utime(old, (1_000_000, 1_000_000))

    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)), 20)
    try:
        await _call(client, 2)
    finally:
        await client.client.aclose()

    assert not old.exists()
    assert _cache_file(tmp_path, 2).is_file()


def test_prune_cache_removes_oldest_until_under_limit(tmp_path: Path) -> None:
    root = tmp_path / "online"
    paths = []
    for index in range(3):
        path = root / str(index) / f"{index}.img"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 100)
        os.utime(path, (1_000 + index, 1_000 + index))
        paths.append(path)

    removed = online_image_cache.prune_cache(root, max_bytes=250)

    assert removed == 1
    assert not paths[0].exists()
    assert paths[1].exists() and paths[2].exists()


# --- budgets ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_waits_for_image_semaphore(
    tmp_path: Path, runtime: Any
) -> None:
    runtime(settings=_settings(tmp_path))
    upstream = _Upstream()
    client = _make_client(upstream)
    client._image_semaphore = asyncio.Semaphore(1)  # type: ignore[assignment]
    await client._image_semaphore.acquire()
    _seed(list(range(1, 21)), 20)
    try:
        task = asyncio.create_task(_call(client, 2))
        for _ in range(20):
            await asyncio.sleep(0.01)
        assert upstream.image_requests == []

        client._image_semaphore.release()
        response = await asyncio.wait_for(task, timeout=5)
    finally:
        await client.client.aclose()

    assert response.status_code == 200
    assert len(upstream.image_requests) == 1


@pytest.mark.asyncio
async def test_shares_reader_concurrency_limit(
    tmp_path: Path, runtime: Any
) -> None:
    runtime(
        settings=_settings(tmp_path, online_reader_concurrency=1)
    )
    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)), 20)
    limiter = online_resolve._reader_limiter(1)
    await limiter.acquire()
    try:
        task = asyncio.create_task(_call(client, 2))
        for _ in range(20):
            await asyncio.sleep(0.01)
        assert upstream.showpage_pages == []
        assert upstream.image_requests == []

        limiter.release()
        response = await asyncio.wait_for(task, timeout=5)
    finally:
        await client.client.aclose()

    assert response.status_code == 200
    assert upstream.showpage_pages == [2]
    assert len(upstream.image_requests) == 1


# --- route wiring ----------------------------------------------------------


def _all_paths(routes: Any) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        nested = getattr(route, "original_router", None)
        if nested is not None:
            paths |= _all_paths(nested.routes)
        elif hasattr(route, "routes"):
            paths |= _all_paths(route.routes)
    return paths


def test_image_route_registered() -> None:
    from galleryvault.app.main import app

    assert "/api/eh/galleries/{gid}/{token}/pages/{n}/image" in _all_paths(app.routes)
