"""T5: separate "seen on the cloud" from "successfully enqueued".

A favorite whose download task could not be created must not be recorded as a
known item: otherwise the next incremental check filters it out and the
download is lost forever.  These tests reproduce the audit probe (first
enqueue fails, second run succeeds) and check that the worker keeps the failed
state instead of overwriting it with ``checked(True)``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Self

import pytest

from galleryvault.app.state import app_state
from galleryvault.services import favorites_worker as fw
from galleryvault.services.eh_client import FavoriteItems
from galleryvault.services.favorites import FavoritesCheckResult, FavoritesService

FAVCAT = 3


def _item(gid: int) -> SimpleNamespace:
    return SimpleNamespace(gid=gid, token=f"tok{gid}", title=f"G{gid}", url=f"/g/{gid}/")


def _listing(items: list[SimpleNamespace]) -> FavoriteItems:
    return FavoriteItems(items)


class _Repo:
    """In-memory favourite store mirroring the repository contract."""

    def __init__(self) -> None:
        self.known: set[int] = set()
        self.remembered: list[int] = []
        self.pruned: list[set[int]] = []

    async def category(self, favcat: int) -> Any:
        return SimpleNamespace(name="Folder")

    async def known_gids(self, favcat: int) -> set[int]:
        return set(self.known)

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        return set()

    async def remember(self, favcat: int, item: Any) -> None:
        self.known.add(item.gid)
        self.remembered.append(item.gid)

    async def remember_many(self, favcat: int, items: list[Any]) -> None:
        for item in items:
            await self.remember(favcat, item)

    async def prune(
        self, favcat: int, current_gids: set[int], allow_empty: bool = False
    ) -> int:
        self.pruned.append(set(current_gids))
        stale = self.known - set(current_gids)
        self.known -= stale
        return len(stale)

    async def checked(self, favcat: int, success: bool) -> None:
        pass


class _Fetcher:
    def __init__(self, items: list[SimpleNamespace]) -> None:
        self.items = items

    async def fetch_favorites(self, favcat: int, progress: Any = None) -> FavoriteItems:
        return _listing(self.items)


class _FlakyQueue:
    """Fails ``enqueue`` for the gids in ``fail_gids`` on every attempt."""

    def __init__(self, fail_gids: set[int] | None = None) -> None:
        self.fail_gids = set(fail_gids or ())
        self.calls: list[int] = []

    async def enqueue(self, item: Any, mode: Any = None, quality: Any = None) -> bool:
        self.calls.append(item.gid)
        if item.gid in self.fail_gids:
            raise RuntimeError("enqueue exploded")
        return True


@pytest.mark.asyncio
async def test_failed_enqueue_is_retried_until_it_succeeds() -> None:
    repo = _Repo()
    queue = _FlakyQueue({1})
    service = FavoritesService(
        fetcher=_Fetcher([_item(1)]), repository=repo, queue=queue
    )

    first = await service.check_category(0)

    assert first.failed == 1 and first.downloaded == 0
    assert queue.calls == [1]
    assert repo.remembered == [], "a failed enqueue must not be remembered as seen"
    assert repo.known == set()

    queue.fail_gids.clear()
    second = await service.check_category(0)

    assert queue.calls == [1, 1], "the failed gid must be offered again"
    assert second.new == 1 and second.downloaded == 1 and second.failed == 0
    assert repo.remembered == [1], "only a successful enqueue is remembered"


@pytest.mark.asyncio
async def test_only_successful_gids_are_remembered_in_a_mixed_batch() -> None:
    repo = _Repo()
    queue = _FlakyQueue({2})
    service = FavoritesService(
        fetcher=_Fetcher([_item(1), _item(2)]), repository=repo, queue=queue
    )

    result = await service.check_category(0)

    assert result.downloaded == 1 and result.failed == 1
    assert repo.remembered == [1]
    assert repo.known == {1}


# ---------------------------------------------------------------------------
# Worker: an enqueue failure must not be recorded as a successful check
# ---------------------------------------------------------------------------


class _WorkerStore:
    def __init__(self) -> None:
        self.times: dict[int, datetime] = {}
        self.checked: list[tuple[int, bool]] = []
        self.spawned: list[str] = []


def _install_worker(
    monkeypatch: pytest.MonkeyPatch, store: _WorkerStore
) -> None:
    class Repo:
        async def category(self, favcat: int) -> SimpleNamespace:
            return SimpleNamespace(
                favcat=favcat,
                last_success_at=object(),
                enabled=True,
                mode="incremental",
            )

        async def known_gids(self, favcat: int) -> set[int]:
            return set()

        async def full_check_times(self) -> dict[int, datetime]:
            return dict(store.times)

        async def set_full_check_time(
            self, favcat: int, when: datetime | None = None
        ) -> None:
            store.times[favcat] = when or datetime.now(UTC)

        async def checked(self, favcat: int, success: bool) -> None:
            store.checked.append((favcat, success))

    class Session:
        def __init__(self) -> None:
            self._repo = Repo()

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

        def begin(self) -> Session:
            return self

    def fake_spawn(coro: Any, operation: str) -> None:
        store.spawned.append(operation)
        if hasattr(coro, "close"):
            coro.close()

    async def fake_counts(*args: Any, **kwargs: Any) -> dict[int, int]:
        return {FAVCAT: 0}

    tm = app_state.task_manager
    monkeypatch.setattr(
        tm,
        "favorites_check_state",
        {
            "running": False,
            "categories": {},
            "last_error": None,
            "started_at": None,
            "completed_at": None,
            "history_recorded": False,
        },
    )
    monkeypatch.setattr(tm, "record_task", lambda *a, **k: None)
    monkeypatch.setattr(app_state, "session_factory", Session)
    monkeypatch.setattr(fw, "FavoritesRepository", lambda session: session._repo)
    monkeypatch.setattr(fw, "favorite_counts_cached", fake_counts)
    monkeypatch.setattr(fw, "_spawn_gallery_updates_detect", lambda: None)
    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", fake_spawn)


@pytest.mark.asyncio
async def test_worker_records_failure_without_success_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _WorkerStore()
    _install_worker(monkeypatch, store)

    class Service:
        async def check_category(self, *args: Any, **kwargs: Any) -> FavoritesCheckResult:
            return FavoritesCheckResult(FAVCAT, found=1, new=1, downloaded=0, failed=1)

    await fw.run_favorites_check(FAVCAT, Service(), scheduled=False)

    assert store.checked == [(FAVCAT, False)], "a failed enqueue must not be checked(True)"
    assert FAVCAT not in store.times, "a failed enqueue must not refresh the deadline"
    assert app_state.task_manager.favorites_check_state["last_error"]


@pytest.mark.asyncio
async def test_worker_records_success_when_nothing_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _WorkerStore()
    _install_worker(monkeypatch, store)

    class Service:
        async def check_category(self, *args: Any, **kwargs: Any) -> FavoritesCheckResult:
            return FavoritesCheckResult(FAVCAT, found=1, new=1, downloaded=1, failed=0)

    await fw.run_favorites_check(FAVCAT, Service(), scheduled=False)

    assert store.checked == [(FAVCAT, True)]
    assert FAVCAT in store.times
