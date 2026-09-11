"""Telegram Bot module aggregating all command and callback routers."""

from __future__ import annotations

from galleryvault.services.messages import (
    bot_already_local,
    bot_gone,
    bot_queued,
    bot_queued_updated,
    bot_stats,
)
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.router import CommandRouter

HELP_TEXT_ZH = (
    "🤖 <b>GalleryVault 机器人指令清单</b>\n\n"
    "⚙️ <b>系统与运维</b>\n"
    "• <code>/status</code> 查询系统运行状态与队列概况\n"
    "• <code>/ping</code> 测试机器人响应延迟\n"
    "• <code>/cookie</code> 检查 E-Hentai Cookie 有效性\n"
    "• <code>/quota</code> 查询 EH 图像配额与 GP 余额\n"
    "• <code>/storage</code> 查看存储空间与磁盘容量\n"
    "• <code>/scan</code> 触发图库扫描入库\n\n"
    "📥 <b>下载与队列</b>\n"
    "• <code>/queue</code> 查看下载队列及交互操作\n"
    "• <code>/pause</code> 暂停全局下载调度\n"
    "• <code>/resume</code> 恢复全局下载调度\n"
    "• <code>/retry &lt;id|all&gt;</code> 重试失败的下载任务\n"
    "• <code>/cancel &lt;id|gid&gt;</code> 取消等待或下载中的任务\n"
    "• <code>/clear</code> 清除已完成任务的历史记录\n"
    "• <code>/stats</code> 统计图库本数与队列状态快照\n\n"
    "📋 <b>任务控制</b>\n"
    "• <code>/tasks</code> 查看后台正在运行的长任务\n"
    "• <code>/kill &lt;name&gt;</code> 中断指定后台长任务\n\n"
    "📖 <b>图库与检索</b>\n"
    "• <code>/search &lt;关键词&gt;</code> 搜索本地画廊并支持翻页\n"
    "• <code>/info &lt;gid&gt;</code> 查看画廊详细信息与封面\n"
    "• <code>/random</code> 随心看，随机抽取一本画廊\n"
    "• <code>/redownload &lt;gid&gt;</code> 重新加入下载队列\n\n"
    "⭐ <b>收藏夹自动化</b>\n"
    "• <code>/fav_sync</code> 同步云端收藏夹分类\n"
    "• <code>/fav_download [0-9]</code> 自动下载收藏夹未入库本子\n"
    "• <code>/fav_check</code> 检查收藏夹全量更新\n\n"
    "• <code>/help</code> 显示帮助菜单\n\n"
    "💡 直接在聊天中发送 E(x)Hentai 画廊 URL 即可自动解析入队。"
)

HELP_TEXT_EN = (
    "🤖 <b>GalleryVault Bot Commands</b>\n\n"
    "⚙️ <b>System & Maintenance</b>\n"
    "• <code>/status</code> Query system status and download queue overview\n"
    "• <code>/ping</code> Test bot response latency\n"
    "• <code>/cookie</code> Check E-Hentai cookie health\n"
    "• <code>/quota</code> Check EH image quota and GP\n"
    "• <code>/storage</code> Check storage usage & disk capacity\n"
    "• <code>/scan</code> Trigger library scan\n\n"
    "📥 <b>Downloads & Queue</b>\n"
    "• <code>/queue</code> View download queue & action buttons\n"
    "• <code>/pause</code> Pause downloads globally\n"
    "• <code>/resume</code> Resume downloads globally\n"
    "• <code>/retry &lt;id|all&gt;</code> Retry failed download tasks\n"
    "• <code>/cancel &lt;id|gid&gt;</code> Cancel pending or downloading task\n"
    "• <code>/clear</code> Clear completed task history\n"
    "• <code>/stats</code> Library counts and queue summary\n\n"
    "📋 <b>Tasks Control</b>\n"
    "• <code>/tasks</code> List running background tasks\n"
    "• <code>/kill &lt;name&gt;</code> Interrupt running task\n\n"
    "📖 <b>Library</b>\n"
    "• <code>/search &lt;query&gt;</code> Search local galleries with pagination\n"
    "• <code>/info &lt;gid&gt;</code> View gallery details & cover\n"
    "• <code>/random</code> Pick a random gallery\n"
    "• <code>/redownload &lt;gid&gt;</code> Re-enqueue gallery for redownload\n\n"
    "⭐ <b>Favorites</b>\n"
    "• <code>/fav_sync</code> Sync remote favorite categories\n"
    "• <code>/fav_download [0-9]</code> Download missing favorites\n"
    "• <code>/fav_check</code> Check all favorite categories for updates\n\n"
    "• <code>/help</code> Show this help message\n\n"
    "💡 Paste an E(x)Hentai gallery URL directly to start downloading."
)


def get_help_message(lang: str = "zh") -> str:
    """Return formatted full bot command help message."""
    return HELP_TEXT_EN if lang == "en" else HELP_TEXT_ZH


def get_root_router() -> CommandRouter:
    """Construct and return the root CommandRouter aggregating all sub-routers."""
    from galleryvault.services.tgbot.handlers.admin import router as router_admin
    from galleryvault.services.tgbot.handlers.favorites import router as router_favorites
    from galleryvault.services.tgbot.handlers.library import router as router_library
    from galleryvault.services.tgbot.handlers.queue import router as router_queue
    from galleryvault.services.tgbot.handlers.tasks import router as router_tasks

    root = CommandRouter()

    # Include modular sub-routers
    root.include_router(router_admin)
    root.include_router(router_queue)
    root.include_router(router_tasks)
    root.include_router(router_library)
    root.include_router(router_favorites)

    # Register /help and /stats commands
    @root.command(["help"], description="Show comprehensive command help")
    async def handle_help(ctx: BotContext) -> None:
        await ctx.reply_text(get_help_message(ctx.lang))

    @root.command(["stats"], description="Show library counts and queue summary")
    async def handle_stats(ctx: BotContext) -> None:
        from galleryvault.services.telegram_bot import library_count, list_queue_snapshot

        _items, counts = await list_queue_snapshot()
        galleries = await library_count()
        await ctx.reply_text(
            bot_stats(
                galleries,
                counts.get("pending", 0),
                counts.get("downloading", 0),
                counts.get("failed", 0),
                ctx.lang,
            )
        )

    # Message handler: parse gallery URLs and enqueue
    @root.default_message
    async def handle_message(ctx: BotContext) -> None:
        from galleryvault.services.eh_client import parse_gallery_url
        from galleryvault.services.telegram_bot import TelegramGalleryItem

        text = ctx.text
        base_url = getattr(ctx.settings, "exhentai_base_url", "https://exhentai.org")
        try:
            gid, token = parse_gallery_url(text, base_url)
        except (ValueError, TypeError):
            await ctx.reply_text(get_help_message(ctx.lang))
            return

        from galleryvault.app.state import app_state

        paused = bool(
            getattr(ctx.settings, "global_paused", False)
            or (app_state.settings and getattr(app_state.settings, "global_paused", False))
        )
        if not paused:
            from galleryvault.app.dependencies import resolve_display_title
            from galleryvault.services.download_prepare import prepare_galleries

            try:
                prepared_list = await prepare_galleries([(gid, token)])
                prepared = prepared_list[0] if prepared_list else None
            except Exception:  # noqa: BLE001
                prepared = None

            if prepared is not None and prepared.gone:
                label = (
                    resolve_display_title(prepared.title, prepared.title_jpn)
                    or prepared.title
                    or str(gid)
                )
                await ctx.reply_text(bot_gone(label, ctx.lang))
                return

            if prepared is not None and prepared.already_local:
                label = (
                    resolve_display_title(prepared.title, prepared.title_jpn)
                    or prepared.title
                    or str(prepared.gid)
                )
                await ctx.reply_text(bot_already_local(prepared.gid, label, ctx.lang))
                return

            item_gid, item_token, item_title, item_jpn, old_gid = (
                gid,
                token,
                text,
                None,
                None,
            )
            if prepared is not None:
                item_gid = prepared.gid
                item_token = prepared.token
                item_jpn = prepared.title_jpn
                old_gid = prepared.old_gid
                item_title = (
                    resolve_display_title(prepared.title, prepared.title_jpn)
                    or prepared.title
                    or str(prepared.gid)
                )

            default_quality = getattr(ctx.settings, "download_quality", None) or "resample"
            item = TelegramGalleryItem(
                gid=item_gid,
                token=item_token,
                title=item_title,
                title_jpn=item_jpn,
            )
            try:
                await ctx.queue.enqueue(item, quality=default_quality)
            except TypeError:
                await ctx.queue.enqueue(item)

            if old_gid:
                await ctx.reply_text(
                    bot_queued_updated(old_gid, item_gid, item_title, ctx.lang)
                )
            else:
                await ctx.reply_text(bot_queued(item_gid, ctx.lang, title=item_title))

    @root.default_command
    async def handle_unknown_command(ctx: BotContext) -> None:
        await ctx.reply_text(get_help_message(ctx.lang))

    return root
