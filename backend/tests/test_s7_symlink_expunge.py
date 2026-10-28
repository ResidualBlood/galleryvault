"""S7: rows ingested through a symlink that escapes the library root expire.

05 P2-13 leftover.  A symlinked archive pointing outside the root used to be
ingested as a normal row whose ``storage_path`` is the link but whose
``path_hash`` is the resolved target.  Because the target lives outside every
root, the missing-row logic ignored the row forever: a scan can never list it
as seen and it can never be expunged.  ``find_missing_ids`` now treats such a
row as missing when its literal (unresolved) path is still inside a root.

Untouched on purpose:
- a symlink pointing inside a root behaves exactly as before;
- a row whose root is no longer configured keeps the old (ignored) behaviour;
- an incomplete scan still skips expunge for the whole run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.services import scan_worker
from galleryvault.services.scan_worker import run_scan
from galleryvault.services.tasks import TaskManager


def _path_hash(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


def _row(storage_path: Path, gallery_id: int, *, hashed_as: Path | None = None) -> dict:
    """A candidate mapping shaped like ``fetch_expunge_candidates`` output."""
    return {
        "id": gallery_id,
        "path_hash": _path_hash(hashed_as or storage_path),
        "storage_path": str(storage_path),
    }


def _out_of_root_link(library: Path, outside: Path) -> tuple[Path, Path]:
    """Create ``library/link.cbz`` -> ``outside/escaped.cbz``."""
    library.mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)
    target = outside / "escaped.cbz"
    target.write_bytes(b"page-bytes")
    link = library / "link.cbz"
    link.symlink_to(target)
    return link, target


# ---------------------------------------------------------------------------
# find_missing_ids: the missing/expunge decision itself
# ---------------------------------------------------------------------------


def test_symlink_escape_row_is_reported_missing(tmp_path: Path) -> None:
    library = tmp_path / "library"
    outside = tmp_path / "outside"
    link, target = _out_of_root_link(library, outside)
    rows = [_row(link, 7, hashed_as=target)]

    # The scan skips out-of-root symlinks, so the row can never be "seen".
    assert GalleryRepository.find_missing_ids(rows, [library], set()) == [7]


def test_symlink_escape_row_kept_when_target_scanned_elsewhere(tmp_path: Path) -> None:
    """The resolved target is a real library file: nothing to expunge."""
    library = tmp_path / "library"
    outside = tmp_path / "outside"
    link, target = _out_of_root_link(library, outside)
    rows = [_row(link, 7, hashed_as=target)]

    seen = {_path_hash(target)}
    assert GalleryRepository.find_missing_ids(rows, [library, outside], seen) == []


def test_symlink_inside_root_is_unaffected(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    target = library / "real.cbz"
    target.write_bytes(b"page-bytes")
    link = library / "link.cbz"
    link.symlink_to(target)
    rows = [_row(link, 3, hashed_as=target)]

    # Seen after a scan: kept.
    assert GalleryRepository.find_missing_ids(rows, [library], {_path_hash(target)}) == []
    # Link/file removed and not seen: expunged through the pre-existing branch.
    assert GalleryRepository.find_missing_ids(rows, [library], set()) == [3]


def test_row_under_removed_root_is_not_expunged(tmp_path: Path) -> None:
    old_library = tmp_path / "old-library"
    outside = tmp_path / "outside"
    link, target = _out_of_root_link(old_library, outside)
    rows = [_row(link, 11, hashed_as=target)]

    # ``old-library`` is no longer a configured root: keep the row untouched.
    assert GalleryRepository.find_missing_ids(rows, [tmp_path / "library"], set()) == []


def test_row_outside_every_root_and_spelling_is_not_expunged(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    stray = outside / "x.cbz"
    stray.write_bytes(b"page-bytes")
    library = tmp_path / "library"
    library.mkdir()

    assert GalleryRepository.find_missing_ids([_row(stray, 12)], [library], set()) == []


def test_root_spelled_through_a_symlink_still_matches(tmp_path: Path) -> None:
    real_library = tmp_path / "real-library"
    outside = tmp_path / "outside"
    link, target = _out_of_root_link(real_library, outside)
    root_link = tmp_path / "library"
    root_link.symlink_to(real_library, target_is_directory=True)
    rows = [_row(link, 21, hashed_as=target)]

    assert GalleryRepository.find_missing_ids(rows, [root_link], set()) == [21]


# ---------------------------------------------------------------------------
# run_scan: the escape row really reaches mark_expunged, and only when complete
# ---------------------------------------------------------------------------


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        return self


class _FakeRepo:
    """Minimal repo wiring; the real ``find_missing_ids`` drives the decision."""

    candidates: ClassVar[list[dict]] = []
    mark_calls: ClassVar[list[list[int]]] = []
    find_calls: ClassVar[int] = 0
    find_missing_ids = staticmethod(GalleryRepository.find_missing_ids)

    def __init__(self, session):
        pass

    async def fetch_existing_rows_raw(self, roots):
        return []

    async def fetch_starred_and_custom_tag_metadata(self):
        return set(), set(), set()

    @staticmethod
    def parse_existing_rows(
        raw_rows, roots, *, custom_tag_ids=None, fav_gids=None, local_list_ids=None
    ):
        return {}

    async def fetch_expunge_candidates(self):
        _FakeRepo.find_calls += 1
        return list(_FakeRepo.candidates)

    async def mark_expunged(self, ids):
        _FakeRepo.mark_calls.append(list(ids))
        return len(ids)

    async def sync_duplicates(self, duplicates):
        pass

    async def metadata_map(self, gids):
        return {}


class _FakeIngest:
    def __init__(self, session):
        pass

    async def ingest(self, batch):
        pass


async def _run_scan_with(
    monkeypatch: pytest.MonkeyPatch,
    roots: list[str],
    candidates: list[dict],
    tmp_path: Path,
) -> tuple[_FakeRepo, TaskManager]:
    orig_tm = app_state.task_manager
    orig_session = app_state.session_factory
    orig_settings = app_state.settings
    _FakeRepo.candidates = candidates
    _FakeRepo.mark_calls = []
    _FakeRepo.find_calls = 0
    tm = TaskManager()
    app_state.task_manager = tm
    app_state.session_factory = lambda: _FakeSession()
    app_state.settings = Settings(
        library_roots=roots,
        download_root="",
        cold_storage_root="",
        scan_batch_size=10,
        auto_sync_tags=False,
    )
    monkeypatch.setattr(scan_worker, "GalleryRepository", _FakeRepo)
    monkeypatch.setattr(scan_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(scan_worker, "backfill_image_quality", AsyncMock(return_value=0))
    monkeypatch.setattr(
        "galleryvault.services.series.rebuild_series_groups", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "galleryvault.services.duplicates.scan_library_cross_gid_duplicates",
        AsyncMock(return_value=[]),
    )
    try:
        await run_scan()
    finally:
        app_state.task_manager = orig_tm
        app_state.session_factory = orig_session
        app_state.settings = orig_settings
    return _FakeRepo, tm


async def test_run_scan_expunges_symlink_escape_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    outside = tmp_path / "outside"
    link, target = _out_of_root_link(library, outside)

    repo, tm = await _run_scan_with(
        monkeypatch, [str(library)], [_row(link, 42, hashed_as=target)], tmp_path
    )

    assert repo.find_calls == 1
    assert repo.mark_calls == [[42]]
    assert tm.scan_state["last"]["expunged"] == 1
    assert not tm.scan_state.get("scan_incomplete")


async def test_run_scan_does_not_expunge_when_scan_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    outside = tmp_path / "outside"
    link, target = _out_of_root_link(library, outside)
    unmounted = tmp_path / "not-mounted"

    repo, tm = await _run_scan_with(
        monkeypatch,
        [str(library), str(unmounted)],
        [_row(link, 42, hashed_as=target)],
        tmp_path,
    )

    do_not_expunge = not repo.mark_calls
    assert do_not_expunge, "scan_incomplete must suppress every expunge"
    assert repo.find_calls == 0
    assert tm.scan_state["scan_incomplete"] is True
    assert str(unmounted) in tm.scan_state["incomplete_roots"]
