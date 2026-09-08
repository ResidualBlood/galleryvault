from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from galleryvault.db.models import Gallery, GalleryMetadata
from galleryvault.scripts.repair_cold_archives import (
    fallback_cleanse_titles,
    fetch_gdata_batch,
    is_title_contaminated,
    repair_cold_archives,
)
from galleryvault.services.cold_archive import compute_cold_path


def test_is_title_contaminated_and_fallback_cleanse() -> None:
    # 1. Genuine clean title
    assert is_title_contaminated("Clean English Title", "きれいなタイトル", 12345) is False
    assert is_title_contaminated("100% Orange Juice", None, 99999) is False

    # 2. Leading GID prefix matching gallery gid
    assert is_title_contaminated("12345-[Dirty] Title", None, 12345) is True
    assert is_title_contaminated("12345_Dirty Title", None, 12345) is True

    # 3. Generic numeric prefix
    assert is_title_contaminated("2849972-[Dirty] Title", None, None) is True

    # 4. Double GID in title
    assert is_title_contaminated("12345-12345-Some Title", None, 12345) is True

    # 5. Missing title_jpn with Japanese kana in title (scanner fallback pollution)
    assert is_title_contaminated("[雨と棘] 少女熱", None, 12345) is True
    assert is_title_contaminated("[雨と棘] 少女熱", "少女熱", 12345) is False

    # 6. Fallback cleanse: strips gid and populates title_jpn if kana present
    clean_t, clean_j = fallback_cleanse_titles(
        "12345-[雨と棘] 少女熱", None, 12345
    )
    assert clean_t == "[雨と棘] 少女熱"
    assert clean_j == "[雨と棘] 少女熱"

    # 7. Fallback cleanse with existing title_jpn
    clean_t2, clean_j2 = fallback_cleanse_titles(
        "12345-English Romaji Title", "既存の日本語タイトル", 12345
    )
    assert clean_t2 == "English Romaji Title"
    assert clean_j2 == "既存の日本語タイトル"


@pytest.mark.asyncio
async def test_fetch_gdata_batch_concurrency_and_chunking() -> None:
    # Generate 30 pairs -> should split into 2 chunks (25 + 5)
    pairs = [(1000 + i, f"tok_{i}") for i in range(30)]  # gitleaks:allow

    call_count = 0
    concurrency_peak = 0
    current_concurrency = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count, concurrency_peak, current_concurrency
        call_count += 1
        current_concurrency += 1
        concurrency_peak = max(concurrency_peak, current_concurrency)
        await asyncio.sleep(0.01)
        current_concurrency -= 1

        import json

        body = json.loads(request.content.decode("utf-8"))
        gidlist = body.get("gidlist", [])
        gmetadata = []
        for gid, _tok in gidlist:
            gmetadata.append(
                {
                    "gid": gid,
                    "token": f"tok_{gid}",  # gitleaks:allow
                    "title": f"Canonical Title {gid}",
                    "title_jpn": f"日本語タイトル {gid}",
                    "category": "Manga",
                    "filecount": "20",
                    "filesize": 1234567,
                    "tags": ["female:maid", "male:sole male"],
                }
            )
        return httpx.Response(200, json={"gmetadata": gmetadata})

    transport = httpx.MockTransport(mock_handler)
    sem = asyncio.Semaphore(6)

    async with httpx.AsyncClient(transport=transport) as client:
        results = await fetch_gdata_batch(
            pairs,
            base_url="https://api.e-hentai.org",
            client=client,
            semaphore=sem,
        )

    assert len(results) == 30
    assert call_count == 2
    assert concurrency_peak <= 6
    assert results[1000]["title"] == "Canonical Title 1000"
    assert results[1000]["title_jpn"] == "日本語タイトル 1000"
    assert results[1000]["category"] == "Manga"
    assert results[1000]["file_count"] == 20


@pytest.mark.asyncio
async def test_fetch_gdata_batch_handles_errors_gracefully() -> None:
    pairs = [(99999, "tok_err")]  # gitleaks:allow

    async def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await fetch_gdata_batch(
            pairs,
            base_url="https://api.e-hentai.org",
            client=client,
        )

    assert results == {}


class MockSession:
    def __init__(
        self,
        galleries: list[Gallery],
        metadata: list[GalleryMetadata] | None = None,
    ):
        self.galleries = {g.id: g for g in galleries}
        self.metadata = {m.gid: m for m in (metadata or [])}
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, query):
        q_str = str(query).lower()
        if "from gallery_metadata" in q_str:
            data = list(self.metadata.values())
        else:
            data = list(self.galleries.values())

        class _Result:
            def __init__(self, items):
                self.items = items

            def scalars(self):
                return self

            def all(self):
                return self.items

        return _Result(data)

    async def get(self, model, ident):
        if model == GalleryMetadata:
            return self.metadata.get(ident)
        if model == Gallery:
            return self.galleries.get(ident)
        return None

    def add(self, instance):
        if isinstance(instance, GalleryMetadata):
            self.metadata[instance.gid] = instance
        elif isinstance(instance, Gallery):
            self.galleries[instance.id] = instance

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_repair_cleanse_titles_cache_hit(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "12" / "34"
    cbz_dir.mkdir(parents=True)

    gid = 12345
    file_path = cbz_dir / f"{gid}-{gid}-Old Title.cbz"
    file_path.write_bytes(b"content")

    gallery = Gallery(
        id=1,
        gid=gid,
        token="tok_1",  # gitleaks:allow
        title=f"{gid}-[Contaminated] Title",
        title_jpn=None,
        storage_type="cbz",
        storage_path=str(file_path),
    )
    meta = GalleryMetadata(
        gid=gid,
        token="tok_1",  # gitleaks:allow
        title="Pure Romaji Title",
        title_jpn="清純な日本語タイトル",
    )

    session = MockSession([gallery], [meta])

    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        cold_root_override=cold_root,
        fix_titles=True,
    )

    assert summary["titles_cleansed"] == 1
    assert summary["titles_cache_hits"] == 1
    assert gallery.title == "Pure Romaji Title"
    assert gallery.title_jpn == "清純な日本語タイトル"
    assert session.committed is True
    # Verify cold CBZ file was renamed according to cleansed title
    assert not file_path.exists()
    assert Path(gallery.storage_path).name == f"{gid}-Pure Romaji Title.cbz"
    assert Path(gallery.storage_path).exists()


@pytest.mark.asyncio
async def test_repair_cleanse_titles_gdata_hit_and_metadata_write(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "aa" / "bb"
    cbz_dir.mkdir(parents=True)

    gid = 54321
    file_path = cbz_dir / f"{gid}-{gid}-Dirty.cbz"
    file_path.write_bytes(b"content")

    gallery = Gallery(
        id=2,
        gid=gid,
        token="tok_gdata",  # gitleaks:allow
        title=f"{gid}-[Dirty Kana] 少女熱",
        title_jpn=None,
        storage_type="cbz",
        storage_path=str(file_path),
    )

    session = MockSession([gallery], [])

    async def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "gmetadata": [
                    {
                        "gid": gid,
                        "token": "tok_gdata",  # gitleaks:allow
                        "title": "Ame to Toge - Shoujo Netsu",
                        "title_jpn": "雨と棘 少女熱",
                        "category": "Doujinshi",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        summary = await repair_cold_archives(
            lambda: session,
            execute=True,
            cold_root_override=cold_root,
            fix_titles=True,
            http_client=http_client,
        )

    assert summary["titles_cleansed"] == 1
    assert summary["titles_gdata_hits"] == 1
    assert gallery.title == "Ame to Toge - Shoujo Netsu"
    assert gallery.title_jpn == "雨と棘 少女熱"
    assert session.committed is True

    # Check that gallery_metadata was inserted
    cached_meta = session.metadata.get(gid)
    assert cached_meta is not None
    assert cached_meta.title == "Ame to Toge - Shoujo Netsu"
    assert cached_meta.title_jpn == "雨と棘 少女熱"
    assert cached_meta.category == "Doujinshi"

    # Cold CBZ was renamed cleanly
    assert not file_path.exists()
    assert Path(gallery.storage_path).name == f"{gid}-Ame to Toge - Shoujo Netsu.cbz"
    assert Path(gallery.storage_path).exists()


@pytest.mark.asyncio
async def test_repair_cleanse_titles_fallback(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "cc" / "dd"
    cbz_dir.mkdir(parents=True)

    gid = 88888
    file_path = cbz_dir / f"{gid}-{gid}-Title.cbz"
    file_path.write_bytes(b"content")

    gallery = Gallery(
        id=3,
        gid=gid,
        token=None,  # No token -> fallback immediately
        title=f"{gid}-[Author] ふたりのわるだくみ",
        title_jpn=None,
        storage_type="cbz",
        storage_path=str(file_path),
    )

    session = MockSession([gallery], [])

    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        cold_root_override=cold_root,
        fix_titles=True,
    )

    assert summary["titles_cleansed"] == 1
    assert summary["titles_fallback"] == 1
    assert gallery.title == "[Author] ふたりのわるだくみ"
    assert gallery.title_jpn == "[Author] ふたりのわるだくみ"
    assert not file_path.exists()
    assert Path(gallery.storage_path).name == f"{gid}-[Author] ふたりのわるだくみ.cbz"


@pytest.mark.asyncio
async def test_repair_cold_cbz_conflict_and_missing_source(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "11" / "22"
    cbz_dir.mkdir(parents=True)

    gid = 11223
    # 1. Missing source test
    missing_file = cbz_dir / f"{gid}-{gid}-Missing.cbz"
    gallery_missing = Gallery(
        id=1,
        gid=gid,
        title="Valid Title",
        storage_type="cbz",
        storage_path=str(missing_file),
    )

    # 2. Conflict test: target already exists
    conflict_source = cbz_dir / f"{gid}-{gid}-Conflict.cbz"
    conflict_source.write_bytes(b"source-bytes")
    # Target that compute_cold_path will point to
    conflict_target = compute_cold_path(cold_root, is_cbz=True, gid=gid, title="Conflict")
    conflict_target.parent.mkdir(parents=True, exist_ok=True)
    conflict_target.write_bytes(b"target-already-exists")

    gallery_conflict = Gallery(
        id=2,
        gid=gid,
        title="Conflict",
        storage_type="cbz",
        storage_path=str(conflict_source),
    )

    session = MockSession([gallery_missing, gallery_conflict], [])

    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        cold_root_override=cold_root,
        fix_titles=False,
    )

    assert summary["skipped_missing_source"] == 1
    assert summary["skipped_conflict"] == 1
    assert summary["repaired"] == 0
    # Conflict source must remain untouched
    assert conflict_source.exists()
    assert conflict_target.read_bytes() == b"target-already-exists"


@pytest.mark.asyncio
async def test_repair_local_directories_dry_run_and_execute(tmp_path: Path) -> None:
    downloads_root = tmp_path / "downloads"
    downloads_root.mkdir()

    gid = 77777
    dirty_dir_name = f"{gid}-{gid}-[Artist] Some Japanese Book"
    dirty_dir = downloads_root / dirty_dir_name
    dirty_dir.mkdir()
    (dirty_dir / "001.jpg").write_bytes(b"image")

    gallery = Gallery(
        id=10,
        gid=gid,
        title=f"{gid}-[Artist] Some Japanese Book",
        title_jpn="[Artist] Some Japanese Book",
        storage_type="dir",
        storage_path=str(dirty_dir),
    )

    session = MockSession([gallery], [])

    # 1. Dry run: does not modify disk or DB
    summary_dry = await repair_cold_archives(
        lambda: session,
        execute=False,
        fix_local=True,
    )
    assert summary_dry["local_needs_repair"] == 1
    assert summary_dry["local_repaired"] == 0
    assert dirty_dir.exists()

    # 2. Execute mode: renames local directory
    summary_exec = await repair_cold_archives(
        lambda: session,
        execute=True,
        fix_local=True,
    )
    assert summary_exec["local_repaired"] == 1
    assert not dirty_dir.exists()
    new_dir = Path(gallery.storage_path)
    assert new_dir.exists()
    assert new_dir.name == f"{gid}-[Artist] Some Japanese Book"
    assert (new_dir / "001.jpg").exists()
    assert session.committed is True


@pytest.mark.asyncio
async def test_repair_local_directories_conflict_skipped(tmp_path: Path) -> None:
    downloads_root = tmp_path / "downloads"
    downloads_root.mkdir()

    gid = 66666
    dirty_dir = downloads_root / f"{gid}-{gid}-Conflicted"
    dirty_dir.mkdir()

    # Create target directory beforehand to induce conflict
    target_dir = downloads_root / f"{gid}-Conflicted"
    target_dir.mkdir()
    (target_dir / "existing.txt").write_text("existing")

    gallery = Gallery(
        id=20,
        gid=gid,
        title=f"{gid}-Conflicted",
        title_jpn="Conflicted",
        storage_type="dir",
        storage_path=str(dirty_dir),
    )

    session = MockSession([gallery], [])

    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        fix_local=True,
    )

    assert summary["local_skipped_conflict"] == 1
    assert summary["local_repaired"] == 0
    assert dirty_dir.exists()
    assert (target_dir / "existing.txt").read_text() == "existing"
