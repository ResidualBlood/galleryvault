"""Safe local gallery and file deletion service."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging import log_extra
from ..scanners.ehviewer import IMAGE_EXTENSIONS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..db.models import Gallery
    from .downloader import DownloadResult

logger = logging.getLogger(__name__)


def in_scan_roots(path: Path, roots: list[str]) -> bool:
    """True when ``path`` (resolved) sits under one of the configured scan roots."""
    try:
        resolved = path.resolve()
    except (ValueError, TypeError, OSError):
        return False
    return any(resolved.is_relative_to(Path(root).resolve()) for root in roots)


def delete_local_copy(path: Path, roots: list[str]) -> bool:
    """Delete one on-disk copy (directory or single file) with scan root boundary check."""
    if not in_scan_roots(path, roots):
        logger.error(
            "SECURITY_ALERT: refusal to delete file outside configured scan roots",
            extra={"path": str(path)},
        )
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
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
            try:
                if stale.is_dir():
                    shutil.rmtree(stale)
                else:
                    stale.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info(
            "pruned stale pages after in-place original upgrade",
            extra=log_extra(path=str(path), removed=removed),
        )
    return removed


async def delete_galleries_local(
    session: AsyncSession,
    galleries: list[Gallery],
    *,
    scan_roots: list[str],
    delete_files: bool,
    delete_all_copies: bool,
    delete_fn: Callable[[Path], bool] | None = None,
) -> list[dict]:
    """Delete galleries (DB rows + optional on-disk copies) with safety boundary checks."""
    from ..db.repository import GalleryRepository

    _deleter = delete_fn if delete_fn is not None else (lambda p: delete_local_copy(p, scan_roots))

    results: list[dict] = []
    for gallery in galleries:
        gid = gallery.gid
        targets = [Path(gallery.storage_path)] if gallery.storage_path else []
        if delete_all_copies and gid is not None:
            copies = await GalleryRepository(session).duplicate_copies_for_gid(gid)
            for copy in copies:
                p = Path(str(copy.get("path") or ""))
                if p not in targets:
                    targets.append(p)
        deleted_paths: list[str] = []
        failed_paths: list[str] = []
        if delete_files:
            for target in targets:
                if _deleter(target):
                    deleted_paths.append(str(target))
                else:
                    failed_paths.append(str(target))
        if not delete_files or not failed_paths:
            await session.delete(gallery)
            if delete_all_copies and gid is not None and not failed_paths:
                await GalleryRepository(session).delete_duplicate(gid)
            db_removed = True
        else:
            db_removed = False
        results.append(
            {
                "gallery_id": gallery.id,
                "gid": gid,
                "db_removed": db_removed,
                "deleted_paths": deleted_paths,
                "failed_paths": failed_paths,
            }
        )
    await session.flush()
    return results


async def remove_superseded_copy(
    result: DownloadResult,
    old_path: Path,
    old_pages: int,
    *,
    scan_roots: list[str],
) -> None:
    """Delete a previous physical copy of the same gid after a successful download."""
    import asyncio

    new_path = Path(result.path)
    try:
        if old_path.resolve() == new_path.resolve():
            return
        if not old_path.exists():
            return
        if not in_scan_roots(old_path, scan_roots):
            logger.error(
                "SECURITY_ALERT: refusal to remove superseded copy outside configured scan roots",
                extra=log_extra(gid=result.gid, path=str(old_path)),
            )
            return
        if (result.pages or 0) != old_pages:
            logger.warning(
                "page count mismatch; keeping old copy",
                extra=log_extra(gid=result.gid, old=old_pages, new=result.pages),
            )
            return
        if old_path.is_dir():
            await asyncio.to_thread(shutil.rmtree, old_path)
        else:
            old_path.unlink()
        logger.info(
            "removed superseded copy",
            extra=log_extra(gid=result.gid, path=str(old_path)),
        )
    except OSError as exc:
        logger.warning(
            "failed to remove superseded copy",
            extra=log_extra(gid=result.gid, path=str(old_path), error=str(exc)),
        )
