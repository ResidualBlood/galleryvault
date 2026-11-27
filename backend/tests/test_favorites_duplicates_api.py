"""T5.3: every duplicate read/write path goes through ``duplicate_groups``.

RED targets from PLAN-backend-hardening Batch 5:

* ``POST /api/library/duplicates/cross-gid/{id}/dismiss|restore`` and
  ``GET .../cross-gid?status=dismissed`` exist and map to ``kind='cross_gid'``
  rows (baseline: no such routes, 404);
* a favorites ignore no longer hides a cross-GID group (the three kinds are
  independent, Q10-b);
* a dismissed same-gid group survives the group disappearing from a scan
  (``present=false`` rows stay readable);
* the favorites status/ignored endpoints read the ``kind='favorites'`` rows
  instead of ``favorite_duplicate_ignores`` / ``tm.duplicates_state``.

The fakes below stand in for the DB layer only: they keep ``DuplicateGroup``
objects in a list and honour the repository methods the routers call.  The
reconciliation rules themselves are covered by ``test_duplicate_groups_repo.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from galleryvault.app.dependencies import get_session
from galleryvault.app.routers import duplicates as duplicates_router
from galleryvault.app.routers import favorites as favorites_router
from galleryvault.db.models import DuplicateGroup
from galleryvault.db.repositories import galleries_query
from galleryvault.services import duplicate_groups as group_service

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class _Store:
    """In-memory replacement for the ``duplicate_groups`` table."""

    def __init__(self, rows: list[DuplicateGroup] | None = None) -> None:
        self.rows = list(rows or [])
        self._next = max([row.id for row in self.rows if row.id is not None] or [0]) + 1

    def add(self, row: DuplicateGroup) -> None:
        if getattr(row, "id", None) is None:
            row.id = self._next
            self._next += 1
        self.rows.append(row)

    def remove(self, row: DuplicateGroup) -> None:
        self.rows.remove(row)


class _Begin:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeSession:
    def __init__(self, store: _Store) -> None:
        self.store = store

    def in_transaction(self) -> bool:
        return False

    def begin(self) -> _Begin:
        return _Begin(self)

    def add(self, row: DuplicateGroup) -> None:
        self.store.add(row)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def scalars(self, stmt: object) -> object:
        class _Rows(list):
            def all(self):
                return list(self)

        return _Rows()

    async def get(self, model: object, ident: int) -> DuplicateGroup | None:
        return next((row for row in self.store.rows if row.id == ident), None)

    async def delete(self, row: DuplicateGroup) -> None:
        self.store.remove(row)


class _FakeDuplicateRepo:
    """Repository stand-in over :class:`_Store` (same method surface as the real one)."""

    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def list(
        self,
        kind: str | None = None,
        status: str | None = None,
        present: bool | None = None,
    ) -> list[DuplicateGroup]:
        rows = list(self.session.store.rows)
        if kind is not None:
            rows = [row for row in rows if row.kind == kind]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if present is not None:
            rows = [row for row in rows if row.present is present]
        return rows

    async def get(self, group_id: int) -> DuplicateGroup | None:
        return next((row for row in self.session.store.rows if row.id == group_id), None)

    async def set_status(self, group_id: int, status: str) -> DuplicateGroup | None:
        row = await self.get(group_id)
        if row is None:
            return None
        row.status = status
        row.dismissed_at = NOW if status == "dismissed" else None
        return row

    async def delete(self, group_id: int) -> bool:
        row = await self.get(group_id)
        if row is None:
            return False
        self.session.store.remove(row)
        return True


def _row(
    *,
    group_id: int,
    kind: str,
    key: str,
    status: str = "open",
    present: bool = True,
    items: list[dict] | None = None,
    copies: list[dict] | None = None,
    member_gids: list[int] | None = None,
    title: str | None = None,
    artist: str | None = None,
    last_seen: datetime | None = None,
) -> DuplicateGroup:
    payload: dict = {}
    if items is not None:
        payload["items"] = items
    if copies is not None:
        payload = {"policy": "keep_first", "winner_path": copies[0]["path"], "copies": copies}
    return DuplicateGroup(
        id=group_id,
        kind=kind,
        group_key=key,
        status=status,
        member_gids=list(member_gids or []),
        legacy_keys=[],
        title=title,
        artist=artist,
        payload=payload,
        present=present,
        last_seen_at=last_seen if last_seen is not None else (NOW if present else None),
        dismissed_at=NOW if status == "dismissed" else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(monkeypatch, store: _Store) -> TestClient:
    session = _FakeSession(store)
    monkeypatch.setattr(group_service, "DuplicateGroupRepository", _FakeDuplicateRepo)
    monkeypatch.setattr(galleries_query, "DuplicateGroupRepository", _FakeDuplicateRepo)

    async def fake_session():
        yield session

    mini = FastAPI()
    mini.include_router(duplicates_router.router)
    mini.include_router(favorites_router.router)
    mini.dependency_overrides[get_session] = fake_session
    return TestClient(mini)


def _cross_gid_group(key: str = "alice|work") -> list[dict]:
    return [
        {
            "gallery_id": 101,
            "gid": 111,
            "title": "Work Title",
            "title_jpn": "作品タイトル",
            "storage_path": "/path/to/111-Work",
            "storage_type": "folder",
            "url": None,
            "favorited": False,
            "legacy_keys": ["alice|work_old"],
        },
        {
            "gallery_id": None,
            "gid": 222,
            "title": "Work Title [DL版]",
            "title_jpn": None,
            "storage_path": None,
            "storage_type": None,
            "url": "https://exhentai.org/g/222/token",
            "favorited": True,
            "legacy_keys": ["alice|work_old"],
        },
    ]


# ---------------------------------------------------------------- cross-gid


def test_cross_gid_dismiss_restore_roundtrip(monkeypatch):
    store = _Store([_row(group_id=7, kind="cross_gid", key="alice|work", items=_cross_gid_group())])

    with _client(monkeypatch, store) as client:
        res = client.get("/api/library/duplicates/cross-gid")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["ready"] is True
        assert body["count"] == 1
        group = body["groups"][0]
        assert group["id"] == 7
        assert group["key"] == "alice|work"
        assert len(group["items"]) == 2
        assert "legacy_keys" not in group
        assert group["items"][0]["display_title"]

        res = client.post("/api/library/duplicates/cross-gid/7/dismiss")
        assert res.status_code == 200, res.text
        assert res.json() == {"status": "dismissed"}
        assert store.rows[0].status == "dismissed"

        res = client.get("/api/library/duplicates/cross-gid")
        assert res.status_code == 200, res.text
        assert res.json()["count"] == 0

        res = client.get("/api/library/duplicates/cross-gid?status=dismissed")
        assert res.status_code == 200, res.text
        dismissed = res.json()
        assert dismissed["ready"] is True
        assert [g["id"] for g in dismissed["groups"]] == [7]

        res = client.post("/api/library/duplicates/cross-gid/7/restore")
        assert res.status_code == 200, res.text
        assert res.json() == {"status": "open"}
        assert client.get("/api/library/duplicates/cross-gid").json()["count"] == 1

        res = client.post("/api/library/duplicates/cross-gid/999/dismiss")
        assert res.status_code == 404, res.text


def test_cross_gid_dismissed_group_survives_disappearing(monkeypatch):
    """A dismissed group whose latest scan no longer contains it stays restorable."""
    store = _Store(
        [
            _row(
                group_id=8,
                kind="cross_gid",
                key="bob|gone",
                status="dismissed",
                present=False,
                items=_cross_gid_group("bob|gone"),
                last_seen=NOW,
            )
        ]
    )

    with _client(monkeypatch, store) as client:
        res = client.get("/api/library/duplicates/cross-gid?status=dismissed")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["ready"] is True
        assert [g["key"] for g in body["groups"]] == ["bob|gone"]

        assert client.get("/api/library/duplicates/cross-gid").json()["count"] == 0


def test_cross_gid_not_scanned_is_not_ready(monkeypatch):
    with _client(monkeypatch, _Store()) as client:
        res = client.get("/api/library/duplicates/cross-gid")
        assert res.status_code == 200, res.text
        assert res.json() == {"ready": False, "count": 0, "groups": []}


def test_cross_gid_rejects_unknown_status(monkeypatch):
    with _client(monkeypatch, _Store()) as client:
        res = client.get("/api/library/duplicates/cross-gid?status=resolved")
        assert res.status_code == 422, res.text


def test_cross_gid_refresh_returns_current_table_view(monkeypatch):
    store = _Store([_row(group_id=9, kind="cross_gid", key="carol|title", items=_cross_gid_group())])
    monkeypatch.setattr(
        "galleryvault.services.duplicates.scan_library_cross_gid_groups",
        lambda *args, **kwargs: [],
    )

    with _client(monkeypatch, store) as client:
        res = client.post("/api/library/duplicates/cross-gid/refresh")
        assert res.status_code == 202, res.text
        assert res.json()["ready"] is True
        assert res.json()["count"] == 1


# --------------------------------------------------------------- favorites


def test_favorites_ignore_does_not_hide_cross_gid(monkeypatch):
    store = _Store(
        [
            _row(group_id=3, kind="cross_gid", key="alice|work", items=_cross_gid_group()),
            _row(group_id=4, kind="favorites", key="bob|title", items=_cross_gid_group("bob|title")),
        ]
    )

    class _FavRepo:
        def __init__(self, session):
            pass

        async def favorite_items_detail_by_gids(self, gids):
            return {gid: {"gid": gid, "title": f"gid {gid}", "token": None} for gid in gids}

    monkeypatch.setattr(favorites_router, "FavoritesRepository", _FavRepo)

    with _client(monkeypatch, store) as client:
        res = client.post(
            "/api/favorites/duplicates/ignore",
            json={"key": "bob|title", "title": "Bob Title", "gids": [222]},
        )
        assert res.status_code == 200, res.text
        assert res.json() == {"ok": True, "key": "bob|title"}

        # Favorites dismissal is its own kind: the cross-GID page is untouched.
        res = client.get("/api/library/duplicates/cross-gid")
        assert res.status_code == 200, res.text
        assert [g["key"] for g in res.json()["groups"]] == ["alice|work"]

        # ... and the favorites page hides it, with the ignored list showing it.
        res = client.get("/api/favorites/duplicates/status")
        assert res.status_code == 200, res.text
        assert res.json()["groups"] == []

        res = client.get("/api/favorites/duplicates/ignored")
        assert res.status_code == 200, res.text
        ignored = res.json()
        assert [entry["key"] for entry in ignored] == ["bob|title"]
        assert ignored[0]["gids"] == [222]
        assert ignored[0]["title"] == "Bob Title"

        res = client.delete("/api/favorites/duplicates/ignore?key=bob|title")
        assert res.status_code == 200, res.text
        assert res.json() == {"ok": True, "key": "bob|title"}

        res = client.get("/api/favorites/duplicates/status")
        assert [g["key"] for g in res.json()["groups"]] == ["bob|title"]


def test_favorites_status_reads_groups_from_table(monkeypatch):
    group_items = _cross_gid_group("dave|book")
    store = _Store(
        [
            _row(
                group_id=11,
                kind="favorites",
                key="dave|book",
                items=group_items,
                title="Dave Book",
                artist="dave",
            )
        ]
    )

    with _client(monkeypatch, store) as client:
        res = client.get("/api/favorites/duplicates/status")
        assert res.status_code == 200, res.text
        body = res.json()
        assert set(body) >= {
            "running",
            "stage",
            "done",
            "total",
            "last_error",
            "groups",
            "group_count",
            "item_count",
            "ignored",
        }
        assert body["group_count"] == 1
        assert body["item_count"] == 2
        assert body["groups"][0]["key"] == "dave|book"
        assert body["groups"][0]["artist"] == "dave"
        assert len(body["groups"][0]["items"]) == 2


def test_favorites_ignore_creates_dismissed_row(monkeypatch):
    store = _Store()

    with _client(monkeypatch, store) as client:
        res = client.post(
            "/api/favorites/duplicates/ignore",
            json={"key": "erin|new", "title": "Erin", "gids": [9, 3]},
        )
        assert res.status_code == 200, res.text

    assert len(store.rows) == 1
    row = store.rows[0]
    assert row.kind == "favorites"
    assert row.group_key == "erin|new"
    assert row.status == "dismissed"
    assert row.member_gids == [3, 9]
    assert row.title == "Erin"
    assert row.present is False


def test_favorites_ignore_requires_key(monkeypatch):
    with _client(monkeypatch, _Store()) as client:
        res = client.post("/api/favorites/duplicates/ignore", json={"key": "  "})
        assert res.status_code == 422, res.text


# ----------------------------------------------------------------- same-gid


def test_same_gid_dismiss_survives_group_disappearance(monkeypatch):
    copies = [
        {"path": "/lib/12345-a", "key": "k1", "gallery_id": 1},
        {"path": "/lib/12345-b", "key": "k2", "gallery_id": None},
    ]
    store = _Store(
        [
            _row(
                group_id=21,
                kind="same_gid",
                key="12345",
                status="dismissed",
                present=False,
                copies=copies,
                member_gids=[12345],
            )
        ]
    )

    with _client(monkeypatch, store) as client:
        res = client.get("/api/scan/duplicates")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["count"] == 1
        group = body["groups"][0]
        assert group["gid"] == 12345
        assert group["status"] == "dismissed"
        assert [copy["path"] for copy in group["copies"]] == ["/lib/12345-a", "/lib/12345-b"]
        assert group["policy"] == "keep_first"
        assert group["winner_path"] == "/lib/12345-a"


def test_favorites_repository_has_no_legacy_ignore_methods():
    from galleryvault.db.repositories.favorites import FavoritesRepository

    for name in (
        "ignored_duplicate_keys",
        "ignored_duplicates",
        "add_duplicate_ignore",
        "remove_duplicate_ignore",
    ):
        assert not hasattr(FavoritesRepository, name), f"{name} must be gone (T5.3)"


def test_app_state_has_no_cross_gid_snapshot():
    from galleryvault.app.state import AppState

    assert not hasattr(AppState(), "cross_gid_duplicates")


@pytest.mark.asyncio
async def test_set_status_by_key_reopens_without_touching_other_kinds(monkeypatch):
    monkeypatch.setattr(group_service, "DuplicateGroupRepository", _FakeDuplicateRepo)
    store = _Store(
        [
            _row(group_id=31, kind="favorites", key="same|key", status="dismissed"),
            _row(group_id=32, kind="cross_gid", key="same|key", status="dismissed"),
        ]
    )
    session = _FakeSession(store)

    await group_service.set_status_by_key(session, "favorites", "same|key", "open")

    assert store.rows[0].status == "open"
    assert store.rows[1].status == "dismissed"
