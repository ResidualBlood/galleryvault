"""Background worker loop for tag synchronization and translation database updater."""

from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ..app.state import app_state
from ..config import get_settings
from ..db.repository import BackgroundJobsRepository, GalleryRepository
from ..logging import log_extra
from .eh_client import EhClientError, GalleryGoneError
from .tag_sync import TagSyncService
from .tag_translation import load_translations, merge_translation_data

logger = logging.getLogger(__name__)

JOB_TAG_SYNC = BackgroundJobsRepository.JOB_TAG_SYNC
_TRANSLATION_REPO = "EhTagTranslation/Database"
_TRANSLATION_RELEASE_API = f"https://api.github.com/repos/{_TRANSLATION_REPO}/releases/latest"

tag_sync_holds: dict[int, int] = {}
_tag_facets_cache: dict[str, Any] = {"ts": 0.0, "facets": []}
_TAG_FACETS_TTL = 120.0


async def tag_facets_cached() -> list[tuple[str, int]]:
    """Per-namespace tag counts, cached."""
    now = _time.time()
    if now - float(_tag_facets_cache.get("ts", 0.0)) < _TAG_FACETS_TTL:
        return list(_tag_facets_cache.get("facets", []))
    if not app_state.session_factory:
        return []
    async with app_state.session_factory() as session:
        facets = await GalleryRepository(session).tag_facets()
    _tag_facets_cache["ts"] = now
    _tag_facets_cache["facets"] = facets
    return facets


async def jobs_count(job_type: str) -> int:
    if not app_state.session_factory:
        return 0
    try:
        async with app_state.session_factory() as session:
            return await BackgroundJobsRepository(session).count(job_type)
    except Exception:  # noqa: BLE001
        return 0


async def claim_jobs(
    job_type: str, limit: int = 1, *, lease_seconds: int = 600
) -> list[tuple[int, int]]:
    if not app_state.session_factory:
        return []
    try:
        async with app_state.session_factory() as session, session.begin():
            return await BackgroundJobsRepository(session).claim(
                job_type, limit, lease_seconds=lease_seconds
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "background job claim failed",
            extra=log_extra(job_type=job_type, error=type(exc).__name__),
        )
        return []


async def complete_job(job_type: str, gallery_id: int) -> None:
    if not app_state.session_factory:
        return
    try:
        async with app_state.session_factory() as session, session.begin():
            await BackgroundJobsRepository(session).complete(job_type, gallery_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "background job completion failed",
            extra=log_extra(job_type=job_type, gallery_id=gallery_id, error=type(exc).__name__),
        )


async def requeue_job(
    job_type: str, gallery_id: int, *, next_attempt_at: datetime | None = None
) -> None:
    if not app_state.session_factory:
        return
    try:
        async with app_state.session_factory() as session, session.begin():
            await BackgroundJobsRepository(session).requeue(
                job_type, gallery_id, next_attempt_at=next_attempt_at
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "background job requeue failed",
            extra=log_extra(job_type=job_type, gallery_id=gallery_id, error=type(exc).__name__),
        )


async def enqueue_job(job_type: str, gallery_id: int) -> bool:
    if not app_state.session_factory:
        return False
    try:
        async with app_state.session_factory() as session, session.begin():
            return await BackgroundJobsRepository(session).enqueue(job_type, gallery_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "background job enqueue failed",
            extra=log_extra(job_type=job_type, gallery_id=gallery_id, error=type(exc).__name__),
        )
        return False


async def enqueue_tag_sync(gallery_ids: list[int]) -> int:
    """Queue gallery ids for background tag synchronization, de-duplicating."""
    if not app_state.session_factory:
        return 0
    added = 0
    tm = app_state.task_manager
    tag_sync_state = tm.tag_sync_state if tm else {}
    for start in range(0, len(gallery_ids), 500):
        chunk = gallery_ids[start : start + 500]
        async with app_state.session_factory() as session, session.begin():
            added += await BackgroundJobsRepository(session).enqueue_many(JOB_TAG_SYNC, chunk)
    if added:
        current = int(tag_sync_state.get("total") or 0)
        tag_sync_state["total"] = current + added
        tag_sync_state["queued"] = await jobs_count(JOB_TAG_SYNC)
    return added


async def translation_download_url(client: httpx.AsyncClient) -> str:
    response = await client.get(
        _TRANSLATION_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "GalleryVault"},
    )
    response.raise_for_status()
    assets = response.json().get("assets", [])
    for asset in assets:
        if asset.get("name") == "db.text.json":
            return asset["browser_download_url"]
    raise RuntimeError("db.text.json asset not found in the latest release")


async def fetch_translation_db() -> Any:
    settings = app_state.settings or get_settings()
    proxy = settings.socks5_proxy or settings.http_proxy
    async with httpx.AsyncClient(timeout=30, proxy=proxy, follow_redirects=True) as client:
        url = await translation_download_url(client)
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def translation_update_once() -> bool:
    tm = app_state.task_manager
    translation_state = tm.translation_state if tm else {}
    if not translation_state.get("running"):
        translation_state["started_at"] = datetime.now(UTC).isoformat()
        translation_state["history_recorded"] = False
    translation_state["running"] = True
    ok = False
    try:
        data = await fetch_translation_db()

        def _apply_translations() -> int:
            load_translations(reset=True)
            return merge_translation_data(data)

        entries = await asyncio.to_thread(_apply_translations)
        translation_state["entries"] = entries
        translation_state["last"] = datetime.now(UTC).isoformat()
        translation_state["last_error"] = None
        logger.info("tag translations updated", extra=log_extra(entries=entries))
        ok = True
    except Exception as exc:  # noqa: BLE001
        translation_state["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "tag translation update failed", extra=log_extra(error=type(exc).__name__)
        )
    finally:
        translation_state["running"] = False
        translation_state["completed_at"] = datetime.now(UTC).isoformat()
        if tm and not translation_state.get("history_recorded"):
            translation_state["history_recorded"] = True
            tm.record_task(
                "translation",
                translation_state.get("started_at"),
                translation_state["completed_at"],
                "success" if ok else "failed",
                reason=translation_state.get("last_error") or "",
                done=int(translation_state.get("entries") or 0),
                total=0,
            )
            from ..app.dependencies import spawn_task

            spawn_task(tm.persist_history(), "persist task history")
    return ok


async def translation_update_loop() -> None:
    tm = app_state.task_manager
    translation_state = tm.translation_state if tm else {}
    while True:
        settings = app_state.settings or get_settings()
        minutes = int(settings.tag_translation_update_interval_minutes)
        if minutes <= 0:
            await asyncio.sleep(3600)
            continue
        try:
            await translation_update_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("tag translation loop error", extra={"error": str(exc)})
            translation_state["last_error"] = str(exc)
        deadline = asyncio.get_event_loop().time() + minutes * 60
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(min(1, max(0.1, deadline - asyncio.get_event_loop().time())))


def _is_public_site(url: str | None) -> bool:
    if not url:
        return True
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return "e-hentai.org" in host or not host


async def _confirm_gone(gid: int, token: str | None) -> bool | None:
    """Double-check a ``GalleryGoneError`` via gdata (``expunged``).

    Returns ``True`` if gdata confirms the gallery is gone (expunged or
    missing with a valid token), ``False`` if gdata says it still exists,
    ``None`` if the check itself failed (network) — caller should requeue.
    """
    if gid is None or not token:
        return None
    client = app_state.eh_client
    if client is None or not hasattr(client, "fetch_gmetadata"):
        return None
    try:
        result = await client.fetch_gmetadata([(int(gid), str(token))])
    except Exception:  # noqa: BLE001 - transient, do not mark deleted
        return None
    entry = result.get(int(gid))
    if entry is None:
        # gdata did not return the gid — token mismatch or API hiccup, treat
        # as not confirmed to avoid false deleted.
        return None
    return bool(entry.get("expunged"))


async def category_refresh_once() -> int:
    """Backfill the 大分类 for galleries stuck in ``other``."""
    tm = app_state.task_manager
    state = tm.tag_sync_state if tm else {}
    if state.get("category_refresh_running"):
        return 0
    state["category_refresh_running"] = True
    refreshed = 0
    try:
        if not app_state.session_factory or not app_state.eh_client:
            return 0
        ids: list[int] = []
        async with app_state.session_factory() as session:
            last_id = 0
            while True:
                batch = await GalleryRepository(session).pending_category_refresh_ids(500, last_id)
                if not batch:
                    break
                ids.extend(batch)
                last_id = batch[-1]
        for gallery_id in ids:
            try:
                async with app_state.session_factory() as session, session.begin():
                    await TagSyncService(
                        app_state.eh_client, GalleryRepository(session)
                    ).refresh_category(gallery_id)
                refreshed += 1
            except GalleryGoneError:
                # Confirm via gdata before reclassifying — an empty/challenge
                # HTML page must not mass-mark live galleries as deleted.
                gid_token: tuple[int | None, str | None] = (None, None)
                try:
                    async with app_state.session_factory() as session:
                        g = await GalleryRepository(session).get_for_tag_sync(gallery_id)
                        if g is not None:
                            gid_token = (g.gid, g.token)
                except Exception:  # noqa: BLE001
                    gid_token = (None, None)
                confirmed = None
                if gid_token[0] is not None:
                    confirmed = await _confirm_gone(int(gid_token[0]), gid_token[1])
                if confirmed is False:
                    # gdata says still present — transient HTML gone, requeue
                    logger.warning(
                        "category refresh gone not confirmed by gdata, requeueing",
                        extra=log_extra(gallery_id=gallery_id, gid=gid_token[0]),
                    )
                    continue
                if confirmed is None:
                    # gdata check failed or inconclusive — do not mark deleted,
                    # let the next backfill attempt handle it
                    logger.warning(
                        "category refresh gdata check inconclusive, skipping deleted mark",
                        extra=log_extra(gallery_id=gallery_id, gid=gid_token[0]),
                    )
                    continue
                settings = app_state.settings or get_settings()
                if _is_public_site(settings.exhentai_base_url):
                    try:
                        async with app_state.session_factory() as session, session.begin():
                            await GalleryRepository(session).mark_tag_not_visible(gallery_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "could not mark gallery not-visible during category refresh",
                            extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                        )
                else:
                    try:
                        async with app_state.session_factory() as session, session.begin():
                            await GalleryRepository(session).mark_tag_synced(gallery_id, category="deleted")
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "could not mark deleted gallery during category refresh",
                            extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                        )
            except EhClientError:
                logger.warning(
                    "category refresh failed",
                    extra=log_extra(gallery_id=gallery_id, error="EhClientError"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "category refresh error",
                    extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                )
            if ids and gallery_id != ids[-1]:
                await asyncio.sleep(0.3)
        state["category_refreshed"] = int(state.get("category_refreshed", 0)) + refreshed
    finally:
        state["category_refresh_running"] = False
    return refreshed


async def tag_sync_worker_loop() -> None:
    if not app_state.session_factory:
        return
    logger.info("tag sync worker started")
    try:
        async with app_state.session_factory() as session, session.begin():
            await BackgroundJobsRepository(session).mark_stale()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tag sync stale-recovery failed", extra=log_extra(error=type(exc).__name__)
        )
    tm = app_state.task_manager
    tag_sync_state = tm.tag_sync_state if tm else {}
    favorites_check_state = tm.favorites_check_state if tm else {}
    try:
        async with app_state.session_factory() as session:
            last_id = 0
            seeded = 0
            while True:
                ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
                if not ids:
                    break
                await enqueue_tag_sync(ids)
                seeded += len(ids)
                last_id = ids[-1]
            tag_sync_state["total"] = seeded + tag_sync_state.get("processed", 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tag sync seeding failed", extra=log_extra(error=type(exc).__name__))
    tag_sync_state["queued"] = await jobs_count(JOB_TAG_SYNC)
    tag_sync_state["running"] = True
    tag_sync_state["completed_at"] = None

    settings = app_state.settings or get_settings()
    concurrency = max(1, min(int(settings.tag_sync_concurrency), 8))
    semaphore = asyncio.Semaphore(concurrency)
    base_interval = max(0.1, float(settings.tag_sync_interval_seconds))
    interval = [base_interval]
    success_streak = [0]
    last_activity = [_time.monotonic()]
    MAX_BACKOFF = 60.0
    MAX_ATTEMPTS = 8
    MAX_TAG_SYNC_HOLDS = 120
    _TAG_SYNC_IDLE_SECONDS = 5.0

    async def _sync_one(gallery_id: int, attempts: int) -> bool | None:
        try:
            if favorites_check_state.get("running"):
                holds = tag_sync_holds.get(gallery_id, 0)
                cached_tags = False
                if holds < MAX_TAG_SYNC_HOLDS:
                    async with app_state.session_factory() as session:
                        repo = GalleryRepository(session)
                        gallery = await repo.get_for_tag_sync(gallery_id)
                        if gallery is not None and gallery.gid is not None:
                            cached = await repo.metadata_for_gid(gallery.gid)
                            cached_tags = bool(cached and cached.get("tags"))
                    if not cached_tags:
                        tag_sync_holds[gallery_id] = holds + 1
                        await requeue_job(
                            JOB_TAG_SYNC,
                            gallery_id,
                            next_attempt_at=datetime.now(UTC) + timedelta(seconds=60),
                        )
                        tag_sync_state["queued"] = await jobs_count(JOB_TAG_SYNC)
                        await asyncio.sleep(interval[0])
                        return False
                tag_sync_holds.pop(gallery_id, None)

            async with app_state.session_factory() as session:
                plan = await TagSyncService(
                    app_state.eh_client, GalleryRepository(session)
                ).fetch_plan(gallery_id)

            async with app_state.session_factory() as session, session.begin():
                await TagSyncService(
                    app_state.eh_client, GalleryRepository(session)
                ).apply_plan(gallery_id, plan)

            tag_sync_state["succeeded"] += 1
            await complete_job(JOB_TAG_SYNC, gallery_id)
            success_streak[0] += 1
            if success_streak[0] >= 10 and interval[0] > base_interval:
                interval[0] = max(base_interval, interval[0] / 2)
            return True
        except GalleryGoneError as exc:
            # Confirm via gdata before reclassifying — see category_refresh_once.
            gid_for_confirm: int | None = None
            token_for_confirm: str | None = None
            try:
                async with app_state.session_factory() as session:
                    gr = await GalleryRepository(session).get_for_tag_sync(gallery_id)
                    if gr is not None:
                        gid_for_confirm = gr.gid
                        token_for_confirm = gr.token
            except Exception:  # noqa: BLE001, S110
                pass
            confirmed = None
            if gid_for_confirm is not None:
                confirmed = await _confirm_gone(int(gid_for_confirm), token_for_confirm)
            if confirmed is False:
                # gdata says still alive → transient HTML gone, requeue for retry
                logger.warning(
                    "tag sync gone not confirmed by gdata, requeueing",
                    extra=log_extra(gallery_id=gallery_id, gid=gid_for_confirm),
                )
                interval[0] = min(MAX_BACKOFF, interval[0] * 2)
                success_streak[0] = 0
                if attempts < MAX_ATTEMPTS:
                    tag_sync_state["retries"] += 1
                    await requeue_job(JOB_TAG_SYNC, gallery_id)
                    return
                # fall through to mark synced without deleted after retries
            elif confirmed is None and gid_for_confirm is not None:
                logger.warning(
                    "tag sync gdata check inconclusive, requeueing",
                    extra=log_extra(gallery_id=gallery_id, gid=gid_for_confirm),
                )
                interval[0] = min(MAX_BACKOFF, interval[0] * 2)
                success_streak[0] = 0
                if attempts < MAX_ATTEMPTS:
                    tag_sync_state["retries"] += 1
                    await requeue_job(JOB_TAG_SYNC, gallery_id)
                    return
            else:
                if _is_public_site(settings.exhentai_base_url):
                    try:
                        async with app_state.session_factory() as session, session.begin():
                            await GalleryRepository(session).mark_tag_not_visible(gallery_id)
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "could not mark gallery not-visible on public mirror",
                            extra=log_extra(gallery_id=gallery_id),
                        )
                else:
                    try:
                        async with app_state.session_factory() as session, session.begin():
                            await GalleryRepository(session).mark_tag_synced(
                                gallery_id, category="deleted"
                            )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "could not mark deleted gallery synced",
                            extra=log_extra(gallery_id=gallery_id),
                        )
                await complete_job(JOB_TAG_SYNC, gallery_id)
                tag_sync_state["failed"] += 1
                logger.warning(
                    "tag sync skipped (gallery gone)",
                    extra=log_extra(gallery_id=gallery_id, error=str(exc)),
                )
                return
            # Requeued case: treat as transient failure without marking deleted
            try:
                async with app_state.session_factory() as session, session.begin():
                    await GalleryRepository(session).mark_tag_synced(gallery_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "could not mark requeued gallery synced",
                    extra=log_extra(gallery_id=gallery_id),
                )
            await complete_job(JOB_TAG_SYNC, gallery_id)
            tag_sync_state["failed"] += 1
            logger.warning(
                "tag sync requeued after unconfirmed gone",
                extra=log_extra(gallery_id=gallery_id, error=str(exc)),
            )
        except Exception as exc:  # noqa: BLE001
            tag_sync_state["failed"] += 1
            tag_sync_state["last_error"] = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "tag sync failed",
                extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
            )
            if isinstance(exc, (EhClientError, asyncio.TimeoutError)):
                interval[0] = min(MAX_BACKOFF, interval[0] * 2)
                success_streak[0] = 0
                if attempts < MAX_ATTEMPTS:
                    tag_sync_state["retries"] += 1
                    await requeue_job(JOB_TAG_SYNC, gallery_id)
                    return
            try:
                async with app_state.session_factory() as session, session.begin():
                    await GalleryRepository(session).mark_tag_synced(gallery_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "could not mark failed gallery synced",
                    extra=log_extra(gallery_id=gallery_id),
                )
            await complete_job(JOB_TAG_SYNC, gallery_id)

    async def _worker() -> None:
        while True:
            if tm and tm.is_cancelled("tag-sync"):
                break
            claimed = await claim_jobs(JOB_TAG_SYNC, 1)
            if not claimed:
                if (
                    tag_sync_state.get("running")
                    and _time.monotonic() - last_activity[0] >= _TAG_SYNC_IDLE_SECONDS
                ):
                    tag_sync_state["running"] = False
                    tag_sync_state["completed_at"] = datetime.now(UTC).isoformat()
                    if tm and not tag_sync_state.get("history_recorded"):
                        tag_sync_state["history_recorded"] = True
                        tm.record_task(
                            "tag-sync",
                            tag_sync_state.get("started_at"),
                            tag_sync_state["completed_at"],
                            "success" if not tag_sync_state.get("last_error") else "failed",
                            reason=tag_sync_state.get("last_error") or "",
                            done=int(tag_sync_state.get("processed") or 0),
                            total=int(tag_sync_state.get("total") or 0),
                        )
                        from ..app.dependencies import spawn_task

                        spawn_task(tm.persist_history(), "persist task history")
                await asyncio.sleep(1)
                continue

            last_activity[0] = _time.monotonic()
            if not tag_sync_state.get("running"):
                tag_sync_state["running"] = True
                tag_sync_state["started_at"] = datetime.now(UTC).isoformat()
                tag_sync_state["completed_at"] = None
                tag_sync_state["history_recorded"] = False

            gallery_id, attempts = claimed[0]
            tag_sync_state["queued"] = await jobs_count(JOB_TAG_SYNC)
            async with semaphore:
                await _sync_one(gallery_id, attempts)
                tag_sync_state["processed"] = (
                    tag_sync_state.get("succeeded", 0) + tag_sync_state.get("failed", 0)
                )
                tag_sync_state["queued"] = await jobs_count(JOB_TAG_SYNC)
                await asyncio.sleep(interval[0])

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        pass
