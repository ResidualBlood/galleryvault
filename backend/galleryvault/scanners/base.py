from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

CATEGORIES = (
    "manga",
    "misc",
    "cosplay",
    "doujinshi",
    "artistcg",
    "gamecg",
    "western",
    "non-h",
    "image_set",
    "asianporn",
    "deleted",
    "other",
)

# ExHentai "Misc" and our generic fallback are the same bucket; unknown or
# unclassifiable galleries land here too.
GENERIC_CATEGORY = "misc"


def normalize_category(value: object) -> str:
    candidate = str(value or "").strip().casefold().replace(" ", "_")
    if candidate == "other":
        # 'other' (our generic bucket) and ExHentai's 'misc' are the same class.
        return GENERIC_CATEGORY
    if candidate in CATEGORIES:
        return candidate
    compact = candidate.replace("_", "")
    if compact in CATEGORIES:
        return compact
    return GENERIC_CATEGORY


def infer_category(path: Path, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    for value in (metadata.get("category"), *(parent.name for parent in path.parents)):
        candidate = str(value or "").strip().casefold().replace(" ", "_")
        if candidate in CATEGORIES:
            return candidate
    return GENERIC_CATEGORY


@dataclass(frozen=True)
class PageInfo:
    index: int
    name: str
    media_type: str
    size: int | None = None
    mtime_ns: int | None = None


@dataclass(frozen=True)
class ExistingGallery:
    """A gallery row already in the DB, folded into a scan as a known copy.

    Lets duplicate-copy resolution compare freshly scanned paths against the
    rows that are already ingested (and skipped by signature), so the same gid
    found under several roots can be merged deterministically instead of being
    silently re-pointed by scan order.
    """

    path: str
    signature: str
    gid: int | None
    gallery_id: int
    storage_type: str
    title: str
    title_jpn: str | None = None
    file_count: int | None = None
    file_size: int | None = None
    posted_at: datetime | None = None


@dataclass
class GalleryMeta:
    title: str
    path: Path
    storage_type: str
    pages: list[PageInfo]
    gid: int | None = None
    token: str | None = None
    title_jpn: str | None = None
    category: str | None = None
    uploader: str | None = None
    file_count: int | None = None
    file_size: int | None = None
    rating: float | None = None
    posted_at: datetime | None = None
    tags: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    image_quality: str | None = None
    source_meta: dict[str, Any] = field(default_factory=dict)
    storage_signature: str = ""
    storage_mtime_ns: int | None = None
    storage_size: int | None = None


class GalleryScanner(ABC):
    storage_type: str

    @abstractmethod
    def matches(self, path: Path) -> bool: ...
    def fingerprint(self, path: Path) -> str:
        return self.storage_signature(path)

    def storage_signature(self, path: Path) -> str:
        stat = path.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"

    @abstractmethod
    def scan(self, path: Path) -> GalleryMeta: ...
    @abstractmethod
    def open_page(self, gallery: GalleryMeta, page: PageInfo) -> BinaryIO: ...


class ScannerRegistry:
    def __init__(self) -> None:
        self._scanners: list[GalleryScanner] = []

    def register(self, scanner: GalleryScanner) -> None:
        self._scanners.append(scanner)

    def for_path(self, path: Path) -> GalleryScanner | None:
        return next((scanner for scanner in self._scanners if scanner.matches(path)), None)
