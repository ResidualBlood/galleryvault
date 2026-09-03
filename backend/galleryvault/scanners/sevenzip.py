from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import BinaryIO

from .archive import ArchiveScanner, validate_archive_member
from .ehviewer import IMAGE_EXTENSIONS


class SevenZipScanner(ArchiveScanner):
    storage_type = "7z"

    def matches(self, path: Path) -> bool:
        return path.is_file() and path.suffix.casefold() == ".7z"

    def _py7zr(self):
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError("7z support requires the 'py7zr' package") from exc
        return py7zr

    def scan(self, path: Path) -> object:
        py7zr = self._py7zr()
        with py7zr.SevenZipFile(path, mode="r") as archive:
            names = list(archive.getnames() or [])
            for name in names:
                validate_archive_member(name, None)
            image_names = [
                name for name in names if Path(name).suffix.casefold() in IMAGE_EXTENSIONS
            ]
            sizes: dict[str, int] = {}
            if image_names:
                sizes = self._image_sizes(archive, image_names)
            pages = self._pages(list(sizes), sizes)
            return self._meta(path, pages, {"archive": "7z"})

    @staticmethod
    def _member_size(buf: object) -> int:
        getbuffer = getattr(buf, "getbuffer", None)
        if callable(getbuffer):
            return int(getbuffer().nbytes)
        read = getattr(buf, "read", None)
        if callable(read):
            return len(read())
        return len(buf)  # type: ignore[arg-type]

    def _image_sizes(self, archive: object, image_names: list[str]) -> dict[str, int]:
        wanted = set(image_names)
        read = getattr(archive, "read", None)
        if callable(read):
            extracted = read(targets=image_names) or {}
            return {
                name: self._member_size(buf)
                for name, buf in extracted.items()
                if name in wanted and buf is not None
            }
        sizes: dict[str, int] = {}
        with tempfile.TemporaryDirectory() as tmp:
            archive.extract(targets=image_names, path=tmp)  # type: ignore[union-attr]
            for name in image_names:
                fp = Path(tmp) / name
                if fp.is_file():
                    sizes[name] = fp.stat().st_size
        return sizes

    def open_page(self, gallery, page) -> BinaryIO:
        validate_archive_member(page.name, None)
        py7zr = self._py7zr()
        with tempfile.TemporaryDirectory() as tmp, py7zr.SevenZipFile(
            gallery.path, mode="r"
        ) as archive:
            archive.extract(targets=[page.name], path=tmp)
            fp = Path(tmp) / page.name
            if not fp.is_file():
                raise ValueError(f"missing 7z member: {page.name}")
            return io.BytesIO(fp.read_bytes())
