"""Small filesystem helpers shared by cache writers.

The only public helper is :func:`write_atomic`: write bytes through a unique
temporary file in the destination directory and publish it with one
``Path.replace()``.  Concurrent writers for the same target therefore never
share a temp path, and readers never observe a half-written file.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(
    path: Path,
    data: bytes,
    *,
    tmp_prefix: str | None = None,
    tmp_suffix: str = ".tmp",
) -> None:
    """Write ``data`` to ``path`` in one rename, via a per-call unique temp file.

    ``tmp_prefix`` defaults to ``<path stem>.``; callers that need a different
    convention (for example ``<full name>.``) pass it explicitly.  The temp
    file always lives in ``path.parent`` so the final ``replace()`` stays a
    same-filesystem rename.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = tmp_prefix if tmp_prefix is not None else f"{path.stem}."
    # Imported as a module and looked up at call time: tests monkeypatch
    # ``tempfile.mkstemp`` and expect the patch to take effect here.
    fd, tmp_name = tempfile.mkstemp(
        prefix=prefix, suffix=tmp_suffix, dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
