from __future__ import annotations

from galleryvault.services.duplicates import (
    _core_effective_length,
    artist_from_title,
    calculate_duplicate_score,
    duplicate_group_is_ignored,
    extract_duplicate_artist_and_core,
    find_duplicate_groups,
    find_gallery_duplicate_groups,
    normalize_title,
)


def _make_item(
    gid: int,
    title: str,
    gallery_id: int | None = None,
    favcat: int = 1,
    token: str = "tok",
    url: str = "",
    file_size: int = 1000,
) -> tuple[int, int, str, str, str, int | None, int | None, object, object]:
    return (favcat, gid, token, title, url, gallery_id, file_size, None, None)


def test_a1_noise_brackets_collapse():
    """A1: [Alice] LongTitle [DL版] 与 [Alice] LongTitle [無修正] 仍一组，key=='alice|longtitle'."""
    items = [
        _make_item(101, "[Alice] LongTitle [DL版]"),
        _make_item(102, "[Alice] LongTitle [無修正]"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "alice|longtitle"
    assert groups[0]["artist"] == "alice"
    assert {it["gid"] for it in groups[0]["items"]} == {101, 102}


def test_a2_event_prefix_stripped():
    """A2: (C100) [Alice] LongTitle 与 [Alice] LongTitle 一组（旧算法不组）."""
    items = [
        _make_item(101, "(C100) [Alice] LongTitle"),
        _make_item(102, "[Alice] LongTitle"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "alice|longtitle"
    assert {it["gid"] for it in groups[0]["items"]} == {101, 102}


def test_a3_noise_parenthesis_stripped():
    """A3: LongTitle (無修正) 与 LongTitle 一组."""
    items = [
        _make_item(101, "GreatTitle (無修正)"),
        _make_item(102, "GreatTitle"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "|greattitle"
    assert groups[0]["artist"] is None
    assert {it["gid"] for it in groups[0]["items"]} == {101, 102}


def test_a4_vol_suffix_not_stripped():
    """A4: [Alice] LongTitle vol.1 与 [Alice] LongTitle vol.2 不组."""
    items = [
        _make_item(101, "[Alice] LongTitle vol.1"),
        _make_item(102, "[Alice] LongTitle vol.2"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0


def test_a5_chapter_suffix_not_stripped():
    """A5: [Alice] LongTitle 前編 与 [Alice] LongTitle 後編 不组."""
    items = [
        _make_item(101, "[Alice] LongTitle 前編"),
        _make_item(102, "[Alice] LongTitle 後編"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0


def test_a6_different_artists_do_not_group():
    """A6: [Alice] SameTitle 与 [Bob] SameTitle 不组."""
    items = [
        _make_item(101, "[Alice] SameTitle"),
        _make_item(102, "[Bob] SameTitle"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0


def test_a7_single_artist_and_empty_artist_group():
    """A7: [Alice] SameTitle 与无作者 SameTitle 一组."""
    items = [
        _make_item(101, "[Alice] SameTitle"),
        _make_item(102, "SameTitle"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "alice|sametitle"
    assert groups[0]["artist"] == "alice"
    assert {it["gid"] for it in groups[0]["items"]} == {101, 102}


def test_a8_two_artists_and_empty_do_not_bridge():
    """A8: Alice + Bob + 无作者 同 core → 至多 Alice 组、Bob 组、空作者组，无三方合并."""
    # 每方各1本：由于每方不同 gid < 2，且空作者不桥接异作者，结果应为 0 组
    items = [
        _make_item(101, "[Alice] SameWork"),
        _make_item(102, "[Bob] SameWork"),
        _make_item(103, "SameWork"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0

    # Alice 有2本，Bob 有2本，空作者有2本
    items_multi = [
        _make_item(101, "[Alice] SameWork"),
        _make_item(102, "[Alice] SameWork [DL版]"),
        _make_item(201, "[Bob] SameWork"),
        _make_item(202, "[Bob] SameWork [DL版]"),
        _make_item(301, "SameWork"),
        _make_item(302, "SameWork [DL版]"),
    ]
    groups_multi = find_duplicate_groups(items_multi, gallery_titles={})
    assert len(groups_multi) == 3
    keys = {g["key"] for g in groups_multi}
    assert keys == {"alice|samework", "bob|samework", "|samework"}


def test_a9_tag_map_artist_matches():
    """A9: tag_map 仅有 artist:alice 的无括号标题可与 [Alice] Title 成组."""
    items = [
        _make_item(101, "[Alice] LongTitleBook", gallery_id=1),
        _make_item(102, "LongTitleBook", gallery_id=2),
    ]
    tag_map = {
        2: [("artist", "alice")],
    }
    groups = find_duplicate_groups(items, gallery_titles={}, tag_map=tag_map)
    assert len(groups) == 1
    assert groups[0]["key"] == "alice|longtitlebook"
    assert {it["gid"] for it in groups[0]["items"]} == {101, 102}


def test_a10_cjk_effective_length():
    """A10: len(normalize_title(title)) 短但 CJK 有效长≥6 的日文短标题可参与."""
    # 3个 CJK 汉字，字符数 3，但有效长 3 * 2 = 6 >= 6
    assert _core_effective_length("初恋本") == 6
    assert _core_effective_length("abc") == 3
    items = [
        _make_item(101, "[Alice] 初恋本"),
        _make_item(102, "[Alice] 初恋本 [DL版]"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "alice|初恋本"


def test_short_ascii_title_skipped():
    """短标题跳过：纯 ASCII 长度 < 6（如 Title 仅 5 字符）跳过."""
    items = [
        _make_item(101, "[Alice] Title [DL版]"),
        _make_item(102, "[Alice] Title [無修正]"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0


def test_a11_legacy_keys_ignore_backward_compatibility():
    """A11: 旧忽略 c100|c100title 仍能藏 A2 那种组（via legacy_key）."""
    items = [
        _make_item(101, "(C100) [Alice] MyTestTitle"),
        _make_item(102, "[Alice] MyTestTitle"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    grp = groups[0]
    old_raw_legacy_key = f"{artist_from_title('(C100) [Alice] MyTestTitle') or ''}|{normalize_title('(C100) [Alice] MyTestTitle')}"
    assert old_raw_legacy_key in grp.get("legacy_keys", [])

    ignored_keys = {old_raw_legacy_key}
    assert duplicate_group_is_ignored(grp, ignored_keys) is True


def test_a12_ignore_group_by_key_and_gid_subset():
    """A12: 新忽略仍 POST key/title/gids，支持 key 忽略与 gid 子集忽略."""
    group = {
        "key": "alice|mytitle",
        "artist": "alice",
        "items": [{"gid": 101}, {"gid": 102}],
        "legacy_keys": ["alice|oldtitle"],
    }
    # 1. key 匹配
    assert duplicate_group_is_ignored(group, {"alice|mytitle"}) is True
    # 2. legacy_keys 匹配
    assert duplicate_group_is_ignored(group, {"alice|oldtitle"}) is True
    # 3. gid 子集匹配
    assert duplicate_group_is_ignored(group, set(), [{101, 102, 103}]) is True
    # 4. 空 gids 的 ignore 行不误杀
    assert duplicate_group_is_ignored(group, set(), [set()]) is False
    # 5. 未忽略
    assert duplicate_group_is_ignored(group, {"other|key"}, [{201, 202}]) is False


def test_a13_calculate_duplicate_score_values():
    """A13: calculate_duplicate_score 65/55/35/30."""
    # 同作者 + exact core: 30 + 35 = 65, can_edge = True
    a = {"artists": {"alice"}, "core": "longtitle", "core_len": 9}
    b = {"artists": {"alice"}, "core": "longtitle", "core_len": 9}
    score, can_edge = calculate_duplicate_score(a, b)
    assert score == 65
    assert can_edge is True

    # 一方无作者 + exact core: 20 + 35 = 55, can_edge = True
    c = {"artists": set(), "core": "longtitle", "core_len": 9}
    score, can_edge = calculate_duplicate_score(a, c)
    assert score == 55
    assert can_edge is True

    # 异作者 + exact core: 0 + 35 = 35, can_edge = False
    d = {"artists": {"bob"}, "core": "longtitle", "core_len": 9}
    score, can_edge = calculate_duplicate_score(a, d)
    assert score == 35
    assert can_edge is False

    # 同作者 + 不同 core: 30 + 0 = 30, can_edge = False
    e = {"artists": {"alice"}, "core": "othertitle", "core_len": 10}
    score, can_edge = calculate_duplicate_score(a, e)
    assert score == 30
    assert can_edge is False


def test_normalize_title_behavior_unchanged():
    """normalize_title 行为不变: 去括号内容、去标点、留英数CJK."""
    assert normalize_title("[DL版] Sample 123!") == "sample123"
    assert normalize_title("Title [DL版]") == "title"


def test_legacy_key_formula_unchanged():
    """legacy_key 仍旧公式: artist_from_title | normalize_title."""
    raw = "[Alice] MyBook [DL版]"
    assert f"{artist_from_title(raw) or ''}|{normalize_title(raw)}" == "alice|mybook"


def test_a16_strip_gid_prefix_groups():
    """A16: {3162165}-[へんりいだ]はつこいりぼん。… 与 {3169181}-[へんりいだ]はつこいりぼん。… 一组."""
    raw1 = "3162165-[へんりいだ]はつこいりぼん。[中文翻译][無修loli整理丶重嵌][無修正][DL版][335p]"
    raw2 = "3169181-[へんりいだ]はつこいりぼん。[中文翻译][無修loli整理丶重嵌][無修正][DL版][335p]"
    items = [
        _make_item(3162165, raw1),
        _make_item(3169181, raw2),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "へんりいだ|はつこいりぼん"
    assert groups[0]["artist"] == "へんりいだ"
    assert {it["gid"] for it in groups[0]["items"]} == {3162165, 3169181}


def test_a17_motto_not_grouped():
    """A17: [へんりいだ] もっと！はつこいりぼん。 与 [へんりいだ]はつこいりぼん。 不组."""
    items = [
        _make_item(2926043, "[へんりいだ] もっと！はつこいりぼん。 [無修正] [DL版]"),
        _make_item(3162165, "[へんりいだ]はつこいりぼん。 [無修正] [DL版]"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0


def test_a18_dup_paren_alt_primary_alt_group():
    """A18: [ぽんこっちゃん] 仲良しアプリ (やらしい気分になるアプリ♡ 姉と俺と妹と) 与 [ぽんこっちゃん] やらしい気分になるアプリ♡ 姉と俺と妹と 一组 (primary↔alt)."""
    raw1 = "3057579-[ぽんこっちゃん] 仲良しアプリ (やらしい気分になるアプリ♡ 姉と俺と妹と) [中国翻訳] [無修正] [DL版]"
    raw2 = "[ぽんこっちゃん] やらしい気分になるアプリ♡ 姉と俺と妹と [中国翻訳] [無修正] [DL版]"
    items = [
        _make_item(3057579, raw1),
        _make_item(2785434, raw2),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert "やらしい気分になるアプリ姉と俺と妹と" in groups[0]["key"]
    assert groups[0]["artist"] == "ぽんこっちゃん"
    assert {it["gid"] for it in groups[0]["items"]} == {3057579, 2785434}


def test_a19_alt_alt_forbidden():
    """A19: [Alice] Foo (Touhou Project) 与 [Alice] Bar (Touhou Project) 不组 (禁止 alt↔alt)."""
    # 两个标题的 primary core 分别为 foobook 和 barbook，alt core 均为 touhouproject
    items = [
        _make_item(101, "[Alice] FooBook (Touhou Project)"),
        _make_item(102, "[Alice] BarBook (Touhou Project)"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 0


def test_a20_strip_gid_prefix_dash_behavior():
    """A20: raw=3162165-[へんりいだ]はつこいりぼん。 且 gid=3162165 → 解析作者 へんりいだ 不是 3162165; gid=None 时允许 dash 把数字当作者."""
    raw = "3162165-[へんりいだ]はつこいりぼん。"
    # 带自身 gid：剥前缀，作者是へんりいだ
    artist_with_gid, core_with_gid, _ = extract_duplicate_artist_and_core(raw, gid=3162165)
    assert artist_with_gid == "へんりいだ"
    assert core_with_gid == "はつこいりぼん"

    # gid=None：不剥前缀，dash 规则将 3162165 当作作者
    artist_no_gid, _, _ = extract_duplicate_artist_and_core(raw, gid=None)
    assert artist_no_gid == "3162165"


def test_opt_lib_xgid_library_galleries_scan():
    """OPT-LIB-XGID: 样本组 A (6230, 6431) 与 样本组 B (5933, 5927) 跨 gid 扫描成组验证."""
    galleries = [
        # 组 A
        {
            "id": 6230,
            "gid": 3162165,
            "title": "3162165-[へんりいだ]はつこいりぼん。[中文翻译][無修loli整理丶重嵌][無修正][DL版][335p]",
            "title_jpn": None,
        },
        {
            "id": 6173,
            "gid": 2926043,
            "title": "2926043-[へんりいだ] もっと！はつこいりぼん。 [無修正] [DL版]",
            "title_jpn": None,
        },
        {
            "id": 6431,
            "gid": 3169181,
            "title": "3169181-[へんりいだ]はつこいりぼん。[中文翻译][無修loli整理丶重嵌][無修正][DL版][335p]",
            "title_jpn": None,
        },
        # 组 B (5927 为双 raw：英文 title + 日文 title_jpn)
        {
            "id": 5933,
            "gid": 3057579,
            "title": "3057579-[ぽんこっちゃん] 仲良しアプリ (やらしい気分になるアプリ♡ 姉と俺と妹と) [中国翻訳] [無修正] [DL版]",
            "title_jpn": None,
        },
        {
            "id": 5927,
            "gid": 2785434,
            "title": "[Poncocchan] Yarashii Kibun ni Naru Appli Ane to Ore to Imouto to [Chinese] [Decensored] [Digital]",
            "title_jpn": "[ぽんこっちゃん] やらしい気分になるアプリ♡ 姉と俺と妹と [中国翻訳] [無修正] [DL版]",
        },
    ]
    tag_map = {
        6230: [("artist", "henreader")],
        6173: [("artist", "henreader")],
        6431: [("artist", "henreader")],
        5933: [("artist", "poncocchan")],
        5927: [("artist", "poncocchan")],
    }
    groups = find_gallery_duplicate_groups(galleries, tag_map=tag_map)

    # 应该成功识别出两组：
    # 组 A: 6230 + 6431 (6173 因 core 不同不成组)
    # 组 B: 5933 + 5927 (5927 依靠双 raw 产出日文 primary core，与 5933 alt_core 匹配)
    assert len(groups) == 2

    group_gids = [{it["gid"] for it in g["items"]} for g in groups]
    assert {3162165, 3169181} in group_gids
    assert {3057579, 2785434} in group_gids
