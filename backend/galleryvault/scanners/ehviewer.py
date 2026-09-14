import hashlib
import json
import re
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree

from ehviewer_parser import (
    SpiderInfo,
    SpiderPageEntry,
    natural_key,
    parse_spider_info,
    strip_gid_prefix,
)

from ..metadata.sidecar import (
    SIDECAR_FILENAME,
    normalize_tags,
    parse_datetime_utc,
    read_galleryvault_json,
)
from .base import GalleryMeta, GalleryScanner, PageInfo, infer_category

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
_GID = re.compile(r"^(\d+)-")

__all__ = [
    "IMAGE_EXTENSIONS",
    "BareImageDirScanner",
    "EhviewerDirScanner",
    "JhentaiDirScanner",
    "SpiderInfo",
    "SpiderPageEntry",
    "natural_key",
    "parse_jhentai_posted",
    "parse_jhentai_tags",
    "parse_spider_info",
    "strip_gid_prefix",
]


_JHENTAI_TAG = re.compile(r"^([^:]*):(.*)$")


def parse_jhentai_tags(raw: object) -> list[dict[str, str]]:
    """Parse JHenTai's comma-joined ``namespace:key`` tag string."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    tags: list[dict[str, str]] = []
    for item in raw.split(","):
        val = item.strip()
        if not val:
            continue
        m = _JHENTAI_TAG.match(val)
        if m:
            ns, name = m.group(1).strip(), m.group(2).strip()
        else:
            ns, name = "misc", val
        if name:
            tags.append({"namespace": ns or "misc", "name": name})
    return tags


parse_jhentai_posted = parse_datetime_utc


def _safe_resolve_page_file(gallery_dir: Path, page_name: str) -> Path:
    root = gallery_dir.resolve()
    name = (page_name or "").replace("\\", "/")
    if not name or name.startswith(("/", "~")):
        raise ValueError(f"unsafe page path: {page_name}")
    parts = Path(name).parts
    if ".." in parts:
        raise ValueError(f"unsafe page path: {page_name}")
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"unsafe page path: {page_name}")
    return candidate


class EhviewerDirScanner(GalleryScanner):
    storage_type = "ehviewer_dir"

    def matches(self, path: Path) -> bool:
        return path.is_dir() and (path / ".ehviewer").is_file()

    def scan(self, path: Path) -> GalleryMeta:
        try:
            spider = parse_spider_info((path / ".ehviewer").read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
        declared = spider.pages
        files = sorted(
            (
                item
                for item in path.iterdir()
                if item.is_file()
                and not item.name.startswith(".")
                and item.suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda item: natural_key(item.name),
        )
        warnings = list(spider.warnings)
        if len(files) != declared:
            warnings.append(f"page count mismatch: metadata={declared}, images={len(files)}")
        pages = [
            PageInfo(
                i,
                item.name,
                item.suffix.casefold().lstrip("."),
                item.stat().st_size,
                item.stat().st_mtime_ns,
            )
            for i, item in enumerate(files)
        ]
        signature = self.storage_signature(path)
        source_meta = spider.source_meta()

        metadata_path = path / SIDECAR_FILENAME
        gv_data = None
        if metadata_path.is_file():
            gv_data = read_galleryvault_json(metadata_path)
            if gv_data is not None:
                source_meta.update(gv_data)
            else:
                warnings.append("invalid .galleryvault.json")

        # Filename regex gid has priority over sidecar gid; sidecar gid has priority over spider
        gid_match = _GID.match(path.name)
        if gid_match:
            gid = int(gid_match.group(1))
        elif gv_data and gv_data.get("gid") is not None:
            gid = gv_data["gid"]
        else:
            gid = spider.gid

        # token and p_tokens: sidecar priority, fallback to spider
        token = (gv_data.get("token") if gv_data else None) or spider.token
        if gv_data and gv_data.get("p_tokens"):
            source_meta["p_tokens"] = gv_data["p_tokens"]

        fallback_title = strip_gid_prefix(path.name, gid) or path.name
        title = (gv_data.get("title") if gv_data and gv_data.get("title") else None) or fallback_title
        title_jpn = (gv_data.get("title_jpn") if gv_data and gv_data.get("title_jpn") else None) or source_meta.get("title_jpn")
        tags = normalize_tags(
            gv_data.get("tags")
            if (gv_data and gv_data.get("tags"))
            else source_meta.get("tags")
        )
        category = (gv_data.get("category") if gv_data and gv_data.get("category") else None) or infer_category(path, source_meta)
        image_quality = gv_data.get("quality") if gv_data else source_meta.get("quality")
        uploader = gv_data.get("uploader") if gv_data else None
        rating = gv_data.get("rating") if gv_data else None
        posted_at = parse_datetime_utc(gv_data.get("posted")) if gv_data else None

        return GalleryMeta(
            title=title,
            title_jpn=title_jpn,
            path=path,
            storage_type=self.storage_type,
            pages=pages,
            gid=gid,
            token=token,
            uploader=uploader,
            rating=rating,
            posted_at=posted_at,
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            warnings=warnings,
            category=category,
            tags=tags,
            image_quality=image_quality,
            source_meta=source_meta,
            storage_signature=signature,
            storage_mtime_ns=path.stat().st_mtime_ns,
            storage_size=sum(p.size or 0 for p in pages),
        )

    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        digest = hashlib.sha256()
        try:
            st = path.stat()
            digest.update(f"{path.name}\0{st.st_size}\0{st.st_mtime_ns}".encode())
        except OSError:
            pass
        for name in (".ehviewer", SIDECAR_FILENAME):
            try:
                st = (path / name).stat()
                digest.update(f"{name}\0{st.st_size}\0{st.st_mtime_ns}".encode())
            except OSError:
                continue
        return digest.hexdigest()

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        return _safe_resolve_page_file(gallery.path, page.name).open("rb")


class JhentaiDirScanner(GalleryScanner):
    """Scanner for JHenTai (https://github.com/jiangtian616/JHenTai) downloads.

    JHenTai stores each gallery as ``<gid> - <sanitizedTitle>/`` with the page
    images named ``<serial>.<ext>`` plus a ``metadata`` JSON file holding a
    ``gallery`` object (gid/token/title/category/uploader/publishTime/tags) and
    a JSON-encoded ``images`` list. Parsing the metadata restores the full
    gallery identity (token, tags, category, uploader, posted date) that a bare
    folder-name match alone cannot provide.
    """

    storage_type = "jhentai_dir"
    _METADATA_NAME = "metadata"

    def matches(self, path: Path) -> bool:
        if not path.is_dir() or (path / ".ehviewer").is_file():
            return False
        metadata = path / self._METADATA_NAME
        if not metadata.is_file():
            return False
        try:
            with metadata.open("r", encoding="utf-8") as fh:
                head = fh.read(4096)
        except OSError:
            return False
        return '"gallery"' in head

    def scan(self, path: Path) -> GalleryMeta:
        metadata_path = path / self._METADATA_NAME
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}: invalid JHenTai metadata") from exc
        gallery = payload.get("gallery") if isinstance(payload, dict) else None
        if not isinstance(gallery, dict):
            raise TypeError(f"{path}: JHenTai metadata 'gallery' must be an object")
        gid = gallery.get("gid")
        if not isinstance(gid, int):
            raise TypeError(f"{path}: JHenTai gid must be an integer")
        if gid <= 0:
            raise ValueError(f"{path}: invalid JHenTai gid")
        token = gallery.get("token")
        if not isinstance(token, str) or not token:
            token = None
        title = str(gallery.get("title") or path.name)
        category = infer_category(path, {"category": gallery.get("category")})
        uploader = gallery.get("uploader")
        if not isinstance(uploader, str):
            uploader = None
        posted_at = parse_datetime_utc(gallery.get("publishTime"))
        tags = parse_jhentai_tags(gallery.get("tags"))
        declared_pages = gallery.get("pageCount")
        files = sorted(
            (
                item
                for item in path.iterdir()
                if item.is_file()
                and not item.name.startswith(".")
                and item.suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda item: natural_key(item.name),
        )
        warnings: list[str] = []
        if (
            isinstance(declared_pages, int)
            and declared_pages > 0
            and len(files) != declared_pages
        ):
            warnings.append(f"page count mismatch: metadata={declared_pages}, images={len(files)}")
        pages = [
            PageInfo(
                i,
                item.name,
                item.suffix.casefold().lstrip("."),
                item.stat().st_size,
                item.stat().st_mtime_ns,
            )
            for i, item in enumerate(files)
        ]
        return GalleryMeta(
            title=title,
            title_jpn=None,
            path=path,
            storage_type=self.storage_type,
            pages=pages,
            gid=gid,
            token=token,
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            warnings=warnings,
            category=category,
            uploader=uploader,
            posted_at=posted_at,
            tags=tags,
            source_meta={"jhentai": {"gallery": gallery}},
            storage_signature=self.storage_signature(path),
            storage_mtime_ns=path.stat().st_mtime_ns,
            storage_size=sum(p.size or 0 for p in pages),
        )

    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        digest = hashlib.sha256()
        try:
            st = path.stat()
            digest.update(f"{path.name}\0{st.st_size}\0{st.st_mtime_ns}".encode())
        except OSError:
            pass
        for name in (self._METADATA_NAME, SIDECAR_FILENAME):
            try:
                st = (path / name).stat()
                digest.update(f"{name}\0{st.st_size}\0{st.st_mtime_ns}".encode())
            except OSError:
                continue
        return digest.hexdigest()

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        return _safe_resolve_page_file(gallery.path, page.name).open("rb")


_DIR_NAME = re.compile(r"^\s*(\d+)\s*[-\s_]\s*(.+?)\s*$")


class BareImageDirScanner(GalleryScanner):
    """Fallback scanner for image directories without an ``.ehviewer`` file.

    Ehviewer-style folder names are ``<gid>-<japanese title>``; when no
    ``.ehviewer`` metadata exists we parse the gallery id and title directly
    from the directory name and index the contained images.
    """

    storage_type = "folder"

    def matches(self, path: Path) -> bool:
        if not path.is_dir() or (path / ".ehviewer").is_file():
            return False
        has_gv_json = (path / SIDECAR_FILENAME).is_file()
        if not has_gv_json and not _DIR_NAME.match(path.name):
            return False
        return any(
            item.is_file()
            and not item.name.startswith(".")
            and item.suffix.casefold() in IMAGE_EXTENSIONS
            for item in path.iterdir()
        )

    def scan(self, path: Path) -> GalleryMeta:
        match = _DIR_NAME.match(path.name)
        filename_gid = int(match.group(1)) if match else None
        rest = match.group(2) if match else path.name
        if filename_gid is None and path.name.isdigit():
            filename_gid = int(path.name)

        files = sorted(
            (
                item
                for item in path.iterdir()
                if item.is_file()
                and not item.name.startswith(".")
                and item.suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda item: natural_key(item.name),
        )
        warnings: list[str] = []
        if not files:
            warnings.append("no image files found")
        source_meta: dict[str, object] = {}

        metadata_path = path / SIDECAR_FILENAME
        gv_data = None
        if metadata_path.is_file():
            gv_data = read_galleryvault_json(metadata_path)
            if gv_data is not None:
                source_meta.update(gv_data)
            else:
                warnings.append("invalid .galleryvault.json")

        comic_title = None
        comic_tags: list[dict[str, str]] = []
        comic_uploader = None
        comic_path = path / "ComicInfo.xml"
        if comic_path.is_file():
            try:
                root = ElementTree.fromstring(comic_path.read_bytes())
                values = {child.tag.split("}")[-1]: (child.text or "").strip() for child in root}
                source_meta["comic_info"] = values
                if values.get("Title"):
                    comic_title = values["Title"]
                if values.get("Genre"):
                    comic_tags = [
                        {"namespace": "misc", "name": t.strip()}
                        for t in values["Genre"].split(",")
                        if t.strip()
                    ]
                if values.get("Writer"):
                    comic_uploader = values["Writer"][:128]
            except (ElementTree.ParseError, OSError):
                warnings.append("invalid ComicInfo.xml")

        # Filename regex gid has priority over sidecar gid
        if filename_gid is not None:
            gid = filename_gid
        elif gv_data and gv_data.get("gid") is not None:
            gid = gv_data["gid"]
        else:
            gid = None

        rest = strip_gid_prefix(rest, gid) or rest

        # Priority: sidecar > ComicInfo > folder name
        if gv_data and gv_data.get("title"):
            title = gv_data["title"]
        elif comic_title:
            title = comic_title
        else:
            title = rest

        if gv_data and gv_data.get("title_jpn"):
            title_jpn = gv_data["title_jpn"]
        elif rest and not rest.strip().isdigit():
            title_jpn = rest
        else:
            title_jpn = None

        tags = normalize_tags(
            gv_data.get("tags")
            if (gv_data and gv_data.get("tags"))
            else comic_tags
        )

        if gv_data and gv_data.get("category"):
            category = gv_data["category"]
        else:
            category = infer_category(path, source_meta)

        image_quality = gv_data.get("quality") if gv_data else source_meta.get("quality")
        token = gv_data.get("token") if gv_data else None
        uploader = (gv_data.get("uploader") if gv_data and gv_data.get("uploader") else None) or comic_uploader
        rating = gv_data.get("rating") if gv_data else None
        posted_at = parse_datetime_utc(gv_data.get("posted")) if gv_data else None

        if gv_data and gv_data.get("p_tokens"):
            source_meta["p_tokens"] = gv_data["p_tokens"]

        pages = [
            PageInfo(
                i,
                item.name,
                item.suffix.casefold().lstrip("."),
                item.stat().st_size,
                item.stat().st_mtime_ns,
            )
            for i, item in enumerate(files)
        ]
        return GalleryMeta(
            title=title,
            title_jpn=title_jpn,
            path=path,
            storage_type=self.storage_type,
            pages=pages,
            gid=gid,
            token=token,
            uploader=uploader,
            rating=rating,
            posted_at=posted_at,
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            warnings=warnings,
            category=category,
            tags=tags,
            image_quality=image_quality,
            source_meta=source_meta,
            storage_signature=self.storage_signature(path),
            storage_mtime_ns=path.stat().st_mtime_ns,
            storage_size=sum(p.size or 0 for p in pages),
        )

    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        digest = hashlib.sha256()
        try:
            st = path.stat()
            digest.update(f"{path.name}\0{st.st_size}\0{st.st_mtime_ns}".encode())
        except OSError:
            pass
        for name in ("ComicInfo.xml", SIDECAR_FILENAME):
            try:
                st = (path / name).stat()
                digest.update(f"{name}\0{st.st_size}\0{st.st_mtime_ns}".encode())
            except OSError:
                continue
        return digest.hexdigest()

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        return _safe_resolve_page_file(gallery.path, page.name).open("rb")
