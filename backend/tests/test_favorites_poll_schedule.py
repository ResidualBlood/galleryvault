"""Batch 26: per-folder favorites polling schedule.

The scheduler must use each folder's own ``poll_interval_seconds`` and re-read
the rows on every fixed tick instead of sleeping on the legacy global interval.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Self

import pytest

from galleryvault.services import favorites_worker as fw

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
FAVCAT_A = 90
FAVCAT_B = 91


class _Repo:
    def __init__(self, folders: list[SimpleNamespace]) -> None:
        self._folders = folders

    async def categories(self) -> list[SimpleNamespace]:
        return list(self._folders)


class _Session:
    def __init__(self, repo: _Repo) -> None:
        self._repo = repo

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _folder(favcat: int, interval: int | None, last_checked: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(
        favcat=favcat,
        enabled=True,
        mode="incremental",
        poll_interval_seconds=interval,
        last_checked_at=last_checked,
    )


async def _tick(
    monkeypatch: pytest.MonkeyPatch,
    folders: list[SimpleNamespace],
    calls: list[tuple[int, bool]],
) -> None:
    repo = _Repo(folders)

    async def fake_check(favcat: int, service: Any, *, scheduled: bool = False) -> None:
        calls.append((favcat, scheduled))
        for item in folders:
            if item.favcat == favcat:
                item.last_checked_at = NOW

    monkeypatch.setattr(fw, "run_favorites_check", fake_check)
    monkeypatch.setattr(fw, "FavoritesRepository", lambda session: repo)
    await fw._run_favorites_poll_tick(
        SimpleNamespace(favorites_poll_interval_minutes=720),
        object(),
        lambda: _Session(repo),
        now=NOW,
    )


def test_tick_is_fixed_at_sixty_seconds() -> None:
    assert fw.FAVORITES_POLL_TICK_SECONDS == 60


async def test_due_folder_runs_while_long_interval_folder_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = [
        _folder(FAVCAT_A, 15 * 60, NOW - timedelta(minutes=20)),
        _folder(FAVCAT_B, 720 * 60, NOW - timedelta(minutes=20)),
    ]
    calls: list[tuple[int, bool]] = []

    await _tick(monkeypatch, folders, calls)

    assert calls == [(FAVCAT_A, True)]


async def test_interval_change_takes_effect_on_next_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder_a = _folder(FAVCAT_A, 15 * 60, NOW - timedelta(minutes=20))
    folder_b = _folder(FAVCAT_B, 720 * 60, NOW - timedelta(minutes=20))
    folders = [folder_a, folder_b]
    calls: list[tuple[int, bool]] = []

    await _tick(monkeypatch, folders, calls)
    assert calls == [(FAVCAT_A, True)]

    # Same row, edited through the settings API between two ticks: the first
    # tick skipped it, the next tick must pick up the new interval.
    folder_b.poll_interval_seconds = 10 * 60
    await _tick(monkeypatch, folders, calls)

    assert calls == [(FAVCAT_A, True), (FAVCAT_B, True)]


async def test_one_minute_interval_is_clamped_to_ten_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _folder(FAVCAT_A, 60, NOW - timedelta(minutes=9))
    folders = [folder]
    calls: list[tuple[int, bool]] = []

    assert fw._favorites_effective_interval_seconds(folder, 720 * 60) == 600

    await _tick(monkeypatch, folders, calls)
    assert calls == []

    # A failed/previous check only recorded last_checked_at; ten minutes later
    # the clamped interval is due and the folder runs again.
    folder.last_checked_at = NOW - timedelta(minutes=10)
    await _tick(monkeypatch, folders, calls)
    assert calls == [(FAVCAT_A, True)]


async def test_missing_last_checked_is_due(monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(FAVCAT_A, 720 * 60, None)
    calls: list[tuple[int, bool]] = []

    await _tick(monkeypatch, [folder], calls)

    assert calls == [(FAVCAT_A, True)]
