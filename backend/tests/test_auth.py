from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.auth import create_session, hash_password, verify_password, verify_session
from galleryvault.services.tag_sync import GalleryGidMissing, TagSyncResult


@pytest.fixture
def client() -> TestClient:
    original = app.state.settings
    app.state.settings = original.model_copy(
        update={
            "auth_secret": "unit-test-secret",
            "auth_password_hash": hash_password("correct horse"),
            "auth_password": None,
        }
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.state.settings = original


@pytest.fixture(autouse=True)
def db_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the app's DB-backed auth bootstrap from clobbering test fixtures.

    The unit tests set app.state.settings directly, but the startup event reads
    the real DB (which holds the production password hash) and would otherwise
    override it.  Stub the DB reads so the in-memory settings stay authoritative.
    """
    from galleryvault.app import main

    async def _empty_runtime() -> dict:
        return {}

    async def _noop() -> None:
        return None

    monkeypatch.setattr(main, "SettingsRepository", lambda: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(main, "_runtime_row", _empty_runtime)
    monkeypatch.setattr(main, "_bootstrap_auth", _empty_runtime)
    # Keep the app's background workers out of the test event loop: they use
    # global asyncio.Queues/engines that must not leak across TestClient loops.
    for _name in (
        "_favorites_poll_loop",
        "_download_worker_loop",
        "_tag_sync_worker_loop",
    ):
        monkeypatch.setattr(main, _name, _noop)
    monkeypatch.setattr(main, "_ensure_translation_updater", lambda: None)


def test_password_hash_and_verify() -> None:
    encoded = hash_password("secret")
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("secret", encoded)
    assert not verify_password("wrong", encoded)


def test_session_expiry_and_tampering() -> None:
    expired = create_session("secret", -1)
    valid = create_session("secret", 60)
    assert not verify_session(expired, "secret")
    assert verify_session(valid, "secret")
    assert not verify_session(valid + "x", "secret")
    assert not verify_session(valid, "other-secret")


def test_protected_api_and_login_flow(client: TestClient) -> None:
    assert client.get("/api/galleries").status_code == 401
    failed = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    assert failed.status_code == 303 and "error=1" in failed.headers["location"]
    successful = client.post("/login", data={"password": "correct horse"}, follow_redirects=False)
    assert successful.status_code == 303
    cookie = successful.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    # The backend is a pure JSON API; the SPA is served by the separate
    # frontend repo, so no HTML page exists here.
    assert client.get("/").status_code == 404
    # GET /login is a redirect to the SPA root (the frontend handles the form).
    assert client.get("/login", follow_redirects=False).status_code == 303


def test_tag_sync_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/galleries/7/sync-tags").status_code == 401


def test_tag_sync_success_and_upstream_failure_are_safe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app import main

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

    class Service:
        async def sync(self, identifier: int):
            if identifier == 7:
                return TagSyncResult(42, "title", 2, datetime.now(UTC))
            if identifier == 8:
                raise GalleryGidMissing("Gallery has no ExHentai gid")
            raise RuntimeError("cookie=secret-token")

    monkeypatch.setattr(main, "_settings_session", lambda: Session())
    monkeypatch.setattr(main, "TagSyncService", lambda client, repository: Service())
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    success = client.post("/api/galleries/7/sync-tags")
    assert success.status_code == 200
    assert success.json()["gid"] == 42 and success.json()["count"] == 2
    assert client.post("/api/galleries/8/sync-tags").status_code == 422
    failure = client.post("/api/galleries/9/sync-tags")
    assert failure.status_code == 502
    assert "secret-token" not in failure.text


def test_pagination_validation_does_not_touch_database(client: TestClient) -> None:
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    assert client.get("/api/galleries?page=0").status_code == 422
    assert client.get("/api/galleries?page_size=101").status_code == 200
    assert client.get("/api/galleries?page_size=501").status_code == 422


def test_settings_api_exposes_configuration_groups(client: TestClient) -> None:
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert all(
        key in data
        for key in ("library_roots", "exhentai_base_url", "download_root", "favorites_categories")
    )


def test_protected_api_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/settings", follow_redirects=False).status_code == 401
    assert client.get("/api/downloads", follow_redirects=False).status_code == 401


@pytest.mark.asyncio
async def test_refresh_services_restarts_telegram_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuilding services (e.g. after saving Settings) must restart the bot.

    Otherwise the old bot keeps polling through a closed client and logs
    RuntimeError every loop (regression guard for the shared-client fix).
    """
    from galleryvault.app import main

    started = []

    def fake_start() -> None:
        started.append(1)

    class FakeNotifier:
        async def aclose(self):
            pass

        async def flush_summary(self) -> bool:
            return False

    class FakeClient:
        async def aclose(self):
            pass

    monkeypatch.setattr(main, "_start_telegram_bot", fake_start)
    monkeypatch.setattr(main, "EhClient", lambda settings, **kwargs: FakeClient())
    monkeypatch.setattr(main, "Downloader", lambda *a, **k: object())
    monkeypatch.setattr(main, "TelegramNotifier", lambda settings: FakeNotifier())
    monkeypatch.setattr(main, "FavoritesService", lambda *a, **k: object())
    monkeypatch.setattr(
        main, "_FavoritesRepositoryProxy", lambda: object()
    )
    monkeypatch.setattr(main, "_FavoriteDownloadQueue", lambda: object())

    old_bot = object()
    monkeypatch.setattr(main.app.state, "telegram_bot_task", old_bot)
    monkeypatch.setattr(main.app.state, "telegram", FakeNotifier())

    await main._refresh_services()
    assert started == [1]


def test_gallery_search_and_pagination_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gallery = SimpleNamespace(
        id=7, gid=42, title="A <title>", title_english="A <title>", title_jpn="",
        page_count=3, storage_type="folder", category=None,
    )

    async def list_page(self, page: int, page_size: int, q: str | None = None, *_a, **_k):
        assert (page, page_size, q) == (2, 24, "needle")
        return 25, [gallery]

    from galleryvault.app import main

    monkeypatch.setattr(main.GalleryRepository, "list_page", list_page)
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    response = client.get("/api/galleries?page=2&q=needle")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 25 and body["page"] == 2
    assert body["items"][0]["title"] == "A <title>"


def test_gallery_detail_includes_spider_info(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app import main

    gallery = SimpleNamespace(
        id=7,
        gid=42,
        title="Reader title",
        title_english="Reader title",
        title_jpn="",
        storage_type="folder",
        category=None,
        token=None,
        tags_synced_at=None,
        file_size=None,
        source_meta={"version": "1.0", "start_page": 0, "mode": "local"},
    )
    page = SimpleNamespace(page_index=0, member_name="one.jpg", media_type="jpeg")

    async def get_gallery(identifier: int):
        return gallery, [page]

    monkeypatch.setattr(main, "_gallery", get_gallery)
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    response = client.get("/api/galleries/7")
    assert response.status_code == 200
    assert response.json()["spider_info"]["version"] == "1.0"
