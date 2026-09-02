"""Background worker loops for detecting, running, and finalizing gallery updates."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..app.dependencies import db_error
from ..app.state import app_state
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.models import FavoriteItem, Gallery
from ..db.repository import DownloadRepository, GalleryUpdatesRepository
from ..logging import bind_log_context, log_extra
from .deletion import delete_galleries_local

logger = logging.getLogger(__name__)

_UPDATE_TITLE_VARIANTS = (
    "中国翻訳", "中国翻译", "中文翻譯", "中文翻译", "中文", "中国語", "汉化", "漢化",
    "汉化组", "漢化組", "翻译", "翻訳", "english", "chinese", "dl版", "無修正", "无修正",
    "デジタル版", "デジタル", "digital", "colorized", "color", "スキャナー",
    "修正版", "未修正", "翻訳版", "翻譯版", "アニメ", "実写", "総集編", "全話",
    "uncensored", "uncenseored", "decensored", "ai generated", "ongoing", "進行中", "连载中",
    "連載中", "完結", "完结",
)


def normalize_update_title(title: str) -> str:
    """Normalize a gallery title for re-upload matching, supporting multi-chapter series and bilingual variants."""
    text = title.strip().lower()
    text = re.sub(r"^\d+[\s\-]+", "", text)

    # Normalize full-width brackets to standard brackets
    text = re.sub(r"[【［〖〔]", "[", text)
    text = re.sub(r"[】］〗〕]", "]", text)
    text = re.sub(r"[（]", "(", text)
    text = re.sub(r"[）]", ")", text)

    # If bilingual title separated by | or ／, take primary part
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if parts:
            text = parts[0]

    # Strip metadata tags inside brackets (languages, translation groups, formats)
    meta_bracket_pattern = r"\[(?:[^\]]*(?:中国|中文|翻訳|翻译|漢化|汉化|english|chinese|dl版|無修正|无修正|uncensor|decensor|デジタル|digital|color|スキャナー|修正|未修正|アニメ|実写|総集編|全話|特典|リーフレット|小冊子|おまけ|進行中|连载中|連載中|ongoing|ai generated|\d+p|\d+話|\d+话|個人|机翻|組|组)[^\]]*)\]"
    text = re.sub(meta_bracket_pattern, "", text, flags=re.IGNORECASE)

    variants = "|".join(_UPDATE_TITLE_VARIANTS)
    text = re.sub(rf"\[(?:{variants})\]", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"\((?:{variants})\)", "", text, flags=re.IGNORECASE)

    # Strip bonus / leaflet additions
    text = re.sub(r"\+\s*[^\[\]()]*?(?:リーフレット|特典|おまけ|小冊子|設定資料)[^\[\]()]*", "", text, flags=re.IGNORECASE)

    # Strip date ranges and timestamps before general number regexes
    text = re.sub(r"\(\s*[\d./\-]+\s*[-~～至到]\s*[\d./\-]+\s*\)", "", text)
    text = re.sub(r"\[\s*[\d./\-]+\s*[-~～至到]\s*[\d./\-]+\s*\]", "", text)
    text = re.sub(r"\b\d{2,4}[./\-]\d{1,2}(?:[./\-]\d{1,2})?\s*[-~～至到]\s*\d{2,4}[./\-]\d{1,2}(?:[./\-]\d{1,2})?\b", "", text)
    text = re.sub(r"\b20\d{2}[./\-]\d{1,2}(?:[./\-]\d{1,2})?\b", "", text)
    text = re.sub(r"\b20\d{6}\b", "", text)

    # Strip chapter / volume / episode markers:
    # "第1-12話+2体目-第1-4話", "第22-38話", "第1-8話", "第8話", "第3話", "最後話"
    text = re.sub(r"第?\s*\d+(?:[-~～/、,]\s*(?:第?\s*)?\d+)*\s*(?:話|话|巻|卷|章|回|篇)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:最後話|最终话|最終話|前編|後編|前篇|後篇|番外編|番外篇|総集編|総集篇|全話)", "", text, flags=re.IGNORECASE)

    # Numbers with symbols / chapter ranges: "①〜⑨", "(01-06)", "1-4", "1-5", "t1-t21", "m1-m50", "#1-4"
    text = re.sub(r"[①-⑳㈠-㈩]\s*[-~～至到]\s*[①-⑳㈠-㈩]", "", text)
    text = re.sub(r"[①-⑳㈠-㈩]", "", text)
    text = re.sub(r"(?:[#t]|vol\.?|part\.?|set\.?|pt\.?)\s*\d+(?:\s*[-~～/]\s*(?:[#t]|vol\.?|part\.?|set\.?|pt\.?)?\s*\d+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*0*\d+\s*[-~～/]\s*0*\d+\s*\)", "", text)
    text = re.sub(r"\[\s*0*\d+\s*[-~～/]\s*0*\d+\s*\]", "", text)
    text = re.sub(r"\b0*\d+\s*[-~～]\s*0*\d+\b", "", text)

    # Subtitle separation with multi-spaces
    sub_parts = re.split(r"\s{2,}", text)
    if len(sub_parts) > 1 and len(sub_parts[0]) > 4:
        text = sub_parts[0]

    text = re.sub(r"[\s\[\](){}“”\"'`,.。、:：;；!！?？\-—_/\\|·・〜～+♥♡⭐]+", "", text)
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
        from ..app.dependencies import spawn_task

        spawn_task(tm.persist_history(), "persist task history")


async def finalize_gallery_update(row: Any) -> None:
    session_cm = app_state.session_factory
    if session_cm is None:
        return
    repo_cls = GalleryUpdatesRepository
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
        if getattr(row, "id", None) is None:
            return
        try:
            async with session_cm() as session, session.begin():
                await repo_cls(session).mark_failed(row.id, str(exc))
        except Exception as exc2:  # noqa: BLE001
            logger.warning(
                "could not record gallery update failure",
                extra=log_extra(update_id=row.id, error=type(exc2).__name__),
            )


async def finalize_updates_for_new_gid(new_gid: int) -> int:
    session_cm = app_state.session_factory
    if session_cm is None:
        return 0
    async with session_cm() as session:
        rows = await GalleryUpdatesRepository(session).actionable_by_new_gid(int(new_gid))
        refs = [SimpleNamespace(id=r.id, gallery_id=r.gallery_id) for r in rows]
    done = 0
    for ref in refs:
        await finalize_gallery_update(ref)
        done += 1
    return done


async def detect_gallery_updates() -> None:
    session_cm = app_state.session_factory
    if session_cm is None:
        return
    repo_cls = GalleryUpdatesRepository
    tm = app_state.task_manager
    gallery_updates_state = tm.gallery_updates_state if tm else {}

    if bool(gallery_updates_state.get("detecting")):
        return
    with bind_log_context(worker="updates"):
        gallery_updates_state.update({"detecting": True, "last_error": None})
        detected: list[dict[str, Any]] = []
        found = 0
        to_insert: list[dict[str, Any]] = []
        to_finalize: list[Any] = []
        to_attach: dict[int, int] = {}
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
                    if "|" in (title or ""):
                        for part in title.split("|"):
                            p_nt = normalize_update_title(part)
                            if p_nt and p_nt not in by_title:
                                by_title[p_nt] = (gid, str(token), int(favcat))
                repo = repo_cls(session)
                tracking = await repo.tracking_by_gallery_id()
                page = 1
                while True:
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
                if detected:
                    new_gids = [e["new_gid"] for e in detected]
                    local_new = await repo.local_new_gids(new_gids)
                    active_tasks = await repo.active_task_ids_for_gids(new_gids)
            for entry in detected:
                status = entry.get("existing_status")
                if entry["new_gid"] in local_new:
                    to_finalize.append(
                        SimpleNamespace(
                            id=entry.get("existing_id"),
                            gallery_id=entry["gallery_id"],
                        )
                    )
                    continue
                extra: dict[str, Any] = {}
                task_id = active_tasks.get(entry["new_gid"])
                if status is None:
                    if task_id:
                        extra["status"] = "downloading"
                        extra["download_task_id"] = task_id
                    to_insert.append(
                        {
                            "gallery_id": entry["gallery_id"],
                            "old_gid": entry["old_gid"],
                            "new_gid": entry["new_gid"],
                            "new_token": entry["new_token"],
                            "title": entry["title"],
                            "favcat": entry["favcat"],
                            **extra,
                        }
                    )
                elif status in {"pending", "failed"} and task_id:
                    to_attach[int(entry["new_gid"])] = int(task_id)
            if to_insert:
                async with session_cm() as session, session.begin():
                    found = await repo_cls(session).detect_many(
                        to_insert, known_gallery_ids=set()
                    )
            if to_attach:
                async with session_cm() as session, session.begin():
                    attached_repo = repo_cls(session)
                    for gid, task_id in to_attach.items():
                        await attached_repo.attach_download(gid, task_id)
            for ref in to_finalize:
                await finalize_gallery_update(ref)
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
                "gallery update detection failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
        finally:
            gallery_updates_state["detecting"] = False
            gallery_updates_state["last_run"] = datetime.now(UTC).isoformat()


async def run_gallery_updates(
    ids: list[int], *, archive: bool = False, quality: str | None = None
) -> dict[str, int]:
    session_cm = app_state.session_factory
    if session_cm is None:
        return {"started": 0, "skipped": len(ids)}
    repo_cls = GalleryUpdatesRepository
    dl_repo_cls = DownloadRepository

    started = 0
    skipped = 0
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
            local = (
                await repo.local_new_gids([row.new_gid for row in pending_rows])
                if pending_rows
                else set()
            )
            for row in pending_rows:
                if row.new_gid in local:
                    ready.append(SimpleNamespace(id=row.id, gallery_id=row.gallery_id))
                    started += 1
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
                await repo.mark_downloading(row.id, task.id)
                started += 1
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    for ref in ready:
        await finalize_gallery_update(ref)
    return {"started": started, "skipped": skipped}


async def gallery_updates_finalize_loop() -> None:
    while True:
        await asyncio.sleep(30)
        session_cm = app_state.session_factory
        if session_cm is None:
            continue
        repo_cls = GalleryUpdatesRepository
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
            await asyncio.sleep(60)
