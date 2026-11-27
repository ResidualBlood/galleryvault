"""S6: archives preview leases the ExHentai client; download-missing refuses
to start a second metadata sync while one is already running (03 #7 / #17)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.params import Depends
from fastapi.testclient import TestClient

from galleryvault.app.exceptions import EhClientUnavailableError
from galleryvault.app.routers import favorites
from galleryvault.app.schemas import ArchivePreviewRequest
from galleryvault.app.state import app_state
from galleryvault.services.tasks import TaskManager

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Session:
    def __init__(self) -> None:
        self.rollbacks = 0

    async def rollback(self) -> None:
        self.rollbacks += 1


class _BoomClient:
    """Any use of the unleased app_state client must fail loudly."""

    def __getattr__(self, item: str) -> Any:
        raise AssertionError(f"app_state.eh_client.{item} must not be used")


class _ArchiveClient:
    def __init__(self) -> None:
        self.gp_calls = 0
        self.archive_calls = 0

    async def fetch_gp_balance(self) -> int:
        self.gp_calls += 1
        return 500

    async def fetch_archive_info(self, gid: int, token: str) -> Any:
        self.archive_calls += 1
        return SimpleNamespace(
            resample_url=None,
            resample_cost=0,
            resample_size=None,
            original_url="https://example/orig",
            original_cost=100,
            original_size=1024,
        )


class _FavRepo:
    def __init__(self, _session: object) -> None:
        pass

    async def favorite_items_detail_by_gids(
        self, gids: list[int]
    ) -> dict[int, dict[str, object]]:
        return {gid: {"token": "tok", "title": "Title"} for gid in gids}

    async def by_new_gids(self, gids: list[int]) -> list[object]:
        return []

    async def find_by_gids(self, gids: list[int]) -> list[object]:
        return []

    async def categories(self) -> list[object]:
        return [SimpleNamespace(favcat=0)]


async def _prepare(pairs: list[tuple[int, str]]) -> list[object]:
    return [
        SimpleNamespace(gone=False, token="tok", gid=gid, title="Title", title_jpn=None)
        for gid, _token in pairs
    ]


@pytest.fixture
def patched_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(favorites, "FavoritesRepository", _FavRepo)
    monkeypatch.setattr(favorites, "GalleryUpdatesRepository", _FavRepo)
    monkeypatch.setattr(favorites, "GalleryRepository", _FavRepo)
    monkeypatch.setattr(favorites, "prepare_galleries", _prepare)


# ---------------------------------------------------------------------------
# 03 #7: archives preview must use the leased client
# ---------------------------------------------------------------------------


def test_archives_preview_depends_on_leased_client() -> None:
    default = inspect.signature(favorites.archives_preview).parameters["leased_client"].default
    assert isinstance(default, Depends)
    assert default.dependency is favorites.get_leased_eh_client


async def test_archives_preview_uses_injected_lease(
    monkeypatch: pytest.MonkeyPatch, patched_repos: None
) -> None:
    monkeypatch.setattr(app_state, "eh_client", _BoomClient())
    client = _ArchiveClient()

    result = await favorites.archives_preview(
        ArchivePreviewRequest(gids=[42]),
        session=_Session(),
        leased_client=client,
    )

    assert result["funds"] == 500
    assert result["items"][0]["original_available"] is True
    assert client.gp_calls == 1
    assert client.archive_calls == 1


async def test_archives_preview_direct_call_leases_from_manager(
    monkeypatch: pytest.MonkeyPatch, patched_repos: None
) -> None:
    monkeypatch.setattr(app_state, "eh_client", _BoomClient())
    leased = _ArchiveClient()

    class _Mgr:
        def get_client(self) -> object:
            return leased

    monkeypatch.setattr(favorites, "get_eh_client_manager", lambda: _Mgr())

    result = await favorites.archives_preview(
        ArchivePreviewRequest(gids=[42]), session=_Session()
    )

    assert result["funds"] == 500
    assert leased.archive_calls == 1


async def test_archives_preview_returns_503_without_leased_client(
    monkeypatch: pytest.MonkeyPatch, patched_repos: None
) -> None:
    class _Mgr:
        def get_client(self) -> object:
            raise EhClientUnavailableError("no client")

    monkeypatch.setattr(favorites, "get_eh_client_manager", lambda: _Mgr())

    with pytest.raises(HTTPException) as exc:
        await favorites.archives_preview(
            ArchivePreviewRequest(gids=[42]), session=_Session()
        )
    assert exc.value.status_code == 503


def test_archives_preview_http_uses_lease_not_app_state(
    monkeypatch: pytest.MonkeyPatch, patched_repos: None
) -> None:
    """Regression: FastAPI's leased client must win over app_state.eh_client."""
    monkeypatch.setattr(app_state, "eh_client", _BoomClient())
    leased = _ArchiveClient()
    session = _Session()

    app = FastAPI()
    app.include_router(favorites.router)
    app.dependency_overrides[favorites.get_session] = lambda: session

    async def _leased() -> Any:
        yield leased

    app.dependency_overrides[favorites.get_leased_eh_client] = _leased

    try:
        with TestClient(app) as http:
            resp = http.post("/api/archives/preview", json={"gids": [42]})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["funds"] == 500
    assert leased.gp_calls == 1
    assert session.rollbacks >= 1


# ---------------------------------------------------------------------------
# 03 #17: download-missing must not stack another metadata sync
# ---------------------------------------------------------------------------


@pytest.fixture
def task_manager(monkeypatch: pytest.MonkeyPatch) -> TaskManager:
    tm = TaskManager()
    monkeypatch.setattr(app_state, "task_manager", tm)
    return tm


def _consume_spawn(coro: object, operation: str) -> object:
    close = getattr(coro, "close", None)
    if callable(close):
        close()
    return object()


async def test_download_missing_returns_409_when_sync_running(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_manager.metadata_sync_state["running"] = True
    spawned: list[str] = []
    monkeypatch.setattr(
        favorites, "spawn_task", lambda coro, op: (spawned.append(op), _consume_spawn(coro, op))[1]
    )

    with pytest.raises(HTTPException) as exc:
        await favorites.download_missing_favorites(session=MagicMock())

    assert exc.value.status_code == 409
    assert spawned == []


async def test_download_missing_starts_when_idle(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[str] = []
    monkeypatch.setattr(
        favorites, "spawn_task", lambda coro, op: (spawned.append(op), _consume_spawn(coro, op))[1]
    )
    monkeypatch.setattr(favorites, "FavoritesRepository", _FavRepo)

    result = await favorites.download_missing_favorites(session=_Session())

    assert result == {"status": "started", "favcats": [0]}
    assert spawned == ["favorite metadata sync 0"]
