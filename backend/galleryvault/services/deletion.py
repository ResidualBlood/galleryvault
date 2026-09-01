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


def delete_local_copy(path: Path, roots: list[str] | None = None) -> bool:
    """Delete one on-disk copy (directory or single file) with scan root boundary check."""
    scan_roots = roots if roots is not None else _scan_roots_default()
    if not in_scan_roots(path, scan_roots):
        logger.error(
            "SECURITY_ALERT: refusal to delete file outside configured scan roots",
            extra={"path": str(path)},
        )
        return False
    try:
        with measure_duration("gv_disk_io_duration_seconds", {"op": "delete_copy"}):
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


def _scan_roots_default() -> list[str]:
    from ..app import main
    fn = getattr(main, "_scan_roots", None)
    if fn is not None:
        try:
            return fn()
        except Exception:  # noqa: S110, BLE001
            pass
    from ..app.state import app_state
    from ..config import get_settings
    settings = app_state.settings or get_settings()
    roots = list(settings.library_roots)
    if settings.download_root and settings.download_root not in roots:
        roots.append(settings.download_root)
    return roots


async def delete_galleries_local(
    session: AsyncSession,
    galleries: list[Gallery],
    *,
    scan_roots: list[str] | None = None,
    delete_files: bool,
    delete_all_copies: bool,
    delete_fn: Callable[[Path], bool] | None = None,
) -> list[dict]:
    """Delete galleries (DB rows + optional on-disk copies) with safety boundary checks."""
    from ..app import main
    from ..db.repository import GalleryRepository

    deleter_fn = getattr(main, "_delete_local_copy", delete_local_copy)

    def _deleter(p: Path) -> bool:
        if delete_fn is not None:
            return delete_fn(p)
        try:
            return deleter_fn(p, scan_roots)
        except TypeError:
            return deleter_fn(p)

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
        if target_path.is_dir():
            await asyncio.to_thread(shutil.rmtree, target_path)
        else:
            target_path.unlink()
        logger.info(
            "removed superseded copy",
            extra=log_extra(gid=result.gid, path=str(target_path)),
        )
    except OSError as exc:
        logger.warning(
            "failed to remove superseded copy",
            extra=log_extra(gid=result.gid, path=str(target_path), error=str(exc)),
        )
