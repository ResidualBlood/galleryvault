"""Admin and operational maintenance commands (/ping, /status, /cookie, /quota, /storage, /scan)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from galleryvault.app.state import app_state
from galleryvault.services.messages import (
    bot_cookie_health,
    bot_pong,
    bot_quota,
    bot_scan_triggered,
    bot_status,
    bot_storage,
)
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.router import CommandRouter

router = CommandRouter()


@router.command(["ping"], description="Test connection latency")
async def cmd_ping(ctx: BotContext) -> None:
    """Respond to /ping with pong and latency."""
    latency_ms: float | None = None
    msg_date = ctx.update.get("message", {}).get("date")
    if msg_date:
        try:
            latency_ms = max(0.0, (time.time() - float(msg_date)) * 1000)
        except (TypeError, ValueError):
            latency_ms = None
    await ctx.reply_text(bot_pong(latency_ms, lang=ctx.lang))


@router.command(["status"], description="Show system status and uptime")
async def cmd_status(ctx: BotContext) -> None:
    """Show system and download status."""
    paused = bool(
        getattr(ctx.settings, "global_paused", False)
        or getattr(app_state.settings, "global_paused", False)
    )
    uptime_seconds: float | None = None
    try:
        started_at = getattr(app_state, "started_at", None)
        if started_at:
            uptime_seconds = max(0.0, time.time() - float(started_at))
    except (TypeError, ValueError, AttributeError):
        uptime_seconds = None

    await ctx.reply_text(
        bot_status(paused, uptime_seconds=uptime_seconds, lang=ctx.lang)
    )


@router.command(["cookie"], description="Check E-Hentai cookie health")
async def cmd_cookie(ctx: BotContext) -> None:
    """Probe and check E-Hentai cookie validity."""
    try:
        from galleryvault.services.eh_client import probe_cookie_health

        health = await probe_cookie_health()
        state = str(health.get("state") or "unknown")
        detail = str(health.get("detail")) if health.get("detail") else None
        checked_at = str(health.get("checked_at")) if health.get("checked_at") else None
        await ctx.reply_text(
            bot_cookie_health(state, detail=detail, checked_at=checked_at, lang=ctx.lang)
        )
    except Exception as exc:  # noqa: BLE001
        await ctx.reply_text(bot_cookie_health("failed", detail=str(exc), lang=ctx.lang))


@router.command(["quota"], description="Check E-Hentai image quota")
async def cmd_quota(ctx: BotContext) -> None:
    """Query E-Hentai image download quota and GP balance."""
    try:
        from galleryvault.app.routers.tasks import get_quota

        res = await get_quota()
        img_limit = res.get("image_limit") or res.get("image_limits")
        gp = res.get("gp")
        if isinstance(img_limit, dict):
            current = img_limit.get("current")
            limit = img_limit.get("limit")
            await ctx.reply_text(
                bot_quota(current=current, limit=limit, gp=gp, lang=ctx.lang)
            )
        else:
            err = res.get("error") or "Quota unavailable"
            await ctx.reply_text(bot_quota(detail=str(err), lang=ctx.lang))
    except Exception as exc:  # noqa: BLE001
        await ctx.reply_text(bot_quota(detail=str(exc), lang=ctx.lang))


@router.command(["storage"], description="Check storage usage and disk capacity")
async def cmd_storage(ctx: BotContext) -> None:
    """Query storage usage for library, downloads, cache and underlying disk."""
    try:
        from galleryvault.services.storage_usage import storage_tracker

        l_snap = storage_tracker.get_library_snapshot()
        d_snap = storage_tracker.get_downloads_snapshot()
        c_snap = storage_tracker.get_cache_snapshot()

        disk_total, disk_used, disk_free = None, None, None
        lib_path = getattr(ctx.settings, "library_path", None)
        if lib_path and Path(lib_path).exists():
            du = shutil.disk_usage(lib_path)
            disk_total, disk_used, disk_free = du.total, du.used, du.free

        await ctx.reply_text(
            bot_storage(
                library_bytes=l_snap.bytes,
                downloads_bytes=d_snap.bytes,
                cache_bytes=c_snap.bytes,
                disk_total=disk_total,
                disk_used=disk_used,
                disk_free=disk_free,
                lang=ctx.lang,
            )
        )
    except Exception as exc:  # noqa: BLE001
        await ctx.reply_text(f"❌ Storage check failed: {exc}")


@router.command(["scan"], description="Trigger library scan")
async def cmd_scan(ctx: BotContext) -> None:
    """Check library scan state and trigger scan if idle."""
    from galleryvault.app.dependencies import get_task_manager, spawn_task
    from galleryvault.services.scan_worker import run_scan

    paused = bool(
        getattr(ctx.settings, "global_paused", False)
        or getattr(app_state.settings, "global_paused", False)
    )
    if paused:
        await ctx.reply_text(bot_scan_triggered("paused", lang=ctx.lang))
        return

    tm = get_task_manager()
    if tm.scan_state.get("running"):
        scanned = int(tm.scan_state.get("scanned") or 0)
        await ctx.reply_text(bot_scan_triggered("running", scanned=scanned, lang=ctx.lang))
        return

    tm.scan_state["running"] = True
    spawn_task(run_scan(), "library scan")
    await ctx.reply_text(bot_scan_triggered("started", lang=ctx.lang))
