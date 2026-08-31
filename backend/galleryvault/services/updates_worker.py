"""Background worker loops for detecting, running, and finalizing gallery updates."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..app.dependencies import db_error
from ..app.state import app_state
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.models import FavoriteItem, Gallery
from ..db.repository import DownloadRepository, GalleryUpdatesRepository
from ..logging import log_extra
from .deletion import delete_galleries_local

logger = logging.getLogger(__name__)

_UPDATE_TITLE_VARIANTS = (
    "中国翻訳", "中文翻譯", "中文", "english", "dl版", "無修正", "デジタル版",
    "デジタル", "digital", "colorized", "color", "スキャナー", "修正版",
    "未修正", "翻訳版", "アニメ", "実写", "総集編",
)


def normalize_update_title(title: str) -> str:
    """Normalize a gallery title for re-upload matching."""
    text = title.strip().lower()
    text = re.sub(r"^\d+-", "", text)
    variants = "|".join(_UPDATE_TITLE_VARIANTS)
    text = re.sub(rf"\[(?:{variants})\]", "", text)
    text = re.sub(r"[\s\[\](){}“”\"'`,.。、:：;；!！?？\-—_/\\|·・〜～]+", "", text)
    return text


def record_gallery_update_log(results: list[dict[str, Any]]) -> None:
    now = datetime.now(UTC).isoformat()
    deleted = sum(1 for r in results if r.get("db_removed"))
    failed = [p for r in results for p in r.get("failed_paths", [])]
    reason = f"updated to new version, removed old copy {deleted}/{len(results)}"
    if failed:
        reason += f", delete failed {len(failed)}: {', '.join(str(p) for p in failed[:3])}"
        if len(failed) > 3:
            reason += f" (+{len(failed) - 3} more)"
    tm = app_state.task_manager
    if tm:
        tm.record_task(
            "gallery-update",
            now,
            now,
            "failed" if failed else "success",
            reason=reason,
            done=deleted,
            total=len(results),
        )
        asyncio.create_task(tm.persist_history())


async def finalize_gallery_update(row: Any) -> None:
    from ..app import main
    session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
    if session_cm is None:
        return
    repo_cls = getattr(main, "GalleryUpdatesRepository", GalleryUpdatesRepository)
    try:
        results = []
        async with session_cm() as session, session.begin():
            gallery = await session.get(Gallery, row.gallery_id)
            if gallery is None:
                return
            results = await delete_galleries_local(
                session, [gallery], delete_files=True, delete_all_copies=False
            )
        record_gallery_update_log(results)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "gallery update finalize failed",
            extra=log_extra(update_id=row.id, error=type(exc).__name__),
        )
        try:
            async with session_cm() as session, session.begin():
                await repo_cls(session).mark_failed(row.id, str(exc))
        except Exception as exc2:  # noqa: BLE001
            logger.warning(
                "could not record gallery update failure",
                extra=log_extra(update_id=row.id, error=type(exc2).__name__),
            )


async def detect_gallery_updates() -> None:
    from ..app import main
    session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
    if session_cm is None:
        return
    repo_cls = getattr(main, "GalleryUpdatesRepository", GalleryUpdatesRepository)
    tm = getattr(main, "default_task_manager", None) or app_state.task_manager
    gallery_updates_state = getattr(main, "gallery_updates_state", None) or (tm.gallery_updates_state if tm else {})

    if bool(gallery_updates_state.get("detecting")):
        return
    gallery_updates_state.update({"detecting": True, "last_error": None})
    detected: list[dict[str, Any]] = []
    found = 0
    try:
        async with session_cm() as session:
            fav_rows = await session.execute(
                select(FavoriteItem.gid, FavoriteItem.token, FavoriteItem.title, FavoriteItem.favcat)
            )
            fav_gids: set[int] = set()
            by_title: dict[str, tuple[int, str, int]] = {}
            for gid, token, title, favcat in fav_rows:
                gid = int(gid)
                fav_gids.add(gid)
                nt = normalize_update_title(title or "")
                if nt and nt not in by_title:
                    by_title[nt] = (gid, str(token), int(favcat))
            repo = repo_cls(session)
            tracked = await repo.tracked_gallery_ids()
            page = 1
            while True:
                rows = await session.execute(
                    select(Gallery.id, Gallery.gid, Gallery.title)
                    .where(Gallery.expunged.is_(False))
                    .order_by(Gallery.id)
                    .offset((page - 1) * 500)
                    .limit(500)
                )
                batch = rows.all()
                if not batch:
                    break
                for gallery_id, gid, title in batch:
                    if gallery_id in tracked or gid is None or gid in fav_gids:
                        continue
                    nt = normalize_update_title(title or "")
                    match = by_title.get(nt)
                    if match:
                        new_gid, new_token, favcat = match
                        detected.append(
                            {
                                "gallery_id": int(gallery_id),
                                "old_gid": int(gid),
                                "new_gid": new_gid,
                                "new_token": new_token,
                                "title": title,
                                "favcat": favcat,
                            }
                        )
                if len(batch) < 500:
                    break
                page += 1
        if detected:
            async with session_cm() as session, session.begin():
                found = await repo_cls(session).detect_many(
                    detected, known_gallery_ids=tracked
                )
        gallery_updates_state.update(
            {"found": found, "last_detected_at": datetime.now(UTC).isoformat()}
        )
        if found:
            logger.info(
                "gallery update scan found new-version candidates",
                extra=log_extra(found=found),
            )
    except Exception as exc:  # noqa: BLE001
        gallery_updates_state["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "gallery update detection failed", extra=log_extra(error=type(exc).__name__)
        )
    finally:
        gallery_updates_state["detecting"] = False
        gallery_updates_state["last_run"] = datetime.now(UTC).isoformat()


async def run_gallery_updates(
    ids: list[int], *, archive: bool = False, quality: str | None = None
) -> dict[str, int]:
    from ..app import main
    session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
    if session_cm is None:
        return {"started": 0, "skipped": len(ids)}
    repo_cls = getattr(main, "GalleryUpdatesRepository", GalleryUpdatesRepository)
    dl_repo_cls = getattr(main, "DownloadRepository", DownloadRepository)

    started = 0
    skipped = 0
    mode = "archive" if archive else "favorite"
    try:
        async with session_cm() as session, session.begin():
            repo = repo_cls(session)
            for update_id in list(dict.fromkeys(ids)):
                row = await repo.get(update_id)
                if row is None or row.status != "pending":
                    skipped += 1
                    continue
                task = await dl_repo_cls(session).create(
                    row.new_gid,
                    row.new_token,
                    row.title or str(row.new_gid),
                    mode,
                    quality=quality,
                )
                if task is None:
                    skipped += 1
                    continue
                await repo.mark_downloading(update_id, task.id)
                started += 1
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"started": started, "skipped": skipped}


async def gallery_updates_finalize_loop() -> None:
    from ..app import main
    while True:
        sleep_fn = getattr(getattr(main, "asyncio", None), "sleep", asyncio.sleep)
        await sleep_fn(30)
        session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
        if session_cm is None:
            continue
        repo_cls = getattr(main, "GalleryUpdatesRepository", GalleryUpdatesRepository)
        try:
            async with session_cm() as session:
                updating = await repo_cls(session).downloading()
            for row in updating:
                if row.download_task_id is None:
                    continue
                async with session_cm() as session:
                    task = await session.get(DownloadTaskModel, row.download_task_id)
                if task is None:
                    async with session_cm() as session, session.begin():
                        await repo_cls(session).mark_failed(
                            row.id, "download task removed"
                        )
                    continue
                if task.status == "success":
                    await finalize_gallery_update(row)
                elif task.status in {"failed", "cancelled"}:
                    async with session_cm() as session, session.begin():
                        await repo_cls(session).mark_failed(
                            row.id, task.error_message
                        )
        except Exception as exc:
            if type(exc).__name__ == "RuntimeError" and "stop-loop" in str(exc):
                raise
            logger.warning(
                "gallery update finalize failed", extra=log_extra(error=type(exc).__name__)
            )
            await sleep_fn(60)
