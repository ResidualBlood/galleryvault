import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree

from .base import GalleryMeta, GalleryScanner, PageInfo, infer_category
from .ehviewer import IMAGE_EXTENSIONS, natural_key


class ArchiveScanner(GalleryScanner):
    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        stat = path.stat()
        return hashlib.sha256(f"{stat.st_size}\0{stat.st_mtime_ns}".encode()).hexdigest()

    def _pages(self, names: list[str], sizes: dict[str, int]) -> list[PageInfo]:
        images = sorted(
            (
                name
                for name in names
                if not name.startswith(".") and Path(name).suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=natural_key,
        )
        return [
            PageInfo(i, name, Path(name).suffix.casefold().lstrip("."), sizes.get(name))
            for i, name in enumerate(images)
        ]

    def _meta(
        self, path: Path, pages: list[PageInfo], raw: dict, **metadata: object
    ) -> GalleryMeta:
        stat = path.stat()
        digest = self.storage_signature(path)
        gid_match = re.match(r"^(\d+)-", path.stem)
        return GalleryMeta(
            title=str(metadata.get("title") or path.stem),
            path=path,
            storage_type=self.storage_type,
            pages=pages,
            gid=int(gid_match.group(1)) if gid_match else None,
            file_count=len(pages),
            file_size=stat.st_size,
            title_jpn=metadata.get("title_jpn"),
            category=infer_category(path, metadata),
            uploader=metadata.get("uploader"),
            tags=metadata.get("tags", []),
            warnings=metadata.get("warnings", []),
            source_meta=raw,
            storage_signature=digest,
            storage_mtime_ns=stat.st_mtime_ns,
            storage_size=stat.st_size,
        )

    @staticmethod
    def _comic_info(archive: object, names: list[str]) -> tuple[dict, dict[str, object]]:
        comic = next((name for name in names if name.casefold() == "comicinfo.xml"), None)
        if not comic:
            return {}, {}
        try:
            root = ElementTree.fromstring(archive.read(comic))
        except ElementTree.ParseError as exc:
            return {"comic_info_error": str(exc)}, {}
        values = {child.tag.split("}")[-1]: (child.text or "").strip() for child in root}
        metadata: dict[str, object] = {}
        if values.get("Title"):
            metadata["title"] = values["Title"]
        if values.get("Genre"):
            metadata["tags"] = [
                {"namespace": "misc", "name": tag.strip()}
                for tag in values["Genre"].split(",")
                if tag.strip()
            ]
        if values.get("Writer"):
            metadata["uploader"] = values["Writer"]
        return {"comic_info": values}, metadata


class CbzZipScanner(ArchiveScanner):
    storage_type = "cbz"

    def matches(self, path: Path) -> bool:
        return path.is_file() and path.suffix.casefold() in {".cbz", ".zip"}

    def scan(self, path: Path) -> GalleryMeta:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                normalized = info.filename.replace("\\", "/")
                if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
                    raise ValueError(f"{path}: unsafe archive member path: {info.filename}")
            sizes = {info.filename: info.file_size for info in archive.infolist()}
            pages = self._pages(list(sizes), sizes)
            raw, metadata = self._comic_info(archive, list(sizes))
            return self._meta(path, pages, raw, **metadata)

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        with zipfile.ZipFile(gallery.path) as archive:
            return io.BytesIO(archive.read(page.name))


class CbrRarScanner(ArchiveScanner):
    storage_type = "cbr"

    def matches(self, path: Path) -> bool:
        return path.is_file() and path.suffix.casefold() in {".cbr", ".rar"}

    def _rar(self):
        try:
            import rarfile
        except ImportError as exc:
            raise RuntimeError("CBR support requires the 'rarfile' package") from exc
        try:
            archive = rarfile.RarFile
            return archive
        except AttributeError as exc:
            raise RuntimeError("rarfile is unavailable") from exc

    def scan(self, path: Path) -> GalleryMeta:
        RarFile = self._rar()
        try:
            with RarFile(path) as archive:
                infos = archive.infolist()
                for info in infos:
                    normalized = info.filename.replace("\\", "/")
                    if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
                        raise ValueError(f"{path}: unsafe archive member path: {info.filename}")
                sizes = {info.filename: info.file_size for info in infos}
                raw, metadata = self._comic_info(archive, list(sizes))
                return self._meta(path, self._pages(list(sizes), sizes), raw, **metadata)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Unable to read CBR/RAR; install unrar or libarchive and ensure the archive is valid"
            ) from exc

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        RarFile = self._rar()
        try:
            with RarFile(gallery.path) as archive:
                return io.BytesIO(archive.read(page.name))
        except Exception as exc:
            raise RuntimeError("Unable to read CBR/RAR page; install unrar or libarchive") from exc
