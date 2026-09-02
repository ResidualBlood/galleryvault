from unittest.mock import patch

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import duplicates
from galleryvault.app.routers.duplicates import (
    DuplicateResolveRequest,
    dismiss_duplicate,
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
