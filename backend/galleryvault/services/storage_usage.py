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


async def measure_dir_bytes(path: Path) -> int:
    """Measure directory size via du -sb if available, falling back to controlled walk."""
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
                "-sb",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                parts = stdout.decode().strip().split()
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
            logger.debug("du -sb failed, falling back to controlled walk", extra={"error": str(exc)})

    # Fallback to controlled walk run in a thread
    def _walk() -> int:
        total = 0
        try:
            for root, _dirs, files in os.walk(path, followlinks=False):
                for f in files:
                    try:
                        total += (Path(root) / f).stat().st_size
                    except OSError:
                        continue
        except OSError:
            pass
        return total

    return await asyncio.to_thread(_walk)


class StorageUsageTracker:
    def __init__(self) -> None:
        self.downloads = StorageSnapshot(computing=True)
        self.cache = StorageSnapshot(computing=True)
        self._delta_downloads = 0
        self._delta_cache = 0
        self._calibration_task: asyncio.Task | None = None

    def get_downloads_snapshot(self) -> StorageSnapshot:
        return self.downloads

    def get_cache_snapshot(self) -> StorageSnapshot:
        return self.cache

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

    async def calibrate(self, download_root: Path | str, cache_root: Path | str) -> None:
        """Run low-priority background calibration."""
        dl_path = Path(download_root)
        c_path = Path(cache_root)

        self.downloads.computing = True
        self.cache.computing = True
        self._delta_downloads = 0
        self._delta_cache = 0

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

    def trigger_calibration(
        self, download_root: Path | str, cache_root: Path | str
    ) -> asyncio.Task | None:
        if self._calibration_task and not self._calibration_task.done():
            return self._calibration_task
        try:
            task = asyncio.create_task(self.calibrate(download_root, cache_root))
            self._calibration_task = task
            return task
        except RuntimeError:
            return None


storage_tracker = StorageUsageTracker()
