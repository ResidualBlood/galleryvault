"""Regression tests for the favorites router/repository audit findings (T7).

1. ``POST /api/favorites/note`` without a token must fall back to the local
   gallery row (``GalleryRepository.get_by_gid``) and still call ExHentai
   instead of blowing up while reading the fallback.
2. ``POST /api/favorites/add`` supports a batch note only: an ``item.note``
   that differs from ``body.note`` is rejected with 422 before any cloud call,
   and the local cache stores the same ``body.note`` the cloud receives.
3. Cover cache writes must use a unique temp file per call so two concurrent
   cold-cache misses for one gid cannot race on a shared ``.tmp`` path.
4. ``FavoritesRepository.list_items`` must end every ORDER BY with the unique
   ``favorite_items.id`` key, otherwise ties (a batch shares one
   ``last_seen_at``) can repeat or skip rows across pages.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, Self

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from galleryvault.app.schemas import FavoriteNoteRequest, FavoritesAddRequest
from galleryvault.app.state import app_state
from galleryvault.db.models import Gallery
from galleryvault.db.repositories.favorites import FavoritesRepository


class _FakeSession:
    """Minimal async session: records statements, returns canned scalar values."""

    def __init__(self, scalars: list[Any] | None = None) -> None:
        self._scalars = list(scalars or [])
        self.sql: list[str] = []
        self.executed: list[Any] = []
        self.rolled_back = 0

    def _compile(self, statement: Any) -> str:
        text = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.sql.append(text)
        return text

    def begin(self) -> Self:
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def scalar(self, statement: Any) -> Any:
        self._compile(statement)
        return self._scalars.pop(0) if self._scalars else None

    async def execute(self, statement: Any) -> Any:
        self._compile(statement)
        self.executed.append(statement)
        return SimpleNamespace(rowcount=1)

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        self.rolled_back += 1


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


def _install_session(monkeypatch: pytest.MonkeyPatch, session: _FakeSession) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    async def fake_session() -> Any:
        yield session

    monkeypatch.setattr(fav_mod, "get_session", fake_session)


@pytest.fixture()
def _quiet_task_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    monkeypatch.setattr(fav_mod, "get_task_manager", _fake_task_manager)
    monkeypatch.setattr(fav_mod, "spawn_task", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# 1. note token fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_falls_back_to_gallery_row_for_missing_token(
    monkeypatch: pytest.MonkeyPatch,
    _quiet_task_manager: None,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    gallery = Gallery(id=1, gid=4242, token="gallery-token", title="t")
    # First scalar() serves FavoritesRepository.item_for_gid() -> no cached item,
    # second serves GalleryRepository.get_by_gid() -> the local gallery row.
    session = _FakeSession(scalars=[None, gallery])
    _install_session(monkeypatch, session)

    calls: list[tuple[int, str, int, str]] = []

    class FakeClient:
        async def add_favorite(
            self, gid: int, token: str, favcat: int, note: str = ""
        ) -> None:
            calls.append((gid, token, favcat, note))

    original_client = app_state.eh_client
    app_state.eh_client = FakeClient()
    try:
        result = await fav_mod.favorites_set_note(
            FavoriteNoteRequest(gid=4242, note="hello", favcat=3)
        )
    finally:
        app_state.eh_client = original_client

    assert result["cloud_ok"] is True
    assert result["note"] == "hello"
    assert calls == [(4242, "gallery-token", 3, "hello")]
    # The persisted note used the same value the cloud accepted.
    assert result["local_updated"] == 1


@pytest.mark.asyncio
async def test_note_without_token_anywhere_is_422(
    monkeypatch: pytest.MonkeyPatch,
    _quiet_task_manager: None,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    _install_session(monkeypatch, _FakeSession(scalars=[None, None]))

    with pytest.raises(HTTPException) as excinfo:
        await fav_mod.favorites_set_note(
            FavoriteNoteRequest(gid=4242, note="hello", favcat=3)
        )
    assert excinfo.value.status_code == 422


# ---------------------------------------------------------------------------
# 2. batch note only / local mirrors cloud
# ---------------------------------------------------------------------------


class _RecordingFavoritesRepo:
    instances: ClassVar[list[_RecordingFavoritesRepo]] = []
    remembered: ClassVar[list[Any]] = []
    moved: ClassVar[list[list[int]]] = []

    def __init__(self, session: Any) -> None:
        self.session = session
        _RecordingFavoritesRepo.instances.append(self)

    async def remember_many(self, favcat: int, items: list[Any]) -> None:
        _RecordingFavoritesRepo.remembered.extend(items)

    async def move_gids(self, gids: list[int], target_favcat: int) -> int:
        _RecordingFavoritesRepo.moved.append(list(gids))
        return len(gids)


def _patch_add_deps(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    _RecordingFavoritesRepo.instances = []
    _RecordingFavoritesRepo.remembered = []
    _RecordingFavoritesRepo.moved = []
    _install_session(monkeypatch, _FakeSession())
    monkeypatch.setattr(fav_mod, "FavoritesRepository", _RecordingFavoritesRepo)
    original_client = app_state.eh_client
    app_state.eh_client = client
    return original_client


@pytest.mark.asyncio
async def test_add_rejects_item_note_conflicting_with_batch_note(
    monkeypatch: pytest.MonkeyPatch,
    _quiet_task_manager: None,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    cloud_calls: list[Any] = []

    class FakeClient:
        async def add_favorites(
            self, pairs: Any, target_favcat: int, note: str = ""
        ) -> list[int]:
            cloud_calls.append((list(pairs), target_favcat, note))
            return []

    original_client = _patch_add_deps(monkeypatch, FakeClient())
    try:
        body = FavoritesAddRequest(
            target_favcat=3,
            note="batch-note",
            items=[{"gid": 7, "token": "tok7", "note": "item-note"}],
        )
        with pytest.raises(HTTPException) as excinfo:
            await fav_mod.favorites_add(body)
    finally:
        app_state.eh_client = original_client

    assert excinfo.value.status_code == 422
    assert "note" in str(excinfo.value.detail)
    # Neither the cloud nor the local cache may be touched on a rejected body.
    assert cloud_calls == []
    assert _RecordingFavoritesRepo.remembered == []


@pytest.mark.asyncio
async def test_add_rejects_item_note_when_batch_note_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    _quiet_task_manager: None,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class FakeClient:
        async def add_favorites(
            self, pairs: Any, target_favcat: int, note: str = ""
        ) -> list[int]:
            raise AssertionError("cloud must not be called")

    original_client = _patch_add_deps(monkeypatch, FakeClient())
    try:
        body = FavoritesAddRequest(
            target_favcat=3,
            items=[{"gid": 7, "token": "tok7", "note": "item-note"}],
        )
        with pytest.raises(HTTPException) as excinfo:
            await fav_mod.favorites_add(body)
    finally:
        app_state.eh_client = original_client

    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_add_uses_batch_note_for_cloud_and_local_cache(
    monkeypatch: pytest.MonkeyPatch,
    _quiet_task_manager: None,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    cloud_calls: list[Any] = []

    class FakeClient:
        async def add_favorites(
            self, pairs: Any, target_favcat: int, note: str = ""
        ) -> list[int]:
            cloud_calls.append((list(pairs), target_favcat, note))
            return []

    original_client = _patch_add_deps(monkeypatch, FakeClient())
    try:
        body = FavoritesAddRequest(
            target_favcat=3,
            note="batch-note",
            items=[
                {"gid": 7, "token": "tok7"},  # no item note
                {"gid": 8, "token": "tok8", "note": ""},  # empty item note
                {"gid": 9, "token": "tok9", "note": "batch-note"},  # same note
            ],
        )
        result = await fav_mod.favorites_add(body)
    finally:
        app_state.eh_client = original_client

    assert result["cloud_ok"] is True
    assert result["successful_gids"] == [7, 8, 9]
    assert [call[2] for call in cloud_calls] == ["batch-note"]
    assert [item.note for item in _RecordingFavoritesRepo.remembered] == [
        "batch-note",
        "batch-note",
        "batch-note",
    ]


@pytest.mark.asyncio
async def test_add_without_any_note_stores_none_locally(
    monkeypatch: pytest.MonkeyPatch,
    _quiet_task_manager: None,
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class FakeClient:
        async def add_favorites(
            self, pairs: Any, target_favcat: int, note: str = ""
        ) -> list[int]:
            assert note == ""
            return []

    original_client = _patch_add_deps(monkeypatch, FakeClient())
    try:
        result = await fav_mod.favorites_add(
            FavoritesAddRequest(
                target_favcat=1, items=[{"gid": 11, "token": "tok11", "note": ""}]
            )
        )
    finally:
        app_state.eh_client = original_client

    assert result["successful_gids"] == [11]
    assert [item.note for item in _RecordingFavoritesRepo.remembered] == [None]


# ---------------------------------------------------------------------------
# 3. cover temp file uniqueness
# ---------------------------------------------------------------------------


def test_cover_write_uses_unique_temp_file_per_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    real_mkstemp = fav_mod.tempfile.mkstemp
    used_names: list[str] = []
    barrier = threading.Barrier(2, timeout=10)

    def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)
        used_names.append(name)
        # Both writers must be inside the write at the same time; with a shared
        # fixed ".tmp" name they would clobber each other here.
        barrier.wait()
        return fd, name

    monkeypatch.setattr(fav_mod.tempfile, "mkstemp", recording_mkstemp)

    target = tmp_path / "remote-covers" / "42.img"
    errors: list[BaseException] = []

    def writer(payload: bytes) -> None:
        try:
            fav_mod._write_cover_atomic(target, payload)
        except BaseException as exc:  # noqa: BLE001 - surfaced in the assertion
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(b"first-image",)),
        threading.Thread(target=writer, args=(b"second-image",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert len(used_names) == 2
    assert len(set(used_names)) == 2
    assert all(not Path(name).exists() for name in used_names)
    assert target.read_bytes() in {b"first-image", b"second-image"}
    assert list(target.parent.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# 4. list_items ORDER BY tiebreaker
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _ListSession(_FakeSession):
    async def execute(self, statement: Any) -> Any:
        self._compile(statement)
        return _Rows([])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_by",
    [
        "last_seen_desc",
        "first_seen_desc",
        "first_seen_asc",
        "title_asc",
        "title_desc",
        "posted_at_desc",
        "file_size_desc",
        "rating_desc",
        "page_count_desc",
        "not-a-known-order",
    ],
)
async def test_list_items_order_by_ends_with_favorite_item_id(order_by: str) -> None:
    session = _ListSession(scalars=[0])
    await FavoritesRepository(session).list_items(
        favcat=2, page=2, page_size=10, order_by=order_by
    )

    sql = session.sql[-1]
    order_clause = sql.split("ORDER BY", 1)[1].split(" LIMIT", 1)[0]
    last_key = order_clause.strip().split(",")[-1].strip().lower()
    assert last_key.startswith("favorite_items.id"), sql
