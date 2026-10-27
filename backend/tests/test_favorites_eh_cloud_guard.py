"""Regression tests for the favorites/ExHentai dual-state write path.

Covers: HTTP-200-but-logged-out favorites responses, quota classification,
router-side "cloud failed gid never touches local state", FavoriteService
success/failure inversion, note ordering, is_configured(), create_task
retirement references, and the favorites worker skip-branch transaction.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self

import httpx
import pytest

from galleryvault.app.core.eh_client_manager import EhClientManager
from galleryvault.config import Settings
from galleryvault.services.eh_client import (
    EhClient,
    EhClientError,
    EhQuotaExceededError,
)


def _favorites_page(*favcats: int) -> str:
    ids = favcats or tuple(range(10))
    links = "".join(
        f'<a href="favorites.php?favcat={favcat}">Favorite {favcat}</a>' for favcat in ids
    )
    return f'<html><body><div class="fp">{links}</div></body></html>'


def _client(handler: Any) -> EhClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(base_url="https://exhentai.org", transport=transport)
    return EhClient(
        Settings(exhentai_base_url="https://exhentai.org"), client=http_client
    )


# ---------------------------------------------------------------------------
# EhClient: favorites write response validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_favorites_rejects_http_200_logged_out_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>You must be logged in to view this page.</body></html>")

    client = _client(handler)
    try:
        with pytest.raises(EhClientError):
            await client.remove_favorites([123])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_remove_favorites_rejects_empty_http_200_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="   ")

    client = _client(handler)
    try:
        with pytest.raises(EhClientError):
            await client.remove_favorites([123])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_remove_favorites_accepts_real_favorites_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_favorites_page())

    client = _client(handler)
    try:
        assert await client.remove_favorites([123]) == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_move_favorites_rejects_http_200_logged_out_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>Sad Panda</body></html>")

    client = _client(handler)
    try:
        with pytest.raises(EhClientError):
            await client.move_favorites([123], target_favcat=3)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_move_favorites_requires_target_favcat_in_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_favorites_page(0, 1, 2))

    client = _client(handler)
    try:
        with pytest.raises(EhClientError):
            await client.move_favorites([123], target_favcat=3)
        assert await client.move_favorites([123], target_favcat=2) == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_favorites_write_http_500_raises_eh_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _client(handler)
    try:
        with pytest.raises(EhClientError) as remove_exc:
            await client.remove_favorites([123])
        with pytest.raises(EhClientError) as move_exc:
            await client.move_favorites([123], target_favcat=2)
    finally:
        await client.aclose()
    assert not isinstance(remove_exc.value, httpx.HTTPStatusError)
    assert not isinstance(move_exc.value, httpx.HTTPStatusError)


# ---------------------------------------------------------------------------
# EhClient: quota classification / retry-after
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_429_maps_to_quota_error_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "120"}, text="slow down")

    client = _client(handler)
    try:
        with pytest.raises(EhQuotaExceededError) as exc_info:
            await client.fetch_favorites(0)
    finally:
        await client.aclose()
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_delay() == 120.0


@pytest.mark.asyncio
async def test_http_509_maps_to_quota_error_with_default_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(509, text="quota")

    client = _client(handler)
    try:
        with pytest.raises(EhQuotaExceededError) as exc_info:
            await client.remove_favorites([1])
    finally:
        await client.aclose()
    assert exc_info.value.retry_after is None
    assert exc_info.value.retry_delay() == 60.0
    assert exc_info.value.retry_delay(default=15.0) == 15.0


@pytest.mark.asyncio
async def test_request_wraps_httpx_status_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(500, text="boom", request=request)
        response.raise_for_status()  # raises httpx.HTTPStatusError inside the transport

    client = _client(handler)
    try:
        with pytest.raises(EhClientError) as exc_info:
            await client._request("GET", "/favorites.php")
    finally:
        await client.aclose()
    assert not isinstance(exc_info.value, httpx.HTTPStatusError)


# ---------------------------------------------------------------------------
# Router: cloud failure must not touch local state
# ---------------------------------------------------------------------------


class _DummySession:
    def begin(self) -> _DummySession:
        return self

    def in_transaction(self) -> bool:
        return False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


async def _dummy_get_session() -> Any:
    yield _DummySession()


class _FakeManager:
    def __init__(self, client: Any) -> None:
        self.client = client

    @asynccontextmanager
    async def client_context(self, settings: Any = None) -> Any:
        yield self.client


@pytest.mark.asyncio
async def test_router_remove_200_logout_page_keeps_local_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from galleryvault.app.routers import favorites as router_module

    local_file = tmp_path / "001.jpg"
    local_file.write_bytes(b"data")
    deleted_ids: list[list[int]] = []
    removed_gids: list[list[int]] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def galleries_for_gids(self, gids: list[int]) -> dict[int, int]:
            return {gid: 1 for gid in gids}

        async def remove_gids(self, gids: list[int]) -> int:
            removed_gids.append(list(gids))
            return len(gids)

    async def fake_delete(gallery_ids: list[int], **kwargs: Any) -> list[dict[str, Any]]:
        deleted_ids.append(list(gallery_ids))
        local_file.unlink(missing_ok=True)
        return [{"db_removed": False, "trashed": True, "failed_paths": []}]

    class LogoutClient:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            raise EhClientError("ExTantai authentication is required or expired")

    monkeypatch.setattr(router_module, "FavoritesRepository", Repo)
    monkeypatch.setattr(router_module, "delete_galleries_local", fake_delete)
    monkeypatch.setattr(router_module, "get_session", _dummy_get_session)

    res = await router_module.favorites_remove(
        router_module.FavoritesRemoveRequest(gids=[999], delete_local=True),
        eh_client_mgr=_FakeManager(LogoutClient()),
    )

    assert res["cloud_ok"] is False
    assert res["cloud_failed"] == [999]
    assert res["local_removed"] == 0
    assert removed_gids == []
    assert deleted_ids == []
    assert local_file.exists(), "cloud failure must never delete local files"


@pytest.mark.asyncio
async def test_router_remove_partial_failure_only_updates_successful_gids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from galleryvault.app.routers import favorites as router_module

    deleted_ids: list[list[int]] = []
    removed_gids: list[list[int]] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def galleries_for_gids(self, gids: list[int]) -> dict[int, int]:
            return {gid: gid * 10 for gid in gids}

        async def remove_gids(self, gids: list[int]) -> int:
            removed_gids.append(list(gids))
            return len(gids)

    async def fake_delete(gallery_ids: list[int], **kwargs: Any) -> list[dict[str, Any]]:
        deleted_ids.append(list(gallery_ids))
        return [{"db_removed": False, "trashed": True, "failed_paths": []}]

    class PartialClient:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            return [200]

    monkeypatch.setattr(router_module, "FavoritesRepository", Repo)
    monkeypatch.setattr(router_module, "delete_galleries_local", fake_delete)
    monkeypatch.setattr(router_module, "get_session", _dummy_get_session)

    res = await router_module.favorites_remove(
        router_module.FavoritesRemoveRequest(gids=[100, 200], delete_local=True),
        eh_client_mgr=_FakeManager(PartialClient()),
    )

    assert res["cloud_failed"] == [200]
    assert res["local_removed"] == 1
    assert removed_gids == [[100]]
    assert deleted_ids == [[1000]]


@pytest.mark.asyncio
async def test_router_move_partial_failure_only_updates_successful_gids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as router_module

    moved: list[tuple[list[int], int]] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            moved.append((list(gids), target_favcat))
            return len(gids)

    class PartialClient:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            return [200]

    monkeypatch.setattr(router_module, "FavoritesRepository", Repo)
    monkeypatch.setattr(router_module, "get_session", _dummy_get_session)

    res = await router_module.favorites_move(
        router_module.FavoritesMoveRequest(gids=[100, 200], target_favcat=3),
        eh_client_mgr=_FakeManager(PartialClient()),
    )

    assert res["cloud_failed"] == [200]
    assert res["local_moved"] == 1
    assert moved == [([100], 3)]


# ---------------------------------------------------------------------------
# FavoriteService: failure/success inversion, cloud-first note, is_configured
# ---------------------------------------------------------------------------


class _FakeUow:
    def __init__(self, repo: Any) -> None:
        self.favorites = repo

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeRepo:
    def __init__(self) -> None:
        self.moved: list[tuple[list[int], int]] = []
        self.removed: list[list[int]] = []
        self.notes: list[tuple[int, str, int | None]] = []
        self.item: Any = SimpleNamespace(token="tok", favcat=2)

    async def move_gids(self, gids: list[int], target_favcat: int) -> int:
        self.moved.append((list(gids), target_favcat))
        return len(gids)

    async def remove_gids(self, gids: list[int]) -> int:
        self.removed.append(list(gids))
        return len(gids)

    async def item_for_gid(self, gid: int) -> Any:
        return self.item

    async def update_note(self, gid: int, note: str, favcat: int | None = None) -> int:
        self.notes.append((gid, note, favcat))
        return 1


def _service(repo: _FakeRepo, client: Any) -> Any:
    from galleryvault.services.favorite_service import FavoriteService

    manager = EhClientManager(
        client_getter=lambda: client,
        settings_getter=lambda: Settings(exhentai_cookies={"ipb_member_id": "x"}),
    )
    return FavoriteService(_FakeUow(repo), eh_client_manager=manager)


@pytest.mark.asyncio
async def test_favorite_service_move_uses_failed_gids_correctly() -> None:
    repo = _FakeRepo()

    class Client:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            return [200]

    service = _service(repo, Client())
    result = await service.move_favorites([100, 200], target_favcat=3)

    assert repo.moved == [([100], 3)]
    assert result.succeeded == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_favorite_service_remove_uses_failed_gids_correctly() -> None:
    repo = _FakeRepo()

    class Client:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            return [200]

    service = _service(repo, Client())
    result = await service.remove_favorites([100, 200])

    assert repo.removed == [[100]]
    assert result.succeeded == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_favorite_service_update_note_writes_cloud_before_local() -> None:
    repo = _FakeRepo()
    order: list[str] = []

    class Client:
        async def add_favorite(self, gid: int, token: str, favcat: int, note: str = "") -> None:
            order.append(f"cloud:{gid}:{token}:{favcat}:{note}")

    async def update_note(gid: int, note: str, favcat: int | None = None) -> int:
        order.append(f"local:{gid}:{note}")
        return 1

    repo.update_note = update_note  # type: ignore[method-assign]
    service = _service(repo, Client())

    assert await service.update_note(5, "hello") is True
    assert order == ["cloud:5:tok:2:hello", "local:5:hello"]


@pytest.mark.asyncio
async def test_favorite_service_update_note_cloud_failure_skips_local() -> None:
    repo = _FakeRepo()
    local_calls: list[Any] = []

    class Client:
        async def add_favorite(self, gid: int, token: str, favcat: int, note: str = "") -> None:
            raise EhClientError("nope")

    async def update_note(gid: int, note: str, favcat: int | None = None) -> int:
        local_calls.append((gid, note))
        return 1

    repo.update_note = update_note  # type: ignore[method-assign]
    service = _service(repo, Client())

    assert await service.update_note(5, "hello") is False
    assert local_calls == []


def test_is_configured_checks_real_settings_field() -> None:
    configured = EhClientManager(
        settings_getter=lambda: Settings(exhentai_cookies={"ipb_member_id": "x"})
    )
    empty = EhClientManager(settings_getter=lambda: Settings(exhentai_cookies={}))
    assert configured.is_configured() is True
    assert empty.is_configured() is False


# ---------------------------------------------------------------------------
# EhClientManager: retirement task keeps a strong reference
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retire_client_keeps_task_reference_until_closed() -> None:
    closed = asyncio.Event()

    class Client:
        async def aclose(self) -> None:
            closed.set()

    manager = EhClientManager(client_getter=lambda: None)
    client = Client()
    manager.retire_client(client, delay=0)

    assert len(manager._retire_tasks) == 1
    await asyncio.wait_for(closed.wait(), timeout=2)
    await asyncio.sleep(0)
    assert client not in manager.retiring_clients
    assert manager._retire_tasks == set()


# ---------------------------------------------------------------------------
# Favorites worker: skip branch must not nest session.begin()
# ---------------------------------------------------------------------------


class _AutobeginSession:
    """Session that raises like SQLAlchemy when begin() nests after a read."""

    def __init__(self, repo: Any) -> None:
        self._repo = repo
        self.in_tx = False
        self.begin_calls = 0
        self.commits = 0

    def mark_read(self) -> None:
        self.in_tx = True

    def in_transaction(self) -> bool:
        return self.in_tx

    def begin(self) -> _AutobeginSession:
        self.begin_calls += 1
        if self.in_tx:
            raise AssertionError("nested session.begin()")
        self.in_tx = True
        return self

    async def commit(self) -> None:
        self.commits += 1
        self.in_tx = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_favorites_skip_branch_does_not_nest_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.services import favorites_worker as fw

    sessions: list[_AutobeginSession] = []
    checked: list[tuple[int, bool]] = []

    class Repo:
        def __init__(self, session: _AutobeginSession) -> None:
            self.session = session

        async def category(self, favcat: int) -> Any:
            self.session.mark_read()
            return SimpleNamespace(
                favcat=favcat, last_success_at=object(), enabled=True, mode="incremental"
            )

        async def count_known_gids(self, favcat: int) -> int:
            return 10

        async def checked(self, favcat: int, success: bool) -> None:
            checked.append((favcat, success))

    def factory() -> _AutobeginSession:
        session = _AutobeginSession(Repo(None))  # type: ignore[arg-type]
        session._repo = Repo(session)
        sessions.append(session)
        return session

    class Service:
        async def check_category(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("skip branch must not run a full check")

    tm = app_state.task_manager
    original_state = tm.favorites_check_state
    orig_factory = app_state.session_factory
    tm.favorites_check_state = {
        "running": False,
        "categories": {},
        "last_error": None,
        "started_at": None,
        "completed_at": None,
        "history_recorded": False,
        "skip_counts": {"1": 2},
    }

    async def _fake_counts(*a: Any, **k: Any) -> dict[int, int]:
        return {1: 10}

    try:
        app_state.session_factory = factory
        monkeypatch.setattr(fw, "FavoritesRepository", lambda session: session._repo)
        monkeypatch.setattr(fw, "favorite_counts_cached", _fake_counts)
        monkeypatch.setattr(tm, "record_task", lambda *a, **k: None)

        await fw.run_favorites_check(1, Service(), scheduled=True)
    finally:
        tm.favorites_check_state = original_state
        app_state.session_factory = orig_factory

    assert checked == [(1, True)]
    assert all(session.begin_calls == 0 for session in sessions)
