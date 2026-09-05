import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree

from .base import GalleryMeta, GalleryScanner, PageInfo, infer_category
from .ehviewer import IMAGE_EXTENSIONS, natural_key


def _normalize_tags(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    tags: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                ns = str(item.get("namespace") or "misc").strip()
                tags.append({"namespace": ns, "name": name})
        elif isinstance(item, str):
            val = item.strip()
            if not val:
                continue
            if ":" in val:
                ns, n = val.split(":", 1)
                tags.append({"namespace": ns.strip(), "name": n.strip()})
            else:
                tags.append({"namespace": "misc", "name": val})
    return tags


def _is_symlink(info: object) -> bool:
    """Return True if archive member is a symlink (ZipInfo/RarInfo unified)."""
    if hasattr(info, "is_symlink"):
        try:
            return bool(info.is_symlink())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001, S110
            pass
    external_attr = getattr(info, "external_attr", 0)
    return ((int(external_attr) >> 16) & 0o170000) == 0o120000


def _is_unsafe_path(filename: str) -> bool:
    """Check for absolute path or path traversal via ``..`` components."""
    normalized = filename.replace("\\", "/")
    p = Path(normalized)
    return p.is_absolute() or ".." in p.parts


def validate_archive_member(filename: str, info: object) -> None:
    """Validate a single archive member, raising ValueError on Zip-Slip/symlink."""
    if _is_unsafe_path(filename):
        raise ValueError(f"unsafe archive member path: {filename}")
    if _is_symlink(info):
        raise ValueError(f"unsafe symlink in archive: {filename}")


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
        gid = int(gid_match.group(1)) if gid_match else None
        if gid is None and metadata.get("gid") is not None:
            try:
                gid = int(metadata["gid"])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        token = str(metadata["token"]) if metadata.get("token") else None
        tags = metadata.get("tags") or []
        image_quality = str(metadata["image_quality"]) if metadata.get("image_quality") else None
        return GalleryMeta(
            title=str(metadata.get("title") or path.stem),
            path=path,
            storage_type=self.storage_type,
            pages=pages,
            gid=gid,
            token=token,
            file_count=len(pages),
            file_size=stat.st_size,
            title_jpn=metadata.get("title_jpn"),  # type: ignore[arg-type]
            category=infer_category(path, metadata),
            uploader=metadata.get("uploader"),  # type: ignore[arg-type]
            tags=tags,  # type: ignore[arg-type]
            warnings=metadata.get("warnings", []),  # type: ignore[arg-type]
            image_quality=image_quality,
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
                try:
                    validate_archive_member(info.filename, info)
                except ValueError as exc:
                    raise ValueError(f"{path}: {exc}") from exc
            sizes = {info.filename: info.file_size for info in archive.infolist()}
            pages = self._pages(list(sizes), sizes)
            raw, metadata = self._comic_info(archive, list(sizes))
            gv_name = next(
                (name for name in sizes if Path(name).name.casefold() == ".galleryvault.json"),
                None,
            )
            if gv_name:
                try:
                    gv_data = json.loads(archive.read(gv_name).decode("utf-8"))
                    if isinstance(gv_data, dict):
                        raw[".galleryvault.json"] = gv_data
                        if gv_data.get("gid") is not None:
                            try:
                                metadata["gid"] = int(gv_data["gid"])
                            except (TypeError, ValueError):
                                pass
                        if gv_data.get("token"):
                            metadata["token"] = str(gv_data["token"])
                        gv_tags = _normalize_tags(gv_data.get("tags"))
                        if gv_tags:
                            metadata["tags"] = gv_tags
                        if gv_data.get("title") and not metadata.get("title"):
                            metadata["title"] = str(gv_data["title"])
                        if gv_data.get("title_jpn"):
                            metadata["title_jpn"] = str(gv_data["title_jpn"])
                        if gv_data.get("quality"):
                            metadata["image_quality"] = str(gv_data["quality"])
                except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                    pass
            return self._meta(path, pages, raw, **metadata)

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        if _is_unsafe_path(page.name):
            raise ValueError(f"unsafe page path: {page.name}")
        with zipfile.ZipFile(gallery.path) as archive:
            info = archive.getinfo(page.name)
            if _is_symlink(info):
                raise ValueError(f"unsafe symlink in archive: {page.name}")
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
                    try:
                        validate_archive_member(info.filename, info)
                    except ValueError as exc:
                        raise ValueError(f"{path}: {exc}") from exc
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
        if _is_unsafe_path(page.name):
            raise ValueError(f"unsafe page path: {page.name}")
        RarFile = self._rar()
        try:
            with RarFile(gallery.path) as archive:
                # Validate symlink for RAR as well (previously missing)
                try:
                    infos = archive.infolist()
                    target_info = next((i for i in infos if i.filename == page.name), None)
                    if target_info is not None and _is_symlink(target_info):
                        raise ValueError(f"unsafe symlink in archive: {page.name}")
                except ValueError:
                    raise
                except Exception:  # noqa: BLE001, S110
                    pass
                return io.BytesIO(archive.read(page.name))
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError("Unable to read CBR/RAR page; install unrar or libarchive") from exc
