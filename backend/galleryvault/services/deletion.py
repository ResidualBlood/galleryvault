"""Safe local gallery and file deletion service."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..logging import log_extra
from ..observability import measure_duration
from ..scanners.ehviewer import IMAGE_EXTENSIONS
from .storage_usage import safe_stat_size, storage_tracker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..db.models import Gallery

logger = logging.getLogger(__name__)


def in_scan_roots(path: Path, roots: list[str]) -> bool:
    """True when ``path`` (resolved) sits under one of the configured scan roots."""
    try:
        resolved = path.resolve()
    except (ValueError, TypeError, OSError):
        return False
    return any(resolved.is_relative_to(Path(root).resolve()) for root in roots)


def _is_in_download_root(path: Path) -> bool:
    try:
        from ..app.state import app_state

        dl_root = None
        downloader_root = getattr(app_state.downloader, "root", None)
        if downloader_root is not None:
            dl_root = Path(downloader_root).resolve()
        elif app_state.settings is not None and getattr(app_state.settings, "download_root", None):
            dl_root = Path(app_state.settings.download_root).resolve()
        if dl_root is None:
            return False
        return path.resolve().is_relative_to(dl_root)
    except (AttributeError, ValueError, TypeError, OSError):
        return False


def delete_local_copy(path: Path, roots: list[str] | None = None) -> bool:
    """Delete one on-disk copy (directory or single file) with scan root boundary check."""
    scan_roots = roots if roots is not None else _scan_roots_default()
    if not in_scan_roots(path, scan_roots):
        logger.error(
            "SECURITY_ALERT: refusal to delete file outside configured scan roots",
            extra={"path": str(path)},
        )
        return False
    in_dl = _is_in_download_root(path)
    size_to_subtract = safe_stat_size(path) if in_dl else 0
    try:
        with measure_duration("gv_disk_io_duration_seconds", {"op": "delete_copy"}):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        if size_to_subtract > 0:
            storage_tracker.record_download_delta(-size_to_subtract)
        return True
    except OSError:
        logger.warning("gallery file removal failed", extra={"path": str(path)})
        return False


def prune_merged_stale_pages(path: Path, new_files: tuple[str, ...] = ()) -> int:
    """Prune superseded images when an original quality download merges in-place."""
    if not path.is_dir():
        return 0

    fresh = set(new_files)
    by_stem: dict[str, list[Path]] = {}
    for item in path.iterdir():
        if (
            item.is_file()
            and not item.name.startswith(".")
            and item.suffix.casefold() in IMAGE_EXTENSIONS
        ):
            by_stem.setdefault(item.stem, []).append(item)
    removed = 0
    for siblings in by_stem.values():
        if not any(sib.name in fresh for sib in siblings):
            continue
        for stale in siblings:
            if stale.name in fresh:
                continue
            in_dl = _is_in_download_root(stale)
            stale_sz = safe_stat_size(stale) if in_dl else 0
            try:
                if stale.is_dir():
                    shutil.rmtree(stale)
                else:
                    stale.unlink()
                if stale_sz > 0:
                    storage_tracker.record_download_delta(-stale_sz)
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info(
            "pruned stale pages after in-place original upgrade",
            extra=log_extra(path=str(path), removed=removed),
        )
    return removed


_COLLAPSE_ORIGINAL_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".avif"}


def collapse_same_stem_pages(path: Path) -> int:
    """Collapse same-stem image variants in a gallery directory.

    Keeps the first non-empty original format (.jpg/.jpeg/.png/.gif/.avif), or
    the largest file if no original format is valid, unlinking any duplicates.
    """
    if not path.is_dir():
        return 0

    by_stem: dict[str, list[Path]] = {}
    for item in path.iterdir():
        if (
            item.is_file()
            and not item.name.startswith(".")
            and item.suffix.casefold() in IMAGE_EXTENSIONS
        ):
            by_stem.setdefault(item.stem, []).append(item)

    removed = 0
    for siblings in by_stem.values():
        if len(siblings) < 2:
            continue
        sorted_sibs = sorted(siblings, key=lambda p: p.name)
        keeper: Path | None = None
        for sib in sorted_sibs:
            try:
                if sib.suffix.casefold() in _COLLAPSE_ORIGINAL_SUFFIXES and sib.stat().st_size > 0:
                    keeper = sib
                    break
            except OSError:
                continue

        if keeper is None:
            def _file_size(p: Path) -> int:
                try:
                    return p.stat().st_size
                except OSError:
                    return -1

            keeper = max(sorted_sibs, key=_file_size)

        for stale in sorted_sibs:
            if stale == keeper:
                continue
            in_dl = _is_in_download_root(stale)
            stale_sz = safe_stat_size(stale) if in_dl else 0
            try:
                stale.unlink()
                if stale_sz > 0:
                    storage_tracker.record_download_delta(-stale_sz)
                removed += 1
            except OSError:
                pass

    if removed:
        logger.info(
            "collapsed same-stem duplicate pages",
            extra=log_extra(path=str(path), removed=removed),
        )
    return removed


def _scan_roots_default() -> list[str]:
    from ..app.dependencies import get_scan_roots

    return get_scan_roots()


async def delete_galleries_local(
    gallery_ids: list[int] | list[Gallery] | AsyncSession,
    galleries: list[Gallery] | list[int] | None = None,
    *,
    session: AsyncSession | None = None,
    session_factory: Callable[[], Any] | None = None,
    scan_roots: list[str] | None = None,
    delete_files: bool,
    delete_all_copies: bool,
    delete_fn: Callable[[Path], bool] | None = None,
    trash: bool | None = None,
) -> list[dict]:
    """Delete galleries (DB rows + optional on-disk copies) with safety boundary checks.

    Phase 1: Query metadata and targets in a short read session.
    Phase 2: Perform disk I/O outside of any DB session or transaction.
    Phase 3: Persist DB status (trash/delete) in a short write transaction.
    """
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime

    from sqlalchemy import select

    from ..db.models import DuplicateRecord, Gallery
    from ..db.repositories.base import path_hash
    from ..db.repository import GalleryRepository, _chunked

    provided_session: AsyncSession | None = None
    if galleries is not None and not isinstance(gallery_ids, (list, tuple, set)):
        provided_session = gallery_ids  # type: ignore[assignment]
        raw_items = galleries
    elif isinstance(gallery_ids, (list, tuple, set)):
        provided_session = session
        raw_items = gallery_ids
    else:
        provided_session = gallery_ids  # type: ignore[assignment]
        raw_items = galleries or []

    raw_ids = [item.id if hasattr(item, "id") else int(item) for item in raw_items]
    ids = list(dict.fromkeys(raw_ids))
    if not ids:
        return []

    if session_factory is not None:
        get_cm = session_factory
    elif provided_session is not None:
        @asynccontextmanager
        async def _provided_cm():
            yield provided_session

        get_cm = _provided_cm
    else:
        from ..app.state import app_state

        get_cm = app_state.session_factory
        if get_cm is None:
            raise RuntimeError("Database session factory is not configured")

    deleter_fn = delete_local_copy

    def _deleter(p: Path) -> bool:
        if delete_fn is not None:
            return delete_fn(p)
        try:
            return deleter_fn(p, scan_roots)
        except TypeError:
            return deleter_fn(p)

    # Phase 1: Query metadata and duplicate targets in a short read session
    items_meta: list[dict[str, Any]] = []
    galleries_map: dict[int, Gallery] = {}
    async with get_cm() as sess:
        repo = GalleryRepository(sess)
        for chunk in _chunked(ids):
            stmt = select(Gallery).where(Gallery.id.in_(chunk))
            rows = (await sess.scalars(stmt)).all()
            for g in rows:
                galleries_map[g.id] = g

        for item in raw_items:
            if hasattr(item, "id") and item.id not in galleries_map:
                galleries_map[item.id] = item

        for gid_val in ids:
            gallery = galleries_map.get(gid_val)
            if gallery is None:
                continue
            gid = gallery.gid
            targets = [Path(gallery.storage_path)] if gallery.storage_path else []
            if delete_all_copies and gid is not None:
                copies = await repo.duplicate_copies_for_gid(gid)
                for copy in copies:
                    p = Path(str(copy.get("path") or ""))
                    if p not in targets:
                        targets.append(p)
            items_meta.append({
                "gallery_id": gallery.id,
                "gid": gid,
                "storage_path": gallery.storage_path,
                "targets": targets,
            })

    if not items_meta:
        return []

    # Phase 2: Perform disk I/O outside of any DB session or transaction
    io_results: list[dict[str, Any]] = []
    for meta in items_meta:
        targets = meta["targets"]
        deleted_paths: list[str] = []
        failed_paths: list[str] = []
        if delete_files:
            for target in targets:
                if _deleter(target):
                    deleted_paths.append(str(target))
                else:
                    failed_paths.append(str(target))
        io_results.append({
            "gallery_id": meta["gallery_id"],
            "gid": meta["gid"],
            "storage_path": meta["storage_path"],
            "targets": targets,
            "deleted_paths": deleted_paths,
            "failed_paths": failed_paths,
        })

    # Phase 3: Persist DB status (trash/delete) in a short write transaction
    auto_trash = trash
    results: list[dict[str, Any]] = []
    async with get_cm() as sess:
        begin_ctx = sess.begin() if hasattr(sess, "begin") and callable(sess.begin) else None
        if begin_ctx is not None and hasattr(begin_ctx, "__aenter__"):
            cm_begin = begin_ctx
        else:
            @asynccontextmanager
            async def _noop_begin():
                yield sess

            cm_begin = _noop_begin()

        async with cm_begin:
            repo = GalleryRepository(sess)
            for item in io_results:
                gallery_id = item["gallery_id"]
                gid = item["gid"]
                storage_path = item["storage_path"]
                targets = item["targets"]
                deleted_paths = item["deleted_paths"]
                failed_paths = item["failed_paths"]

                gallery = await sess.get(Gallery, gallery_id)
                if gallery is None and galleries_map.get(gallery_id) is not None:
                    gallery = galleries_map[gallery_id]

                should_trash = auto_trash
                if should_trash is None:
                    should_trash = not delete_files

                if should_trash:
                    if gallery is not None:
                        gallery.trashed = True
                        gallery.trashed_at = datetime.now(UTC)
                        gallery.updated_at = datetime.now(UTC)
                    db_removed = False
                    trashed = True
                else:
                    if not delete_files or not failed_paths:
                        if gallery is not None:
                            await sess.delete(gallery)
                        if delete_all_copies and gid is not None and not failed_paths:
                            await repo.delete_duplicate(gid)
                        db_removed = True
                        trashed = False
                    else:
                        db_removed = False
                        trashed = False
                        if delete_all_copies and deleted_paths and gid is not None:
                            dup_row = await sess.get(DuplicateRecord, gid)
                            if dup_row is not None:
                                    deleted_resolved = {Path(p).resolve() for p in deleted_paths}
                                    remaining_copies = [
                                        c for c in (dup_row.copies or [])
                                        if Path(str(c.get("path") or "")).resolve() not in deleted_resolved
                                    ]
                                    if not remaining_copies:
                                        await sess.delete(dup_row)
                                    else:
                                        dup_row.copies = remaining_copies
                                        if (
                                            dup_row.winner_path
                                            and Path(dup_row.winner_path).resolve() in deleted_resolved
                                        ):
                                            dup_row.winner_path = str(remaining_copies[0].get("path") or "")
                                        dup_row.updated_at = datetime.now(UTC)

                        if storage_path and gallery is not None:
                            gallery_resolved = Path(storage_path).resolve()
                            deleted_resolved = {Path(p).resolve() for p in deleted_paths}
                            if gallery_resolved in deleted_resolved:
                                failed_resolved = [Path(p).resolve() for p in failed_paths]
                                surviving = [p for p in targets if p.resolve() in failed_resolved]
                                if not surviving and failed_paths:
                                    surviving = [Path(failed_paths[0])]
                                if surviving:
                                    new_path = surviving[0]
                                    gallery.storage_path = str(new_path)
                                    gallery.path_hash = path_hash(new_path)
                                    gallery.updated_at = datetime.now(UTC)
                results.append({
                    "gallery_id": gallery_id,
                    "gid": gid,
                    "db_removed": db_removed,
                    "trashed": trashed,
                    "deleted_paths": deleted_paths,
                    "failed_paths": failed_paths,
                })
            await sess.flush()
    return results


async def remove_superseded_copy(
    result: Any,
    old_path: Any,
    old_pages: int,
    *,
    scan_roots: list[str] | None = None,
) -> None:
    """Delete a previous physical copy of the same gid after a successful download."""
    import asyncio

    if hasattr(old_path, "storage_path"):
        target_path = Path(str(old_path.storage_path or ""))
    else:
        target_path = Path(str(old_path))

    new_path = Path(result.path)
    try:
        if target_path.resolve() == new_path.resolve():
            return
        if not target_path.exists():
            return
        if scan_roots is not None and not in_scan_roots(target_path, scan_roots):
            logger.error(
                "SECURITY_ALERT: refusal to remove superseded copy outside configured scan roots",
                extra=log_extra(gid=result.gid, path=str(target_path)),
            )
            return
        if (result.pages or 0) != old_pages:
            logger.warning(
                "page count mismatch; keeping old copy",
                extra=log_extra(gid=result.gid, old=old_pages, new=result.pages),
            )
            return
        in_dl = _is_in_download_root(target_path)
        sz = safe_stat_size(target_path) if in_dl else 0
        if target_path.is_dir():
            await asyncio.to_thread(shutil.rmtree, target_path)
        else:
            target_path.unlink()
        if sz > 0:
            storage_tracker.record_download_delta(-sz)
        logger.info(
            "removed superseded copy",
            extra=log_extra(gid=result.gid, path=str(target_path)),
        )
    except OSError as exc:
        logger.warning(
            "failed to remove superseded copy",
            extra=log_extra(gid=result.gid, path=str(target_path), error=str(exc)),
        )
