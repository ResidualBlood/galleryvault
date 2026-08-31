"""Static thumbnail generation and on-disk caching.

Thumbnails live in a dedicated cache directory (``thumbnail_cache_dir``,
default ``/gv-cache/thumbs``) keyed by gallery id and page index — never in
the gallery archive itself, so downloaded galleries are never modified.
Animated formats (WebP) are rendered as their first, static frame.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image
from PIL.Image import DecompressionBombError

logger = logging.getLogger(__name__)

# Display boxes are roughly 240px wide; cap width and let the height follow
# the aspect ratio (bounded so very tall pages don't produce huge files).
THUMB_MAX_WIDTH = 240
THUMB_MAX_HEIGHT = 480
THUMB_QUALITY = 70
JPEG_MIME = "image/jpeg"

# Limit maximum allowed image pixels (64 million pixels) to prevent
# decompression bomb Denial of Service (DoS) memory exhaustion.
Image.MAX_IMAGE_PIXELS = 64_000_000


class ThumbnailError(Exception):
    """Raised when a thumbnail cannot be produced for a page."""


class ThumbnailService:
    def __init__(self, cache_root: str | Path) -> None:
        self.root = Path(cache_root)

    def cache_path(self, gallery_id: int, page_index: int) -> Path:
        return self.root / str(gallery_id) / f"{page_index}.jpg"

    def cached(self, gallery_id: int, page_index: int) -> Path | None:
        path = self.cache_path(gallery_id, page_index)
        return path if path.is_file() else None

    def get_or_create(
        self,
        gallery_id: int,
        page_index: int,
        page_bytes: bytes,
    ) -> Path:
        """Return a cached thumbnail path, generating it from raw page bytes."""
        path = self.cache_path(gallery_id, page_index)
        if path.is_file():
            return path
        data = self._render(page_bytes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def missing_pages(self, gallery_id: int, page_count: int) -> list[int]:
        """Page indexes that have no cached thumbnail yet."""
        root = self.root / str(gallery_id)
        return [
            i for i in range(page_count)
            if not (root / f"{i}.jpg").is_file()
        ]

    def get_or_create_dup(self, key: str, page_bytes: bytes) -> Path:
        """Cached thumbnail for a duplicate copy, keyed by its path hash.

        Duplicate copies are not (yet) gallery rows, so they cannot use the
        id-based cache; the key keeps them under ``<root>/dup/<key>/0.jpg``.
        """
        path = self.root / "dup" / key / "0.jpg"
        if path.is_file():
            return path
        data = self._render(page_bytes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    @staticmethod
    def _render(page_bytes: bytes) -> bytes:
        from PIL import UnidentifiedImageError

        try:
            with Image.open(BytesIO(page_bytes)) as source:
                source.load()
                image = source.convert("RGB")
                image.thumbnail((THUMB_MAX_WIDTH, THUMB_MAX_HEIGHT))
        except DecompressionBombError as exc:
            raise ThumbnailError(f"image exceeds maximum safe dimensions: {exc}") from exc
        except UnidentifiedImageError as exc:
            raise ThumbnailError(f"unsupported image format: {exc}") from exc
        except OSError as exc:
            raise ThumbnailError(f"could not decode image: {exc}") from exc

        buf = BytesIO()
        image.save(buf, format="JPEG", quality=THUMB_QUALITY, optimize=True)
        return buf.getvalue()