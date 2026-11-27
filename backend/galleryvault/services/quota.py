"""E-Hentai quota (GP balance + image limits) use case.

Moved out of ``app/routers/tasks.py`` so both the HTTP router and the Telegram
bot call the same service instead of the bot importing the router module.
"""

from __future__ import annotations

import logging

from ..app.state import app_state
from ..config import get_settings
from ..logging import log_extra, mask_sensitive

logger = logging.getLogger(__name__)

# Stable, generic text for /api/quota failures: exception strings may embed
# cookies, tokens or internal paths, so they only go to the log.
_QUOTA_ERROR_MESSAGE = "quota check failed"


_GP_CACHE_TTL = 1800  # 30 min, same as cookie probe
_IL_FAIL_TTL = 60  # retry Image Limit sooner than GP after a fetch error
_GP_LOCK = None


def _get_gp_lock():
    global _GP_LOCK
    if _GP_LOCK is None:
        import asyncio

        _GP_LOCK = asyncio.Lock()
    return _GP_LOCK


async def get_quota() -> dict[str, object]:
    """Cached GP balance + Image Limits (low-frequency, 30 min TTL)."""
    from datetime import UTC, datetime

    settings = app_state.settings or get_settings()
    cache = app_state.extra.get("gp_cache") if isinstance(app_state.extra.get("gp_cache"), dict) else {}
    now = datetime.now(UTC)
    if cache.get("gp_checked_at") is None and cache.get("checked_at"):
        cache["gp_checked_at"] = cache["checked_at"]
        cache["il_checked_at"] = cache.get("il_checked_at") or cache["checked_at"]

    def _age(key: str) -> float | None:
        checked = cache.get(key)
        if not checked:
            return None
        try:
            return (now - datetime.fromisoformat(str(checked))).total_seconds()
        except Exception:  # noqa: BLE001
            return None

    def _il_is_fresh(age: float | None, err: object) -> bool:
        if age is None:
            return False
        return age <= (_IL_FAIL_TTL if err else _GP_CACHE_TTL)

    gp_age = _age("gp_checked_at")
    il_age = _age("il_checked_at")
    gp_fresh = gp_age is not None and gp_age <= _GP_CACHE_TTL and cache.get("balance") is not None
    il_fresh = _il_is_fresh(il_age, cache.get("il_error"))
    if gp_fresh and il_fresh:
        return {
            "gp": cache.get("balance"),
            "image_limit": cache.get("image_limit"),
            "image_limits": cache.get("image_limit"),
            "checked_at": cache.get("gp_checked_at") or cache.get("checked_at"),
            "error": cache.get("error"),
            "cached": True,
        }
    lock = _get_gp_lock()
    if lock.locked():
        return {
            "gp": cache.get("balance"),
            "image_limit": cache.get("image_limit"),
            "image_limits": cache.get("image_limit"),
            "checked_at": cache.get("gp_checked_at") or cache.get("checked_at"),
            "error": cache.get("error"),
            "cached": True,
            "refreshing": True,
        }
    async with lock:
        cache = app_state.extra.get("gp_cache", {}) if isinstance(app_state.extra.get("gp_cache"), dict) else {}
        if cache.get("gp_checked_at") is None and cache.get("checked_at"):
            cache["gp_checked_at"] = cache["checked_at"]
            cache["il_checked_at"] = cache.get("il_checked_at") or cache["checked_at"]
        gp_age = _age("gp_checked_at")
        il_age = _age("il_checked_at")
        gp_fresh = gp_age is not None and gp_age <= _GP_CACHE_TTL and cache.get("balance") is not None
        il_fresh = _il_is_fresh(il_age, cache.get("il_error"))
        if gp_fresh and il_fresh:
            return {
                "gp": cache["balance"],
                "image_limit": cache.get("image_limit"),
                "image_limits": cache.get("image_limit"),
                "checked_at": cache.get("gp_checked_at"),
                "error": cache.get("error"),
                "cached": True,
            }
        balance = cache.get("balance")
        image_limit = cache.get("image_limit")
        error = cache.get("error")
        gp_checked_at = cache.get("gp_checked_at")
        il_checked_at = cache.get("il_checked_at")
        il_error = bool(cache.get("il_error"))
        stamp = datetime.now(UTC).isoformat()

        async def _load_image_limit(c: object) -> None:
            nonlocal image_limit, il_checked_at, il_error
            try:
                fetched = await c.fetch_image_limits()
            except Exception:  # noqa: BLE001
                il_checked_at = stamp
                il_error = True
                return
            il_checked_at = stamp
            if fetched:
                image_limit = fetched
                il_error = False
            else:
                il_error = True

        try:
            client = app_state.eh_client
            if client is None:
                from ...services.eh_client import EhClient

                async with EhClient(settings, max_concurrency=settings.exhentai_max_concurrency) as tmp:
                    if not gp_fresh:
                        balance = await tmp.fetch_gp_balance()
                        gp_checked_at = stamp
                    if not il_fresh:
                        await _load_image_limit(tmp)
            else:
                if not gp_fresh:
                    balance = await client.fetch_gp_balance()
                    gp_checked_at = stamp
                if not il_fresh:
                    await _load_image_limit(client)
            error = None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "quota check failed",
                extra=log_extra(
                    error=type(exc).__name__,
                    detail=mask_sensitive(str(exc))[:200],
                ),
            )
            error = _QUOTA_ERROR_MESSAGE
            if not gp_fresh:
                balance = cache.get("balance")
        new_cache = {
            "balance": balance,
            "image_limit": image_limit,
            "gp_checked_at": gp_checked_at,
            "il_checked_at": il_checked_at,
            "il_error": il_error,
            "checked_at": gp_checked_at or il_checked_at or stamp,
            "error": error,
        }
        app_state.extra["gp_cache"] = new_cache
        return {
            "gp": balance,
            "image_limit": image_limit,
            "image_limits": image_limit,
            "checked_at": new_cache["checked_at"],
            "error": error,
            "cached": False,
        }
