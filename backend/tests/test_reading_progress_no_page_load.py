"""T9.2d: local reading progress costs a page count, not the page list.

``GET/PUT /api/galleries/{identifier}/progress`` used to call
``GalleryRepository.get_pages`` just to know ``len(pages)``.  The repository now
exposes ``page_count`` (``SELECT COUNT(*)`` on ``gallery_pages``); these tests
fail on the old implementation because its lookup path reaches ``get_pages``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import galleries
from galleryvault.app.routers import reading as reading_router
from galleryvault.app.schemas import ProgressRequest


class _NoPageLoadRepo:
    """Gallery repository double whose ``get_pages`` must never be reached."""

    calls: ClassVar[list[object]] = []
    page_total: ClassVar[int] = 3

    def __init__(self, _session: object) -> None:
        pass

    async def get_by_id(self, identifier: int) -> SimpleNamespace:
        type(self).calls.append(("get_by_id", identifier))
        return SimpleNamespace(id=7, gid=42)

    async def get_by_gid(self, identifier: int) -> None:
        type(self).calls.append(("get_by_gid", identifier))

    async def page_count(self, gallery_id: int) -> int:
        type(self).calls.append(("page_count", gallery_id))
        return type(self).page_total

    async def progress(self, gallery_id: int) -> None:
        type(self).calls.append(("progress", gallery_id))

    async def advance_progress(
        self, gallery_id: int, current_page: int, total_pages: int
    ) -> tuple[SimpleNamespace, bool]:
        type(self).calls.append(("advance_progress", current_page, total_pages))
        return SimpleNamespace(current_page=current_page, total_pages=total_pages), True

    async def record_history(
        self, gallery_id: int, current_page: int, total_pages: int
    ) -> None:
        type(self).calls.append(("record_history", current_page, total_pages))

    async def get_pages(self, gallery_id: int) -> list[object]:
        raise AssertionError(
            "reading progress must count gallery_pages, not load them"
        )


@pytest.fixture(autouse=True)
def _repo(monkeypatch: pytest.MonkeyPatch) -> type[_NoPageLoadRepo]:
    _NoPageLoadRepo.calls = []
    _NoPageLoadRepo.page_total = 3
    monkeypatch.setattr(galleries, "GalleryRepository", _NoPageLoadRepo)
    return _NoPageLoadRepo


def _session() -> MagicMock:
    session = MagicMock()
    session.in_transaction = MagicMock(return_value=False)
    session.commit = MagicMock()
    return session


async def test_get_progress_defaults_total_pages_to_count() -> None:
    result = await reading_router.gallery_progress(7, session=_session())

    assert result["gallery_id"] == 7
    assert result["current_page"] == 0
    assert result["total_pages"] == 3
    assert ("page_count", 7) in _NoPageLoadRepo.calls


async def test_save_progress_validates_and_defaults_against_count() -> None:
    result = await reading_router.save_gallery_progress(
        7, ProgressRequest(current_page=2), session=_session()
    )

    assert result["current_page"] == 2
    assert result["total_pages"] == 3
    assert ("advance_progress", 2, 3) in _NoPageLoadRepo.calls
    assert ("record_history", 2, 3) in _NoPageLoadRepo.calls


async def test_save_progress_rejects_page_at_count_not_max_index() -> None:
    # Sparse page indexes used to make ``max(page_index)`` look larger than the
    # real page count; ``current_page == count`` is still outside the gallery.
    with pytest.raises(HTTPException) as exc:
        await reading_router.save_gallery_progress(
            7, ProgressRequest(current_page=3), session=_session()
        )

    assert exc.value.status_code == 422
    assert not any(
        isinstance(call, tuple) and call[0] == "advance_progress"
        for call in _NoPageLoadRepo.calls
    )
