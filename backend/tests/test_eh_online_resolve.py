"""Batch 14: single-page online resolve (direct H@H URLs).

Covers the PLAN §3.3/§3.4 contract: one upstream ``showpage`` per page in the
steady state, 600 s result caching, in-flight dedupe, ``nl`` node switching on
retry, 509 placeholder detection, host allow-listing, page-range 404s, the
``online_reader_concurrency`` self-limit, state passthrough for auth/banned,
and the two new settings keys.  The image semaphore must never be touched.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from galleryvault.app.middleware import SECURITY_HEADERS
from galleryvault.app.routers.eh_online import eh_online_resolve_page
from galleryvault.app.schemas import SettingsRequest
from galleryvault.app.state import app_state
from galleryvault.config import EDITABLE_SETTINGS, Settings
from galleryvault.services import online_resolve
from galleryvault.services.eh_client import EhClient
from galleryvault.services.settings_service import settings_public, update_runtime_settings

GID = 4323821
TOKEN = "3e444314f7"
SHOWKEY = "showkeyabc123"
SKIP_KEY = "111-222"


def _ptoken(page: int) -> str:
    return f"{page:010x}"


def _image_url(page: int, *, host: str = "node1.hath.network", name: str | None = None) -> str:
    filename = name or f"{page}.webp"
    return (
        f"https://{host}/h/abc123def456-3456-800-1200-wbp/"
        f"keystamp=1700000000;fileindex={page};xres=1280/{filename}"
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


def _viewer_html(page: int, image_url: str | None = None) -> str:
    url = image_url or _image_url(page, host="node2.hath.network")
    return (
        "<html><head><script>"
        f'var showkey="{SHOWKEY}";'
        "</script></head><body>"
        f'<a href="https://e-hentai.org/s/{_ptoken(page)}/{GID}-{page}"></a>'
        f'<div id="i3"><img id="img" src="{url}" '
        'style="height:1200px;width:800px" '
        f'onerror="this.onerror=null; nl(\'{SKIP_KEY}\')" /></div>'
        "</body></html>"
    )


def _showpage_json(page: int, image_url: str | None = None) -> dict[str, str]:
    url = image_url or _image_url(page)
    return {
        "i3": f'<img src="{url}" style="height:1200px;width:800px" />',
        "i6": f"<a onclick=\"nl('{SKIP_KEY}')\">reload</a>",
    }


def _seed(
    pages: list[int],
    *,
    total: int | None = None,
    preview_page: int = 0,
    showkey: str = SHOWKEY,
) -> None:
    online_resolve._showkey_set(GID, TOKEN, showkey)
    online_resolve._ptokens_set(
        GID,
        TOKEN,
        preview_page,
        {"ptokens": {page: _ptoken(page) for page in pages}, "total": total or max(pages)},
    )


class _Upstream:
    """Mock ExHentai: preview HTML, viewer HTML and the showpage JSON API."""

    def __init__(
        self,
        *,
        total: int = 20,
        pages: list[int] | None = None,
        banned: str | None = None,
        showpage_images: dict[int, str] | None = None,
        viewer_images: dict[int, str] | None = None,
        gate: asyncio.Event | None = None,
        entered: asyncio.Event | None = None,
    ) -> None:
        self.total = total
        self.pages = pages or list(range(1, total + 1))
        self.banned = banned
        self.showpage_images = showpage_images or {}
        self.viewer_images = viewer_images or {}
        self.gate = gate
        self.entered = entered
        self.showpage_pages: list[int] = []
        self.gallery_gets = 0
        self.viewer_urls: list[str] = []
        self.requests: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        path = request.url.path
        if self.banned is not None and path.startswith(f"/g/{GID}/"):
            return httpx.Response(200, text=self.banned)
        if path == "/api.php":
            payload = json.loads(request.content.decode("utf-8"))
            page = int(payload["page"])
            self.showpage_pages.append(page)
            if self.gate is not None and self.entered is not None:
                self.entered.set()
                await self.gate.wait()
            return httpx.Response(
                200, json=_showpage_json(page, self.showpage_images.get(page))
            )
        if path.startswith(f"/g/{GID}/"):
            self.gallery_gets += 1
            return httpx.Response(200, text=_preview_html(self.total, self.pages))
        if path.startswith("/s/"):
            self.viewer_urls.append(str(request.url))
            page = int(path.rsplit("-", 1)[-1])
            return httpx.Response(
                200, text=_viewer_html(page, self.viewer_images.get(page))
            )
        return httpx.Response(404)


class _Manager:
    def __init__(self, client: EhClient) -> None:
        self.client = client

    @asynccontextmanager
    async def client_context(self):
        yield self.client


class _ForbiddenSemaphore:
    async def __aenter__(self) -> None:
        raise AssertionError("resolve must not acquire the image semaphore")

    async def __aexit__(self, *_: object) -> bool:
        return False


def _make_client(handler: Any) -> EhClient:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://e-hentai.org",
        follow_redirects=True,
    )
    return EhClient(
        Settings(exhentai_base_url="https://e-hentai.org"), client=http_client
    )


async def _resolve(client: EhClient, page: int, retry: int = 0) -> dict[str, Any]:
    return await online_resolve.resolve_online_page(
        _Manager(client), GID, TOKEN, page, retry=retry
    )


# --- steady state / caching ------------------------------------------------


@pytest.mark.asyncio
async def test_cached_showkey_costs_exactly_one_showpage() -> None:
    upstream = _Upstream()
    client = _make_client(upstream)
    client._image_semaphore = _ForbiddenSemaphore()  # type: ignore[assignment]
    _seed(list(range(1, 21)))
    try:
        out = await _resolve(client, 2)
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == [2]
    assert upstream.gallery_gets == 0
    assert upstream.viewer_urls == []
    assert set(out) == {"state", "page", "url", "width", "height", "expires_at"}
    assert out["state"] == "ok"
    assert out["page"] == 2
    assert out["url"] == _image_url(2)
    assert (out["width"], out["height"]) == (800, 1200)
    assert datetime.fromisoformat(out["expires_at"]).timestamp() > 0
    body = json.dumps(out)
    assert SHOWKEY not in body
    assert _ptoken(2) not in body


@pytest.mark.asyncio
async def test_five_concurrent_same_page_share_one_upstream() -> None:
    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)))
    try:
        results = await asyncio.gather(*(_resolve(client, 3) for _ in range(5)))
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == [3]
    assert all(result == results[0] for result in results)


@pytest.mark.asyncio
async def test_result_cache_serves_600_seconds_then_re_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(online_resolve, "_now", lambda: clock[0])
    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)))
    try:
        first = await _resolve(client, 2)
        assert upstream.showpage_pages == [2]

        clock[0] += 599.0
        cached = await _resolve(client, 2)
        assert upstream.showpage_pages == [2]
        assert cached == first

        clock[0] += 2.0  # now past the 600 s window
        refreshed = await _resolve(client, 2)
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == [2, 2]
    assert refreshed["url"] == first["url"]
    assert refreshed["expires_at"] != first["expires_at"]


@pytest.mark.asyncio
async def test_retry_uses_nl_and_one_html_request() -> None:
    upstream = _Upstream()
    client = _make_client(upstream)
    _seed(list(range(1, 21)))
    try:
        await _resolve(client, 2)
        assert upstream.showpage_pages == [2]
        before = len(upstream.requests)

        out = await _resolve(client, 2, retry=1)
    finally:
        await client.client.aclose()

    assert len(upstream.requests) - before == 1
    assert len(upstream.viewer_urls) == 1
    assert f"nl={SKIP_KEY}" in upstream.viewer_urls[0]
    assert out["url"] == _image_url(2, host="node2.hath.network")


# --- failures --------------------------------------------------------------


@pytest.mark.asyncio
async def test_disallowed_image_host_returns_502_without_url() -> None:
    upstream = _Upstream(showpage_images={2: "https://evil.example.com/x.webp"})
    client = _make_client(upstream)
    _seed(list(range(1, 21)))
    try:
        with pytest.raises(HTTPException) as excinfo:
            await eh_online_resolve_page(
                GID, TOKEN, 2, retry=0, client_mgr=_Manager(client)
            )
    finally:
        await client.client.aclose()

    assert excinfo.value.status_code == 502
    assert excinfo.value.detail == {"code": "host_not_allowed"}
    assert "evil.example.com" not in json.dumps(excinfo.value.detail)


@pytest.mark.asyncio
async def test_509_placeholder_is_429_and_never_cached() -> None:
    placeholder = _image_url(2, name="509.gif")
    upstream = _Upstream(showpage_images={2: placeholder})
    client = _make_client(upstream)
    _seed(list(range(1, 21)))
    try:
        for _ in range(2):
            with pytest.raises(HTTPException) as excinfo:
                await eh_online_resolve_page(
                    GID, TOKEN, 2, retry=0, client_mgr=_Manager(client)
                )
            assert excinfo.value.status_code == 429
            assert excinfo.value.detail == {"code": "image_limit"}
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == [2, 2]


@pytest.mark.asyncio
async def test_page_out_of_range_is_404_without_upstream_resolve() -> None:
    upstream = _Upstream(total=2, pages=[1, 2])
    client = _make_client(upstream)
    _seed([1, 2], total=2)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await eh_online_resolve_page(
                GID, TOKEN, 5, retry=0, client_mgr=_Manager(client)
            )
    finally:
        await client.client.aclose()

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == {"code": "page_out_of_range"}
    assert upstream.showpage_pages == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("Your IP address has been banned", "banned"),
        ("<html>Sad Panda</html>", "auth"),
    ],
)
async def test_auth_and_banned_state_passthrough(body: str, code: str) -> None:
    upstream = _Upstream(banned=body)
    client = _make_client(upstream)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await eh_online_resolve_page(
                GID, TOKEN, 1, retry=0, client_mgr=_Manager(client)
            )
    finally:
        await client.client.aclose()

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == {"code": code}


# --- concurrency limit -----------------------------------------------------


@pytest.mark.asyncio
async def test_reader_concurrency_limit_makes_extra_request_wait(
    runtime: Any,
) -> None:
    runtime(
        settings=Settings(
            exhentai_base_url="https://e-hentai.org",
            online_reader_concurrency=1,
        )
    )
    gate = asyncio.Event()
    entered = asyncio.Event()
    upstream = _Upstream(gate=gate, entered=entered)
    client = _make_client(upstream)
    _seed(list(range(1, 21)))
    try:
        first = asyncio.create_task(_resolve(client, 2))
        await asyncio.wait_for(entered.wait(), timeout=5)
        second = asyncio.create_task(_resolve(client, 3))
        for _ in range(10):
            await asyncio.sleep(0.01)
        assert upstream.showpage_pages == [2]

        gate.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
    finally:
        await client.client.aclose()

    assert upstream.showpage_pages == [2, 3]


# --- settings chain --------------------------------------------------------


def test_new_settings_keys_defaults_and_public_chain(runtime: Any) -> None:
    settings = Settings()
    assert settings.online_reader_concurrency == 3
    assert settings.online_cache_max_mb == 512
    assert {"online_reader_concurrency", "online_cache_max_mb"} <= EDITABLE_SETTINGS

    body = SettingsRequest(online_reader_concurrency=2, online_cache_max_mb=1024)
    assert body.model_dump(exclude_none=True) == {
        "online_reader_concurrency": 2,
        "online_cache_max_mb": 1024,
    }

    runtime(
        settings=Settings(online_reader_concurrency=5, online_cache_max_mb=256)
    )
    assert settings_public()["online_reader_concurrency"] == 5
    assert settings_public()["online_cache_max_mb"] == 256

    update_runtime_settings(
        {"online_reader_concurrency": 4, "online_cache_max_mb": 128}
    )
    assert app_state.settings is not None
    assert app_state.settings.online_reader_concurrency == 4
    assert app_state.settings.online_cache_max_mb == 128


def test_csp_img_src_allows_direct_hah_hosts() -> None:
    csp = SECURITY_HEADERS["Content-Security-Policy"]
    assert "https://*.hath.network:*" in csp
    assert "https://*.ehgt.org" in csp
    assert "script-src 'self'" in csp
    assert "connect-src 'self'" in csp
    assert "'unsafe-eval'" not in csp
