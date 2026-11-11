"""Audit: media duration probes live in ``media_probe`` and ``galleries`` re-exports them.

The pure helpers were moved out of the router module; every pre-split caller
(``galleries`` itself and ``test_gallery_meta``) must keep working through the
re-export, and the probe module must stay importable without FastAPI/SQLAlchemy.
"""

from __future__ import annotations

import io
import subprocess
import sys

from galleryvault.app.routers import galleries, media_probe

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
