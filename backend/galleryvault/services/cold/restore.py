"""Cold archive restore: extract cold packs back into the download root."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...app.state import app_state
from ...config import get_settings
from ...db.models import DownloadTask, Gallery, GalleryPage
from ...db.repositories.base import path_hash
from ...metadata.sidecar import read_galleryvault_json
from ...scanners.ehviewer import IMAGE_EXTENSIONS, natural_key
from ...storage_paths import is_under_cold, resolve_archive_roots
from ._util import _IGNORED_NAMES, _clear_gallery_thumbs, page_archive_name
from .orchestrate import (
    _active_gids,
    _gallery_locks,
    _gallery_locks_guard,
    _get_gallery_lock,
)
from .pack import ColdStorageError, _collect_pages_from_dir
from .paths import safe_title
from .verify import _count_source_image_pages, _is_online_cold_root, may_delete_copy

logger = logging.getLogger("galleryvault.services.cold_archive")


def _extract_cold_pack(cold_path: Path, partial_dir: Path) -> list[str]:
    """Extract a cold CBZ/directory into ``partial_dir`` using canonical page names.

    Cold packs are self-contained (``0001.ext`` pages plus ``ComicInfo.xml`` and
    ``.galleryvault.json``), so restoring re-normalises the page names instead of
    trying to recover the original hot filenames. Returns the sorted page names.
    """
    if partial_dir.exists():
        shutil.rmtree(partial_dir, ignore_errors=True)
    partial_dir.mkdir(parents=True, exist_ok=True)

    pages: list[str] = []
    sidecars: dict[str, bytes] = {}

    if cold_path.is_file() and cold_path.suffix.lower() in {".cbz", ".zip"}:
        with zipfile.ZipFile(cold_path, "r") as zf:
            members = [
                info
                for info in zf.infolist()
                if not info.is_dir()
                and not Path(info.filename).name.startswith(".")
                and Path(info.filename).name.lower() not in _IGNORED_NAMES
                and Path(info.filename).name.lower() not in {"comicinfo.xml", ".galleryvault.json"}
                and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
            ]
            members.sort(key=lambda m: natural_key(Path(m.filename).name))
            for idx, member in enumerate(members, start=1):
                name = page_archive_name(idx, Path(member.filename).suffix)
                with zf.open(member) as src, open(partial_dir / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pages.append(name)
            for sidecar in ("ComicInfo.xml", ".galleryvault.json"):
                try:
                    sidecars[sidecar] = zf.read(sidecar)
                except KeyError:
                    continue
    elif cold_path.is_dir():
        page_files = _collect_pages_from_dir(cold_path)
        for idx, page_file in enumerate(page_files, start=1):
            name = page_archive_name(idx, page_file.suffix)
            shutil.copy2(page_file, partial_dir / name)
            pages.append(name)
        for sidecar in ("ComicInfo.xml", ".galleryvault.json"):
            sidecar_path = cold_path / sidecar
            if sidecar_path.is_file():
                sidecars[sidecar] = sidecar_path.read_bytes()
    else:
        raise ColdStorageError(f"Unsupported cold pack format: {cold_path}")

    if not pages:
        raise ColdStorageError(f"No image pages found in cold pack: {cold_path}")

    for sidecar, payload in sidecars.items():
        (partial_dir / sidecar).write_bytes(payload)
    return pages


def _remove_cold_pack(cold_path: Path, keep: Path) -> bool:
    """Drop the cold pack only when the restored ``keep`` copy provably covers it."""
    if not may_delete_copy(keep, cold_path):
        logger.warning(
            "Refusing to remove cold pack %s: restored copy %s cannot be verified to cover it",
            cold_path,
            keep,
        )
        return False
    if cold_path.is_dir():
        shutil.rmtree(cold_path)
    elif cold_path.exists():
        cold_path.unlink()
    return True


async def _do_unarchive_locked(
    gallery_id: int,
    *,
    download_root: Path | str | None = None,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> Path | None:
    if session_factory is None:
        return None
    roots = resolve_archive_roots(archive_roots=archive_roots, cold_root=cold_root)
    if not roots:
        logger.warning("No archive roots configured, cannot unarchive gallery %s", gallery_id)
        return None

    settings = app_state.settings or get_settings()
    dl_root = Path(download_root or getattr(settings, "download_root", "/downloads")).resolve()

    async with session_factory() as session:
        gallery = await session.get(Gallery, gallery_id)
        if not gallery or gallery.trashed:
            return None
        if getattr(gallery, "storage_tier", "hot") != "cold":
            logger.info("Gallery %s is not cold; unarchive skipped", gallery_id)
            return None
        cold_path = Path(gallery.storage_path).resolve() if gallery.storage_path else None
        if cold_path is None:
            logger.warning("Gallery %s has no storage_path; unarchive skipped", gallery_id)
            return None
        gallery_title = gallery.title
        gallery_gid = gallery.gid
        old_page_count = gallery.page_count

    if not is_under_cold(cold_path, roots):
        logger.warning(
            "Gallery %s storage path %s is outside cold roots; unarchive skipped",
            gallery_id,
            cold_path,
        )
        return None
    if not cold_path.exists():
        logger.warning("Cold pack %s is offline/missing; unarchive skipped", cold_path)
        return None
    cold_root_online = any(
        cold_path == root or cold_path.is_relative_to(root)
        for root in roots
        if _is_online_cold_root(root)
    )
    if not cold_root_online:
        logger.warning("Cold root for %s is offline; unarchive skipped", cold_path)
        return None

    cold_size = int(getattr(gallery, "storage_size", 0) or 0)
    if cold_size <= 0:
        try:
            if cold_path.is_file():
                cold_size = cold_path.stat().st_size
            else:
                cold_size = sum(f.stat().st_size for f in cold_path.rglob("*") if f.is_file())
        except OSError:
            logger.warning("Cannot stat cold pack %s; unarchive skipped", cold_path)
            return None

    try:
        dl_root.mkdir(parents=True, exist_ok=True)
        if not os.access(dl_root, os.W_OK):
            logger.warning("Download root %s is not writable; unarchive skipped", dl_root)
            return None
    except OSError as exc:
        logger.warning("Download root %s unavailable: %s", dl_root, exc)
        return None

    required_free = int(cold_size * 1.2)
    try:
        free = shutil.disk_usage(dl_root).free
    except OSError as exc:
        logger.warning("Cannot determine free space for %s: %s", dl_root, exc)
        return None
    if free < required_free:
        logger.warning(
            "Insufficient free space for unarchive of gallery %s (need %s, free %s)",
            gallery_id,
            required_free,
            free,
        )
        return None

    if gallery_gid is not None:
        target_name = f"{gallery_gid}-{safe_title(gallery_title)}"
    else:
        target_name = safe_title(cold_path.stem if cold_path.is_file() else cold_path.name)
    target = dl_root / target_name
    if target.exists():
        logger.warning("Unarchive target already exists: %s", target)
        return None

    target_hash = path_hash(target)
    async with session_factory() as session:
        conflict = await session.scalar(
            select(Gallery.id).where(
                Gallery.path_hash == target_hash,
                Gallery.id != gallery_id,
            )
        )
    if conflict is not None:
        logger.warning(
            "Unarchive target %s path_hash is used by gallery %s; skipped",
            target,
            conflict,
        )
        return None

    partial = target.parent / f"{target.name}.partial"
    try:
        page_names = await asyncio.to_thread(_extract_cold_pack, cold_path, partial)
        expected_pages = _count_source_image_pages(cold_path)
        if expected_pages is not None and len(page_names) != expected_pages:
            raise ColdStorageError(
                f"Extracted page count {len(page_names)} != cold pack {expected_pages}"
            )
        partial.replace(target)
    except Exception:
        if partial.is_dir():
            shutil.rmtree(partial, ignore_errors=True)
        elif partial.exists():
            partial.unlink(missing_ok=True)
        raise

    try:
        dest_stat = target.stat()
        new_mtime_ns = dest_stat.st_mtime_ns
        new_size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        new_sig = hashlib.sha256(f"{new_mtime_ns}:{new_size}".encode()).hexdigest()
        gv_data = read_galleryvault_json(target) or {}
        p_tokens = gv_data.get("p_tokens") if isinstance(gv_data, dict) else None
    except Exception:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink(missing_ok=True)
        raise

    async def _apply_unarchive_db_updates(s: AsyncSession) -> bool:
        gallery_obj = await s.get(Gallery, gallery_id)
        if not gallery_obj:
            logger.warning("Gallery was deleted before unarchive DB update")
            return False

        gallery_obj.storage_path = str(target)
        gallery_obj.storage_type = "folder"
        gallery_obj.path_hash = path_hash(target)
        gallery_obj.storage_mtime_ns = new_mtime_ns
        gallery_obj.storage_size = new_size
        gallery_obj.storage_signature = new_sig
        gallery_obj.page_count = len(page_names)
        gallery_obj.cover_path = page_names[0]
        gallery_obj.storage_tier = "hot"
        gallery_obj.cold_at = None
        if p_tokens:
            source_meta = dict(getattr(gallery_obj, "source_meta", None) or {})
            source_meta["p_tokens"] = list(p_tokens)
            gallery_obj.source_meta = source_meta
        gallery_obj.updated_at = datetime.now(UTC)

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
        try:
            if hasattr(session, "begin"):
                async with session.begin():
                    if not await _apply_unarchive_db_updates(session):
                        shutil.rmtree(target, ignore_errors=True)
                        return None
            else:
                if not await _apply_unarchive_db_updates(session):
                    shutil.rmtree(target, ignore_errors=True)
                    return None
                if hasattr(session, "commit"):
                    await session.commit()
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

    # DB commit succeeded: the move is now durable, drop the cold copy.
    try:
        _remove_cold_pack(cold_path, target)
    except OSError as exc:
        logger.warning("Failed to remove cold pack %s after unarchive: %s", cold_path, exc)

    if old_page_count != len(page_names):
        _clear_gallery_thumbs(gallery_id)

    try:
        from ..storage_usage import safe_stat_size, storage_tracker

        moved = safe_stat_size(target)
        if moved > 0:
            storage_tracker.record_download_delta(moved)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Storage delta for unarchive failed: %s", exc)

    logger.info("Unarchived gallery %s from %s to %s", gallery_id, cold_path, target)
    return target


async def unarchive_one(
    gallery_id: int,
    *,
    download_root: Path | str | None = None,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> Path | None:
    """Move a cold gallery back to the download root (Q8: move, not copy).

    Preconditions (tier cold, cold root online, no active download/archive for
    the same gid, writable download root, free space, target free) are checked
    before any disk write. Extraction happens in ``<target>.partial``; the DB
    pointer is switched in one short transaction and only then is the cold pack
    removed. Any failure before the commit leaves both the cold pack and the DB
    row untouched.
    """
    roots = resolve_archive_roots(archive_roots=archive_roots, cold_root=cold_root)
    if not roots:
        logger.warning("Cold storage root not configured, cannot unarchive gallery %s", gallery_id)
        return None

    sf = session_factory or app_state.session_factory
    if not sf:
        logger.warning("No session factory available for unarchive_one")
        return None

    async with sf() as session:
        gallery = await session.get(Gallery, gallery_id)
        if not gallery:
            gallery = await session.scalar(select(Gallery).where(Gallery.gid == gallery_id))
            if not gallery:
                logger.warning("Gallery %s not found for unarchive", gallery_id)
                return None
        target_id = gallery.id
        target_gid = gallery.gid

    if target_gid is not None:
        if target_gid in _active_gids:
            logger.info("Gallery gid %s is already in progress, skipping unarchive", target_gid)
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
                    "Gallery %s (gid=%s) has active download task %s, skipping unarchive",
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
            return await _do_unarchive_locked(
                target_id,
                download_root=download_root,
                archive_roots=roots,
                session_factory=sf,
            )
    finally:
        if gid_to_unlock is not None:
            _active_gids.discard(gid_to_unlock)
        async with _gallery_locks_guard:
            existing_lock = _gallery_locks.get(target_id)
            if existing_lock is not None and not existing_lock.locked():
                _gallery_locks.pop(target_id, None)


async def run_unarchive(
    gallery_ids: Sequence[int],
    *,
    download_root: Path | str | None = None,
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    task_manager: Any = None,
) -> None:
    """Batch cold→hot restore, cancellable between galleries."""
    ids = list(dict.fromkeys(int(gid) for gid in gallery_ids))
    if task_manager is None:
        from ...app.dependencies import get_task_manager

        tm = get_task_manager()
    else:
        tm = task_manager

    sf = session_factory or app_state.session_factory
    if not sf:
        logger.warning("No session factory available for run_unarchive")
        tm.unarchive_state["running"] = False
        return

    done = skipped = failed = 0
    was_cancelled = False
    async with tm.track_task("unarchive", cancellable=True) as tracker:
        tracker.update(done=0, total=len(ids), skipped=0, failed=0, last_error=None)
        for gallery_id in ids:
            if tm.is_cancelled("unarchive"):
                was_cancelled = True
                break
            try:
                result = await unarchive_one(
                    gallery_id,
                    download_root=download_root,
                    archive_roots=archive_roots,
                    cold_root=cold_root,
                    session_factory=sf,
                )
                if result is not None:
                    done += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                tracker.update(last_error=str(exc))
                logger.exception("Failed to unarchive gallery %s", gallery_id)
            tracker.update(done=done, skipped=skipped, failed=failed)

        reason = f"done {done} / skip {skipped} / fail {failed}"
        if was_cancelled:
            reason += " (cancelled)"
        tracker.update(reason=reason)
