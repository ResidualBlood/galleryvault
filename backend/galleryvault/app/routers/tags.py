"""
Tag search and translation endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from galleryvault.app import main
from galleryvault.db.repository import GalleryRepository
from galleryvault.services.tag_translation import (
    search_zh,
    translated_tag,
    translation_entry_count,
)

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
    # Chinese autocomplete: reverse-search the translation table.
    if zh and q and q.strip():
        matched = search_zh(q, limit=page_size)
        # Attach real usage counts for the matched (namespace, name) pairs.
        async with main._settings_session() as session:
            repo = GalleryRepository(session)
            rows = await repo.tag_counts_for([(ns, name) for ns, name, _ in matched])
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
    async with main._settings_session() as session:
        repo = GalleryRepository(session)
        total, rows = await repo.search_tags(q, page, page_size, namespace)
        facets = await main._tag_facets_cached() if not namespace else []
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
            {"namespace": namespace, "name": name, "display": translated_tag(namespace, name)[1], "usage_count": count}
            for namespace, name, count in rows
        ],
    }


@router.get("/api/tags/search/status")
async def tag_translation_status() -> dict[str, object]:
    return {
        **main.translation_state,
        "entries": translation_entry_count(),
        "source": main._TRANSLATION_RELEASE_API,
        "interval_minutes": main._settings().tag_translation_update_interval_minutes,
    }


@router.post("/api/tags/search/reload", status_code=202)
async def tag_translation_reload() -> dict[str, object]:
    ok = await main._translation_update_once()
    return {"accepted": True, "ok": ok, "last_error": main.translation_state["last_error"]}


@router.post("/api/telegram/test")
async def telegram_test() -> dict[str, object]:
    notifier = main.app.state.telegram
    if notifier is None or not main._settings().telegram_bot_token:
        raise HTTPException(status_code=422, detail="Telegram bot token is not configured")
    targets = main._settings().telegram_chat_ids
    if not targets:
        raise HTTPException(status_code=422, detail="No Telegram chat IDs configured")
    results: dict[str, object] = {}
    for chat_id in targets:
        results[str(chat_id)] = await notifier.send_message(
            "GalleryVault: Telegram 连接测试 OK", chat_id=chat_id
        )
    ok = all(results.values())
    return {"ok": ok, "results": results}

