"""Batch 14: online reading progress/history for galleries not in the library.

The online reader keeps its page counter on the browser side, so these
endpoints only persist it keyed by ExHentai ``gid``. The contract under test is
the §3.3 one: ``GET`` 404 before the first save, ``PUT`` then ``GET`` consistent,
the same never-backwards page rule as the local reader, newest-first paginated
history, ``page < 1`` rejected with 422, and no page-image URL ever stored.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from galleryvault.app.dependencies import get_session
from galleryvault.app.routers import eh_progress
from galleryvault.app.routers.eh_progress import (
    OnlineProgressRequest,
    eh_online_history,
    eh_online_progress,
    save_eh_online_progress,
)
from galleryvault.db.models import OnlineReadingProgress
from galleryvault.db.repositories.online_progress import OnlineProgressRepository

GID = 4323821
TOKEN = "3e444314f7"
THUMB = "https://ehgt.org/t/43/00/4323821-1.jpg"
RESOLVED_IMAGE = (
    "https://hath.network/h/abc123-2560-1440-jpg/keystamp=1700000000-abcdef/page.jpg"
)


def _progress_url(gid: int = GID, token: str = TOKEN) -> str:
    return f"/api/eh/galleries/{gid}/{token}/progress"


class _AsyncSessionShim:
    """Async facade over a sync SQLite session (no aiosqlite in the suite)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_bind(self) -> Any:
        return self.session.get_bind()

    def in_transaction(self) -> bool:
        return bool(self.session.in_transaction())

    async def get(self, model: Any, pk: Any) -> Any:
        return self.session.get(model, pk)

    async def add(self, obj: Any) -> None:
        self.session.add(obj)

    async def execute(self, stmt: Any) -> Any:
        return self.session.execute(stmt)

    async def flush(self) -> None:
        self.session.flush()

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    OnlineReadingProgress.__table__.create(engine)
    session = Session(engine)
    shim = _AsyncSessionShim(session)
    app = FastAPI()
    app.include_router(eh_progress.router)
    app.dependency_overrides[get_session] = lambda: shim
    client = TestClient(app)
    try:
        yield client, session
    finally:
        session.close()
        engine.dispose()


def test_first_get_is_404(api: Any) -> None:
    client, _session = api

    response = client.get(_progress_url())

    assert response.status_code == 404


def test_put_then_get_round_trip(api: Any) -> None:
    client, session = api

    saved = client.put(
        _progress_url(),
        json={"page": 5, "total_pages": 20, "title": "Online Title", "thumb": THUMB},
    )
    assert saved.status_code == 200
    assert saved.json()["page"] == 5
    assert saved.json()["total_pages"] == 20
    assert saved.json()["updated_at"]

    fetched = client.get(_progress_url())
    assert fetched.status_code == 200
    assert fetched.json() == saved.json()

    row = session.get(OnlineReadingProgress, GID)
    assert row is not None
    assert (row.current_page, row.total_pages) == (5, 20)
    assert (row.token, row.title, row.thumb) == (TOKEN, "Online Title", THUMB)


def test_page_never_moves_backwards(api: Any) -> None:
    client, _session = api
    assert client.put(_progress_url(), json={"page": 10, "total_pages": 30}).status_code == 200
    advanced = client.get(_progress_url()).json()

    stale = client.put(_progress_url(), json={"page": 3})
    assert stale.status_code == 200
    assert stale.json()["page"] == 10

    after = client.get(_progress_url()).json()
    assert after["page"] == 10
    assert after["total_pages"] == 30
    # A stale write must not refresh the history timestamp either.
    assert after["updated_at"] == advanced["updated_at"]


def test_equal_page_refreshes_position_in_history(api: Any) -> None:
    client, _session = api
    other_gid = GID + 1
    client.put(_progress_url(), json={"page": 4})
    time.sleep(0.005)
    client.put(_progress_url(gid=other_gid, token="abcdef12"), json={"page": 4})

    first = client.get("/api/eh/history").json()
    assert [item["gid"] for item in first["items"]] == [other_gid, GID]

    # Re-opening the first gallery at the same page is a refresh, not a stale write.
    time.sleep(0.005)
    client.put(_progress_url(), json={"page": 4})
    refreshed = client.get("/api/eh/history").json()
    assert [item["gid"] for item in refreshed["items"]] == [GID, other_gid]


def test_history_newest_first_and_paginated(api: Any) -> None:
    client, session = api
    for index, gid in enumerate((GID, GID + 1, GID + 2), start=1):
        assert (
            client.put(
                _progress_url(gid=gid, token="abcdef12"),
                json={"page": index, "total_pages": 10, "title": f"T{gid}"},
            ).status_code
            == 200
        )
        time.sleep(0.005)

    page_one = client.get("/api/eh/history", params={"page": 1, "page_size": 2})
    assert page_one.status_code == 200
    body = page_one.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 3
    assert [item["gid"] for item in body["items"]] == [GID + 2, GID + 1]
    assert body["items"][0]["title"] == f"T{GID + 2}"
    assert body["items"][0]["thumb"] is None

    page_two = client.get("/api/eh/history", params={"page": 2, "page_size": 2}).json()
    assert [item["gid"] for item in page_two["items"]] == [GID]

    beyond = client.get("/api/eh/history", params={"page": 9, "page_size": 2}).json()
    assert beyond["total"] == 3
    assert beyond["items"] == []

    assert session.query(OnlineReadingProgress).count() == 3


@pytest.mark.parametrize("bad_page", [0, -3])
def test_page_below_one_is_422(api: Any, bad_page: int) -> None:
    client, session = api

    response = client.put(_progress_url(), json={"page": bad_page})

    assert response.status_code == 422
    assert session.get(OnlineReadingProgress, GID) is None


def test_page_beyond_total_is_422(api: Any) -> None:
    client, _session = api

    response = client.put(_progress_url(), json={"page": 9, "total_pages": 8})

    assert response.status_code == 422


def test_resolved_image_urls_are_never_stored(api: Any) -> None:
    client, session = api

    response = client.put(
        _progress_url(),
        json={"page": 2, "image_url": RESOLVED_IMAGE, "url": RESOLVED_IMAGE},
    )
    assert response.status_code == 200
    assert RESOLVED_IMAGE not in response.text
    assert "image_url" not in response.json()

    row = session.get(OnlineReadingProgress, GID)
    assert row is not None
    stored_values = {str(value) for value in vars(row).values()}
    assert RESOLVED_IMAGE not in stored_values
    assert not any("url" in column.name for column in OnlineReadingProgress.__table__.columns)

    # Even smuggled through ``thumb`` a resolved page-image host is rejected.
    rejected = client.put(_progress_url(), json={"page": 2, "thumb": RESOLVED_IMAGE})
    assert rejected.status_code == 422
    assert session.get(OnlineReadingProgress, GID).thumb is None


def test_token_mismatch_is_404(api: Any) -> None:
    client, _session = api
    assert client.put(_progress_url(), json={"page": 2}).status_code == 200

    response = client.get(_progress_url(token="deadbeef"))

    assert response.status_code == 404


# --- repository-level contract --------------------------------------------


class _MemorySession:
    """Fake session with only ``get``/``add``/``flush`` (read-modify-write path)."""

    def __init__(self) -> None:
        self.rows: dict[int, OnlineReadingProgress] = {}

    async def get(self, _model: Any, pk: Any) -> Any:
        return self.rows.get(pk)

    def add(self, obj: Any) -> None:
        self.rows[obj.gid] = obj

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_repository_read_modify_write_fallback_is_monotonic() -> None:
    repo = OnlineProgressRepository(_MemorySession())

    created, accepted = await repo.save(GID, token=TOKEN, page=3, total_pages=9)
    assert accepted is True
    assert (created.current_page, created.total_pages) == (3, 9)

    stale, accepted = await repo.save(GID, token=TOKEN, page=1)
    assert accepted is False
    assert stale.current_page == 3
    assert stale.total_pages == 9

    refreshed, accepted = await repo.save(GID, token=TOKEN, page=3)
    assert accepted is True
    assert refreshed.current_page == 3


def test_router_request_model_rejects_page_zero() -> None:
    with pytest.raises(ValidationError):
        OnlineProgressRequest(page=0)


@pytest.mark.asyncio
async def test_direct_route_404_and_history_empty(api: Any) -> None:
    _client, session = api
    shim = _AsyncSessionShim(session)

    with pytest.raises(HTTPException) as error:
        await eh_online_progress(GID, TOKEN, session=shim)
    assert error.value.status_code == 404

    await save_eh_online_progress(GID, TOKEN, OnlineProgressRequest(page=1), session=shim)
    history = await eh_online_history(page=1, page_size=20, session=shim)
    assert history["total"] == 1
    assert history["items"][0]["gid"] == GID
