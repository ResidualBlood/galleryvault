"""Cold archive orchestration: archive runs, source purge and tier reconcile."""

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

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...app.state import app_state
from ...config import get_settings
from ...db.models import DownloadTask, Gallery, GalleryPage, GalleryTag, Tag
from ...db.repositories.base import path_hash
from ...logging import log_extra
from ...scanners.ehviewer import IMAGE_EXTENSIONS, natural_key, parse_spider_info
from ...storage_paths import is_under_cold, resolve_archive_roots
from ._util import _IGNORED_NAMES, _clear_gallery_thumbs
from .pack import (
    ColdAlreadyArchivedError,
    ColdDestinationExistsError,
    cold_pack_gallery,
)
from .paths import _cold_path_filter, select_archive_root

logger = logging.getLogger("galleryvault.services.cold_archive")
from .verify import (
    _is_online_cold_root,
    may_delete_copy,
)


async def reconcile_storage_tier(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    archive_roots: Sequence[Path | str] | None = None,
) -> dict[str, int]:
    """Align ``galleries.storage_tier``/``cold_at`` with the configured cold roots.

    Idempotent set-based reconciliation: three bulk ``UPDATE`` statements run
    entirely in the database (no ORM row hydration), so startup cost stays flat
    for large libraries.  ``cold_at`` is backfilled from ``updated_at`` for
    historical rows, which is only an approximation of when the gallery became
    cold.

    Cold roots are runtime settings, therefore the 0044 migration cannot
    backfill; this pass is the backfill.  Matching follows ``is_under_cold`` for
    the normalized absolute paths stored by the scanner/archive writers.
    """
    counts = {"checked": 0, "fixed_cold": 0, "fixed_hot": 0, "cold_at_filled": 0}
    sf = session_factory or app_state.session_factory
    if sf is None:
        logger.debug("reconcile_storage_tier skipped: no session factory available")
        return counts

    roots = resolve_archive_roots(archive_roots=archive_roots)
    path_filter = _cold_path_filter(roots)
    try:
        async with sf() as session:
            counts["checked"] = int(
                (await session.scalar(select(func.count()).select_from(Gallery))) or 0
            )

            cold_values = {
                "storage_tier": "cold",
                "cold_at": func.coalesce(Gallery.cold_at, Gallery.updated_at, func.now()),
            }
            if path_filter is not None:
                cold_stmt = (
                    update(Gallery)
                    .where(path_filter, Gallery.storage_tier != "cold")
                    .values(**cold_values)
                )
                cold_result = await session.execute(cold_stmt)
                counts["fixed_cold"] = max(int(cold_result.rowcount or 0), 0)

                fill_stmt = (
                    update(Gallery)
                    .where(
                        Gallery.storage_tier == "cold",
                        Gallery.cold_at.is_(None),
                        path_filter,
                    )
                    .values(cold_at=func.coalesce(Gallery.updated_at, func.now()))
                )
                fill_result = await session.execute(fill_stmt)
                counts["cold_at_filled"] = max(int(fill_result.rowcount or 0), 0)

            hot_stmt = update(Gallery).where(Gallery.storage_tier == "cold")
            if path_filter is not None:
                hot_stmt = hot_stmt.where(~path_filter)
            hot_result = await session.execute(
                hot_stmt.values(storage_tier="hot", cold_at=None)
            )
            counts["fixed_hot"] = max(int(hot_result.rowcount or 0), 0)

            if (
                counts["fixed_cold"]
                or counts["fixed_hot"]
                or counts["cold_at_filled"]
            ) and hasattr(session, "commit"):
                await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reconcile_storage_tier failed",
            extra=log_extra(error=type(exc).__name__),
        )
        return counts

    logger.info(
        "reconcile_storage_tier: checked=%d fixed_cold=%d fixed_hot=%d cold_at_filled=%d roots=%s",
        counts["checked"],
        counts["fixed_cold"],
        counts["fixed_hot"],
        counts["cold_at_filled"],
        [str(root) for root in roots],
    )
    return counts


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
        gallery_quality = getattr(gallery, "image_quality", None)
        gallery_uploader = getattr(gallery, "uploader", None)
        gallery_posted_at = getattr(gallery, "posted_at", None)
        gallery_rating = getattr(gallery, "rating", None)
        gallery_file_count = getattr(gallery, "file_count", None)
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
            quality=gallery_quality,
            uploader=gallery_uploader,
            posted_at=gallery_posted_at,
            rating=gallery_rating,
            file_count=gallery_file_count,
            file_size=gallery_file_size or gallery_storage_size,
            delete_source=False,
        )
    except ColdAlreadyArchivedError as exc:
        logger.info("Skipping gallery %s: %s", gallery_id, exc)
        return None
    except ColdDestinationExistsError as exc:
        if exc.dest_path and may_delete_copy(exc.dest_path, source_path):
            logger.info(
                "Adopting existing cold destination for gallery %s: %s",
                gallery_id,
                exc.dest_path,
            )
            dest_path = exc.dest_path
        elif exc.dest_path is not None:
            logger.warning(
                "Refusing to adopt existing cold destination for gallery %s: %s "
                "does not provably cover source %s; keeping source",
                gallery_id,
                exc.dest_path,
                source_path,
            )
            return None
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
        gallery_obj.storage_tier = "cold"
        gallery_obj.cold_at = datetime.now(UTC)
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
    if delete_source:
        if may_delete_copy(dest_path, source_path):
            try:
                from ..storage_usage import safe_stat_size, storage_tracker

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
        elif source_path.resolve() != dest_path.resolve():
            logger.warning(
                "Refusing to delete SSD source %s after archive: cold copy %s "
                "cannot be verified to cover it",
                source_path,
                dest_path,
            )

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

    archived_paths: dict[int, Path] = {}
    for gid, sp in archived_rows:
        if gid is None or not sp:
            continue
        if is_under_cold(sp, cold_roots) and gid not in archived_paths:
            archived_paths[gid] = Path(sp)
    archived_gids = set(archived_paths)
    active_gids = active_dl_gids | _active_gids
    active_paths = {
        Path(p).resolve() for p in active_paths_raw if p
    }

    if not archived_gids and not cold_roots:
        return 0

    online_cold_roots = [r for r in cold_roots if _is_online_cold_root(r)]
    if cold_roots and not online_cold_roots:
        logger.warning(
            "Cold storage roots are offline or unreadable; skipping source purge "
            "to avoid deleting sole sources: %s",
            cold_roots,
        )
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

    from ..storage_usage import safe_stat_size, storage_tracker

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

                    # Check DB archived state or fallback to physical check in cold storage.
                    # A DB path alone is not enough: the cold copy must exist and
                    # provably cover this source before the sole source may be deleted.
                    dest = archived_paths.get(gid)
                    has_covering_copy = may_delete_copy(
                        dest, cur_dir, gid=gid, cold_roots=online_cold_roots
                    )
                    if gid in archived_paths and not has_covering_copy:
                        logger.warning(
                            "Refusing to purge source directory for gallery %s: cold copy %s "
                            "cannot be verified to cover %s",
                            gid,
                            archived_paths[gid],
                            cur_dir,
                        )
                    if has_covering_copy:
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
    from ...app.dependencies import get_current_settings, get_task_manager
    from ..storage_usage import storage_tracker

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
        from ...app.dependencies import get_task_manager

        tm = get_task_manager()
    else:
        tm = task_manager

    sf = session_factory or app_state.session_factory
    if not sf:
        logger.warning("No session factory available for run_cold_archive")
        tm.archive_state["running"] = False
        return

    from ...app.dependencies import get_scan_roots

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
    from ..notifications import _notify_lang, notify_archive

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
