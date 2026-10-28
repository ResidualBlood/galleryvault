"""B2-D #15: /pages/{i}/meta must not swallow errors and return 200."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import galleries


def _row() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        gid=42,
        token="tok",
        title="Title",
        storage_path="/tmp/gallery",
        storage_type="ehviewer_dir",
        storage_signature=None,
    )


def _page() -> SimpleNamespace:
    return SimpleNamespace(
        page_index=0, member_name="0001.jpg", media_type="jpg", manifest={}
    )


@pytest.fixture
def patched_page(monkeypatch: pytest.MonkeyPatch):
    """Patch gallery lookup and return an installer for the scanner error."""

    monkeypatch.setattr(
        galleries,
        "_invoke_gallery",
        _async_return((_row(), [_page()])),
    )

    def _install(error: BaseException) -> None:
        class _Scanner:
            def open_page(self, meta: object, info: object) -> object:
                raise error

        monkeypatch.setattr(galleries.registry, "for_path", lambda _path: _Scanner())

    return _install


def _async_return(value: object):
    async def _inner(*args: object, **kwargs: object) -> object:
        return value

    return _inner


async def test_page_meta_missing_file_returns_404(patched_page) -> None:
    patched_page(FileNotFoundError("secret path"))
    with pytest.raises(HTTPException) as exc:
        await galleries.get_page_meta(7, 0, session=object())
    assert exc.value.status_code == 404


async def test_page_meta_invalid_path_returns_400(patched_page) -> None:
    patched_page(ValueError("unsafe member"))
    with pytest.raises(HTTPException) as exc:
        await galleries.get_page_meta(7, 0, session=object())
    assert exc.value.status_code == 400


async def test_page_meta_unreadable_returns_500(patched_page) -> None:
    patched_page(OSError("disk on fire"))
    with pytest.raises(HTTPException) as exc:
        await galleries.get_page_meta(7, 0, session=object())
    assert exc.value.status_code == 500
    assert "disk on fire" not in str(exc.value.detail)


async def test_page_meta_missing_page_still_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        galleries, "_invoke_gallery", _async_return((_row(), [_page()]))
    )
    with pytest.raises(HTTPException) as exc:
        await galleries.get_page_meta(7, 9, session=object())
    assert exc.value.status_code == 404


async def test_page_meta_releases_session_before_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class _Session:
        def in_transaction(self) -> bool:
            return True

        async def rollback(self) -> None:
            events.append("rollback")

        async def commit(self) -> None:
            events.append("commit")

    class _Scanner:
        def open_page(self, meta: object, info: object) -> object:
            events.append("open")
            import io

            return io.BytesIO(b"corrupted")

    monkeypatch.setattr(
        galleries, "_invoke_gallery", _async_return((_row(), [_page()]))
    )
    monkeypatch.setattr(galleries.registry, "for_path", lambda _path: _Scanner())

    result = await galleries.get_page_meta(7, 0, session=_Session())

    assert result == {"animated": False, "duration_ms": 0}
    assert events.index("rollback") < events.index("open")
