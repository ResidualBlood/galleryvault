"""Tests for Unit of Work pattern (galleryvault.db.uow)."""

import pytest

from galleryvault.db.uow import UnitOfWork


class FakeAsyncSession:
    def __init__(self):
        self.begun = False
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.added = []

    async def begin(self):
        self.begun = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        self.closed = True

    def add(self, item):
        self.added.append(item)


@pytest.mark.asyncio
async def test_uow_commit_on_success():
    fake_session = FakeAsyncSession()
    uow = UnitOfWork(lambda: fake_session)

    async with uow:
        assert uow.session is fake_session
        assert fake_session.begun is True
        # Access repositories
        assert uow.galleries is not None
        assert uow.downloads is not None
        assert uow.favorites is not None
        assert uow.settings is not None
        assert uow.jobs is not None
        assert uow.updates is not None

    assert fake_session.committed is True
    assert fake_session.closed is True
    assert fake_session.rolled_back is False


@pytest.mark.asyncio
async def test_uow_rollback_on_exception():
    fake_session = FakeAsyncSession()
    uow = UnitOfWork(lambda: fake_session)

    with pytest.raises(ValueError, match="boom"):
        async with uow:
            raise ValueError("boom")

    assert fake_session.committed is False
    assert fake_session.rolled_back is True
    assert fake_session.closed is True


def test_uow_repo_outside_context_raises():
    uow = UnitOfWork(lambda: FakeAsyncSession())
    with pytest.raises(RuntimeError, match="not active"):
        _ = uow.galleries


@pytest.mark.asyncio
async def test_resolve_session_with_active_session_returns_directly():
    from galleryvault.app.dependencies import resolve_session

    fake_session = FakeAsyncSession()
    resolved = await resolve_session(fake_session)
    assert resolved is fake_session


@pytest.mark.asyncio
async def test_resolve_session_wraps_generator_and_closes_safely():
    import asyncio

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from galleryvault.app.dependencies import _ManagedSessionWrapper, resolve_session

    gen_exited = False

    async def fake_get_session():
        nonlocal gen_exited
        try:
            yield FakeAsyncSession()
        finally:
            gen_exited = True

    async def run_in_task():
        dep_obj = Depends(fake_get_session)
        resolved = await resolve_session(dep_obj)
        assert isinstance(resolved, _ManagedSessionWrapper)
        assert isinstance(resolved, FakeAsyncSession)
        assert gen_exited is False
        return resolved

    # Run in separate asyncio task to check task-level auto-close
    task = asyncio.create_task(run_in_task())
    wrapper = await task
    await asyncio.sleep(0.01)
    # Generator must be automatically closed on task finish without pool leaks
    assert gen_exited is True

    # Calling aclose() idempotently must be safe
    await wrapper.aclose()

    class MockDbSession(AsyncSession):
        pass

    mock_sess = _ManagedSessionWrapper(MockDbSession(bind=None))
    assert isinstance(mock_sess, AsyncSession)
