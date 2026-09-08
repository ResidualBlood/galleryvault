"""Unit tests for the Telegram notification message templates (zh / en)."""

import re

import pytest

from galleryvault.services import messages


@pytest.mark.parametrize(
    "title, pages, lang, expected",
    [
        ("A & B", "3", "zh", "✅ 下载完成 <b>A &amp; B</b>（3 页）"),
        ("A", None, "en", "✅ Download complete: <b>A</b>"),
    ],
)
def test_download_ok(title, pages, lang, expected) -> None:
    assert messages.download_ok(title, pages, lang) == expected


@pytest.mark.parametrize(
    "title, reason, lang, expected",
    [
        ("A", "Timeout", "zh", "❌ 下载失败 <b>A</b>：Timeout"),
        ("A", "Timeout", "en", "❌ Download failed: <b>A</b>: Timeout"),
        ("A", "GalleryGoneError", "zh", "❌ <b>A</b>已删除或不存在（404）"),
        ("A", messages.GONE_DETAIL, "en", "❌ <b>A</b> deleted or not found (404)"),
    ],
)
def test_download_fail(title, reason, lang, expected) -> None:
    assert messages.download_fail(title, reason, lang) == expected


@pytest.mark.parametrize(
    "ok_entries, fail_entries, lang, checks",
    [
        (
            [("A", "3"), ("B", "5")],
            [("C", "Timeout")],
            "zh",
            [
                lambda t: t.startswith("📊 下载汇总：完成 <b>2</b>，失败 <b>1</b>"),
                lambda t: "✅ <b>A</b>（3 页）" in t,
                lambda t: "<b>B</b>（5 页）" in t,
                lambda t: "❌ <b>C</b>：Timeout" in t,
            ],
        ),
        (
            [("A", "3"), ("B", "5")],
            [("C", "Timeout")],
            "en",
            [
                lambda t: t.startswith("📊 Download summary: <b>2</b> completed, <b>1</b> failed"),
                lambda t: "✅ <b>A</b> (3 pages)" in t,
                lambda t: "❌ <b>C</b>: Timeout" in t,
            ],
        ),
        ([("A", "3")], [], "zh", [lambda t: t == "✅ 下载完成 <b>A</b>（3 页）"]),
        ([], [("B", "Timeout")], "zh", [lambda t: t == "❌ 下载失败 <b>B</b>：Timeout"]),
        (
            [("<x>", None), ("a&b", None)],
            [],
            "zh",
            [
                lambda t: "<x>" not in t,
                lambda t: "&lt;x&gt;" in t,
                lambda t: "a&amp;b" in t,
            ],
        ),
    ],
)
def test_download_summary(ok_entries, fail_entries, lang, checks) -> None:
    text = messages.download_summary(ok_entries, fail_entries, lang)
    for check in checks:
        assert check(text)


def test_download_summary_caps_failure_list_to_message_limit() -> None:
    entries = [(f"g{i}", "Err") for i in range(1000)]
    text = messages.download_summary([("ok", "1")], entries, "zh")
    assert "失败未列出" in text
    rendered = re.sub(r"<[^>]+>", "", text)
    assert len(rendered) < messages.MAX_MESSAGE_CHARS


@pytest.mark.parametrize(
    "new_cnt, rm_cnt, dup_cnt, dup_gids, lang, checks",
    [
        (6, 0, 0, [], "zh", [lambda t: t == "🔎 扫库完成：新增 <b>6</b>，移除 <b>0</b>"]),
        (
            6,
            2,
            2,
            [1665763, 2862805],
            "en",
            [
                lambda t: t.startswith("🔎 Library scan complete: <b>6</b> new, <b>2</b> removed"),
                lambda t: "2</b> duplicate-copy group(s) found (gid <code>1665763, 2862805</code>)"
                in t,
            ],
        ),
        (6, 0, 6, list(range(1, 7)), "en", [lambda t: "1, 2, 3, 4, 5" in t and ", …" in t]),
    ],
)
def test_scan_summary(new_cnt, rm_cnt, dup_cnt, dup_gids, lang, checks) -> None:
    text = messages.scan_summary(new_cnt, rm_cnt, dup_cnt, dup_gids, lang)
    for check in checks:
        assert check(text)


@pytest.mark.parametrize(
    "error, lang, expected",
    [
        ("GalleryGoneError", "zh", "❌ 扫库失败：GalleryGoneError"),
        ("GalleryGoneError", "en", "❌ Library scan failed: GalleryGoneError"),
    ],
)
def test_scan_failed(error, lang, expected) -> None:
    assert messages.scan_failed(error, lang) == expected


@pytest.mark.parametrize(
    "cat_id, name, new_cnt, enq_cnt, lang, expected",
    [
        (3, "R18", 2, 0, "zh", "⭐ 收藏夹 R18（#3）：新增 <b>2</b>，入队 <b>0</b>"),
        (
            3,
            "R18",
            2,
            0,
            "en",
            "⭐ Favorites category 3 (R18): <b>2</b> new galleries, <b>0</b> queued",
        ),
        (3, None, 1, 1, "zh", "⭐ 收藏夹 #3：新增 <b>1</b>，入队 <b>1</b>"),
        (3, "", 1, 1, "en", "⭐ Favorites category 3: <b>1</b> new galleries, <b>1</b> queued"),
    ],
)
def test_favorites_summary(cat_id, name, new_cnt, enq_cnt, lang, expected) -> None:
    assert messages.favorites_summary(cat_id, name, new_cnt, enq_cnt, lang) == expected


@pytest.mark.parametrize(
    "call_fn, expected",
    [
        (
            lambda: messages.favorites_check_failed(3, "R18", 3, "zh"),
            "⭐ 收藏夹 R18（#3）：检查失败（3 次）",
        ),
        (
            lambda: messages.favorites_enqueue_failed(3, "R18", 1665763, "en"),
            "⭐ Favorites category 3 (R18): download failed for gid <code>1665763</code>",
        ),
        (lambda: messages.bot_paused("zh"), "⏸ 下载已暂停"),
        (lambda: messages.bot_resumed("zh"), "▶️ 下载已恢复"),
        (lambda: messages.bot_status(False, "zh"), "📋 下载状态：运行中"),
        (lambda: messages.bot_status(True, "en"), "📋 GalleryVault downloads are paused"),
        (lambda: messages.bot_queued(1665763, "en"), "📥 Queued gallery <code>1665763</code>"),
        (
            lambda: messages.bot_queued(1665763, "zh", title="Foo"),
            "📥 已入队 <b>Foo</b>（gid <code>1665763</code>）",
        ),
        (lambda: messages.test_message("zh"), "📡 Telegram 连接测试 OK"),
        (lambda: messages.test_message("en"), "📡 Telegram connection test OK"),
    ],
)
def test_bot_and_favorites_messages(call_fn, expected) -> None:
    assert call_fn() == expected


def test_bot_replies_custom() -> None:
    assert "Bar" in messages.bot_queued_updated(1, 2, "Bar", "en")
    assert "404" in messages.bot_gone("Foo", "zh")


@pytest.mark.parametrize(
    "input_lang, expected",
    [
        ("fr", "zh"),
        ("en", "en"),
    ],
)
def test_normalize_lang(input_lang, expected) -> None:
    assert messages.normalize_lang(input_lang) == expected
