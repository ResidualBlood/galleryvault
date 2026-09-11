"""Admin and operational maintenance commands (/ping, /status, /cookie, /quota, /storage, /scan)."""

from __future__ import annotations

import time

from galleryvault.app.state import app_state
from galleryvault.services.messages import (
    bot_cookie_health,
    bot_pong,
    bot_quota,
    bot_scan_triggered,
    bot_status,
    bot_storage,
    bot_text,
    esc,
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


@router.command(["status"], description="Query system status and download queue overview")
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

    queue_counts: dict[str, int] | None = None
    try:
        dq = getattr(getattr(ctx, "state", None), "download_queue", None)
        if dq is not None and hasattr(dq, "list_queue_snapshot"):
            res = dq.list_queue_snapshot()
            if hasattr(res, "__await__"):
                res = await res
            if isinstance(res, tuple) and len(res) == 2 and isinstance(res[1], dict):
                queue_counts = res[1]
            elif isinstance(res, dict):
                queue_counts = res
        if queue_counts is None:
            from galleryvault.services.telegram_bot import list_queue_snapshot

            _items, queue_counts = await list_queue_snapshot()
    except Exception:  # noqa: BLE001
        queue_counts = None

    await ctx.reply_text(
        bot_status(
            paused,
            uptime_seconds=uptime_seconds,
            queue_counts=queue_counts,
            lang=ctx.lang,
        )
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
        if isinstance(img_limit, dict) or gp is not None:
            current = img_limit.get("current") if isinstance(img_limit, dict) else None
            limit = img_limit.get("limit") if isinstance(img_limit, dict) else None
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
        from galleryvault.app.routers.settings import system_storage

        if app_state.session_factory is not None:
            try:
                data = await system_storage()
            except Exception:  # noqa: BLE001
                data = await system_storage(session=object())  # type: ignore[arg-type]
        else:
            data = await system_storage(session=object())  # type: ignore[arg-type]

        lib = data.get("library") if isinstance(data.get("library"), dict) else {}
        cold = data.get("cold") if isinstance(data.get("cold"), dict) else {}
        dl = data.get("downloads") if isinstance(data.get("downloads"), dict) else {}
        cache = data.get("cache") if isinstance(data.get("cache"), dict) else {}

        disk_total = (
            lib.get("disk_total")
            or dl.get("disk_total")
            or cache.get("disk_total")
            or cold.get("disk_total")
        )
        disk_used = (
            lib.get("disk_used")
            or dl.get("disk_used")
            or cache.get("disk_used")
            or cold.get("disk_used")
        )
        disk_free = (
            lib.get("disk_free")
            or dl.get("disk_free")
            or cache.get("disk_free")
            or cold.get("disk_free")
        )

        gallery_count = data.get("library", {}).get("gallery_count") if isinstance(data.get("library"), dict) else None
        file_count = data.get("downloads", {}).get("image_count") if isinstance(data.get("downloads"), dict) else None
        thumb_count = data.get("cache", {}).get("thumbnail_count") if isinstance(data.get("cache"), dict) else None

        await ctx.reply_text(
            bot_storage(
                library_bytes=lib.get("bytes"),  # type: ignore[arg-type]
                downloads_bytes=dl.get("bytes"),  # type: ignore[arg-type]
                cache_bytes=cache.get("bytes"),  # type: ignore[arg-type]
                cold_bytes=cold.get("bytes") or 0,  # type: ignore[arg-type]
                disk_total=disk_total,  # type: ignore[arg-type]
                disk_used=disk_used,  # type: ignore[arg-type]
                disk_free=disk_free,  # type: ignore[arg-type]
                gallery_count=gallery_count,
                file_count=file_count,
                thumb_count=thumb_count,
                lang=ctx.lang,
            )
        )
    except Exception as exc:  # noqa: BLE001
        await ctx.reply_text(bot_text(ctx.lang, "bot_storage_fail", detail=esc(exc)))


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
