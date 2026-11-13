"""Remote cover fetch throttling: negative cache, single-flight, cache headers.

Motivation: during an EH anti-bot challenge every cover cache miss re-hit
upstream, so one favorites heal round produced ~45 identical requests for the
same gid. These tests pin the three guards that stop that burst.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from galleryvault.app.state import app_state
from galleryvault.services import favorites_worker as fw
from galleryvault.services.eh_client import EhChallengeError

GID = 2_285_141
THUMB = "https://ehgt.org/t/cover.jpg"


class _FailingClient:
    """EH client whose two cover paths always fail."""

    def __init__(self, exc: BaseException | None = None) -> None:
        self.exc = exc or EhChallengeError("challenge page")
        self.download_calls = 0
        self.cover_calls = 0

    @property
    def upstream_calls(self) -> int:
        return self.download_calls + self.cover_calls

    async def download_image(self, url: str) -> bytes:
        self.download_calls += 1
        await asyncio.sleep(0)
        raise self.exc

    async def fetch_gallery_cover(self, gid: int, token: str) -> tuple[bytes, str]:
        self.cover_calls += 1
        raise self.exc


class _SucceedingClient:
    def __init__(self, payload: bytes = b"\xff\xd8\xff\xe0cover") -> None:
        self.payload = payload
        self.download_calls = 0
        self.cover_calls = 0

    @property
    def upstream_calls(self) -> int:
        return self.download_calls + self.cover_calls

    async def download_image(self, url: str) -> bytes:
        self.download_calls += 1
        await asyncio.sleep(0)
        return self.payload

    async def fetch_gallery_cover(self, gid: int, token: str) -> tuple[bytes, str]:
        self.cover_calls += 1
        return self.payload, "image/jpeg"


@pytest.fixture(autouse=True)
def _fast_cover_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real pacing interval; upstream call *counts* are what these tests pin."""
    # ``raising=False`` keeps the failure mode behavioural: on a build without
    # these knobs the tests must fail on their assertions, not at setup.
    monkeypatch.setattr(fw, "REMOTE_COVER_MIN_INTERVAL", 0.0, raising=False)
    monkeypatch.setattr(fw, "REMOTE_COVER_NEG_TTL_TRANSIENT", 30 * 60.0, raising=False)
    monkeypatch.setattr(fw, "REMOTE_COVER_NEG_TTL_MISSING", 6 * 3600.0, raising=False)
    # Isolate from whatever database the surrounding process happens to own: a
    # real session factory would let ``_fill_remote_cover`` look up a stored
    # token for ``GID`` and take the download+fetch_gallery_cover path, turning
    # the single-upstream-call assertions into flaky double calls.
    monkeypatch.setattr(fw, "_get_background_session_factory", lambda: None, raising=False)


def _clock(monkeypatch: pytest.MonkeyPatch, start: float = 1_000.0) -> dict[str, float]:
    now = {"value": start}
    monkeypatch.setattr(fw, "_cover_clock", lambda: now["value"], raising=False)
    return now


async def test_repeated_misses_only_hit_upstream_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FailingClient()
    monkeypatch.setattr(app_state, "eh_client", client)

    results = [
        await fw.ensure_remote_cover(
            GID, None, cache_dir=tmp_path, source="thumb0", cached_meta={"thumb": THUMB}
        )
        for _ in range(5)
    ]

    assert results == [None] * 5
    # One download attempt total; the negative cache absorbs the other four.
    assert client.upstream_calls == 1
    assert client.download_calls == 1


async def test_concurrent_same_gid_is_single_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FailingClient()
    monkeypatch.setattr(app_state, "eh_client", client)

    results = await asyncio.gather(
        *[
            fw.ensure_remote_cover(
                GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
            )
            for _ in range(10)
        ]
    )

    assert results == [None] * 10
    assert client.upstream_calls == 1


async def test_negative_cache_expires_then_retries_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = _clock(monkeypatch)
    client = _FailingClient()
    monkeypatch.setattr(app_state, "eh_client", client)

    first = await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    )
    assert first is None
    assert client.upstream_calls == 1

    # Still inside the transient (challenge) TTL: no upstream traffic.
    now["value"] += 29 * 60.0
    assert await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert client.upstream_calls == 1

    # Past the 30 min TTL: exactly one retry, then the cache blocks again.
    now["value"] += 2 * 60.0
    assert await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert client.upstream_calls == 2

    assert await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert client.upstream_calls == 2


async def test_missing_thumb_uses_long_negative_ttl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = _clock(monkeypatch)
    client = _FailingClient(RuntimeError("no usable thumb"))
    monkeypatch.setattr(app_state, "eh_client", client)

    assert await fw.ensure_remote_cover(
        GID, "tok", cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert client.upstream_calls == 2  # download_image + fetch_gallery_cover

    # A generic upstream failure is not a challenge: it waits 6h, not 30min.
    now["value"] += 31 * 60.0
    assert await fw.ensure_remote_cover(
        GID, "tok", cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert client.upstream_calls == 2

    now["value"] += 6 * 3600.0
    assert await fw.ensure_remote_cover(
        GID, "tok", cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert client.upstream_calls == 4


async def test_file_cache_hit_makes_no_upstream_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _SucceedingClient()
    monkeypatch.setattr(app_state, "eh_client", client)

    path = await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    )
    assert path is not None and path.is_file()
    assert client.download_calls == 1

    again = await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    )
    assert again == path
    assert client.upstream_calls == 1


async def test_success_clears_previous_negative_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing = _FailingClient()
    monkeypatch.setattr(app_state, "eh_client", failing)
    assert await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    ) is None
    assert failing.upstream_calls == 1

    # Even inside the TTL a successful fill must clear the entry, so the next
    # call after a cache eviction can retry immediately.
    fw.clear_remote_cover_negative(GID)
    succeeding = _SucceedingClient()
    monkeypatch.setattr(app_state, "eh_client", succeeding)
    path = await fw.ensure_remote_cover(
        GID, None, cache_dir=tmp_path, cached_meta={"thumb": THUMB}
    )
    assert path is not None
    assert getattr(fw, "_cover_neg_cache", {}).get(GID) is None


async def test_cover_endpoint_cache_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import galleries as galleries_router
    from galleryvault.db.models import Gallery, GalleryPage
    from galleryvault.services.thumbnails import ThumbnailService

    thumb_root = tmp_path / "cache" / "thumbs"
    service = ThumbnailService(thumb_root)
    monkeypatch.setattr(galleries_router, "_get_thumb_service", lambda: service)

    gallery = Gallery(
        id=7, gid=777, token="abc12345", storage_path=str(tmp_path / "g7")
    )
    pages = [
        GalleryPage(gallery_id=7, page_index=0, member_name="01.jpg", media_type="jpg")
    ]

    async def fake_lookup(identifier: int) -> tuple[Gallery, list[GalleryPage]]:
        return gallery, pages

    monkeypatch.setattr(galleries_router, "_gallery", fake_lookup)

    cover = service.remote_cover_dir() / "777.img"
    cover.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8)

    hit = await galleries_router.get_thumbnail(7, 0)
    assert hit.headers["cache-control"] == "public, max-age=604800"

    # Cover not filled yet -> the placeholder/local page response must only be
    # cached briefly so the browser retries instead of spamming the endpoint.
    cover.unlink()
    monkeypatch.setattr(app_state, "eh_client", None)
    local_page = service.cache_path(7, 0)
    local_page.parent.mkdir(parents=True, exist_ok=True)
    local_page.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8)

    miss = await galleries_router.get_thumbnail(7, 0)
    assert miss.headers["cache-control"] == "public, max-age=300"
