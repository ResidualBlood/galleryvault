from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from ..app.dependencies import get_current_settings
from .eh_client import FavoriteData
from .messages import (
    favorites_check_failed,
    favorites_enqueue_failed,
    favorites_summary,
)

logger = logging.getLogger(__name__)
MODES = {"monitor_only", "incremental", "force"}


class FavoriteRepository(Protocol):
    async def known_gids(self, favcat: int) -> set[int]: ...
    async def existing_gallery_gids(self, gids: list[int]) -> set[int]: ...
    async def remember(self, favcat: int, item: FavoriteData) -> None: ...
    async def remember_many(self, favcat: int, items: list[FavoriteData]) -> None: ...
    async def prune(self, favcat: int, current_gids: set[int]) -> int: ...
    async def checked(self, favcat: int, success: bool) -> None: ...
    async def category(self, favcat: int) -> Any: ...


@dataclass(frozen=True)
class FavoritesCheckResult:
    favcat: int
    found: int
    new: int
    downloaded: int
    failed: int


class FavoritesService:
    def __init__(
        self, fetcher: Any, repository: FavoriteRepository, queue: Any = None, notifier: Any = None
    ) -> None:
        self.fetcher, self.repository, self.queue, self.notifier = (
            fetcher,
            repository,
            queue,
            notifier,
        )

    async def check_category(
        self,
        favcat: int,
        *,
        mode: str = "incremental",
        retries: int = 3,
        progress: Any | None = None,
        archive_enabled: bool = False,
        archive_max_pages: int = 0,
        archive_quality: str = "resample",
    ) -> FavoritesCheckResult:
        if mode not in MODES:
            raise ValueError("mode must be monitor_only, incremental, or force")
        cat = await self.repository.category(favcat)
        cat_name = getattr(cat, "name", None) if cat is not None else None
        lang = getattr(self.notifier, "message_lang", "zh") if self.notifier else "zh"
        items: list[FavoriteData] = []
        last: Exception | None = None
        fetched = False
        attempts = min(max(1, retries), 3)
        for attempt in range(1, attempts + 1):
            try:
                items = await self.fetcher.fetch_favorites(favcat, progress=progress)
                fetched = True
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                logger.warning(
                    "favorites check attempt failed",
                    extra={
                        "context": {
                            "favcat": favcat,
                            "attempt": attempt,
                            "error": type(exc).__name__,
                        }
                    },
                )
        if not fetched:
            await self.repository.checked(favcat, False)
            log_check = getattr(self.repository, "log_check", None)
            if log_check:
                await log_check(favcat, [], attempts, False, type(last).__name__ if last else None)
            if self.notifier:
                await self.notifier.send_message(
                    favorites_check_failed(favcat, cat_name, attempts, lang)
                )
            raise RuntimeError(f"favorites check failed after {attempts} attempts") from last
        known = await self.repository.known_gids(favcat)
        unique = {item.gid: item for item in items}
        candidates = (
            list(unique.values())
            if mode == "force"
            else [item for item in unique.values() if item.gid not in known]
        )
        # Deduplicate against the local library: a gallery already present on
        # disk (e.g. an Ehviewer export under a mounted library root) must not
        # be downloaded again into the downloads directory.
        if candidates:
            local_gids = await self.repository.existing_gallery_gids(
                [item.gid for item in candidates]
            )
            if local_gids:
                candidates = [item for item in candidates if item.gid not in local_gids]
        # Record every folder item as seen (idempotent) so the per-folder count
        # reflects the whole ExHentai folder, including galleries already local.
        # Then drop rows for gids no longer in the folder (unfavorited /
        # expunged galleries vanish from the listing) so the recorded set stays
        # in sync with the cloud — otherwise the scheduled "count unchanged"
        # skip never fires again and phantom cloud items linger in lists.
        await self.repository.remember_many(favcat, list(unique.values()))
        await self.repository.prune(favcat, set(unique))
        downloaded = failed = 0
        archive_mode = "favorite_archive" if archive_enabled else None
        archive_sizes: dict[int, int] = {}
        if archive_enabled and candidates:
            pairs = [(item.gid, item.token) for item in candidates if item.token]
            try:
                gmeta = await self.fetcher.fetch_gmetadata(pairs)
                archive_sizes = {
                    int(gid): int(meta.get("file_count") or 0)
                    for gid, meta in gmeta.items()
                }
            except Exception as exc:  # noqa: BLE001 - fall back to page-by-page
                logger.warning(
                    "favorites archive sizing failed; falling back to page-by-page",
                    extra={"context": {"favcat": favcat, "error": type(exc).__name__}},
                )
        for item in candidates:
            if mode == "monitor_only":
                continue
            try:
                if self.queue is not None:
                    filecount = archive_sizes.get(item.gid, 0)
                    use_archive = bool(
                        archive_mode
                        and item.token
                        and (archive_max_pages == 0 or filecount > archive_max_pages)
                    )
                    if use_archive:
                        accepted = await self.queue.enqueue(
                            item, mode="favorite_archive", quality=archive_quality
                        )
                    else:
                        default_quality = (
                            getattr(get_current_settings(), "download_quality", None) or "resample"
                        )
                        try:
                            accepted = await self.queue.enqueue(item, quality=default_quality)
                        except TypeError:
                            accepted = await self.queue.enqueue(item)
                    if accepted is False:
                        raise RuntimeError("download task was not created")
                downloaded += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.warning(
                    "favorite download enqueue failed",
                    extra={
                        "context": {"favcat": favcat, "gid": item.gid, "error": type(exc).__name__}
                    },
                )
                if self.notifier:
                    await self.notifier.send_message(
                        favorites_enqueue_failed(favcat, cat_name, item.gid, lang)
                    )
        await self.repository.checked(favcat, failed == 0)
        log_check = getattr(self.repository, "log_check", None)
        if log_check:
            await log_check(favcat, sorted(item.gid for item in candidates), attempts, failed == 0)
        if self.notifier and candidates:
            await self.notifier.send_message(
                favorites_summary(favcat, cat_name, len(candidates), downloaded, lang)
            )
        return FavoritesCheckResult(favcat, len(unique), len(candidates), downloaded, failed)
