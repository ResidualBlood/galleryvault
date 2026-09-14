from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

from .archive import MAX_ARCHIVE_PAGE_SIZE, ArchiveScanner, validate_archive_member
from .ehviewer import IMAGE_EXTENSIONS


class _CappedMemWriter:
    """py7zr WriterFactory product: cap writes for the requested member only."""

    def __init__(self, max_size: int, member_name: str) -> None:
        self._buf = io.BytesIO()
        self._max_size = max_size
        self._member_name = member_name
        self._written = 0

    def write(self, s: bytes | bytearray) -> int:
        n = len(s)
        if self._written + n > self._max_size:
            raise ValueError(
                f"page file exceeds size limit ({self._written + n} > {self._max_size}): {self._member_name}"
            )
        self._written += n
        return self._buf.write(s)

    def read(self, size: int | None = None) -> bytes:
        if size is None:
            return self._buf.read()
        return self._buf.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._buf.seek(offset, whence)

    def flush(self) -> None:
        self._buf.flush()

    def size(self) -> int:
        return self._written

    def close(self) -> None:
        return None

    def seekable(self) -> bool:
        return True

    def getvalue(self) -> bytes:
        return self._buf.getvalue()


class _CappedWriterFactory:
    def __init__(self, max_size: int, member_name: str) -> None:
        self.max_size = max_size
        self.member_name = member_name
        self.writer: _CappedMemWriter | None = None

    def create(self, _filename: str) -> _CappedMemWriter:
        self.writer = _CappedMemWriter(self.max_size, self.member_name)
        return self.writer

    def getvalue(self) -> bytes:
        if self.writer is None:
            return b""
        return self.writer.getvalue()


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

    def _image_sizes(self, archive: object, image_names: list[str]) -> dict[str, int]:
        wanted = set(image_names)
        sizes: dict[str, int] = {}
        list_fn = getattr(archive, "list", None)
        if callable(list_fn):
            try:
                for item in list_fn():
                    name = getattr(item, "filename", None)
                    if name not in wanted:
                        continue
                    uncompressed = getattr(item, "uncompressed", None)
                    if uncompressed is None:
                        continue
                    size = int(uncompressed)
                    if size > MAX_ARCHIVE_PAGE_SIZE:
                        continue
                    sizes[name] = size
            except Exception:  # noqa: BLE001
                sizes = {}
        missing = [name for name in image_names if name not in sizes]
        for name in missing:
            reset = getattr(archive, "reset", None)
            if callable(reset):
                reset()
            factory = _CappedWriterFactory(MAX_ARCHIVE_PAGE_SIZE, name)
            try:
                archive.extract(targets=[name], factory=factory)
            except Exception:  # noqa: BLE001, S112
                continue
            if factory.writer is not None:
                sizes[name] = factory.writer.size()
        return sizes

    @staticmethod
    def _reject_oversize_member(archive: object, page_name: str) -> None:
        list_fn = getattr(archive, "list", None)
        if not callable(list_fn):
            return
        try:
            for item in list_fn():
                if getattr(item, "filename", None) == page_name:
                    uncompressed = getattr(item, "uncompressed", 0)
                    if uncompressed and uncompressed > MAX_ARCHIVE_PAGE_SIZE:
                        raise ValueError(
                            f"page file exceeds size limit ({uncompressed} > {MAX_ARCHIVE_PAGE_SIZE}): {page_name}"
                        )
                    break
        except ValueError:
            raise
        except Exception:  # noqa: BLE001, S110
            pass

    def open_page(self, gallery, page) -> BinaryIO:
        validate_archive_member(page.name, None)
        py7zr = self._py7zr()
        with py7zr.SevenZipFile(gallery.path, mode="r") as archive:
            self._reject_oversize_member(archive, page.name)
            factory = _CappedWriterFactory(MAX_ARCHIVE_PAGE_SIZE, page.name)
            archive.extract(targets=[page.name], factory=factory)
            data = factory.getvalue()
            if factory.writer is None:
                raise ValueError(f"missing 7z member: {page.name}")
            if len(data) > MAX_ARCHIVE_PAGE_SIZE:
                raise ValueError(
                    f"page file exceeds size limit ({len(data)} > {MAX_ARCHIVE_PAGE_SIZE}): {page.name}"
                )
            return io.BytesIO(data)
