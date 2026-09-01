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
        "_download_retry_sweep_loop",
        "_gallery_updates_finalize_loop",
        "_tag_sync_worker_loop",
        "_thumbnail_worker_loop",
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
    assert data.get("download_title") == "japanese"


def test_exhentai_test_endpoint_maps_status_codes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The login-test endpoint must answer with meaningful HTTP status codes."""
    from galleryvault.app import main

    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))

    class FakeLogin:
        def __init__(self) -> None:
            self.result: tuple[str, str] = ("ok", "HTTP 200")

        async def check_login(self) -> tuple[str, str]:
            return self.result

        async def aclose(self) -> None:
            pass

    fake = FakeLogin()
    monkeypatch.setattr(main.app.state, "eh_client", fake)
    real_settings = main._settings()
    monkeypatch.setattr(
        main,
        "_settings",
        lambda: real_settings.model_copy(
            update={"exhentai_cookies": {"ipb_member_id": "12345"}}
        ),
    )

    assert client.post("/api/settings/exhentai/test").status_code == 200
    fake.result = ("not_logged_in", "HTTP 200")
    assert client.post("/api/settings/exhentai/test").status_code == 401
    fake.result = ("no_exhentai_access", "HTTP 200")
    assert client.post("/api/settings/exhentai/test").status_code == 403
    fake.result = ("failed", "ConnectError")
    assert client.post("/api/settings/exhentai/test").status_code == 502

    # No cookies configured → 400, never reaching the client.
    monkeypatch.setattr(
        main,
        "_settings",
        lambda: real_settings.model_copy(update={"exhentai_cookies": {}}),
    )
    assert client.post("/api/settings/exhentai/test").status_code == 400


def test_settings_save_persists_auth_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The settings page checkbox must survive a save.

    Regression guard: SettingsRequest previously had no ``auth_required`` field,
    so pydantic silently dropped the submitted value and the toggle could never
    be persisted (dead UI since v1.0.0).
    """
    from galleryvault.app import main
    from galleryvault.app.routers import settings as settings_router

    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    saved: dict[str, object] = {}

    class FakeRepo:
        def __init__(self, session: object) -> None:
            self.session = session

        async def get(self) -> dict[str, object]:
            return dict(saved)

        async def save(self, values: dict[str, object]) -> None:
            saved.clear()
            saved.update(values)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

    monkeypatch.setattr(settings_router, "SettingsRepository", FakeRepo)
    monkeypatch.setattr(main, "_settings_session", lambda: Session())
    response = client.post("/api/settings", json={"auth_required": False, "page_concurrency": 8})
    assert response.status_code == 200
    assert saved["auth_required"] is False
    assert saved["page_concurrency"] == 8
    # In-memory runtime settings must reflect the toggle immediately too.
    assert main._settings().auth_required is False


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


@pytest.mark.asyncio
async def test_settings_service_refresh_services_syncs_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """settings_service.refresh_services must update both app_state and main.app.state."""
    from galleryvault.app import dependencies, main
    from galleryvault.app.state import app_state
    from galleryvault.services import settings_service

    closed = []

    class FakeClient:
        async def aclose(self):
            closed.append("eh_client")

    class FakeNotifier:
        client = object()

        async def aclose(self):
            closed.append("telegram")

        async def flush_summary(self) -> bool:
            return False

    old_client = FakeClient()
    old_notifier = FakeNotifier()
    app_state.eh_client = old_client
    app_state.telegram = old_notifier
    main.app.state.eh_client = old_client
    main.app.state.telegram = old_notifier

    new_client = FakeClient()
    new_dl = object()
    new_tg = FakeNotifier()
    new_fav = object()

    monkeypatch.setattr(settings_service, "EhClient", lambda *a, **k: new_client)
    monkeypatch.setattr(settings_service, "Downloader", lambda *a, **k: new_dl)
    monkeypatch.setattr(settings_service, "TelegramNotifier", lambda *a, **k: new_tg)
    monkeypatch.setattr(settings_service, "FavoritesService", lambda *a, **k: new_fav)
    monkeypatch.setattr(settings_service, "start_telegram_bot", lambda: None)
    monkeypatch.delattr(main, "_refresh_services", raising=False)

    await settings_service.refresh_services()

    assert "eh_client" in closed
    assert "telegram" in closed
    assert app_state.downloader is new_dl
    assert main.app.state.downloader is new_dl
    assert app_state.eh_client is new_client
    assert main.app.state.eh_client is new_client
    assert dependencies.get_downloader() is new_dl
    assert dependencies.get_eh_client() is new_client


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


def test_gallery_list_category_not_fav_forwards_exclude_favorited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app import main

    calls = []

    async def list_page(self, page: int, page_size: int, q: str | None = None,
                        tags=(), tag_mode="or", tag_match="exact", category=None,
                        exclude_favorited=False):
        calls.append((category, exclude_favorited))
        return 0, []

    monkeypatch.setattr(main.GalleryRepository, "list_page", list_page)
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    response = client.get("/api/galleries?category=__not_fav__")
    assert response.status_code == 200
    assert calls[-1] == (None, True)
    assert response.json()["category"] == "__not_fav__"


def test_gallery_list_not_fav_with_real_category_still_rejects_unknown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    assert client.get("/api/galleries?category=bogus").status_code == 422


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


def _fake_request(headers, client_host="127.0.0.1"):
    class _Headers(dict):
        def get(self, key, default=None):
            return super().get(key.lower(), default)

    return SimpleNamespace(
        headers=_Headers({k.lower(): v for k, v in headers.items()}),
        client=SimpleNamespace(host=client_host),
    )


def test_client_ip_prefers_trusted_x_real_ip() -> None:
    """Login rate limiting keys on nginx's X-Real-IP, not the socket peer."""
    from galleryvault.app.main import _client_ip

    assert _client_ip(_fake_request({"x-real-ip": "1.2.3.4"})) == "1.2.3.4"
    assert _client_ip(_fake_request({"X-Real-IP": "  1.2.3.4  "})) == "1.2.3.4"


def test_client_ip_falls_back_to_socket_peer() -> None:
    """Direct backend access without a proxy header falls back to client.host."""
    from galleryvault.app.main import _client_ip

    assert _client_ip(_fake_request({}, client_host="9.9.9.9")) == "9.9.9.9"
    assert _client_ip(_fake_request({"x-real-ip": ""}, client_host="9.9.9.9")) == "9.9.9.9"
    assert (
        _client_ip(_fake_request({"x-real-ip": " "}, client_host="7.7.7.7")) == "7.7.7.7"
    )


def test_client_ip_unknown_without_client() -> None:
    from galleryvault.app.main import _client_ip

    assert _client_ip(SimpleNamespace(headers={}, client=None)) == "unknown"


def test_login_rate_limit_keys_on_x_real_ip(client: TestClient) -> None:
    """A spoofed X-Real-IP must not reset another bucket's counters."""
    from galleryvault.app import main

    original = main._login_attempts
    original_lock = main._login_lock
    main._login_attempts = {}
    main._login_lock = __import__("asyncio").Lock()

    def reset():
        main._login_attempts = original
        main._login_lock = original_lock

    try:
        # Pretend every request carries the proxy-set X-Real-IP; the bucket
        # must key on it (here via the TestClient, whose socket peer is
        # 127.0.0.1 — a spoofed header must not mix into that bucket).
        for _ in range(main.LOGIN_RATE_MAX + 1):
            resp = client.post(
                "/login",
                data={"password": "wrong"},
                follow_redirects=False,
                headers={"X-Real-IP": "5.5.5.5"},
            )
            assert resp.status_code in {303, 429}
        limited = client.post(
            "/login",
            data={"password": "wrong"},
            follow_redirects=False,
            headers={"X-Real-IP": "5.5.5.5"},
        )
        assert limited.status_code == 429
        # A different X-Real-IP still has its own fresh bucket.
        other = client.post(
            "/login",
            data={"password": "wrong"},
            follow_redirects=False,
            headers={"X-Real-IP": "6.6.6.6"},
        )
        assert other.status_code == 303
    finally:
        reset()


def test_client_ip_ignores_spoofed_headers_from_untrusted_socket() -> None:
    from galleryvault.app.main import _client_ip

    # Untrusted public IP directly connecting with spoofed proxy headers
    fake_req = SimpleNamespace(
        headers={"x-real-ip": "1.2.3.4", "x-forwarded-for": "8.8.8.8"},
        client=SimpleNamespace(host="8.8.8.8"),
    )
    assert _client_ip(fake_req) == "8.8.8.8"

    # Trusted proxy connecting with real client header
    trusted_req = SimpleNamespace(
        headers={"x-real-ip": "198.51.100.22"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert _client_ip(trusted_req) == "198.51.100.22"


def test_cross_origin_api_request_rejected(client: TestClient) -> None:
    # Mutating API requests with cross-origin Sec-Fetch-Site or mismatched Origin
    client.cookies.set("galleryvault_session", create_session("unit-test-secret", 60))
    resp = client.post(
        "/api/tasks/scan",
        headers={"Sec-Fetch-Site": "cross-site", "Origin": "http://evil.com"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Cross-origin request rejected"}
