import hashlib
from datetime import UTC, datetime

from galleryvault.scanners.base import ExistingGallery
from galleryvault.scanners.ehviewer import EhviewerDirScanner
from galleryvault.services.duplicate_resolver import Copy, resolve_group
from galleryvault.services.library import LibraryService


def _copy(path: str, gid: int, pages: int | None = None, size: int | None = None,
          posted: datetime | None = None, current: bool = False, priority: int = 0) -> Copy:
    return Copy(
        path=__import__("pathlib").Path(path),
        gid=gid,
        storage_type="ehviewer_dir",
        title=path,
        page_count=pages,
        file_size=size,
        posted_at=posted,
        root_priority=priority,
        is_current=current,
    )


def test_resolve_keep_first_prefers_existing_then_root_order() -> None:
    a = _copy("/a/100-x", 100, pages=2, current=True)
    b = _copy("/b/100-y", 100, pages=5)
    group = resolve_group(100, [a, b], "keep_first")
    assert group.winner is a and group.losers == [b]

    # No existing row: lowest root priority wins.
    c = _copy("/c/100-z", 100, pages=9, priority=2)
    group = resolve_group(100, [b, c], "keep_first")
    assert group.winner is b and group.losers == [c]


def test_resolve_prefer_more_pages() -> None:
    a = _copy("/a/100-x", 100, pages=3)
    b = _copy("/b/100-y", 100, pages=8)
    group = resolve_group(100, [a, b], "prefer_more_pages")
    assert group.winner is b


def test_resolve_prefer_larger_and_smaller() -> None:
    a = _copy("/a/100-x", 100, size=1000)
    b = _copy("/b/100-y", 100, size=9000)
    assert resolve_group(100, [a, b], "prefer_larger").winner is b
    assert resolve_group(100, [a, b], "prefer_smaller").winner is a


def test_resolve_prefer_newer() -> None:
    a = _copy("/a/100-x", 100, posted=datetime(2020, 1, 1, tzinfo=UTC))
    b = _copy("/b/100-y", 100, posted=datetime(2022, 6, 1, tzinfo=UTC))
    unknown = _copy("/c/100-z", 100, posted=None)
    assert resolve_group(100, [a, b], "prefer_newer").winner is b
    # Missing posted date loses against a dated copy.
    assert resolve_group(100, [unknown, a], "prefer_newer").winner is a


def test_resolve_manual_reports_everything() -> None:
    a = _copy("/a/100-x", 100)
    b = _copy("/b/100-y", 100)
    group = resolve_group(100, [a, b], "manual")
    assert group.winner is None
    assert len(group.losers) == 2


def _make_ehviewer(path, gid: int, pages: int = 2, token: str = "tok") -> None:
    path.mkdir()
    (path / ".ehviewer").write_text(
        f"VERSION2\n0\n{gid}\n{token}\n1\n1\n1\n{pages}\n"
        + "".join(f"{i} t{i}\n" for i in range(pages))
    )
    for i in range(pages):
        (path / f"{i + 1:08d}.jpg").write_bytes(b"x")


def test_scan_two_roots_same_gid_keeps_first(tmp_path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    _make_ehviewer(root_a / "100-aa", 100)
    _make_ehviewer(root_b / "100-bb", 100)
    svc = LibraryService([root_a, root_b], duplicate_policy="keep_first")
    galleries, counters = svc.scan()
    assert len(galleries) == 1
    assert "aa" in str(galleries[0].path)
    assert counters.success == 1
    assert len(svc.last_duplicates) == 1
    group = svc.last_duplicates[0]
    assert group.gid == 100
    assert group.winner is not None and "aa" in str(group.winner.path)
    assert len(group.losers) == 1 and "bb" in str(group.losers[0].path)


def test_scan_duplicate_winner_has_more_pages(tmp_path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _make_ehviewer(root / "100-small", 100, pages=2)
    _make_ehviewer(root / "100-big", 100, pages=7)
    svc = LibraryService([root], duplicate_policy="prefer_more_pages")
    galleries, _ = svc.scan()
    assert len(galleries) == 1
    assert "big" in str(galleries[0].path)
    assert galleries[0].file_count == 7


def test_scan_folds_existing_row_into_duplicate_group(tmp_path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    existing_path = root / "100-existing"
    _make_ehviewer(existing_path, 100, pages=2)
    new_path = root / "100-new"
    _make_ehviewer(new_path, 100, pages=5)
    scanner = EhviewerDirScanner()
    existing = {
        hashlib.sha256(str(existing_path.resolve()).encode()).hexdigest(): ExistingGallery(
            path=str(existing_path),
            signature=scanner.fingerprint(existing_path),
            gid=100,
            gallery_id=7,
            storage_type="ehviewer_dir",
            title="existing",
            file_count=2,
            file_size=2,
            posted_at=None,
        )
    }
    svc = LibraryService(
        [root],
        existing=existing,
        duplicate_policy="prefer_more_pages",
    )
    galleries, _ = svc.scan()
    # The new (larger) copy wins and repoints the DB row.
    assert len(galleries) == 1
    assert "new" in str(galleries[0].path)
    assert len(svc.last_duplicates) == 1
    assert svc.last_duplicates[0].winner is not None
    assert svc.last_duplicates[0].winner.is_current is False
    assert len(svc.last_duplicates[0].losers) == 1
    assert svc.last_duplicates[0].losers[0].is_current is True


def test_scan_manual_policy_ingests_nothing(tmp_path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _make_ehviewer(root / "100-x", 100)
    _make_ehviewer(root / "100-y", 100)
    svc = LibraryService([root], duplicate_policy="manual")
    galleries, _ = svc.scan()
    assert galleries == []
    assert len(svc.last_duplicates) == 1
    assert svc.last_duplicates[0].winner is None


def test_scan_summary_message_mentions_duplicates() -> None:
    from galleryvault.app.main import _scan_summary_message

    base = {"persisted": 6, "expunged": 0}
    plain = _scan_summary_message(base, 0, [])
    assert plain == "Library scan complete: 6 new, 0 removed"
    with_dup = _scan_summary_message(base, 2, [1665763, 2862805])
    assert "2 duplicate-copy group(s) found" in with_dup
    assert "1665763" in with_dup and "2862805" in with_dup
    capped = _scan_summary_message(base, 6, list(range(1, 7)))
    assert "…" in capped and "1, 2, 3, 4, 5" in capped
