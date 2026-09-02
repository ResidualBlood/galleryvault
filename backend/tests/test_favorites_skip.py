"""Regression tests for the favorites skip heuristic missing equal-count swaps.

A user can replace a favorite without changing the folder's cloud count
(remove one gallery, add another).  The old skip heuristic short-circuited the
full re-list whenever ``known == live_count``, so an equal-count replacement
was never detected.  Consecutive skips are now counted per folder; the poll
that would be the 5th consecutive skip forces a full pass and resets the
counter.
"""

from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.services import favorites_worker
from galleryvault.services.favorites_worker import (
    FAVORITES_SKIP_LIMIT,
    favorites_skip_decision,
    run_favorites_check,
)


def test_skip_decision_skips_until_limit_then_forces_full() -> None:
    """4 consecutive unchanged polls skip; the 5th forces a full pass."""
    counter = 0
    for _ in range(FAVORITES_SKIP_LIMIT - 1):
        should_skip, counter = favorites_skip_decision(
            counter, scheduled=True, category_ready=True, live_count=10, known=10
        )
        assert should_skip is True
    # The poll that would be the 5th consecutive skip runs a full pass instead.
    should_skip, counter = favorites_skip_decision(
        counter, scheduled=True, category_ready=True, live_count=10, known=10
    )
    assert should_skip is False and counter == 0


def test_skip_decision_manual_check_never_skips() -> None:
    should_skip, next_count = favorites_skip_decision(
        3, scheduled=False, category_ready=True, live_count=10, known=10
    )
    assert should_skip is False and next_count == 0


def test_skip_decision_not_ready_never_skips() -> None:
    should_skip, next_count = favorites_skip_decision(
        0, scheduled=True, category_ready=False, live_count=10, known=10
    )
    assert should_skip is False and next_count == 0


def test_skip_decision_count_mismatch_never_skips() -> None:
    # A different count is the whole reason the skip exists; any mismatch
    # (including the equal-swap case where a previous forced full pass
    # re-listed) must run the full pass.
    should_skip, next_count = favorites_skip_decision(
        4, scheduled=True, category_ready=True, live_count=11, known=10
    )
    assert should_skip is False and next_count == 0


def test_skip_decision_zero_live_count_never_skips() -> None:
    should_skip, next_count = favorites_skip_decision(
        2, scheduled=True, category_ready=True, live_count=0, known=0
    )
    assert should_skip is False and next_count == 0


async def test_run_favorites_check_forces_full_pass_after_five_skips() -> None:
    """The integrated path: 4 skips then a full re-list on the 5th poll.

    The cloud count stays 10 the whole time (equal-count replacement); only the
    forced full pass on the 5th scheduled poll re-walks favorites.php.
    """
    monkeypatch = pytest.MonkeyPatch()
    tm = app_state.task_manager
    original_state = tm.favorites_check_state
    tm.favorites_check_state = {
        "running": False,
        "categories": {},
        "last_error": None,
        "started_at": None,
        "completed_at": None,
        "history_recorded": False,
        "skip_counts": {},
    }

    full_checks = []

    class Repo:
        async def category(self, favcat):
            return SimpleNamespace(
                favcat=favcat,
                last_success_at=object(),
                enabled=True,
                mode="incremental",
                poll_interval_seconds=3600,
                last_checked_at=None,
            )

        async def count_known_gids(self, favcat):
            return 10

        async def checked(self, favcat, success):
            pass

    class Service:
        async def check_category(
            self,
            favcat,
            mode="incremental",
            progress=None,
            archive_enabled=False,
            archive_max_pages=0,
            archive_quality="resample",
        ):
            full_checks.append(favcat)

    async def _fake_counts(*args, **kwargs):
        return {3: 10}

    orig_factory = app_state.session_factory
    try:
        # Reset per-test state and patch seams.
        app_state.session_factory = lambda: _FakeSession(Repo())
        app_state.favorites_service = Service()
        monkeypatch.setattr(favorites_worker, "FavoritesRepository", lambda session: session._repo)
        monkeypatch.setattr(favorites_worker, "favorite_size_sync", lambda favcat: None)
        monkeypatch.setattr(favorites_worker, "favorite_counts_cached", _fake_counts)
        monkeypatch.setattr(tm, "record_task", lambda *a, **k: None)

        for _ in range(5):
            await run_favorites_check(3, Service(), scheduled=True)
        assert full_checks == [3], "the 5th scheduled poll must run a full pass"
        assert tm.favorites_check_state["skip_counts"] == {"3": 0}
    finally:
        tm.favorites_check_state = original_state
        app_state.session_factory = orig_factory
        monkeypatch.undo()


class _FakeSession:
    def __init__(self, repo):
        self._repo = repo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def begin(self):
        return self

    async def scalar(self, statement):
        from sqlalchemy.dialects import postgresql

        sql = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        if "categories" in sql:
            return 10
        return None

    async def execute(self, statement):
        class _Result:
            def scalars(self):
                return self

            def first(self):
                return None

            def all(self):
                return []

        return _Result()

    async def flush(self):
        pass
