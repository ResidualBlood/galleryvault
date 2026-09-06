from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import duplicates
from galleryvault.app.routers.duplicates import (
    DuplicateResolveRequest,
    dismiss_duplicate,
    duplicate_thumb,
    list_duplicates,
    resolve_duplicate,
    restore_duplicate,
)


@pytest.mark.asyncio
async def test_list_duplicates(monkeypatch):
    groups_data = [
        {
            "gid": 12345,
            "copies": [
                {
                    "path": "/lib/g1",
                    "title": "Title 1",
                    "title_jpn": "タイトル1",
                    "tags": [{"namespace": "artist", "name": "foo"}],
                }
            ],
        }
    ]

    class FakeSession:
        pass

    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_duplicates(self):
            return groups_data

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(duplicates, "get_session", fake_get_session)
    monkeypatch.setattr(duplicates, "GalleryRepository", FakeRepo)

    res = await list_duplicates()
    assert set(res.keys()) == {"groups", "count"}
    assert res["count"] == 1
    assert len(res["groups"]) == 1
    assert "display_title" in res["groups"][0]["copies"][0]


@pytest.mark.asyncio
async def test_resolve_duplicate_outside_roots(tmp_path):
    body = DuplicateResolveRequest(path=str(tmp_path / "outside"), delete_others=False)
    with patch("galleryvault.app.routers.duplicates._in_roots", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_duplicate(12345, body)
        assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_duplicate_group_not_found(tmp_path, monkeypatch):
    body = DuplicateResolveRequest(path=str(tmp_path / "copy"), delete_others=False)

    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_duplicates(self):
            return []

    async def fake_get_session():
        yield object()

    monkeypatch.setattr(duplicates, "get_session", fake_get_session)
    monkeypatch.setattr(duplicates, "GalleryRepository", FakeRepo)
    monkeypatch.setattr(duplicates, "_in_roots", lambda p: True)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_duplicate(12345, body)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_and_restore_duplicate(monkeypatch):
    class FakeSession:
        def begin(self):
            class _Ctx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return _Ctx()

    class FakeRepo:
        def __init__(self, session):
            pass

        async def set_duplicate_status(self, gid, status):
            return gid == 12345

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(duplicates, "get_session", fake_get_session)
    monkeypatch.setattr(duplicates, "GalleryRepository", FakeRepo)

    res = await dismiss_duplicate(12345)
    assert res == {"status": "dismissed"}

    res2 = await restore_duplicate(12345)
    assert res2 == {"status": "open"}

    with pytest.raises(HTTPException) as exc_info:
        await dismiss_duplicate(99999)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_thumb_invalid_keys():
    for bad_key in ["", "../secret", "sub/dir", r"win\path", "/absolute", ".."]:
        with pytest.raises(HTTPException) as exc_info:
            await duplicate_thumb(bad_key)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_thumb_valid_cached(tmp_path, monkeypatch):
    from types import SimpleNamespace

    thumb_root = tmp_path / "thumbs"
    dup_dir = thumb_root / "dup" / "validkey123"
    dup_dir.mkdir(parents=True)
    img_file = dup_dir / "0.jpg"
    img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)

    fake_service = SimpleNamespace(root=thumb_root)
    monkeypatch.setattr(duplicates, "_get_thumb_service", lambda: fake_service)

    resp = await duplicate_thumb("validkey123")
    assert resp.status_code == 200
    assert Path(resp.path) == img_file


@pytest.mark.asyncio
async def test_cross_gid_get_none_cache(monkeypatch):
    from galleryvault.app.routers.duplicates import get_cross_gid_duplicates
    from galleryvault.app.state import app_state

    monkeypatch.setattr(app_state, "cross_gid_duplicates", None)
    monkeypatch.setattr(app_state, "session_factory", None)

    res = await get_cross_gid_duplicates()
    assert res == {"ready": False, "count": 0, "groups": []}


@pytest.mark.asyncio
async def test_cross_gid_get_with_cache_and_cloud_item(monkeypatch):
    from galleryvault.app.routers.duplicates import get_cross_gid_duplicates
    from galleryvault.app.state import app_state

    fake_cache = [
        {
            "key": "alice|work",
            "artist": "alice",
            "legacy_keys": ["alice|work_old"],
            "items": [
                {
                    "gallery_id": 101,
                    "gid": 111,
                    "title": "Work Title",
                    "title_jpn": "作品タイトル",
                    "storage_path": "/path/to/111-Work",
                    "storage_type": "folder",
                    "url": None,
                    "favorited": False,
                    "legacy_keys": ["alice|work_old"],
                },
                {
                    "gallery_id": None,
                    "gid": 222,
                    "title": "Work Title [DL版]",
                    "title_jpn": None,
                    "storage_path": None,
                    "storage_type": None,
                    "url": "https://exhentai.org/g/222/token",
                    "favorited": True,
                    "legacy_keys": ["alice|work_old"],
                },
            ],
        }
    ]

    monkeypatch.setattr(app_state, "cross_gid_duplicates", fake_cache)
    monkeypatch.setattr(app_state, "session_factory", None)

    res = await get_cross_gid_duplicates()
    assert res["ready"] is True
    assert res["count"] == 1
    group = res["groups"][0]
    assert group["key"] == "alice|work"
    assert "legacy_keys" not in group
    assert len(group["items"]) == 2

    # Local item
    local_it = group["items"][0]
    assert local_it["gallery_id"] == 101
    assert "display_title" in local_it
    assert local_it["favorited"] is False
    assert "legacy_keys" not in local_it

    # Cloud item
    cloud_it = group["items"][1]
    assert cloud_it["gallery_id"] is None
    assert cloud_it["url"] == "https://exhentai.org/g/222/token"
    assert cloud_it["favorited"] is True
    assert "display_title" in cloud_it
    assert "legacy_keys" not in cloud_it

    # Verify original cache was not mutated
    assert "legacy_keys" in fake_cache[0]
    assert "legacy_keys" in fake_cache[0]["items"][0]


@pytest.mark.asyncio
async def test_cross_gid_post_refresh(monkeypatch):
    from unittest.mock import AsyncMock

    from galleryvault.app.routers.duplicates import refresh_cross_gid_duplicates
    from galleryvault.app.state import app_state

    scanned_groups = [
        {
            "key": "bob|title",
            "artist": "bob",
            "items": [
                {
                    "gallery_id": 201,
                    "gid": 333,
                    "title": "Bob Title",
                    "title_jpn": None,
                    "storage_path": "/data/333",
                    "storage_type": "cbz",
                    "url": None,
                    "favorited": True,
                }
            ],
        }
    ]

    async def fake_scan(session_factory):
        app_state.cross_gid_duplicates = scanned_groups
        return scanned_groups

    scan_mock = AsyncMock(side_effect=fake_scan)
    monkeypatch.setattr(
        "galleryvault.services.duplicates.scan_library_cross_gid_duplicates",
        scan_mock,
    )

    class MockRepo:
        def __init__(self, session):
            pass

        async def ignored_duplicate_keys(self):
            return set()

        async def ignored_duplicates(self):
            return []

    class MockSessionFactory:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self):
                    return object()

                async def __aexit__(self, *args):
                    pass

            return _Ctx()

    monkeypatch.setattr("galleryvault.app.routers.duplicates.FavoritesRepository", MockRepo)
    monkeypatch.setattr(app_state, "session_factory", MockSessionFactory())

    # Ensure duplicate_records is not touched
    with patch("galleryvault.db.repository.GalleryRepository.sync_duplicates") as sync_mock:
        res = await refresh_cross_gid_duplicates()
        assert sync_mock.call_count == 0

    assert scan_mock.await_count == 1
    assert res["ready"] is True
    assert res["count"] == 1
    assert res["groups"][0]["key"] == "bob|title"


def test_cross_gid_no_library_delete_or_ignore_routes():
    from galleryvault.app.routers.duplicates import router

    paths = [r.path for r in router.routes]
    # No delete/ignore/remove routes under /api/library/duplicates/cross-gid
    for p in paths:
        if p.startswith("/api/library/duplicates/cross-gid"):
            assert "delete" not in p.lower()
            assert "ignore" not in p.lower()
            assert "remove" not in p.lower()
            assert "resolve" not in p.lower()
            assert "dismiss" not in p.lower()

