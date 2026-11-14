"""In-memory storage usage snapshot and delta tracking."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class StorageSnapshot:
    bytes: int | None = None
    computed_at: float | None = None
    stale: bool = False
    computing: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "bytes": self.bytes,
            "computed_at": self.computed_at,
            "stale": self.stale,
            "computing": self.computing,
        }


def safe_stat_size(path: Path | str) -> int:
    """Safely calculate total byte size of a file or directory before removal."""
    try:
        p = Path(path)
        if not p.exists():
            return 0
        if p.is_file():
            return p.stat().st_size
        if p.is_dir():
            total = 0
            for root, _dirs, files in os.walk(p, followlinks=False):
                for f in files:
                    try:
                        total += (Path(root) / f).stat().st_size
                    except OSError:
                        pass
            return total
    except OSError:
        pass
    return 0


# ``du`` prints a single size line; cap the consumed output so a future flag
# change (or a pathological path name containing newlines) cannot buffer
# unbounded data into memory.
_DU_OUTPUT_CAP = 64 * 1024


async def _read_capped(stream: asyncio.StreamReader, cap: int) -> tuple[bytes, bool]:
    """Read at most ``cap`` bytes from ``stream``; return ``(data, truncated)``."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            return b"".join(chunks), False
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            return b"".join(chunks), True


async def measure_dir_bytes(path: Path) -> int:
    """Measure directory size via ``du -sbx`` if available, else a bounded walk.

    ``-x`` keeps the measurement on the starting filesystem so a nested cold
    archive mount under the library root is not double counted.
    """
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    du_bin = shutil.which("du")
    if du_bin:
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                du_bin,
                "-sbx",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, truncated = await _read_capped(proc.stdout, _DU_OUTPUT_CAP)
            if truncated:
                logger.debug("du -sbx output exceeded cap; falling back to controlled walk")
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
                stdout = b""
            else:
                await proc.wait()
            if proc.returncode == 0 and stdout:
                parts = stdout.decode(errors="replace").strip().split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
        except asyncio.CancelledError:
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "du -sb failed, falling back to controlled walk", extra={"error": str(exc)}
            )

    # Fallback to controlled walk run in a thread
    def _walk() -> int:
        total = 0
        seen_inodes: set[tuple[int, int]] = set()
        try:
            for root, _dirs, files in os.walk(path, followlinks=False):
                for f in files:
                    try:
                        st = (Path(root) / f).stat()
                    except OSError:
                        continue
                    # Hard links share an inode; ``du`` counts them once.
                    key = (st.st_dev, st.st_ino)
                    if key in seen_inodes:
                        continue
                    seen_inodes.add(key)
                    total += st.st_size
        except OSError:
            pass
        return total

    return await asyncio.to_thread(_walk)


class StorageUsageTracker:
    def __init__(self) -> None:
        self.library = StorageSnapshot(computing=True)
        self.downloads = StorageSnapshot(computing=True)
        self.cache = StorageSnapshot(computing=True)
        self._delta_library = 0
        self._delta_downloads = 0
        self._delta_cache = 0
        self._calibration_task: asyncio.Task | None = None

    def get_library_snapshot(self) -> StorageSnapshot:
        return self.library

    def get_downloads_snapshot(self) -> StorageSnapshot:
        return self.downloads

    def get_cache_snapshot(self) -> StorageSnapshot:
        return self.cache

    def record_library_delta(self, delta: int) -> None:
        if delta == 0:
            return
        if self.library.bytes is not None:
            self.library.bytes = max(0, self.library.bytes + delta)
        self._delta_library += delta

    def record_download_delta(self, delta: int) -> None:
        if delta == 0:
            return
        if self.downloads.bytes is not None:
            self.downloads.bytes = max(0, self.downloads.bytes + delta)
        self._delta_downloads += delta

    def record_cache_delta(self, delta: int) -> None:
        if delta == 0:
            return
        if self.cache.bytes is not None:
            self.cache.bytes = max(0, self.cache.bytes + delta)
        self._delta_cache += delta

    async def calibrate(
        self,
        download_root: Path | str,
        cache_root: Path | str,
        library_root: Path | str | None = None,
    ) -> None:
        """Run low-priority background calibration."""
        from ..app.dependencies import get_task_manager

        tm = get_task_manager()
        async with tm.track_task("calibrate-storage") as tracker:
            dl_path = Path(download_root)
            c_path = Path(cache_root)

            self.downloads.computing = True
            self.cache.computing = True
            self._delta_downloads = 0
            self._delta_cache = 0

            lib_path: Path | None = None
            if library_root:
                lib_path = Path(library_root)
                self.library.computing = True
                self._delta_library = 0

            # Calibrate downloads
            try:
                dl_bytes = await measure_dir_bytes(dl_path)
                self.downloads.bytes = max(0, dl_bytes + self._delta_downloads)
                self.downloads.computed_at = time.time()
                self.downloads.computing = False
                self.downloads.stale = False
            except asyncio.CancelledError:
                self.downloads.computing = False
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("downloads storage calibration failed", extra={"error": str(exc)})
                self.downloads.computing = False

            # Calibrate cache
            try:
                c_bytes = await measure_dir_bytes(c_path)
                self.cache.bytes = max(0, c_bytes + self._delta_cache)
                self.cache.computed_at = time.time()
                self.cache.computing = False
                self.cache.stale = False
            except asyncio.CancelledError:
                self.cache.computing = False
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("cache storage calibration failed", extra={"error": str(exc)})
                self.cache.computing = False

            # Calibrate library if provided
            if lib_path is not None:
                try:
                    lib_bytes = await measure_dir_bytes(lib_path)
                    self.library.bytes = max(0, lib_bytes + self._delta_library)
                    self.library.computed_at = time.time()
                    self.library.computing = False
                    self.library.stale = False
                except asyncio.CancelledError:
                    self.library.computing = False
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning("library storage calibration failed", extra={"error": str(exc)})
                    self.library.computing = False

            tracker.update(done=1, total=1)

    def trigger_calibration(
        self,
        download_root: Path | str,
        cache_root: Path | str,
        library_root: Path | str | None = None,
    ) -> asyncio.Task | None:
        if self._calibration_task and not self._calibration_task.done():
            return self._calibration_task
        try:
            task = asyncio.create_task(self.calibrate(download_root, cache_root, library_root))
            self._calibration_task = task
            return task
        except RuntimeError:
            return None


storage_tracker = StorageUsageTracker()


def _path_info(
    path: object,
    bytes_value: int | None = None,
    computed_at: float | None = None,
    stale: bool = False,
    computing: bool = False,
) -> dict[str, object]:
    import shutil

    root = Path(str(path)) if path else Path()
    exists = bool(path) and root.exists()
    info: dict[str, object] = {
        "path": str(root) if path else "",
        "bytes": bytes_value,
        "exists": exists,
        "computed_at": computed_at,
        "stale": stale,
        "computing": computing,
    }
    if exists:
        try:
            usage = shutil.disk_usage(root)
            info["disk_total"] = int(usage.total)
            info["disk_used"] = int(usage.used)
            info["disk_free"] = int(usage.free)
        except OSError:
            pass
    return info


async def _query_storage_aggregates(
    session: object,
) -> tuple[int, int, int, int, int]:
    from sqlalchemy import func, select

    from ..db.models import Gallery

    cold_galleries = 0
    cold_images = 0
    cold_bytes = 0
    library_galleries = 0
    library_images = 0

    size_col = func.coalesce(Gallery.storage_size, Gallery.file_size)
    # Cold rows are counted by their explicit tier (not a path prefix), so
    # multiple ``archive_roots`` and still-trash-listed cold items (which keep
    # consuming cold space) are all represented.  Hot rows keep the historic
    # expunged/trashed exclusion.
    cold_stmt = select(
        func.count(Gallery.id),
        func.coalesce(func.sum(Gallery.page_count), 0),
        func.coalesce(func.sum(size_col), 0),
    ).where(Gallery.storage_tier == "cold")
    cold_row = (await session.execute(cold_stmt)).first()  # type: ignore[attr-defined]
    if cold_row:
        cold_galleries = int(cold_row[0] or 0)
        cold_images = int(cold_row[1] or 0)
        cold_bytes = int(cold_row[2] or 0)

    lib_stmt = select(
        func.count(Gallery.id),
        func.coalesce(func.sum(Gallery.page_count), 0),
    ).where(
        Gallery.expunged.is_(False),
        Gallery.trashed.is_(False),
        Gallery.storage_tier != "cold",
    )
    lib_row = (await session.execute(lib_stmt)).first()  # type: ignore[attr-defined]
    if lib_row:
        library_galleries = int(lib_row[0] or 0)
        library_images = int(lib_row[1] or 0)

    return cold_galleries, cold_images, cold_bytes, library_galleries, library_images


async def system_storage(session: object | None = None) -> dict[str, object]:
    """Storage dashboard use case shared by the settings router and the bot."""
    from ..app.dependencies import display_title, get_current_settings
    from ..db.repository import GalleryRepository

    settings = get_current_settings()
    cache_root = Path(settings.thumbnail_cache_dir).parent
    cold_root = (getattr(settings, "cold_storage_root", None) or "").strip()
    library_bytes = 0
    cold_bytes = 0
    library_galleries = 0
    library_images = 0
    cold_galleries = 0
    cold_images = 0
    largest: list[dict[str, object]] = []

    try:
        repo = GalleryRepository(session)
        library_bytes = await repo.library_storage_sum()
        (
            cold_galleries,
            cold_images,
            cold_bytes,
            library_galleries,
            library_images,
        ) = await _query_storage_aggregates(session)

        rows = await repo.largest_by_storage(10)
        largest = [
            {
                "id": row.id,
                "title": display_title(row),
                "storage_size": row.storage_size or row.file_size or 0,
                "file_count": row.page_count or 0,
            }
            for row in rows
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("storage dashboard db failed", extra={"error": str(exc)})

    # Ensure background calibration is initiated if not already running and no snapshot exists
    lib_path = (settings.library_roots or [None])[0]
    dl_snap = storage_tracker.get_downloads_snapshot()
    c_snap = storage_tracker.get_cache_snapshot()
    l_snap = storage_tracker.get_library_snapshot()
    if dl_snap.bytes is None or c_snap.bytes is None or (lib_path and l_snap.bytes is None):
        storage_tracker.trigger_calibration(
            settings.download_root, cache_root, library_root=lib_path
        )

    downloads = _path_info(
        settings.download_root,
        bytes_value=dl_snap.bytes,
        computed_at=dl_snap.computed_at,
        stale=dl_snap.stale,
        computing=dl_snap.computing,
    )
    cache = _path_info(
        str(cache_root),
        bytes_value=c_snap.bytes,
        computed_at=c_snap.computed_at,
        stale=c_snap.stale,
        computing=c_snap.computing,
    )
    lib_val = (
        l_snap.bytes if l_snap.bytes is not None else (None if l_snap.computing else library_bytes)
    )
    library = _path_info(
        lib_path,
        bytes_value=lib_val,
        computed_at=l_snap.computed_at,
        stale=l_snap.stale,
        computing=l_snap.computing,
    )
    cold = _path_info(cold_root, bytes_value=cold_bytes)
    cache_thumbs = library_images + cold_images
    library["gallery_count"] = library_galleries
    library["image_count"] = library_images
    cold["gallery_count"] = cold_galleries
    cold["image_count"] = cold_images
    cache["thumbnail_count"] = cache_thumbs
    return {
        "library": library,
        "cold": cold,
        "downloads": downloads,
        "cache": cache,
        "largest": largest,
    }
