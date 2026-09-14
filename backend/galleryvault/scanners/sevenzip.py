from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import BinaryIO

from .archive import MAX_ARCHIVE_PAGE_SIZE, ArchiveScanner, validate_archive_member
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
        try:
            archive = py7zr.SevenZipFile(
                gallery.path, mode="r", max_extract_size=MAX_ARCHIVE_PAGE_SIZE
            )
        except TypeError:
            archive = py7zr.SevenZipFile(gallery.path, mode="r")
            archive.max_extract_size = MAX_ARCHIVE_PAGE_SIZE
        with (
            tempfile.TemporaryDirectory() as tmp,
            archive,
        ):
            if getattr(archive, "max_extract_size", None) is None:
                archive.max_extract_size = MAX_ARCHIVE_PAGE_SIZE
            # Check uncompressed size before extraction if metadata is available
            list_fn = getattr(archive, "list", None)
            if callable(list_fn):
                try:
                    for item in list_fn():
                        if getattr(item, "filename", None) == page.name:
                            uncompressed = getattr(item, "uncompressed", 0)
                            if uncompressed and uncompressed > MAX_ARCHIVE_PAGE_SIZE:
                                raise ValueError(
                                    f"page file exceeds size limit ({uncompressed} > {MAX_ARCHIVE_PAGE_SIZE}): {page.name}"
                                )
                            break
                except ValueError:
                    raise
                except Exception:  # noqa: BLE001, S110
                    pass
            try:
                archive.extract(
                    targets=[page.name],
                    path=tmp,
                )
            except Exception as exc:
                decompression_bomb_err = getattr(
                    getattr(py7zr, "exceptions", None), "DecompressionBombError", None
                )
                if (
                    decompression_bomb_err and isinstance(exc, decompression_bomb_err)
                ) or type(exc).__name__ == "DecompressionBombError":
                    raise ValueError(
                        f"page file exceeds size limit (decompression bomb): {page.name}"
                    ) from exc
                raise
            fp = Path(tmp) / page.name
            if not fp.is_file():
                raise ValueError(f"missing 7z member: {page.name}")
            st_size = fp.stat().st_size
            if st_size > MAX_ARCHIVE_PAGE_SIZE:
                raise ValueError(
                    f"page file exceeds size limit ({st_size} > {MAX_ARCHIVE_PAGE_SIZE}): {page.name}"
                )
            data = fp.read_bytes()
            if len(data) > MAX_ARCHIVE_PAGE_SIZE:
                raise ValueError(
                    f"page file exceeds size limit ({len(data)} > {MAX_ARCHIVE_PAGE_SIZE}): {page.name}"
                )
            return io.BytesIO(data)
