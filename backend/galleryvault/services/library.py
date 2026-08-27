import hashlib
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..logging import log_extra
from ..scanners import registry
from ..scanners.base import ExistingGallery, GalleryMeta
from ..scanners.ehviewer import _DIR_NAME as _BARE_DIR_NAME
from .duplicate_resolver import (
    DEFAULT_DUPLICATE_POLICY,
    Copy,
    ResolvedGroup,
    resolve_group,
)

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


def _path_key(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


def _root_priority(roots: list[Path], path: Path) -> int:
    resolved = path.resolve()
    for index, root in enumerate(roots):
        if resolved.is_relative_to(root):
            return index
    return len(roots)


class LibraryService:
    def __init__(
        self,
        roots: Iterable[str | Path],
        store: InMemoryLibrary | None = None,
        batch_size: int = 500,
        existing: dict[str, ExistingGallery] | None = None,
        duplicate_policy: str = DEFAULT_DUPLICATE_POLICY,
    ) -> None:
        self.roots = [Path(root) for root in roots]
        self.store = store or InMemoryLibrary()
        self.batch_size = batch_size
        self.existing = existing or {}
        self.duplicate_policy = duplicate_policy
        self.last_counters = ScanCounters()
        self.last_duplicates: list[ResolvedGroup] = []
        self.seen_path_hashes: set[str] = set()
        self._seen_signatures: set[tuple[str, str]] = set()

    def candidates(self) -> Iterable[tuple[Path, int]]:
        for priority, root in enumerate(self.roots):
            if not root.exists():
                logger.warning("library root missing", extra=log_extra(root=str(root)))
                continue
            if registry.for_path(root) is not None:
                yield root, priority
                continue
            yield from (
                (item, priority)
                for item in root.rglob("*")
                if (
                    item.is_dir()
                    and ((item / ".ehviewer").is_file() or _BARE_DIR_NAME.match(item.name))
                )
                or (item.is_file() and item.suffix.casefold() in {".cbz", ".zip", ".cbr", ".rar"})
            )

    def scan_batches(self, should_stop=None) -> Iterator[list[GalleryMeta]]:
        """Two-phase scan: collect every copy first, then resolve duplicates.

        Phase 1 walks the roots and gathers each candidate as a ``Copy``,
        folding in rows already in the DB (so a skipped-by-signature copy still
        counts).  Phase 2 groups copies by gid and lets ``duplicate_policy``
        pick a winner per group; only the winners and gid-less copies are
        yielded for ingestion.  The losers are reported in ``last_duplicates``
        so the caller can persist them for the cleanup page.

        ``should_stop`` (optional callable) is checked before every candidate so
        a long scan can be cancelled between galleries.
        """
        counters = ScanCounters()
        copies_by_gid: dict[int, list[Copy]] = {}
        non_gid: list[GalleryMeta] = []
        self.last_duplicates = []
        logger.info("library scan start", extra=log_extra(roots=[str(r) for r in self.roots]))
        for path, priority in self.candidates():
            if should_stop is not None and should_stop():
                logger.info("library scan cancelled", extra=log_extra(processed=counters.scanned))
                break
            counters.scanned += 1
            key = _path_key(path)
            self.seen_path_hashes.add(key)
            scanner = registry.for_path(path)
            if scanner is None:
                continue
            known = self.existing.get(key)
            if known is not None and known.signature == scanner.fingerprint(path):
                counters.skipped += 1
                if known.gid is not None:
                    copies_by_gid.setdefault(known.gid, []).append(
                        Copy.from_existing(known, _root_priority(self.roots, Path(known.path)))
                    )
                continue
            try:
                gallery = scanner.scan(path)
            except Exception as exc:  # noqa: BLE001 - one bad gallery must not abort a full scan
                counters.errors += 1
                logger.error("library scan error", extra=log_extra(path=str(path), error=str(exc)))
                continue
            seen_key = (key, gallery.storage_signature)
            if seen_key in self._seen_signatures:
                # Same content already collected on this instance (re-scan of an
                # unchanged library without the DB ``existing`` map).
                counters.skipped += 1
                continue
            self._seen_signatures.add(seen_key)
            if gallery.gid is not None:
                copies_by_gid.setdefault(gallery.gid, []).append(
                    Copy.from_meta(gallery, priority)
                )
            else:
                non_gid.append(gallery)
        winners: list[GalleryMeta] = []
        for gid, copies in copies_by_gid.items():
            if len(copies) == 1:
                if copies[0].meta is not None:
                    winners.append(copies[0].meta)
                    counters.success += 1
                else:
                    counters.skipped += 1
                continue
            resolved = resolve_group(gid, copies, self.duplicate_policy)
            self.last_duplicates.append(resolved)
            if resolved.winner is not None and resolved.winner.meta is not None:
                winners.append(resolved.winner.meta)
                counters.success += 1
            else:
                counters.skipped += 1
        batch: list[GalleryMeta] = []
        for gallery in winners:
            batch.append(gallery)
            logger.info(
                "library scan success",
                extra=log_extra(path=str(gallery.path), gid=gallery.gid, pages=len(gallery.pages)),
            )
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        for gallery in non_gid:
            batch.append(gallery)
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
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
