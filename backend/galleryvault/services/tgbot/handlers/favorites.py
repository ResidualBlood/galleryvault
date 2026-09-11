"""Favorites automation commands (/fav_sync, /fav_download, /fav_check)."""

from __future__ import annotations

import logging

from galleryvault.app.dependencies import spawn_task
from galleryvault.app.state import app_state
from galleryvault.db.repositories.favorites import FavoritesRepository
from galleryvault.logging import log_extra
from galleryvault.services.favorites_worker import (
    FavoriteDownloadQueue,
    favorite_size_sync,
    run_favorites_check,
)
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.router import CommandRouter

logger = logging.getLogger(__name__)

router = CommandRouter()


def _get_target_favcats(raw: str) -> tuple[list[int] | None, str | None]:
    """Parse optional favcat argument (0-9). Returns (list_of_cats, error_message)."""
    clean = raw.strip()
    if not clean:
        return list(range(10)), None
    try:
        val = int(clean)
        if 0 <= val <= 9:
            return [val], None
        return None, "分类编号必须在 0 到 9 之间"
    except ValueError:
        return None, "分类编号必须为数字 (0-9)"


@router.command(["fav_sync"], description="Sync favorite categories and metadata")
async def cmd_fav_sync(ctx: BotContext) -> None:
    """Sync remote favorite categories from ExHentai."""
    cookies = getattr(ctx.settings, "exhentai_cookies", None) or getattr(
        app_state.settings, "exhentai_cookies", None
    )
    if not cookies:
        await ctx.reply_text("⚠️ 尚未配置 ExHentai Cookie，无法同步云端收藏夹。")
        return

    if not app_state.session_factory:
        await ctx.reply_text("❌ 数据库未就绪")
        return

    try:
        from galleryvault.app.dependencies import get_eh_client_manager
        from galleryvault.app.routers.favorites import sync_favorite_categories

        eh_client_mgr = get_eh_client_manager()
        async with app_state.session_factory() as session:
            cats = await sync_favorite_categories(session=session, eh_client_mgr=eh_client_mgr)
            count = len(cats)
        await ctx.reply_text(f"✅ 收藏夹分类同步成功，共获取到 <b>{count}</b> 个云端分类。")
    except Exception as exc:
        logger.warning("Bot fav_sync failed", extra=log_extra(error=str(exc)), exc_info=True)
        await ctx.reply_text(f"❌ 收藏夹同步失败：{exc}")


@router.command(["fav_download"], description="Download missing favorites: /fav_download [favcat]")
async def cmd_fav_download(ctx: BotContext) -> None:
    """Trigger missing favorites download for a specific category or all categories."""
    cats, err = _get_target_favcats(ctx.args)
    if err is not None or cats is None:
        await ctx.reply_text(f"📥 用法：<code>/fav_download [favcat (0-9)]</code>\n{err or ''}")
        return

    enqueued_count = 0
    triggered_cats: list[int] = []

    if app_state.session_factory:
        try:
            from galleryvault.db.models import Gallery

            async with app_state.session_factory() as session:
                repo = FavoritesRepository(session)
                # Query local known galleries to identify missing items
                from sqlalchemy import select

                local_gids_res = await session.scalars(
                    select(Gallery.gid).where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
                )
                local_gids = set(local_gids_res.all())

                queue = FavoriteDownloadQueue(session=session)
                default_quality = getattr(ctx.settings, "download_quality", None) or "resample"

                from types import SimpleNamespace

                for c in cats:
                    items = await repo.all_gids_for_favcat(c)
                    for gid, token, _thumb in items:
                        if gid not in local_gids and token:
                            fav_item = SimpleNamespace(
                                gid=gid,
                                token=token,
                                title=f"Favorite {gid}",
                                title_jpn=None,
                            )
                            try:
                                if await queue.enqueue(fav_item, mode="favorite", quality=default_quality):
                                    enqueued_count += 1
                            except Exception:  # noqa: BLE001, S110
                                pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed enqueuing missing favorite items directly", extra=log_extra(error=str(exc)))

    for c in cats:
        spawn_task(favorite_size_sync(c), f"favorite metadata sync {c}")
        triggered_cats.append(c)

    if len(triggered_cats) == 1:
        cat_desc = f"分类 {triggered_cats[0]}"
    else:
        cat_desc = f"全部分类 ({len(triggered_cats)} 个)"

    if enqueued_count > 0:
        await ctx.reply_text(
            f"📥 已触发 <b>{cat_desc}</b> 缺本下载任务，共将 <b>{enqueued_count}</b> 本未入库画廊加入下载队列。"
        )
    else:
        await ctx.reply_text(
            f"📥 已触发 <b>{cat_desc}</b> 缺本下载与元数据补全长任务。"
        )


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
        await ctx.reply_text("❌ 收藏夹服务未初始化，无法启动检查。")
        return

    favcats = list(range(10))
    for favcat in favcats:
        spawn_task(run_favorites_check(favcat, service), f"favorites check {favcat}")

    await ctx.reply_text(f"⏳ 已启动全量收藏夹检查长任务（共 <b>{len(favcats)}</b> 个分类）。")
