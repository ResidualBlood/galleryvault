"""Unit tests for the Telegram notification message templates (zh / en)."""

from galleryvault.services import messages


def test_download_ok_zh_with_pages() -> None:
    assert messages.download_ok("A & B", "3", "zh") == "✅ 下载完成 <b>A &amp; B</b>（3 页）"


def test_download_ok_en_without_pages() -> None:
    assert messages.download_ok("A", None, "en") == "✅ Download complete: <b>A</b>"


def test_download_fail_zh() -> None:
    assert (
        messages.download_fail("A", "Timeout", "zh")
        == "❌ 下载失败 <b>A</b>：Timeout"
    )


def test_download_fail_en() -> None:
    assert (
        messages.download_fail("A", "Timeout", "en")
        == "❌ Download failed: <b>A</b>: Timeout"
    )


def test_download_fail_gone_human() -> None:
    assert messages.download_fail("A", "GalleryGoneError", "zh") == "❌ <b>A</b>已删除或不存在（404）"
    assert (
        messages.download_fail("A", messages.GONE_DETAIL, "en")
        == "❌ <b>A</b> deleted or not found (404)"
    )


def test_download_summary_zh_mixed() -> None:
    text = messages.download_summary(
        [("A", "3"), ("B", "5")], [("C", "Timeout")], "zh"
    )
    assert text.startswith("📊 下载汇总：完成 <b>2</b>，失败 <b>1</b>")
    assert "✅ <b>A</b>（3 页）" in text
    assert "<b>B</b>（5 页）" in text
    assert "❌ <b>C</b>：Timeout" in text


def test_download_summary_en_mixed() -> None:
    text = messages.download_summary(
        [("A", "3"), ("B", "5")], [("C", "Timeout")], "en"
    )
    assert text.startswith("📊 Download summary: <b>2</b> completed, <b>1</b> failed")
    assert "✅ <b>A</b> (3 pages)" in text
    assert "❌ <b>C</b>: Timeout" in text


def test_download_summary_single_ok_is_plain_single() -> None:
    text = messages.download_summary([("A", "3")], [], "zh")
    assert text == "✅ 下载完成 <b>A</b>（3 页）"


def test_download_summary_single_fail_is_plain_single() -> None:
    text = messages.download_summary([], [("B", "Timeout")], "zh")
    assert text == "❌ 下载失败 <b>B</b>：Timeout"


def test_download_summary_caps_failure_list_to_message_limit() -> None:
    entries = [(f"g{i}", "Err") for i in range(1000)]
    text = messages.download_summary([("ok", "1")], entries, "zh")
    assert "失败未列出" in text
    import re as _re

    rendered = _re.sub(r"<[^>]+>", "", text)
    assert len(rendered) < messages.MAX_MESSAGE_CHARS


def test_download_summary_escapes_html_in_titles() -> None:
    text = messages.download_summary([("<x>", None), ("a&b", None)], [], "zh")
    assert "<x>" not in text
    assert "&lt;x&gt;" in text
    assert "a&amp;b" in text


def test_scan_summary_zh() -> None:
    text = messages.scan_summary(6, 0, 0, [], "zh")
    assert text == "🔎 扫库完成：新增 <b>6</b>，移除 <b>0</b>"


def test_scan_summary_en_with_duplicates_and_cap() -> None:
    text = messages.scan_summary(6, 2, 2, [1665763, 2862805], "en")
    assert text.startswith("🔎 Library scan complete: <b>6</b> new, <b>2</b> removed")
    assert "2</b> duplicate-copy group(s) found (gid <code>1665763, 2862805</code>)" in text
    capped = messages.scan_summary(6, 0, 6, list(range(1, 7)), "en")
    assert "1, 2, 3, 4, 5" in capped and ", …" in capped


def test_scan_failed_zh_and_en() -> None:
    assert messages.scan_failed("GalleryGoneError", "zh") == "❌ 扫库失败：GalleryGoneError"
    assert messages.scan_failed("GalleryGoneError", "en") == "❌ Library scan failed: GalleryGoneError"


def test_favorites_summary_zh_and_en() -> None:
    zh = messages.favorites_summary(3, "R18", 2, 0, "zh")
    assert zh == "⭐ 收藏夹 R18（#3）：新增 <b>2</b>，入队 <b>0</b>"
    en = messages.favorites_summary(3, "R18", 2, 0, "en")
    assert en == "⭐ Favorites category 3 (R18): <b>2</b> new galleries, <b>0</b> queued"


def test_favorites_summary_without_name() -> None:
    assert messages.favorites_summary(3, None, 1, 1, "zh") == "⭐ 收藏夹 #3：新增 <b>1</b>，入队 <b>1</b>"
    assert messages.favorites_summary(3, "", 1, 1, "en") == "⭐ Favorites category 3: <b>1</b> new galleries, <b>1</b> queued"


def test_favorites_check_failed_and_enqueue_failed() -> None:
    assert (
        messages.favorites_check_failed(3, "R18", 3, "zh")
        == "⭐ 收藏夹 R18（#3）：检查失败（3 次）"
    )
    assert (
        messages.favorites_enqueue_failed(3, "R18", 1665763, "en")
        == "⭐ Favorites category 3 (R18): download failed for gid <code>1665763</code>"
    )


def test_bot_replies_zh_and_en() -> None:
    assert messages.bot_paused("zh") == "⏸ 下载已暂停"
    assert messages.bot_resumed("zh") == "▶️ 下载已恢复"
    assert messages.bot_status(False, "zh") == "📋 下载状态：运行中"
    assert messages.bot_status(True, "en") == "📋 GalleryVault downloads are paused"
    assert messages.bot_queued(1665763, "en") == "📥 Queued gallery <code>1665763</code>"
    assert (
        messages.bot_queued(1665763, "zh", title="Foo")
        == "📥 已入队 <b>Foo</b>（gid <code>1665763</code>）"
    )
    assert "Bar" in messages.bot_queued_updated(1, 2, "Bar", "en")
    assert "404" in messages.bot_gone("Foo", "zh")


def test_test_message_zh_and_en() -> None:
    assert messages.test_message("zh") == "📡 Telegram 连接测试 OK"
    assert messages.test_message("en") == "📡 Telegram connection test OK"


def test_normalize_lang_falls_back_to_zh() -> None:
    assert messages.normalize_lang("fr") == "zh"
    assert messages.normalize_lang("en") == "en"
