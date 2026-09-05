"""Tests for expunged gallery listing and redownload by GID (PLAN T10)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import galleries
from galleryvault.app.routers.galleries import (
    ExpungedRedownloadRequest,
    list_expunged,
    redownload_expunged,
)
from galleryvault.services.download_prepare import PreparedGallery


class FakeGallery:
    def __init__(
        self,
        id: int,
        gid: int | None = None,
        token: str | None = None,
        title: str = "Test Title",
        page_count: int = 10,
        storage_path: str = "/tmp/test",
    ) -> None:
        self.id = id
        self.gid = gid
        self.token = token
        self.title = title
        self.title_jpn = None
        self.page_count = page_count
        self.storage_path = storage_path
        self.updated_at = None


@pytest.mark.asyncio
async def test_list_expunged_returns_gid_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_rows = [
        FakeGallery(id=1, gid=12345, token="abcdef1234", title="Gallery 1"),
        FakeGallery(id=2, gid=67890, token=None, title="Gallery 2"),
    ]

    class FakeRepo:
        def __init__(self, session: object) -> None:
            pass

        async def list_expunged(self, page: int, page_size: int) -> tuple[int, list[FakeGallery]]:
            return len(fake_rows), fake_rows

        async def tags_for_galleries(self, ids: list[int]) -> dict[int, list]:
            return {}

    async def fake_get_session():
        yield object()

    monkeypatch.setattr(galleries, "get_session", fake_get_session)
    monkeypatch.setattr(galleries, "GalleryRepository", FakeRepo)

    res = await list_expunged(page=1, page_size=24)
    assert res["total"] == 2
    items = res["items"]
    assert len(items) == 2
    assert items[0]["id"] == 1
    assert items[0]["gid"] == 12345
    assert items[0]["token"] == "abcdef1234"
    assert items[1]["id"] == 2
    assert items[1]["gid"] == 67890
    assert items[1]["token"] is None


@pytest.mark.asyncio
async def test_redownload_expunged_empty_ids_raises_422() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await redownload_expunged(ExpungedRedownloadRequest(ids=[]))
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_redownload_expunged_counts_skips_and_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1: valid with gid + token
    # 2: has gid but no token -> skipped_no_token
    # 3: has no gid -> skipped_no_gid
    # 4: not in DB -> skipped_no_gid
    fake_galleries = {
        1: FakeGallery(id=1, gid=1001, token="tok1001", title="G1"),
        2: FakeGallery(id=2, gid=1002, token=None, title="G2"),
        3: FakeGallery(id=3, gid=None, token=None, title="G3"),
    }

    class FakeSession:
        async def scalars(self, query: object) -> object:
            class _Scalars:
                def all(self_inner) -> list[FakeGallery]:
                    return list(fake_galleries.values())

            return _Scalars()

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(galleries, "get_session", fake_get_session)

    # Mock prepare_galleries and _create_from_prepared
    async def fake_prepare(pairs: list[tuple[int, str]]) -> list[PreparedGallery]:
        return [PreparedGallery(gid=gid, token=token, title="Prepared") for gid, token in pairs]

    created_calls = []

    async def fake_create_from_prepared(prepared: PreparedGallery, **kwargs: object) -> tuple[str, dict]:
        created_calls.append((prepared.gid, prepared.token))
        return "queued", {"status": "queued"}

    monkeypatch.setattr(galleries, "prepare_galleries", fake_prepare)
    monkeypatch.setattr(galleries, "_create_from_prepared", fake_create_from_prepared)

    req = ExpungedRedownloadRequest(ids=[1, 2, 3, 4])
    result = await redownload_expunged(req)

    assert result == {
        "queued": 1,
        "skipped_no_gid": 2,  # id 3 (gid=None) and id 4 (not in DB)
        "skipped_no_token": 1,  # id 2 (token=None)
    }
    assert len(created_calls) == 1
    assert created_calls[0] == (1001, "tok1001")


def test_i18n_keys_present() -> None:
    from pathlib import Path

    import pytest

    zh_path = Path(__file__).parents[2] / "frontend" / "assets" / "locales" / "zh.js"
    en_path = Path(__file__).parents[2] / "frontend" / "assets" / "locales" / "en.js"

    if not zh_path.exists() or not en_path.exists():
        pytest.skip("frontend locale files not available in test environment")

    zh_text = zh_path.read_text(encoding="utf-8")
    en_text = en_path.read_text(encoding="utf-8")

    assert "recycleRedownload" in zh_text
    assert "recycleRedownloadSkip" in zh_text
    assert "recycleRedownload" in en_text
    assert "recycleRedownloadSkip" in en_text
