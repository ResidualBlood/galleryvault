"""Finalize gallery updates: replace the old copy once the new one is stored."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

from ...app.state import app_state
from ...db.models import DownloadTask as DownloadTaskModel
from ...db.models import Gallery, GalleryUpdate
from ...db.repository import GalleryUpdatesRepository
from ...db.uow import UnitOfWork
from ...logging import log_extra
from ..duplicate_groups import delete_group_by_key

# Same logger name as the legacy module (CR1).
logger = logging.getLogger("galleryvault.services.updates_worker")

#: Consecutive finalize checks a ``downloading`` update may wait for its new
#: version to be ingested before it is marked ``failed``.  The finalize loop
#: ticks every 30s, so 48 checks is roughly 24 minutes of tolerance.
FINALIZE_WAIT_LIMIT = 48

#: Prefix of the ``error_message`` written while a finalize is postponed.
_WAIT_PREFIX = "waiting for ingest"

#: Storage types whose copies live in the (possibly offline) cold archive.
_COLD_STORAGE_TYPES = {"cold", "cold_archive"}

#: In-process counter of consecutive ingest waits, keyed by gallery-update id.
_finalize_wait_counts: dict[int, int] = {}


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


def _is_cold_storage(gallery: Gallery) -> bool:
    """True when the gallery copy lives in the (possibly offline) cold archive."""
    if (getattr(gallery, "storage_type", None) or "") in _COLD_STORAGE_TYPES:
        return True
    storage_path = getattr(gallery, "storage_path", None)
    if not storage_path:
        return False
    try:
        from ..cold_archive import is_under_cold

        return is_under_cold(Path(storage_path))
    except (ImportError, OSError, TypeError, ValueError):
        # Cold-archive roots unavailable: treat the copy as local.
        return False


def _ingest_pending_reason(new_gid: int | None, new_gallery: Gallery | None) -> str | None:
    """Why the new version is not ingested yet, or ``None`` when finalize is safe.

    Finalizing deletes the old gallery row and its files, so it may only run
    once the replacement is actually stored.  The download task reaching
    ``success`` is not evidence of that: ``download_worker`` commits it before
    ingest runs, and ingest may still fail afterwards.
    """
    if new_gid is None:
        return f"{_WAIT_PREFIX}: new gid unknown"
    if new_gallery is None:
        return f"{_WAIT_PREFIX}: new gallery not stored yet"
    if _is_cold_storage(new_gallery):
        return None
    storage_path = getattr(new_gallery, "storage_path", None)
    if not storage_path:
        # No managed local copy to verify (legacy row); nothing to check here.
        return None
    if not Path(storage_path).exists():
        return f"{_WAIT_PREFIX}: new gallery files missing"
    return None


def _page_count_pending_reason(new_gallery: Gallery | None) -> str | None:
    """Why the replacement cannot take over reading state yet.

    The transfer clamps the old reading position to the new page count; without a
    positive page count the progress would be meaningless (and the new version is
    probably a broken/partial ingest).  ``None`` (unknown, legacy rows) still
    passes: only a known non-positive count blocks the finalize.
    """
    if new_gallery is None:
        return None
    page_count = getattr(new_gallery, "page_count", None)
    if page_count is None:
        return None
    if int(page_count) <= 0:
        return f"{_WAIT_PREFIX}: new gallery has no pages"
    return None


async def finalize_gallery_update(row: Any) -> str | None:
    """Finalize one gallery update, replacing the old gallery with the new version.

    Returns the reason the finalize was postponed (the update stays
    ``downloading`` and nothing is deleted), or ``None`` once the old gallery
    was removed.  A successful download task alone is not enough to finalize:
    ``download_worker`` marks it ``success`` independently of ingest, so the
    replacement must already exist locally with its files on disk.
    """
    session_cm = app_state.session_factory
    if session_cm is None:
        return None
    gallery_id = getattr(row, "gallery_id", None)
    if gallery_id is None:
        return None

    update_id = getattr(row, "id", None)
    repo_cls = GalleryUpdatesRepository
    old_storage_path: str | None = None
    old_gid: int | None = None

    try:
        async with session_cm() as session, session.begin():
            uow = UnitOfWork(session)
            old_gallery = await uow.session.get(Gallery, gallery_id)
            if old_gallery is None:
                return None

            old_storage_path = old_gallery.storage_path
            old_gid = old_gallery.gid

            update_row: GalleryUpdate | None = None
            if update_id is not None:
                update_row = await uow.updates.get(update_id)
            if update_row is None and old_gallery.id is not None:
                update_row = await uow.session.scalar(
                    select(GalleryUpdate).where(GalleryUpdate.gallery_id == old_gallery.id)
                )

            new_gid = getattr(row, "new_gid", None)
            if new_gid is None and update_row is not None:
                new_gid = update_row.new_gid

            new_gallery: Gallery | None = None
            if new_gid is not None:
                new_gallery = await uow.session.scalar(
                    select(Gallery).where(
                        Gallery.gid == int(new_gid),
                        Gallery.expunged.is_(False),
                        Gallery.trashed.is_(False),
                    )
                )

            pending_reason = _ingest_pending_reason(new_gid, new_gallery)
            if pending_reason is None:
                pending_reason = _page_count_pending_reason(new_gallery)
            if pending_reason is not None:
                # The replacement is not stored yet: keep the old gallery (and
                # its files) until a later finalize pass sees a complete copy.
                if update_row is not None:
                    update_row.status = "downloading"
                    update_row.error_message = pending_reason
                    update_row.updated_at = datetime.now(UTC)
                logger.info(
                    "gallery update finalize postponed",
                    extra=log_extra(
                        update_id=update_id,
                        gallery_id=gallery_id,
                        new_gid=new_gid,
                        reason=pending_reason,
                    ),
                )
                return pending_reason

            # 迁移旧版本的用户数据（进度/历史/列表/系列归属/在线进度），必须在删旧行之前
            if (
                new_gallery is not None
                and old_gallery.id is not None
                and new_gallery.id is not None
            ):
                await uow.galleries.transfer_user_data(
                    old_gallery.id, new_gallery.id, old_gid, new_gid
                )

            # 转移旧画廊用户数据（本地评分与备注、分类）
            if new_gallery is not None:
                if old_gallery.local_rating is not None and new_gallery.local_rating is None:
                    new_gallery.local_rating = old_gallery.local_rating
                if old_gallery.local_note and not new_gallery.local_note:
                    new_gallery.local_note = old_gallery.local_note
                if old_gallery.category and not new_gallery.category:
                    new_gallery.category = old_gallery.category
                new_gallery.updated_at = datetime.now(UTC)

            # 标记状态完结并在级联下删除旧版本画廊
            if update_row is not None:
                update_row.status = "completed"
                update_row.error_message = None
                update_row.updated_at = datetime.now(UTC)

            await uow.session.delete(old_gallery)
            if old_gid is not None:
                # T5.3: the duplicate group follows the GID into
                # ``duplicate_groups``; the stale row is dropped here and the
                # next scan re-registers the new GID.
                await delete_group_by_key(uow.session, "same_gid", str(old_gid))
    except Exception as exc:
        logger.warning(
            "gallery update finalize failed, rolled back to downloading",
            extra=log_extra(update_id=update_id, gallery_id=gallery_id, error=type(exc).__name__),
        )
        if update_id is not None:
            try:
                async with session_cm() as retry_session, retry_session.begin():
                    update_row = await repo_cls(retry_session).get(update_id)
                    if update_row is not None:
                        update_row.status = "downloading"
                        update_row.error_message = f"Finalize error, will retry: {exc}"
                        update_row.updated_at = datetime.now(UTC)
            except Exception as exc2:  # noqa: BLE001
                logger.warning(
                    "could not reset gallery update status to downloading",
                    extra=log_extra(update_id=update_id, error=type(exc2).__name__),
                )
        raise

    # 事务成功提交后，执行物理文件删除与日志记录
    if old_storage_path:
        p = Path(old_storage_path)
        try:
            from ..deletion import delete_local_copy

            delete_local_copy(p)
        except Exception as io_err:  # noqa: BLE001
            logger.warning(
                "failed to delete old gallery physical copy",
                extra=log_extra(
                    gallery_id=gallery_id,
                    path=old_storage_path,
                    error=type(io_err).__name__,
                ),
            )
    try:
        record_gallery_update_log([
            {
                "gallery_id": gallery_id,
                "gid": old_gid,
                "db_removed": True,
                "deleted_paths": [old_storage_path] if old_storage_path else [],
                "failed_paths": [],
            }
        ])
    except Exception as log_err:  # noqa: BLE001
        logger.warning(
            "failed to record gallery update log",
            extra=log_extra(
                gallery_id=gallery_id,
                error=type(log_err).__name__,
            ),
        )


async def finalize_updates_for_new_gid(new_gid: int) -> int:
    session_cm = app_state.session_factory
    if session_cm is None:
        return 0
    async with session_cm() as session:
        repo = GalleryUpdatesRepository(session)
        rows = await repo.actionable_by_new_gid(int(new_gid))
        if len(rows) > 1:
            # One re-upload matching several local galleries is the title
            # N→1 hazard: without an official replace link there is no way to
            # tell which local copies are really superseded, so nothing may be
            # auto-deleted.  Park the unchained rows in ``pending`` for the user.
            old_gids = await repo.gallery_gids([r.gallery_id for r in rows])
            chained = await repo.replacement_chain_pairs(
                [(old_gid, int(new_gid)) for old_gid in old_gids.values()]
            )
            total = len(rows)
            blocked = [
                int(r.id)
                for r in rows
                if (old_gids.get(int(r.gallery_id)), int(new_gid)) not in chained
            ]
            if blocked:
                blocked_ids = set(blocked)
                rows = [r for r in rows if int(r.id) not in blocked_ids]
                async with session_cm() as mark_session, mark_session.begin():
                    await GalleryUpdatesRepository(mark_session).mark_ambiguous(
                        blocked, f"ambiguous: {total} local galleries match"
                    )
        refs = [
            SimpleNamespace(
                id=r.id, gallery_id=r.gallery_id, new_gid=getattr(r, "new_gid", new_gid)
            )
            for r in rows
        ]
    done = 0
    for ref in refs:
        try:
            await finalize_gallery_update(ref)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "finalize_updates_for_new_gid failed for row, leaving actionable for retry",
                extra=log_extra(update_id=ref.id, new_gid=new_gid, error=type(exc).__name__),
            )
    return done


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
                    _finalize_wait_counts.pop(row.id, None)
                    async with session_cm() as session, session.begin():
                        await repo_cls(session).mark_failed(
                            row.id, "download task removed"
                        )
                    continue
                if task.status == "success":
                    pending_reason = await finalize_gallery_update(row)
                    if pending_reason is None:
                        _finalize_wait_counts.pop(row.id, None)
                        continue
                    waits = _finalize_wait_counts.get(row.id, 0) + 1
                    _finalize_wait_counts[row.id] = waits
                    if waits >= FINALIZE_WAIT_LIMIT:
                        _finalize_wait_counts.pop(row.id, None)
                        message = (
                            f"gave up waiting for ingest after {waits} checks: "
                            f"{pending_reason}; old copy kept"
                        )
                        logger.warning(
                            "gallery update ingest never completed, marking failed",
                            extra=log_extra(update_id=row.id, new_gid=row.new_gid),
                        )
                        async with session_cm() as session, session.begin():
                            await repo_cls(session).mark_failed(row.id, message)
                elif task.status in {"failed", "cancelled"}:
                    _finalize_wait_counts.pop(row.id, None)
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
