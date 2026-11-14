"""Golden response-key shapes for the endpoints the UI reads constantly.

These tests go through the real FastAPI app (middleware, routing, response
models) while swapping only the database-backed repositories for deterministic
fakes.  That keeps the contract check HTTP-level without needing Postgres, and
the committed goldens under ``golden/`` make any accidental key rename or
dropped field visible in review.

Set ``CONTRACT_GOLDEN_UPDATE=1`` to regenerate the goldens intentionally.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from galleryvault.app import dependencies
from galleryvault.app.main import app
from galleryvault.app.routers import (
    downloads,
    duplicates,
    favorites,
    galleries,
    tasks,
    updates,
)
from galleryvault.app.routers import settings as settings_router
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.settings_service import settings_public

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class _FakeSession:
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _FakeSettingsService:
    async def get_persisted_settings(self) -> dict[str, Any]:
        return {}

    def get_public_settings(self) -> dict[str, Any]:
        return settings_public()


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    library = tmp_path / "library"
    library.mkdir()
    app_state.settings = Settings(
        auth_required=False,
        auth_secret="contract-test-secret",
        library_roots=[str(library)],
        download_root=str(library),
        # Pin the list-valued settings so the response shape does not depend on
        # the developer/CI environment (e.g. COLD_STORAGE_ROOT in the test stack).
        cold_storage_root="",
        archive_roots=[],
        exhentai_cookies={},
        trusted_proxies=[],
        telegram_chat_ids=[],
        telegram_allowed_user_ids=[],
        favorites_categories=[0, 1, 2],
    )

    async def fake_get_session():
        yield _FakeSession()

    app.dependency_overrides[dependencies.get_session] = fake_get_session
    app.dependency_overrides[dependencies.get_gallery_service] = lambda: SimpleNamespace()
    app.dependency_overrides[settings_router.get_settings_service] = _FakeSettingsService
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _shape(value: Any) -> Any:
    """Collapse a JSON value to its key structure, ignoring leaf values."""
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return "<value>"


def _assert_golden(name: str, response: Any) -> None:
    assert response.status_code == 200, response.text
    shape = _shape(response.json())
    path = GOLDEN_DIR / name
    if os.environ.get("CONTRACT_GOLDEN_UPDATE") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(shape, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert shape == expected, f"{name} response shape changed"


def _gallery_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        gid=100,
        token="token",
        title="English title",
        title_jpn="日本語タイトル",
        storage_type="ehviewer_dir",
        storage_tier="hot",
        cold_at=None,
        category="manga",
        page_count=2,
        uploader="uploader",
        posted_at=_NOW,
        file_size=1234,
        storage_size=1234,
        rating=4.5,
        favorite=False,
        favorite_category=None,
        reading_progress=0,
        expunged=False,
        image_quality="resample",
        local_rating=None,
        local_note=None,
        storage_path="/library/1-title",
        tags_synced_at=None,
        source_meta={},
    )


def test_galleries_list_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    row = _gallery_row()

    class FakeGalleryRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_page(self, *args: Any, **kwargs: Any) -> tuple[int, list[Any]]:
            return 1, [row]

        async def tags_for_galleries(
            self, gallery_ids: list[int], *args: Any
        ) -> dict[int, list[tuple[str, str]]]:
            return {row.id: [("artist", "alice")]}

        async def progress_for_galleries(self, gallery_ids: list[int]) -> dict[int, int]:
            return {row.id: 0}

    monkeypatch.setattr(galleries, "GalleryRepository", FakeGalleryRepository)
    _assert_golden("galleries_list.json", client.get("/api/galleries"))


def test_gallery_detail_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    row = _gallery_row()
    page = SimpleNamespace(page_index=0, member_name="01.jpg", media_type="image/jpeg")

    class FakeGalleryRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def get_by_id(self, identifier: int) -> Any:
            return row

        async def get_pages(self, gallery_id: int) -> list[Any]:
            return [page]

        async def tags_for_gallery(self, gallery_id: int) -> list[tuple[str, str]]:
            return [("artist", "alice")]

    monkeypatch.setattr(galleries, "GalleryRepository", FakeGalleryRepository)
    _assert_golden("gallery_detail.json", client.get("/api/galleries/1"))


def test_downloads_list_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace(
        id=1,
        gid=100,
        token="token",
        gallery_id=None,
        archive_fallback=False,
        title="English title",
        title_jpn="日本語タイトル",
        status="success",
        retry_count=0,
        max_retries=10,
        current_page=2,
        total_pages=2,
        error_message=None,
        mode="download",
        quality="resample",
        archive_status=None,
        archive_error=None,
        ingest_status="done",
    )

    class FakeDownloadRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_page(
            self, page: int, page_size: int, status: str | None
        ) -> tuple[int, list[Any]]:
            return 1, [row]

    monkeypatch.setattr(downloads, "DownloadRepository", FakeDownloadRepository)
    _assert_golden("downloads_list.json", client.get("/api/downloads"))


def test_favorites_items_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    item = SimpleNamespace(
        favcat=0,
        gid=100,
        token="token",
        title="English title",
        title_jpn="日本語タイトル",
        url="https://e-hentai.org/g/100/token/",
        first_seen_at=_NOW,
        note=None,
        file_size=1234,
        thumb=None,
    )

    class FakeFavoritesRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_items(self, *args: Any, **kwargs: Any) -> tuple[int, list[Any]]:
            return 1, [(item, None)]

    class FakeGalleryRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def tags_for_galleries(
            self, gallery_ids: list[int], *args: Any
        ) -> dict[int, list[tuple[str, str]]]:
            return {}

    async def fake_metadata(pairs: list[tuple[int, str]]) -> dict[int, dict[str, Any]]:
        return {
            100: {
                "title": "English title",
                "title_jpn": "日本語タイトル",
                "category": "manga",
                "file_count": 2,
                "file_size": 1234,
                "tags": [{"namespace": "artist", "name": "alice"}],
            }
        }

    monkeypatch.setattr(favorites, "FavoritesRepository", FakeFavoritesRepository)
    monkeypatch.setattr(favorites, "GalleryRepository", FakeGalleryRepository)
    monkeypatch.setattr(favorites, "favorites_metadata", fake_metadata)
    _assert_golden("favorites_items.json", client.get("/api/favorites/0/items"))


def test_updates_list_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace(
        id=1,
        gallery_id=5,
        old_gid=100,
        new_gid=200,
        title="English title",
        favcat=0,
        status="pending",
        error_message=None,
        detected_at=_NOW,
        updated_at=_NOW,
    )

    class FakeUpdatesRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_page(
            self, page: int, page_size: int, status: str | None
        ) -> tuple[int, list[Any]]:
            return 1, [row]

    class FakeFavoritesRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def category_names(self, favcats: list[int]) -> dict[int, str]:
            return {}

    monkeypatch.setattr(updates, "GalleryUpdatesRepository", FakeUpdatesRepository)
    monkeypatch.setattr(updates, "FavoritesRepository", FakeFavoritesRepository)
    _assert_golden("updates_list.json", client.get("/api/updates"))


def test_library_duplicates_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    groups = [
        {
            "gid": 100,
            "copies": [
                {
                    "path": "/library/100-title",
                    "title": "English title",
                    "title_jpn": "日本語タイトル",
                    "tags": [{"namespace": "artist", "name": "alice"}],
                }
            ],
        }
    ]

    class FakeGalleryRepository:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_duplicates(self) -> list[dict[str, Any]]:
            return groups

    monkeypatch.setattr(duplicates, "GalleryRepository", FakeGalleryRepository)
    _assert_golden("duplicates_library.json", client.get("/api/scan/duplicates"))


def test_cross_gid_duplicates_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = SimpleNamespace(
        id=3,
        kind="cross_gid",
        group_key="alice|work",
        artist="alice",
        status="open",
        present=True,
        payload={
            "items": [
                {
                    "gallery_id": None,
                    "gid": 100,
                    "title": "English title",
                    "title_jpn": "日本語タイトル",
                    "storage_path": None,
                    "storage_type": None,
                    "url": "https://e-hentai.org/g/100/token/",
                    "token": "token",
                    "favorited": True,
                }
            ]
        },
        legacy_keys=[],
        last_seen_at=_NOW,
    )

    async def fake_list_groups(session: Any, kind: str, **kwargs: Any) -> list[Any]:
        return [row]

    async def fake_kind_scanned(session: Any, kind: str) -> bool:
        return False

    monkeypatch.setattr(duplicates, "list_groups", fake_list_groups)
    monkeypatch.setattr(duplicates, "kind_scanned", fake_kind_scanned)
    _assert_golden(
        "duplicates_cross_gid.json", client.get("/api/library/duplicates/cross-gid")
    )


def test_favorite_duplicates_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = SimpleNamespace(
        id=1,
        group_key="alice|work",
        artist="alice",
        payload={
            "items": [
                {
                    "gid": 100,
                    "title": "English title",
                    "title_jpn": "日本語タイトル",
                    "favcat": 0,
                    "gallery_id": None,
                    "url": "https://e-hentai.org/g/100/token/",
                    "token": "token",
                    "file_size": 1234,
                    "posted_at": _NOW.isoformat(),
                    "cover_url": None,
                    "cover_data": None,
                    "favorited": True,
                    "tags": [],
                }
            ]
        },
    )

    async def fake_list_groups(
        session: Any, kind: str, *, status: str | None = None
    ) -> list[Any]:
        return [row]

    monkeypatch.setattr(favorites, "list_groups", fake_list_groups)
    _assert_golden(
        "duplicates_favorites.json", client.get("/api/favorites/duplicates/status")
    )


def test_logs_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    record = {
        "task": "scan",
        "started_at": _NOW.isoformat(),
        "completed_at": _NOW.isoformat(),
        "status": "success",
        "reason": "1 gallery",
        "done": 1,
        "total": 1,
    }

    class FakeTaskManager:
        def __init__(self) -> None:
            self.task_history = [record]

        def get_running_summary(self) -> list[dict[str, Any]]:
            return [
                {
                    "task": "scan",
                    "started_at": _NOW.isoformat(),
                    "done": 1,
                    "total": None,
                    "stage": None,
                    "cancellable": True,
                }
            ]

    monkeypatch.setattr(tasks, "get_task_manager", lambda: FakeTaskManager())
    _assert_golden("logs.json", client.get("/api/logs"))


def test_settings_shape(client: TestClient) -> None:
    _assert_golden("settings.json", client.get("/api/settings"))
