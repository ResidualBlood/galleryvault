"""Characterization tests for ``galleryvault.fsutil.write_atomic``.

The helper replaces three near-identical "unique temp file + ``replace()``"
writers (favorites cover cache, online image cache and the favorites router).
These tests pin the behaviour they all relied on: temp file naming/directory,
one rename, no fsync, private permissions, failure cleanup and per-call
uniqueness under concurrency.  The three old function names stay as thin
wrappers, so their naming conventions are pinned here too.
"""

from __future__ import annotations

import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from galleryvault import fsutil


def _record_mkstemp(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[Path, dict[str, Any]]]
) -> None:
    real_mkstemp = fsutil.tempfile.mkstemp

    def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)
        calls.append((Path(name), kwargs))
        return fd, name

    monkeypatch.setattr(fsutil.tempfile, "mkstemp", recording_mkstemp)


def test_write_atomic_creates_parents_and_publishes_bytes(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "cover.img"

    fsutil.write_atomic(target, b"payload")

    assert target.read_bytes() == b"payload"
    assert [entry.name for entry in target.parent.iterdir()] == ["cover.img"]


def test_write_atomic_uses_stem_prefix_in_target_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, dict[str, Any]]] = []
    _record_mkstemp(monkeypatch, calls)
    target = tmp_path / "gallery-1" / "cover.img"

    fsutil.write_atomic(target, b"x")

    assert len(calls) == 1
    tmp_path_created, kwargs = calls[0]
    assert tmp_path_created.parent == target.parent
    assert kwargs["prefix"] == "cover."
    assert kwargs["suffix"] == ".tmp"
    assert kwargs["dir"] == str(target.parent)
    assert not tmp_path_created.exists()


def test_write_atomic_accepts_explicit_temp_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, dict[str, Any]]] = []
    _record_mkstemp(monkeypatch, calls)
    target = tmp_path / "cover.img"

    fsutil.write_atomic(target, b"x", tmp_prefix=f"{target.name}.")

    assert calls[0][1]["prefix"] == "cover.img."


def test_write_atomic_does_not_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(fsutil.os, "fsync", lambda fd: calls.append(fd))

    fsutil.write_atomic(tmp_path / "page.bin", b"x")

    assert calls == []


def test_write_atomic_temp_file_permissions_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    real_mkstemp = fsutil.tempfile.mkstemp

    def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)
        seen.append(stat.S_IMODE(os.stat(name).st_mode))
        return fd, name

    monkeypatch.setattr(fsutil.tempfile, "mkstemp", recording_mkstemp)

    fsutil.write_atomic(tmp_path / "page.bin", b"x")

    assert seen == [0o600]


def test_write_atomic_removes_temp_file_and_keeps_old_bytes_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "cover.img"
    target.write_bytes(b"old")

    def failing_fdopen(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr(fsutil.os, "fdopen", failing_fdopen)

    with pytest.raises(OSError, match="disk full"):
        fsutil.write_atomic(target, b"new")

    assert target.read_bytes() == b"old"
    assert [entry.name for entry in tmp_path.iterdir()] == ["cover.img"]


def test_write_atomic_uses_unique_temp_file_per_concurrent_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names: list[str] = []
    barrier = threading.Barrier(2, timeout=10)
    real_mkstemp = fsutil.tempfile.mkstemp

    def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)
        names.append(name)
        barrier.wait()
        return fd, name

    monkeypatch.setattr(fsutil.tempfile, "mkstemp", recording_mkstemp)
    target = tmp_path / "out" / "42.img"
    payloads = [b"a" * 1024, b"b" * 1024]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(fsutil.write_atomic, target, payload) for payload in payloads]
        errors = [exc for future in futures if (exc := future.exception()) is not None]

    assert errors == []
    assert len(set(names)) == 2
    assert target.read_bytes() in payloads
    assert list(target.parent.glob("*.tmp")) == []


def test_cover_cache_wrapper_uses_full_name_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.services.favorites import cover_cache

    calls: list[tuple[Path, dict[str, Any]]] = []
    _record_mkstemp(monkeypatch, calls)
    target = tmp_path / "remote-covers" / "42.img"

    cover_cache._write_cover_file(target, b"cover")

    assert target.read_bytes() == b"cover"
    assert calls[0][1]["prefix"] == "42.img."
    assert calls[0][1]["dir"] == str(target.parent)


def test_online_image_cache_wrapper_uses_stem_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.services import online_image_cache

    calls: list[tuple[Path, dict[str, Any]]] = []
    _record_mkstemp(monkeypatch, calls)
    target = tmp_path / "online" / "page.img"

    online_image_cache._write_atomic(target, b"page")

    assert target.read_bytes() == b"page"
    assert calls[0][1]["prefix"] == "page."


def test_router_cover_wrapper_uses_stem_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.routers import favorites as favorites_router

    calls: list[tuple[Path, dict[str, Any]]] = []
    _record_mkstemp(monkeypatch, calls)
    target = tmp_path / "cache" / "cover.img"

    favorites_router._write_cover_atomic(target, b"cover")

    assert target.read_bytes() == b"cover"
    assert calls[0][1]["prefix"] == "cover."
