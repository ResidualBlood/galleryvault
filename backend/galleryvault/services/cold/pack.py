"""Cold archive packing: source metadata extraction and CBZ/dir writers."""

from __future__ import annotations

import re
import shutil
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ...app.state import app_state
from ...config import get_settings
from ...db.repositories.base import path_hash
from ...metadata.sidecar import normalize_tags, read_galleryvault_json
from ...scanners.ehviewer import (
    IMAGE_EXTENSIONS,
    natural_key,
    parse_spider_info,
    strip_gid_prefix,
)
from ...storage_paths import is_under_cold
from ._util import _IGNORED_NAMES, ZIP_STORED, logger, page_archive_name
from .paths import build_comic_info_xml, build_galleryvault_json, compute_cold_path

_GID_STEM = re.compile(r"^(\d+)(?:-(.*))?$")


COLD_ARCHIVE_MAX_CBZ_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
COLD_ARCHIVE_MAX_CBZ_PAGES = 500


class ColdStorageError(Exception):
    """Base exception for cold archive operations."""


class ColdDestinationExistsError(ColdStorageError, FileExistsError):
    """Raised when cold storage destination already exists."""

    def __init__(self, message: str = "", dest_path: Path | None = None) -> None:
        super().__init__(message)
        self.dest_path = dest_path


class ColdAlreadyArchivedError(ColdStorageError):
    """Raised when source is already located under the cold storage root."""


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
    quality: str | None = None,
) -> tuple[int | None, str | None, str, str, list[dict[str, str]], list[str], str, str | None, str | None, str | None]:
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
    current_quality = quality

    gv_data = read_galleryvault_json(source)
    if gv_data:
        if current_gid is None and gv_data.get("gid") is not None:
            current_gid = gv_data["gid"]
        if not current_token and gv_data.get("token"):
            current_token = gv_data["token"]
        if not current_title and gv_data.get("title"):
            current_title = gv_data["title"]
        if not current_title_jpn and gv_data.get("title_jpn"):
            current_title_jpn = gv_data["title_jpn"]
        if not current_tags and gv_data.get("tags"):
            current_tags = gv_data["tags"]
        if not current_p_tokens and gv_data.get("p_tokens"):
            current_p_tokens = gv_data["p_tokens"]
        if not current_site and gv_data.get("site"):
            current_site = gv_data["site"]
        if not current_category and gv_data.get("category"):
            current_category = gv_data["category"]
        if not current_quality and gv_data.get("quality"):
            current_quality = gv_data["quality"]

    if source.is_dir():
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
        current_quality,
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
    quality: str | None = None,
    uploader: str | None = None,
    posted_at: Any | None = None,
    rating: float | None = None,
    file_count: int | None = None,
    file_size: int | None = None,
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
        res_quality,
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
        quality=quality,
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
        quality=res_quality,
        uploader=uploader,
        posted=posted_at,
        rating=rating,
        file_count=file_count if file_count is not None else page_count,
        file_size=file_size if file_size is not None else total_page_bytes,
        site=res_site,
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
