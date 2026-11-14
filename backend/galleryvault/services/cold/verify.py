"""Cold archive copy verification helpers."""

from __future__ import annotations

import os
import zipfile
from collections.abc import Sequence
from pathlib import Path

from ...scanners.ehviewer import IMAGE_EXTENSIONS
from ._util import _IGNORED_NAMES, logger
from .pack import _collect_pages_from_dir
from .paths import cold_partition


def _validate_cold_destination(dest_path: Path) -> bool:
    """Validate that an existing cold archive destination is healthy and non-empty."""
    try:
        if not dest_path.exists():
            return False
        if dest_path.is_file() and dest_path.suffix.lower() in {".cbz", ".zip"}:
            if dest_path.stat().st_size <= 0:
                return False
            if not zipfile.is_zipfile(dest_path):
                return False
            with zipfile.ZipFile(dest_path, "r") as zf:
                if zf.testzip() is not None:
                    return False
                return any(
                    not n.startswith(".")
                    and Path(n).suffix.lower() in IMAGE_EXTENSIONS
                    and Path(n).name.lower() not in _IGNORED_NAMES
                    for n in zf.namelist()
                )
        elif dest_path.is_dir():
            return any(
                p.is_file()
                and not p.name.startswith(".")
                and p.suffix.lower() in IMAGE_EXTENSIONS
                and p.name.lower() not in _IGNORED_NAMES
                for p in dest_path.rglob("*")
            )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Validation failed for cold archive destination %s: %s", dest_path, exc)
        return False


def _count_zip_image_pages(path: Path) -> int | None:
    """Count image pages in a zip; ``None`` when unreadable or CRC-broken."""
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        if not zipfile.is_zipfile(path):
            return None
        with zipfile.ZipFile(path, "r") as zf:
            if zf.testzip() is not None:
                return None
            return sum(
                1
                for n in zf.namelist()
                if not n.startswith(".")
                and Path(n).suffix.lower() in IMAGE_EXTENSIONS
                and Path(n).name.lower() not in _IGNORED_NAMES
            )
    except (OSError, zipfile.BadZipFile):
        return None


def _count_dir_image_pages(path: Path) -> int | None:
    """Count image pages in a directory tree; ``None`` when unreadable."""
    try:
        if not path.is_dir():
            return None
        return sum(
            1
            for p in path.rglob("*")
            if p.is_file()
            and not p.name.startswith(".")
            and p.suffix.lower() in IMAGE_EXTENSIONS
            and p.name.lower() not in _IGNORED_NAMES
        )
    except OSError:
        return None


def _count_source_image_pages(source: Path) -> int | None:
    """Count image pages in a source directory or cbz; ``None`` when unknown."""
    try:
        if source.is_dir():
            return len(_collect_pages_from_dir(source))
        if source.is_file() and source.suffix.lower() in {".cbz", ".zip"}:
            return _count_zip_image_pages(source)
    except OSError:
        return None
    return None


def cold_copy_covers_source(source: Path, dest: Path) -> bool:
    """Return True only when ``dest`` provably covers every ``source`` page.

    Fail-closed guard shared by destination adoption and source purging: the cold
    copy must exist and be readable, pass zip CRC checks, contain real image pages
    (a metadata-only directory does not count), and have at least as many pages as
    the source. Unknown page counts never authorize deleting the only source.
    """
    try:
        if not dest.exists() or not os.access(dest, os.R_OK):
            return False
    except OSError:
        return False

    source_pages = _count_source_image_pages(source)
    if source_pages is None or source_pages <= 0:
        return False

    if dest.is_file():
        dest_pages = _count_zip_image_pages(dest)
    else:
        dest_pages = _count_dir_image_pages(dest)
    if dest_pages is None or dest_pages <= 0:
        return False
    return dest_pages >= source_pages


def _is_online_cold_root(root: Path) -> bool:
    """Return True when a cold-storage root exists, is a directory and is readable."""
    try:
        return root.is_dir() and os.access(root, os.R_OK)
    except OSError:
        return False


def _check_physically_archived(
    gid: int,
    cold_roots: Sequence[Path],
    *,
    source: Path | None = None,
) -> bool:
    """Check if a gallery GID physically exists in cold storage (cbz or dir).

    When ``source`` is given, a candidate only counts when
    :func:`cold_copy_covers_source` proves it covers the source pages.
    """
    try:
        hh, ii = cold_partition(gid=gid)
    except Exception:  # noqa: BLE001
        return False

    def _is_matching_cbz(path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 0:
                return False
        except OSError:
            return False
        name = path.name
        if not (name == f"{gid}.cbz" or (name.startswith(f"{gid}-") and name.endswith(".cbz"))):
            return False
        return zipfile.is_zipfile(path)

    def _is_matching_dir(path: Path) -> bool:
        # A directory with only metadata (e.g. ComicInfo.xml) is not a cold copy.
        pages = _count_dir_image_pages(path)
        return pages is not None and pages > 0

    def _covers(path: Path) -> bool:
        if source is None:
            return True
        return cold_copy_covers_source(source, path)

    for c_root in cold_roots:
        # 1. Standard partition path: cbz/hh/ii/{gid}-*.cbz or {gid}.cbz
        cbz_part_dir = c_root / "cbz" / hh / ii
        if cbz_part_dir.is_dir():
            try:
                for f in cbz_part_dir.iterdir():
                    if _is_matching_cbz(f) and _covers(f):
                        return True
            except OSError:
                pass

        # 2. Standard partition path: dir/hh/ii/{gid}
        dir_part_target = c_root / "dir" / hh / ii / str(gid)
        if _is_matching_dir(dir_part_target) and _covers(dir_part_target):
            return True

        # 3. Direct fallback path: cbz/{gid}-*.cbz or cbz/{gid}.cbz
        cbz_direct_dir = c_root / "cbz"
        if cbz_direct_dir.is_dir():
            try:
                for f in cbz_direct_dir.iterdir():
                    if _is_matching_cbz(f) and _covers(f):
                        return True
            except OSError:
                pass

        # 4. Direct fallback path: dir/{gid}
        dir_direct_target = c_root / "dir" / str(gid)
        if _is_matching_dir(dir_direct_target) and _covers(dir_direct_target):
            return True

    return False
