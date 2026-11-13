"""Regression tests: favorites remove/move must lease the real EhClientManager.

The production manager exposes ``client_context()`` without a ``settings``
parameter, while ``services.favorites_mutations.remove_favorites`` /
``move_favorites`` call ``client_context(settings=settings)``.  Before the fix,
``POST /api/favorites/remove`` handed the raw manager to the service, so the
call raised ``TypeError`` and every gid landed in ``cloud_failed`` (observed as
``cloud favorite removal failed [error='TypeError']`` in real EH testing).

These tests deliberately use the real ``EhClientManager`` (not a lenient mock
whose ``client_context`` accepts ``settings``), because the lenient mock is what
hid the signature mismatch.  They pin the dual-write rule: only cloud-confirmed
gids may be updated locally.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Self

import pytest

from galleryvault.app.core.eh_client_manager import EhClientManager


class _DummySession:
    def begin(self) -> Self:
        return self

    def in_transaction(self) -> bool:
        return False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


async def _dummy_get_session() -> Any:
    yield _DummySession()


def _quiet_task_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import favorites as router_module

    monkeypatch.setattr(
        router_module,
        "get_task_manager",
        lambda: SimpleNamespace(record_task=lambda *a, **k: None, persist_history=lambda: None),
    )
    monkeypatch.setattr(router_module, "spawn_task", lambda *a, **k: None)


def _strict_manager(client: Any) -> EhClientManager:
    """A real manager whose leased client is the supplied stand-in.

    ``EhClientManager.client_context()`` takes no ``settings`` argument, which is
    exactly the contract the router has to satisfy.
    """
    return EhClientManager(client_getter=lambda: client)


def test_real_manager_client_context_rejects_settings_kwarg() -> None:
    """Document the contract that made the old router path fail with TypeError."""

    manager = _strict_manager(object())
    with pytest.raises(TypeError):
        manager.client_context(settings=object())


@pytest.mark.asyncio
async def test_router_remove_with_real_manager_updates_local_for_confirmed_gids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as router_module

    cloud_calls: list[list[int]] = []
    removed_gids: list[list[int]] = []
    deleted_ids: list[list[int]] = []

    class Client:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            cloud_calls.append(list(gids))
            return [200]  # 200 failed in the cloud, 100 confirmed

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

    _quiet_task_manager(monkeypatch)
    monkeypatch.setattr(router_module, "FavoritesRepository", Repo)
    monkeypatch.setattr(router_module, "delete_galleries_local", fake_delete)
    monkeypatch.setattr(router_module, "get_session", _dummy_get_session)

    result = await router_module.favorites_remove(
        router_module.FavoritesRemoveRequest(gids=[100, 200], delete_local=True),
        eh_client_mgr=_strict_manager(Client()),
    )

    assert cloud_calls == [[100, 200]]
    assert result["cloud_ok"] is False
    assert result["cloud_failed"] == [200]
    assert result["cloud_removed"] == 1
    assert result["local_removed"] == 1
    assert removed_gids == [[100]], "only cloud-confirmed gids may be removed locally"
    assert deleted_ids == [[1000]]


@pytest.mark.asyncio
async def test_router_remove_full_success_with_real_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as router_module

    removed_gids: list[list[int]] = []

    class Client:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            return []

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def remove_gids(self, gids: list[int]) -> int:
            removed_gids.append(list(gids))
            return len(gids)

    _quiet_task_manager(monkeypatch)
    monkeypatch.setattr(router_module, "FavoritesRepository", Repo)
    monkeypatch.setattr(router_module, "get_session", _dummy_get_session)

    result = await router_module.favorites_remove(
        router_module.FavoritesRemoveRequest(gids=[11, 12]),
        eh_client_mgr=_strict_manager(Client()),
    )

    assert result["cloud_ok"] is True
    assert result["cloud_failed"] == []
    assert result["local_removed"] == 2
    assert removed_gids == [[11, 12]]


@pytest.mark.asyncio
async def test_router_move_with_real_manager_updates_local_for_confirmed_gids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as router_module

    cloud_calls: list[tuple[list[int], int]] = []
    moved: list[tuple[list[int], int]] = []

    class Client:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            cloud_calls.append((list(gids), target_favcat))
            return [200]

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            moved.append((list(gids), target_favcat))
            return len(gids)

    _quiet_task_manager(monkeypatch)
    monkeypatch.setattr(router_module, "FavoritesRepository", Repo)
    monkeypatch.setattr(router_module, "get_session", _dummy_get_session)

    result = await router_module.favorites_move(
        router_module.FavoritesMoveRequest(gids=[100, 200], target_favcat=3),
        eh_client_mgr=_strict_manager(Client()),
    )

    assert cloud_calls == [([100, 200], 3)]
    assert result["cloud_ok"] is False
    assert result["cloud_failed"] == [200]
    assert result["cloud_moved"] == 1
    assert result["local_moved"] == 1
    assert moved == [([100], 3)], "only cloud-confirmed gids may be moved locally"
