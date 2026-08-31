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
from .eh_client import (
    ArchiveExpiredError,
    EhImageSlowError,
    GalleryData,
    GalleryPageData,
    ShowkeyState,
)

logger = logging.getLogger(__name__)

ProgressCallback = "callable[[int, int], object]"

_ARCHIVE_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


class DownloadCancelledError(Exception):
    """Raised when a pending/active download is cancelled mid-flight."""


class ArchiveNotRetryableError(Exception):
    """An archive download cannot succeed without user action (no funds, etc.).

    Raised instead of letting the persistent worker burn its automatic retry
    budget on a condition that will not heal on its own.
    """


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
    quality: str | None = None


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
    quality: str | None = None
    new_files: tuple[str, ...] = ()


class DownloadClient(Protocol):
    async def fetch_gallery(
        self,
        gid: int,
        token: str,
        max_pages: int | None = None,
        *,
        resolve_urls: bool = True,
    ) -> GalleryData: ...
    async def resolve_page(
        self,
        gid: int,
        page: GalleryPageData,
        showkey: ShowkeyState | None = None,
    ) -> GalleryPageData: ...
    async def download_image(self, url: str) -> bytes: ...
    async def fetch_archive_info(self, gid: int, token: str) -> object: ...
    async def request_archive(self, url: str, dltype: str) -> str: ...
    async def download_archive(
        self, url: str, dest: Path, cb: ProgressCallback | None = None
    ) -> int: ...


def safe_title(title: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", title).strip(" .")
    return value or "gallery"


def _truncate_utf8(value: str, limit: int = 255) -> str:
    """Truncate ``value`` to at most ``limit`` UTF-8 bytes (filename limit).

    Drops a trailing partial multibyte character so the result is always a
    valid, decodable string (CJK titles can otherwise exceed the filesystem
    filename limit).
    """
    data = value.encode("utf-8")
    if len(data) <= limit:
        return value
    return data[:limit].decode("utf-8", "ignore")


def gallery_dirname(
    gid: int, title_jpn: str | None, title: str | None, mode: str = "japanese"
) -> str:
    """Ehviewer-style download folder: ``<gid>-<title>``.

    ``mode`` follows the download-title setting: ``japanese`` picks the
    Japanese title first (the default, matching Ehviewer's ``getSuitableTitle``
    default), ``english`` the romaji/English title first. The whole name is
    byte-truncated to 255 UTF-8 bytes so long CJK titles cannot overflow the
    filesystem filename limit.
    """
    mode = (mode or "japanese").lower()
    if mode == "english":
        suitable = (title or title_jpn or "").strip()
    else:
        suitable = (title_jpn or title or "").strip()
    if suitable:
        return _truncate_utf8(f"{gid}-{safe_title(suitable)}")
    return str(gid)


def _find_existing_dirname(root: Path, gid: int) -> str | None:
    """Return the existing download dir for ``gid`` (longest ``<gid>-`` name), or None.

    Mirrors Ehviewer_CN_SXJ's ``findDownloadDirname``: reusing the on-disk
    folder keeps one directory per gid even when the title setting changes,
    instead of orphaning or deleting the previous one.
    """
    prefix = f"{gid}-"
    best: str | None = None
    try:
        for child in root.iterdir():
            if (
                child.is_dir()
                and child.name.startswith(prefix)
                and (best is None or len(child.name) > len(best))
            ):
                best = child.name
    except OSError:
        return None
    return best


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
        if task.mode and "archive" in task.mode:
            temp = self.root / f".gv-{task.gid}"
            if (temp / ".archive_fallback").exists():
                logger.info(
                    "archive fallback marker found; continuing page-by-page",
                    extra=log_extra(gid=task.gid),
                )
                return await self._download_pages(task, progress)
            try:
                return await self._download_archive_once(task, progress)
            except ArchiveNotRetryableError:
                # The archive channel cannot serve this gallery (no such tier,
                # insufficient GP, corrupt zip). When enabled, fall back to the
                # page-by-page channel, which costs no GP and lets H@H carry the
                # traffic, instead of failing the whole download.
                settings = getattr(self.client, "settings", None)
                if not getattr(settings, "archive_fallback_pages", True):
                    raise
                logger.info(
                    "archive download unavailable; falling back to page-by-page",
                    extra=log_extra(gid=task.gid),
                )
                temp = self.root / f".gv-{task.gid}"
                temp.mkdir(parents=True, exist_ok=True)
                (temp / ".archive_fallback").touch()
                return await self._download_pages(task, progress)
        return await self._download_pages(task, progress)

    async def _download_pages(
        self, task: DownloadTask, progress: ProgressCallback | None = None
    ) -> DownloadResult:
        # Pass max_pages through to fetch_gallery so a sample download only
        # resolves the pages it actually needs (otherwise every page's URL is
        # fetched from ExHentai via showpage before the list is truncated).
        gallery = await self.client.fetch_gallery(
            task.gid,
            task.token,
            max_pages=task.max_pages,
            resolve_urls=False,
        )
        pages = list(gallery.pages)
        if task.max_pages is not None and task.max_pages > 0:
            pages = pages[: task.max_pages]
        if progress is not None:
            await progress(0, len(pages))
        settings = getattr(self.client, "settings", None)
        quality = (
            task.quality
            or getattr(settings, "download_quality", None)
            or "resample"
        ).lower()
        self.root.mkdir(parents=True, exist_ok=True)
        # Reuse an existing `<gid>-` directory so re-downloads and download-title
        # changes never orphan (or worse, delete) the previous folder — keeping
        # one on-disk directory per gid like Ehviewer does.
        existing = _find_existing_dirname(self.root, gallery.gid)
        if existing is not None:
            target = self.root / existing
        else:
            target = self.root / gallery_dirname(
                gallery.gid,
                gallery.title_jpn,
                gallery.title,
                mode=getattr(settings, "download_title", None) or "japanese",
            )
        temp = self.root / f".gv-{task.gid}"
        temp.mkdir(parents=True, exist_ok=True)
        # A shared showkey holder: resolve_page seeds/refreshes it from the
        # first viewer HTML and the lightweight showpage API reuses it, so a
        # gallery does not re-fetch its gallery metadata between pages.
        showkey = ShowkeyState()
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

        async def _download_page(index: int, page: GalleryPageData) -> None:
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
                current: GalleryPageData = page
                # Lazy URL resolution + self-healing retries (mirrors
                # Ehviewer_CN_SXJ's 5-round downloadImage loop): every round
                # resolves a FRESH keystamp URL right before downloading, so a
                # 403 from an expired keystamp is healed by re-resolving the
                # page instead of sinking the whole task into exponential
                # backoff.  A persistent failure still escalates to the
                # task-level retry so the gallery stays complete.
                for attempt in range(5):
                    try:
                        current = await self.client.resolve_page(
                            gallery.gid, current, showkey
                        )
                        url = self._resolve_image_url(current, quality)
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
                    except EhImageSlowError:
                        # A throttled/slow H@H node will not heal in the
                        # sub-second window of the per-page retry — re-hitting
                        # it five times only burns slots. Surface it now so the
                        # persistent DownloadManager applies its 30s backoff and
                        # retries just the failed page later.
                        raise
                    except Exception as exc:  # noqa: BLE001 - per-page retry
                        # Includes EhClientError from a 403/expired keystamp or
                        # a failed re-resolution: the next round fetches a fresh
                        # URL and tries again.
                        last_error = exc
                        if attempt < 4:
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
        self._write_metadata(temp, gallery, pages, quality)
        manifest = temp / ".download-manifest.json"
        if manifest.exists():
            manifest.unlink()
        return await self._finalize_target(task, temp, gallery, pages, quality)

    def _write_metadata(
        self,
        temp: Path,
        gallery: GalleryData,
        pages: list[GalleryPageData],
        quality: str | None = None,
    ) -> None:
        """Write the Ehviewer ``.ehviewer`` resume manifest and ``.galleryvault.json``.

        Shared by the page-by-page and archive downloaders so both end up with
        identical metadata layouts.
        """
        # Ehviewer VERSION2 reserves line 2 for the eight-digit start page.
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
                    "quality": quality,
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

    async def _finalize_target(
        self,
        task: DownloadTask,
        temp: Path,
        gallery: GalleryData,
        pages: list[GalleryPageData],
        quality: str | None = None,
    ) -> DownloadResult:
        """Merge the staged temp dir into the final ``<gid>-`` folder and return the result."""
        settings = getattr(self.client, "settings", None)
        existing = _find_existing_dirname(self.root, gallery.gid)
        if existing is not None:
            target = self.root / existing
        else:
            target = self.root / gallery_dirname(
                gallery.gid,
                gallery.title_jpn,
                gallery.title,
                mode=getattr(settings, "download_title", None) or "japanese",
            )
        new_files = tuple(
            item.name
            for item in temp.iterdir()
            if item.is_file()
            and not item.name.startswith(".")
            and item.suffix.casefold() in _ARCHIVE_IMAGE_SUFFIXES
        ) if temp.is_dir() else ()
        if target.exists():
            # Merge into the existing directory (already-downloaded pages were
            # copied into temp during resume) instead of deleting it, so files
            # a previous run or the user left behind are preserved.
            await asyncio.to_thread(shutil.copytree, temp, target, dirs_exist_ok=True)
            await asyncio.to_thread(shutil.rmtree, temp)
        else:
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
            quality,
            new_files,
        )

    async def _download_archive_once(
        self, task: DownloadTask, progress: ProgressCallback | None = None
    ) -> DownloadResult:
        """Download a gallery through the ExHentai archive (zip) channel.

        Uses GP instead of H@H traffic for large galleries.  The flow mirrors
        Ehviewer_CN_SXJ's ArchiverDownloader / ArchiverDownloadCompleter:
        read the archive info page, request the zip (charged once), stream the
        zip with Range resume, unzip, rename by page order, then reuse the
        standard metadata + merge pipeline.  ``.gv-{gid}/.archive.json`` keeps
        the requested quality + zip URL so a retry resumes without re-charging.
        """
        gallery = await self.client.fetch_gallery(
            task.gid, task.token, resolve_urls=False
        )
        pages = list(gallery.pages)
        if progress is not None:
            await progress(0, len(pages))
        settings = getattr(self.client, "settings", None)
        quality = (
            task.quality
            or getattr(settings, "download_quality", None)
            or "resample"
        ).lower()
        if quality not in {"original", "resample"}:
            quality = "resample"
        temp = self.root / f".gv-{task.gid}"
        temp.mkdir(parents=True, exist_ok=True)
        state_file = temp / ".archive.json"
        state: dict[str, object] = {}
        if state_file.exists():
            try:
                loaded = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    state = loaded
            except (OSError, json.JSONDecodeError):
                state = {}
        # A persisted zip URL means the archive was already requested (GP
        # already spent): a retry resumes the zip without re-checking funds or
        # re-charging.  Only a fresh request needs the info page + funds gate.
        zip_url = state.get("zip_url")
        if not zip_url:
            info = await self.client.fetch_archive_info(task.gid, task.token)
            tier = "original" if quality == "original" else "resample"
            cost = getattr(info, "original_cost", None) if tier == "original" else getattr(
                info, "resample_cost", None
            )
            # archiver.php no longer exposes the GP balance; fall back to the
            # GP exchange page when the info page did not include it.
            funds = getattr(info, "funds", None)
            if funds is None and hasattr(self.client, "fetch_gp_balance"):
                funds = await self.client.fetch_gp_balance()
            if cost and funds is not None and funds < cost:
                raise ArchiveNotRetryableError(
                    f"insufficient GP for archive download ({cost} GP needed, {funds} GP available)"
                )
            url = getattr(info, "original_url", None) if tier == "original" else getattr(
                info, "resample_url", None
            )
            if not url:
                raise ArchiveNotRetryableError("ExHentai archive is unavailable for this gallery")
            dltype = "org" if tier == "original" else "res"
            zip_url = await self.client.request_archive(url, dltype)
            state = {"quality": tier, "zip_url": zip_url}
            state_file.write_text(json.dumps(state), encoding="utf-8")
        zip_path = temp / "archive.zip"
        page_count = max(1, len(pages))
        _last_bytes = 0
        _last_done = 0

        async def _zip_progress(downloaded: int, total: int | None) -> None:
            nonlocal _last_bytes, _last_done
            current = int(downloaded / total * page_count) if total else 0
            # Feed the live speed/ETA stats the same way the page-by-page path
            # does (bytes moved + progress done), or the downloads API would
            # have no stats and the UI would show no speed for archive tasks.
            # ``cb`` reports cumulative values; _record_bytes accumulates
            # increments, so only pass the delta since the last callback.
            byte_delta = max(0, downloaded - _last_bytes)
            done_delta = max(0, current - _last_done)
            _last_bytes, _last_done = downloaded, current
            await self._record_bytes(task.gid, byte_delta, done_delta)
            if progress is not None:
                await progress(min(current, page_count), len(pages))

        # A transient network error leaves the partial zip and the persisted zip
        # URL intact, so the next attempt resumes with a Range request instead
        # of re-charging GP.  A corrupt/expired archive is caught later at
        # extraction time, which clears both and re-requests.
        try:
            await self.client.download_archive(str(zip_url), zip_path, cb=_zip_progress)
        except ArchiveExpiredError as exc:
            zip_path.unlink(missing_ok=True)
            state_file.unlink(missing_ok=True)
            raise ArchiveNotRetryableError(str(exc)) from exc
        if progress is not None:
            await progress(len(pages), len(pages))
        unzip_dir = temp / "_unzip"
        if unzip_dir.exists():
            await asyncio.to_thread(shutil.rmtree, unzip_dir, True)
        try:
            await asyncio.to_thread(self._extract_zip, zip_path, unzip_dir)
        except Exception:
            zip_path.unlink(missing_ok=True)
            state_file.unlink(missing_ok=True)
            if unzip_dir.exists():
                await asyncio.to_thread(shutil.rmtree, unzip_dir, True)
            raise
        images = sorted(
            (
                item
                for item in unzip_dir.rglob("*")
                if item.is_file() and item.suffix.casefold() in _ARCHIVE_IMAGE_SUFFIXES
            ),
            key=lambda item: item.name,
        )
        if not images:
            zip_path.unlink(missing_ok=True)
            state_file.unlink(missing_ok=True)
            await asyncio.to_thread(shutil.rmtree, unzip_dir, True)
            raise ArchiveNotRetryableError("archive contained no images")
        if len(images) != len(pages):
            zip_path.unlink(missing_ok=True)
            state_file.unlink(missing_ok=True)
            await asyncio.to_thread(shutil.rmtree, unzip_dir, True)
            raise ArchiveNotRetryableError(
                f"archive image count {len(images)} != gallery page count {len(pages)}"
            )
        for index, image in enumerate(images):
            extension = image.suffix.casefold() or ".jpg"
            image.rename(temp / f"{index + 1:08d}{extension}")
        zip_path.unlink(missing_ok=True)
        await asyncio.to_thread(shutil.rmtree, unzip_dir, True)
        # The archive state was consumed; drop it so it does not leak into the
        # final gallery folder (dotfiles are hidden but unnecessary).
        state_file.unlink(missing_ok=True)
        self._write_metadata(temp, gallery, pages, quality)
        return await self._finalize_target(task, temp, gallery, pages, quality)

    @staticmethod
    def _extract_zip(zip_path: Path, dest: Path) -> None:
        """Extract an archive zip into ``dest`` safely without Zip Slip or Symlink escape."""
        import shutil
        import zipfile

        dest.mkdir(parents=True, exist_ok=True)
        dest_resolved = dest.resolve()
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                normalized = member.filename.replace("\\", "/")
                if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
                    raise ArchiveNotRetryableError(
                        f"archive member escapes extraction dir: {member.filename}"
                    )
                is_symlink = (
                    member.is_symlink()
                    if hasattr(member, "is_symlink")
                    else ((member.external_attr >> 16) & 0o170000 == 0o120000)
                )
                if is_symlink:
                    raise ArchiveNotRetryableError(
                        f"archive member is a symlink: {member.filename}"
                    )
                target = (dest / normalized).resolve()
                if not target.is_relative_to(dest_resolved):
                    raise ArchiveNotRetryableError(
                        f"archive member escapes extraction dir: {member.filename}"
                    )
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

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
