from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repository import GalleryRepository
from ..metadata.sidecar import SIDECAR_FILENAME, write_galleryvault_json
from ..scanners.base import GalleryMeta
from ..scanners.ehviewer import parse_spider_info

logger = logging.getLogger(__name__)

CRITICAL_SIDECAR_KEYS = ("gid", "token", "category", "quality", "p_tokens", "tags", "title")
ARCHIVE_STORAGE_TYPES = {"cbz", "zip", "pdf", "cbr", "rar"}


class GalleryIngestService:
    def __init__(self, session: AsyncSession, batch_size: int = 500) -> None:
        self.repository = GalleryRepository(session)
        self.batch_size = max(1, batch_size)

    async def ingest(self, galleries: Sequence[GalleryMeta]) -> None:
        # Reuse cached gdata metadata: galleries the favorites monitor already
        # saw (gid known) get tags/title/category/posted filled in here, so no
        # per-gallery ExHentai fetch is needed after ingest.
        cached = await self.repository.metadata_map(
            [g.gid for g in galleries if g.gid is not None and (not g.tags or not g.category)]
        )
        for gallery in galleries:
            if gallery.gid is None or gallery.gid not in cached:
                continue
            meta = cached[gallery.gid]
            if not gallery.tags:
                gallery.tags = [{"namespace": t["namespace"], "name": t["name"]} for t in meta["tags"]]
            gallery.category = gallery.category or meta["category"]
            gallery.title_jpn = gallery.title_jpn or meta["title_jpn"]
            gallery.rating = gallery.rating or meta["rating"]
            gallery.posted_at = gallery.posted_at or meta["posted_at"]
        for start in range(0, len(galleries), self.batch_size):
            await self.repository.upsert_many(galleries[start : start + self.batch_size])
        self._sync_directory_sidecars(galleries)

    def _sync_directory_sidecars(self, galleries: Sequence[GalleryMeta]) -> None:
        """Backfill full v1 .galleryvault.json for directory-based galleries missing critical keys."""
        for gallery in galleries:
            # Strictly directories only; archives (cbz, cbr, pdf, etc.) must NEVER be modified
            if gallery.storage_type in ARCHIVE_STORAGE_TYPES:
                continue
            try:
                if not gallery.path.is_dir():
                    continue
            except (OSError, ValueError):
                continue

            sidecar_path = gallery.path / SIDECAR_FILENAME
            raw: dict[str, Any] | None = None
            if sidecar_path.is_file():
                try:
                    loaded = json.loads(sidecar_path.read_bytes())
                    if isinstance(loaded, dict):
                        raw = loaded
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    raw = None

            # Skip if already a complete v1 sidecar containing all critical keys
            if raw is not None and all(k in raw for k in CRITICAL_SIDECAR_KEYS):
                continue

            try:
                self._write_directory_sidecar(gallery, raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to sync sidecar for %s: %s", gallery.path, exc)

    @staticmethod
    def _write_directory_sidecar(gallery: GalleryMeta, raw: dict[str, Any] | None) -> None:
        raw_dict = raw if isinstance(raw, dict) else {}

        # Preserve unknown extra keys for forward compatibility
        known_keys = {
            "version",
            "gid",
            "token",
            "title",
            "title_jpn",
            "category",
            "quality",
            "tags",
            "p_tokens",
            "uploader",
            "posted",
            "rating",
            "file_count",
            "file_size",
            "site",
        }
        extra = {k: v for k, v in raw_dict.items() if k not in known_keys}

        spider_info = None
        ehviewer_path = gallery.path / ".ehviewer"
        if ehviewer_path.is_file():
            try:
                spider_info = parse_spider_info(ehviewer_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                spider_info = None

        gid = gallery.gid
        if gid is None and raw_dict.get("gid") is not None:
            gid = raw_dict["gid"]
        if gid is None and spider_info is not None:
            gid = spider_info.gid

        token = gallery.token or raw_dict.get("token")
        if not token and spider_info is not None:
            token = spider_info.token

        p_tokens = None
        if isinstance(gallery.source_meta, dict) and gallery.source_meta.get("p_tokens"):
            p_tokens = gallery.source_meta["p_tokens"]
        elif raw_dict.get("p_tokens"):
            p_tokens = raw_dict["p_tokens"]
        elif spider_info is not None:
            p_tokens = spider_info.p_tokens

        quality = (
            gallery.image_quality
            if gallery.image_quality is not None
            else raw_dict.get("quality")
        )
        category = gallery.category if gallery.category is not None else raw_dict.get("category")
        tags = gallery.tags if gallery.tags else raw_dict.get("tags")
        title = gallery.title if gallery.title else raw_dict.get("title")
        title_jpn = gallery.title_jpn if gallery.title_jpn else raw_dict.get("title_jpn")
        uploader = gallery.uploader if gallery.uploader else raw_dict.get("uploader")
        posted = (
            gallery.posted_at
            if gallery.posted_at is not None
            else raw_dict.get("posted")
        )
        rating = gallery.rating if gallery.rating is not None else raw_dict.get("rating")
        file_count = (
            gallery.file_count
            if gallery.file_count is not None
            else (len(gallery.pages) if gallery.pages else raw_dict.get("file_count"))
        )
        file_size = (
            gallery.file_size
            if gallery.file_size is not None
            else raw_dict.get("file_size")
        )
        site = raw_dict.get("site")

        write_galleryvault_json(
            gallery.path,
            gid=gid,
            token=token,
            tags=tags,
            p_tokens=p_tokens,
            title=title,
            title_jpn=title_jpn,
            category=category,
            quality=quality,
            uploader=uploader,
            posted=posted,
            rating=rating,
            file_count=file_count,
            file_size=file_size,
            site=site,
            extra=extra,
        )
