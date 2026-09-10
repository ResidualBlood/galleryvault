#!/usr/bin/env python3
"""scripts/fix_corrupted_gallery_pages.py.

Maintenance script to inspect and repair corrupted gallery pages:
  - Scans gallery CBZ archives or directories for truncated/corrupted images
    using magic byte verification, JPEG EOI marker detection, and PIL Image.verify().
  - Re-downloads corrupted pages from ExHentai via EhClient and replaces them.
  - Re-packs CBZ archives via pack_directory_cbz with atomic replace.
  - Supports `--dry-run` to detect issues without modifying files or downloading.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

# Add backend directory to sys.path so galleryvault can be imported directly
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from galleryvault.app.state import app_state
from galleryvault.config import Settings, get_settings
from galleryvault.db.models import Gallery, GalleryPage
from galleryvault.scanners.ehviewer import natural_key
from galleryvault.services.cold_archive import resolve_archive_roots
from galleryvault.services.downloader import _is_valid_image_magic
from galleryvault.services.eh_client import EhClient, GalleryData, ShowkeyState
from galleryvault.services.export_cbz import pack_directory_cbz

if TYPE_CHECKING:
    from collections.abc import Sequence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fix_corrupted_gallery_pages")

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


def check_image_integrity(data: bytes) -> tuple[bool, str]:
    """Check image data integrity using magic prefix, JPEG EOI and PIL verify.

    Returns (is_valid, reason).
    """
    if not data:
        return False, "image is empty (0 bytes)"
    if data[:20].lstrip().lower().startswith((b"<html", b"<!doctype")):
        return False, "html response detected"
    if not _is_valid_image_magic(data):
        return False, f"unrecognized magic prefix: {data[:16].hex()}"
    if data[:2] == b"\xff\xd8" and b"\xff\xd9" not in data[-1024:]:
        return False, "JPEG file is truncated (missing EOI)"
    if len(data) > 512:
        if data.startswith(b"GIF"):
            if not data.rstrip(b"\x00").endswith(b";"):
                return False, "GIF file is truncated (missing trailer)"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            expected_len = struct.unpack("<I", data[4:8])[0] + 8
            if len(data) < expected_len:
                return False, "WebP file is truncated (payload size mismatch)"
    try:
        from PIL import Image

        Image.open(io.BytesIO(data)).verify()
    except Exception as exc:  # noqa: BLE001
        return False, f"PIL verify failed: {exc}"
    return True, "ok"


def resolve_gallery_path(storage_path: str, settings: Settings) -> Path | None:
    """Resolve storage_path (absolute, relative or cold: prefix) to local Path."""
    raw = (storage_path or "").strip()
    if not raw:
        return None

    if raw.startswith("cold:"):
        rel = raw[5:].lstrip("/")
        roots = resolve_archive_roots()
        for root in roots:
            candidate = root / rel
            if candidate.exists():
                return candidate
        return None

    p = Path(raw)
    if p.exists():
        return p

    # Try relative to download_root or library_roots
    if settings.download_root:
        candidate = Path(settings.download_root) / raw
        if candidate.exists():
            return candidate
    for lib in settings.library_roots:
        candidate = Path(lib) / raw
        if candidate.exists():
            return candidate

    return None


async def redownload_page_image(
    client: EhClient,
    gid: int,
    token: str,
    page_index: int,
    cached_gallery_data: GalleryData | None,
    showkey: ShowkeyState,
) -> tuple[bytes, str, GalleryData]:
    """Redownload a single page image and return verified bytes and extension."""
    if cached_gallery_data is None:
        cached_gallery_data = await client.fetch_gallery(gid, token, resolve_urls=False)

    if page_index < 0 or page_index >= len(cached_gallery_data.pages):
        raise ValueError(
            f"page index {page_index} out of bounds (gallery has {len(cached_gallery_data.pages)} pages)"
        )

    target_page = cached_gallery_data.pages[page_index]
    resolved = await client.resolve_page(gid, target_page, showkey)
    url = getattr(resolved, "image_url", None) or getattr(resolved, "url", None)
    if not url:
        raise ValueError(f"failed to resolve image URL for page {page_index}")

    fetch_with_type = getattr(client, "download_image_with_metadata", None)
    if fetch_with_type is not None:
        data, content_type = await fetch_with_type(url)
    else:
        data = await client.download_image(url)
        content_type = ""

    valid, reason = check_image_integrity(data)
    if not valid:
        raise ValueError(f"redownloaded image failed integrity check: {reason}")

    ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }.get(content_type.split(";", 1)[0].lower(), Path(url).suffix.lower())
    if ext not in _IMAGE_SUFFIXES:
        ext = ".jpg"

    return data, ext, cached_gallery_data


def clean_thumbnail_cache(gallery_id: int, page_indexes: Sequence[int], settings: Settings) -> None:
    """Remove cached thumbnail files for repaired pages so fresh ones can be generated."""
    thumb_dir = Path(settings.thumbnail_cache_dir) / str(gallery_id)
    if not thumb_dir.is_dir():
        return
    for p_idx in page_indexes:
        target = thumb_dir / f"{p_idx}.jpg"
        if target.is_file():
            try:
                target.unlink()
                logger.info("Cleared cached thumbnail: %s", target)
            except OSError as exc:
                logger.warning("Could not clear cached thumbnail %s: %exc", target, exc)


async def repair_cbz(
    cbz_path: Path,
    gid: int | None,
    token: str | None,
    client: EhClient | None,
    gallery_id: int | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Scan and repair corrupted images inside a CBZ archive."""
    with zipfile.ZipFile(cbz_path, "r") as zf:
        infolist = zf.infolist()
        image_infos = [
            info
            for info in infolist
            if not info.is_dir()
            and Path(info.filename).suffix.lower() in _IMAGE_SUFFIXES
            and not Path(info.filename).name.startswith(".")
        ]
        image_infos.sort(key=lambda x: natural_key(x.filename))

        corrupted: list[tuple[int, zipfile.ZipInfo, str]] = []
        for idx, info in enumerate(image_infos):
            try:
                data = zf.read(info)
                valid, reason = check_image_integrity(data)
                if not valid:
                    corrupted.append((idx, info, reason))
            except Exception as exc:  # noqa: BLE001
                corrupted.append((idx, info, f"failed to read zip entry: {exc}"))

    if not corrupted:
        return 0, 0

    logger.warning(
        "CBZ %s has %d corrupted pages (out of %d)",
        cbz_path.name,
        len(corrupted),
        len(image_infos),
    )
    for idx, info, reason in corrupted:
        logger.warning("  Page %d (%s): %s", idx + 1, info.filename, reason)

    if dry_run:
        logger.info("[DRY-RUN] No changes applied to %s", cbz_path.name)
        return len(corrupted), 0

    if not gid or not token or client is None:
        logger.error(
            "Cannot repair %s: missing GID/token or EhClient instance",
            cbz_path.name,
        )
        return len(corrupted), 0

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        with zipfile.ZipFile(cbz_path, "r") as zf:
            zf.extractall(tmp_dir)

        cached_gallery_data: GalleryData | None = None
        showkey = ShowkeyState()
        repaired_indexes: list[int] = []

        for idx, info, _reason in corrupted:
            logger.info("Re-downloading page %d for %s (gid=%s)...", idx + 1, cbz_path.name, gid)
            try:
                new_data, new_ext, cached_gallery_data = await redownload_page_image(
                    client, gid, token, idx, cached_gallery_data, showkey
                )
                target_file = tmp_dir / info.filename
                if target_file.suffix.lower() == new_ext.lower():
                    target_file.write_bytes(new_data)
                else:
                    target_file.unlink(missing_ok=True)
                    new_target = target_file.with_suffix(new_ext)
                    new_target.write_bytes(new_data)
                    if gallery_id is not None and app_state.session_factory is not None:
                        new_member_name = new_target.relative_to(tmp_dir).as_posix()
                        clean_ext = new_ext.lstrip(".").lower()
                        async with app_state.session_factory() as session, session.begin():
                            await session.execute(
                                update(GalleryPage)
                                .where(
                                    GalleryPage.gallery_id == gallery_id,
                                    GalleryPage.page_index == idx,
                                )
                                .values(
                                    member_name=new_member_name,
                                    media_type=clean_ext,
                                )
                            )
                repaired_indexes.append(idx)
                logger.info("Successfully repaired page %d", idx + 1)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to repair page %d: %s", idx + 1, exc)

        if not repaired_indexes:
            logger.warning("No pages could be repaired for %s", cbz_path.name)
            return len(corrupted), 0

        # Re-pack CBZ atomically using pack_directory_cbz
        temp_cbz = cbz_path.with_name(f".tmp_{cbz_path.name}")
        current_images = [
            p
            for p in tmp_dir.rglob("*")
            if p.is_file()
            and p.suffix.lower() in _IMAGE_SUFFIXES
            and not p.name.startswith(".")
        ]
        current_images.sort(key=lambda p: natural_key(p.name))
        pages_spec = [
            (i + 1, str(p.relative_to(tmp_dir)))
            for i, p in enumerate(current_images)
        ]
        pack_directory_cbz(tmp_dir, pages_spec, temp_cbz)

        # Preserve non-image metadata files (e.g. .galleryvault.json, ComicInfo.xml)
        with zipfile.ZipFile(temp_cbz, "a", compression=zipfile.ZIP_STORED) as zf_out:
            for extra_file in tmp_dir.rglob("*"):
                if (
                    extra_file.is_file()
                    and extra_file.suffix.lower() not in _IMAGE_SUFFIXES
                ):
                    rel = str(extra_file.relative_to(tmp_dir))
                    if rel not in zf_out.namelist():
                        zf_out.write(extra_file, rel)

        os.replace(temp_cbz, cbz_path)
        logger.info("CBZ %s re-packed successfully", cbz_path.name)

        if gallery_id is not None and settings is not None:
            clean_thumbnail_cache(gallery_id, repaired_indexes, settings)

        return len(corrupted), len(repaired_indexes)


async def repair_dir(
    dir_path: Path,
    gid: int | None,
    token: str | None,
    client: EhClient | None,
    gallery_id: int | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Scan and repair corrupted images inside a gallery directory."""
    images = [
        p
        for p in dir_path.iterdir()
        if p.is_file()
        and p.suffix.lower() in _IMAGE_SUFFIXES
        and not p.name.startswith(".")
    ]
    images.sort(key=lambda p: natural_key(p.name))

    corrupted: list[tuple[int, Path, str]] = []
    for idx, p in enumerate(images):
        try:
            data = p.read_bytes()
            valid, reason = check_image_integrity(data)
            if not valid:
                corrupted.append((idx, p, reason))
        except Exception as exc:  # noqa: BLE001
            corrupted.append((idx, p, f"failed to read file: {exc}"))

    if not corrupted:
        return 0, 0

    logger.warning(
        "Directory %s has %d corrupted pages (out of %d)",
        dir_path.name,
        len(corrupted),
        len(images),
    )
    for idx, p, reason in corrupted:
        logger.warning("  Page %d (%s): %s", idx + 1, p.name, reason)

    if dry_run:
        logger.info("[DRY-RUN] No changes applied to %s", dir_path.name)
        return len(corrupted), 0

    if not gid or not token or client is None:
        logger.error(
            "Cannot repair %s: missing GID/token or EhClient instance",
            dir_path.name,
        )
        return len(corrupted), 0

    cached_gallery_data: GalleryData | None = None
    showkey = ShowkeyState()
    repaired_indexes: list[int] = []

    for idx, p, _reason in corrupted:
        logger.info("Re-downloading page %d for %s (gid=%s)...", idx + 1, dir_path.name, gid)
        try:
            new_data, new_ext, cached_gallery_data = await redownload_page_image(
                client, gid, token, idx, cached_gallery_data, showkey
            )
            tmp_target = p.with_name(f".tmp_{p.name}")
            tmp_target.write_bytes(new_data)
            if p.suffix.lower() == new_ext.lower():
                os.replace(tmp_target, p)
            else:
                p.unlink(missing_ok=True)
                new_final = p.with_suffix(new_ext)
                os.replace(tmp_target, new_final)
                if gallery_id is not None and app_state.session_factory is not None:
                    clean_ext = new_ext.lstrip(".").lower()
                    async with app_state.session_factory() as session, session.begin():
                        await session.execute(
                            update(GalleryPage)
                            .where(
                                GalleryPage.gallery_id == gallery_id,
                                GalleryPage.page_index == idx,
                            )
                            .values(
                                member_name=new_final.name,
                                media_type=clean_ext,
                            )
                        )
            repaired_indexes.append(idx)
            logger.info("Successfully repaired page %d (%s)", idx + 1, p.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to repair page %d: %s", idx + 1, exc)

    if gallery_id is not None and settings is not None and repaired_indexes:
        clean_thumbnail_cache(gallery_id, repaired_indexes, settings)

    return len(corrupted), len(repaired_indexes)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect and repair corrupted gallery pages"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gid", type=int, help="Target gallery ExHentai GID")
    group.add_argument("--id", type=int, help="Target gallery database ID")
    group.add_argument("--path", type=str, help="Direct path to CBZ file or directory")
    group.add_argument("--all", action="store_true", help="Scan all galleries in database")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and report corrupted pages without downloading or modifying files",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Optional gallery token when using --path directly",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum galleries to scan when using --all",
    )

    args = parser.parse_args()

    settings = app_state.settings or get_settings()
    app_state.settings = settings

    if app_state.session_factory is None:
        engine = create_async_engine(settings.database_url, future=True)
        app_state.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    client: EhClient | None = None
    if not args.dry_run:
        client = getattr(app_state, "eh_client", None)
        if client is None:
            client = EhClient(settings, max_concurrency=settings.exhentai_max_concurrency)
            app_state.eh_client = client

    total_corrupted = 0
    total_repaired = 0

    try:
        if args.path:
            p = Path(args.path).resolve()
            if not p.exists():
                logger.error("Specified path does not exist: %s", p)
                sys.exit(1)
            gid = args.gid
            token = args.token
            if p.is_file() and p.suffix.lower() in {".cbz", ".zip"}:
                c, r = await repair_cbz(
                    p, gid, token, client, settings=settings, dry_run=args.dry_run
                )
            elif p.is_dir():
                c, r = await repair_dir(
                    p, gid, token, client, settings=settings, dry_run=args.dry_run
                )
            else:
                logger.error("Unsupported file path format: %s", p)
                sys.exit(1)
            total_corrupted += c
            total_repaired += r
        else:
            async with app_state.session_factory() as session:
                stmt = select(Gallery).where(Gallery.storage_path.is_not(None))
                if args.gid is not None:
                    stmt = stmt.where(Gallery.gid == args.gid)
                elif args.id is not None:
                    stmt = stmt.where(Gallery.id == args.id)
                stmt = stmt.order_by(Gallery.id)
                if args.limit:
                    stmt = stmt.limit(args.limit)

                result = await session.execute(stmt)
                galleries = result.scalars().all()

            logger.info("Found %d galleries to scan", len(galleries))
            for gallery in galleries:
                resolved_path = resolve_gallery_path(gallery.storage_path, settings)
                if not resolved_path or not resolved_path.exists():
                    logger.debug(
                        "Skipping gallery %d: path not found (%s)",
                        gallery.id,
                        gallery.storage_path,
                    )
                    continue

                if resolved_path.is_file() and resolved_path.suffix.lower() in {".cbz", ".zip"}:
                    c, r = await repair_cbz(
                        resolved_path,
                        gallery.gid,
                        gallery.token,
                        client,
                        gallery_id=gallery.id,
                        settings=settings,
                        dry_run=args.dry_run,
                    )
                elif resolved_path.is_dir():
                    c, r = await repair_dir(
                        resolved_path,
                        gallery.gid,
                        gallery.token,
                        client,
                        gallery_id=gallery.id,
                        settings=settings,
                        dry_run=args.dry_run,
                    )
                else:
                    continue

                total_corrupted += c
                total_repaired += r

    finally:
        if client is not None:
            await client.aclose()

    logger.info(
        "Summary: Corrupted pages found: %d, Repaired pages: %d",
        total_corrupted,
        total_repaired,
    )


if __name__ == "__main__":
    asyncio.run(main())
