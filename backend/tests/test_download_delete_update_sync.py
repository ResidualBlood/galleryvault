"""Deleting a download task must sync its gallery-update row to failed.

The finalize loop looks the task up by id; a deleted task means the update row
would stay ``downloading`` forever.  The delete endpoint marks any pinned
gallery-update rows failed so they stay actionable (retry / ignore).
"""

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import downloads as downloads_router


class _Row:
    id = 555
    gid = 7
    status = "downloading"


class _Sess:
    def __init__(self):
        self.failed_by_task = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def begin(self):
        return self

    async def get(self, model, task_id):
        return _Row() if task_id == 555 else None


async def test_delete_task_syncs_gallery_update(monkeypatch):
    marked = []
    cleaned = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def delete(self, task_id):
            return True

    class FakeUpdatesRepo:
        def __init__(self, session):
            pass

        async def mark_failed_by_task(self, task_id, error):
            marked.append((task_id, error))
            return 1

    monkeypatch.setattr(downloads_router, "DownloadRepository", FakeRepo)
    monkeypatch.setattr(downloads_router, "GalleryUpdatesRepository", FakeUpdatesRepo)

    async def fake_cleanup(gid):
        cleaned.append(gid)

    monkeypatch.setattr(downloads_router, "_cleanup_download_temp", fake_cleanup)
    monkeypatch.setattr(
        downloads_router.main,
        "_settings_session",
        lambda: _Sess(),
    )

    await downloads_router.delete_download_task(555)

    assert marked == [(555, "download task removed")]
    assert cleaned == [7]


async def test_delete_missing_task_404(monkeypatch):
    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

        async def get(self, model, task_id):
            return None

    class FakeRepo:
        def __init__(self, session):
            pass

        async def delete(self, task_id):
            return False

    class FakeUpdatesRepo:
        def __init__(self, session):
            pass

        async def mark_failed_by_task(self, task_id, error):
            return 0

    monkeypatch.setattr(downloads_router, "DownloadRepository", FakeRepo)
    monkeypatch.setattr(downloads_router, "GalleryUpdatesRepository", FakeUpdatesRepo)
    monkeypatch.setattr(
        downloads_router.main,
        "_settings_session",
        lambda: Sess(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await downloads_router.delete_download_task(999)
    assert exc_info.value.status_code == 404
