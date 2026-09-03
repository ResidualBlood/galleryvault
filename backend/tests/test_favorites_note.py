from types import SimpleNamespace

import pytest

from galleryvault.app.schemas import FavoriteNoteRequest
from galleryvault.app.state import app_state
from galleryvault.services.eh_client import EhClientError


@pytest.mark.asyncio
async def test_favorite_note_cloud_failure_does_not_write_local(monkeypatch) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class BoomClient:
        async def add_favorite(self, *args, **kwargs):
            raise EhClientError("cloud down")

    class Repo:
        def __init__(self, session):
            self.session = session
            self.updated = 0

        async def item_for_gid(self, gid):
            return SimpleNamespace(token="tok", favcat=2, gid=gid)

        async def update_note(self, gid, note, favcat=None):
            self.updated += 1
            return 1

    updates = {"n": 0}

    class Session:
        async def begin(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def scalar(self, statement):
            return None

    async def fake_session():
        yield Session()

    orig = app_state.eh_client
    app_state.eh_client = BoomClient()
    monkeypatch.setattr(fav_mod, "get_session", fake_session)
    monkeypatch.setattr(fav_mod, "FavoritesRepository", Repo)

    def fake_record(*args, **kwargs):
        updates["n"] += 1

    monkeypatch.setattr(fav_mod, "get_task_manager", lambda: SimpleNamespace(
        record_task=fake_record, persist_history=lambda: None
    ))
    monkeypatch.setattr(fav_mod, "spawn_task", lambda *a, **k: None)
    try:
        result = await fav_mod.favorites_set_note(
            FavoriteNoteRequest(gid=11, note="secret", token="tok", favcat=2)
        )
        assert result["cloud_ok"] is False
        assert result["local_updated"] == 0
        assert result["note"] is None
    finally:
        app_state.eh_client = orig
