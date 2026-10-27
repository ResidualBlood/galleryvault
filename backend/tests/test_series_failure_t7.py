"""T7: series rebuild must surface failures instead of reporting success."""

from __future__ import annotations

from typing import Any, Self
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from galleryvault.app.core.task_dispatcher import TaskDispatcher
from galleryvault.app.dependencies import get_task_dispatcher
from galleryvault.app.routers import series as series_router
from galleryvault.services.series import rebuild_series_groups


class _FakeTaskManager:
    def __init__(self) -> None:
        self.task_history: list[dict[str, Any]] = []

    def record_task(
        self,
        task: str,
        started_at: str | None,
        completed_at: str | None,
        status: str,
        reason: str = "",
        done: int = 0,
        total: int = 0,
    ) -> None:
        self.task_history.insert(
            0,
            {
                "task": task,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": status,
                "reason": reason,
                "done": done,
                "total": total,
            },
        )

    async def persist_history(self) -> None:
        return None


class _DummySession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _DummySessionFactory:
    def __call__(self) -> _DummySession:
        return _DummySession()


@pytest.mark.asyncio
async def test_rebuild_series_groups_propagates_repository_error() -> None:
    repo = AsyncMock()
    repo.get_auto_series.side_effect = RuntimeError("db down")

    with (
        patch("galleryvault.services.series.SeriesRepository", return_value=repo),
        pytest.raises(RuntimeError, match="db down"),
    ):
        await rebuild_series_groups(session_factory=_DummySessionFactory())


@pytest.mark.asyncio
async def test_rebuild_series_groups_raises_without_session_factory(monkeypatch) -> None:
    from galleryvault.app.state import app_state

    monkeypatch.setattr(app_state, "session_factory", None)
    monkeypatch.setattr(app_state, "worker_session_factory", None)

    with pytest.raises(RuntimeError, match="session factory"):
        await rebuild_series_groups()


def test_rebuild_route_returns_500_and_records_failed_task(monkeypatch) -> None:
    tm = _FakeTaskManager()
    dispatcher = TaskDispatcher(task_manager_getter=lambda: tm)

    api = FastAPI()
    api.include_router(series_router.router)
    api.dependency_overrides[get_task_dispatcher] = lambda: dispatcher

    monkeypatch.setattr(
        series_router,
        "rebuild_series_groups",
        AsyncMock(side_effect=RuntimeError("rebuild exploded")),
    )

    client = TestClient(api, raise_server_exceptions=False)
    response = client.post("/api/series/rebuild")

    assert response.status_code == 500
    assert tm.task_history, "failed rebuild must be recorded in task history"
    record = tm.task_history[0]
    assert record["task"] == "series-rebuild"
    assert record["status"] == "failed"
    assert "rebuild exploded" in str(record["reason"])


def test_rebuild_route_records_success_on_success(monkeypatch) -> None:
    tm = _FakeTaskManager()
    dispatcher = TaskDispatcher(task_manager_getter=lambda: tm)

    api = FastAPI()
    api.include_router(series_router.router)
    api.dependency_overrides[get_task_dispatcher] = lambda: dispatcher

    monkeypatch.setattr(
        series_router,
        "rebuild_series_groups",
        AsyncMock(return_value={"created": 1, "merged": 3}),
    )

    client = TestClient(api)
    response = client.post("/api/series/rebuild")

    assert response.status_code == 200
    assert response.json()["rebuilt"] is True
    assert tm.task_history[0]["status"] == "success"
