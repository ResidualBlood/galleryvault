import hashlib
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..logging import log_extra
from ..scanners import registry
from ..scanners.base import GalleryMeta
from ..scanners.ehviewer import _DIR_NAME as _BARE_DIR_NAME

logger = logging.getLogger(__name__)


@dataclass
class ScanCounters:
    scanned: int = 0
    skipped: int = 0
    success: int = 0
    errors: int = 0


@dataclass
class InMemoryLibrary:
    galleries: dict[str, GalleryMeta] = field(default_factory=dict)

    def ingest(self, gallery: GalleryMeta) -> bool:
        key = (
            f"gid:{gallery.gid}"
            if gallery.gid is not None
            else f"path:{hashlib.sha256(str(gallery.path.resolve()).encode()).hexdigest()}"
        )
        existing = self.galleries.get(key)
        if existing and existing.storage_signature == gallery.storage_signature:
            return False
        self.galleries[key] = gallery
        return True


class LibraryService:
    def __init__(
        self,
        roots: Iterable[str | Path],
        store: InMemoryLibrary | None = None,
        batch_size: int = 500,
        known_signatures: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.roots = [Path(root) for root in roots]
        self.store = store or InMemoryLibrary()
        self.batch_size = batch_size
        self.known_signatures = known_signatures or {}
        self.last_counters = ScanCounters()
        self.seen_path_hashes: set[str] = set()

    def candidates(self) -> Iterable[Path]:
        for root in self.roots:
            if not root.exists():
                logger.warning("library root missing", extra=log_extra(root=str(root)))
                continue
            if registry.for_path(root) is not None:
                yield root
                continue
            yield from (
                item
                for item in root.rglob("*")
                if (
                    item.is_dir()
                    and ((item / ".ehviewer").is_file() or _BARE_DIR_NAME.match(item.name))
                )
                or (item.is_file() and item.suffix.casefold() in {".cbz", ".zip", ".cbr", ".rar"})
            )

    def scan_batches(self, should_stop=None) -> Iterator[list[GalleryMeta]]:
        """Yield galleries in bounded batches.

        ``should_stop`` (optional callable) is checked before every gallery so a
        long scan can be cancelled between individual galleries instead of only
        between batches. When it returns ``True`` the scan stops early and the
        remaining galleries are skipped.
        """
        counters = ScanCounters()
        batch: list[GalleryMeta] = []
        logger.info("library scan start", extra=log_extra(roots=[str(r) for r in self.roots]))
        for path in self.candidates():
            if should_stop is not None and should_stop():
                logger.info("library scan cancelled", extra=log_extra(processed=counters.scanned))
                break
            counters.scanned += 1
            try:
                key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
                self.seen_path_hashes.add(key)
                scanner = registry.for_path(path)
                if scanner is None:
                    continue
                known = self.known_signatures.get(key)
                if known and known[0] == scanner.fingerprint(path):
                    counters.skipped += 1
                    continue
                gallery = scanner.scan(path)
                if not self.store.ingest(gallery):
                    counters.skipped += 1
                    logger.info(
                        "library scan skip", extra=log_extra(path=str(path), gid=gallery.gid)
                    )
                else:
                    counters.success += 1
                    batch.append(gallery)
                    logger.info(
                        "library scan success",
                        extra=log_extra(path=str(path), gid=gallery.gid, pages=len(gallery.pages)),
                    )
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []
            except Exception as exc:  # noqa: BLE001 - one bad gallery must not abort a full scan
                counters.errors += 1
                logger.error("library scan error", extra=log_extra(path=str(path), error=str(exc)))
        if batch:
            yield batch
        self.last_counters = counters
        logger.info("library scan complete", extra=log_extra(**counters.__dict__))

    def scan(self) -> tuple[list[GalleryMeta], ScanCounters]:
        result: list[GalleryMeta] = []
        # Compatibility API; callers needing bounded memory should consume scan_batches().
        for batch in self.scan_batches():
            result.extend(batch)
        return result, self.last_counters
