from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.state import app_state
from ..config import get_settings
from ..db.models import DownloadTask, Gallery, GalleryPage, GalleryTag, Tag
from ..db.repositories.base import path_hash
from ..logging import log_extra
from ..scanners.ehviewer import IMAGE_EXTENSIONS, natural_key, parse_spider_info, strip_gid_prefix
from .downloader import _truncate_utf8
from .export_cbz import ZIP_STORED, page_archive_name

logger = logging.getLogger(__name__)

COLD_ARCHIVE_MAX_CBZ_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
COLD_ARCHIVE_MAX_CBZ_PAGES = 500

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_GID_STEM = re.compile(r"^(\d+)(?:-(.*))?$")

_IGNORED_NAMES = {
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    ".ehviewer",
    "metadata",
    "metadata.json",
    "comicinfo.xml",
    ".galleryvault.json",
    "thumbs.db",
    ".ds_store",
}


class ColdStorageError(Exception):
    """Base exception for cold archive operations."""


class ColdDestinationExistsError(ColdStorageError, FileExistsError):
    """Raised when cold storage destination already exists."""

    def __init__(self, message: str = "", dest_path: Path | None = None) -> None:
        super().__init__(message)
        self.dest_path = dest_path


class ColdAlreadyArchivedError(ColdStorageError):
    """Raised when source is already located under the cold storage root."""


def safe_title(title: str | None) -> str:
    """Sanitize title for directory and filename paths."""
    base = (title or "").strip()
    base = _UNSAFE_NAME.sub("_", base).strip(" .")
    return base or "gallery"


def _resolve_base_url(site: str | None = None) -> str:
    """Resolve download source base URL for ComicInfo Web field."""
    if site:
        s = str(site).strip()
        if s.startswith(("http://", "https://")):
            return s.rstrip("/")
        s_lower = s.lower()
        if s_lower in {"exhentai", "ex", "exhentai.org"}:
            return "https://exhentai.org"
        if s_lower in {"e-hentai", "eh", "e-hentai.org"}:
            return "https://e-hentai.org"
    settings = app_state.settings or get_settings()
    configured = getattr(settings, "exhentai_base_url", None)
    if configured:
        return str(configured).strip().rstrip("/")
    return "https://exhentai.org"


def _clear_gallery_thumbs(gallery_id: int) -> None:
    """Clear thumbnail cache directory for a gallery if pages changed."""
    if app_state.thumbnail_service is not None:
        thumb_dir = app_state.thumbnail_service.root / str(gallery_id)
    else:
        settings = app_state.settings or get_settings()
        root = Path(getattr(settings, "thumbnail_cache_dir", "/gv-cache/thumbs"))
        thumb_dir = root / str(gallery_id)

    if thumb_dir.exists():
        try:
            if thumb_dir.is_dir():
                shutil.rmtree(thumb_dir, ignore_errors=True)
            else:
                thumb_dir.unlink(missing_ok=True)
            logger.info("Cleared thumbnail cache for gallery %s at %s", gallery_id, thumb_dir)
        except OSError as exc:
            logger.warning("Failed to clear thumbnail cache for gallery %s: %s", gallery_id, exc)


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
            filename = _truncate_utf8(f"{gid}-{safe}", 243)
            return root / "cbz" / hh / ii / f"{filename}.cbz"
        return root / "dir" / hh / ii / str(gid)

    if not stable:
        raise ValueError("stable (path_hash) is required when gid is None")
    if is_cbz:
        filename = _truncate_utf8(f"{stable}-{safe}", 243)
        return root / "ungid" / hh / ii / f"{filename}.cbz"
    filename = _truncate_utf8(f"{stable}-{safe}", 247)
    return root / "ungid" / hh / ii / filename


def normalize_tags(raw_tags: Sequence[dict[str, Any] | str] | None) -> list[dict[str, str]]:
    """Normalize tags into a list of dicts with namespace and name."""
    if not raw_tags:
        return []
    tags: list[dict[str, str]] = []
    for item in raw_tags:
        if isinstance(item, dict):
            ns = str(item.get("namespace") or "misc").strip()
            name = str(item.get("name") or "").strip()
            if name:
                tags.append({"namespace": ns, "name": name})
        elif isinstance(item, str):
            val = item.strip()
            if not val:
                continue
            if ":" in val:
                ns, name = val.split(":", 1)
                tags.append({"namespace": ns.strip(), "name": name.strip()})
            else:
                tags.append({"namespace": "misc", "name": val})
    return tags


def build_galleryvault_json(
    gid: int | None,
    token: str | None,
    tags: Sequence[dict[str, Any] | str] | None,
    p_tokens: Sequence[str] | None,
    title: str | None = None,
    title_jpn: str | None = None,
    category: str | None = None,
) -> bytes:
    """Generate .galleryvault.json content."""
    clean_title = title or ""
    clean_title_jpn = title_jpn or ""
    if clean_title_jpn.strip().isdigit():
        clean_title_jpn = ""
    data: dict[str, Any] = {
        "gid": gid,
        "token": token or None,
        "title": clean_title,
        "title_jpn": clean_title_jpn,
        "tags": normalize_tags(tags),
        "p_tokens": list(p_tokens or []),
    }
    if category is not None:
        data["category"] = category
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


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


def resolve_archive_roots(
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
) -> list[Path]:
    """Resolve archive roots from parameters or settings with backwards compatibility.

    - If explicit archive_roots are provided, use them.
    - Else if explicit cold_root is provided, wrap in a single-item list.
    - Otherwise, read settings.archive_roots; if empty, read settings.cold_storage_root.
    - Returns resolved, non-empty, deduplicated Path objects.
    """
    candidates: list[str | Path] = []
    if archive_roots is not None:
        candidates = list(archive_roots)
    elif cold_root is not None:
        cr_str = str(cold_root).strip()
        if cr_str:
            candidates = [cr_str]
    else:
        settings = app_state.settings or get_settings()
        roots = getattr(settings, "archive_roots", []) or []
        if not roots:
            cr = (getattr(settings, "cold_storage_root", None) or "").strip()
            if cr:
                roots = [cr]
        candidates = list(roots)

    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        s = str(item).strip()
        if not s:
            continue
        p = Path(s).resolve()
        key = str(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def is_under_cold(
    path: Path | str,
    cold_roots: Path | str | Sequence[Path | str] | None = None,
) -> bool:
    """Check whether a path is already located under any cold storage root."""
    try:
        resolved = Path(path).resolve()
        if cold_roots is None:
            roots = resolve_archive_roots()
        elif isinstance(cold_roots, (Path, str)):
            roots = [Path(cold_roots).resolve()]
        else:
            roots = [Path(r).resolve() for r in cold_roots]
        for c in roots:
            if resolved == c or resolved.is_relative_to(c):
                return True
        return False
    except (ValueError, OSError):
        return False


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


def _check_physically_archived(gid: int, cold_roots: Sequence[Path]) -> bool:
    """Check if a gallery GID physically exists in cold storage (cbz or dir)."""
    try:
        hh, ii = cold_partition(gid=gid)
    except Exception:  # noqa: BLE001
        return False

    def _is_matching_cbz(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        name = path.name
        if not (name == f"{gid}.cbz" or (name.startswith(f"{gid}-") and name.endswith(".cbz"))):
            return False
        return zipfile.is_zipfile(path)

    def _is_matching_dir(path: Path) -> bool:
        if not path.is_dir():
            return False
        try:
            return any(path.iterdir())
        except OSError:
            return False

    for c_root in cold_roots:
        # 1. Standard partition path: cbz/hh/ii/{gid}-*.cbz or {gid}.cbz
        cbz_part_dir = c_root / "cbz" / hh / ii
        if cbz_part_dir.is_dir():
            try:
                for f in cbz_part_dir.iterdir():
                    if _is_matching_cbz(f):
                        return True
            except OSError:
                pass

        # 2. Standard partition path: dir/hh/ii/{gid}
        dir_part_target = c_root / "dir" / hh / ii / str(gid)
        if _is_matching_dir(dir_part_target):
            return True

        # 3. Direct fallback path: cbz/{gid}-*.cbz or cbz/{gid}.cbz
        cbz_direct_dir = c_root / "cbz"
        if cbz_direct_dir.is_dir():
            try:
                for f in cbz_direct_dir.iterdir():
                    if _is_matching_cbz(f):
                        return True
            except OSError:
                pass

        # 4. Direct fallback path: dir/{gid}
        dir_direct_target = c_root / "dir" / str(gid)
        if _is_matching_dir(dir_direct_target):
            return True

    return False


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


def _collect_pages_from_dir(source_dir: Path) -> list[Path]:
    """Collect image pages from a directory sorted by natural key, excluding ignored files."""
    pages: list[Path] = []
    # Check flat directory first
    for item in source_dir.iterdir():
        if not item.is_file() or item.name.startswith("."):
            continue
        if item.name.lower() in _IGNORED_NAMES:
            continue
        if item.suffix.lower() in IMAGE_EXTENSIONS:
            pages.append(item)

    if not pages:
        # Fallback to rglob if nested
        for item in source_dir.rglob("*"):
            if not item.is_file() or item.name.startswith("."):
                continue
            if item.name.lower() in _IGNORED_NAMES:
                continue
            if item.suffix.lower() in IMAGE_EXTENSIONS:
                pages.append(item)

    pages.sort(key=lambda p: natural_key(p.name))
    return pages


def _extract_source_meta(
    source: Path,
    gid: int | None = None,
    token: str | None = None,
    title: str | None = None,
    title_jpn: str | None = None,
    tags: Sequence[dict[str, Any] | str] | None = None,
    p_tokens: Sequence[str] | None = None,
    stable: str | None = None,
    site: str | None = None,
    category: str | None = None,
) -> tuple[int | None, str | None, str, str, list[dict[str, str]], list[str], str, str | None, str | None]:
    """Fill missing metadata from source filesystem artifacts if available."""
    current_gid = gid
    current_token = token
    current_title = title
    current_title_jpn = title_jpn
    if current_title_jpn and str(current_title_jpn).strip().isdigit():
        current_title_jpn = ""
    current_tags = list(normalize_tags(tags))
    current_p_tokens = list(p_tokens or [])
    current_stable = stable
    current_site = site
    current_category = category

    if source.is_dir():
        # Check .galleryvault.json
        gv_path = source / ".galleryvault.json"
        if gv_path.is_file():
            try:
                data = json.loads(gv_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if current_gid is None and data.get("gid") is not None:
                        current_gid = int(data["gid"])
                    if not current_token and data.get("token"):
                        current_token = str(data["token"])
                    if not current_title and data.get("title"):
                        current_title = str(data["title"])
                    if not current_title_jpn and data.get("title_jpn"):
                        tj = str(data["title_jpn"]).strip()
                        if not tj.isdigit():
                            current_title_jpn = str(data["title_jpn"])
                    if not current_tags and data.get("tags"):
                        current_tags = normalize_tags(data["tags"])
                    if not current_p_tokens and data.get("p_tokens"):
                        current_p_tokens = [str(x) for x in data["p_tokens"]]
                    if not current_site and data.get("site"):
                        current_site = str(data["site"])
                    if data.get("category"):
                        current_category = str(data["category"])
            except (json.JSONDecodeError, OSError, ValueError):
                logger.debug("Failed reading .galleryvault.json from %s", source)

        # Check .ehviewer
        eh_path = source / ".ehviewer"
        if eh_path.is_file() and (current_gid is None or not current_token or not current_p_tokens):
            try:
                spider = parse_spider_info(eh_path.read_text(encoding="utf-8"))
                if current_gid is None:
                    current_gid = spider.gid
                if not current_token:
                    current_token = spider.token
                if not current_p_tokens:
                    current_p_tokens = spider.p_tokens
            except (OSError, ValueError):
                logger.debug("Failed reading .ehviewer from %s", source)

    elif source.is_file() and source.suffix.lower() in {".cbz", ".zip"}:
        try:
            with zipfile.ZipFile(source, "r") as zf:
                if ".galleryvault.json" in zf.namelist():
                    data = json.loads(zf.read(".galleryvault.json").decode("utf-8"))
                    if isinstance(data, dict):
                        if current_gid is None and data.get("gid") is not None:
                            current_gid = int(data["gid"])
                        if not current_token and data.get("token"):
                            current_token = str(data["token"])
                        if not current_title and data.get("title"):
                            current_title = str(data["title"])
                        if not current_title_jpn and data.get("title_jpn"):
                            tj = str(data["title_jpn"]).strip()
                            if not tj.isdigit():
                                current_title_jpn = str(data["title_jpn"])
                        if not current_tags and data.get("tags"):
                            current_tags = normalize_tags(data["tags"])
                        if not current_p_tokens and data.get("p_tokens"):
                            current_p_tokens = [str(x) for x in data["p_tokens"]]
                        if not current_site and data.get("site"):
                            current_site = str(data["site"])
                        if data.get("category"):
                            current_category = str(data["category"])
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError, ValueError):
            logger.debug("Failed reading zip metadata from %s", source)

    # Infer gid and title from folder/file name pattern if still missing
    stem = source.stem
    match = _GID_STEM.match(stem)
    if match:
        if current_gid is None:
            current_gid = int(match.group(1))
        if not current_title and match.group(2):
            current_title = match.group(2)

    if not current_title:
        current_title = stem

    if current_gid is not None and current_title:
        current_title = strip_gid_prefix(current_title, current_gid) or current_title
    elif current_title:
        current_title = strip_gid_prefix(current_title, None) or current_title

    if current_gid is None and not current_stable:
        current_stable = path_hash(source)

    if current_title_jpn and str(current_title_jpn).strip().isdigit():
        current_title_jpn = ""

    return (
        current_gid,
        current_token,
        current_title,
        current_title_jpn or "",
        current_tags,
        current_p_tokens,
        current_stable or "",
        current_site,
        current_category,
    )


def cold_pack_gallery(
    source: Path | str,
    cold_root: Path | str,
    *,
    gid: int | None = None,
    token: str | None = None,
    title: str | None = None,
    title_jpn: str | None = None,
    tags: Sequence[dict[str, Any] | str] | None = None,
    p_tokens: Sequence[str] | None = None,
    stable: str | None = None,
    writer: str | None = None,
    site: str | None = None,
    category: str | None = None,
    max_cbz_bytes: int = COLD_ARCHIVE_MAX_CBZ_BYTES,
    max_cbz_pages: int = COLD_ARCHIVE_MAX_CBZ_PAGES,
    delete_source: bool = False,
) -> Path:
    """Pack a gallery to cold storage.

    Rules:
    - If total page bytes <= max_cbz_bytes (2GiB) and page_count <= max_cbz_pages (500)
      -> ZIP_STORED single CBZ.
    - Otherwise -> directory structure, big zip forbidden.
    - Destination paths follow compute_cold_path.
    - Contents only: 0001.ext... + ComicInfo.xml + .galleryvault.json.
    - Forbidden: cover.jpg, .ehviewer, JHenTai metadata.
    - Writes to {dest}.partial before atomic rename; on error, deletes partial, keeps source.
    - If delete_source=True and packing succeeds, deletes SSD source.
    """
    src = Path(source).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Gallery source does not exist: {src}")

    c_root = Path(cold_root).resolve()
    if is_under_cold(src, c_root):
        raise ColdAlreadyArchivedError(f"Source {src} is already in cold storage root {c_root}")

    (
        res_gid,
        res_token,
        res_title,
        res_title_jpn,
        res_tags,
        res_p_tokens,
        res_stable,
        res_site,
        res_category,
    ) = _extract_source_meta(
        src,
        gid=gid,
        token=token,
        title=title,
        title_jpn=title_jpn,
        tags=tags,
        p_tokens=p_tokens,
        stable=stable,
        site=site,
        category=category,
    )

    if res_gid is not None and res_title:
        res_title = strip_gid_prefix(res_title, res_gid) or res_title

    is_source_cbz = src.is_file() and src.suffix.lower() in {".cbz", ".zip"}
    if not src.is_dir() and not is_source_cbz:
        raise ValueError(f"Source must be a directory or CBZ/ZIP file: {src}")

    # Gather pages and total page bytes
    if is_source_cbz:
        with zipfile.ZipFile(src, "r") as zf:
            members = [
                info
                for info in zf.infolist()
                if not info.is_dir()
                and not Path(info.filename).name.startswith(".")
                and Path(info.filename).name.lower() not in _IGNORED_NAMES
                and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
            ]
            members.sort(key=lambda m: natural_key(Path(m.filename).name))
            if not members:
                raise ValueError(f"No valid image pages found in archive: {src}")
            total_page_bytes = sum(m.file_size for m in members)
            page_count = len(members)
    else:
        page_files = _collect_pages_from_dir(src)
        if not page_files:
            raise ValueError(f"No valid image pages found in directory: {src}")
        total_page_bytes = sum(p.stat().st_size for p in page_files)
        page_count = len(page_files)

    is_cbz = total_page_bytes <= max_cbz_bytes and page_count <= max_cbz_pages

    dest = compute_cold_path(
        c_root,
        is_cbz=is_cbz,
        gid=res_gid,
        title=res_title,
        stable=res_stable,
    )

    if dest.exists():
        raise ColdDestinationExistsError(
            f"Cold archive destination already exists: {dest}",
            dest_path=dest,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial_path = dest.parent / f"{dest.name}.partial"

    # Clean leftover partial if any
    if partial_path.is_dir():
        shutil.rmtree(partial_path, ignore_errors=True)
    elif partial_path.exists():
        partial_path.unlink(missing_ok=True)

    web: str | None = None
    if res_gid and res_token:
        base_url = _resolve_base_url(res_site)
        web = f"{base_url}/g/{res_gid}/{res_token}/"
    comic_xml_bytes = build_comic_info_xml(
        title=res_title,
        page_count=page_count,
        tags=res_tags,
        writer=writer,
        web=web,
    )
    gv_json_bytes = build_galleryvault_json(
        gid=res_gid,
        token=res_token,
        tags=res_tags,
        p_tokens=res_p_tokens,
        title=res_title,
        title_jpn=res_title_jpn,
        category=res_category,
    )

    try:
        if is_cbz:
            with zipfile.ZipFile(partial_path, "w", compression=ZIP_STORED) as zf_out:
                if is_source_cbz:
                    with zipfile.ZipFile(src, "r") as zf_in:
                        for idx, member in enumerate(members, start=1):
                            ext = Path(member.filename).suffix
                            target_name = page_archive_name(idx, ext)
                            with zf_in.open(member) as sf, zf_out.open(target_name, "w") as df:
                                shutil.copyfileobj(sf, df)
                else:
                    for idx, page_path in enumerate(page_files, start=1):
                        target_name = page_archive_name(idx, page_path.suffix)
                        zf_out.write(page_path, target_name)

                zf_out.writestr("ComicInfo.xml", comic_xml_bytes)
                zf_out.writestr(".galleryvault.json", gv_json_bytes)
        else:
            partial_path.mkdir(parents=True, exist_ok=True)
            if is_source_cbz:
                with zipfile.ZipFile(src, "r") as zf_in:
                    for idx, member in enumerate(members, start=1):
                        ext = Path(member.filename).suffix
                        target_file = partial_path / page_archive_name(idx, ext)
                        with zf_in.open(member) as sf, open(target_file, "wb") as df:
                            shutil.copyfileobj(sf, df)
            else:
                for idx, page_path in enumerate(page_files, start=1):
                    target_file = partial_path / page_archive_name(idx, page_path.suffix)
                    shutil.copy2(page_path, target_file)

            (partial_path / "ComicInfo.xml").write_bytes(comic_xml_bytes)
            (partial_path / ".galleryvault.json").write_bytes(gv_json_bytes)

        # Atomic commit to final location
        partial_path.replace(dest)

    except Exception:
        # Failure cleanup: remove partial, never touch source
        if partial_path.is_dir():
            shutil.rmtree(partial_path, ignore_errors=True)
        elif partial_path.exists():
            partial_path.unlink(missing_ok=True)
        raise

    # Only delete source if packing succeeded and explicitly requested
    if delete_source:
        try:
            if src.is_dir():
                shutil.rmtree(src, ignore_errors=True)
            elif src.is_file():
                src.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to delete source after successful archive: %s", src)

    return dest


_gallery_locks: dict[int, asyncio.Lock] = {}
_gallery_locks_guard = asyncio.Lock()


async def _get_gallery_lock(gallery_id: int) -> asyncio.Lock:
    """Acquire or create a per-gallery lock under guard protection."""
    async with _gallery_locks_guard:
        lock = _gallery_locks.get(gallery_id)
        if lock is None:
            lock = asyncio.Lock()
            _gallery_locks[gallery_id] = lock
        return lock


_active_gids: set[int] = set()


async def _do_archive_locked(
    gallery_id: int,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
    delete_source: bool = False,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> Path | None:
    if session_factory is None:
        return None
    roots = resolve_archive_roots(archive_roots=archive_roots, cold_root=cold_root)
    if not roots:
        logger.warning("No archive roots configured, cannot archive gallery %s", gallery_id)
        return None

    # Step 1: Read gallery metadata under a brief session (released before disk I/O and compression)
    async with session_factory() as session:
        gallery = await session.get(Gallery, gallery_id)
        if not gallery or gallery.trashed:
            return None

        # 获取 tags
        tags_stmt = (
            select(Tag.namespace, Tag.name)
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
            .where(GalleryTag.gallery_id == gallery_id)
        )
        tags = [
            {"namespace": row[0], "name": row[1]}
            for row in (await session.execute(tags_stmt)).all()
        ]

        # 画廊已有 site 或从 source_meta 中读取
        gallery_site = getattr(gallery, "site", None)
        if not gallery_site:
            source_meta = getattr(gallery, "source_meta", None)
            if isinstance(source_meta, dict):
                gallery_site = source_meta.get("site")

        # 查询归档前的页文件名列表（按 page_index 升序）
        old_pages_stmt = (
            select(GalleryPage.member_name)
            .where(GalleryPage.gallery_id == gallery_id)
            .order_by(GalleryPage.page_index)
        )
        old_page_names = [row[0] for row in (await session.execute(old_pages_stmt)).all()]
        gallery_gid = gallery.gid
        gallery_token = gallery.token
        gallery_title = gallery.title
        gallery_title_jpn = getattr(gallery, "title_jpn", None)
        gallery_category = getattr(gallery, "category", None)
        gallery_path_hash = gallery.path_hash
        gallery_storage_path = gallery.storage_path
        gallery_storage_size = gallery.storage_size
        gallery_file_size = gallery.file_size

    if not gallery_storage_path:
        logger.warning(
            "No storage path recorded for gallery",
            extra=log_extra(gallery_id=gallery_id),
        )
        return None

    source_path = Path(gallery_storage_path).resolve()
    if not source_path.exists():
        logger.warning(
            "Source path does not exist for gallery",
            extra=log_extra(gallery_id=gallery_id, source_path=str(source_path)),
        )
        return None

    # 已在任一 cold：skip
    if is_under_cold(source_path, roots):
        logger.info("Source %s is already under cold storage root, skipping", source_path)
        return None

    # 选盘：剩余≥体积×1.2 中取剩余最大
    stat_size = gallery_storage_size or gallery_file_size or 0
    if stat_size <= 0:
        if source_path.is_file():
            stat_size = source_path.stat().st_size
        elif source_path.is_dir():
            stat_size = sum(f.stat().st_size for f in source_path.rglob("*") if f.is_file())

    required_free = int(stat_size * 1.2)
    selected_root, _ = select_archive_root(required_free, archive_roots=roots)
    if selected_root is None:
        logger.warning(
            "No cold storage root has enough free space, skipping",
            extra=log_extra(gallery_id=gallery_id, required_free=required_free),
        )
        return None

    # Step 2: Pack and compress outside of DB session (no connection held)
    try:
        dest_path = await asyncio.to_thread(
            cold_pack_gallery,
            source=source_path,
            cold_root=selected_root,
            gid=gallery_gid,
            token=gallery_token,
            title=gallery_title,
            title_jpn=gallery_title_jpn,
            tags=tags,
            stable=gallery_path_hash,
            site=gallery_site,
            category=gallery_category,
            delete_source=False,
        )
    except ColdAlreadyArchivedError as exc:
        logger.info("Skipping gallery %s: %s", gallery_id, exc)
        return None
    except ColdDestinationExistsError as exc:
        if exc.dest_path and _validate_cold_destination(exc.dest_path):
            logger.info(
                "Adopting existing cold destination for gallery %s: %s",
                gallery_id,
                exc.dest_path,
            )
            dest_path = exc.dest_path
        else:
            logger.info("Skipping gallery %s: %s", gallery_id, exc)
            return None

    # Collect destination statistics
    try:
        is_dest_cbz = dest_path.is_file() and dest_path.suffix.lower() in {".cbz", ".zip"}
        dest_stat = dest_path.stat()
        new_mtime_ns = dest_stat.st_mtime_ns

        if is_dest_cbz:
            new_size = dest_stat.st_size
            with zipfile.ZipFile(dest_path, "r") as zf:
                page_names = sorted(
                    [
                        n
                        for n in zf.namelist()
                        if not n.startswith(".")
                        and Path(n).suffix.lower() in IMAGE_EXTENSIONS
                        and Path(n).name.lower() not in _IGNORED_NAMES
                    ],
                    key=natural_key,
                )
        else:
            new_size = sum(f.stat().st_size for f in dest_path.rglob("*") if f.is_file())
            page_names = sorted(
                [
                    p.name
                    for p in dest_path.iterdir()
                    if p.is_file()
                    and not p.name.startswith(".")
                    and p.suffix.lower() in IMAGE_EXTENSIONS
                    and p.name.lower() not in _IGNORED_NAMES
                ],
                key=natural_key,
            )

        if not page_names:
            logger.warning(
                "No valid pages found in destination",
                extra=log_extra(gallery_id=gallery_id, dest_path=str(dest_path)),
            )
            return None

        new_sig = hashlib.sha256(f"{new_mtime_ns}:{new_size}".encode()).hexdigest()
    except Exception as exc:
        logger.warning(
            "Failed to collect destination stats for gallery",
            extra=log_extra(gallery_id=gallery_id, error=str(exc)),
            exc_info=True,
        )
        return None

    # Step 3: Brief DB write transaction to update Gallery and GalleryPage
    async def _apply_archive_db_updates(s: AsyncSession) -> bool:
        gallery_obj = await s.get(Gallery, gallery_id)
        if not gallery_obj:
            logger.warning(
                "Gallery was deleted before archive DB update",
                extra=log_extra(gallery_id=gallery_id),
            )
            return False

        # 更新 Gallery
        gallery_obj.storage_path = str(dest_path)
        gallery_obj.storage_type = "cbz" if is_dest_cbz else "folder"
        gallery_obj.path_hash = path_hash(dest_path)
        gallery_obj.storage_mtime_ns = new_mtime_ns
        gallery_obj.storage_size = new_size
        gallery_obj.storage_signature = new_sig
        gallery_obj.page_count = len(page_names)
        if page_names:
            gallery_obj.cover_path = page_names[0]
        gallery_obj.updated_at = datetime.now(UTC)

        # 更新 GalleryPage
        await s.execute(delete(GalleryPage).where(GalleryPage.gallery_id == gallery_obj.id))
        new_pages = [
            GalleryPage(
                gallery_id=gallery_obj.id,
                page_index=idx,
                member_name=pname,
                media_type=Path(pname).suffix.lstrip(".").lower() or "jpg",
                manifest={"size": 0, "mtime_ns": new_mtime_ns},
            )
            for idx, pname in enumerate(page_names)
        ]
        if new_pages:
            s.add_all(new_pages)
        return True

    async with session_factory() as session:
        if hasattr(session, "begin"):
            async with session.begin():
                if not await _apply_archive_db_updates(session):
                    return None
        else:
            if not await _apply_archive_db_updates(session):
                return None
            if hasattr(session, "commit"):
                await session.commit()

    # 页数变化则清 thumbs（纯重命名不清理）
    if len(old_page_names) != len(page_names):
        _clear_gallery_thumbs(gallery_id)

    # DB 更新提交成功后，按设置决定是否删除 SSD 源
    if delete_source and source_path.resolve() != dest_path.resolve():
        try:
            from .storage_usage import safe_stat_size, storage_tracker

            settings = app_state.settings or get_settings()
            try:
                dl_root = Path(settings.download_root).resolve()
                is_dl = source_path.resolve().is_relative_to(dl_root)
            except (AttributeError, ValueError, TypeError, OSError):
                is_dl = False
            sz = safe_stat_size(source_path) if is_dl else 0

            if source_path.is_dir():
                shutil.rmtree(source_path, ignore_errors=True)
            elif source_path.is_file():
                source_path.unlink(missing_ok=True)
            if is_dl and sz > 0 and not source_path.exists():
                storage_tracker.record_download_delta(-sz)
            logger.info("Deleted SSD source %s after archive to %s", source_path, dest_path)
        except OSError as exc:
            logger.warning("Failed to delete SSD source %s: %s", source_path, exc)

    return dest_path


async def archive_one(
    gallery_id: int,
    *,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
    delete_source: bool | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> Path | None:
    """Archive a single gallery to cold storage with writer lock and per-gid lock.

    Returns destination path on success, or None if skipped/unavailable.
    """
    settings = app_state.settings or get_settings()
    roots = resolve_archive_roots(archive_roots=archive_roots, cold_root=cold_root)
    if not roots:
        logger.warning("Cold storage root not configured, cannot archive gallery %s", gallery_id)
        return None

    if delete_source is None:
        delete_source = bool(getattr(settings, "archive_delete_source", True))

    sf = session_factory or app_state.session_factory
    if not sf:
        logger.warning("No session factory available for archive_one")
        return None

    # Resolve target gallery and gid
    async with sf() as session:
        gallery = await session.get(Gallery, gallery_id)
        if not gallery:
            gallery = await session.scalar(select(Gallery).where(Gallery.gid == gallery_id))
            if not gallery:
                logger.warning("Gallery %s not found for archive", gallery_id)
                return None
        target_id = gallery.id
        target_gid = gallery.gid

    # Per-gid lock & skip ongoing download tasks
    if target_gid is not None:
        if target_gid in _active_gids:
            logger.info("Gallery gid %s is already in archive progress, skipping", target_gid)
            return None

        async with sf() as session:
            active_dl = await session.scalar(
                select(DownloadTask.id).where(
                    DownloadTask.gid == target_gid,
                    DownloadTask.status.in_(["pending", "downloading"]),
                )
            )
            if active_dl:
                logger.info(
                    "Gallery %s (gid=%s) has active download task %s, skipping archive",
                    target_id,
                    target_gid,
                    active_dl,
                )
                return None

    gid_to_unlock: int | None = target_gid
    if gid_to_unlock is not None:
        _active_gids.add(gid_to_unlock)
    try:
        lock = await _get_gallery_lock(target_id)
        async with lock:
            return await _do_archive_locked(
                target_id,
                archive_roots=roots,
                delete_source=delete_source,
                session_factory=sf,
            )
    finally:
        if gid_to_unlock is not None:
            _active_gids.discard(gid_to_unlock)
        async with _gallery_locks_guard:
            existing_lock = _gallery_locks.get(target_id)
            if existing_lock is not None and not existing_lock.locked():
                _gallery_locks.pop(target_id, None)


async def purge_archived_sources_internal(
    session_factory: Callable[[], AsyncSession] | None = None,
    tracker: Any | None = None,
    tm: Any | None = None,
) -> int:
    """Safely scan download_root and library_roots for leftover source dirs of archived galleries.

    Deletes source folders for galleries already archived to cold storage (both cbz and folder format)
    without active downloads/archiving tasks, and records download/library deltas.
    Returns the count of purged directories.
    """
    settings = app_state.settings or get_settings()
    sf = session_factory or app_state.session_factory
    if sf is None:
        logger.warning("No session factory available for purge_archived_sources_internal")
        return 0

    cold_roots = [Path(r).resolve() for r in resolve_archive_roots()]

    async with sf() as session:
        # GIDs that have already been archived to cold storage
        archived_stmt = select(Gallery.gid, Gallery.storage_path).where(
            Gallery.gid.is_not(None),
            Gallery.storage_path.is_not(None),
        )
        archived_rows = (await session.execute(archived_stmt)).all()

        # GIDs with active downloads
        active_dl_stmt = select(DownloadTask.gid).where(
            DownloadTask.status.in_(["pending", "downloading"]),
            DownloadTask.gid.is_not(None),
        )
        active_dl_gids = set((await session.scalars(active_dl_stmt)).all())

        # Safety guard: never delete any path currently recorded as a gallery's active storage_path
        active_paths_stmt = select(Gallery.storage_path).where(Gallery.storage_path.is_not(None))
        active_paths_raw = (await session.scalars(active_paths_stmt)).all()

    archived_gids = {
        gid
        for gid, sp in archived_rows
        if is_under_cold(sp, cold_roots)
    }
    active_gids = active_dl_gids | _active_gids
    active_paths = {
        Path(p).resolve() for p in active_paths_raw if p
    }

    if not archived_gids and not cold_roots:
        return 0

    dl_root_raw = getattr(settings, "download_root", None)
    dl_root = Path(dl_root_raw).resolve() if dl_root_raw else None
    lib_roots_raw = getattr(settings, "library_roots", []) or []
    lib_roots = [Path(r).resolve() for r in lib_roots_raw if r]

    scan_roots: list[Path] = []
    if dl_root and dl_root.exists():
        scan_roots.append(dl_root)
    for lr in lib_roots:
        if lr.exists() and lr not in scan_roots:
            scan_roots.append(lr)

    if not scan_roots:
        return 0

    from .storage_usage import safe_stat_size, storage_tracker

    def _sync_purge() -> int:
        purged = 0
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        def _report_progress(done_count: int) -> None:
            if tracker is None:
                return
            if loop and not loop.is_closed():
                loop.call_soon_threadsafe(lambda: tracker.update(done=done_count, stage="purging"))
            else:
                tracker.update(done=done_count, stage="purging")

        _report_progress(0)

        for s_root in scan_roots:
            if not s_root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(s_root):
                if tm and tm.is_cancelled("purge-archived-sources"):
                    logger.info("Purge archived sources task cancelled during directory walk")
                    return purged

                cur_dir = Path(dirpath).resolve()
                if is_under_cold(cur_dir, cold_roots):
                    continue

                # Clean leftover .log and .nomedia waste files
                for fname in filenames:
                    if fname.lower().endswith(".log") or fname.lower() == ".nomedia":
                        waste_file = cur_dir / fname
                        try:
                            waste_file.unlink(missing_ok=True)
                            logger.debug("Cleaned leftover waste file: %s", waste_file)
                        except OSError as exc:
                            logger.warning("Failed to delete waste file %s: %s", waste_file, exc)

                # Exclude hidden directories except temporary .gv- downloads
                dirnames[:] = [d for d in dirnames if not d.startswith(".") or d.startswith(".gv-")]
                if cur_dir == s_root:
                    continue
                if cur_dir in active_paths:
                    continue

                gid: int | None = None

                # 1. Try reading .galleryvault.json
                gv_file = cur_dir / ".galleryvault.json"
                if gv_file.is_file():
                    try:
                        data = json.loads(gv_file.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            raw_gid = data.get("gid")
                            if raw_gid is not None and str(raw_gid).isdigit() and int(raw_gid) > 0:
                                gid = int(raw_gid)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        pass

                # 2. Try reading metadata (JHenTai)
                if gid is None:
                    meta_file = cur_dir / "metadata"
                    if meta_file.is_file():
                        try:
                            meta = json.loads(meta_file.read_text(encoding="utf-8"))
                            if isinstance(meta, dict):
                                raw_gid = meta.get("gid")
                                if raw_gid is None and isinstance(meta.get("gallery"), dict):
                                    raw_gid = meta["gallery"].get("gid")
                                if raw_gid is not None and str(raw_gid).isdigit() and int(raw_gid) > 0:
                                    gid = int(raw_gid)
                        except (OSError, ValueError, TypeError, json.JSONDecodeError):
                            pass

                # 3. Try reading .ehviewer
                if gid is None:
                    eh_file = cur_dir / ".ehviewer"
                    if eh_file.is_file():
                        try:
                            spider = parse_spider_info(eh_file.read_text(encoding="utf-8"))
                            gid = spider.gid
                        except (OSError, ValueError):
                            try:
                                lines = [
                                    line.strip()
                                    for line in eh_file.read_text(encoding="utf-8").splitlines()
                                    if line.strip()
                                ]
                                for line in lines[:3]:
                                    if line.isdigit() and int(line) > 0:
                                        gid = int(line)
                                        break
                            except OSError:
                                pass

                # 4. Regex and name matching
                if gid is None:
                    m_gv = re.match(r"^\.gv-(\d+)", cur_dir.name)
                    if m_gv:
                        try:
                            gid = int(m_gv.group(1))
                        except ValueError:
                            pass

                if gid is None:
                    m_pre = re.match(r"^\s*(\d+)\s*[-\s_]", cur_dir.name)
                    if m_pre:
                        try:
                            gid = int(m_pre.group(1))
                        except ValueError:
                            pass

                if gid is None and cur_dir.name.isdigit():
                    try:
                        gid = int(cur_dir.name)
                    except ValueError:
                        pass

                if gid is not None:
                    dirnames.clear()
                    # First priority guard: never delete active downloads or ongoing archive tasks
                    if gid in active_gids:
                        continue

                    # Check DB archived state or fallback to physical check in cold storage
                    is_archived = (gid in archived_gids) or _check_physically_archived(gid, cold_roots)
                    if is_archived:
                        is_dl = False
                        if dl_root:
                            try:
                                is_dl = cur_dir.is_relative_to(dl_root)
                            except (AttributeError, ValueError, TypeError, OSError):
                                is_dl = False
                        is_lib = False
                        if not is_dl:
                            for lr in lib_roots:
                                try:
                                    if cur_dir.is_relative_to(lr):
                                        is_lib = True
                                        break
                                except (AttributeError, ValueError, TypeError, OSError):
                                    continue
                        sz = safe_stat_size(cur_dir) if (is_dl or is_lib) else 0
                        try:
                            shutil.rmtree(cur_dir, ignore_errors=True)
                            if not cur_dir.exists():
                                purged += 1
                                if is_dl and sz > 0:
                                    storage_tracker.record_download_delta(-sz)
                                elif is_lib and sz > 0:
                                    storage_tracker.record_library_delta(-sz)
                                _report_progress(purged)
                                logger.info(
                                    "Purged leftover source directory for archived gallery %s: %s",
                                    gid,
                                    cur_dir,
                                )
                        except OSError as exc:
                            logger.warning("Failed to purge source directory %s: %s", cur_dir, exc)
        return purged

    return await asyncio.to_thread(_sync_purge)


async def run_purge_archived_sources(
    tm: Any | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> int:
    """Execute purge archived sources task within task manager tracking."""
    from ..app.dependencies import get_current_settings, get_task_manager
    from .storage_usage import storage_tracker

    if tm is None:
        tm = get_task_manager()

    async with tm.track_task("purge-archived-sources", cancellable=True) as tracker:
        tracker.update(done=0, stage="purging")
        purged = await purge_archived_sources_internal(
            session_factory=session_factory,
            tracker=tracker,
            tm=tm,
        )
        tracker.update(done=purged, stage="finished")

        try:
            settings = app_state.settings or get_current_settings()
            dl_root = getattr(settings, "download_root", "")
            cache_root = Path(getattr(settings, "thumbnail_cache_dir", "")).parent
            lib_root = (getattr(settings, "library_roots", []) or [None])[0]
            await storage_tracker.calibrate(
                download_root=dl_root,
                cache_root=cache_root,
                library_root=lib_root,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("storage calibration after purge failed", extra={"error": str(exc)})

        return purged


async def run_cold_archive(
    *,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    task_manager: Any = None,
) -> None:
    """Batch cold archive background task for all unarchived SSD galleries."""
    settings = app_state.settings or get_settings()
    roots = resolve_archive_roots(archive_roots=archive_roots, cold_root=cold_root)
    if not roots:
        logger.warning("Cold storage root not configured; aborting run_cold_archive")
        return

    if getattr(settings, "global_paused", False):
        logger.info("Global paused is active; aborting run_cold_archive")
        return

    if task_manager is None:
        from ..app.dependencies import get_task_manager

        tm = get_task_manager()
    else:
        tm = task_manager

    sf = session_factory or app_state.session_factory
    if not sf:
        logger.warning("No session factory available for run_cold_archive")
        tm.archive_state["running"] = False
        return

    from ..app.dependencies import get_scan_roots

    ssd_roots = [Path(r).resolve() for r in get_scan_roots()]

    async with sf() as session:
        active_dl_stmt = select(DownloadTask.gid).where(
            DownloadTask.status.in_(["pending", "downloading"]),
            DownloadTask.gid.is_not(None),
        )
        active_gids = set((await session.scalars(active_dl_stmt)).all())

        galleries_stmt = (
            select(Gallery.id, Gallery.gid, Gallery.storage_path)
            .where(Gallery.trashed.is_(False))
            .order_by(Gallery.id)
        )
        rows = (await session.execute(galleries_stmt)).all()

    candidate_ids: list[int] = []
    for row_id, row_gid, row_path in rows:
        if row_gid is not None and row_gid in active_gids:
            continue
        if not row_path:
            continue
        p = Path(row_path).resolve()
        if is_under_cold(p, roots):
            continue
        if not any(p == r or p.is_relative_to(r) for r in ssd_roots):
            continue
        if not p.exists():
            continue
        candidate_ids.append(row_id)

    total = len(candidate_ids)
    from .notifications import _notify_lang, notify_archive

    zh = _notify_lang() != "en"
    start_title = "批量归档开始" if zh else "Batch archive started"
    start_detail = f"共 {total} 本" if zh else f"{total} galleries"
    notify_archive("archive_start", start_title, start_detail)

    if app_state.telegram is not None:
        try:
            await app_state.telegram.record_batch_archive("archive_start", total=total)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send telegram batch archive start: %s", exc)

    done = 0
    skipped = 0
    failed = 0
    was_cancelled = False

    async with tm.track_task("archive", cancellable=True) as tracker:
        tracker.update(done=0, total=total, skipped=0, failed=0, last_error=None)
        for gid_or_id in candidate_ids:
            # Check cancellation between galleries
            if tm.is_cancelled("archive"):
                was_cancelled = True
                break

            try:
                res = await archive_one(
                    gid_or_id,
                    archive_roots=roots,
                    session_factory=sf,
                )
                if res is not None:
                    done += 1
                else:
                    skipped += 1
            except (ColdAlreadyArchivedError, ColdDestinationExistsError):
                skipped += 1
            except Exception as exc:
                failed += 1
                tracker.update(last_error=str(exc))
                logger.exception("Failed to archive gallery %s", gid_or_id)

            tracker.update(done=done, skipped=skipped, failed=failed)

            if tm.is_cancelled("archive"):
                was_cancelled = True
                break

        reason = f"done {done} / skip {skipped} / fail {failed}"
        if was_cancelled:
            reason += " (cancelled)"
        tracker.update(reason=reason)

    if getattr(settings, "archive_delete_source", True):
        try:
            purged = await purge_archived_sources_internal(session_factory=sf)
            if purged > 0:
                logger.info("Auto-purged %d leftover archived source directories", purged)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-purge archived sources failed: %s", exc)

    has_fail = failed > 0
    end_kind = "archive_fail" if has_fail else "archive_ok"
    if has_fail:
        end_title = "批量归档结束（有失败）" if zh else "Batch archive finished with errors"
        end_detail = (
            f"完成 {done}，跳过 {skipped}，失败 {failed}"
            if zh
            else f"done {done} / skip {skipped} / fail {failed}"
        )
    else:
        end_title = "批量归档完成" if zh else "Batch archive complete"
        end_detail = f"完成 {done}，跳过 {skipped}" if zh else f"done {done} / skip {skipped}"
    if was_cancelled:
        end_detail += " (已取消)" if zh else " (cancelled)"

    notify_archive(end_kind, end_title, end_detail)

    if app_state.telegram is not None:
        try:
            await app_state.telegram.record_batch_archive(
                "archive_end",
                done=done,
                skipped=skipped,
                failed=failed,
                error=tm.archive_state.get("last_error"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send telegram batch archive end: %s", exc)
