"""Regression tests for atomic page writes and resume-time image validation."""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from PIL import Image as PILImage

from galleryvault.services import downloader
from galleryvault.services.downloader import (
    _existing_page_file,
    _verify_image_file,
    _write_page_atomic,
)


def _jpeg_bytes(size: tuple[int, int] = (128, 128)) -> bytes:
    """Return a real JPEG whose random pixels keep it comfortably above 512 bytes."""
    width, height = size
    image = PILImage.frombytes(
        "RGB", (width, height), os.urandom(width * height * 3)
    )
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def test_truncated_jpeg_is_not_accepted_as_existing_page(tmp_path: Path) -> None:
    data = _jpeg_bytes()
    truncated = data[: len(data) - 200]
    assert len(truncated) > 512
    assert b"\xff\xd9" not in truncated[-1024:]

    page = tmp_path / "00000001.jpg"
    page.write_bytes(truncated)

    assert _verify_image_file(page) is False
    assert _existing_page_file(tmp_path, 0) is None


def test_valid_page_file_is_accepted(tmp_path: Path) -> None:
    page = tmp_path / "00000001.jpg"
    page.write_bytes(_jpeg_bytes())

    assert _verify_image_file(page) is True
    assert _existing_page_file(tmp_path, 0) == page


def test_complete_partial_leftover_is_not_resumed_as_page(tmp_path: Path) -> None:
    """Crash after fsync but before replace leaves a full ``.partial``; never a page."""
    leftover = tmp_path / "00000001.jpg.abc123.partial"
    leftover.write_bytes(_jpeg_bytes())

    assert _existing_page_file(tmp_path, 0) is None

    page = tmp_path / "00000001.jpg"
    page.write_bytes(_jpeg_bytes())
    assert _existing_page_file(tmp_path, 0) == page


def test_write_page_atomic_round_trips_without_partial_leftover(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "00000001.jpg"
    data = _jpeg_bytes()

    _write_page_atomic(dest, data)

    assert dest.read_bytes() == data
    assert list(tmp_path.glob("*.partial")) == []


def test_write_page_atomic_failure_leaves_no_target_and_cleans_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "00000001.jpg"

    def failing_fsync(fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(downloader.os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="fsync failed"):
        _write_page_atomic(dest, _jpeg_bytes())

    assert not dest.exists()
    assert list(tmp_path.glob("*.partial")) == []
