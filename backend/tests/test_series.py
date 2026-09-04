from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from galleryvault.app.routers.series import (
    SeriesCreateRequest,
    create_series,
    delete_series,
    get_series,
    list_series,
    rebuild_series,
    rename_series,
)
from galleryvault.db.models import Gallery, Series
from galleryvault.db.repositories.series import SeriesRepository
from galleryvault.services.series import (
    compute_match_key,
    compute_series_key,
    determine_group_name,
    rebuild_series_groups,
)


def test_compute_series_key_and_match_key() -> None:
    # 1. Trailing numbers stripped; core and artist extraction
    assert compute_series_key("[Artist] Long Series Title 01", None) == "longseriestitle"
    assert compute_series_key("[Artist] Long Series Title 2", None) == "longseriestitle"
    assert compute_series_key(None, "[Artist] Long Series Title 123") == "longseriestitle"

    # Match key formatting: {artist}::{core}
    key1 = compute_match_key("[Artist] Long Series Title 01", None)
    key2 = compute_match_key("[Artist] Long Series Title 02", None)
    assert key1 == key2
    assert key1 == "artist::longseriestitle"

    # len(core) < 6 should not form a match key
    assert compute_match_key("[Artist] Abc 1", None) is None
    assert compute_match_key("Short 1", None) is None

    # 反例 1: 理想の妹6 与 理想の妹催眠編 → 天凪青磁::理想の妹，成组
    # 前导 (C93) 不是作者；[INS-mode(天凪青磁)] 作者为天凪青磁
    k_imouto1 = compute_match_key("(C93) [INS-mode(天凪青磁)] 理想の妹6", None)
    k_imouto2 = compute_match_key("(C93) [INS-mode(天凪青磁)] 理想の妹催眠編", None)
    assert k_imouto1 == "天凪青磁::理想の妹"
    assert k_imouto2 == "天凪青磁::理想の妹"
    assert k_imouto1 == k_imouto2

    # 反例 2: 落难少女4/5 → ::落难少女，成组 (找不到作者 artist="")
    k_girl4 = compute_match_key("落难少女4", None)
    k_girl5 = compute_match_key("落难少女5", None)
    assert k_girl4 == "::落难少女"
    assert k_girl5 == "::落难少女"
    assert k_girl4 == k_girl5

    # 反例 3: exodus626 那本 → exodus626::落难山村的少女，与落难少女不成组
    k_exodus = compute_match_key("exodus626 - 落难山村的少女", None)
    assert k_exodus == "exodus626::落难山村的少女"
    assert k_exodus != k_girl4

    # 噪声括号整段删：动态压缩版/动态版/无修/無修正/AI Generated/DL版
    k_noise1 = compute_match_key("[Artist] Long Series Title 01 [DL版]", None)
    k_noise2 = compute_match_key("[Artist] Long Series Title 01 (無修正)", None)
    k_noise3 = compute_match_key("[Artist] Long Series Title 01 【无修】", None)
    k_noise4 = compute_match_key("[Artist] Long Series Title 01 [AI Generated]", None)
    k_noise5 = compute_match_key("[Artist] Long Series Title 01 [动态版]", None)
    k_noise6 = compute_match_key("[Artist] Long Series Title 01 [动态压缩版]", None)
    for kn in (k_noise1, k_noise2, k_noise3, k_noise4, k_noise5, k_noise6):
        assert kn == "artist::longseriestitle"

    # 末尾副标题词：前編/後編/中編/完結編/上巻/下巻
    assert compute_match_key("[Circle (Artist)] Epic Story 前編", None) == "artist::epicstory"
    assert compute_match_key("[Circle (Artist)] Epic Story 後編", None) == "artist::epicstory"
    assert compute_match_key("[Circle (Artist)] Epic Story 中編", None) == "artist::epicstory"
    assert compute_match_key("[Circle (Artist)] Epic Story 完結編", None) == "artist::epicstory"
    assert compute_match_key("[Circle (Artist)] Epic Story 上巻", None) == "artist::epicstory"
    assert compute_match_key("[Circle (Artist)] Epic Story 下巻", None) == "artist::epicstory"

    # 不删书名内部其它数字
    assert compute_match_key("落难山村的少女", None) == "::落难山村的少女"
    assert compute_match_key("[Artist] Title 3 with internal 4 number 01", None) == "artist::title3withinternal4number"

    # 内层若是 C\d+ 则跳过再找
    k_c_skip = compute_match_key("[C93] [Circle (Artist)] Long Series Title 01", None)
    assert k_c_skip == "artist::longseriestitle"


def test_determine_group_name() -> None:
    g1 = MagicMock(spec=Gallery, title="[Circle (Artist)] Long Series Title Vol. 1", title_jpn=None)
    g2 = MagicMock(spec=Gallery, title="[Circle (Artist)] Long Series Title 2", title_jpn="Long Series Title")
    # Shortest is "Long Series Title"
    assert determine_group_name([g1, g2]) == "Long Series Title"

    g3 = MagicMock(spec=Gallery, title="[Circle] Work 01", title_jpn=None)
    g4 = MagicMock(spec=Gallery, title="[Circle] Work 02", title_jpn=None)
    assert determine_group_name([g3, g4]) == "[Circle] Work"


class _Rows:
    def __init__(self, rows=None, rowcount=0):
        self.rows = rows or []
        self.rowcount = rowcount

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self):
        self.sql = []
        self.added = []

    def _compile(self, statement) -> str:
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.sql.append(sql)
        return sql

    async def execute(self, statement):
        self._compile(statement)
        return _Rows(rowcount=1)

    async def scalars(self, statement):
        self._compile(statement)
        return _Rows([10, 20])

    async def scalar(self, statement):
        self._compile(statement)

    async def get(self, model, ident):
        if model is Series:
            return Series(id=ident, name="Existing Series", match_key=None, name_manual=False)
        return None

    def add(self, obj):
        obj.id = 1
        self.added.append(obj)

    async def flush(self):
        pass

    async def delete(self, obj):
        pass


@pytest.mark.asyncio
async def test_series_repository_sql_statements() -> None:
    session = _FakeSession()
    repo = SeriesRepository(session)

    # create
    created = await repo.create("New Series")
    assert created.name == "New Series"
    assert created in session.added

    # add_items
    session.sql.clear()
    added = await repo.add_items(1, [10, 20])
    assert added == 2
    # Verify exclusions delete and series_items insert
    assert any("series_exclusions" in s.lower() for s in session.sql)
    assert any("series_items" in s.lower() for s in session.sql)

    # remove_items
    session.sql.clear()
    removed = await repo.remove_items(1, [10])
    assert removed == 1
    assert any("delete from series_items" in s.lower() for s in session.sql)
    assert any("insert into series_exclusions" in s.lower() for s in session.sql)

    # rename
    session.sql.clear()
    renamed = await repo.rename(1, "Updated Name")
    assert renamed is not None
    assert renamed.name == "Updated Name"
    assert renamed.name_manual is True

    # delete_series
    session.sql.clear()
    ok = await repo.delete_series(1)
    assert ok is True

    # get_auto_series
    session.sql.clear()
    await repo.get_auto_series()
    assert any("match_key is not null" in s.lower() for s in session.sql)

    # get_auto_series_gids
    session.sql.clear()
    await repo.get_auto_series_gids([1, 2])
    assert any("series_items" in s.lower() for s in session.sql)

    # get_rebuild_candidate_galleries
    session.sql.clear()
    await repo.get_rebuild_candidate_galleries()
    assert any("series_exclusions" in s.lower() for s in session.sql)

    # clear_auto_series_items
    session.sql.clear()
    await repo.clear_auto_series_items([1, 2])
    assert any("delete from series_items" in s.lower() for s in session.sql)


@pytest.mark.asyncio
async def test_rebuild_series_groups_logic() -> None:
    # Setup candidate galleries (unassigned or auto group members)
    g1 = MagicMock(spec=Gallery, id=1, title="[Artist] Amazing Adventure 1", title_jpn=None, trashed=False)
    g2 = MagicMock(spec=Gallery, id=2, title="[Artist] Amazing Adventure 2", title_jpn=None, trashed=False)
    # g3 alone: len < 2, should not form group
    g3 = MagicMock(spec=Gallery, id=3, title="[SoloArtist] Solitary Work 1", title_jpn=None, trashed=False)

    fake_repo = AsyncMock()
    fake_repo.get_auto_series.return_value = []
    fake_repo.get_auto_series_gids.return_value = {}
    fake_repo.get_rebuild_candidate_galleries.return_value = [g1, g2, g3]

    created_series = Series(id=10, name="[Artist] Amazing Adventure", match_key="artist::amazingadventure", name_manual=False)
    fake_repo.create.return_value = created_series
    fake_repo.add_items.return_value = 2

    class DummyCtx:
        async def __aenter__(self):
            return MagicMock()
        async def __aexit__(self, *args):
            pass

    class DummySession:
        def begin(self):
            return DummyCtx()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    fake_session_factory = MagicMock(return_value=DummySession())

    with patch("galleryvault.services.series.SeriesRepository", return_value=fake_repo):
        res = await rebuild_series_groups(session_factory=fake_session_factory)
        assert res["created"] == 1
        assert res["merged"] == 2
        fake_repo.create.assert_called_once()
        fake_repo.add_items.assert_called_once_with(10, [1, 2], source="auto")


@pytest.mark.asyncio
async def test_rebuild_series_groups_name_manual_and_empty_cleanup() -> None:
    # Existing auto series:
    # s1: name_manual=True, member g1 & g2, old key was "artist::oldkey"
    # s2: name_manual=False, will become empty and should be deleted
    s1 = Series(id=1, name="My Custom Renamed Series", match_key="artist::oldkey", name_manual=True)
    s2 = Series(id=2, name="Old Empty Series", match_key="artist::obsoletekey", name_manual=False)

    # Candidates: g1 and g2 will form "artist::newadventure"
    g1 = MagicMock(spec=Gallery, id=10, title="[Artist] New Adventure 1", title_jpn=None, trashed=False)
    g2 = MagicMock(spec=Gallery, id=11, title="[Artist] New Adventure 2", title_jpn=None, trashed=False)

    fake_repo = AsyncMock()
    fake_repo.get_auto_series.return_value = [s1, s2]
    fake_repo.get_auto_series_gids.return_value = {1: {10, 11}, 2: set()}
    fake_repo.get_rebuild_candidate_galleries.return_value = [g1, g2]

    class DummyCtx:
        async def __aenter__(self):
            return MagicMock()
        async def __aexit__(self, *args):
            pass

    class DummySession:
        def begin(self):
            return DummyCtx()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    fake_session_factory = MagicMock(return_value=DummySession())

    with patch("galleryvault.services.series.SeriesRepository", return_value=fake_repo):
        res = await rebuild_series_groups(session_factory=fake_session_factory)
        # s1 is reused for the group because of membership overlap; its custom name is NOT changed
        assert s1.name == "My Custom Renamed Series"
        assert s1.match_key == "artist::newadventure"
        # s2 is deleted because it became empty and name_manual=False
        fake_repo.delete_series.assert_called_once_with(2)
        # s1 is NOT deleted because name_manual=True
        assert res["created"] == 0
        assert res["merged"] == 2


@pytest.mark.asyncio
async def test_series_router_endpoints(monkeypatch) -> None:
    from galleryvault.app.routers import series as series_mod

    g = MagicMock(spec=Gallery, id=1, gid=100, token="tok", title="Title 1", category="manga", page_count=10)
    s = Series(id=5, name="My Series", match_key=None, name_manual=True, created_at=None)

    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_all(self):
            return [(s, 1, [g])]

        async def get(self, sid):
            return s if sid == 5 else None

        async def get_with_galleries(self, sid):
            return (s, [g]) if sid == 5 else None

        async def create(self, name, match_key=None, name_manual=False):
            return Series(id=6, name=name, match_key=match_key, name_manual=name_manual, created_at=None)

        async def rename(self, sid, name):
            if sid == 5:
                s.name = name
                s.name_manual = True
                return s
            return None

        async def delete_series(self, sid):
            return sid == 5

        async def add_items(self, sid, gids, source="manual"):
            return len(gids)

        async def remove_items(self, sid, gids):
            return len(gids)

    class FakeSession:
        def begin(self):
            class Ctx:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *args):
                    pass
            return Ctx()

    async def fake_get_session():
        yield FakeSession()

    class FakeGalleryRepo:
        def __init__(self, session):
            pass

        async def tags_for_galleries(self, gids):
            return {gid: [("artist", "tanaka")] for gid in gids}

    monkeypatch.setattr(series_mod, "get_session", fake_get_session)
    monkeypatch.setattr(series_mod, "SeriesRepository", FakeRepo)
    monkeypatch.setattr(series_mod, "GalleryRepository", FakeGalleryRepo)
    monkeypatch.setattr(series_mod, "display_title", lambda x: getattr(x, "title", ""))

    # 1. GET /api/series
    res = await list_series()
    assert len(res["items"]) == 1
    assert res["items"][0]["name"] == "My Series"
    assert len(res["items"][0]["galleries"]) == 1

    # 2. GET /api/series/5
    detail = await get_series(5)
    assert detail["id"] == 5
    assert detail["count"] == 1

    # GET 404
    with pytest.raises(HTTPException) as exc:
        await get_series(999)
    assert exc.value.status_code == 404

    # 3. POST /api/series
    c_res = await create_series(SeriesCreateRequest(name="New Manual Series"))
    assert c_res["name"] == "New Manual Series"

    # POST 422 if empty
    with pytest.raises(HTTPException) as exc:
        await create_series(SeriesCreateRequest(name="   "))
    assert exc.value.status_code == 422

    # 4. PATCH /api/series/5
    r_res = await rename_series(5, SeriesCreateRequest(name="Renamed"))
    assert r_res["name"] == "Renamed"
    assert r_res["name_manual"] is True

    # 5. DELETE /api/series/5
    d_res = await delete_series(5)
    assert d_res["deleted"] is True

    # 6. POST /api/series/rebuild
    with patch("galleryvault.app.routers.series.rebuild_series_groups", AsyncMock(return_value={"created": 1, "merged": 0})):
        reb_res = await rebuild_series()
        assert reb_res["rebuilt"] is True
        assert reb_res["created"] == 1


def test_series_acceptance_constraints() -> None:
    from pathlib import Path

    from galleryvault.app.routers.galleries import CATEGORIES

    # 1. CATEGORIES not modified; series does not enter EH CATEGORIES
    assert "series" not in CATEGORIES
    assert "series" not in [c.lower() for c in CATEGORIES]

    # 2. Check frontend index.html has series topbar link and script inclusion (if frontend dir present)
    root = Path(__file__).resolve().parents[2]
    frontend_dir = root / "frontend"
    if frontend_dir.exists():
        index_html = (frontend_dir / "index.html").read_text(encoding="utf-8")
        assert 'href="#/series"' in index_html
        assert 'data-i18n="series"' in index_html
        assert '<script src="/assets/views/series.js"></script>' in index_html

        # 3. Check core.js routes
        core_js = (frontend_dir / "assets" / "core.js").read_text(encoding="utf-8")
        assert 'case "series": renderSeries(); break;' in core_js
        assert 'targetSelector = \'.topbar .links a[href="#/series"]\'' in core_js

        # 4. Check locales
        zh_js = (frontend_dir / "assets" / "locales" / "zh.js").read_text(encoding="utf-8")
        en_js = (frontend_dir / "assets" / "locales" / "en.js").read_text(encoding="utf-8")
        assert 'series: "系列作品"' in zh_js
        assert 'series: "Series"' in en_js
        assert 'seriesTitle:' in zh_js
        assert 'seriesTitle:' in en_js

