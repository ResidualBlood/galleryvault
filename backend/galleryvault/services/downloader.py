"""Concurrent, atomic Ehviewer directory downloader."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..logging import log_extra
from .eh_client import GalleryData

logger = logging.getLogger(__name__)

ProgressCallback = "callable[[int, int], object]"


class DownloadCancelledError(Exception):
    """Raised when a pending/active download is cancelled mid-flight."""


@dataclass(frozen=True)
class DownloadTask:
    gid: int
    token: str
    title: str
    id: int | None = None
    max_retries: int = 3
    mode: str | None = None
    category: str = "other"
    max_pages: int | None = None


@dataclass(frozen=True)
class DownloadResult:
    gid: int
    path: Path
    pages: int
    category: str = "other"
    title: str | None = None
    title_jpn: str | None = None
    token: str | None = None
    tags: tuple[tuple[str, str], ...] = ()


class DownloadClient(Protocol):
    async def fetch_gallery(
        self, gid: int, token: str, max_pages: int | None = None
    ) -> GalleryData: ...
    async def download_image(self, url: str) -> bytes: ...


def safe_title(title: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", title).strip(" .")
    return value[:180] or "gallery"


def gallery_dirname(gid: int, title_jpn: str | None, title: str | None) -> str:
    """Ehviewer-style download folder: ``<gid>-<japanese title>``.

    Matches Ehviewer's ``gid + "-" + getSuitableTitle`` default so downloaded
    directories look like the examples in ``TEMP``.
    """
    suitable = (title_jpn or title or "").strip()
    if suitable:
        return f"{gid}-{safe_title(suitable)}"
    return str(gid)


def _existing_page_file(directory: Path, index: int) -> Path | None:
    """Return the already-downloaded page file for ``index`` (0-based) if present."""
    try:
        matches = list(directory.glob(f"{index + 1:08d}.*"))
    except OSError:
        return None
    for candidate in matches:
        if candidate.is_file() and candidate.stat().st_size:
            return candidate
    return None


class Downloader:
    def __init__(
        self,
        client: DownloadClient,
        root: str | Path,
        *,
        concurrency: int = 2,
        page_concurrency: int = 8,
    ) -> None:
        self.client, self.root = client, Path(root)
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.page_concurrency = max(1, min(page_concurrency, 16))
        self._gids: set[int] = set()
        self._lock = asyncio.Lock()
        # Live speed/ETA stats per gallery, keyed by gid, fed by every page
        # write and consumed by the downloads API (Downloader.speed_stats).
        self._stats: dict[int, dict[str, object]] = {}
        self._stats_lock = asyncio.Lock()

    async def speed_stats(
        self, gid: int, *, current_page: int = 0, total_pages: int | None = None
    ) -> dict[str, object] | None:
        """Compute download speed (bytes/s) and ETA (seconds) for ``gid``."""
        import time as _time

        stat = self._stats.get(int(gid))
        if stat is None:
            return None
        elapsed = max(1.0, _time.time() - float(stat["started_at"]))
        speed = float(stat["bytes"]) / elapsed
        done = max(1, int(stat.get("done") or 1))
        remaining = max(0, (int(total_pages or 0) - int(current_page)))
        eta = remaining * (elapsed / done)
        return {"speed": round(speed, 1), "eta_seconds": round(eta, 1)}

    async def _record_bytes(self, gid: int, count: int, done: int) -> None:
        import time as _time

        async with self._stats_lock:
            stat = self._stats.setdefault(
                int(gid), {"bytes": 0, "started_at": _time.time(), "done": 0}
            )
            stat["bytes"] = int(stat["bytes"]) + count
            stat["done"] = int(stat.get("done") or 0) + done

    def _clear_stats(self, gid: int) -> None:
        self._stats.pop(int(gid), None)

    async def enqueue(self, task: DownloadTask) -> bool:
        async with self._lock:
            if task.gid in self._gids:
                return False
            self._gids.add(task.gid)
        return True

    async def execute(
        self, task: DownloadTask, progress: ProgressCallback | None = None
    ) -> DownloadResult:
        if not await self.enqueue(task):
            raise RuntimeError("an active download already exists for this gid")
        try:
            async with self.semaphore:
                return await self._execute_with_retries(task, progress)
        finally:
            async with self._lock:
                self._gids.discard(task.gid)
            self._clear_stats(task.gid)

    async def _execute_with_retries(
        self, task: DownloadTask, progress: ProgressCallback | None = None
    ) -> DownloadResult:
        # Retry ownership belongs to the persistent DownloadManager. A call to
        # execute is exactly one attempt, otherwise attempt rows lie after a restart.
        if task.id is not None:
            return await self._download_once(task, progress)
        # Direct, non-persistent callers retain the small convenience API. The
        # application worker always supplies a persistent task id above.
        last: Exception | None = None
        for _ in range(min(max(1, task.max_retries), 3)):
            try:
                return await self._download_once(task, progress)
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise RuntimeError("download failed after three attempts") from last

    async def _download_once(
        self, task: DownloadTask, progress: ProgressCallback | None = None
    ) -> DownloadResult:
        # Pass max_pages through to fetch_gallery so a sample download only
        # resolves the pages it actually needs (otherwise every page's URL is
        # fetched from ExHentai via showpage before the list is truncated).
        gallery = await self.client.fetch_gallery(
            task.gid, task.token, max_pages=task.max_pages
        )
        pages = list(gallery.pages)
        if task.max_pages is not None and task.max_pages > 0:
            pages = pages[: task.max_pages]
        if progress is not None:
            await progress(0, len(pages))
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / gallery_dirname(
            gallery.gid, gallery.title_jpn, gallery.title
        )
        temp = self.root / f".gv-{task.gid}"
        temp.mkdir(parents=True, exist_ok=True)
        settings = getattr(self.client, "settings", None)
        quality = (getattr(settings, "download_quality", None) or "resample").lower()
        # Download pages concurrently (like Ehviewer / SXJ) so long galleries
        # finish faster, bounded so ExHentai is not hammered.
        worker_semaphore = asyncio.Semaphore(self.page_concurrency)
        downloaded: set[int] = set()
        first_error: Exception | None = None
        first_error_lock = asyncio.Lock()
        done_count = 0
        done_lock = asyncio.Lock()

        async def _report_progress() -> None:
            nonlocal done_count
            async with done_lock:
                done_count += 1
            if progress is not None:
                await progress(done_count, len(pages))

        async def _download_page(index: int, page: object) -> None:
            nonlocal first_error
            # Resume support (Ehviewer / SXJ style): pages already on disk in the
            # temp dir OR the final target dir are skipped, so a retry only
            # fetches the pages that failed or were never written.
            existing = _existing_page_file(temp, index)
            if existing is None:
                existing = _existing_page_file(target, index)
                if existing is not None:
                    # Keep the page for the final atomic merge: copy the
                    # already-downloaded file into the temp dir.
                    shutil.copy2(existing, temp / existing.name)
            if existing is not None:
                downloaded.add(index)
                await self._record_bytes(gallery.gid, 0, 1)
                await _report_progress()
                return
            async with worker_semaphore:
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        url = self._resolve_image_url(page, quality)
                        content_type = ""
                        fetch_with_type = getattr(
                            self.client, "download_image_with_metadata", None
                        )
                        if fetch_with_type is not None:
                            data, content_type = await fetch_with_type(url)
                        else:
                            data = await self.client.download_image(url)
                        if not data or data[:20].lstrip().lower().startswith(
                            (b"<html", b"<!doctype")
                        ):
                            raise ValueError("image response is invalid")
                        extension = {
                            "image/jpeg": ".jpg",
                            "image/png": ".png",
                            "image/gif": ".gif",
                            "image/webp": ".webp",
                            "image/avif": ".avif",
                        }.get(
                            content_type.split(";", 1)[0].lower(),
                            Path(url).suffix.lower(),
                        )
                        if extension not in {
                            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
                        }:
                            extension = ".jpg"
                        (temp / f"{index + 1:08d}{extension}").write_bytes(data)
                        downloaded.add(index)
                        await self._record_bytes(gallery.gid, len(data), 1)
                        break
                    except DownloadCancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - per-page retry
                        last_error = exc
                        if attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                if last_error is not None:
                    raise last_error
            await _report_progress()

        async def _worker(pair: tuple[int, object]) -> None:
            nonlocal first_error
            index, page = pair
            try:
                await _download_page(index, page)
            except DownloadCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - record and keep going
                async with first_error_lock:
                    if first_error is None:
                        first_error = exc
                logger.warning(
                    "page download failed",
                    extra=log_extra(gid=gallery.gid, page=index, error=type(exc).__name__),
                )

        await asyncio.gather(
            *(_worker((index, page)) for index, page in enumerate(pages))
        )
        if first_error is not None:
            raise first_error
        # Final pass writes the resume manifest (progress is reported live above).
        done = 0
        for index, page in enumerate(pages):
            if index not in downloaded:
                (temp / ".download-manifest.json").write_text(
                    json.dumps({"gid": gallery.gid, "pages": done}), encoding="utf-8"
                )
                continue
            done += 1
            (temp / ".download-manifest.json").write_text(
                json.dumps({"gid": gallery.gid, "pages": done}), encoding="utf-8"
            )
        # Ehviewer VERSION2 reserves line 2 for the eight-digit start page.
        # When a partial (sample) download was requested via ``max_pages`` the
        # metadata must reflect only the pages actually written on disk.
        page_count = len(pages)
        # Preview metadata must match how ExHentai lays out the gallery page
        # (20 thumbnails per page) so Ehviewer's pToken lookup computes the
        # right preview page — with a complete pToken map it is never needed,
        # but partial downloads still work.
        preview_per_page = 20
        preview_pages = max(1, (page_count + preview_per_page - 1) // preview_per_page)
        lines = [
            "VERSION2",
            "00000000",
            str(gallery.gid),
            gallery.token,
            "1",
            str(preview_pages),
            str(preview_per_page),
            str(page_count),
        ]
        lines.extend(f"{i} {page.token}" for i, page in enumerate(pages) if page.token)
        (temp / ".ehviewer").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (temp / ".galleryvault.json").write_text(
            json.dumps(
                {
                    "category": gallery.category,
                    "title": gallery.title,
                    "title_jpn": gallery.title_jpn,
                    "tags": [
                        {"namespace": tag.get("namespace", "misc"), "name": tag.get("name", "")}
                        for tag in gallery.tags
                        if tag.get("name")
                    ],
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
        manifest = temp / ".download-manifest.json"
        if manifest.exists():
            manifest.unlink()
        if target.exists():
            shutil.rmtree(target)
        temp.rename(target)
        return DownloadResult(
            gallery.gid,
            target,
            len(pages),
            gallery.category,
            gallery.title,
            gallery.title_jpn,
            gallery.token,
            tuple(
                (tag.get("namespace", "misc"), tag.get("name", ""))
                for tag in gallery.tags
                if tag.get("name")
            ),
        )

    @staticmethod
    def _resolve_image_url(page, quality: str) -> str:
        """Pick the final image URL for a page given the configured quality.

        Original quality downloads the full image directly from ExHentai by
        appending the ``nl`` (skip-H@H) key to the ``fullimg`` link, mirroring
        Ehviewer's behaviour. Resample uses the viewer ``<img>`` source.
        """
        if (
            quality == "original"
            and page.origin_url
            and page.skip_hath_key
        ):
            sep = "&" if "?" in page.origin_url else "?"
            return f"{page.origin_url}{sep}nl={page.skip_hath_key}"
        return page.image_url or page.url
