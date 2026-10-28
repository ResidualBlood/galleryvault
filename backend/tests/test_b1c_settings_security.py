"""B1-C: settings/auth security hardening (review 03 #12/#13/#14/#18/#19/#25/#26).

Each test pins one review item:

* #12 security-sensitive settings need a confirmation (password or flag)
* #13 login failures escalate into an in-process account backoff
* #14 ``GET /api/settings`` must not answer 200 when the DB read failed
* #18 saved searches read-modify-write under ``SELECT ... FOR UPDATE``
* #19 ``/api/system/logs`` must not echo unmasked tracebacks
* #25 baseline security response headers
* #26 enum/quality values are validated before they reach the database
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.auth import (
    account_lock_remaining,
    create_session,
    hash_password,
    login_failed,
    login_succeeded,
    reset_runtime_auth_bootstrap,
)
from galleryvault.config import Settings


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    def add(self, _obj: object) -> None:
        pass

    def in_transaction(self) -> bool:
        return False

    def begin(self):
        return self


class _Repo:
    """Settings repository double recording what a save would persist."""

    def __init__(self, session: object, *, stored: dict | None = None) -> None:
        self.session = session
        self.stored = dict(stored or {})
        self.saved: dict | None = None

    async def get(self) -> dict:
        return dict(self.stored)

    async def save(self, values: dict) -> None:
        self.saved = dict(values)
        self.stored = dict(values)


@pytest.fixture
def client() -> TestClient:
    original = app_state.settings
    base = original or app.state.settings
    updated = base.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "b1c-unit-test-secret",
            "auth_secret_ephemeral": False,
            "auth_password_hash": hash_password("admin-pass"),
            "auth_password": None,
            "download_root": "/downloads",
            "library_roots": ["/library"],
            "trusted_proxies": [],
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    orig_factory = app_state.session_factory
    try:
        with TestClient(app) as test_client:
            app_state.session_factory = lambda: _FakeSession()
            test_client.cookies.set(
                "galleryvault_session", create_session("b1c-unit-test-secret", 60)
            )
            yield test_client
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = original
        app.state.settings = original


def _patch_settings_repo(monkeypatch: pytest.MonkeyPatch, repo: _Repo) -> None:
    from galleryvault.app.routers import settings as settings_router

    monkeypatch.setattr(settings_router, "SettingsRepository", lambda session: repo)
    monkeypatch.setattr(settings_router, "refresh_services", _noop_async)
    monkeypatch.setattr(settings_router, "_resolve_dispatcher", lambda _d: _Dispatcher())


async def _noop_async() -> None:
    return None


class _Dispatcher:
    def spawn(self, coro: object, _name: str) -> None:
        # The cookie-health probe is unrelated to these tests.
        close = getattr(coro, "close", None)
        if callable(close):
            close()


# --- #14: GET /api/settings must fail loudly --------------------------------


def _override_settings_service(service: object) -> None:
    from galleryvault.app.routers import settings as settings_router

    app.dependency_overrides[settings_router.get_settings_service] = lambda: service


def test_get_settings_returns_503_on_database_error(client: TestClient) -> None:
    class FailingService:
        async def get_persisted_settings(self) -> dict:
            raise OperationalError("SELECT 1", {}, Exception("connection refused to db:5432"))

        def get_public_settings(self) -> dict:
            return {}

    _override_settings_service(FailingService())
    try:
        response = client.get("/api/settings")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "connection refused" not in response.text


def test_get_settings_returns_500_on_unexpected_error(client: TestClient) -> None:
    class FailingService:
        async def get_persisted_settings(self) -> dict:
            raise RuntimeError("secret-token-leak")

        def get_public_settings(self) -> dict:
            return {}

    _override_settings_service(FailingService())
    try:
        response = client.get("/api/settings")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert "secret-token-leak" not in response.text


# --- #12: security-sensitive settings need confirmation ---------------------


def test_download_root_change_requires_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo(None, stored={"download_root": "/downloads"})
    _patch_settings_repo(monkeypatch, repo)

    blocked = client.post("/api/settings", json={"download_root": "/mnt/new"})

    assert blocked.status_code == 428
    assert "download_root" in str(blocked.json()["detail"]["keys"])
    assert repo.saved is None
    assert app_state.settings.download_root == "/downloads"

    confirmed = client.post(
        "/api/settings",
        json={"download_root": "/mnt/new"},
        headers={"X-Confirm-Security-Change": "true"},
    )
    assert confirmed.status_code == 200
    assert repo.saved is not None and repo.saved["download_root"] == "/mnt/new"


def test_download_root_change_accepts_current_password(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo(None, stored={"download_root": "/downloads"})
    _patch_settings_repo(monkeypatch, repo)

    wrong = client.post(
        "/api/settings",
        json={"download_root": "/mnt/new", "current_password": "nope"},
    )
    assert wrong.status_code == 428
    assert repo.saved is None

    ok = client.post(
        "/api/settings",
        json={"download_root": "/mnt/new", "current_password": "admin-pass"},
    )
    assert ok.status_code == 200
    assert repo.saved is not None and repo.saved["download_root"] == "/mnt/new"


def test_library_roots_and_trusted_proxies_are_gated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo(None, stored={"library_roots": ["/library"]})
    _patch_settings_repo(monkeypatch, repo)

    assert client.post("/api/settings", json={"library_roots": ["/"]}).status_code == 428
    assert (
        client.post("/api/settings", json={"trusted_proxies": ["0.0.0.0/0"]}).status_code == 428
    )
    assert repo.saved is None


def test_unchanged_sensitive_values_need_no_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The settings page always resubmits roots: identical values must pass."""
    repo = _Repo(None, stored={"library_roots": ["/library"]})
    _patch_settings_repo(monkeypatch, repo)

    response = client.post(
        "/api/settings",
        json={
            "library_roots": "/library",
            "download_root": "/downloads",
            "page_concurrency": 6,
        },
    )

    assert response.status_code == 200
    assert repo.saved is not None and repo.saved["page_concurrency"] == 6


def test_auth_required_disable_is_gated_without_admin_password(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default-password installs must not be pushed into open mode silently."""
    repo = _Repo(None, stored={})
    _patch_settings_repo(monkeypatch, repo)
    pristine = app_state.settings.model_copy(
        update={"auth_password": None, "auth_password_hash": None, "auth_required": True}
    )
    app_state.settings = pristine
    app.state.settings = pristine

    blocked = client.post("/api/settings", json={"auth_required": False})
    assert blocked.status_code == 428
    assert repo.saved is None

    allowed = client.post(
        "/api/settings",
        json={"auth_required": False, "confirm_security_change": True},
    )
    assert allowed.status_code == 200
    assert repo.saved is not None and repo.saved["auth_required"] is False


# --- #26: enum validation ---------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"download_quality": "high"},
        {"archive_quality": "max"},
        {"download_title": "korean"},
        {"title_display": "romaji"},
    ],
)
def test_invalid_choice_values_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    repo = _Repo(None, stored={})
    _patch_settings_repo(monkeypatch, repo)

    response = client.post("/api/settings", json=payload)

    assert response.status_code == 422
    assert repo.saved is None


# --- #19: log export masking ------------------------------------------------


def test_system_logs_masks_exception_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import settings as settings_router

    monkeypatch.setattr(
        settings_router,
        "get_recent_logs",
        lambda **_kwargs: [
            {
                "message": "request failed",
                "exception": "HTTPStatusError: url?ipb_pass_hash=deadbeef",
                "context": {"ipb_pass_hash": "deadbeef"},
            }
        ],
    )

    response = client.get("/api/system/logs")

    assert response.status_code == 200
    body = response.text
    assert "deadbeef" not in body
    assert "***" in body


# --- #18: saved searches use a row lock -------------------------------------


class _Result:
    def __init__(self, row: object) -> None:
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def scalar_one(self):
        assert self._row is not None
        return self._row


class _Row:
    def __init__(self, value: dict) -> None:
        self.value = value


class _LockSession(_FakeSession):
    def __init__(self, stored: dict) -> None:
        self.stored = stored
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Result(_Row(self.stored) if self.stored else None)


def test_saved_search_add_locks_settings_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import settings as settings_router

    stored = {"saved_searches": [{"id": "keep", "name": "Keep", "query": {}}]}
    session = _LockSession(stored)
    app_state.session_factory = lambda: session
    repo = _Repo(None, stored=stored)
    monkeypatch.setattr(settings_router, "SettingsRepository", lambda _session: repo)

    response = client.post("/api/saved-searches", json={"name": "New", "query": {"q": "x"}})

    assert response.status_code == 200
    assert any("FOR UPDATE" in statement.upper() for statement in session.statements)
    assert repo.saved is not None
    names = [item["name"] for item in repo.saved["saved_searches"]]
    assert names == ["Keep", "New"]


# --- #13: account-level login backoff --------------------------------------


@pytest.fixture(autouse=True)
def _reset_login_state():
    from galleryvault import auth as auth_module

    saved = (auth_module._account_failures, auth_module._account_locked_until)
    auth_module._account_failures = {}
    auth_module._account_locked_until = {}
    try:
        yield
    finally:
        auth_module._account_failures, auth_module._account_locked_until = saved


@pytest.mark.asyncio
async def test_account_backoff_escalates_and_clears() -> None:
    ip = "203.0.113.9"
    assert await account_lock_remaining(ip) == 0.0

    lockouts = [await login_failed(ip) for _ in range(5)]
    assert lockouts[:4] == [0.0, 0.0, 0.0, 0.0]
    assert lockouts[4] > 0
    assert await account_lock_remaining(ip) > 0

    # Further failures double the delay instead of resetting it.
    again = await login_failed(ip)
    assert again > lockouts[4]
    # Rotating source IP cannot evade the single account's backoff.
    assert await account_lock_remaining("198.51.100.7") > 0.0

    await login_succeeded(ip)
    assert await account_lock_remaining(ip) == 0.0


def test_login_returns_429_when_account_locked(client: TestClient) -> None:
    from galleryvault import auth as auth_module

    auth_module._account_locked_until["admin"] = 9_999_999_999.0
    try:
        response = client.post("/login", data={"password": "admin-pass"}, follow_redirects=False)
    finally:
        auth_module._account_locked_until.pop("admin", None)

    assert response.status_code == 429
    assert "retry-after" in {key.lower() for key in response.headers}


# --- #25: security headers --------------------------------------------------


def test_security_headers_are_present(client: TestClient) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self'" in csp
    # The shell is a hash-routed SPA served by nginx; the backend CSP must keep
    # the policies the frontend relies on (inline <style>, worker).
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "worker-src 'self'" in csp


def test_security_headers_on_unauthenticated_responses() -> None:
    with TestClient(app, client=("198.51.100.5", 50000)) as ext_client:
        response = ext_client.get("/api/settings")
    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"


# --- #24: DB-persisted session secret (workers disabled) -------------------


class _SecretSession(_FakeSession):
    def __init__(self, store: dict) -> None:
        self.store = store

    async def get(self, _model, key):
        return self.store.get(key)

    async def execute(self, *_args, **_kwargs):
        from types import SimpleNamespace

        from sqlalchemy.dialects.postgresql import Insert
        from sqlalchemy.sql import Select

        statement = _args[0]
        if isinstance(statement, Insert):
            self.store.setdefault("runtime_auth", SimpleNamespace(value={}))
        if isinstance(statement, Select):
            assert statement._for_update_arg is not None
            return _Result(self.store["runtime_auth"])
        return _Result(None)

    def add(self, obj: object) -> None:
        self.store[obj.key] = obj


@pytest.mark.asyncio
async def test_ephemeral_secret_adopts_persisted_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from galleryvault.auth import ensure_runtime_auth_secret

    reset_runtime_auth_bootstrap()
    store = {"runtime_auth": SimpleNamespace(value={"auth_secret": "shared-secret"})}
    original_settings = app_state.settings
    original_factory = app_state.session_factory
    app_state.settings = original_settings.model_copy(
        update={"auth_secret": "local-only", "auth_secret_ephemeral": True}
    )
    app_state.settings._generated_auth_secret = "local-only"
    app_state.session_factory = lambda: _SecretSession(store)
    try:
        await ensure_runtime_auth_secret()

        assert app_state.settings.auth_secret == "shared-secret"
        assert app_state.settings.auth_secret_ephemeral is False
        from galleryvault.auth import verify_session

        assert verify_session(create_session("shared-secret", 60), "shared-secret")
    finally:
        app_state.settings = original_settings
        app_state.session_factory = original_factory
        reset_runtime_auth_bootstrap()


@pytest.mark.asyncio
async def test_ephemeral_secret_is_persisted_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.auth import ensure_runtime_auth_secret

    reset_runtime_auth_bootstrap()
    store: dict = {}
    original_settings = app_state.settings
    original_factory = app_state.session_factory
    app_state.settings = original_settings.model_copy(
        update={"auth_secret": "fresh-secret", "auth_secret_ephemeral": True}
    )
    app_state.settings._generated_auth_secret = "fresh-secret"
    app_state.session_factory = lambda: _SecretSession(store)
    try:
        await ensure_runtime_auth_secret()

        assert store["runtime_auth"].value["auth_secret"] == "fresh-secret"
        assert app_state.settings.auth_secret == "fresh-secret"
        assert app_state.settings.auth_secret_ephemeral is False
    finally:
        app_state.settings = original_settings
        app_state.session_factory = original_factory
        reset_runtime_auth_bootstrap()


@pytest.mark.asyncio
async def test_explicit_secret_is_not_overridden() -> None:
    from galleryvault.auth import ensure_runtime_auth_secret

    reset_runtime_auth_bootstrap()
    original_settings = app_state.settings
    app_state.settings = original_settings.model_copy(
        update={"auth_secret": "env-secret", "auth_secret_ephemeral": False}
    )
    try:
        await ensure_runtime_auth_secret()
        assert app_state.settings.auth_secret == "env-secret"
    finally:
        app_state.settings = original_settings
        reset_runtime_auth_bootstrap()


# --- config bounds (01 P3-7 / 02 P3-3) -------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"thumbnail_workers": 0},
        {"thumbnail_workers": 99},
        {"exhentai_max_concurrency": 0},
        {"exhentai_max_concurrency": 100},
    ],
)
def test_concurrency_bounds_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(**payload)


def test_concurrency_bounds_accept_reasonable_values() -> None:
    settings = Settings(thumbnail_workers=1, exhentai_max_concurrency=1)
    assert settings.thumbnail_workers == 1
    assert settings.exhentai_max_concurrency == 1


@pytest.mark.parametrize("flag", ["false", "true", 1, [], {}])
def test_security_confirmation_requires_json_boolean(client, monkeypatch, flag):
    repo = _Repo(None)
    _patch_settings_repo(monkeypatch, repo)
    response = client.post("/api/settings", json={
        "download_root": "/different", "confirm_security_change": flag,
    })
    assert response.status_code == 428
    assert repo.saved is None


def test_auth_required_change_with_configured_password_requires_confirmation(client, monkeypatch):
    repo = _Repo(None)
    _patch_settings_repo(monkeypatch, repo)
    response = client.post("/api/settings", json={"auth_required": False})
    assert response.status_code == 428
    assert repo.saved is None
    response = client.post("/api/settings", json={
        "auth_required": False, "confirm_security_change": True,
    })
    assert response.status_code == 200
    assert repo.saved["auth_required"] is False


@pytest.mark.asyncio
async def test_secret_bootstrap_database_failure_is_retryable(monkeypatch):
    from galleryvault import auth as auth_module

    original = app_state.settings
    generated = Settings()
    generated.auth_secret_ephemeral = True
    generated._generated_auth_secret = generated.auth_secret
    monkeypatch.setattr(app_state, "settings", generated)

    class BrokenSession(_SecretSession):
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    reset_runtime_auth_bootstrap()
    monkeypatch.setattr(app_state, "session_factory", lambda: BrokenSession({}))
    try:
        with pytest.raises(RuntimeError):
            await auth_module.ensure_runtime_auth_secret()
        assert auth_module._auth_bootstrap_done is False
        store = {}
        monkeypatch.setattr(app_state, "session_factory", lambda: _SecretSession(store))
        await auth_module.ensure_runtime_auth_secret()
        assert app_state.settings.auth_secret_ephemeral is False
    finally:
        app_state.settings = original
        reset_runtime_auth_bootstrap()


@pytest.mark.asyncio
async def test_saved_search_missing_row_is_seeded_before_lock():
    from galleryvault.app.routers.settings import _locked_user_settings

    session = _LockSession({})
    assert await _locked_user_settings(session) == {}
    assert "ON CONFLICT" in session.statements[0]
    assert "FOR UPDATE" in session.statements[1]
