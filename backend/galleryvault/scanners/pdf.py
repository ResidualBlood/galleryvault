from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import BinaryIO

from .archive import ArchiveScanner, _is_unsafe_path
from .base import GalleryMeta, PageInfo
from .ehviewer import IMAGE_EXTENSIONS, natural_key

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class PdfScanner(ArchiveScanner):
    storage_type = "pdf"

    def matches(self, path: Path) -> bool:
        return path.is_file() and path.suffix.casefold() == ".pdf"

    def _pypdf(self):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF support requires the 'pypdf' package") from exc
        return PdfReader

    def _extract_images(self, path: Path) -> list[tuple[str, bytes]]:
        PdfReader = self._pypdf()
        reader = PdfReader(str(path))
        images: list[tuple[str, bytes]] = []
        for page_index, page in enumerate(getattr(reader, "pages", []) or []):
            page_images = getattr(page, "images", None) or []
            for img_index, image in enumerate(page_images):
                name = str(getattr(image, "name", "") or f"p{page_index:04d}_{img_index:03d}.jpg")
                name = name.replace("\\", "/").split("/")[-1]
                name = _SAFE_NAME.sub("_", name).lstrip(".")
                if not name:
                    name = f"p{page_index:04d}_{img_index:03d}.jpg"
                if _is_unsafe_path(name) or ".." in name:
                    continue
                suffix = Path(name).suffix.casefold()
                data = getattr(image, "data", None)
                if not data:
                    continue
                if suffix not in IMAGE_EXTENSIONS:
                    name = f"{Path(name).stem or name}.jpg"
                images.append((name, bytes(data)))
        return images

    def scan(self, path: Path) -> GalleryMeta:
        warnings: list[str] = []
        try:
            extracted = self._extract_images(path)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"pdf extract failed: {exc}")
            extracted = []
        if not extracted:
            warnings.append("pdf contained no extractable embedded images")
            logger.warning("pdf scan skipped images", extra={"path": str(path)})
        names = [name for name, _ in extracted]
        sizes = {name: len(data) for name, data in extracted}
        ordered = sorted(
            (name for name in names if Path(name).suffix.casefold() in IMAGE_EXTENSIONS),
            key=natural_key,
        )
        pages = [
            PageInfo(i, name, Path(name).suffix.casefold().lstrip("."), sizes.get(name))
            for i, name in enumerate(ordered)
        ]
        return self._meta(path, pages, {"archive": "pdf"}, warnings=warnings)

    def open_page(self, gallery, page) -> BinaryIO:
        if _is_unsafe_path(page.name):
            raise ValueError(f"unsafe page path: {page.name}")
        extracted = self._extract_images(gallery.path)
        for name, data in extracted:
            if name == page.name:
                return io.BytesIO(data)
        raise ValueError(f"missing pdf image: {page.name}")
