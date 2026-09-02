"""Tag search and translation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ...db.repository import GalleryRepository
from ...services import messages
from ...services.tag_sync_worker import (
    _TRANSLATION_RELEASE_API,
    tag_facets_cached,
    translation_update_once,
)
from ...services.tag_translation import (
    search_zh,
    translated_tag,
    translation_entry_count,
)
from ..dependencies import get_current_settings, get_session, get_task_manager
from ..state import app_state

router = APIRouter()


@router.get("/api/tags/search")
async def tag_search(
    q: str | None = None,
    namespace: str | None = None,
    page: int = 1,
    page_size: int = 60,
    zh: bool = False,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    if zh and q and q.strip():
        matched = await run_in_threadpool(search_zh, q, page_size)
        async for session in get_session():
            repo = GalleryRepository(session)
            rows = await repo.tag_counts_for([(ns, name) for ns, name, _ in matched])
            break
        counts = {(ns, name): count for ns, name, count in rows}
        return {
            "total": len(matched),
            "page": 1,
            "page_size": page_size,
            "facets": [],
            "items": [
                {
                    "namespace": ns,
                    "name": name,
                    "display": display,
                    "usage_count": counts.get((ns, name), 0),
                }
                for ns, name, display in matched
            ],
        }
    async for session in get_session():
        repo = GalleryRepository(session)
        total, rows = await repo.search_tags(q, page, page_size, namespace)
        facets = await tag_facets_cached() if not namespace else []
        break
    facet_items = [
        {"namespace": name, "total": count}
        for name, count in sorted(facets, key=lambda x: -x[1])
    ]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "facets": facet_items,
        "items": [
            {
                "namespace": ns,
                "name": name,
                "display": translated_tag(ns, name)[1],
                "usage_count": count,
            }
            for ns, name, count in rows
        ],
    }


@router.get("/api/tags/search/status")
async def tag_translation_status() -> dict[str, object]:
    tm = get_task_manager()
    settings = get_current_settings()
    return {
        **tm.translation_state,
        "entries": translation_entry_count(),
        "source": _TRANSLATION_RELEASE_API,
        "interval_minutes": settings.tag_translation_update_interval_minutes,
    }


@router.post("/api/tags/search/reload", status_code=202)
async def tag_translation_reload() -> dict[str, object]:
    tm = get_task_manager()
    ok = await translation_update_once()
    return {"accepted": True, "ok": ok, "last_error": tm.translation_state.get("last_error")}


@router.post("/api/telegram/test")
async def telegram_test() -> dict[str, object]:
    notifier = app_state.telegram
    settings = get_current_settings()
    if notifier is None or not settings.telegram_bot_token:
        raise HTTPException(status_code=422, detail="Telegram bot token is not configured")
    targets = settings.telegram_chat_ids
    if not targets:
        raise HTTPException(status_code=422, detail="No Telegram chat IDs configured")
    results: dict[str, object] = {}
    message = messages.test_message(settings.telegram_notify_lang)
    for chat_id in targets:
        results[str(chat_id)] = await notifier.send_message(message, chat_id=chat_id)
    ok = all(results.values())
    return {"ok": ok, "results": results}
