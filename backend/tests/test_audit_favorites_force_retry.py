"""R2 audit: a failed enqueue must not leave a permanent "seen" row.

Two gaps made a favourite whose download could not be enqueued unrecoverable:

* the gid was already recorded locally, so the ``failed_gids`` guard only
  prevented a *new* row — the old row kept it out of every later
  ``incremental`` candidate set forever;
* a ``force`` folder whose local row count matched the live count was skipped
  by the scheduled heuristic, which did not look at the folder mode at all.

These tests pin the fixes: forget the recorded row of a failed gid, never skip
a force folder, and treat "already has an active task" as benign.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Self

import pytest

from galleryvault.app.state import app_state
from galleryvault.services import favorites_worker as fw
from galleryvault.services.eh_client import FavoriteItems
from galleryvault.services.favorites import FavoritesCheckResult, FavoritesService
from galleryvault.services.favorites_worker import favorites_skip_decision

FAVCAT = 3


def _item(gid: int) -> SimpleNamespace:
    return SimpleNamespace(gid=gid, token=f"tok{gid}", title=f"G{gid}", url=f"/g/{gid}/")


class _Repo:
    def __init__(self, known: set[int] | None = None) -> None:
        self.known = set(known or ())
        self.remembered: list[int] = []
        self.forgotten: list[set[int]] = []

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
        stale = self.known - set(current_gids)
        self.known -= stale
        return len(stale)

    async def forget(self, favcat: int, gids: list[int]) -> int:
        self.forgotten.append(set(gids))
        removed = self.known & set(gids)
        self.known -= removed
        return len(removed)

    async def checked(self, favcat: int, success: bool) -> None:
        pass


class _Fetcher:
    def __init__(self, items: list[SimpleNamespace]) -> None:
        self.items = items

    async def fetch_favorites(self, favcat: int, progress: Any = None) -> FavoriteItems:
        return FavoriteItems(self.items)


class _Queue:
    """Fails for ``fail_gids`` (exception) and reports ``false_gids`` as False."""

    def __init__(
        self, fail_gids: set[int] | None = None, false_gids: set[int] | None = None
    ) -> None:
        self.fail_gids = set(fail_gids or ())
        self.false_gids = set(false_gids or ())
        self.calls: list[int] = []

    async def enqueue(self, item: Any, mode: Any = None, quality: Any = None) -> bool:
        self.calls.append(item.gid)
        if item.gid in self.fail_gids:
            raise RuntimeError("enqueue exploded")
        return item.gid not in self.false_gids


def _service(repo: _Repo, queue: _Queue, gids: list[int]) -> FavoritesService:
    return FavoritesService(
        fetcher=_Fetcher([_item(gid) for gid in gids]), repository=repo, queue=queue
    )


# ---------------------------------------------------------------------------
# Service: known gid + failed enqueue is forgotten and retried incrementally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_enqueue_forgets_known_row_and_incremental_retries() -> None:
    repo = _Repo(known={1})
    queue = _Queue(fail_gids={1})
    service = _service(repo, queue, [1])

    first = await service.check_category(0, mode="force")

    assert first.failed == 1 and first.downloaded == 0
    assert repo.forgotten == [{1}], "the failed gid's 'seen' row must be dropped"
    assert repo.known == set(), "a failed gid must not stay recorded as seen"

    queue.fail_gids.clear()
    second = await service.check_category(0, mode="incremental")

    assert queue.calls == [1, 1], "incremental must offer the forgotten gid again"
    assert second.new == 1 and second.downloaded == 1 and second.failed == 0
    assert repo.known == {1}, "a successful retry records the gid again"
    assert repo.forgotten == [{1}], "a success must not forget anything else"


@pytest.mark.asyncio
async def test_failed_gid_never_known_is_not_forgotten() -> None:
    repo = _Repo()
    queue = _Queue(fail_gids={1})
    service = _service(repo, queue, [1])

    await service.check_category(0, mode="incremental")

    assert repo.forgotten == [], "only previously recorded rows need deleting"
    assert repo.known == set()


@pytest.mark.asyncio
async def test_monitor_only_does_not_forget_known_rows() -> None:
    repo = _Repo(known={1})
    queue = _Queue(fail_gids={1})
    service = _service(repo, queue, [1])

    result = await service.check_category(0, mode="monitor_only")

    assert result.failed == 0
    assert queue.calls == [], "monitor-only must never enqueue"
    assert repo.forgotten == []
    assert repo.known == {1}
    assert repo.remembered == [1]


@pytest.mark.asyncio
async def test_active_task_enqueue_false_is_benign() -> None:
    repo = _Repo(known={1})
    queue = _Queue(false_gids={1})
    service = _service(repo, queue, [1])

    result = await service.check_category(0, mode="force")

    assert result.failed == 0, "an already queued gid is not a failed enqueue"
    assert result.downloaded == 1
    assert repo.forgotten == []
    assert repo.known == {1}


@pytest.mark.asyncio
async def test_success_path_remembers_without_forget() -> None:
    repo = _Repo(known={1})
    queue = _Queue()
    service = _service(repo, queue, [1, 2])

    result = await service.check_category(0, mode="incremental")

    assert result.new == 1 and result.downloaded == 1 and result.failed == 0
    assert repo.remembered == [1, 2], "a successful pass records every seen item"
    assert repo.forgotten == []
    assert repo.known == {1, 2}


# ---------------------------------------------------------------------------
# Worker: force folders must never be skipped by the scheduled heuristic
# ---------------------------------------------------------------------------


def test_skip_decision_never_skips_force_folder() -> None:
    now = datetime(2026, 10, 29, tzinfo=UTC)

    assert (
        favorites_skip_decision(
            scheduled=True,
            category_ready=True,
            live_count=10,
            known=10,
            first_page_known=True,
            last_full_check=now - timedelta(days=1),
            mode="force",
            now=now,
        )
        is False
    )


class _WorkerStore:
    def __init__(self) -> None:
        self.times: dict[int, datetime] = {}
        self.checked: list[tuple[int, bool]] = []
        self.checks: list[tuple[int, dict[str, Any]]] = []
        self.probes: list[int | None] = []


def _install_worker(
    monkeypatch: pytest.MonkeyPatch,
    store: _WorkerStore,
    *,
    mode: str = "incremental",
    known: int = 10,
    live: int = 10,
) -> None:
    class Repo:
        async def category(self, favcat: int) -> SimpleNamespace:
            return SimpleNamespace(
                favcat=favcat,
                last_success_at=object(),
                enabled=True,
                mode=mode,
            )

        async def known_gids(self, favcat: int) -> set[int]:
            return set(range(known))

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

    class Client:
        async def fetch_favorites(
            self, favcat: int, progress: Any = None, *, max_pages: int | None = None
        ) -> list[Any]:
            store.probes.append(max_pages)
            return [SimpleNamespace(gid=gid) for gid in range(known)]

    def fake_spawn(coro: Any, operation: str) -> None:
        if hasattr(coro, "close"):
            coro.close()

    async def fake_counts(*args: Any, **kwargs: Any) -> dict[int, int]:
        return {FAVCAT: live}

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
    monkeypatch.setattr(app_state, "eh_client", Client())
    monkeypatch.setattr(fw, "FavoritesRepository", lambda session: session._repo)
    monkeypatch.setattr(fw, "favorite_counts_cached", fake_counts)
    monkeypatch.setattr(fw, "_spawn_gallery_updates_detect", lambda: None)
    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", fake_spawn)


@pytest.mark.asyncio
async def test_force_folder_with_all_known_runs_full_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _WorkerStore()
    store.times[FAVCAT] = datetime.now(UTC) - timedelta(days=1)
    _install_worker(monkeypatch, store, mode="force")
    service = _RecordingService(store)

    await fw.run_favorites_check(FAVCAT, service, scheduled=True)

    assert store.checks, "a force folder must not be skipped"
    assert store.checks[0][1]["mode"] == "force"
    assert store.probes == [], "no first-page probe is needed for a force folder"
    assert store.checked == [(FAVCAT, True)]


@pytest.mark.asyncio
async def test_incremental_folder_with_all_known_is_still_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _WorkerStore()
    store.times[FAVCAT] = datetime.now(UTC) - timedelta(days=1)
    _install_worker(monkeypatch, store, mode="incremental")
    service = _RecordingService(store)

    await fw.run_favorites_check(FAVCAT, service, scheduled=True)

    assert store.probes == [1]
    assert store.checks == [], "unchanged incremental folders keep their skip"


class _RecordingService:
    def __init__(self, store: _WorkerStore) -> None:
        self.store = store

    async def check_category(self, favcat: int, **kwargs: Any) -> FavoritesCheckResult:
        self.store.checks.append((favcat, dict(kwargs)))
        return FavoritesCheckResult(
            favcat, found=10, new=10, downloaded=10, failed=0
        )
