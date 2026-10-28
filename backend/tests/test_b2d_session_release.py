"""B2-D #7/#8: request DB sessions must not stay checked out during network
I/O or while a streaming/file response is being transferred."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.responses import StreamingResponse

from galleryvault.app.dependencies import release_session
from galleryvault.app.routers import favorites, galleries
from galleryvault.app.schemas import (
    ArchivePreviewRequest,
    DownloadOriginalRequest,
    FavoriteNoteRequest,
)


class _Session:
    """Minimal async session double recording transaction boundaries."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.in_tx = True

    def in_transaction(self) -> bool:
        return self.in_tx

    async def rollback(self) -> None:
        self.in_tx = False
        self.events.append("rollback")

    async def commit(self) -> None:
        self.in_tx = False
        self.events.append("commit")


class _ClientContext:
    def __init__(self, events: list[str], client: object) -> None:
        self.events = events
        self.client = client

    async def __aenter__(self) -> object:
        return self.client

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _Mgr:
    def __init__(self, events: list[str], client: object) -> None:
        self.events = events
        self.client = client

    def client_context(self, settings: object = None) -> _ClientContext:
        return _ClientContext(self.events, self.client)


def _gallery_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        gid=42,
        token="tok",
        title="Title",
        title_jpn=None,
        storage_path="/tmp/gallery",
        storage_type="ehviewer_dir",
        storage_signature=None,
    )


async def test_release_session_rolls_back_open_transaction() -> None:
    events: list[str] = []
    await release_session(_Session(events))
    assert events == ["rollback"]


async def test_release_session_ignores_non_session_values() -> None:
    # Endpoints called directly without FastAPI DI may hold a Depends marker.
    await release_session(object())


async def test_toggle_favorite_releases_before_cloud_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)
    row = _gallery_row()

    class _Client:
        async def add_favorite(self, gid: int, token: str, favcat: int, note: str | None = None) -> None:
            events.append("network")

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def favcats_for_gid(self, gid: int, gallery_id: int | None = None) -> list[int]:
            return []

        async def remember(self, favcat: int, item: object) -> None:
            events.append("write")

    monkeypatch.setattr(
        galleries, "_invoke_gallery", AsyncMock(return_value=(row, []))
    )
    monkeypatch.setattr(galleries, "FavoritesRepository", _Repo)

    result = await galleries.toggle_gallery_favorite(
        7, 0, session=session, eh_client_mgr=_Mgr(events, _Client())
    )

    assert result["favorite"] is True
    assert events.index("rollback") < events.index("network")
    assert events.index("network") < events.index("write")


async def test_download_original_releases_before_metadata_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)
    row = _gallery_row()

    class _Client:
        async def fetch_gallery(self, *args: object, **kwargs: object) -> object:
            events.append("network")
            return SimpleNamespace(pages=[SimpleNamespace(origin_url="https://example/orig")])

    class _DownloadRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def create(self, *args: object, **kwargs: object) -> object:
            events.append("write")
            return SimpleNamespace(id=1, gid=42)

    monkeypatch.setattr(
        galleries, "_invoke_gallery", AsyncMock(return_value=(row, []))
    )
    monkeypatch.setattr(galleries, "get_eh_client", lambda: _Client())
    monkeypatch.setattr(galleries, "DownloadRepository", _DownloadRepo)

    result = await galleries.download_gallery_original(
        7, DownloadOriginalRequest(archive=False), session=session
    )

    assert result["status"] == "pending"
    assert events.index("rollback") < events.index("network")
    assert events.index("network") < events.index("write")


async def test_favorite_note_releases_before_cloud_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)

    class _Client:
        async def add_favorite(self, *args: object, **kwargs: object) -> None:
            events.append("network")

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def item_for_gid(self, gid: int) -> object:
            return SimpleNamespace(token="tok", favcat=3)

        async def update_note(self, gid: int, note: str, favcat: int | None = None) -> int:
            events.append("write")
            return 1

    monkeypatch.setattr(favorites, "FavoritesRepository", _Repo)

    def _spawn(coro: object, operation: str) -> object:
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        return object()

    monkeypatch.setattr(favorites, "spawn_task", _spawn)

    result = await favorites.favorites_set_note(
        FavoriteNoteRequest(gid=42, note="hello"),
        session=session,
        favorite_service=None,
        eh_client_mgr=_Mgr(events, _Client()),
    )

    assert result["cloud_ok"] is True
    assert events.index("rollback") < events.index("network")
    assert events.index("network") < events.index("write")


async def test_archives_preview_releases_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)

    class _Client:
        async def fetch_gp_balance(self) -> int:
            events.append("network-gp")
            return 1000

        async def fetch_archive_info(self, gid: int, token: str) -> object:
            events.append("network-archive")
            return SimpleNamespace(
                resample_url=None,
                resample_cost=0,
                resample_size=None,
                original_url="https://example/orig",
                original_cost=10,
                original_size=11,
            )

    class _FavRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def favorite_items_detail_by_gids(self, gids: list[int]) -> dict[int, dict[str, object]]:
            return {gid: {"token": "tok", "title": "Title"} for gid in gids}

        async def by_new_gids(self, gids: list[int]) -> list[object]:
            return []

        async def find_by_gids(self, gids: list[int]) -> list[object]:
            return []

    async def _prepare(pairs: list[tuple[int, str]]) -> list[object]:
        events.append("network-prepare")
        return [
            SimpleNamespace(gone=False, token="tok", gid=gid, title="Title", title_jpn=None)
            for gid, _token in pairs
        ]

    monkeypatch.setattr(favorites, "FavoritesRepository", _FavRepo)
    monkeypatch.setattr(favorites, "GalleryUpdatesRepository", _FavRepo)
    monkeypatch.setattr(favorites, "GalleryRepository", _FavRepo)
    monkeypatch.setattr(favorites, "prepare_galleries", _prepare)
    monkeypatch.setattr(favorites.app_state, "eh_client", _Client())

    result = await favorites.archives_preview(
        ArchivePreviewRequest(gids=[42]), session=session
    )

    assert result["items"][0]["original_available"] is True
    assert events.index("rollback") < events.index("network-prepare")
    assert events.index("network-prepare") < events.index("network-gp")
    assert events.index("network-gp") < events.index("network-archive")


async def test_get_page_releases_before_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    session = _Session(events)
    row = _gallery_row()
    page = SimpleNamespace(page_index=0, member_name="0001.jpg", media_type="jpg", manifest={})

    class _Scanner:
        def open_page(self, meta: object, info: object) -> io.BytesIO:
            return io.BytesIO(b"page-bytes")

    monkeypatch.setattr(
        galleries, "_invoke_gallery", AsyncMock(return_value=(row, [page]))
    )
    monkeypatch.setattr(galleries.registry, "for_path", lambda _path: _Scanner())

    response = await galleries.get_page(7, 0, session=session)

    assert isinstance(response, StreamingResponse)
    assert events == ["rollback"]
    assert response.media_type == "image/jpeg"
