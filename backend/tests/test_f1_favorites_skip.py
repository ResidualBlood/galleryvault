"""F1: scheduled favorites skip must not hide version-replacement galleries.

A folder whose cloud count is unchanged can still contain a brand-new gid when
an old gallery was replaced by a re-upload under the same title.  These tests
cover the first-page probe, the persisted 15-day full-check deadline, the
skip-path update detection and the update matcher itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Self

import httpx
import pytest

from galleryvault.app.state import app_state
from galleryvault.db.repositories.favorites import FULL_CHECK_CONFIG_KEY, FavoritesRepository
from galleryvault.services import favorites_worker as fw
from galleryvault.services import updates_worker
from galleryvault.services.eh_client import EhClient
from galleryvault.services.favorites_worker import FAVORITES_FULL_CHECK_MAX_AGE_DAYS
from galleryvault.services.updates_worker import detect_gallery_updates

FAVCAT = 3


class _Store:
    """Stand-in for the ``app_config.favorites_full_check`` JSON row."""

    def __init__(self) -> None:
        self.times: dict[int, datetime] = {}
        self.checked: list[tuple[int, bool]] = []
        self.checks: list[int] = []
        self.spawned: list[str] = []
        self.probes: list[int | None] = []


def _install(monkeypatch: pytest.MonkeyPatch, store: _Store, *, known: int, live: int, probe: Any) -> None:
    class Repo:
        async def category(self, favcat: int) -> SimpleNamespace:
            return SimpleNamespace(
                favcat=favcat,
                last_success_at=object(),
                enabled=True,
                mode="incremental",
            )

        async def known_gids(self, favcat: int) -> set[int]:
            return set(range(known))

        async def full_check_times(self) -> dict[int, datetime]:
            return dict(store.times)

        async def set_full_check_time(self, favcat: int, when: datetime | None = None) -> None:
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
            if isinstance(probe, Exception):
                raise probe
            if probe is None:
                return []
            return [SimpleNamespace(gid=gid) for gid in probe]

    def fake_spawn(coro: Any, operation: str) -> None:
        store.spawned.append(operation)
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
    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", fake_spawn)


async def _run(
    monkeypatch: pytest.MonkeyPatch,
    store: _Store,
    *,
    known: int = 10,
    live: int = 10,
    probe: Any = range(10),
    scheduled: bool = True,
) -> _Store:
    class Service:
        async def check_category(self, favcat: int, **kwargs: Any) -> None:
            store.checks.append(favcat)

    _install(monkeypatch, store, known=known, live=live, probe=probe)
    await fw.run_favorites_check(FAVCAT, Service(), scheduled=scheduled)
    return store


@pytest.mark.asyncio
async def test_same_count_with_unknown_first_page_gid_runs_full_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4285259 replaced 4269190: count is unchanged, but the probe sees a new gid."""
    store = _Store()
    store.times[FAVCAT] = datetime.now(UTC)
    await _run(monkeypatch, store, probe=[0, 1, 2, 3, 4285259])

    assert store.probes == [1], "the probe must request exactly one page"
    assert store.checks == [FAVCAT], "an unknown first-page gid must force a full check"
    assert store.checked == [(FAVCAT, True)]
    assert FAVCAT in store.times, "a successful full check refreshes the deadline"
    assert "gallery updates detect" in store.spawned


@pytest.mark.asyncio
async def test_same_count_all_known_and_fresh_skips_and_runs_update_detect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    timestamp = datetime.now(UTC) - timedelta(days=1)
    store.times[FAVCAT] = timestamp

    await _run(monkeypatch, store, probe=range(10))

    assert store.probes == [1]
    assert store.checks == [], "unchanged + known first page + fresh deadline must skip"
    assert store.times[FAVCAT] == timestamp, "skipping must not refresh the deadline"
    assert store.checked == [(FAVCAT, True)]
    assert "gallery updates detect" in store.spawned


@pytest.mark.asyncio
async def test_expired_or_missing_timestamp_forces_full_check_without_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    for label, times in (
        ("missing", {}),
        ("expired", {FAVCAT: now - timedelta(days=FAVORITES_FULL_CHECK_MAX_AGE_DAYS + 1)}),
        ("exactly_at_limit", {FAVCAT: now - timedelta(days=FAVORITES_FULL_CHECK_MAX_AGE_DAYS)}),
    ):
        store = _Store()
        store.times.update(times)
        await _run(monkeypatch, store, probe=range(10))
        assert store.checks == [FAVCAT], label
        assert store.probes == [], f"{label}: no probe is needed when a full check is due"


@pytest.mark.asyncio
async def test_probe_failure_falls_back_to_full_check(monkeypatch: pytest.MonkeyPatch) -> None:
    for probe in (RuntimeError("network down"), [], None):
        store = _Store()
        store.times[FAVCAT] = datetime.now(UTC)
        if probe is None:
            await _run(monkeypatch, store, probe=None)
        else:
            await _run(monkeypatch, store, probe=probe)
        assert store.checks == [FAVCAT]
        assert store.probes == [1]


@pytest.mark.asyncio
async def test_manual_check_is_never_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store()
    store.times[FAVCAT] = datetime.now(UTC)
    await _run(monkeypatch, store, probe=range(10), scheduled=False)

    assert store.checks == [FAVCAT]
    assert store.probes == []


@pytest.mark.asyncio
async def test_timestamp_persists_in_app_config_and_survives_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AppConfigSession:
        def __init__(self) -> None:
            self.rows: dict[str, Any] = {}

        async def get(self, model: Any, key: str) -> Any:
            return self.rows.get(key)

        def add(self, obj: Any) -> None:
            self.rows[obj.key] = obj

        async def flush(self) -> None:
            pass

    stored = AppConfigSession()
    stamp = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)
    await FavoritesRepository(stored).set_full_check_time(7, stamp)  # type: ignore[arg-type]

    assert FULL_CHECK_CONFIG_KEY in stored.rows
    assert stored.rows[FULL_CHECK_CONFIG_KEY].value == {"7": stamp.isoformat()}

    # A new repository instance only sees the persisted row (process restart).
    reloaded = await FavoritesRepository(stored).full_check_times()  # type: ignore[arg-type]
    assert reloaded == {7: stamp}
    stored.rows[FULL_CHECK_CONFIG_KEY].value["broken"] = "not-a-date"
    assert await FavoritesRepository(stored).full_check_times() == {7: stamp}  # type: ignore[arg-type]

    # Behaviourally: the timestamp written by a full run makes the next
    # scheduled run skip even after the in-memory caches/task state reset.
    store = _Store()
    await _run(monkeypatch, store, probe=range(10))
    assert store.checks == [FAVCAT]
    persisted = dict(store.times)

    fw._fav_counts_cache.clear()
    store2 = _Store()
    store2.times.update(persisted)
    await _run(monkeypatch, store2, probe=range(10))
    assert store2.checks == []
    assert store2.probes == [1]


# --------------------------------------------------------------------------
# Update detection matches old/new gids sharing a title
# --------------------------------------------------------------------------


class _Res:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def __iter__(self) -> Any:
        return iter(self._rows)

    def all(self) -> list[Any]:
        return self._rows


@pytest.mark.asyncio
async def test_new_version_gid_is_matched_as_gallery_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fav_rows = [(4285259, "newtok", "Same Gallery Title", 0)]
    gallery_rows = [(1, 4269190, "Same Gallery Title", None)]
    detected: list[dict[str, Any]] = []

    class Session:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        def begin(self) -> Session:
            return self

        async def execute(self, stmt: Any) -> _Res:
            if "favorite_items" in str(stmt):
                return _Res(fav_rows)
            return _Res(gallery_rows)

    class FakeRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def tracking_by_gallery_id(self) -> dict[int, Any]:
            return {}

        async def local_new_gids(self, gids: list[int]) -> set[int]:
            return set()

        async def active_task_ids_for_gids(self, gids: list[int]) -> dict[int, int]:
            return {}

        async def detect_many(self, entries: list[dict[str, Any]], *, known_gallery_ids: set[int]) -> int:
            detected.extend(entries)
            return len(entries)

    monkeypatch.setattr(app_state, "session_factory", Session)
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", FakeRepo)
    app_state.task_manager.gallery_updates_state.update({"detecting": False})

    await detect_gallery_updates()

    assert len(detected) == 1
    entry = detected[0]
    assert entry["old_gid"] == 4269190
    assert entry["new_gid"] == 4285259
    assert entry["new_token"] == "newtok"
    assert entry["favcat"] == 0


# --------------------------------------------------------------------------
# Single-page probe reuses EhClient's parser without walking the cursor
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_favorites_max_pages_requests_only_first_page() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.params.get("next"):
            return httpx.Response(200, text='<a href="/g/2000/bbbbbb/">Second</a>')
        return httpx.Response(
            200,
            text=(
                '<a href="/g/1000/aaaaaa/">First</a>'
                '<script>var nexturl="https://exhentai.test/favorites.php?'
                'favcat=0&amp;next=1000-1770000000";</script>'
            ),
        )

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        items = await client.fetch_favorites(0, max_pages=1)

    assert [item.gid for item in items] == [1000]
    assert len(requests) == 1
