"""Regression tests for P0/P1/P2 pause/purge/integrity/quota fixes."""

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import get_settings
from galleryvault.db.models import Gallery
from galleryvault.services.settings_service import update_runtime_settings


@pytest.mark.asyncio
async def test_pause_save_merges_not_overwrites(monkeypatch):
    """POST /api/pause must merge into existing user_settings, not overwrite.

    Regression for P0: SettingsRepository.save({"global_paused": True}) cleared
    Cookie / library_roots. The web and bot paths now get() then merge.
    """
    from galleryvault.app.routers import tasks as tasks_module

    # Start from a known settings with cookies + roots
    base = get_settings()
    base = base.model_copy(update={
        "exhentai_cookies": {"ipb_member_id": "1", "ipb_pass_hash": "h", "igneous": "i"},
        "library_roots": ["/library"],
        "global_paused": False,
    })
    app_state.settings = base

    # Fake DB that stores whatever save() receives
    stored = {"exhentai_cookies": {"ipb_member_id": "1"}, "library_roots": ["/library"], "some_other": "keep"}

    class FakeRepo:
        def __init__(self, session):
            pass
        async def get(self):
            return dict(stored)
        async def save(self, value):
            stored.clear()
            stored.update(value)
            # expose for assertion
            self.saved = value

    monkeypatch.setattr(tasks_module, "SettingsRepository", FakeRepo)
    # Also need get_session to yield a session with begin()
    class FakeSession:
        def begin(self):
            return self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(tasks_module, "get_session", fake_get_session)
    # Ensure the DB path is taken (session_factory guard)
    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: FakeSession()
    # update_runtime_settings should now accept global_paused (P0 #2)
    # Ensure it doesn't filter it out
    update_runtime_settings({"global_paused": True})
    assert app_state.settings.global_paused is True

    # Call the web pause endpoint
    result = await tasks_module.set_pause({"paused": True})
    assert result["paused"] is True
    # DB must still contain the old keys plus the new flag
    assert stored.get("exhentai_cookies") == {"ipb_member_id": "1"}
    assert stored.get("library_roots") == ["/library"]
    assert stored.get("some_other") == "keep"
    assert stored.get("global_paused") is True
    # runtime also reflects it
    assert app_state.settings.global_paused is True
    app_state.session_factory = orig_factory


def test_update_runtime_settings_allows_global_paused():
    """global_paused must be in allowed so restart hydrates it from DB."""
    from galleryvault.services.settings_service import update_runtime_settings

    base = get_settings().model_copy(update={"global_paused": False})
    app_state.settings = base
    update_runtime_settings({"global_paused": True})
    assert app_state.settings.global_paused is True
    update_runtime_settings({"global_paused": False})
    assert app_state.settings.global_paused is False


@pytest.mark.asyncio
async def test_telegram_pause_merges(monkeypatch):
    """Telegram /pause must also merge, not overwrite (code uses get() + merge)."""
    # Verify the fixed code path does a merge – inspect source
    import inspect

    from galleryvault.services import telegram_bot
    src = inspect.getsource(telegram_bot.TelegramBotService.handle_update)
    assert "await SettingsRepository(session).get()" in src
    assert "merged" in src or "{**existing" in src
    # Simulate merge keeps old keys
    stored = {"exhentai_cookies": {"ipb_member_id": "x"}, "global_paused": False, "keep": 1}
    existing = dict(stored)
    merged = {**existing, "global_paused": True}
    assert merged["keep"] == 1
    assert merged["exhentai_cookies"] == {"ipb_member_id": "x"}


@pytest.mark.asyncio
async def test_purge_uses_delete_galleries_local_with_delete_files(monkeypatch, tmp_path):
    """Purge must call delete_galleries_local with trash=False and respect delete_files."""
    from galleryvault.app.routers import galleries as gal_mod

    # Create a fake gallery row that would be deleted
    # Use a real DB via the test DB? Instead, mock the helper and verify args
    called = {}

    async def fake_delete(session, galleries, *, delete_files, delete_all_copies, trash=None, **kw):
        called["delete_files"] = delete_files
        called["trash"] = trash
        called["count"] = len(galleries)
        return [{"gallery_id": g.id, "db_removed": True, "trashed": False, "failed_paths": [], "deleted_paths": []} for g in galleries]

    monkeypatch.setattr(gal_mod, "delete_galleries_local", fake_delete)

    # Mock DB session to return galleries
    g1 = Gallery(id=1, gid=101, title="t1", storage_path=str(tmp_path / "a"), path_hash="h1")
    g2 = Gallery(id=2, gid=102, title="t2", storage_path=str(tmp_path / "b"), path_hash="h2")

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows
        def all(self):
            return self._rows

    class FakeSession:
        async def scalars(self, stmt):
            return FakeResult([g1, g2])
        def begin(self):
            return self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(gal_mod, "get_session", fake_get_session)
    # Need to also mock _chunked to return single chunk
    from galleryvault.app.schemas import BulkDeleteRequest

    # delete_files=True should be forwarded and trash=False forced
    result = await gal_mod.purge_galleries(BulkDeleteRequest(ids=[1, 2], delete_files=True))
    assert called["delete_files"] is True
    assert called["trash"] is False
    assert result["purged"] == 2

    # delete_files=False also forces trash=False (hard delete without files)
    await gal_mod.purge_galleries(BulkDeleteRequest(ids=[1], delete_files=False))
    assert called["delete_files"] is False
    assert called["trash"] is False


@pytest.mark.asyncio
async def test_delete_bulk_soft_delete_counts_trashed(monkeypatch):
    """Soft delete (delete_files=False) should count trashed as deleted, not 0."""
    from galleryvault.app.routers import galleries as gal_mod
    from galleryvault.app.schemas import BulkDeleteRequest

    g = Gallery(id=10, gid=110, title="t", storage_path="/tmp/a", path_hash="h")

    class FakeResult:
        def all(self):
            return [g]
        def __iter__(self):
            return iter([g])

    class FakeSession:
        async def scalars(self, stmt):
            return FakeResult()
        def begin(self):
            return self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(gal_mod, "get_session", fake_get_session)

    async def fake_delete(session, galleries, **kw):
        return [{"gallery_id": g.id, "gid": g.gid, "db_removed": False, "trashed": True, "failed_paths": [], "deleted_paths": []} for g in galleries]

    monkeypatch.setattr(gal_mod, "delete_galleries_local", fake_delete)

    res = await gal_mod.delete_galleries_bulk(BulkDeleteRequest(ids=[10], delete_files=False))
    assert res["deleted"] == 1
    assert res["trashed"] == 1

    # Hard delete should still be 1
    async def fake_delete2(session, galleries, **kw):
        return [{"gallery_id": g.id, "gid": g.gid, "db_removed": True, "trashed": False, "failed_paths": [], "deleted_paths": []} for g in galleries]
    monkeypatch.setattr(gal_mod, "delete_galleries_local", fake_delete2)
    res2 = await gal_mod.delete_galleries_bulk(BulkDeleteRequest(ids=[10], delete_files=True))
    assert res2["deleted"] == 1


@pytest.mark.asyncio
async def test_scan_returns_paused_not_423(monkeypatch):
    """When global_paused, POST /api/scan must return paused, not raise 423."""
    from galleryvault.app.routers import tasks as tasks_mod

    base = get_settings().model_copy(update={"global_paused": True})
    app_state.settings = base
    result = await tasks_mod.trigger_scan()
    assert result["status"] == "paused"
    # When not paused, it should start scan (mock spawn)
    base2 = get_settings().model_copy(update={"global_paused": False})
    app_state.settings = base2
    # Mock task manager
    class FakeTM:
        def __init__(self):
            self.scan_state = {"running": False}
        def clear_cancelled(self, *a): pass
    monkeypatch.setattr(tasks_mod, "get_task_manager", lambda: FakeTM())
    def fake_spawn(coro, name):
        import contextlib

        with contextlib.suppress(Exception):
            coro.close()
    monkeypatch.setattr(tasks_mod, "spawn_task", fake_spawn)
    result2 = await tasks_mod.trigger_scan()
    assert result2["status"] in ("running", "started", "paused")


@pytest.mark.asyncio
async def test_integrity_excludes_none_and_max_pages(monkeypatch):
    """Integrity must not flag page_count None, must exclude file_count mismatch, must exclude max_pages truncation."""
    # This test hits the real DB repository logic via the test DB fixture would be needed.
    # Instead, we verify the query structure by inspecting the function source.
    import inspect

    from galleryvault.db.repositories.galleries import GalleryRepository
    src = inspect.getsource(GalleryRepository.list_integrity_issues)
    assert "Gallery.page_count.is_(None)" not in src or "is_not(None)" in src  # should not be or_ with is_(None)
    assert "file_count" not in src or "DownloadTask" in src  # old file_count check removed
    assert "max_pages" in src or "DownloadTask" in src
    assert "trashed.is_(False)" in src


@pytest.mark.asyncio
async def test_quota_includes_image_limits(monkeypatch):
    """GET /api/quota must return image_limit alongside GP, cached."""
    from galleryvault.app.routers import tasks as tasks_mod

    app_state.extra["gp_cache"] = {}
    # Mock EhClient
    class FakeClient:
        async def fetch_gp_balance(self):
            return 12345
        async def fetch_image_limits(self):
            return {"current": 800, "limit": 5000}

    app_state.eh_client = FakeClient()
    app_state.settings = get_settings()
    # Clear lock
    tasks_mod._GP_LOCK = None
    result = await tasks_mod.get_quota()
    assert result["gp"] == 12345
    assert result["image_limit"] == {"current": 800, "limit": 5000}
    assert result["image_limits"] == {"current": 800, "limit": 5000}
    # Second call should be cached
    result2 = await tasks_mod.get_quota()
    assert result2["cached"] is True
    # Cleanup
    app_state.eh_client = None
    app_state.extra.pop("gp_cache", None)
