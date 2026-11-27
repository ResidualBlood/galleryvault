"""Regression tests: ListService must raise NotFoundError/ConflictError, not TypeError."""

from __future__ import annotations

from typing import Any, Self

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from galleryvault.app.exceptions import ConflictError, NotFoundError, ValidationError
from galleryvault.app.routers import lists as lists_router
from galleryvault.services.list_service import ListService


class _FakeListsRepo:
    """Minimal local-list repository stub returning fixed outcomes."""

    def __init__(
        self,
        *,
        existing: Any = None,
        deleted: bool = False,
        renamed: Any = None,
        added: int = 0,
        removed: int = 0,
    ) -> None:
        self.existing = existing
        self.deleted = deleted
        self.renamed = renamed
        self.added = added
        self.removed = removed

    async def get(self, list_id: int) -> Any:
        return self.existing

    async def get_by_name(self, name: str) -> Any:
        return self.existing

    async def rename(self, list_id: int, name: str) -> Any:
        return self.renamed

    async def delete_list(self, list_id: int) -> bool:
        return self.deleted

    async def add_items(self, list_id: int, gallery_ids: list[int]) -> int:
        return self.added

    async def remove_items(self, list_id: int, gallery_ids: list[int]) -> int:
        return self.removed

    async def get_items_with_galleries(self, list_id: int) -> list[Any]:
        return []


class _FakeUoW:
    def __init__(self, lists_repo: _FakeListsRepo) -> None:
        self.lists = lists_repo

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeDispatcher:
    def spawn_record_task(self, *args: Any, **kwargs: Any) -> None:
        return None


class _ExistingList:
    id = 7
    name = "dup"
    created_at = None


def _service(repo: _FakeListsRepo) -> ListService:
    return ListService(uow=_FakeUoW(repo), task_dispatcher=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_list_detail_missing_raises_not_found() -> None:
    with pytest.raises(NotFoundError) as excinfo:
        await _service(_FakeListsRepo()).get_list_detail(999)

    assert excinfo.value.status_code == 404
    assert excinfo.value.details["entity"] == "LocalList"
    assert excinfo.value.details["identifier"] == "999"


@pytest.mark.asyncio
async def test_all_mutating_methods_missing_raise_not_found() -> None:
    service = _service(_FakeListsRepo(deleted=False, renamed=None))

    calls = [
        service.rename_list(999, "renamed"),
        service.delete_list(999),
        service.add_galleries_to_list(999, [1]),
        service.remove_galleries_from_list(999, [1]),
    ]
    for call in calls:
        with pytest.raises(NotFoundError) as excinfo:
            await call
        assert excinfo.value.status_code == 404
        assert excinfo.value.details["entity"] == "LocalList"


@pytest.mark.asyncio
async def test_create_duplicate_raises_conflict_with_entity_id() -> None:
    service = _service(_FakeListsRepo(existing=_ExistingList()))

    with pytest.raises(ConflictError) as excinfo:
        await service.create_list("dup")

    assert excinfo.value.status_code == 409
    assert excinfo.value.details["entity_id"] == 7
    assert "already exists" in excinfo.value.message


@pytest.mark.asyncio
async def test_rename_duplicate_raises_conflict() -> None:
    service = _service(_FakeListsRepo(existing=_ExistingList()))

    with pytest.raises(ConflictError) as excinfo:
        await service.rename_list(1, "dup")

    assert excinfo.value.status_code == 409
    assert excinfo.value.details["entity_id"] == 7


@pytest.mark.asyncio
async def test_blank_name_raises_validation_not_type_error() -> None:
    service = _service(_FakeListsRepo())

    with pytest.raises(ValidationError) as excinfo:
        await service.create_list("   ")

    assert excinfo.value.status_code == 422
    assert excinfo.value.details["field"] == "name"


def _client(repo: _FakeListsRepo) -> TestClient:
    api = FastAPI()
    api.include_router(lists_router.router)
    api.dependency_overrides[lists_router.get_list_service] = lambda: _service(repo)
    api.dependency_overrides[lists_router.get_task_dispatcher] = lambda: _FakeDispatcher()
    return TestClient(api)


def test_routes_return_404_for_missing_list() -> None:
    client = _client(_FakeListsRepo(deleted=False, renamed=None))

    assert client.delete("/api/lists/999").status_code == 404
    assert client.patch("/api/lists/999", json={"name": "new"}).status_code == 404
    assert client.post("/api/lists/999/items", json={"gallery_ids": [1]}).status_code == 404
    assert client.post("/api/lists/999/items/remove", json={"gallery_ids": [1]}).status_code == 404


def test_route_returns_409_for_duplicate_name() -> None:
    client = _client(_FakeListsRepo(existing=_ExistingList()))

    response = client.post("/api/lists", json={"name": "dup"})
    assert response.status_code == 409

    response = client.patch("/api/lists/1", json={"name": "dup"})
    assert response.status_code == 409
