"""Audit: media helpers/endpoints live in their own modules and are re-exported.

``media_probe`` owns the pure duration probes; ``galleries_media`` owns the page
streaming / page meta / CBZ export endpoints. Every pre-split caller (``galleries``
itself and the endpoint tests) must keep working through those re-exports, and the
moved handlers must keep resolving test-patched helpers from ``galleries`` at call
time. ``media_probe`` must stay importable without FastAPI/SQLAlchemy.
"""

from __future__ import annotations

import io
import subprocess
import sys

import pytest

from galleryvault.app.routers import galleries, galleries_media, media_probe


class _Sentinel(Exception):
    """Raised by fake lookups to prove the moved handler reached them."""

_EXPECTED_EXPORTS = (
    "_fast_parse_gif_duration",
    "_fast_parse_webp_duration",
    "_inspect_image_meta",
    "_skip_stream_bytes",
    "_skip_subblocks",
)


def test_galleries_reexports_every_probe_helper() -> None:
    missing = [name for name in _EXPECTED_EXPORTS if not hasattr(galleries, name)]
    assert missing == []


def test_galleries_reexports_are_the_same_objects() -> None:
    for name in _EXPECTED_EXPORTS:
        assert getattr(galleries, name) is getattr(media_probe, name), name


def test_probe_module_does_not_pull_router_dependencies() -> None:
    for name in ("fastapi", "sqlalchemy", "APIRouter", "BaseModel"):
        assert not hasattr(media_probe, name)
    imported = {getattr(value, "__name__", "") for value in vars(media_probe).values()}
    assert "fastapi" not in imported
    assert "sqlalchemy" not in imported


def test_probe_module_imports_standalone_and_keeps_behaviour() -> None:
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('_media_probe_standalone', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "assert 'fastapi' not in sys.modules, 'media_probe pulled in fastapi'\n"
        "assert 'sqlalchemy' not in sys.modules, 'media_probe pulled in sqlalchemy'\n"
        "assert mod._fast_parse_gif_duration(__import__('io').BytesIO(b'not a gif')) is None\n"
        "assert mod._skip_subblocks(__import__('io').BytesIO(b'\\x00')) is True\n"
        "assert mod._fast_parse_webp_duration(__import__('io').BytesIO(b'not a webp')) is None\n"
        "assert mod._inspect_image_meta(__import__('io').BytesIO(b'nope')) == "
        "{'animated': False, 'duration_ms': 0}\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(media_probe.__file__)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_reexported_probe_helpers_keep_their_behaviour() -> None:
    assert galleries._fast_parse_gif_duration(io.BytesIO(b"not a gif")) is None
    assert galleries._fast_parse_webp_duration(io.BytesIO(b"not a webp")) is None
    assert galleries._inspect_image_meta(io.BytesIO(b"garbage")) == {
        "animated": False,
        "duration_ms": 0,
    }
    assert galleries._skip_stream_bytes(io.BytesIO(b"abc"), 2) is True
    assert galleries._skip_subblocks(io.BytesIO(b"\x00")) is True


_MEDIA_EXPORTS = (
    "get_page",
    "get_page_meta",
    "export_gallery_cbz",
    "_page_media_type",
    "_closing_stream",
    "_meta",
    "_unlink_export",
)

_MEDIA_PATHS = {
    "/api/galleries/{identifier}/export.cbz",
    "/api/galleries/{identifier}/pages/{page_index}",
    "/api/galleries/{identifier}/pages/{page_index}/meta",
}


def _route_paths(router: object) -> list[str]:
    paths: list[str] = []
    for route in getattr(router, "routes", []):
        included = getattr(route, "original_router", None)
        if included is not None:
            paths.extend(_route_paths(included))
        else:
            paths.append(getattr(route, "path", ""))
    return paths


def test_galleries_reexports_every_media_symbol() -> None:
    missing = [name for name in _MEDIA_EXPORTS if not hasattr(galleries, name)]
    assert missing == []


def test_media_reexports_are_the_same_objects() -> None:
    for name in _MEDIA_EXPORTS:
        assert getattr(galleries, name) is getattr(galleries_media, name), name


def test_handlers_are_defined_in_the_media_module() -> None:
    for name in ("get_page", "get_page_meta", "export_gallery_cbz"):
        assert getattr(galleries_media, name).__module__ == galleries_media.__name__


def test_legacy_page_aliases_point_at_media_handlers() -> None:
    assert galleries.gallery_page is galleries_media.get_page
    assert galleries.gallery_page_meta is galleries_media.get_page_meta


def test_media_router_paths_are_included_at_the_tail() -> None:
    assert set(_route_paths(galleries_media.router)) == _MEDIA_PATHS
    assert _MEDIA_PATHS <= set(_route_paths(galleries.router))
    # The include must run after every pre-split route so registration order and
    # ``DELETE /api/galleries/progress`` matching are unchanged.
    last = galleries.router.routes[-1]
    included = getattr(last, "original_router", None)
    if included is not None:
        assert included is galleries_media.router
    else:
        assert getattr(last, "path", "") in _MEDIA_PATHS


def test_media_logger_keeps_the_router_name() -> None:
    assert galleries_media.logger.name == "galleryvault.app.routers.galleries"


def test_gal_returns_the_galleries_module() -> None:
    assert galleries_media._gal() is galleries


def test_page_helpers_keep_their_behaviour() -> None:
    assert galleries._page_media_type("jpg") == "image/jpeg"
    assert galleries._page_media_type("JPE") == "image/jpeg"
    assert galleries._page_media_type("png") == "image/png"
    stream = io.BytesIO(b"page-bytes")
    assert b"".join(galleries._closing_stream(stream)) == b"page-bytes"
    assert stream.closed


async def test_moved_get_page_uses_patched_invoke_gallery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    async def fake_invoke(identifier: int, session: object = None):
        calls.append(identifier)
        raise _Sentinel("patched _invoke_gallery reached")

    monkeypatch.setattr(galleries, "_invoke_gallery", fake_invoke)

    with pytest.raises(_Sentinel):
        await galleries_media.get_page(7, 0, session=object())
    assert calls == [7]


async def test_moved_endpoints_use_patched_gallery_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    async def fake_gallery(identifier: int):
        calls.append(identifier)
        raise _Sentinel("patched _gallery reached")

    monkeypatch.setattr(galleries, "_gallery", fake_gallery)

    with pytest.raises(_Sentinel):
        await galleries_media.get_page(11, 2, session=object())
    with pytest.raises(_Sentinel):
        await galleries_media.get_page_meta(11, 2, session=object())
    with pytest.raises(_Sentinel):
        await galleries_media.export_gallery_cbz(11, session=object())
    assert calls == [11, 11, 11]


