from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from galleryvault.app.state import app_state
from galleryvault.services import tag_sync_worker
from galleryvault.services.tag_sync_worker import (
    JOB_TAG_SYNC,
    _confirm_gone,
    _is_public_site,
    claim_jobs,
    complete_job,
    enqueue_tag_sync,
    jobs_count,
    requeue_job,
    tag_facets_cached,
)


def test_is_public_site():
    assert _is_public_site(None) is True
    assert _is_public_site("") is True
    assert _is_public_site("https://e-hentai.org") is True
    assert _is_public_site("https://exhentai.org") is False


@pytest.mark.asyncio
async def test_tag_facets_cached_hit_and_miss():
    orig_session = app_state.session_factory
    try:
        tag_sync_worker._tag_facets_cache = {"ts": 0.0, "facets": []}

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeRepo:
            def __init__(self, session):
                pass

            async def tag_facets(self):
                return [("female", 10), ("male", 5)]

        app_state.session_factory = lambda: FakeSession()
        with patch("galleryvault.services.tag_sync_worker.GalleryRepository", FakeRepo):
            facets = await tag_facets_cached()
            assert facets == [("female", 10), ("male", 5)]

            # Cache hit
            facets2 = await tag_facets_cached()
            assert facets2 == [("female", 10), ("male", 5)]
    finally:
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_job_queue_helpers():
    orig_session = app_state.session_factory
    try:
        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

        class FakeJobsRepo:
            def __init__(self, session):
                pass

            async def count(self, job_type):
                return 3

            async def claim(self, job_type, limit, lease_seconds):
                return [(1, 0), (2, 1)]

            async def complete(self, job_type, gallery_id):
                pass

            async def requeue(self, job_type, gallery_id, next_attempt_at=None):
                pass

            async def enqueue_many(self, job_type, gallery_ids):
                return len(gallery_ids)

        app_state.session_factory = lambda: FakeSession()
        with patch("galleryvault.services.tag_sync_worker.BackgroundJobsRepository", FakeJobsRepo):
            assert await jobs_count(JOB_TAG_SYNC) == 3
            claimed = await claim_jobs(JOB_TAG_SYNC, 2)
            assert claimed == [(1, 0), (2, 1)]
            await complete_job(JOB_TAG_SYNC, 1)
            await requeue_job(JOB_TAG_SYNC, 2)
            enqueued = await enqueue_tag_sync([1, 2, 3])
            assert enqueued == 3
    finally:
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_confirm_gone():
    orig_client = app_state.eh_client
    try:
        assert await _confirm_gone(1, None) is None
        assert await _confirm_gone(None, "token") is None

        fake_client = MagicMock()
        fake_client.fetch_gmetadata = AsyncMock(return_value={
            123: {"expunged": True},
            456: {"expunged": False},
        })
        app_state.eh_client = fake_client

        assert await _confirm_gone(123, "tok") is True
        assert await _confirm_gone(456, "tok") is False
        assert await _confirm_gone(789, "tok") is None
    finally:
        app_state.eh_client = orig_client
