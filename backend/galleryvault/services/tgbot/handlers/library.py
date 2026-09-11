"""Library search and browsing commands (/search, /info, /random, /redownload)."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select

from galleryvault.app.dependencies import resolve_display_title
from galleryvault.app.state import app_state
from galleryvault.db.models import DownloadTask, Gallery, GalleryTag, Tag
from galleryvault.logging import log_extra
from galleryvault.services.messages import bot_text, esc, format_bytes
from galleryvault.services.tag_translation import translated_tag
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.keyboards import (
    build_pagination_row,
    inline_button,
    inline_keyboard,
)
from galleryvault.services.tgbot.router import CommandRouter
from galleryvault.services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)

router = CommandRouter()

PAGE_SIZE = 5
_SEARCH_QUERY_CACHE_MAX = 256
_search_query_cache: OrderedDict[str, str] = OrderedDict()


def _search_token(query: str) -> str:
    """Store the full search query and return a short callback token."""
    token = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    if token in _search_query_cache:
        _search_query_cache.move_to_end(token)
    else:
        _search_query_cache[token] = query
        while len(_search_query_cache) > _SEARCH_QUERY_CACHE_MAX:
            _search_query_cache.popitem(last=False)
    return token


def _search_query_from_token(token: str) -> str | None:
    query = _search_query_cache.get(token)
    if query is not None:
        _search_query_cache.move_to_end(token)
    return query


def _fit_html_caption(caption: str, limit: int = 1024) -> str:
    """Truncate HTML caption without slicing through tags."""
    if len(caption) <= limit:
        return caption
    cut = caption[: max(0, limit - 32)]
    last_nl = cut.rfind("\n")
    if last_nl > 64:
        cut = cut[:last_nl]
    last_lt = cut.rfind("<")
    last_gt = cut.rfind(">")
    if last_lt > last_gt:
        cut = cut[:last_lt].rstrip()
    for tag in ("b", "code", "i"):
        opens = cut.count(f"<{tag}>")
        closes = cut.count(f"</{tag}>")
        if opens > closes:
            cut += f"</{tag}>" * (opens - closes)
    return cut


def _extract_gid(raw: str) -> int | None:
    """Extract integer GID from pure digits or gallery URL string."""
    clean = raw.strip()
    if not clean:
        return None
    if clean.isdigit():
        return int(clean)
    match = re.search(r"/g/(\d+)/", clean)
    if match:
        return int(match.group(1))
    return None


async def _fetch_gallery_tags(session: Any, gallery_id: int, limit: int = 15) -> list[str]:
    """Fetch associated tags for a gallery."""
    try:
        stmt = (
            select(Tag.namespace, Tag.name)
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
            .where(GalleryTag.gallery_id == gallery_id)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        tags: list[str] = []
        for ns, name in rows:
            if ns and str(ns).strip():
                tags.append(f"{ns}:{name}")
            else:
                tags.append(str(name))
        return tags
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed fetching gallery tags", extra=log_extra(error=str(exc)))
        return []


def _format_gallery_info(
    gallery: Gallery,
    tags: list[str] | None = None,
    lang: str = "zh",
) -> tuple[str, dict[str, Any]]:
    """Format full gallery detail caption and inline buttons."""
    title = (
        resolve_display_title(gallery.title, gallery.title_jpn) or gallery.title or str(gallery.gid)
    )
    lines: list[str] = [f"📖 <b>{esc(title)}</b>"]
    if gallery.title_jpn and gallery.title_jpn != title:
        lines.append(f"<code>{esc(gallery.title_jpn)}</code>")

    lines.append("")
    lines.append(bot_text(lang, "bot_info_gid", gid=gallery.gid))
    if gallery.category:
        lines.append(bot_text(lang, "bot_info_category", category=esc(gallery.category)))
    pages = gallery.page_count or gallery.file_count or 0
    if pages:
        lines.append(bot_text(lang, "bot_info_pages", pages=pages))
    size = gallery.storage_size or gallery.file_size
    if size:
        lines.append(bot_text(lang, "bot_info_size", size=format_bytes(size)))
    if gallery.rating is not None:
        lines.append(bot_text(lang, "bot_info_rating", rating=f"{gallery.rating:.1f}"))
    if gallery.uploader:
        lines.append(bot_text(lang, "bot_info_uploader", uploader=esc(gallery.uploader)))

    if tags:
        if lang == "zh":
            formatted_tags: list[str] = []
            for t in tags[:15]:
                try:
                    if ":" in t:
                        ns, name = t.split(":", 1)
                    else:
                        ns, name = None, t
                    try:
                        res = translated_tag(t)  # type: ignore[call-arg]
                    except TypeError:
                        res = translated_tag(ns, name)
                    if isinstance(res, (tuple, list)) and len(res) >= 2:
                        tag_disp = res[1] or name
                    elif isinstance(res, str):
                        tag_disp = res
                    else:
                        tag_disp = str(res)
                except Exception:  # noqa: BLE001
                    tag_disp = t
                formatted_tags.append(tag_disp)
        else:
            formatted_tags = tags[:15]

        tag_str = " ".join(f"#{esc(t)}" for t in formatted_tags)
        if len(tags) > 15:
            tag_str += " …"
        lines.append(bot_text(lang, "bot_info_tags", tags=tag_str))

    caption = "\n".join(lines)

    buttons: list[dict[str, Any]] = [
        inline_button(
            bot_text(lang, "bot_btn_redownload"),
            callback_data=f"lib:redownload:{gallery.gid}",
        )
    ]
    if gallery.token:
        buttons.append(
            inline_button(
                bot_text(lang, "bot_btn_eh_link"),
                url=f"https://e-hentai.org/g/{gallery.gid}/{gallery.token}/",
            )
        )

    kb = inline_keyboard([buttons])
    return caption, kb


async def _send_gallery_card(
    ctx: BotContext,
    gallery: Gallery,
    tags: list[str] | None = None,
    extra_buttons: list[dict[str, Any]] | None = None,
) -> bool:
    """Send gallery info card, attempting photo first with fallback to text."""
    caption, kb = _format_gallery_info(gallery, tags=tags, lang=ctx.lang)
    if extra_buttons:
        kb = {"inline_keyboard": [*kb.get("inline_keyboard", []), list(extra_buttons)]}

    photo_path: Path | None = None
    thumb_svc = getattr(app_state, "thumbnail_service", None)
    if thumb_svc is None:
        try:
            cache_dir = getattr(
                getattr(app_state, "settings", None),
                "thumbnail_cache_dir",
                "./data/thumbnails",
            )
            thumb_svc = ThumbnailService(cache_dir)
        except Exception:  # noqa: BLE001
            thumb_svc = None

    # Check ThumbnailService.cached_remote_cover(gallery.gid)
    try:
        remote_cover = None
        if thumb_svc is not None:
            try:
                remote_cover = thumb_svc.cached_remote_cover(gallery.gid)
            except TypeError:
                remote_cover = ThumbnailService.cached_remote_cover(gallery.gid)  # type: ignore[call-arg]
        else:
            remote_cover = ThumbnailService.cached_remote_cover(gallery.gid)  # type: ignore[call-arg]
        if remote_cover:
            p = Path(remote_cover)
            if p.is_file():
                photo_path = p
    except Exception:  # noqa: BLE001
        photo_path = None

    # If not found, try ThumbnailService.cached(gallery.id, 0)
    if photo_path is None:
        try:
            local_cover = None
            if thumb_svc is not None:
                try:
                    local_cover = thumb_svc.cached(gallery.id, 0)
                except TypeError:
                    local_cover = ThumbnailService.cached(gallery.id, 0)  # type: ignore[call-arg]
            else:
                local_cover = ThumbnailService.cached(gallery.id, 0)  # type: ignore[call-arg]
            if local_cover:
                p = Path(local_cover)
                if p.is_file():
                    photo_path = p
        except Exception:  # noqa: BLE001
            photo_path = None

    cover_sent = False
    if photo_path is not None:
        try:
            cover_sent = await ctx.reply_photo(
                photo_path,
                caption=_fit_html_caption(caption),
                reply_markup=kb,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed sending cover photo", extra=log_extra(error=str(exc)))
            cover_sent = False

    if not cover_sent:
        reply_fn = getattr(ctx, "reply", getattr(ctx, "reply_text", None))
        if reply_fn is not None:
            return await reply_fn(caption, reply_markup=kb)
        return False
    return True


async def _execute_search(
    ctx: BotContext, query: str, page: int = 1, is_edit: bool = False
) -> None:
    """Query galleries matching keyword and reply or edit message with paginated list."""
    clean_query = query.strip()
    if not clean_query:
        await ctx.reply_text(bot_text(ctx.lang, "bot_search_usage"))
        return

    if not app_state.session_factory:
        msg = bot_text(ctx.lang, "bot_db_not_ready")
        if is_edit:
            await ctx.edit_text(msg)
        else:
            await ctx.reply_text(msg)
        return

    page = max(1, page)
    async with app_state.session_factory() as session:
        base_where = [
            Gallery.expunged.is_(False),
            Gallery.trashed.is_(False),
        ]
        if clean_query.isdigit():
            match_cond = or_(
                Gallery.gid == int(clean_query),
                Gallery.title.ilike(f"%{clean_query}%"),
            )
        else:
            like_pattern = f"%{clean_query}%"
            match_cond = or_(
                Gallery.title.ilike(like_pattern),
                Gallery.title_jpn.ilike(like_pattern),
                Gallery.uploader.ilike(like_pattern),
                Gallery.category.ilike(like_pattern),
            )

        total_stmt = select(func.count()).select_from(Gallery).where(*base_where, match_cond)
        total_count = int(await session.scalar(total_stmt) or 0)

        if total_count == 0:
            text = bot_text(ctx.lang, "bot_search_empty", query=esc(clean_query))
            if is_edit:
                await ctx.edit_text(text)
            else:
                await ctx.reply_text(text)
            return

        if total_count == 1:
            single_stmt = select(Gallery).where(*base_where, match_cond).limit(1)
            single_gallery = await session.scalar(single_stmt)
            if single_gallery is not None:
                tags = await _fetch_gallery_tags(session, single_gallery.id)
                await _send_gallery_card(ctx, single_gallery, tags=tags)
                return

        total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
        page = min(page, total_pages)

        stmt = (
            select(Gallery)
            .where(*base_where, match_cond)
            .order_by(Gallery.id.desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
        rows = list((await session.scalars(stmt)).all())

    lines: list[str] = [
        bot_text(
            ctx.lang,
            "bot_search_head",
            page=page,
            total_pages=total_pages,
            total=total_count,
        ),
        "",
    ]
    info_buttons: list[dict[str, Any]] = []

    for idx, g in enumerate(rows, start=1 + (page - 1) * PAGE_SIZE):
        g_title = resolve_display_title(g.title, g.title_jpn) or g.title or str(g.gid)
        pages_str = f" · {g.page_count or g.file_count}P" if (g.page_count or g.file_count) else ""
        cat_str = f"[{esc(g.category)}] " if g.category else ""
        rating_str = f" · ⭐{g.rating:.1f}" if g.rating is not None else ""
        lines.append(f"<b>{idx}.</b> {cat_str}<code>{g.gid}</code> {esc(g_title[:50])}")
        lines.append(f"   <i>{g.uploader or 'unknown'}{pages_str}{rating_str}</i>")
        info_buttons.append(inline_button(f"📖 {g.gid}", callback_data=f"lib:info:{g.gid}"))

    page_row = build_pagination_row(
        page, total_pages, callback_prefix=f"lib:p:{_search_token(clean_query)}"
    )

    rows_kb: list[list[dict[str, Any]]] = []
    # Place info buttons 3 per row
    for i in range(0, len(info_buttons), 3):
        rows_kb.append(info_buttons[i : i + 3])
    if page_row:
        rows_kb.append(page_row)

    kb = inline_keyboard(rows_kb)
    text = "\n".join(lines)
    if is_edit:
        await ctx.edit_text(text, reply_markup=kb)
    else:
        await ctx.reply_text(text, reply_markup=kb)


@router.command(["search"], description="Search local galleries: /search <query>")
async def cmd_search(ctx: BotContext) -> None:
    """Search local galleries by title, uploader, or gid."""
    await _execute_search(ctx, ctx.args.strip(), page=1, is_edit=False)


@router.command(["info"], description="View gallery details: /info <gid>")
async def cmd_info(ctx: BotContext) -> None:
    """Display gallery details and cover photo."""
    gid = _extract_gid(ctx.args)
    if gid is None:
        await ctx.reply_text(bot_text(ctx.lang, "bot_info_usage"))
        return

    if not app_state.session_factory:
        await ctx.reply_text(bot_text(ctx.lang, "bot_db_not_ready"))
        return

    async with app_state.session_factory() as session:
        gallery = await session.scalar(select(Gallery).where(Gallery.gid == gid).limit(1))
        if gallery is None:
            await ctx.reply_text(bot_text(ctx.lang, "bot_gallery_not_found", gid=gid))
            return
        tags = await _fetch_gallery_tags(session, gallery.id)

    await _send_gallery_card(ctx, gallery, tags=tags)


@router.command(["random"], description="Pick a random gallery")
async def cmd_random(ctx: BotContext) -> None:
    """Randomly pick a gallery from local library."""
    if not app_state.session_factory:
        await ctx.reply_text(bot_text(ctx.lang, "bot_db_not_ready"))
        return

    async with app_state.session_factory() as session:
        stmt = (
            select(Gallery)
            .where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
            .order_by(func.random())
            .limit(1)
        )
        gallery = await session.scalar(stmt)
        if gallery is None:
            await ctx.reply_text(bot_text(ctx.lang, "bot_random_empty"))
            return
        tags = await _fetch_gallery_tags(session, gallery.id)

    next_btn = [
        inline_button(bot_text(ctx.lang, "bot_btn_random_again"), callback_data="lib:random")
    ]
    await _send_gallery_card(ctx, gallery, tags=tags, extra_buttons=next_btn)


@router.command(["redownload"], description="Redownload gallery: /redownload <gid>")
async def cmd_redownload(ctx: BotContext) -> None:
    """Queue redownload of a gallery by gid."""
    gid = _extract_gid(ctx.args)
    if gid is None:
        await ctx.reply_text(bot_text(ctx.lang, "bot_redownload_usage"))
        return

    if not app_state.session_factory:
        await ctx.reply_text(bot_text(ctx.lang, "bot_db_not_ready"))
        return

    token: str | None = None
    title: str = str(gid)
    title_jpn: str | None = None

    async with app_state.session_factory() as session:
        gallery = await session.scalar(select(Gallery).where(Gallery.gid == gid).limit(1))
        if gallery and gallery.token:
            token = gallery.token
            title = (
                resolve_display_title(gallery.title, gallery.title_jpn) or gallery.title or str(gid)
            )
            title_jpn = gallery.title_jpn
        else:
            task = await session.scalar(
                select(DownloadTask)
                .where(DownloadTask.gid == gid)
                .order_by(DownloadTask.id.desc())
                .limit(1)
            )
            if task and task.token:
                token = task.token
                title = task.title or str(gid)

    if not token:
        await ctx.reply_text(bot_text(ctx.lang, "bot_redownload_no_token", gid=gid))
        return

    quality = getattr(ctx.settings, "download_quality", None) or "resample"
    from galleryvault.services.telegram_bot import TelegramGalleryItem

    item = TelegramGalleryItem(gid=gid, token=token, title=title, title_jpn=title_jpn)
    try:
        await ctx.queue.enqueue(item, quality=quality)
    except TypeError:
        await ctx.queue.enqueue(item)

    await ctx.reply_text(bot_text(ctx.lang, "bot_redownload_queued", title=esc(title), gid=gid))


# --- Callback query handlers ---


@router.callback(r"^lib:p:(.*):p:(\d+)$")
async def cb_search_page(ctx: BotContext) -> None:
    """Handle pagination callback for /search results."""
    match = ctx.extra.get("match")
    if not match:
        await ctx.answer_callback()
        return
    token = match.group(1)
    page = int(match.group(2))
    await ctx.answer_callback()
    query = _search_query_from_token(token)
    if query is None:
        await ctx.edit_text(bot_text(ctx.lang, "bot_search_expired"))
        return
    await _execute_search(ctx, query=query, page=page, is_edit=True)


@router.callback(r"^lib:info:(\d+)$")
async def cb_gallery_info(ctx: BotContext) -> None:
    """Handle gallery detail click from search list."""
    match = ctx.extra.get("match")
    gid = int(match.group(1)) if match else None
    await ctx.answer_callback()
    if gid is None or not app_state.session_factory:
        return

    async with app_state.session_factory() as session:
        gallery = await session.scalar(select(Gallery).where(Gallery.gid == gid).limit(1))
        if gallery is None:
            await ctx.reply_text(bot_text(ctx.lang, "bot_gallery_not_found", gid=gid))
            return
        tags = await _fetch_gallery_tags(session, gallery.id)

    await _send_gallery_card(ctx, gallery, tags=tags)


@router.callback(r"^lib:random$")
async def cb_random_again(ctx: BotContext) -> None:
    """Handle 'Random Again' button click."""
    await ctx.answer_callback()
    await cmd_random(ctx)


@router.callback(r"^lib:redownload:(\d+)$")
async def cb_redownload(ctx: BotContext) -> None:
    """Handle inline redownload button click."""
    match = ctx.extra.get("match")
    gid = int(match.group(1)) if match else None
    await ctx.answer_callback(bot_text(ctx.lang, "bot_cb_redownloading"))
    if gid is None:
        return
    ctx.args = str(gid)
    await cmd_redownload(ctx)


@router.callback(r"^lib:.*noop.*$")
async def cb_noop(ctx: BotContext) -> None:
    """Handle noop pagination indicator buttons."""
    await ctx.answer_callback()
