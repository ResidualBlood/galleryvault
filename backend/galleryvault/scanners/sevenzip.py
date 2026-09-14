from __future__ import annotations

import builtins
import io
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Self

from .archive import MAX_ARCHIVE_PAGE_SIZE, ArchiveScanner, validate_archive_member
from .ehviewer import IMAGE_EXTENSIONS


@contextmanager
def _limit_extracted_file_size(target_dir: Path, max_size: int, member_name: str | None = None):
    orig_open = builtins.open
    target_dir_resolved = target_dir.resolve()

    class _LimitedWriter:
        def __init__(self, raw_file: object) -> None:
            self._raw = raw_file
            self._written = 0

        def write(self, b: object) -> int:
            chunk_len = len(b) if isinstance(b, (bytes, bytearray, memoryview, str)) else 0
            if self._written + chunk_len > max_size:
                name_suffix = f": {member_name}" if member_name else ""
                raise ValueError(
                    f"page file exceeds size limit ({self._written + chunk_len} > {max_size}){name_suffix}"
                )
            n = self._raw.write(b)  # type: ignore[attr-defined]
            self._written += chunk_len
            return n

        def writelines(self, lines: object) -> None:
            for line in lines:  # type: ignore[union-attr]
                self.write(line)

        def __getattr__(self, name: str) -> object:
            return getattr(self._raw, name)

        def __enter__(self) -> Self:
            self._raw.__enter__()  # type: ignore[attr-defined]
            return self

        def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> object:
            return self._raw.__exit__(exc_type, exc_val, exc_tb)  # type: ignore[attr-defined]

    def guarded_open(file: object, *args: object, **kwargs: object) -> object:
        f = orig_open(file, *args, **kwargs)  # type: ignore[call-overload]
        mode = kwargs.get("mode")
        if mode is None:
            mode = args[0] if args else "r"
        if any(m in str(mode) for m in ("w", "a", "x", "+")):
            try:
                p = Path(str(file)).resolve()
                if p.is_relative_to(target_dir_resolved):
                    return _LimitedWriter(f)
            except Exception:  # noqa: BLE001, S110
                pass
        return f

    builtins.open = guarded_open  # type: ignore[assignment]
    try:
        yield
    finally:
        builtins.open = orig_open  # type: ignore[assignment]


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
        with (
            tempfile.TemporaryDirectory() as tmp,
            py7zr.SevenZipFile(gallery.path, mode="r") as archive,
        ):
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
            with _limit_extracted_file_size(Path(tmp), MAX_ARCHIVE_PAGE_SIZE, page.name):
                archive.extract(targets=[page.name], path=tmp)
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
