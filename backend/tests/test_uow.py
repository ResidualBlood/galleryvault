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
