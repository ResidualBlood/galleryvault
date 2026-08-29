"""Library duplicate-copy resolution.

The same ExHentai gallery (same ``gid``) can exist as several physical copies
under different scan roots (an EhViewer download directory, a CBZ archive, a
second copy the user dropped in).  The library scan collects every copy it can
see — freshly scanned paths plus rows already in the DB — and this module picks
a winner per ``duplicate_policy`` and reports the losers, so the UI can offer
manual cleanup.

Only copies that carry a ``gid`` participate in resolution; gid-less copies
(e.g. a CBZ whose ExHentai id lives in an external sidecar file) are ingested
as separate path-keyed rows and bypass duplicate detection entirely.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..scanners.base import GalleryMeta

DUPLICATE_POLICIES = (
    "keep_first",
    "prefer_more_pages",
    "prefer_newer",
    "prefer_larger",
    "prefer_smaller",
    "manual",
)

DEFAULT_DUPLICATE_POLICY = "keep_first"

# ``posted_at`` is stored with a timezone; comparing against a naive ``min``
# would raise.  Use this sentinel instead of ``datetime.min``.
_NEVER = datetime.min.replace(tzinfo=UTC)


def duplicate_key(path: Path) -> str:
    """Stable copy key (sha256 of the resolved path), shared with path_hash."""
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


@dataclass
class Copy:
    """One physical copy of a gallery in a duplicate group."""

    path: Path
    gid: int
    gallery_id: int | None = None  # DB row id when this copy is already ingested
    storage_type: str = ""
    title: str = ""
    title_jpn: str = ""
    page_count: int | None = None
    file_size: int | None = None
    posted_at: datetime | None = None
    signature: str = ""
    root_priority: int = 0  # 0 = highest-priority scan root
    is_current: bool = False  # True when this copy is the DB row
    tags: list[dict[str, str]] = field(default_factory=list)
    meta: GalleryMeta | None = None  # present for freshly scanned copies

    @classmethod
    def from_meta(cls, gallery: GalleryMeta, root_priority: int) -> Copy:
        return cls(
            path=gallery.path,
            gid=gallery.gid or 0,
            storage_type=gallery.storage_type,
            title=gallery.title,
            title_jpn=gallery.title_jpn or "",
            page_count=gallery.file_count,
            file_size=gallery.file_size,
            posted_at=gallery.posted_at,
            signature=gallery.storage_signature,
            root_priority=root_priority,
            is_current=False,
            meta=gallery,
        )

    @classmethod
    def from_existing(cls, row, root_priority: int) -> Copy:
        return cls(
            path=Path(row.path),
            gid=row.gid,
            gallery_id=row.gallery_id,
            storage_type=row.storage_type,
            title=row.title,
            title_jpn=getattr(row, "title_jpn", None) or "",
            page_count=row.file_count,
            file_size=row.file_size,
            posted_at=row.posted_at,
            signature=row.signature,
            root_priority=root_priority,
            is_current=True,
        )

    def as_record(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "key": duplicate_key(self.path),
            "gallery_id": self.gallery_id,
            "storage_type": self.storage_type,
            "title": self.title,
            "title_jpn": self.title_jpn,
            "page_count": self.page_count,
            "file_size": self.file_size,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "is_current": self.is_current,
            "tags": self.tags,
        }


@dataclass
class ResolvedGroup:
    """Outcome of resolving one duplicate group (copies of one gid)."""

    gid: int
    policy: str
    winner: Copy | None  # None under the "manual" policy
    losers: list[Copy]

    def record(self) -> dict[str, object]:
        return {
            "gid": self.gid,
            "policy": self.policy,
            "winner_path": str(self.winner.path) if self.winner else None,
            "copies": [copy.as_record() for copy in self.all_copies()],
        }

    def all_copies(self) -> list[Copy]:
        copies = list(self.losers)
        if self.winner is not None:
            copies.insert(0, self.winner)
        return copies


def _tie_rank(copy: Copy) -> tuple[object, ...]:
    """Deterministic fallback: prefer the current row, then root order, then path."""
    return (0 if copy.is_current else 1, copy.root_priority, str(copy.path))


def _better(a: Copy, b: Copy, policy: str) -> bool:
    """True if ``a`` beats ``b`` on the policy's primary metric."""
    if policy == "prefer_more_pages":
        return (a.page_count or 0) > (b.page_count or 0)
    if policy == "prefer_newer":
        return (a.posted_at or _NEVER) > (b.posted_at or _NEVER)
    if policy == "prefer_larger":
        return (a.file_size or 0) > (b.file_size or 0)
    if policy == "prefer_smaller":
        return (a.file_size or 0) < (b.file_size or 0)
    return False


def _resolve_winner(copies: list[Copy], policy: str) -> Copy:
    if policy == "keep_first":
        return min(copies, key=_tie_rank)
    best = copies[0]
    for candidate in copies[1:]:
        if _better(candidate, best, policy):
            best = candidate
        elif not _better(best, candidate, policy) and _tie_rank(candidate) < _tie_rank(best):
            # Tied on the primary metric: fall back to the deterministic rank.
            best = candidate
    return best


def resolve_group(gid: int, copies: list[Copy], policy: str) -> ResolvedGroup:
    """Pick a winner among ``copies`` of ``gid`` according to ``policy``.

    Under "manual" nothing is resolved automatically: all copies are reported
    as losers and the UI decides.  Every other policy keeps the winner (whose
    metadata is ingested by the caller) and reports the rest.
    """
    if not copies:
        return ResolvedGroup(gid, policy, None, [])
    if policy not in DUPLICATE_POLICIES:
        policy = DEFAULT_DUPLICATE_POLICY
    if policy == "manual":
        return ResolvedGroup(gid, policy, winner=None, losers=list(copies))
    winner = _resolve_winner(copies, policy)
    losers = [copy for copy in copies if copy is not winner]
    return ResolvedGroup(gid, policy, winner=winner, losers=losers)
