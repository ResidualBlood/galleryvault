"""Detect new gallery versions and queue their downloads/finalize."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...app.dependencies import db_error
from ...app.state import app_state
from ...db.models import FavoriteItem, Gallery
from ...db.repository import DownloadRepository, GalleryUpdatesRepository
from ...logging import bind_log_context, log_extra
from ..download_worker import notify_new_task
from .updates_finalize import finalize_gallery_update
from .updates_normalize import normalize_update_title

# Same logger name as the legacy module (CR1).
logger = logging.getLogger("galleryvault.services.updates_worker")


async def detect_gallery_updates() -> None:
    session_cm = app_state.session_factory
    if session_cm is None:
        return
    from ...app.dependencies import get_task_manager

    tm = get_task_manager()
    if bool(tm.gallery_updates_state.get("detecting")):
        return
    repo_cls = GalleryUpdatesRepository
    with bind_log_context(worker="updates"):
        async with tm.track_task("gallery-updates") as tracker:
            detected: list[dict[str, Any]] = []
            found = 0
            to_insert: list[dict[str, Any]] = []
            to_finalize: list[Any] = []
            to_attach: dict[int, int] = {}
            try:
                fav_gids: set[int] = set()
                by_title: dict[str, tuple[int, str, int]] = {}
                async with session_cm() as session:
                    fav_rows = (
                        await session.execute(
                            select(FavoriteItem.gid, FavoriteItem.token, FavoriteItem.title, FavoriteItem.favcat)
                        )
                    ).all()
                    repo = repo_cls(session)
                    tracking = await repo.tracking_by_gallery_id()

                for gid, token, title, favcat in fav_rows:
                    gid = int(gid)
                    fav_gids.add(gid)
                    nt = normalize_update_title(title or "")
                    if nt and nt not in by_title:
                        by_title[nt] = (gid, str(token), int(favcat))
                    if "|" in (title or ""):
                        for part in title.split("|"):
                            p_nt = normalize_update_title(part)
                            if p_nt and p_nt not in by_title:
                                by_title[p_nt] = (gid, str(token), int(favcat))

                page = 1
                while True:
                    async with session_cm() as session:
                        rows = await session.execute(
                            select(Gallery.id, Gallery.gid, Gallery.title, Gallery.title_jpn)
                            .where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
                            .order_by(Gallery.id)
                            .offset((page - 1) * 500)
                            .limit(500)
                        )
                        batch = rows.all()
                    if not batch:
                        break
                    for gallery_id, gid, title, title_jpn in batch:
                        if gid is None or gid in fav_gids:
                            continue
                        tracked_row = tracking.get(int(gallery_id))
                        if tracked_row is not None and getattr(tracked_row, "status", None) == "ignored":
                            continue
                        nt = normalize_update_title(title or "")
                        match = by_title.get(nt)
                        if not match and title_jpn:
                            match = by_title.get(normalize_update_title(title_jpn))
                        if not match and "|" in (title or ""):
                            for part in title.split("|"):
                                match = by_title.get(normalize_update_title(part))
                                if match:
                                    break
                        if match and match[0] != int(gid):
                            new_gid, new_token, favcat = match
                            detected.append(
                                {
                                    "gallery_id": int(gallery_id),
                                    "old_gid": int(gid),
                                    "new_gid": new_gid,
                                    "new_token": new_token,
                                    "title": title,
                                    "favcat": favcat,
                                    "existing_id": getattr(tracked_row, "id", None),
                                    "existing_status": getattr(tracked_row, "status", None),
                                }
                            )
                    if len(batch) < 500:
                        break
                    page += 1

                local_new: set[int] = set()
                active_tasks: dict[int, int] = {}
                chained: set[tuple[int, int]] = set()
                matches_per_new_gid: Counter[int] = Counter(
                    int(e["new_gid"]) for e in detected
                )
                if detected:
                    new_gids = [e["new_gid"] for e in detected]
                    async with session_cm() as session:
                        repo = repo_cls(session)
                        local_new = await repo.local_new_gids(new_gids)
                        active_tasks = await repo.active_task_ids_for_gids(new_gids)
                    needs_chain = any(
                        int(e["new_gid"]) in local_new
                        or matches_per_new_gid[int(e["new_gid"])] > 1
                        for e in detected
                    )
                    if needs_chain:
                        pairs = list(
                            {(int(e["old_gid"]), int(e["new_gid"])) for e in detected}
                        )
                        async with session_cm() as session:
                            chained = await repo_cls(
                                session
                            ).replacement_chain_pairs(pairs)
                to_park: list[tuple[int, str]] = []
                for entry in detected:
                    status = entry.get("existing_status")
                    new_gid = int(entry["new_gid"])
                    pair = (int(entry["old_gid"]), new_gid)
                    ambiguous_count = matches_per_new_gid[new_gid]
                    if pair not in chained and ambiguous_count > 1:
                        # Title matching only: one re-upload matched several
                        # local galleries and no official replace link tells
                        # which ones it supersedes.  Never auto-delete; the
                        # user picks in the updates page.
                        message = f"ambiguous: {ambiguous_count} local galleries match"
                        if status in {"pending", "failed"} and entry.get("existing_id") is not None:
                            to_park.append((int(entry["existing_id"]), message))
                        if status is None:
                            to_insert.append(
                                {
                                    "gallery_id": entry["gallery_id"],
                                    "old_gid": entry["old_gid"],
                                    "new_gid": new_gid,
                                    "new_token": entry["new_token"],
                                    "title": entry["title"],
                                    "favcat": entry["favcat"],
                                    "error_message": message,
                                }
                            )
                        continue
                    if new_gid in local_new and pair in chained:
                        to_finalize.append(
                            SimpleNamespace(
                                id=entry.get("existing_id"),
                                gallery_id=entry["gallery_id"],
                                new_gid=entry.get("new_gid"),
                            )
                        )
                        continue
                    extra: dict[str, Any] = {}
                    task_id = active_tasks.get(new_gid)
                    if status is None:
                        if task_id:
                            extra["status"] = "downloading"
                            extra["download_task_id"] = task_id
                        to_insert.append(
                            {
                                "gallery_id": entry["gallery_id"],
                                "old_gid": entry["old_gid"],
                                "new_gid": new_gid,
                                "new_token": entry["new_token"],
                                "title": entry["title"],
                                "favcat": entry["favcat"],
                                **extra,
                            }
                        )
                    elif status in {"pending", "failed"} and task_id:
                        to_attach[int(new_gid)] = int(task_id)
                if to_insert:
                    async with session_cm() as session, session.begin():
                        found = await repo_cls(session).detect_many(
                            to_insert, known_gallery_ids=set()
                        )
                if to_park:
                    async with session_cm() as session, session.begin():
                        parked_repo = repo_cls(session)
                        for update_id, message in to_park:
                            await parked_repo.mark_ambiguous([update_id], message)
                if to_attach:
                    async with session_cm() as session, session.begin():
                        attached_repo = repo_cls(session)
                        for gid, task_id in to_attach.items():
                            await attached_repo.attach_download(gid, task_id)
                for ref in to_finalize:
                    await finalize_gallery_update(ref)
                tracker.update(
                    found=found,
                    last_detected_at=datetime.now(UTC).isoformat(),
                )
                if found:
                    logger.info(
                        "gallery update scan found new-version candidates",
                        extra=log_extra(found=found),
                    )
            except Exception as exc:  # noqa: BLE001
                tracker.update(last_error=f"{type(exc).__name__}: {exc}")
                logger.warning(
                    "gallery update detection failed",
                    extra=log_extra(error=type(exc).__name__, message=str(exc)),
                )


async def run_gallery_updates(
    ids: list[int],
    *,
    archive: bool = False,
    quality: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Queue downloads / finalize updates for the given row ids.

    Rows that only matched on the normalized title *and* whose new gid matched
    several local galleries are skipped by default: that N→1 case has no
    official replacement link, so deleting the wrong old copy unattended would
    lose user data.  The updates page passes ``force=True`` only for an explicit
    per-row confirmation.
    """
    session_cm = app_state.session_factory
    if session_cm is None:
        return {"started": 0, "skipped": len(ids), "skipped_ambiguous": 0}
    repo_cls = GalleryUpdatesRepository
    dl_repo_cls = DownloadRepository

    started = 0
    skipped = 0
    skipped_ambiguous = 0
    mode = "archive" if archive else "favorite"
    ready: list[Any] = []
    try:
        async with session_cm() as session, session.begin():
            repo = repo_cls(session)
            pending_rows: list[Any] = []
            for update_id in list(dict.fromkeys(ids)):
                row = await repo.get(update_id)
                if row is None or row.status != "pending":
                    skipped += 1
                    continue
                pending_rows.append(row)
            if pending_rows and not force:
                evidence = await repo.match_evidence(pending_rows)
                guarded: list[Any] = []
                for row in pending_rows:
                    ev = evidence.get(int(row.id), {})
                    if ev.get("match_source") == "title" and ev.get("ambiguous"):
                        skipped += 1
                        skipped_ambiguous += 1
                        continue
                    guarded.append(row)
                pending_rows = guarded
            local = (
                await repo.local_new_gids([row.new_gid for row in pending_rows])
                if pending_rows
                else set()
            )
            for row in pending_rows:
                if row.new_gid in local:
                    ready.append(
                        SimpleNamespace(
                            id=row.id,
                            gallery_id=row.gallery_id,
                            new_gid=row.new_gid,
                        )
                    )
                    started += 1
                    continue
                try:
                    dl_repo = dl_repo_cls(session, on_new_task=notify_new_task)
                except TypeError:
                    # Older test doubles only accept the session argument.
                    dl_repo = dl_repo_cls(session)
                task = await dl_repo.create(
                    row.new_gid,
                    row.new_token,
                    row.title or str(row.new_gid),
                    mode,
                    quality=quality,
                )
                if task is None:
                    skipped += 1
                    continue
                await repo.mark_downloading(row.id, task.id)
                started += 1
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    for ref in ready:
        await finalize_gallery_update(ref)
    return {"started": started, "skipped": skipped, "skipped_ambiguous": skipped_ambiguous}
