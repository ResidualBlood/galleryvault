import hashlib
import logging
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..logging import log_extra
from ..scanners import registry
from ..scanners.base import ExistingGallery, GalleryMeta
from ..scanners.ehviewer import _DIR_NAME as _BARE_DIR_NAME
from ..scanners.ehviewer import IMAGE_EXTENSIONS
from .duplicate_resolver import (
    DEFAULT_DUPLICATE_POLICY,
    Copy,
    ResolvedGroup,
    resolve_group,
)

logger = logging.getLogger(__name__)

# Process-wide record of files whose scan failed, keyed by
# ``(path_hash, signature)``.  A broken archive is then reported (error log +
# error counter) once per process instead of on every scan.  Repairing or
# replacing the file changes its signature, which makes the next scan retry.
# Only regular files are cached: a directory gallery failing on a transient
# IO error must stay retryable even when its stat signature does not change.
_KNOWN_BAD_FILES: OrderedDict[tuple[str, str], None] = OrderedDict()
_KNOWN_BAD_LIMIT = 1024


def _is_known_bad(path_hash: str, signature: str) -> bool:
    return (path_hash, signature) in _KNOWN_BAD_FILES


def _remember_bad_file(path_hash: str, signature: str) -> None:
    key = (path_hash, signature)
    _KNOWN_BAD_FILES[key] = None
    _KNOWN_BAD_FILES.move_to_end(key)
    while len(_KNOWN_BAD_FILES) > _KNOWN_BAD_LIMIT:
        _KNOWN_BAD_FILES.popitem(last=False)


def _forget_bad_file(path_hash: str) -> None:
    for stale in [key for key in _KNOWN_BAD_FILES if key[0] == path_hash]:
        del _KNOWN_BAD_FILES[stale]


def reset_known_bad_files() -> None:
    """Clear the process-wide failed-file cache (used by tests / manual repair)."""
    _KNOWN_BAD_FILES.clear()


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
        try:
            resolved_root = root.resolve()
        except OSError:
            resolved_root = root
        if resolved.is_relative_to(resolved_root):
            return index
    return len(roots)


def _page_stat_digest(path: Path) -> str:
    """Digest of the page files' ``name:size:mtime_ns`` inside a directory gallery.

    Stat-only (never reads page contents) so an in-place page overwrite that
    does not touch the directory mtime still changes the signature.
    """
    digest = hashlib.sha256()
    try:
        entries = sorted(
            (
                entry
                for entry in path.iterdir()
                if entry.is_file() and entry.suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda entry: entry.name,
        )
    except OSError:
        return ""
    for entry in entries:
        try:
            st = entry.stat()
        except OSError:
            continue
        digest.update(f"{entry.name}\0{st.st_size}\0{st.st_mtime_ns}\0".encode())
    return digest.hexdigest()


def _scan_signature(scanner: Any, path: Path) -> tuple[str, str]:
    """Return ``(base, augmented)`` fingerprints for ``path``.

    Directory galleries embed a page-stat digest in ``augmented`` so editing a
    page in place invalidates the cached signature. Archive files keep the
    scanner signature unchanged.
    """
    base = scanner.fingerprint(path)
    if not path.is_dir():
        return base, base
    pages = _page_stat_digest(path)
    if not pages:
        return base, base
    return base, hashlib.sha256(f"{base}\0{pages}".encode()).hexdigest()


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
        # Roots that could not be fully traversed (missing, unreadable, walk
        # error or no candidates at all).  ``scan_worker`` must not expunge
        # rows when this is non-empty, otherwise an unmounted root would mark
        # the whole library as deleted.
        self.incomplete_roots: set[str] = set()

    @property
    def scan_incomplete(self) -> bool:
        return bool(self.incomplete_roots)

    def _root_has_known_rows(self, root: Path) -> bool:
        """Whether the DB has active rows under ``root`` (used for empty roots)."""
        try:
            resolved_root = root.resolve()
        except OSError:
            resolved_root = root
        for known in self.existing.values():
            path = getattr(known, "path", None)
            if not path:
                continue
            try:
                if Path(path).resolve().is_relative_to(resolved_root):
                    return True
            except (OSError, ValueError):
                continue
        return False

    def candidates(self) -> Iterable[tuple[Path, int]]:
        import os

        archive_exts = {".cbz", ".zip", ".cbr", ".rar", ".7z", ".pdf"}
        self.incomplete_roots = set()
        for priority, root in enumerate(self.roots):
            if not root.exists():
                logger.warning("library root missing", extra=log_extra(root=str(root)))
                self.incomplete_roots.add(str(root))
                continue
            try:
                resolved_root = root.resolve()
            except OSError:
                resolved_root = root
            if registry.for_path(root) is not None:
                yield root, priority
                continue
            found = 0

            def _on_walk_error(exc: OSError, _root: Path = root) -> None:
                self.incomplete_roots.add(str(_root))
                logger.warning(
                    "library scan error on root",
                    extra=log_extra(root=str(_root), error=str(exc)),
                )

            try:
                for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error):
                    # Exclude hidden directories (e.g. .git, .gv-*)
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                    current_path = Path(dirpath)
                    # Check if current directory is an Ehviewer gallery directory
                    if current_path != root and (
                        (current_path / ".ehviewer").is_file()
                        or (current_path / ".galleryvault.json").is_file()
                        or _BARE_DIR_NAME.match(current_path.name)
                    ):
                        # A bare-directory name is only a hint; confirm the
                        # registry really has a scanner for it before yielding
                        # and pruning, otherwise nested galleries would be
                        # silently skipped.
                        if registry.for_path(current_path) is None:
                            continue
                        found += 1
                        yield current_path, priority
                        # Prune: do not traverse into gallery directory's subdirectories
                        dirnames.clear()
                        continue
                    for fname in filenames:
                        if fname.startswith("."):
                            continue
                        fpath = current_path / fname
                        if fpath.suffix.casefold() in archive_exts:
                            if fpath.is_symlink():
                                # A symlinked file may point outside the root;
                                # ingesting it would create a row whose resolved
                                # path_hash is outside the library and therefore
                                # can never be expunged.
                                try:
                                    target = fpath.resolve()
                                except OSError:
                                    continue
                                if not target.is_relative_to(resolved_root):
                                    logger.debug(
                                        "skipping out-of-root symlink",
                                        extra=log_extra(path=str(fpath), target=str(target)),
                                    )
                                    continue
                            found += 1
                            yield fpath, priority
            except OSError as exc:
                logger.warning(
                    "library scan error on root",
                    extra=log_extra(root=str(root), error=str(exc)),
                )
                self.incomplete_roots.add(str(root))
            if found == 0 and self._root_has_known_rows(root):
                # An existing but empty root that still has DB rows is the
                # classic unmounted-volume shape; treat it as unverified rather
                # than "everything gone".  A genuinely empty new root (no rows)
                # stays complete so expunge keeps working for other roots.
                logger.warning("library root yielded no candidates", extra=log_extra(root=str(root)))
                self.incomplete_roots.add(str(root))

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
            # Normalize once so the scanner-produced GalleryMeta.path (which is
            # persisted as storage_path) matches path_hash, which is always
            # built from Path.resolve().
            path = Path(path).resolve()
            counters.scanned += 1
            key = _path_key(path)
            self.seen_path_hashes.add(key)
            scanner = registry.for_path(path)
            if scanner is None:
                continue
            known = self.existing.get(key)
            base_signature, signature = _scan_signature(scanner, path)
            if known is not None and known.signature in {base_signature, signature}:
                # ``base_signature`` keeps rows written by older releases
                # (scanner fingerprint only) skipping as before; fresh scans
                # persist ``signature`` below so page edits are detected.
                counters.skipped += 1
                if known.gid is not None:
                    copies_by_gid.setdefault(known.gid, []).append(
                        Copy.from_existing(known, _root_priority(self.roots, Path(known.path)))
                    )
                continue
            if path.is_file() and _is_known_bad(key, signature):
                # This exact file version already failed in this process; do not
                # parse it again and do not repeat the error log/counter.
                counters.skipped += 1
                logger.debug(
                    "library scan skip known bad file",
                    extra=log_extra(path=str(path)),
                )
                continue
            try:
                gallery = scanner.scan(path)
            except Exception as exc:  # noqa: BLE001 - one bad gallery must not abort a full scan
                counters.errors += 1
                if path.is_file():
                    _remember_bad_file(key, signature)
                logger.error("library scan error", extra=log_extra(path=str(path), error=str(exc)))
                continue
            _forget_bad_file(key)
            gallery.storage_signature = signature
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
                # An existing-only single copy was already counted as skipped in
                # phase 1; do not double-count it here.
                continue
            resolved = resolve_group(gid, copies, self.duplicate_policy)
            self.last_duplicates.append(resolved)
            if resolved.winner is not None and resolved.winner.meta is not None:
                winners.append(resolved.winner.meta)
                counters.success += 1
            # Losers that were freshly scanned are counted as skipped here;
            # existing losers were already counted in phase 1.
            counters.skipped += sum(1 for copy in resolved.losers if copy.meta is not None)
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
