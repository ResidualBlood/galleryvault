"""Cold archive path, sidecar and root-selection helpers."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import or_

from ...db.models import Gallery
from ...metadata.sidecar import build_galleryvault_json as _build_galleryvault_json
from ...metadata.sidecar import normalize_tags
from ...scanners.ehviewer import strip_gid_prefix
from ...storage_paths import resolve_archive_roots
from ._util import logger, truncate_utf8

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_title(title: str | None) -> str:
    """Sanitize title for directory and filename paths."""
    base = (title or "").strip()
    base = _UNSAFE_NAME.sub("_", base).strip(" .")
    return base or "gallery"


def cold_partition(gid: int | None = None, stable: str | None = None) -> tuple[str, str]:
    """Compute (hh, ii) directory hash components.

    For gid: hh/ii = sha256(str(gid))[:4].
    For ungid: derived from sha256 of stable (or stable hex prefix if already 64-hex).
    """
    if gid is not None:
        digest = hashlib.sha256(str(gid).encode("utf-8")).hexdigest()
    elif stable:
        stable_str = str(stable).strip()
        if len(stable_str) == 64 and all(c in "0123456789abcdefABCDEF" for c in stable_str):
            digest = stable_str.lower()
        else:
            digest = hashlib.sha256(stable_str.encode("utf-8")).hexdigest()
    else:
        raise ValueError("Either gid or stable must be provided for cold partition")
    return digest[:2], digest[2:4]


def compute_cold_path(
    cold_root: Path | str,
    *,
    is_cbz: bool,
    gid: int | None = None,
    title: str | None = None,
    stable: str | None = None,
) -> Path:
    """Calculate cold archive destination path.

    - gid + cbz: {cold}/cbz/{hh}/{ii}/{gid}-{safe_title}.cbz
    - gid + dir: {cold}/dir/{hh}/{ii}/{gid}
    - ungid + cbz: {cold}/ungid/{hh}/{ii}/{stable}-{safe_title}.cbz
    - ungid + dir: {cold}/ungid/{hh}/{ii}/{stable}-{safe_title}
    """
    root = Path(cold_root).resolve()
    hh, ii = cold_partition(gid=gid, stable=stable)
    cleaned_title = strip_gid_prefix(title or "", gid) if gid is not None else (title or "")
    safe = safe_title(cleaned_title)

    if gid is not None:
        if is_cbz:
            filename = truncate_utf8(f"{gid}-{safe}", 243)
            return root / "cbz" / hh / ii / f"{filename}.cbz"
        return root / "dir" / hh / ii / str(gid)

    if not stable:
        raise ValueError("stable (path_hash) is required when gid is None")
    if is_cbz:
        filename = truncate_utf8(f"{stable}-{safe}", 243)
        return root / "ungid" / hh / ii / f"{filename}.cbz"
    filename = truncate_utf8(f"{stable}-{safe}", 247)
    return root / "ungid" / hh / ii / filename


def build_galleryvault_json(
    gid: int | None = None,
    token: str | None = None,
    tags: Sequence[dict[str, Any] | str] | None = None,
    p_tokens: Sequence[str | None] | None = None,
    title: str | None = None,
    title_jpn: str | None = None,
    category: str | None = None,
    quality: str | None = None,
    *,
    uploader: str | None = None,
    posted: Any | None = None,
    rating: float | None = None,
    file_count: int | None = None,
    file_size: int | None = None,
    site: str | None = None,
    extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> bytes:
    """Generate .galleryvault.json content using the unified sidecar builder."""
    return _build_galleryvault_json(
        gid=gid,
        token=token,
        tags=tags,
        p_tokens=p_tokens,
        title=title,
        title_jpn=title_jpn,
        category=category,
        quality=quality,
        uploader=uploader,
        posted=posted,
        rating=rating,
        file_count=file_count,
        file_size=file_size,
        site=site,
        extra=extra,
        **kwargs,
    )


def build_comic_info_xml(
    title: str | None,
    page_count: int,
    tags: Sequence[dict[str, Any] | str] | None = None,
    writer: str | None = None,
    web: str | None = None,
) -> bytes:
    """Generate ComicInfo.xml content."""
    root = ElementTree.Element("ComicInfo")
    if title:
        el = ElementTree.SubElement(root, "Title")
        el.text = title
    if page_count:
        el = ElementTree.SubElement(root, "PageCount")
        el.text = str(page_count)

    normalized = normalize_tags(tags)
    if not writer:
        artists = [t["name"] for t in normalized if t["namespace"] == "artist"]
        if artists:
            writer = ", ".join(artists)
    if writer:
        el = ElementTree.SubElement(root, "Writer")
        el.text = writer

    if normalized:
        genre_str = ", ".join(
            f"{t['namespace']}:{t['name']}" if t["namespace"] != "misc" else t["name"]
            for t in normalized
        )
        el = ElementTree.SubElement(root, "Genre")
        el.text = genre_str

    if web:
        el = ElementTree.SubElement(root, "Web")
        el.text = web

    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _normalize_root_prefix(root: Path | str) -> str:
    """Normalize a resolved cold root to a path prefix without a trailing slash."""
    normalized = os.path.normpath(str(root))
    return normalized


def _cold_path_filter(roots: Sequence[Path | str]) -> Any | None:
    """Build the SQL predicate equivalent to ``is_under_cold`` for stored paths.

    ``is_under_cold`` resolves one path on the filesystem (following symlinks);
    doing that per DB row is not viable for large libraries.  Stored
    ``storage_path`` values are already absolute resolved paths, so the same
    containment can be expressed as ``path == root`` or ``path LIKE root/%``
    with the separator included: ``/Archive`` must not match ``/Archive2``.
    SQLAlchemy escapes ``%``/``_`` in the prefix (``autoescape``).
    """
    conditions: list[Any] = []
    for root in roots:
        base = _normalize_root_prefix(root)
        if base == os.sep:
            # Every absolute stored path lives under the filesystem root.
            conditions.append(Gallery.storage_path.startswith(os.sep))
            continue
        conditions.append(
            or_(
                Gallery.storage_path == base,
                Gallery.storage_path.startswith(base + os.sep, autoescape=True),
            )
        )
    if not conditions:
        return None
    return or_(*conditions)


def select_archive_root(
    required_bytes: int,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
) -> tuple[Path | None, int]:
    """Select the archive root with the largest free disk space satisfying free >= required_bytes.

    Returns (selected_root, max_free_space). If no root qualifies, returns (None, 0).
    """
    roots = resolve_archive_roots(archive_roots=archive_roots, cold_root=cold_root)
    best_root: Path | None = None
    best_free = -1

    for root in roots:
        try:
            probe_dir = root
            while not probe_dir.exists() and probe_dir.parent != probe_dir:
                probe_dir = probe_dir.parent
            free_space = shutil.disk_usage(probe_dir).free
            if free_space >= required_bytes and free_space > best_free:
                best_free = free_space
                best_root = root
        except OSError as exc:
            logger.warning("Failed to check disk usage on %s: %s", root, exc)

    return best_root, max(0, best_free)
