"""Batch 13: online gallery detail, preview pages and local-only status.

Covers the §3.3 contract: detail fields + local badges, lazy preview-page
thumbnails (ptoken stays server-side), process-local TTL caches, state
passthrough for challenge/auth/banned, and ``/api/eh/status`` never touching
ExHentai.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from galleryvault.app.routers.eh import attach_search_badges
from galleryvault.app.routers.eh_online import (
    eh_local_status,
    eh_online_gallery_detail,
    eh_online_pages,
)
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.eh_client import EhClient
from galleryvault.services.eh_parsers import (
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    OnlineGalleryDetail,
    PageThumb,
    PreviewItem,
    PreviewPage,
    parse_gallery_preview,
    parse_online_gallery,
)

FIXTURES = Path(__file__).parent / "fixtures" / "eh_online"
GID = 4323821
TOKEN = "3e444314f7"


def _fixture() -> str:
    return (FIXTURES / "gallery-detail.html").read_text(encoding="utf-8")


class _Rows:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class _FakeSession:
    """Dispatch the three local badge queries by table name."""

    def __init__(
        self,
        library: list[tuple[Any, ...]] | None = None,
        favorites: list[tuple[Any, ...]] | None = None,
        downloads: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.library = library or []
        self.favorites = favorites or []
        self.downloads = downloads or []
        self.sql: list[str] = []

    async def execute(self, statement: Any) -> _Rows:
        sql = str(statement).lower()
        self.sql.append(sql)
        if "download_tasks" in sql:
            return _Rows(self.downloads)
        if "favorite_items" in sql:
            return _Rows(self.favorites)
        return _Rows(self.library)


class _DetailClient:
    def __init__(self, detail: OnlineGalleryDetail | None = None, error: Exception | None = None) -> None:
        self.detail = detail
        self.error = error
        self.calls = 0

    async def fetch_online_gallery(self, gid: int, token: str) -> OnlineGalleryDetail:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.detail is not None
        return self.detail


class _PreviewClient:
    def __init__(self, pages: dict[int, PreviewPage]) -> None:
        self.pages = pages
        self.calls: list[int] = []

    async def fetch_gallery_preview_page(
        self, gid: int, token: str, page: int = 0
    ) -> PreviewPage:
        self.calls.append(page)
        return self.pages[page]


class _ExplodingClient:
    """Any EH touch is a test failure for the local-only endpoint."""

    def __init__(self) -> None:
        self.calls = 0

    async def fetch_online_gallery(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        raise AssertionError("/api/eh/status must not query ExHentai")

    async def fetch_gallery_preview_page(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        raise AssertionError("/api/eh/status must not query ExHentai")


def _parsed_detail() -> OnlineGalleryDetail:
    return parse_online_gallery(_fixture(), GID, TOKEN)


# --- parsing ---------------------------------------------------------------


def test_parse_online_gallery_fields_complete() -> None:
    detail = _parsed_detail()
    assert detail.gid == GID
    assert detail.token == TOKEN
    assert detail.title.startswith("[Roxor] Artoria Pendragon")
    assert detail.title_jpn is None
    assert detail.category == "misc"
    assert detail.uploader == "sample-uploader"
    assert detail.pages == 26
    assert detail.rating == pytest.approx(2.65)
    assert detail.file_size == 146276352  # 139.5 MiB
    assert detail.posted is not None and detail.posted > 0
    assert detail.thumb == "https://ehgt.org/w/02/793/65983-nlonteat.webp"
    assert {"namespace": "female", "name": "big breasts"} in detail.tags
    assert detail.parent_gid is None
    assert detail.newer is None


def test_parse_online_gallery_gdata_supersedes_typed_fields() -> None:
    detail = parse_online_gallery(
        _fixture(),
        GID,
        TOKEN,
        gdata={
            "title": "gdata title",
            "title_jpn": "日本語タイトル",
            "category": "Manga",
            "uploader": "gdata-uploader",
            "posted": 1700000000,
            "file_count": 30,
            "rating": 4.25,
            "file_size": 123,
            "thumb": "https://ehgt.org/gdata.jpg",
            "parent_gid": 999,
            "tags": ["female:ponytail", "other:ai generated"],
        },
    )
    assert detail.title == "gdata title"
    assert detail.title_jpn == "日本語タイトル"
    assert detail.uploader == "gdata-uploader"
    assert detail.posted == 1700000000
    assert detail.pages == 30
    assert detail.rating == pytest.approx(4.25)
    assert detail.file_size == 123
    assert detail.thumb == "https://ehgt.org/gdata.jpg"
    assert detail.parent_gid == 999
    assert {"namespace": "female", "name": "ponytail"} in detail.tags


def test_parse_gallery_preview_extracts_sprite_cells() -> None:
    page = parse_gallery_preview(_fixture(), GID)
    assert page.total == 26
    assert [item.index for item in page.items] == list(range(1, 21))
    assert len(page.ptokens) == 20
    first = page.items[0].thumb
    assert first == PageThumb(
        index=1,
        url=(
            "https://node1.example.hath.network/c2/samplegenkey01/"
            f"{GID}-0.webp"
        ),
        x=0,
        y=0,
        w=200,
        h=200,
    )
    assert page.items[-1].thumb is not None
    assert page.items[-1].thumb.x == -3800


def test_parse_gallery_preview_degrades_to_null_thumb() -> None:
    body = (
        f'<div id="gdt"><a href="https://e-hentai.org/s/abcdef0123/{GID}-1">'
        '<div title="Page 1"></div></a></div>'
    )
    page = parse_gallery_preview(body, GID)
    assert len(page.items) == 1
    assert page.items[0].index == 1
    assert page.items[0].thumb is None
    assert page.ptokens == {1: "abcdef0123"}


# --- EhClient state classification ----------------------------------------


def _client(handler: Any) -> EhClient:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://e-hentai.org",
        follow_redirects=True,
    )
    return EhClient(Settings(exhentai_base_url="https://e-hentai.org"), client=http_client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, text="Your IP address has been banned"), "banned"),
        (httpx.Response(200, text="<html>Sad Panda</html>"), "auth"),
        (httpx.Response(401, text=""), "auth"),
    ],
)
async def test_client_detail_raises_distinguishable_states(
    response: httpx.Response, expected: str
) -> None:
    client = _client(lambda request: response)
    try:
        with pytest.raises((EhBannedError, EhAuthRequiredError)) as excinfo:
            await client.fetch_online_gallery(GID, TOKEN)
        mapping = {
            "banned": EhBannedError,
            "auth": EhAuthRequiredError,
        }
        assert isinstance(excinfo.value, mapping[expected])
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_client_detail_detects_redirect_challenge() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text="<html>home</html>")
        return httpx.Response(302, headers={"Location": "/"})

    client = _client(handler)
    try:
        with pytest.raises(EhChallengeError):
            await client.fetch_online_gallery(GID, TOKEN)
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_client_detail_merges_gdata() -> None:
    body = _fixture()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api.php":
            return httpx.Response(
                200,
                json={
                    "gmetadata": [
                        {
                            "gid": GID,
                            "token": TOKEN,
                            "thumb": "https://ehgt.org/gdata-thumb.webp",
                            "title": "Gdata Title",
                            "title_jpn": "Gdata JPN",
                            "category": "Manga",
                            "filecount": 26,
                            "filesize": 100,
                            "tags": ["female:ponytail"],
                            "posted": 1700000000,
                            "uploader": "gdata-uploader",
                            "rating": 4.5,
                            "parent_gid": "123",
                        }
                    ]
                },
            )
        return httpx.Response(200, text=body)

    client = _client(handler)
    try:
        detail = await client.fetch_online_gallery(GID, TOKEN)
    finally:
        await client.client.aclose()
    assert detail.posted == 1700000000
    assert detail.uploader == "gdata-uploader"
    assert detail.thumb == "https://ehgt.org/gdata-thumb.webp"
    assert detail.parent_gid == 123
    assert detail.title == "Gdata Title"


# --- detail endpoint -------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_endpoint_fields_and_badges(runtime: Any) -> None:
    app_state.extra.pop("eh_online_detail_cache", None)
    client = _DetailClient(detail=_parsed_detail())
    runtime(eh_client=client)
    session = _FakeSession(
        library=[(GID, 7)],
        favorites=[(GID, 3)],
        downloads=[(9, GID, "downloading", 4, 26)],
    )
    out = await eh_online_gallery_detail(GID, TOKEN, session=session)
    assert out["state"] == "ok"
    gallery = out["gallery"]
    assert gallery is not None
    for field in (
        "gid",
        "token",
        "title",
        "title_jpn",
        "category",
        "uploader",
        "posted",
        "pages",
        "rating",
        "file_size",
        "thumb",
        "tags",
        "newer",
        "parent_gid",
        "in_library",
        "gallery_id",
        "favorited",
        "favcat",
        "download",
    ):
        assert field in gallery
    assert gallery["in_library"] is True
    assert gallery["gallery_id"] == 7
    assert gallery["favorited"] is True
    assert gallery["favcat"] == 3
    assert gallery["download"] == {
        "id": 9,
        "status": "downloading",
        "current_page": 4,
        "total_pages": 26,
    }
    assert client.calls == 1


@pytest.mark.asyncio
async def test_detail_cache_second_request_zero_upstream(runtime: Any) -> None:
    app_state.extra.pop("eh_online_detail_cache", None)
    client = _DetailClient(detail=_parsed_detail())
    runtime(eh_client=client)
    session = _FakeSession()
    first = await eh_online_gallery_detail(GID, TOKEN, session=session)
    second = await eh_online_gallery_detail(GID, TOKEN, session=session)
    assert client.calls == 1
    assert first == second


@pytest.mark.asyncio
async def test_detail_invalid_token_422_without_upstream(runtime: Any) -> None:
    client = _DetailClient(detail=_parsed_detail())
    runtime(eh_client=client)
    with pytest.raises(HTTPException) as excinfo:
        await eh_online_gallery_detail(GID, "not-hex!", session=_FakeSession())
    assert excinfo.value.status_code == 422
    assert client.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        (EhChallengeError("challenge"), "challenge"),
        (EhAuthRequiredError("auth"), "auth"),
        (EhBannedError("banned"), "banned"),
    ],
)
async def test_detail_state_passthrough(
    runtime: Any, error: Exception, expected_state: str
) -> None:
    app_state.extra.pop("eh_online_detail_cache", None)
    runtime(eh_client=_DetailClient(error=error))
    out = await eh_online_gallery_detail(GID, TOKEN, session=_FakeSession())
    assert out["state"] == expected_state
    assert out["gallery"] is None


# --- pages endpoint --------------------------------------------------------


def _preview_page(indices: list[int]) -> PreviewPage:
    items = [
        PreviewItem(
            index=index,
            thumb=PageThumb(
                index=index,
                url=f"https://node1.example.hath.network/c2/gen/{GID}-1.webp",
                x=-((index - 21) * 200),
                y=0,
                w=200,
                h=200,
            ),
        )
        for index in indices
    ]
    return PreviewPage(
        total=26,
        items=items,
        ptokens={index: f"{index:010x}" for index in indices},
    )


@pytest.mark.asyncio
async def test_pages_endpoint_thumbs_and_no_ptoken(runtime: Any) -> None:
    app_state.extra.pop("eh_online_pages_cache", None)
    client = _PreviewClient({0: parse_gallery_preview(_fixture(), GID)})
    runtime(eh_client=client)
    out = await eh_online_pages(GID, TOKEN, p=0)
    assert out["state"] == "ok"
    assert out["p"] == 0
    assert out["per_page"] == 20
    assert out["total"] == 26
    assert [item["index"] for item in out["items"]] == list(range(1, 21))
    assert out["items"][0]["thumb"] is not None
    serialized = json.dumps(out)
    assert "ptoken" not in serialized
    for ptoken in client.pages[0].ptokens.values():
        assert ptoken not in serialized
    # cached: second call is served locally
    await eh_online_pages(GID, TOKEN, p=0)
    assert client.calls == [0]


@pytest.mark.asyncio
async def test_pages_second_preview_uses_meta_per_page(runtime: Any) -> None:
    app_state.extra.pop("eh_online_pages_cache", None)
    app_state.extra.pop("eh_online_pages_meta", None)
    client = _PreviewClient(
        {
            0: parse_gallery_preview(_fixture(), GID),
            1: _preview_page([21, 22, 23, 24, 25, 26]),
        }
    )
    runtime(eh_client=client)
    await eh_online_pages(GID, TOKEN, p=0)
    out = await eh_online_pages(GID, TOKEN, p=1)
    assert out["p"] == 1
    assert out["per_page"] == 20  # inferred from the first preview page
    assert [item["index"] for item in out["items"]] == [21, 22, 23, 24, 25, 26]
    assert client.calls == [0, 1]


@pytest.mark.asyncio
async def test_pages_null_thumb_still_200(runtime: Any) -> None:
    app_state.extra.pop("eh_online_pages_cache", None)
    page = parse_gallery_preview(
        f'<a href="https://e-hentai.org/s/abcdef0123/{GID}-1"><div title="Page 1"></div></a>',
        GID,
    )
    runtime(eh_client=_PreviewClient({0: page}))
    out = await eh_online_pages(GID, TOKEN, p=0)
    assert out["state"] == "ok"
    assert out["items"] == [{"index": 1, "thumb": None}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        (EhChallengeError("challenge"), "challenge"),
        (EhAuthRequiredError("auth"), "auth"),
        (EhBannedError("banned"), "banned"),
    ],
)
async def test_pages_state_passthrough(
    runtime: Any, error: Exception, expected_state: str
) -> None:
    app_state.extra.pop("eh_online_pages_cache", None)

    class _ErrorClient:
        async def fetch_gallery_preview_page(self, *args: Any, **kwargs: Any) -> PreviewPage:
            raise error

    runtime(eh_client=_ErrorClient())
    out = await eh_online_pages(GID, TOKEN, p=0)
    assert out["state"] == expected_state
    assert out["items"] == []


# --- local status ----------------------------------------------------------


@pytest.mark.asyncio
async def test_status_local_only_never_calls_eh(runtime: Any) -> None:
    client = _ExplodingClient()
    runtime(eh_client=client)
    session = _FakeSession(
        library=[(1, 10)],
        favorites=[(1, 2)],
        downloads=[(5, 1, "failed", 0, None)],
    )
    out = await eh_local_status(gids="1,2", session=session)
    assert client.calls == 0
    assert out["items"] == [
        {
            "gid": 1,
            "in_library": True,
            "gallery_id": 10,
            "favorited": True,
            "favcat": 2,
            "download_status": "failed",
        },
        {
            "gid": 2,
            "in_library": False,
            "gallery_id": None,
            "favorited": False,
            "favcat": None,
            "download_status": None,
        },
    ]


@pytest.mark.asyncio
async def test_status_too_many_gids_422(runtime: Any) -> None:
    client = _ExplodingClient()
    runtime(eh_client=client)
    gids = ",".join(str(i) for i in range(1, 102))
    with pytest.raises(HTTPException) as excinfo:
        await eh_local_status(gids=gids, session=_FakeSession())
    assert excinfo.value.status_code == 422
    assert client.calls == 0


@pytest.mark.asyncio
async def test_status_invalid_gids_422(runtime: Any) -> None:
    runtime(eh_client=_ExplodingClient())
    for raw in ("abc", "1,,2", "-3", "0"):
        with pytest.raises(HTTPException) as excinfo:
            await eh_local_status(gids=raw, session=_FakeSession())
        assert excinfo.value.status_code == 422


# --- search badges ---------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_search_badges_four_download_states() -> None:
    items = [
        {"gid": 1, "token": "a" * 10},
        {"gid": 2, "token": "b" * 10},
        {"gid": 3, "token": "c" * 10},
        {"gid": 4, "token": "d" * 10},
    ]
    session = _FakeSession(
        library=[(1, 10)],
        favorites=[(3, 2)],
        downloads=[
            (5, 1, "downloading", 3, 10),
            (6, 2, "pending", 0, None),
            (7, 3, "failed", 0, 10),
        ],
    )
    out = await attach_search_badges(session, items)
    assert [it["download_status"] for it in out] == [
        "downloading",
        "pending",
        "failed",
        None,
    ]
    # Existing fields keep their meaning; ``downloaded`` still mirrors the library.
    assert out[0]["in_library"] is True
    assert out[0]["downloaded"] is True
    assert out[1]["in_library"] is False
    assert out[1]["downloaded"] is False
    assert out[2]["favorited"] is True
    assert out[2]["favcat"] == 2
    assert out[3]["favorited"] is False
