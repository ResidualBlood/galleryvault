from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from galleryvault.db.models import Gallery
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.scripts.repair_cold_archives import repair_cold_archives
from galleryvault.services.tag_sync import TagSyncResult, TagSyncService


@pytest.mark.asyncio
async def test_gallery_repository_update_titles() -> None:
    gallery = Gallery(
        id=1,
        title="2849972-[Dirty] Old Title",
        title_jpn=None,
    )

    class FakeSession:
        def __init__(self, target_gallery: Gallery):
            self.target = target_gallery
            self.flushed = False

        async def get(self, model, ident):
            if ident == self.target.id:
                return self.target
            return None

        async def flush(self):
            self.flushed = True

    session = FakeSession(gallery)
    repo = GalleryRepository(session)  # type: ignore[arg-type]

    # 1. Update with clean title and valid title_jpn
    changed = await repo.update_titles(1, "Clean Title", "日文タイトル")
    assert changed is True
    assert gallery.title == "Clean Title"
    assert gallery.title_jpn == "日文タイトル"
    assert session.flushed is True

    # 2. Update with identical values -> changed is False
    session.flushed = False
    changed_again = await repo.update_titles(1, "Clean Title", "日文タイトル")
    assert changed_again is False
    assert session.flushed is False

    # 3. Numeric title_jpn is rejected and does not overwrite valid title_jpn
    changed_num = await repo.update_titles(1, "Clean Title", "2849972")
    assert changed_num is False
    assert gallery.title_jpn == "日文タイトル"

    # 4. Unknown gallery id -> False
    assert await repo.update_titles(999, "Clean Title", "日文") is False


@pytest.mark.asyncio
async def test_tag_sync_apply_plan_updates_titles() -> None:
    gallery = Gallery(
        id=42,
        gid=2849972,
        token="abcdef123456",
        title="2849972-[Contaminated] Gallery",
        title_jpn=None,
    )

    class FakeTagRepo:
        def __init__(self, target_gallery: Gallery):
            self.gallery = target_gallery
            self.replace_tags_called = False
            self.updated_titles: tuple[int, str | None, str | None] | None = None

        async def get_for_tag_sync(self, ident: int):
            return self.gallery

        async def replace_tags(self, g, tags, synced_at, category=None):
            self.replace_tags_called = True
            return len(tags)

        async def update_titles(self, gallery_id: int, title: str | None, title_jpn: str | None):
            self.updated_titles = (gallery_id, title, title_jpn)
            return True

        async def upsert_metadata(self, items):
            pass

    fake_repo = FakeTagRepo(gallery)
    fake_client = MagicMock()

    service = TagSyncService(fake_client, fake_repo)  # type: ignore[arg-type]
    plan = {
        "source": "network",
        "gid": 2849972,
        "token": "abcdef123456",
        "title": "Clean Canonical Title",
        "title_jpn": "純粋な日本語タイトル",
        "category": "Manga",
        "tags": [{"namespace": "artist", "name": "TestArtist"}],
    }

    count = await service.apply_plan(42, plan)
    assert count == 1
    assert fake_repo.replace_tags_called is True
    assert fake_repo.updated_titles == (42, "Clean Canonical Title", "純粋な日本語タイトル")


@pytest.mark.asyncio
async def test_tag_sync_sync_updates_titles_from_cache_and_network() -> None:
    gallery = Gallery(
        id=10,
        gid=12345,
        token="tok10",
        title="12345-Dirty",
        title_jpn=None,
    )

    class FakeSyncRepo:
        def __init__(self, target_gallery: Gallery):
            self.gallery = target_gallery
            self.cached_meta: dict[str, object] | None = None
            self.updated_titles: tuple[int, str | None, str | None] | None = None

        async def get_for_tag_sync(self, ident: int):
            return self.gallery

        async def replace_tags(self, g, tags, synced_at, category=None):
            return len(tags)

        async def update_titles(self, gallery_id: int, title: str | None, title_jpn: str | None):
            self.updated_titles = (gallery_id, title, title_jpn)
            return True

        async def upsert_metadata(self, items):
            pass

        async def metadata_for_gid(self, gid: int):
            return self.cached_meta

    fake_repo = FakeSyncRepo(gallery)

    # 1. Test cache hit path
    fake_repo.cached_meta = {
        "gid": 12345,
        "title": "Cached Title",
        "title_jpn": "キャッシュタイトル",
        "tags": [{"namespace": "female", "name": "maid"}],
        "category": "Doujinshi",
    }

    fake_client = MagicMock()
    fake_client.fetch_gallery_metadata = None
    service = TagSyncService(fake_client, fake_repo)  # type: ignore[arg-type]
    res_cache = await service.sync(10)

    assert isinstance(res_cache, TagSyncResult)
    assert res_cache.source == "cache"
    assert fake_repo.updated_titles == (10, "Cached Title", "キャッシュタイトル")

    # 2. Test network fetch path
    fake_repo.cached_meta = None
    fake_repo.updated_titles = None

    mock_gallery_meta = SimpleNamespace(
        gid=12345,
        title="Network Title",
        title_jpn="ネットワークタイトル",
        category="Artist CG",
        file_size=1000,
        tags=[{"namespace": "male", "name": "sole male"}],
    )
    fake_client.fetch_gallery = AsyncMock(return_value=mock_gallery_meta)

    res_net = await service.sync(10)
    assert res_net.source == "network"
    assert fake_repo.updated_titles == (10, "Network Title", "ネットワークタイトル")


@pytest.mark.asyncio
async def test_repair_cold_archives_dry_run_and_execute(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "12" / "34"
    cbz_dir.mkdir(parents=True)

    # Source file with double GID in filename
    gid = 12345
    dirty_filename = f"{gid}-{gid}-Some Title.cbz"
    dirty_file = cbz_dir / dirty_filename
    dirty_file.write_bytes(b"cbz-archive-bytes")

    gallery = Gallery(
        id=1,
        gid=gid,
        title=f"{gid}-Some Title",
        storage_type="cbz",
        storage_path=str(dirty_file),
    )

    class FakeSession:
        def __init__(self, items: list[Gallery]):
            self.items = items
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, query):
            class _Result:
                def __init__(self, data):
                    self.data = data

                def scalars(self):
                    return self

                def all(self):
                    return self.data

            return _Result(self.items)

        async def commit(self):
            self.committed = True

    def session_factory():
        return FakeSession([gallery])

    # 1. Dry run mode: does NOT modify disk or DB
    summary_dry = await repair_cold_archives(
        session_factory,  # type: ignore[arg-type]
        execute=False,
        cold_root_override=cold_root,
    )
    assert summary_dry["cold_archived"] == 1
    assert summary_dry["double_gid_detected"] == 1
    assert summary_dry["needs_repair"] == 1
    assert summary_dry["repaired"] == 0
    assert dirty_file.exists()

    # 2. Execute mode: renames disk file and updates DB storage_path
    summary_exec = await repair_cold_archives(
        session_factory,  # type: ignore[arg-type]
        execute=True,
        cold_root_override=cold_root,
    )
    assert summary_exec["repaired"] == 1
    assert not dirty_file.exists()
    assert Path(gallery.storage_path).name == f"{gid}-Some Title.cbz"
    assert Path(gallery.storage_path).exists()
