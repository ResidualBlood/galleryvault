"""Favorites automation commands (/fav_sync, /fav_download, /fav_check)."""

from __future__ import annotations

import logging

from galleryvault.app.dependencies import spawn_task
from galleryvault.app.state import app_state
from galleryvault.logging import log_extra
from galleryvault.services.favorites_worker import (
    favorite_size_sync,
    run_favorites_check,
)
from galleryvault.services.messages import bot_text, esc
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.router import CommandRouter

logger = logging.getLogger(__name__)

router = CommandRouter()


def _get_target_favcats(raw: str) -> tuple[list[int] | None, str | None]:
    """Parse optional favcat argument (0-9). Returns (list_of_cats, error_key)."""
    clean = raw.strip()
    if not clean:
        return list(range(10)), None
    try:
        val = int(clean)
        if 0 <= val <= 9:
            return [val], None
        return None, "bot_fav_cat_range"
    except ValueError:
        return None, "bot_fav_cat_number"


@router.command(["fav_sync"], description="Sync favorite categories and metadata")
async def cmd_fav_sync(ctx: BotContext) -> None:
    """Sync remote favorite categories from ExHentai."""
    cookies = getattr(ctx.settings, "exhentai_cookies", None) or getattr(
        app_state.settings, "exhentai_cookies", None
    )
    if not cookies:
        await ctx.reply_text(bot_text(ctx.lang, "bot_fav_no_cookie"))
        return

    if not app_state.session_factory:
        await ctx.reply_text(bot_text(ctx.lang, "bot_db_not_ready"))
        return

    try:
        from galleryvault.app.dependencies import get_eh_client_manager
        from galleryvault.app.routers.favorites import sync_favorite_categories

        eh_client_mgr = get_eh_client_manager()
        async with app_state.session_factory() as session:
            cats = await sync_favorite_categories(session=session, eh_client_mgr=eh_client_mgr)
            count = len(cats)
        await ctx.reply_text(bot_text(ctx.lang, "bot_fav_sync_ok", count=count))
    except Exception as exc:
        logger.warning("Bot fav_sync failed", extra=log_extra(error=str(exc)), exc_info=True)
        await ctx.reply_text(bot_text(ctx.lang, "bot_fav_sync_fail", detail=esc(exc)))


@router.command(["fav_download"], description="Download missing favorites: /fav_download [favcat]")
async def cmd_fav_download(ctx: BotContext) -> None:
    """Trigger missing favorites download for a specific category or all categories."""
    cats, err_key = _get_target_favcats(ctx.args)
    if err_key is not None or cats is None:
        usage = bot_text(ctx.lang, "bot_fav_download_usage")
        extra = bot_text(ctx.lang, err_key) if err_key else ""
        await ctx.reply_text(f"{usage}\n{extra}".rstrip())
        return

    triggered_cats: list[int] = []
    for c in cats:
        spawn_task(favorite_size_sync(c), f"favorite metadata sync {c}")
        triggered_cats.append(c)

    if len(triggered_cats) == 1:
        cat_desc = bot_text(ctx.lang, "bot_fav_cat_one", favcat=triggered_cats[0])
    else:
        cat_desc = bot_text(ctx.lang, "bot_fav_cat_all", count=len(triggered_cats))

    await ctx.reply_text(bot_text(ctx.lang, "bot_fav_download_started", cat=cat_desc))


@router.command(["fav_check"], description="Check all favorites for updates")
async def cmd_fav_check(ctx: BotContext) -> None:
    """Trigger full check on all 10 favorite categories for remote updates."""
    service = getattr(app_state, "favorites_service", None)
    if service is None:
        try:
            from galleryvault.app.dependencies import get_favorite_service

            service = get_favorite_service()
        except Exception:  # noqa: BLE001
            service = None

    if service is None:
        await ctx.reply_text(bot_text(ctx.lang, "bot_fav_check_no_service"))
        return

    favcats = list(range(10))
    for favcat in favcats:
        spawn_task(run_favorites_check(favcat, service), f"favorites check {favcat}")

    await ctx.reply_text(bot_text(ctx.lang, "bot_fav_check_started", count=len(favcats)))
