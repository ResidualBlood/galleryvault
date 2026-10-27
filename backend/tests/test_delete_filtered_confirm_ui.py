"""Structured 409 contract for the filtered-delete confirmation guard.

The frontend (``frontend/assets/views/library.js``) recognises a large delete by
``detail.code == "CONFIRM_REQUIRED"`` and resends the same payload with
``confirm=true`` and ``match_count=<matched>``.  These tests pin that contract
plus the other 409 paths that must keep their plain-string detail.
"""

import pytest
from fastapi.encoders import jsonable_encoder

from galleryvault.app.schemas import FilteredDeleteRequest
from galleryvault.db.models import Gallery


class _StubRequest:
    """Minimal ``Request`` stand-in exposing only the JSON guard fields."""

    def __init__(self, payload: dict | None = None):
        self._payload = payload or {}

    async def json(self):
        return self._payload


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


def _rows(count: int) -> list[Gallery]:
    return [
        Gallery(id=i, gid=5000 + i, title=f"g{i}", storage_path="")
        for i in range(1, count + 1)
    ]


def _install_repo(monkeypatch, rows):
    from galleryvault.app.routers import galleries as galleries_module

    class Repo:
        def __init__(self, session):
            self.session = session

        async def resolve_exact_tags(self, tags):
            return {}

        async def list_page(self, page, page_size, *args, **kwargs):
            start = (page - 1) * page_size
            return len(rows), rows[start : start + page_size]

    monkeypatch.setattr(galleries_module, "GalleryRepository", Repo)
    return galleries_module


@pytest.fixture
def _delete_setup(monkeypatch):
    from galleryvault.app.state import app_state as state

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

        async def scalars(self, statement):
            return _Rows([])

    orig_factory = state.session_factory
    state.session_factory = lambda: Session()
    deleted_batches: list[int] = []
    yield deleted_batches
    state.session_factory = orig_factory


def _patch_delete(monkeypatch, module, batches: list[int]):
    async def fake_delete(batch, *args, delete_files=False, delete_all_copies=False, **kw):
        actual = args[0] if args else batch
        batches.append(len(actual))
        return [
            {
                "gallery_id": g if isinstance(g, int) else g.id,
                "gid": getattr(g, "gid", None),
                "db_removed": True,
                "deleted_paths": [],
                "failed_paths": [],
            }
            for g in actual
        ]

    monkeypatch.setattr(module, "delete_galleries_local", fake_delete)


@pytest.mark.asyncio
async def test_large_delete_returns_structured_confirm_required(monkeypatch, _delete_setup):
    from fastapi import HTTPException

    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(250))
    _patch_delete(monkeypatch, module, _delete_setup)

    with pytest.raises(HTTPException) as excinfo:
        await delete_galleries_filtered(FilteredDeleteRequest(favorite=True), _StubRequest())

    exc = excinfo.value
    assert exc.status_code == 409
    body = jsonable_encoder(exc.detail)  # must serialise into the JSON response
    assert body["code"] == "CONFIRM_REQUIRED"
    assert body["matched"] == 250
    assert body["threshold"] == 200
    assert "confirm=true" in body["message"]
    assert "match_count=250" in body["message"]
    assert _delete_setup == []


@pytest.mark.asyncio
async def test_confirm_and_match_count_resend_deletes(monkeypatch, _delete_setup):
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(250))
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(favorite=True, delete_files=True)
    result = await delete_galleries_filtered(
        body, _StubRequest({"confirm": True, "match_count": 250})
    )

    assert result["matched"] == 250
    assert result["deleted"] == 250
    assert _delete_setup == [250]


@pytest.mark.asyncio
async def test_stale_match_count_keeps_string_detail(monkeypatch, _delete_setup):
    from fastapi import HTTPException

    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(250))
    _patch_delete(monkeypatch, module, _delete_setup)

    with pytest.raises(HTTPException) as excinfo:
        await delete_galleries_filtered(
            FilteredDeleteRequest(favorite=True),
            _StubRequest({"confirm": True, "match_count": 240}),
        )

    assert excinfo.value.status_code == 409
    assert isinstance(excinfo.value.detail, str)
    assert "match_count" in excinfo.value.detail
    assert _delete_setup == []


@pytest.mark.asyncio
async def test_over_safe_limit_keeps_string_detail(monkeypatch, _delete_setup):
    from fastapi import HTTPException

    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(5001))
    _patch_delete(monkeypatch, module, _delete_setup)

    with pytest.raises(HTTPException) as excinfo:
        await delete_galleries_filtered(
            FilteredDeleteRequest(favorite=True),
            _StubRequest({"confirm": True, "match_count": 5001}),
        )

    assert excinfo.value.status_code == 409
    assert isinstance(excinfo.value.detail, str)
    assert "safe limit 5000" in excinfo.value.detail
    assert _delete_setup == []
