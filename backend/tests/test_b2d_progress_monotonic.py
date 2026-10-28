"""B2-D / 04 P2-5 backend: reading progress must only move forward."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from galleryvault.app.routers import galleries
from galleryvault.app.schemas import ProgressRequest
from galleryvault.db.models import ReadingProgress
from galleryvault.db.repositories.galleries import GalleryRepository


class _RepoSession:
    def __init__(self, row: ReadingProgress | None) -> None:
        self.row = row
        self.added: list[object] = []
        self.flushes = 0

    async def get(self, model: object, pk: object) -> ReadingProgress | None:
        return self.row

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1


def _row(page: int, total: int | None = 20) -> ReadingProgress:
    return ReadingProgress(
        gallery_id=1,
        current_page=page,
        total_pages=total,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_advance_progress_ignores_stale_page() -> None:
    row = _row(8)
    session = _RepoSession(row)

    stored, advanced = await GalleryRepository(session).advance_progress(1, 3, 20)

    assert advanced is False
    assert stored is row
    assert row.current_page == 8
    assert row.total_pages == 20
    assert row.updated_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert session.flushes == 1


async def test_advance_progress_moves_forward() -> None:
    row = _row(8)
    session = _RepoSession(row)

    stored, advanced = await GalleryRepository(session).advance_progress(1, 12, 30)

    assert advanced is True
    assert stored.current_page == 12
    assert stored.total_pages == 30
    assert stored.updated_at > datetime(2026, 1, 1, tzinfo=UTC)


async def test_advance_progress_inserts_first_entry() -> None:
    session = _RepoSession(None)

    stored, advanced = await GalleryRepository(session).advance_progress(1, 5, 10)

    assert advanced is True
    assert stored.current_page == 5
    assert stored.total_pages == 10
    assert session.added == [stored]


def _pages() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(page_index=i, member_name=f"{i:04d}.jpg", media_type="jpg", manifest={})
        for i in range(10)
    ]


async def test_save_progress_returns_stored_page_when_regressing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(id=7, gid=42, token="tok", title="T")

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def advance_progress(self, gallery_id: int, current: int, total: int):
            return SimpleNamespace(current_page=8, total_pages=total), False

        async def record_history(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("stale progress must not overwrite history")

    async def _lookup(*args: object, **kwargs: object) -> tuple[object, list[object]]:
        return row, _pages()

    monkeypatch.setattr(galleries, "_invoke_gallery", _lookup)
    monkeypatch.setattr(galleries, "GalleryRepository", _Repo)

    session = MagicMock()
    session.in_transaction = MagicMock(return_value=False)
    session.commit = MagicMock()

    result = await galleries.save_gallery_progress(
        7, ProgressRequest(current_page=2), session=session, gallery_service=None
    )

    assert result["current_page"] == 8
    assert result["reading_progress"] == 8


async def test_save_progress_records_history_when_advancing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(id=7, gid=42, token="tok", title="T")
    recorded: list[tuple[int, int]] = []

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def advance_progress(self, gallery_id: int, current: int, total: int):
            return SimpleNamespace(current_page=current, total_pages=total), True

        async def record_history(self, gallery_id: int, current: int, total: int) -> None:
            recorded.append((current, total))

    async def _lookup(*args: object, **kwargs: object) -> tuple[object, list[object]]:
        return row, _pages()

    monkeypatch.setattr(galleries, "_invoke_gallery", _lookup)
    monkeypatch.setattr(galleries, "GalleryRepository", _Repo)

    session = MagicMock()
    session.in_transaction = MagicMock(return_value=False)
    session.commit = MagicMock()

    result = await galleries.save_gallery_progress(
        7, ProgressRequest(current_page=4), session=session, gallery_service=None
    )

    assert result["reading_progress"] == 4
    assert recorded == [(4, 10)]
