import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

from .base import GalleryMeta, GalleryScanner, PageInfo, infer_category

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
_GID = re.compile(r"^(\d+)-")
_TOKEN = re.compile(r"^[A-Za-z0-9]+$")
MAX_PAGES = 100_000
MAX_HEADER_LINE_LENGTH = 1024


@dataclass(frozen=True)
class SpiderPageEntry:
    index: int
    p_token: str


@dataclass(frozen=True)
class SpiderInfo:
    version: str
    start_page: int
    gid: int
    token: str
    mode: int
    preview_pages: int
    preview_per_page: int | None
    pages: int
    page_entries: list[SpiderPageEntry]
    warnings: list[str]

    @property
    def p_tokens(self) -> list[str]:
        return [entry.p_token for entry in self.page_entries]

    def source_meta(self) -> dict[str, object]:
        result = asdict(self)
        result["p_tokens"] = self.p_tokens
        result["page_entries"] = [asdict(entry) for entry in self.page_entries]
        return result


def parse_spider_info(text: str) -> SpiderInfo:
    """Parse Ehviewer SpiderInfo v1/v2 without discarding recoverable entries."""
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ValueError("empty .ehviewer")
    marker = lines[0].strip()
    if marker.startswith("VERSION") and marker not in {"VERSION1", "VERSION2"}:
        raise ValueError("unsupported SpiderInfo version")
    version2 = marker == "VERSION2"
    version = "VERSION2" if version2 else "VERSION1"
    offset = 1 if marker in {"VERSION1", "VERSION2"} else 0
    # Both formats carry the same physical header fields. VERSION1 ignores
    # previewPerPage, while VERSION2 stores it.
    field_count = 7
    if len(lines) < offset + field_count:
        raise ValueError(f"malformed {version} header")
    if any(len(line) > MAX_HEADER_LINE_LENGTH for line in lines[offset : offset + field_count]):
        raise ValueError(f"{version} header line is too long")
    fields = [line.strip() for line in lines[offset : offset + field_count]]
    try:
        start_page = int(fields[0], 16)
        gid = int(fields[1])
        token = fields[2]
        mode = int(fields[3])
        preview_pages = int(fields[4])
        preview_per_page = int(fields[5]) if version2 else None
        pages = int(fields[6])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"malformed {version} header fields") from exc
    if start_page < 0 or gid <= 0 or not _TOKEN.fullmatch(token) or len(token) > 64:
        raise ValueError("invalid start_page, gid, or token")
    if mode < 0 or preview_pages < 0 or pages <= 0 or pages > MAX_PAGES:
        raise ValueError("invalid page counts")
    if version2 and (preview_per_page is None or preview_per_page < 0):
        raise ValueError("invalid preview_per_page")

    warnings: list[str] = []
    entries: list[SpiderPageEntry] = []
    seen: set[int] = set()
    entry_offset = offset + field_count
    for line_number, line in enumerate(lines[entry_offset:], entry_offset + 1):
        if len(line) > 2048:
            warnings.append(f"line {line_number}: page entry is too long")
            continue
        parts = line.split()
        if not parts:
            continue
        if len(parts) < 2:
            warnings.append(f"line {line_number}: missing pToken")
            continue
        try:
            index = int(parts[0])
        except ValueError:
            warnings.append(f"line {line_number}: invalid page index")
            continue
        p_token = parts[1]
        if len(p_token) > 128:
            warnings.append(f"line {line_number}: pToken is too long")
            continue
        if index in seen:
            warnings.append(f"line {line_number}: duplicate page index {index}")
            continue
        if index < 0 or index >= pages:
            warnings.append(f"line {line_number}: page index {index} out of range")
            continue
        if not _TOKEN.fullmatch(p_token):
            warnings.append(f"line {line_number}: invalid pToken")
            continue
        seen.add(index)
        entries.append(SpiderPageEntry(index, p_token))
    if len(entries) < pages:
        warnings.append(f"missing pToken entries: metadata={pages}, parsed={len(entries)}")
    if len(lines[entry_offset:]) > pages:
        warnings.append("extra page entry lines")
    return SpiderInfo(
        version,
        start_page,
        gid,
        token,
        mode,
        preview_pages,
        preview_per_page,
        pages,
        entries,
        warnings,
    )


def natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]


class EhviewerDirScanner(GalleryScanner):
    storage_type = "ehviewer_dir"

    def matches(self, path: Path) -> bool:
        return path.is_dir() and (path / ".ehviewer").is_file()

    def scan(self, path: Path) -> GalleryMeta:
        try:
            spider = parse_spider_info((path / ".ehviewer").read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
        gid, token, declared = spider.gid, spider.token, spider.pages
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
        metadata_path = path / ".galleryvault.json"
        if metadata_path.is_file():
            try:
                extra = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(extra, dict):
                    source_meta.update(extra)
            except (OSError, json.JSONDecodeError):
                warnings.append("invalid .galleryvault.json")
        title = source_meta.get("title") or path.name
        title_jpn = source_meta.get("title_jpn")
        tags = source_meta.get("tags") or []
        return GalleryMeta(
            title=title,
            title_jpn=title_jpn,
            path=path,
            storage_type=self.storage_type,
            pages=pages,
            gid=gid,
            token=token,
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            warnings=warnings,
            category=infer_category(path, source_meta),
            tags=tags,
            source_meta=source_meta,
            storage_signature=signature,
            storage_mtime_ns=path.stat().st_mtime_ns,
            storage_size=sum(p.size or 0 for p in pages),
        )

    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        digest = hashlib.sha256()
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
        metadata_stat = (path / ".ehviewer").stat()
        digest.update(f".ehviewer\0{metadata_stat.st_size}\0{metadata_stat.st_mtime_ns}".encode())
        for item in files:
            stat = item.stat()
            digest.update(f"{item.name}\0{stat.st_size}\0{stat.st_mtime_ns}".encode())
        return digest.hexdigest()

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        return (gallery.path / page.name).open("rb")


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
        if not _DIR_NAME.match(path.name):
            return False
        return any(
            item.is_file()
            and not item.name.startswith(".")
            and item.suffix.casefold() in IMAGE_EXTENSIONS
            for item in path.iterdir()
        )

    def scan(self, path: Path) -> GalleryMeta:
        match = _DIR_NAME.match(path.name)
        gid = int(match.group(1)) if match else None
        rest = match.group(2) if match else path.name
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
        title = rest
        title_jpn = None
        tags: list[dict[str, str]] = []
        metadata_path = path / ".galleryvault.json"
        if metadata_path.is_file():
            try:
                extra = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(extra, dict):
                    source_meta.update(extra)
                    title = extra.get("title") or rest
                    title_jpn = extra.get("title_jpn")
                    tags = extra.get("tags") or []
            except (OSError, json.JSONDecodeError):
                warnings.append("invalid .galleryvault.json")
        if title_jpn is None:
            title_jpn = rest
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
            token=None,
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            warnings=warnings,
            category=infer_category(path, source_meta),
            tags=tags,
            source_meta=source_meta,
            storage_signature=self.storage_signature(path),
            storage_mtime_ns=path.stat().st_mtime_ns,
            storage_size=sum(p.size or 0 for p in pages),
        )

    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        digest = hashlib.sha256()
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
        for item in files:
            stat = item.stat()
            digest.update(f"{item.name}\0{stat.st_size}\0{stat.st_mtime_ns}".encode())
        return digest.hexdigest()

    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO:
        return (gallery.path / page.name).open("rb")
