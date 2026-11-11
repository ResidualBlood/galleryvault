"""Contract tests for the extracted favorites mutation service (R2 batch F1).

Pins the split boundary:

1. ``services/favorites_mutations.py`` exports exactly the public API the
   router delegates to and imports nothing from ``galleryvault.app`` (so the
   service layer stays below the HTTP layer).
2. Importing the service must not import any router module.
3. ``favorites_set_note`` remains a thin shell: the repository class, session
   release, task recorder and logger still come from the router module globals,
   so ``monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository")``
   keeps working and the response shape is unchanged.
4. Behaviour/order is unchanged: 422 validation happens before any cloud call,
   the pooled connection is released before the cloud call, and the local write
   only happens after cloud confirmation.
5. ``remove_favorites`` keeps the cloud-first contract: the injected
   ``delete_local`` (the router's ``delete_galleries_local`` patch target) is
   only reached for cloud-confirmed gids, and the router still records the task
   log from the returned counters.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from galleryvault.app.schemas import (
    FavoriteNoteRequest,
    FavoritesMoveRequest,
    FavoritesRemoveRequest,
)
from galleryvault.services import favorites_mutations as fm

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. module boundary
# ---------------------------------------------------------------------------


def test_service_exports_only_public_api() -> None:
    assert sorted(fm.__all__) == [
        "MutationDeps",
        "move_favorites",
        "remove_favorites",
        "set_favorite_note",
    ]


def _resolved_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = ["galleryvault", "services"]
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                modules.append(node.module or "")
                continue
            base = package[: len(package) - (node.level - 1)]
            tail = (node.module or "").split(".") if node.module else []
            modules.append(".".join(base + tail))
    return modules


def test_service_module_imports_no_app_layer() -> None:
    modules = _resolved_imports(Path(fm.__file__))
    assert "galleryvault.app" not in modules
    assert not [m for m in modules if m.startswith("galleryvault.app")]


def test_importing_service_does_not_import_routers() -> None:
    code = (
        "import sys, galleryvault.services.favorites_mutations;"
        "loaded = [n for n in sys.modules if n.startswith('galleryvault.app.routers')];"
        "assert not loaded, loaded"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_BACKEND_ROOT), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class _FakeSession:
    """Async session double recording transaction boundaries and scalars."""

    def __init__(self, scalars: list[Any] | None = None) -> None:
        self._scalars = list(scalars or [])
        self.events: list[str] = []
        self.in_tx = True

    def in_transaction(self) -> bool:
        return self.in_tx

    async def scalar(self, statement: Any) -> Any:
        return self._scalars.pop(0) if self._scalars else None

    async def rollback(self) -> None:
        self.in_tx = False
        self.events.append("rollback")

    async def commit(self) -> None:
        self.in_tx = False
        self.events.append("commit")


def _manager(client: Any) -> Any:
    class _Manager:
        @asynccontextmanager
        async def client_context(self, settings: Any = None) -> AsyncIterator[Any]:
            yield client

    return _Manager()


def _fake_task_manager() -> SimpleNamespace:
    recorded: list[dict[str, Any]] = []

    def record_task(
        kind: str,
        start: Any,
        finish: Any,
        status: str,
        reason: str = "",
        done: int = 0,
        total: int = 0,
    ) -> None:
        recorded.append({"kind": kind, "status": status, "done": done, "total": total})

    return SimpleNamespace(
        record_task=record_task, persist_history=lambda: None, recorded=recorded
    )


def _patch_task_manager(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    from galleryvault.app.routers import favorites as fav_mod

    tm = _fake_task_manager()
    monkeypatch.setattr(fav_mod, "get_task_manager", lambda: tm)
    monkeypatch.setattr(fav_mod, "spawn_task", lambda *a, **k: None)
    return tm


# ---------------------------------------------------------------------------
# 2. router is a thin shell over the patched globals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_uses_patched_favorites_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    seen = {"constructed": 0, "item_for_gid": 0, "update_note": 0}

    class PatchedRepo:
        def __init__(self, session: Any) -> None:
            seen["constructed"] += 1
            self.session = session

        async def item_for_gid(self, gid: int) -> Any:
            seen["item_for_gid"] += 1
            return SimpleNamespace(token="tok", favcat=2, gid=gid)

        async def update_note(self, gid: int, note: str, favcat: Any = None) -> int:
            seen["update_note"] += 1
            return 1

    class Client:
        async def add_favorite(
            self, gid: int, token: str, favcat: int, note: str = ""
        ) -> None:
            return None

    monkeypatch.setattr(fav_mod, "FavoritesRepository", PatchedRepo)
    _patch_task_manager(monkeypatch)

    result = await fav_mod.favorites_set_note(
        FavoriteNoteRequest(gid=77, note="hi", token="tok", favcat=2),
        session=_FakeSession(),
        eh_client_mgr=_manager(Client()),
    )

    # The service received the patched class, not its own import.
    assert seen == {"constructed": 2, "item_for_gid": 1, "update_note": 1}
    assert set(result) == {"gid", "cloud_ok", "local_updated", "note"}
    assert result == {"gid": 77, "cloud_ok": True, "local_updated": 1, "note": "hi"}


@pytest.mark.asyncio
async def test_router_records_task_through_patched_task_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def item_for_gid(self, gid: int) -> Any:
            return SimpleNamespace(token="tok", favcat=3, gid=gid)

        async def update_note(self, gid: int, note: str, favcat: Any = None) -> int:
            return 1

    class Client:
        async def add_favorite(
            self, gid: int, token: str, favcat: int, note: str = ""
        ) -> None:
            return None

    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    tm = _patch_task_manager(monkeypatch)

    await fav_mod.favorites_set_note(
        FavoriteNoteRequest(gid=5, note="n", token="tok", favcat=3),
        session=_FakeSession(),
        eh_client_mgr=_manager(Client()),
    )

    assert tm.recorded == [
        {"kind": "favorites-note", "status": "success", "done": 1, "total": 1}
    ]


# ---------------------------------------------------------------------------
# 3. unchanged validation / ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_token_is_422_before_release_and_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    cloud_calls: list[Any] = []

    class Client:
        async def add_favorite(self, *args: Any, **kwargs: Any) -> None:
            cloud_calls.append(args)

    session = _FakeSession(scalars=[None, None])
    _patch_task_manager(monkeypatch)

    with pytest.raises(HTTPException) as excinfo:
        await fav_mod.favorites_set_note(
            FavoriteNoteRequest(gid=4242, note="hello", favcat=3),
            session=session,
            eh_client_mgr=_manager(Client()),
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "token is required"
    assert cloud_calls == []
    assert session.events == []


@pytest.mark.asyncio
async def test_missing_favcat_is_422_not_in_favorites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def item_for_gid(self, gid: int) -> Any:
            return SimpleNamespace(token=None, favcat=None, gid=gid)

    class Client:
        async def add_favorite(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("cloud must not be called")

    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    session = _FakeSession()
    _patch_task_manager(monkeypatch)

    with pytest.raises(HTTPException) as excinfo:
        await fav_mod.favorites_set_note(
            FavoriteNoteRequest(gid=4242, note="hello", token="tok"),
            session=session,
            eh_client_mgr=_manager(Client()),
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "not in favorites"
    assert session.events == []


@pytest.mark.asyncio
async def test_release_before_cloud_and_local_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    events: list[str] = []

    class Session(_FakeSession):
        async def rollback(self) -> None:
            self.in_tx = False
            events.append("rollback")

        async def commit(self) -> None:
            self.in_tx = False
            events.append("commit")

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def item_for_gid(self, gid: int) -> Any:
            return SimpleNamespace(token="tok", favcat=3, gid=gid)

        async def update_note(self, gid: int, note: str, favcat: Any = None) -> int:
            events.append("write")
            return 1

    class Client:
        async def add_favorite(
            self, gid: int, token: str, favcat: int, note: str = ""
        ) -> None:
            events.append("network")

    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    session = Session()
    _patch_task_manager(monkeypatch)

    result = await fav_mod.favorites_set_note(
        FavoriteNoteRequest(gid=42, note="hello"),
        session=session,
        eh_client_mgr=_manager(Client()),
    )

    assert result["cloud_ok"] is True
    assert events.index("rollback") < events.index("network")
    assert events.index("network") < events.index("write")


@pytest.mark.asyncio
async def test_cloud_failure_skips_local_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    writes: list[Any] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def item_for_gid(self, gid: int) -> Any:
            return SimpleNamespace(token="tok", favcat=2, gid=gid)

        async def update_note(self, *args: Any, **kwargs: Any) -> int:
            writes.append(args)
            return 1

    class Client:
        async def add_favorite(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("cloud down")

    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    tm = _patch_task_manager(monkeypatch)

    result = await fav_mod.favorites_set_note(
        FavoriteNoteRequest(gid=11, note="secret", token="tok", favcat=2),
        session=_FakeSession(),
        eh_client_mgr=_manager(Client()),
    )

    assert result == {"gid": 11, "cloud_ok": False, "local_updated": 0, "note": None}
    assert writes == []
    assert tm.recorded == [
        {"kind": "favorites-note", "status": "failed", "done": 0, "total": 1}
    ]


# ---------------------------------------------------------------------------
# 4. remove: cloud confirmation gates every local delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_uses_patched_delete_local_for_confirmed_gids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    removed: list[list[int]] = []
    deleted: list[tuple[list[int], dict[str, Any]]] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def remove_gids(self, gids: list[int]) -> int:
            removed.append(list(gids))
            return len(gids)

        async def galleries_for_gids(self, gids: list[int]) -> dict[int, int]:
            return {gid: gid * 10 for gid in gids}

    async def fake_delete(
        gallery_ids: list[int], **kwargs: Any
    ) -> list[dict[str, Any]]:
        deleted.append((list(gallery_ids), kwargs))
        return [
            {"db_removed": True, "trashed": False, "failed_paths": []},
            {"db_removed": False, "trashed": False, "failed_paths": ["/tmp/gone.jpg"]},
        ]

    class Client:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            return [200]

    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    monkeypatch.setattr(fav_mod, "delete_galleries_local", fake_delete)
    tm = _patch_task_manager(monkeypatch)

    result = await fav_mod.favorites_remove(
        FavoritesRemoveRequest(gids=[100, 200, 100], delete_local=True),
        session=_FakeSession(),
        eh_client_mgr=_manager(Client()),
    )

    assert result == {
        "gids": [100, 200],
        "cloud_ok": False,
        "cloud_removed": 1,
        "cloud_failed": [200],
        "local_removed": 1,
        "deleted_local_galleries": 1,
        "failed_deletions": ["/tmp/gone.jpg"],
    }
    assert removed == [[100]]
    assert deleted == [([1000], {"delete_files": True, "delete_all_copies": False})]
    # The task log still comes from the router helper, fed by the service result.
    assert tm.recorded == [
        {"kind": "favorites-remove", "status": "failed", "done": 1, "total": 2}
    ]


@pytest.mark.asyncio
async def test_remove_cloud_failure_never_touches_local_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    calls: list[str] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            calls.append("repo")

        async def remove_gids(self, gids: list[int]) -> int:
            calls.append("remove_gids")
            return len(gids)

        async def galleries_for_gids(self, gids: list[int]) -> dict[int, int]:
            calls.append("galleries_for_gids")
            return {}

    async def fake_delete(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls.append("delete_local")
        return []

    class Client:
        async def remove_favorites(self, gids: list[int]) -> list[int]:
            raise RuntimeError("cloud down")

    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    monkeypatch.setattr(fav_mod, "delete_galleries_local", fake_delete)
    tm = _patch_task_manager(monkeypatch)

    result = await fav_mod.favorites_remove(
        FavoritesRemoveRequest(gids=[7, 8], delete_local=True, delete_files=True),
        session=_FakeSession(),
        eh_client_mgr=_manager(Client()),
    )

    assert result["cloud_ok"] is False
    assert result["cloud_removed"] == 0
    assert result["cloud_failed"] == [7, 8]
    assert result["local_removed"] == 0
    assert result["deleted_local_galleries"] == 0
    assert result["failed_deletions"] == []
    assert calls == []
    assert tm.recorded == [
        {"kind": "favorites-remove", "status": "failed", "done": 0, "total": 2}
    ]


@pytest.mark.asyncio
async def test_remove_empty_gids_is_422_before_any_cloud_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class Manager:
        @asynccontextmanager
        async def client_context(self, settings: Any = None) -> AsyncIterator[Any]:
            raise AssertionError("cloud must not be called")
            yield  # pragma: no cover

    with pytest.raises(HTTPException) as excinfo:
        await fav_mod.favorites_remove(
            FavoritesRemoveRequest(gids=[]),
            session=_FakeSession(),
            eh_client_mgr=Manager(),
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "no galleries selected"


# ---------------------------------------------------------------------------
# 5. move: one deduped gid list feeds both phases, log stays in the router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_uses_patched_repository_and_records_move_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    moved: list[tuple[list[int], int]] = []

    class Repo:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            moved.append((list(gids), target_favcat))
            return len(gids)

    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[list[int], int]] = []

        async def move_favorites(
            self, gids: list[int], target_favcat: int
        ) -> list[int]:
            self.calls.append((list(gids), target_favcat))
            return [200]

    client = Client()
    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)
    tm = _patch_task_manager(monkeypatch)

    result = await fav_mod.favorites_move(
        FavoritesMoveRequest(gids=[100, 200, 100, 200], target_favcat=3),
        session=_FakeSession(),
        eh_client_mgr=_manager(client),
    )

    assert result == {
        "gids": [100, 200],
        "target_favcat": 3,
        "cloud_ok": False,
        "cloud_moved": 1,
        "cloud_failed": [200],
        "local_moved": 1,
    }
    # Same deduped list for the cloud call and the local transaction, and the
    # repository class comes from the router module (patch target stays valid).
    assert client.calls == [([100, 200], 3)]
    assert moved == [([100], 3)]
    # The task log is still emitted by the router helper, fed by the result.
    assert tm.recorded == [
        {"kind": "favorites-move", "status": "failed", "done": 1, "total": 2}
    ]
