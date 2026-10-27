import atexit
import hashlib
import io
import json
import re
import threading
import time
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree

from ..metadata.sidecar import (
    SIDECAR_FILENAME,
    normalize_tags,
    parse_galleryvault_json,
)
from .base import GalleryMeta, GalleryScanner, PageInfo, infer_category
from .ehviewer import IMAGE_EXTENSIONS, natural_key, strip_gid_prefix

MAX_ARCHIVE_PAGE_SIZE = 128 * 1024 * 1024  # 128 MB max uncompressed page size to prevent Zip bomb/OOM
MAX_COMICINFO_SIZE = 8 * 1024 * 1024  # 8 MB cap for ComicInfo.xml members
MAX_SIDECAR_SIZE = 4 * 1024 * 1024  # 4 MB cap for .galleryvault.json members
# Legacy codepages used when a ZIP member name was written without the UTF-8
# flag (bit 11).  Python decodes those names as cp437 by default.
_LEGACY_ZIP_ENCODINGS = ("utf-8", "gbk", "cp932")
_encoding_cache: dict[str, tuple[int, str | None]] = {}
_encoding_cache_lock = threading.Lock()


def _has_cjk(text: str) -> bool:
    for char in text:
        code = ord(char)
        if (
            0x3040 <= code <= 0x30FF  # kana
            or 0x3400 <= code <= 0x9FFF  # CJK ideographs
            or 0xAC00 <= code <= 0xD7AF  # hangul
            or 0xF900 <= code <= 0xFAFF  # CJK compatibility ideographs
        ):
            return True
    return False


def _legacy_zip_name_encoding(name: str, flag_bits: int) -> str | None:
    """Return the codepage that recovers a non-UTF-8-flagged member name."""
    if flag_bits & 0x800:
        return None
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return None
    for encoding in _LEGACY_ZIP_ENCODINGS:
        try:
            decoded = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded != name and _has_cjk(decoded):
            return encoding
    return None


def detect_zip_metadata_encoding(path: Path | str) -> str | None:
    """Probe a ZIP for member names written with a legacy codepage (GBK/cp932)."""
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        return None
    with _encoding_cache_lock:
        cached = _encoding_cache.get(cache_key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
    encoding: str | None = None
    try:
        with zipfile.ZipFile(resolved) as archive:
            for info in archive.infolist():
                found = _legacy_zip_name_encoding(info.filename, info.flag_bits)
                if found is not None:
                    encoding = found
                    break
    except (OSError, zipfile.BadZipFile):
        return None
    with _encoding_cache_lock:
        if len(_encoding_cache) >= 64:
            _encoding_cache.pop(next(iter(_encoding_cache)))
        _encoding_cache[cache_key] = (mtime, encoding)
    return encoding


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
                if not Path(name.replace("\\", "/")).name.startswith(".")
                and Path(name.replace("\\", "/")).suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda n: natural_key(n.replace("\\", "/")),
        )
        return [
            PageInfo(
                i,
                name,
                Path(name.replace("\\", "/")).suffix.casefold().lstrip("."),
                sizes.get(name),
            )
            for i, name in enumerate(images)
        ]

    def _meta(
        self, path: Path, pages: list[PageInfo], raw: dict, **metadata: object
    ) -> GalleryMeta:
        stat = path.stat()
        digest = self.storage_signature(path)
        gid_match = re.match(r"^(\d{5,})-", path.stem)
        gid = int(gid_match.group(1)) if gid_match else None
        if gid is None and metadata.get("gid") is not None:
            try:
                gid = int(metadata["gid"])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        token = str(metadata["token"]) if metadata.get("token") else None
        tags = normalize_tags(metadata.get("tags"))
        image_quality = str(metadata["image_quality"]) if metadata.get("image_quality") else None
        fallback_title = strip_gid_prefix(path.stem, gid) if gid is not None else path.stem
        return GalleryMeta(
            title=str(metadata.get("title") or fallback_title),
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
    def _comic_info(
        archive: object, names: list[str], sizes: dict[str, int] | None = None
    ) -> tuple[dict, dict[str, object]]:
        comic = next(
            (
                name
                for name in names
                if Path(name.replace("\\", "/")).name.casefold() == "comicinfo.xml"
            ),
            None,
        )
        if not comic:
            return {}, {}
        if sizes is not None and sizes.get(comic, 0) > MAX_COMICINFO_SIZE:
            return {"comic_info_error": "ComicInfo.xml exceeds size limit"}, {}
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
            metadata["uploader"] = values["Writer"][:128]
        return {"comic_info": values}, metadata


_ZIP_CACHE_MAX = 16
_zip_cache: OrderedDict[str, tuple[zipfile.ZipFile, float, float, threading.RLock]] = OrderedDict()
_zip_cache_lock = threading.RLock()


def _cleanup_stale_zips(ttl: float = 300.0) -> int:
    """Close and remove cached ZipFiles that have been idle longer than ttl seconds."""
    now = time.monotonic()
    to_close: list[tuple[zipfile.ZipFile, threading.RLock]] = []
    with _zip_cache_lock:
        stale_keys = [
            key for key, (_, _, last_access, _) in _zip_cache.items()
            if now - last_access > ttl
        ]
        for key in stale_keys:
            zf, _, _, file_lock = _zip_cache.pop(key)
            to_close.append((zf, file_lock))

    closed = 0
    for zf, lock in to_close:
        try:
            with lock:
                zf.close()
                closed += 1
        except Exception:  # noqa: BLE001, S110
            pass
    return closed


def _close_all_zips() -> None:
    """Close all open zip archives in cache (e.g. at process exit)."""
    to_close: list[tuple[zipfile.ZipFile, threading.RLock]] = []
    with _zip_cache_lock:
        while _zip_cache:
            _, item = _zip_cache.popitem()
            to_close.append((item[0], item[3]))
    for zf, lock in to_close:
        try:
            with lock:
                zf.close()
        except Exception:  # noqa: BLE001, S110
            pass


atexit.register(_close_all_zips)


def _get_cached_zip(
    path: Path | str, metadata_encoding: str | None = None
) -> tuple[zipfile.ZipFile, threading.RLock]:
    _cleanup_stale_zips()
    resolved = Path(path).resolve()
    key = f"{resolved}\0{metadata_encoding or ''}"
    current_mtime = resolved.stat().st_mtime
    now = time.monotonic()

    to_close: list[tuple[zipfile.ZipFile, threading.RLock]] = []
    with _zip_cache_lock:
        entry = _zip_cache.get(key)
        if entry is not None:
            zf, cached_mtime, _, file_lock = entry
            if cached_mtime == current_mtime:
                _zip_cache[key] = (zf, cached_mtime, now, file_lock)
                _zip_cache.move_to_end(key)
                return zf, file_lock
            del _zip_cache[key]
            to_close.append((zf, file_lock))

        new_zf = zipfile.ZipFile(resolved, metadata_encoding=metadata_encoding)
        new_lock = threading.RLock()
        _zip_cache[key] = (new_zf, current_mtime, now, new_lock)
        _zip_cache.move_to_end(key)

        while len(_zip_cache) > _ZIP_CACHE_MAX:
            _, item = _zip_cache.popitem(last=False)
            to_close.append((item[0], item[3]))

    for old_zf, old_lock in to_close:
        try:
            with old_lock:
                old_zf.close()
        except Exception:  # noqa: BLE001, S110
            pass

    return new_zf, new_lock


class CbzZipScanner(ArchiveScanner):
    storage_type = "cbz"

    def matches(self, path: Path) -> bool:
        return path.is_file() and path.suffix.casefold() in {".cbz", ".zip"}

    def scan(self, path: Path) -> GalleryMeta:
        _cleanup_stale_zips()
        metadata_encoding = detect_zip_metadata_encoding(path)
        warnings: list[str] = []
        with zipfile.ZipFile(path, metadata_encoding=metadata_encoding) as archive:
            for info in archive.infolist():
                try:
                    validate_archive_member(info.filename, info)
                except ValueError as exc:
                    raise ValueError(f"{path}: {exc}") from exc
            sizes = {info.filename: info.file_size for info in archive.infolist()}
            pages = self._pages(list(sizes), sizes)
            raw, metadata = self._comic_info(archive, list(sizes), sizes)
            gv_name = next(
                (
                    name
                    for name in sizes
                    if Path(name.replace("\\", "/")).name.casefold() == SIDECAR_FILENAME.casefold()
                ),
                None,
            )
            if gv_name and sizes.get(gv_name, 0) > MAX_SIDECAR_SIZE:
                warnings.append(f"{SIDECAR_FILENAME} exceeds size limit")
                gv_name = None
            if gv_name:
                try:
                    gv_data = parse_galleryvault_json(archive.read(gv_name))
                    raw[SIDECAR_FILENAME] = gv_data
                    if gv_data.get("gid") is not None:
                        metadata["gid"] = gv_data["gid"]
                    if gv_data.get("token"):
                        metadata["token"] = gv_data["token"]
                    if gv_data.get("tags"):
                        metadata["tags"] = gv_data["tags"]
                    # Fix inverted title priority: sidecar title overrides ComicInfo Title
                    if gv_data.get("title"):
                        metadata["title"] = gv_data["title"]
                    if gv_data.get("title_jpn"):
                        metadata["title_jpn"] = gv_data["title_jpn"]
                    if gv_data.get("quality"):
                        metadata["image_quality"] = gv_data["quality"]
                    if gv_data.get("category"):
                        metadata["category"] = gv_data["category"]
                    if gv_data.get("uploader"):
                        metadata["uploader"] = gv_data["uploader"]
                    if gv_data.get("rating") is not None:
                        metadata["rating"] = gv_data["rating"]
                    if gv_data.get("posted"):
                        try:
                            metadata["posted_at"] = datetime.fromisoformat(str(gv_data["posted"]))
                        except (ValueError, TypeError):
                            pass
                except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError, TypeError):
                    pass
            return self._meta(path, pages, raw, warnings=warnings, **metadata)

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        if _is_unsafe_path(page.name):
            raise ValueError(f"unsafe page path: {page.name}")
        zf, file_lock = _get_cached_zip(
            gallery.path, detect_zip_metadata_encoding(gallery.path)
        )
        with file_lock:
            try:
                info = zf.getinfo(page.name)
            except KeyError:
                stem = Path(page.name.replace("\\", "/")).stem
                matched_name = next(
                    (
                        name
                        for name in zf.namelist()
                        if Path(name.replace("\\", "/")).stem == stem
                        and Path(name.replace("\\", "/")).suffix.casefold() in IMAGE_EXTENSIONS
                    ),
                    None,
                )
                if matched_name is None:
                    raise
                info = zf.getinfo(matched_name)
            if _is_symlink(info):
                raise ValueError(f"unsafe symlink in archive: {info.filename}")
            if info.file_size > MAX_ARCHIVE_PAGE_SIZE:
                raise ValueError(
                    f"page file exceeds size limit ({info.file_size} > {MAX_ARCHIVE_PAGE_SIZE}): {info.filename}"
                )
            with zf.open(info.filename) as member:
                buf = io.BytesIO()
                copied = 0
                while chunk := member.read(65536):
                    copied += len(chunk)
                    if copied > MAX_ARCHIVE_PAGE_SIZE:
                        raise ValueError(
                            f"page file exceeds size limit during extraction: {info.filename}"
                        )
                    buf.write(chunk)
                buf.seek(0)
                return buf


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
                raw, metadata = self._comic_info(archive, list(sizes), sizes)
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
                    if target_info is not None:
                        if _is_symlink(target_info):
                            raise ValueError(f"unsafe symlink in archive: {page.name}")
                        if getattr(target_info, "file_size", 0) > MAX_ARCHIVE_PAGE_SIZE:
                            raise ValueError(
                                f"page file exceeds size limit ({target_info.file_size} > {MAX_ARCHIVE_PAGE_SIZE}): {page.name}"
                            )
                except ValueError:
                    raise
                except Exception:  # noqa: BLE001, S110
                    pass
                with archive.open(page.name) as member:
                    buf = io.BytesIO()
                    copied = 0
                    while chunk := member.read(65536):
                        copied += len(chunk)
                        if copied > MAX_ARCHIVE_PAGE_SIZE:
                            raise ValueError(
                                f"page file exceeds size limit during extraction: {page.name}"
                            )
                        buf.write(chunk)
                    buf.seek(0)
                    return buf
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError("Unable to read CBR/RAR page; install unrar or libarchive") from exc
