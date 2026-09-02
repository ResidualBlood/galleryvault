"""Telegram notification message templates (zh / en).

All Telegram notification copy lives here so the backend has exactly one place
that decides both the *language* (driven by the ``telegram_notify_lang``
setting) and the *format* (Telegram HTML: bold titles, ``<code>`` gids, and a
consistent emoji prefix per event type).

Every user-supplied value (titles, gids, errors, category names) is HTML
escaped before being interpolated, because ``send_message`` uses
``parse_mode="HTML"`` and an unescaped ``<`` / ``&`` would make Telegram reject
the whole message.

Only the outer "shell" text is translated; gallery titles come from ExHentai
and are never translated, only escaped.
"""

from __future__ import annotations

import re

LANGS = ("zh", "en")
GONE_DETAIL = "gallery deleted or not found (404)"
# Single downloads list their title; larger batches only show counts for the
# success side (failures are always listed, capped to the Telegram 4096 limit).
LIST_TITLES_LIMIT = 5
MAX_MESSAGE_CHARS = 4096

_TEMPLATES: dict[str, dict[str, str]] = {
    "zh": {
        "download_ok_verb": "下载完成 ",
        "download_ok_title": "<b>{title}</b>",
        "download_ok_pages": "（{pages} 页）",
        "download_fail_verb": "下载失败 ",
        "download_fail_title": "<b>{title}</b>",
        "download_fail_detail": "：{detail}",
        "download_summary_head": "📊 下载汇总：完成 <b>{ok}</b>，失败 <b>{fail}</b>",
        "list_sep": "、",
        "download_more_failures": "… 还有 {n} 个失败未列出",
        "scan_ok": "🔎 扫库完成：新增 <b>{new}</b>，移除 <b>{removed}</b>",
        "scan_dup": "⚠️ <b>{n}</b> 组重复副本（gid <code>{gids}</code>）",
        "scan_failed": "❌ 扫库失败：{error}",
        "ellipsis": "…",
        "fav_category": "收藏夹 {name}（#{favcat}）",
        "fav_category_noname": "收藏夹 #{favcat}",
        "fav_check_failed": "⭐ {cat}：检查失败（{n} 次）",
        "fav_enqueue_failed": "⭐ {cat}：gid <code>{gid}</code> 入队失败",
        "fav_summary": "⭐ {cat}：新增 <b>{new}</b>，入队 <b>{queued}</b>",
        "bot_paused": "⏸ 下载已暂停",
        "bot_resumed": "▶️ 下载已恢复",
        "bot_status_running": "📋 下载状态：运行中",
        "bot_status_paused": "📋 下载状态：已暂停",
        "bot_queued": "📥 已入队 gid <code>{gid}</code>",
        "bot_queued_title": "📥 已入队 <b>{title}</b>（gid <code>{gid}</code>）",
        "bot_queued_updated": (
            "📥 原 gid <code>{old}</code> 已更新为 gid <code>{new}</code>，"
            "已入队 <b>{title}</b>"
        ),
        "bot_gone": "❌ <b>{title}</b>已删除或不存在（404），未入队",
        "bot_already_local": "✅ 新版已在库中：<b>{title}</b>（gid <code>{gid}</code>）",
        "download_gone": "❌ <b>{title}</b>已删除或不存在（404）",
        "download_updated": (
            "🔄 原 gid <code>{old}</code> → 新版 gid <code>{new}</code>，"
            "改为下载 <b>{title}</b>"
        ),
        "test": "📡 Telegram 连接测试 OK",
    },
    "en": {
        "download_ok_verb": "Download complete: ",
        "download_ok_title": "<b>{title}</b>",
        "download_ok_pages": " ({pages} pages)",
        "download_fail_verb": "Download failed: ",
        "download_fail_title": "<b>{title}</b>",
        "download_fail_detail": ": {detail}",
        "download_summary_head": "📊 Download summary: <b>{ok}</b> completed, <b>{fail}</b> failed",
        "list_sep": ", ",
        "download_more_failures": "… and {n} more failures not listed",
        "scan_ok": "🔎 Library scan complete: <b>{new}</b> new, <b>{removed}</b> removed",
        "scan_dup": "⚠️ <b>{n}</b> duplicate-copy group(s) found (gid <code>{gids}</code>)",
        "scan_failed": "❌ Library scan failed: {error}",
        "ellipsis": ", …",
        "fav_category": "Favorites category {favcat} ({name})",
        "fav_category_noname": "Favorites category {favcat}",
        "fav_check_failed": "⭐ {cat}: check failed after {n} attempts",
        "fav_enqueue_failed": "⭐ {cat}: download failed for gid <code>{gid}</code>",
        "fav_summary": "⭐ {cat}: <b>{new}</b> new galleries, <b>{queued}</b> queued",
        "bot_paused": "⏸ Downloads paused",
        "bot_resumed": "▶️ Downloads resumed",
        "bot_status_running": "📋 GalleryVault downloads are running",
        "bot_status_paused": "📋 GalleryVault downloads are paused",
        "bot_queued": "📥 Queued gallery <code>{gid}</code>",
        "bot_queued_title": "📥 Queued <b>{title}</b> (gid <code>{gid}</code>)",
        "bot_queued_updated": (
            "📥 Original gid <code>{old}</code> updated to gid <code>{new}</code>, "
            "queued <b>{title}</b>"
        ),
        "bot_gone": "❌ <b>{title}</b> deleted or not found (404), not queued",
        "bot_already_local": "✅ Newer version already in library: <b>{title}</b> (gid <code>{gid}</code>)",
        "download_gone": "❌ <b>{title}</b> deleted or not found (404)",
        "download_updated": (
            "🔄 Original gid <code>{old}</code> → new gid <code>{new}</code>, "
            "downloading <b>{title}</b>"
        ),
        "test": "📡 Telegram connection test OK",
    },
}

_TAG_RE = re.compile(r"<[^>]+>")


def normalize_lang(lang: object) -> str:
    return lang if lang in LANGS else "zh"


def esc(value: object) -> str:
    """HTML-escape a value for Telegram ``parse_mode="HTML"`` messages."""
    text = str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _t(lang: str, key: str) -> str:
    return _TEMPLATES[normalize_lang(lang)][key]


def _plain_len(text: str) -> int:
    """Length of the rendered text (Telegram counts this, not HTML markup)."""
    return len(_TAG_RE.sub("", text))


# --- downloads --------------------------------------------------------------

def _entry_ok(title: str, pages: str | None, lang: str) -> str:
    text = _t(lang, "download_ok_title").format(title=esc(title))
    if pages not in (None, ""):
        text += _t(lang, "download_ok_pages").format(pages=esc(pages))
    return text


def _entry_fail(title: str, detail: str | None, lang: str) -> str:
    text = _t(lang, "download_fail_title").format(title=esc(title))
    if detail:
        text += _t(lang, "download_fail_detail").format(detail=esc(detail))
    return text


def download_ok(title: str, pages: str | None = None, lang: str = "zh") -> str:
    """Single successful-download message."""
    return "✅ " + _t(lang, "download_ok_verb") + _entry_ok(title, pages, lang)


def is_gone_detail(detail: str | None) -> bool:
    if not detail:
        return False
    text = detail.lower()
    return (
        "gallerygoneerror" in text
        or "deleted or not found" in text
        or "does not exist on exhentai" in text
    )


def download_fail(title: str, detail: str | None = None, lang: str = "zh") -> str:
    """Single failed-download message."""
    if is_gone_detail(detail):
        return _t(lang, "download_gone").format(title=esc(title))
    return "❌ " + _t(lang, "download_fail_verb") + _entry_fail(title, detail, lang)


def download_updated(
    old_gid: object, new_gid: object, title: str, lang: str = "zh"
) -> str:
    return _t(lang, "download_updated").format(
        old=esc(old_gid), new=esc(new_gid), title=esc(title)
    )


def download_summary(
    ok_entries: list[tuple[str, str | None]],
    fail_entries: list[tuple[str, str | None]],
    lang: str = "zh",
) -> str:
    """Digest of a download batch; collapses into a single message."""
    ok, fail = len(ok_entries), len(fail_entries)
    if ok == 1 and fail == 0:
        return download_ok(*ok_entries[0], lang)
    if ok == 0 and fail == 1:
        return download_fail(*fail_entries[0], lang=lang)
    text = _t(lang, "download_summary_head").format(ok=ok, fail=fail)
    if ok and ok <= LIST_TITLES_LIMIT:
        text += "\n✅ " + _t(lang, "list_sep").join(
            _entry_ok(title, pages, lang) for title, pages in ok_entries
        )
    if fail:
        lines: list[str] = []
        for title, detail in fail_entries:
            if is_gone_detail(detail):
                entry = _t(lang, "download_gone").format(title=esc(title)).removeprefix("❌ ").strip()
            else:
                entry = _entry_fail(title, detail, lang)
            candidate = "\n❌ " + "\n".join(lines + [entry])
            if _plain_len(text) + _plain_len(candidate) > MAX_MESSAGE_CHARS - 100:
                lines.append(
                    _t(lang, "download_more_failures").format(
                        n=len(fail_entries) - len(lines)
                    )
                )
                break
            lines.append(entry)
        text += "\n❌ " + "\n".join(lines)
    return text


# --- library scan -----------------------------------------------------------

def scan_summary(
    persisted: int, expunged: int, duplicates: int, duplicate_gids: list[int], lang: str = "zh"
) -> str:
    text = _t(lang, "scan_ok").format(new=persisted, removed=expunged)
    if duplicates:
        gids = [str(g) for g in (duplicate_gids or [])][:5]
        shown = ", ".join(gids)
        if len(duplicate_gids or []) > 5:
            shown += _t(lang, "ellipsis")
        text += "\n" + _t(lang, "scan_dup").format(n=duplicates, gids=esc(shown))
    return text


def scan_failed(error: object, lang: str = "zh") -> str:
    return _t(lang, "scan_failed").format(error=esc(error))


# --- favorites --------------------------------------------------------------

def category_label(favcat: int, name: object = None, lang: str = "zh") -> str:
    if name:
        return _t(lang, "fav_category").format(favcat=favcat, name=esc(name))
    return _t(lang, "fav_category_noname").format(favcat=favcat)


def favorites_check_failed(
    favcat: int, name: object, attempts: int, lang: str = "zh"
) -> str:
    return _t(lang, "fav_check_failed").format(
        cat=category_label(favcat, name, lang), n=attempts
    )


def favorites_enqueue_failed(favcat: int, name: object, gid: object, lang: str = "zh") -> str:
    return _t(lang, "fav_enqueue_failed").format(
        cat=category_label(favcat, name, lang), gid=esc(gid)
    )


def favorites_summary(
    favcat: int, name: object, new: int, queued: int, lang: str = "zh"
) -> str:
    return _t(lang, "fav_summary").format(
        cat=category_label(favcat, name, lang), new=new, queued=queued
    )


# --- Telegram bot replies ---------------------------------------------------

def bot_paused(lang: str = "zh") -> str:
    return _t(lang, "bot_paused")


def bot_resumed(lang: str = "zh") -> str:
    return _t(lang, "bot_resumed")


def bot_status(paused: bool, lang: str = "zh") -> str:
    return _t(lang, "bot_status_paused" if paused else "bot_status_running")


def bot_queued(gid: object, lang: str = "zh", title: object | None = None) -> str:
    if title:
        return _t(lang, "bot_queued_title").format(gid=esc(gid), title=esc(title))
    return _t(lang, "bot_queued").format(gid=esc(gid))


def bot_queued_updated(
    old_gid: object, new_gid: object, title: object, lang: str = "zh"
) -> str:
    return _t(lang, "bot_queued_updated").format(
        old=esc(old_gid), new=esc(new_gid), title=esc(title)
    )


def bot_gone(title: object, lang: str = "zh") -> str:
    return _t(lang, "bot_gone").format(title=esc(title))


def bot_already_local(gid: object, title: object, lang: str = "zh") -> str:
    return _t(lang, "bot_already_local").format(gid=esc(gid), title=esc(title))


# --- misc -------------------------------------------------------------------

def test_message(lang: str = "zh") -> str:
    return _t(lang, "test")
