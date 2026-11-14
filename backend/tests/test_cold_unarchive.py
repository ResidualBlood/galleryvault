"""T4.3: cold → hot restore (``unarchive_one``).

DB-free tests around the move semantics finalised in Q8: a cold pack is
extracted to ``download_root/<gid>-<title>`` with canonical ``0001.ext`` page
names, the pointer is switched in one short transaction, and only then is the
cold pack deleted. Any failure must leave the cold pack and the DB row intact
and leave no ``.partial`` behind.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.db.models import Gallery


class _FakeSession:
    def __init__(self, gallery_obj, *, active_download=None, page_rows=()):
        self.gallery_obj = gallery_obj
        self.active_download = active_download
        self.page_rows = list(page_rows)
        self.added: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, ident):
        if model is Gallery and ident == self.gallery_obj.id:
            return self.gallery_obj
        return None

    async def scalar(self, stmt):
        text = str(stmt).lower()
        if self.active_download is not None and "download_tasks" in text:
            return self.active_download
        return None

    async def execute(self, stmt):
        class Res:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        if "gallery_pages" in str(stmt).lower():
            return Res(self.page_rows)
        return Res([])

    def add_all(self, items):
        self.added.extend(items)

    async def commit(self):
        pass


def _factory(gallery_obj, **kwargs):
    return lambda: _FakeSession(gallery_obj, **kwargs)


def _gallery(path: Path, *, gallery_id: int = 10, gid: int = 337, tier: str = "hot"):
    return SimpleNamespace(
        id=gallery_id,
        gid=gid,
        token=f"tok{gid}",
        title="Restore Me",
        storage_path=str(path),
        storage_type="folder",
        storage_size=10,
        file_size=10,
        trashed=False,
        path_hash="oldhash",
        page_count=2,
        cover_path="01.jpg",
        storage_tier=tier,
        cold_at=None,
        source_meta=None,
    )


def _hot_source(tmp_path: Path) -> Path:
    source = tmp_path / "downloads" / "337-Restore Me"
    source.mkdir(parents=True)
    (source / "01.jpg").write_bytes(b"page-one")
    (source / "02.png").write_bytes(b"page-two")
    return source


async def _archive(gallery_obj, cold_root: Path):
    from galleryvault.services.cold_archive import archive_one

    return await archive_one(
        gallery_obj.id,
        cold_root=cold_root,
        delete_source=True,
        session_factory=_factory(gallery_obj),
    )


@pytest.mark.asyncio
async def test_unarchive_roundtrip(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import unarchive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "downloads"
    source = _hot_source(tmp_path)
    gallery_obj = _gallery(source)

    dest = await _archive(gallery_obj, cold_root)
    assert dest is not None and dest.is_file()
    assert gallery_obj.storage_tier == "cold"
    assert not source.exists()

    restored = await unarchive_one(
        gallery_obj.id,
        download_root=download_root,
        cold_root=cold_root,
        session_factory=_factory(gallery_obj),
    )

    assert restored == download_root / "337-Restore Me"
    assert restored.is_dir()
    assert sorted(p.name for p in restored.iterdir() if p.suffix in {".jpg", ".png"}) == [
        "0001.jpg",
        "0002.png",
    ]
    assert gallery_obj.storage_path == str(restored)
    assert gallery_obj.storage_type == "folder"
    assert gallery_obj.page_count == 2
    assert gallery_obj.cover_path == "0001.jpg"
    assert gallery_obj.storage_tier == "hot"
    assert gallery_obj.cold_at is None
    assert not dest.exists()


@pytest.mark.asyncio
async def test_unarchive_restores_p_tokens_from_sidecar(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import unarchive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "downloads"
    source = _hot_source(tmp_path)
    (source / ".ehviewer").write_text(
        "VERSION1\n0\n337\nabcdef1234\n0\n0\n0\n2\n0 ptok1\n1 ptok2\n"
    )
    gallery_obj = _gallery(source)
    gallery_obj.source_meta = {"site": "e-hentai"}

    dest = await _archive(gallery_obj, cold_root)
    assert dest is not None

    await unarchive_one(
        gallery_obj.id,
        download_root=download_root,
        cold_root=cold_root,
        session_factory=_factory(gallery_obj),
    )
    assert gallery_obj.source_meta["p_tokens"] == ["ptok1", "ptok2"]


@pytest.mark.asyncio
async def test_unarchive_failure_keeps_cold_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.services import cold_archive

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "downloads"
    source = _hot_source(tmp_path)
    gallery_obj = _gallery(source)

    dest = await _archive(gallery_obj, cold_root)
    assert dest is not None

    def _boom(cold_path: Path, partial_dir: Path) -> list[str]:
        partial_dir.mkdir(parents=True, exist_ok=True)
        (partial_dir / "0001.jpg").write_bytes(b"half")
        raise RuntimeError("extract failed")

    monkeypatch.setattr(cold_archive, "_extract_cold_pack", _boom)

    with pytest.raises(RuntimeError):
        await cold_archive.unarchive_one(
            gallery_obj.id,
            download_root=download_root,
            cold_root=cold_root,
            session_factory=_factory(gallery_obj),
        )

    target = download_root / "337-Restore Me"
    assert dest.exists()
    assert not target.exists()
    assert not target.with_name(target.name + ".partial").exists()
    assert gallery_obj.storage_path == str(dest)
    assert gallery_obj.storage_tier == "cold"


@pytest.mark.asyncio
async def test_unarchive_refuses_when_target_exists(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import unarchive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "downloads"
    download_root.mkdir()
    source = _hot_source(tmp_path)
    gallery_obj = _gallery(source)

    dest = await _archive(gallery_obj, cold_root)
    assert dest is not None

    target = download_root / "337-Restore Me"
    target.mkdir()
    (target / "keep.txt").write_text("occupied")

    result = await unarchive_one(
        gallery_obj.id,
        download_root=download_root,
        cold_root=cold_root,
        session_factory=_factory(gallery_obj),
    )

    assert result is None
    assert dest.exists()
    assert (target / "keep.txt").read_text() == "occupied"
    assert gallery_obj.storage_path == str(dest)
    assert gallery_obj.storage_tier == "cold"


@pytest.mark.asyncio
async def test_unarchive_refuses_active_download(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import unarchive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "downloads"
    source = _hot_source(tmp_path)
    gallery_obj = _gallery(source)

    dest = await _archive(gallery_obj, cold_root)
    assert dest is not None

    result = await unarchive_one(
        gallery_obj.id,
        download_root=download_root,
        cold_root=cold_root,
        session_factory=_factory(gallery_obj, active_download=999),
    )

    assert result is None
    assert dest.exists()
    assert gallery_obj.storage_path == str(dest)
    assert gallery_obj.storage_tier == "cold"
    assert not (download_root / "337-Restore Me").exists()


@pytest.mark.asyncio
async def test_unarchive_skips_hot_gallery(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import unarchive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    source = _hot_source(tmp_path)
    gallery_obj = _gallery(source, tier="hot")

    result = await unarchive_one(
        gallery_obj.id,
        download_root=tmp_path / "downloads",
        cold_root=cold_root,
        session_factory=_factory(gallery_obj),
    )

    assert result is None
    assert source.exists()
    assert gallery_obj.storage_tier == "hot"


@pytest.mark.asyncio
async def test_run_unarchive_cancels_between_galleries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.services import cold_archive
    from galleryvault.services.tasks import TaskManager

    tm = TaskManager()
    calls: list[int] = []

    async def _fake_unarchive_one(gallery_id, **kwargs):
        calls.append(gallery_id)
        if gallery_id == 1:
            tm.request_cancel("unarchive")
        return tmp_path / str(gallery_id)

    monkeypatch.setattr(cold_archive, "unarchive_one", _fake_unarchive_one)

    await cold_archive.run_unarchive(
        [1, 2],
        session_factory=lambda: None,
        task_manager=tm,
    )

    assert calls == [1]
    assert tm.unarchive_state["running"] is False
    assert tm.task_history[0]["task"] == "unarchive"
    assert tm.task_history[0]["status"] == "cancelled"
