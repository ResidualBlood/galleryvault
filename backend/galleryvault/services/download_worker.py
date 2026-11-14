"""Background worker loops and post-processing for downloads."""

from __future__ import annotations

import asyncio
import logging
import os
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..app.state import app_state
from ..config import get_settings
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.models import Gallery, GalleryUpdate
from ..db.repository import DownloadRepository
from ..logging import bind_log_context, log_extra
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from ..scanners.ehviewer import IMAGE_EXTENSIONS, natural_key
from .deletion import (
    collapse_same_stem_pages,
    prune_merged_stale_pages,
    remove_superseded_copy,
)
from .downloader import (
    ArchiveNotRetryableError,
    DownloadCancelledError,
    DownloadTask,
)
from .duplicate_resolver import (
    DEFAULT_DUPLICATE_POLICY,
    Copy,
    ResolvedGroup,
)
from .eh_client import (  # noqa: F401  # kept for backoff classification docs
    EhChallengeError,
    EhClientError,
    GalleryGoneError,
    GalleryReplacedError,
)
from .ingest import GalleryIngestService
from .messages import (
    GONE_DETAIL,
    HOPS_DETAIL,
    download_ingest_fail_detail,
    normalize_lang,
)

logger = logging.getLogger(__name__)

# Retry budget semantics: transient errors are requeued with exponential
# backoff until ``max_retries`` is exhausted; after that the task is terminal.
# There is no automatic "resurrect failed tasks" sweep: failed rows always
# carried a fully consumed budget, so the old 60s sweep was dead code, and it
# would also have resurrected tasks that failed on purpose (e.g. the 302
# challenge budget). Recovery is the manual retry endpoint, which resets
# retry_count (report 01 P2-2).
_RETRY_BACKOFFS = (
    30, 120, 480, 1800, 3600, 7200, 10800, 14400, 18000, 21600,
)
# Idle workers must not depend on external events: the worker event is only an
# early-wakeup hint, while a bounded timeout derived from the earliest scheduled
# ``retry_at`` is the actual scheduler (report 01 P1-4). The upper bound doubles
# as a safety-net poll when no retry is scheduled at all.
_WORKER_POLL_MIN_SECONDS = 1.0
_WORKER_POLL_MAX_SECONDS = 60.0
_PROGRESS_FLUSH_STEP = 20
_PROGRESS_FLUSH_INTERVAL = 5.0
_TELEGRAM_FLUSH_INTERVAL = 60.0

_worker_events: set[asyncio.Event] = set()
_worker_tasks: list[asyncio.Task] = []
_target_download_concurrency: int = 2


def _get_background_session_factory() -> Any:
    return getattr(app_state, "background_session_factory", None) or app_state.session_factory


def notify_new_task() -> None:
    """Wake up download workers when a new task is enqueued or retried."""
    for ev in list(_worker_events):
        ev.set()


def retry_backoff(retry_count: int) -> int:
    """Return the backoff delay (seconds) for the given failed attempt count."""
    return _RETRY_BACKOFFS[min(max(1, retry_count) - 1, len(_RETRY_BACKOFFS) - 1)]


def _idle_poll_timeout(next_retry_at: datetime | None) -> float:
    """Bounded idle wait: wake for the earliest scheduled retry, else poll."""
    if next_retry_at is None:
        return _WORKER_POLL_MAX_SECONDS
    if next_retry_at.tzinfo is None:
        # SQLite drops the timezone; retry_at is always stored as UTC.
        next_retry_at = next_retry_at.replace(tzinfo=UTC)
    remaining = (next_retry_at - datetime.now(UTC)).total_seconds()
    return min(max(remaining, _WORKER_POLL_MIN_SECONDS), _WORKER_POLL_MAX_SECONDS)


def infer_image_quality(
    storage_size: int | None, original_size: int | None, storage_type: str | None = None
) -> str | None:
    """Infer original/resample from local size vs the ExHentai original size."""
    if not storage_size or not original_size:
        return None
    threshold = 0.8 if storage_type == "cbz" else 0.85
    return "original" if (storage_size / original_size) >= threshold else "resample"


class IngestError(RuntimeError):
    """The main ingest step of a finished download failed.

    Raised by :func:`ingest_downloaded_gallery` so the ingest pump can persist
    ``failed`` instead of leaving the task ``downloading`` forever. Secondary
    steps (update finalize, cold archive hook) stay best-effort warnings.
    """


# Every field ``ingest_downloaded_gallery`` reads from the download result.
# ``ingest_payload`` must round-trip all of them so a restarted pump behaves
# exactly like the first run (T2.1 risk note in PLAN).
_INGEST_PAYLOAD_FIELDS = (
    "path",
    "quality",
    "new_files",
    "tags",
    "file_size",
    "title",
    "gid",
    "token",
    "title_jpn",
    "category",
    "uploader",
    "rating",
    "pages",
)


def _jsonable(value: Any) -> Any:
    """Convert sets/tuples/paths from a download result into JSON values."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def serialize_ingest_payload(result: Any) -> dict[str, Any]:
    """Snapshot enough of a download result to replay the ingest after a restart."""
    return {
        field: _jsonable(getattr(result, field, None))
        for field in _INGEST_PAYLOAD_FIELDS
    }


def ingest_result_from_payload(payload: dict[str, Any]) -> Any:
    """Rebuild the object shape ``ingest_downloaded_gallery`` expects."""
    from types import SimpleNamespace

    return SimpleNamespace(
        **{field: payload.get(field) for field in _INGEST_PAYLOAD_FIELDS}
    )



def _path_is_relative_to(path: Path, root: str | Path) -> bool:
    """Resolve ``path``/``root`` and report whether ``path`` sits under ``root``."""
    try:
        return path.resolve().is_relative_to(Path(root).resolve())
    except (OSError, RuntimeError, ValueError, TypeError):
        return False


def _is_library_only_copy(path: Path, settings: Any) -> bool:
    """True for an old copy under a library root but not under ``download_root``.

    Copies outside the download root may live on a read-only library mount.  They
    must never be removed by a download/supersede (T2.4); callers register them
    as duplicates instead so the user decides.
    """
    download_root = getattr(settings, "download_root", None)
    if download_root and _path_is_relative_to(path, download_root):
        return False
    roots = getattr(settings, "library_roots", None) or []
    return any(_path_is_relative_to(path, root) for root in roots)


def _merge_duplicate_copies(
    existing: list[Any], additions: list[Any]
) -> list[dict[str, Any]]:
    """Merge new copies into an existing duplicate record without losing others."""
    merged: dict[str, dict[str, Any]] = {}
    for copy in existing:
        if isinstance(copy, dict) and copy.get("path"):
            merged[str(copy["path"])] = dict(copy)
    for copy in additions:
        if isinstance(copy, dict) and copy.get("path"):
            merged[str(copy["path"])] = dict(copy)
    copies = list(merged.values())
    copies.sort(key=lambda copy: (not bool(copy.get("is_current")), str(copy.get("path"))))
    return copies


async def _register_superseded_duplicate(
    result: Any, old_path: Path, old_pages: int
) -> None:
    """Record the kept old copy as a duplicate of the freshly ingested gid."""
    gid = getattr(result, "gid", None)
    if gid is None:
        return
    gid = int(gid)
    new_path = Path(result.path)
    group = ResolvedGroup(
        gid=gid,
        policy=DEFAULT_DUPLICATE_POLICY,
        winner=Copy(
            path=new_path,
            gid=gid,
            title=getattr(result, "title", "") or "",
            title_jpn=getattr(result, "title_jpn", "") or "",
            page_count=getattr(result, "pages", None),
            file_size=getattr(result, "file_size", None),
            is_current=True,
        ),
        losers=[
            Copy(
                path=old_path,
                gid=gid,
                page_count=old_pages,
                is_current=False,
            )
        ],
    )
    payload = group.record()
    session_cm = _get_background_session_factory()
    if session_cm is None:
        logger.warning(
            "cannot register superseded copy without a session factory",
            extra=log_extra(gid=gid, path=str(old_path)),
        )
        return

    from ..db.repositories.duplicates import DuplicateGroupRepository

    async with session_cm() as session, session.begin():
        # Single source of truth (T2.4/T5.3): reconcile the whole same-gid kind
        # so registering one superseded copy cannot drop the other open groups.
        # ``sync`` keeps a dismissed row dismissed (the user's decision wins).
        repo = DuplicateGroupRepository(session)
        existing_groups = [
            {
                "group_key": row.group_key,
                "member_gids": list(row.member_gids or []),
                "payload": dict(row.payload or {}),
                "title": row.title,
                "artist": row.artist,
            }
            for row in await repo.list(kind="same_gid")
        ]
        target = next((g for g in existing_groups if g["group_key"] == str(gid)), None)
        if target is None:
            existing_groups.append(
                {
                    "group_key": str(gid),
                    "member_gids": [gid],
                    "payload": {
                        "policy": payload["policy"],
                        "winner_path": payload["winner_path"],
                        "copies": payload["copies"],
                    },
                }
            )
        else:
            stored_payload = dict(target.get("payload") or {})
            target["payload"] = {
                **stored_payload,
                "policy": payload["policy"],
                "winner_path": payload["winner_path"],
                "copies": _merge_duplicate_copies(
                    list(stored_payload.get("copies") or []), list(payload["copies"])
                ),
            }
        await repo.sync("same_gid", existing_groups)
    logger.info(
        "registered superseded copy as duplicate",
        extra=log_extra(gid=gid, path=str(old_path)),
    )


async def _supersede_old_copy(
    result: Any, old_path: Path, old_pages: int
) -> None:
    """Delete a superseded *download-root* copy, or register a library copy.

    The removal path always receives the configured scan roots (the old call
    omitted them, so a mis-configured root could silently delete a library
    directory). Library-root copies are never deleted here.
    """
    new_path = Path(result.path)
    try:
        if old_path.resolve() == new_path.resolve():
            return
    except (OSError, RuntimeError, ValueError):
        pass

    settings = app_state.settings or get_settings()
    if _is_library_only_copy(old_path, settings):
        await _register_superseded_duplicate(result, old_path, old_pages)
        return

    from ..app import dependencies

    await remove_superseded_copy(
        result, old_path, old_pages, scan_roots=dependencies.get_scan_roots()
    )


async def ingest_downloaded_gallery(result: Any, *, strict: bool = False) -> None:
    """Ingest a freshly downloaded gallery directly from memory metadata.

    ``strict=True`` (used by the ingest pump) raises :class:`IngestError` when
    the main import (scanner lookup, page scan, library upsert) fails, so the
    pump can record ``failed``. The default keeps the legacy best-effort
    behaviour for direct callers. Best-effort follow-ups (update finalize, cold
    archive) only warn in both modes.
    """
    try:
        path = Path(result.path)
        reg = registry
        scanner = reg.for_path(path)
        if scanner is None:
            raise IngestError(f"no scanner for path {path}")

        if getattr(result, "quality", None) == "original":
            await asyncio.to_thread(
                prune_merged_stale_pages, path, getattr(result, "new_files", ())
            )
        await asyncio.to_thread(collapse_same_stem_pages, path)

        def _gather_pages(p: Path) -> list[PageInfo]:
            files = sorted(
                (
                    item
                    for item in p.iterdir()
                    if item.is_file()
                    and not item.name.startswith(".")
                    and item.suffix.casefold() in IMAGE_EXTENSIONS
                ),
                key=lambda item: natural_key(item.name),
            )
            return [
                PageInfo(
                    i,
                    item.name,
                    item.suffix.casefold().lstrip("."),
                    item.stat().st_size,
                    item.stat().st_mtime_ns,
                )
                for i, item in enumerate(files)
            ]

        pages = await asyncio.to_thread(_gather_pages, path)
        raw_tags = getattr(result, "tags", None) or ()
        if isinstance(raw_tags, dict):
            tags = [
                {"namespace": ns, "name": name}
                for ns, names in raw_tags.items()
                for name in (names if isinstance(names, (list, tuple, set)) else [names])
            ]
        elif isinstance(raw_tags, (list, tuple)):
            tags = []
            for item in raw_tags:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    tags.append({"namespace": str(item[0]), "name": str(item[1])})
                elif isinstance(item, dict):
                    tags.append({
                        "namespace": str(item.get("namespace", "misc")),
                        "name": str(item.get("name", "")),
                    })
                elif isinstance(item, str):
                    tags.append({"namespace": "misc", "name": item})
        else:
            tags = []
        quality = getattr(result, "quality", None)
        if quality is None:
            storage_size = sum(p.size for p in pages)
            st_type = getattr(scanner, "storage_type", getattr(scanner, "kind", lambda: "ehviewer_dir")())
            quality = infer_image_quality(
                storage_size, getattr(result, "file_size", None), st_type
            )

        sig = scanner.storage_signature(path) if hasattr(scanner, "storage_signature") else "sig"
        mtime = path.stat().st_mtime_ns if path.exists() else 0
        gallery_meta = GalleryMeta(
            title=result.title or path.name,
            path=path,
            storage_type=getattr(scanner, "storage_type", "ehviewer_dir"),
            pages=pages,
            gid=result.gid,
            token=result.token,
            title_jpn=getattr(result, "title_jpn", None),
            category=getattr(result, "category", "other"),
            uploader=getattr(result, "uploader", None),
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            rating=getattr(result, "rating", None),
            tags=tags,
            image_quality=quality,
            storage_signature=sig,
            storage_mtime_ns=mtime,
            storage_size=sum(p.size or 0 for p in pages),
            source_meta={"title": result.title or path.name, "tags": tags},
        )

        ingest_cls = GalleryIngestService
        session_cm = _get_background_session_factory()
        old_copy: tuple[Path, int] | None = None

        if session_cm is not None:
            async with session_cm() as session, session.begin():
                if getattr(gallery_meta, "gid", None) is not None:
                    prev = await session.scalar(
                        select(Gallery).where(Gallery.gid == gallery_meta.gid)
                    )
                    if prev is not None and prev.storage_path != str(path):
                        old_copy = (Path(prev.storage_path), getattr(prev, "page_count", 0) or 0)
                await ingest_cls(session).ingest([gallery_meta])

        if getattr(result, "quality", None) == "original" and old_copy is not None:
            await _supersede_old_copy(result, old_copy[0], old_copy[1])

        logger.info("download ingest succeeded", extra=log_extra(gid=result.gid, path=str(path)))
        try:
            from .updates_worker import finalize_updates_for_new_gid

            await finalize_updates_for_new_gid(int(result.gid))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gallery update finalize after ingest failed",
                extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__),
            )
        try:
            settings = app_state.settings or get_settings()
            auto_archive = bool(getattr(settings, "auto_archive_downloads", True))
            from .cold_archive import resolve_archive_roots

            has_archive = bool(resolve_archive_roots())
            if auto_archive and has_archive and getattr(result, "gid", None) is not None:
                gid_int = int(result.gid)
                if session_cm is not None:
                    try:
                        async with session_cm() as session, session.begin():
                            await DownloadRepository(session).update_archive_status(
                                gid_int, "pending", None
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to pre-mark download task archive_status=pending",
                            extra=log_extra(gid=gid_int, error=type(exc).__name__),
                        )
                from ..app.dependencies import spawn_task

                spawn_task(
                    _archive_downloaded_gallery(gid_int),
                    f"download auto archive {gid_int}",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "download auto archive hook failed",
                extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__),
            )
    except IngestError:
        logger.exception(
            "download ingest failed",
            extra=log_extra(gid=getattr(result, "gid", None), error="IngestError"),
        )
        if strict:
            raise
        return
    except Exception as exc:
        logger.exception(
            "download ingest failed",
            extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__, message=str(exc)),
        )
        if strict:
            raise IngestError(f"{type(exc).__name__}: {exc}") from exc
        return


async def _archive_downloaded_gallery(gid: int) -> None:
    """Background task to archive a freshly ingested gallery into cold storage."""
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return

    try:
        async with session_cm() as session, session.begin():
            await DownloadRepository(session).update_archive_status(gid, "pending", None)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to mark download task archive pending",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )

    archive_err: str | None = None
    dest = None
    try:
        from . import cold_archive

        dest = await cold_archive.archive_one(gid, session_factory=session_cm)
        if dest is None:
            archive_err = "archive destination not created or skipped"
    except Exception as exc:  # noqa: BLE001
        archive_err = str(exc)
        logger.warning(
            "Auto archive execution failed",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )

    try:
        async with session_cm() as session, session.begin():
            if dest is not None:
                await DownloadRepository(session).update_archive_status(gid, "ok", None)
            else:
                await DownloadRepository(session).update_archive_status(gid, "fail", archive_err)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to persist download task archive outcome",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )

    title = str(gid)
    try:
        async with session_cm() as session:
            g_row = await session.execute(
                select(Gallery.title).where(Gallery.gid == gid)
            )
            g_title = g_row.scalar_one_or_none()
            if g_title:
                title = g_title
            else:
                d_row = await session.execute(
                    select(DownloadTaskModel.title).where(DownloadTaskModel.gid == gid)
                )
                d_title = d_row.scalar_one_or_none()
                if d_title:
                    title = d_title
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to resolve gallery title for archive notification: %s", exc)

    kind = "archive_ok" if dest is not None else "archive_fail"
    detail = None if dest is not None else archive_err
    await record_archive_notification(kind, title, detail)


_INGEST_PUMP_INTERVAL = 2.0
_INGEST_PUMP_BATCH = 10


def _scan_running() -> bool:
    tm = app_state.task_manager
    return bool(tm and tm.scan_state.get("running"))


async def _resolve_notify_old_gid(
    session: Any, gid: int, replaced_from_gid: int | None
) -> int | None:
    """Gid old copy for the ok/updated wording, resolved *before* the ingest.

    Must run in transaction A (files on disk, gallery not yet in the library):
    once the ingest has inserted ``Gallery.gid == gid`` every download would
    look like an update, so this cannot be queried after the import.
    """
    if replaced_from_gid is not None:
        return replaced_from_gid
    if not hasattr(session, "scalar"):
        return None
    try:
        update_row = await session.scalar(
            select(GalleryUpdate).where(GalleryUpdate.new_gid == gid)
        )
        if update_row is not None:
            return update_row.old_gid
        prev = await session.scalar(select(Gallery).where(Gallery.gid == gid))
        if prev is not None:
            return gid
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "failed to check update status for download notification",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )
    return None


async def _notify_ingested(payload: dict[str, Any]) -> None:
    gid = payload.get("gid")
    title = payload.get("title") or str(gid)
    # ``notify_old_gid`` was resolved before the ingest; never look the gallery
    # up here, because the just-inserted row would always look pre-existing.
    old_gid = payload.get("notify_old_gid")
    try:
        if old_gid is not None:
            await record_download_notification("updated", title, f"{old_gid}:{gid}")
        else:
            await record_download_notification("ok", title, str(payload.get("pages") or 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "download ingest notification failed",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )


async def _notify_ingest_failed(payload: dict[str, Any], error: str) -> None:
    """Report a download whose files landed but whose import failed.

    Reuses the ``fail`` kind so it lands in the same Telegram digest and in-app
    notification ring, with a detail that says the download itself completed.
    Named ``notifier`` guard: without a notifier there is no channel (the
    callee would return immediately anyway), and the ingest state transition
    stays free of notification side effects.
    """
    if app_state.telegram is None:
        return
    gid = payload.get("gid")
    title = payload.get("title") or str(gid)
    settings = app_state.settings or get_settings()
    lang = normalize_lang(getattr(settings, "telegram_notify_lang", "zh"))
    try:
        await record_download_notification(
            "fail", title, download_ingest_fail_detail(error, lang)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "download ingest failure notification failed",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )


def _record_ingest_history(
    payload: dict[str, Any], *, ok: bool, error: str | None = None
) -> None:
    """Append the ingest outcome to the TaskManager ledger and persist it (G5)."""
    tm = app_state.task_manager
    if tm is None:
        return
    now = datetime.now(UTC).isoformat()
    gid = payload.get("gid")
    if ok:
        reason = f"gid {gid} ingested"
    else:
        reason = f"gid {gid} ingest failed: {error}"
    tm.record_task(
        "download-ingest",
        now,
        now,
        "success" if ok else "failed",
        reason=reason,
        done=1,
        total=1,
    )
async def _record_ingest_outcome(task_id: int, *, error: str | None) -> bool:
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return False
    try:
        async with session_cm() as session, session.begin():
            repo = DownloadRepository(session)
            if error is None:
                return await repo.mark_ingest_done(task_id)
            return await repo.mark_ingest_failed(task_id, error)
    except SQLAlchemyError as exc:
        logger.error(
            "download ingest state persistence failed",
            extra=log_extra(task_id=task_id, error=type(exc).__name__),
        )
        return False


async def run_pending_ingest_once() -> bool:
    """Ingest one persisted ``downloading + ingest_status='pending'`` row.

    Returns ``True`` when a row was claimed (and processed), ``False`` when the
    queue is empty. Safe to call from tests with a fresh pump instance: the
    queue lives in the database, not in process memory.
    """
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return False
    async with session_cm() as session:
        pending = await DownloadRepository(session).next_pending_ingest()
    if pending is None:
        return False
    task_id = int(pending["id"])
    payload = pending.get("ingest_payload") or {}
    if not payload:
        error = "missing ingest_payload"
        await _record_ingest_outcome(task_id, error=error)
        _record_ingest_history(payload, ok=False, error=error)
        return True
    try:
        await ingest_downloaded_gallery(ingest_result_from_payload(payload), strict=True)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        await _record_ingest_outcome(task_id, error=error)
        await _notify_ingest_failed(payload, error)
        _record_ingest_history(payload, ok=False, error=error)
        return True
    # ``success`` is only written here, after the gallery is in the library.
    if await _record_ingest_outcome(task_id, error=None):
        _record_ingest_history(payload, ok=True)
        await _notify_ingested(payload)
    return True


async def ingest_pump_loop() -> None:
    """DB-driven ingest pump: survives restarts and outlives download slots."""
    while True:
        try:
            if not _scan_running():
                for _ in range(_INGEST_PUMP_BATCH):
                    if not await run_pending_ingest_once():
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "download ingest pump iteration failed",
                extra=log_extra(error=type(exc).__name__),
            )
        await asyncio.sleep(_INGEST_PUMP_INTERVAL)


def maybe_scan_after_download(result: Any) -> None:
    """Deprecated no-op: ingestion is now driven by the DB queue.

    Kept as an import-compatible name for external callers/tests; the pump
    reads ``download_tasks.ingest_status='pending'`` rows instead of holding
    results in process memory.
    """
    return


async def download_progress(
    task_id: int | None,
    current_page: int,
    total_pages: int,
    archive_fallback: bool | None = None,
    gid: int | None = None,
) -> None:
    session_factory = _get_background_session_factory()
    if task_id is None or not session_factory:
        return
    try:
        async def _persist() -> None:
            async with session_factory() as session, session.begin():
                await DownloadRepository(session).progress(
                    task_id, current_page, total_pages, archive_fallback=archive_fallback
                )

        await asyncio.wait_for(_persist(), timeout=2.0)
    except TimeoutError:
        logger.warning(
            "download progress persistence timed out, skipping [task_id=%s gid=%s]",
            task_id,
            gid,
            extra=log_extra(task_id=task_id, gid=gid),
        )
    except SQLAlchemyError as exc:
        logger.warning(
            "download progress persistence failed",
            extra=log_extra(task_id=task_id, error=type(exc).__name__),
        )


async def record_download_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    notifier = app_state.telegram
    if notifier is None:
        return
    await notifier.record_download_outcome(kind, title, detail)
    settings = app_state.settings or get_settings()
    if settings.telegram_notify_level != "summary" or not notifier.pending_events:
        return
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            active = await DownloadRepository(session).count_active()
        if active == 0:
            await notifier.flush_summary()
    except SQLAlchemyError as exc:
        logger.warning(
            "telegram summary flush check failed", extra=log_extra(error=type(exc).__name__)
        )


async def record_archive_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    from .notifications import notify_archive

    notify_archive(kind, title, detail)
    notifier = app_state.telegram
    if notifier is None:
        return
    await notifier.record_archive_outcome(kind, title, detail, ring=False)
    settings = app_state.settings or get_settings()
    if (
        getattr(settings, "telegram_notify_level", "summary") != "summary"
        or not notifier.pending_archive_events
    ):
        return
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            active = await DownloadRepository(session).count_active()
        tm = app_state.task_manager
        archive_running = bool(tm.archive_state.get("running")) if tm else False
        if active == 0 and not archive_running:
            await notifier.flush_archive_summary()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telegram archive summary flush check failed",
            extra=log_extra(error=type(exc).__name__),
        )


async def telegram_flush_loop() -> None:
    while True:
        await asyncio.sleep(_TELEGRAM_FLUSH_INTERVAL)
        notifier = app_state.telegram
        if notifier is not None:
            try:
                if notifier.events_stale(_TELEGRAM_FLUSH_INTERVAL):
                    await notifier.flush_summary()
                if hasattr(notifier, "archive_events_stale") and notifier.archive_events_stale(
                    _TELEGRAM_FLUSH_INTERVAL
                ):
                    await notifier.flush_archive_summary()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "telegram summary flush failed",
                    extra=log_extra(error=str(exc) or type(exc).__name__),
                )


def is_download_cancelled(task_id: int | None) -> bool:
    if task_id is None:
        return False
    tm = app_state.task_manager
    return bool(tm and tm.is_cancelled(task_id))


def clear_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.clear_cancelled(task_id)


def mark_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.request_cancel(task_id)


async def run_download(task: DownloadTask) -> None:
    if task.id is None:
        logger.warning("download task missing id; skipping", extra=log_extra(gid=task.gid))
        return
    with bind_log_context(worker="download", task_id=task.id, gid=task.gid):
        await _run_download_inner(task)


async def _apply_replacement(task: DownloadTask, exc: GalleryReplacedError) -> DownloadTask | None:
    session_cm = _get_background_session_factory()
    if session_cm is None or task.id is None:
        return None
    from .download_prepare import _local_gids

    local = await _local_gids([exc.new_gid])
    if exc.new_gid in local:
        logger.info(
            "download retarget skipped; newer gid already in library",
            extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
        )
        try:
            async with session_cm() as session, session.begin():
                await DownloadRepository(session).cancel(task.id)
        except SQLAlchemyError:
            pass
        return None
    ok = False
    try:
        async with session_cm() as session, session.begin():
            ok = await DownloadRepository(session).retarget(
                task.id, exc.new_gid, exc.new_token, exc.title, exc.title_jpn
            )
    except IntegrityError:
        ok = False
    if not ok:
        logger.info(
            "download retarget skipped; newer gid already queued",
            extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
        )
        return None
    settings = app_state.settings or get_settings()
    try:
        temp = Path(settings.download_root) / f".gv-{task.gid}"
        if temp.exists():
            import shutil

            from .storage_usage import safe_stat_size, storage_tracker

            sz = safe_stat_size(temp)
            shutil.rmtree(temp, ignore_errors=True)
            if sz > 0:
                storage_tracker.record_download_delta(-sz)
    except OSError:
        pass
    title = exc.title or str(exc.new_gid)
    tm = app_state.task_manager
    if tm:
        now = datetime.now(UTC).isoformat()
        tm.record_task(
            "download-updated",
            now,
            now,
            "success",
            reason=f"gid {exc.old_gid} -> {exc.new_gid}",
            done=1,
            total=1,
        )
    return DownloadTask(
        exc.new_gid,
        exc.new_token,
        title,
        task.id,
        task.max_retries,
        task.mode,
        task.category,
        max_pages=task.max_pages,
        quality=task.quality,
    )


async def _finalize_replacement_skip(task: DownloadTask, exc: GalleryReplacedError) -> None:
    """Write a terminal state when a replaced gallery could not be retargeted.

    Without this the row stays ``downloading`` forever and keeps occupying the
    unique active-gid index, blocking any later enqueue for the same gid.
    """
    session_cm = _get_background_session_factory()
    if session_cm is None or task.id is None:
        return
    message = f"替换链未能重定向：gid {exc.old_gid} -> {exc.new_gid}"
    try:
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None:
                return
            now = datetime.now(UTC)
            if row.status == "cancelled":
                row.finished_at = row.finished_at or now
            else:
                row.status = "failed"
                row.error_message = message
                row.retry_at = None
                row.finished_at = now
                row.updated_at = now
                # The source gid no longer exists on ExHentai, so requeueing it
                # is pointless: consume the budget so it stays terminal.
                row.retry_count = max(row.retry_count or 0, row.max_retries)
            await DownloadRepository(session).record_attempt(
                task.id, max(1, row.retry_count or 1), "failed", "GalleryReplacedError"
            )
    except SQLAlchemyError as db_exc:
        logger.error(
            "download replacement skip state persistence failed",
            extra=log_extra(
                task_id=task.id,
                gid=task.gid,
                error=str(db_exc) or type(db_exc).__name__,
            ),
        )


def _extract_http_meta(exc: BaseException) -> dict[str, Any]:
    resp = getattr(exc, "response", None)
    if resp is None:
        return {}
    meta: dict[str, Any] = {}
    status_code = getattr(resp, "status_code", None)
    if status_code is not None:
        meta["status_code"] = status_code
    headers = getattr(resp, "headers", None)
    if headers and hasattr(headers, "items"):
        summary = {
            str(k): str(v)
            for k, v in headers.items()
            if str(k).lower() in {"location", "server", "cf-ray", "content-type", "retry-after"}
        }
        if summary:
            meta["headers"] = summary
    return meta


_CHALLENGE_PROBE_INTERVAL = float(os.getenv("GV_CHALLENGE_PROBE_INTERVAL", "600"))
_MAX_CHALLENGE_PAUSES = max(1, int(os.getenv("GV_MAX_CHALLENGE_PAUSES", "5")))
# 302 challenges have their own per-task budget: pausing must not burn the
# retry budget, but an endless pause/resume/challenge loop must still
# terminate.
_challenge_counts: dict[int, int] = {}
# Created lazily on first use instead of at import time: asyncio primitives
# bind to the loop of their first waiter, and module import happens before any
# loop exists (report 01 P3-10).
_challenge_lock: asyncio.Lock | None = None
_challenge_lock_loop: asyncio.AbstractEventLoop | None = None
_last_resume_time = 0.0
_RESUME_DEBOUNCE_SECONDS = float(os.getenv("GV_RESUME_DEBOUNCE_SECONDS", "1.0"))


def _get_challenge_lock() -> asyncio.Lock:
    """Return a challenge lock bound to the current event loop."""
    global _challenge_lock, _challenge_lock_loop
    loop = asyncio.get_running_loop()
    if _challenge_lock is None or _challenge_lock_loop is not loop:
        _challenge_lock = asyncio.Lock()
        _challenge_lock_loop = loop
    return _challenge_lock


def challenge_count(task_id: int | None) -> int:
    if task_id is None:
        return 0
    return _challenge_counts.get(int(task_id), 0)


def reset_challenge_count(task_id: int | None) -> None:
    if task_id is None:
        return
    _challenge_counts.pop(int(task_id), None)


def _bump_challenge_count(task_id: int | None) -> int:
    if task_id is None:
        return 1
    count = _challenge_counts.get(int(task_id), 0) + 1
    _challenge_counts[int(task_id)] = count
    return count


async def _trigger_challenge_pause(
    sample_path: str | None = None,
    *,
    task_id: int | None = None,
    gid: int | None = None,
    response_meta: dict[str, Any] | None = None,
) -> None:
    """Trigger global pause due to ExHentai 302 anti-abuse challenge."""
    async with _get_challenge_lock():
        if app_state.extra.get("auto_resume_challenge") and getattr(
            app_state.settings or get_settings(), "global_paused", False
        ):
            if sample_path and not app_state.extra.get("challenge_sample_path"):
                app_state.extra["challenge_sample_path"] = sample_path
            return
        app_state.extra["auto_resume_challenge"] = True
        if sample_path:
            app_state.extra["challenge_sample_path"] = sample_path

        from .settings_service import update_runtime_settings

        update_runtime_settings({"global_paused": True})

        session_factory = _get_background_session_factory()
        if session_factory:
            try:
                from ..db.repositories.settings import patch_settings
                from ..db.repository import SettingsRepository

                async with session_factory() as session, session.begin():
                    await patch_settings(SettingsRepository(session), {"global_paused": True})
            except Exception as exc:
                err_extra: dict[str, Any] = {"error": str(exc)}
                if task_id is not None:
                    err_extra["task_id"] = task_id
                if gid is not None:
                    err_extra["gid"] = gid
                if response_meta:
                    err_extra.update(response_meta)
                logger.exception(
                    "failed to persist global_paused setting on challenge",
                    extra=log_extra(**err_extra),
                )

        if app_state.telegram is not None:
            try:
                await app_state.telegram.send_message("🚨 触发 302 临时挑战，系统自动暂停下载")
            except Exception as exc:  # noqa: BLE001
                alert_extra: dict[str, Any] = {"error": type(exc).__name__}
                if task_id is not None:
                    alert_extra["task_id"] = task_id
                if gid is not None:
                    alert_extra["gid"] = gid
                logger.warning(
                    "failed to send challenge telegram alert",
                    extra=log_extra(**alert_extra),
                )


async def _resume_challenge_pause() -> None:
    """Resume global pause after ExHentai 302 anti-abuse challenge clears."""
    global _last_resume_time
    async with _get_challenge_lock():
        if not app_state.extra.get("auto_resume_challenge") and not getattr(
            app_state.settings or get_settings(), "global_paused", False
        ):
            return
        now_ts = _time.monotonic()
        if now_ts - _last_resume_time < _RESUME_DEBOUNCE_SECONDS and not app_state.extra.get("auto_resume_challenge"):
            return
        _last_resume_time = now_ts
        app_state.extra["auto_resume_challenge"] = False
        app_state.extra.pop("challenge_sample_path", None)

        from .settings_service import update_runtime_settings

        update_runtime_settings({"global_paused": False})

        session_factory = _get_background_session_factory()
        if session_factory:
            try:
                from ..db.repositories.settings import patch_settings
                from ..db.repository import SettingsRepository

                async with session_factory() as session, session.begin():
                    await patch_settings(SettingsRepository(session), {"global_paused": False})
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to persist global_paused setting on resume",
                    extra=log_extra(error=str(exc)),
                )

        notify_new_task()

        if app_state.telegram is not None:
            try:
                await app_state.telegram.send_message("✅ 302 临时挑战解除，自动恢复下载")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "failed to send challenge resume telegram alert",
                    extra=log_extra(error=type(exc).__name__),
                )


async def challenge_probe_loop() -> None:
    """Periodically probe ExHentai if paused due to anti-abuse challenge."""
    while True:
        try:
            await asyncio.sleep(_CHALLENGE_PROBE_INTERVAL)
            settings = app_state.settings or get_settings()
            if not getattr(settings, "global_paused", False) or not app_state.extra.get(
                "auto_resume_challenge"
            ):
                continue

            client = app_state.eh_client
            if client is None and app_state.downloader is not None:
                client = getattr(app_state.downloader, "client", None)
            if client is None:
                continue

            sample_path = app_state.extra.get("challenge_sample_path", "/")
            cleared = await client.probe_challenge(sample_path)
            if cleared:
                logger.info("ExHentai anti-abuse challenge has cleared; resuming downloads")
                await _resume_challenge_pause()
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("challenge probe failed", extra=log_extra(error=type(exc).__name__))


async def _run_download_inner(
    task: DownloadTask,
    *,
    follow_hops: int = 0,
    replaced_from_gid: int | None = None,
) -> None:
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return
    downloader = app_state.downloader
    if downloader is None:
        return
    notify_fn = record_download_notification

    row = None
    exec_task: DownloadTask | None = None
    try:
        if is_download_cancelled(task.id):
            raise DownloadCancelledError("download was cancelled")

        attempt_no = 1
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None or row.status == "cancelled" or is_download_cancelled(task.id):
                if row is not None and row.status != "cancelled":
                    row.status = "cancelled"
                    row.finished_at = datetime.now(UTC)
                clear_download_cancelled(task.id)
                return
            row.status = "downloading"
            # ``started_at`` is the first start of the task, not of the latest
            # retry: overwriting it on every attempt loses that (report 01 P3-3).
            if getattr(row, "started_at", None) is None:
                row.started_at = datetime.now(UTC)
            attempt_no = (getattr(row, "retry_count", 0) or 0) + 1

        exec_task = DownloadTask(
            task.gid,
            task.token,
            task.title,
            task.id,
            1,
            task.mode,
            task.category,
            max_pages=task.max_pages,
            quality=task.quality,
            archive_fallback=bool(getattr(task, "archive_fallback", False)),
        )

        progress_state = {"last_persisted": 0, "last_flush": 0.0}

        async def _on_progress(current: int, total: int) -> None:
            if is_download_cancelled(task.id):
                raise DownloadCancelledError("download was cancelled")
            now = _time.monotonic()
            if (
                current >= total
                or progress_state["last_persisted"] == 0
                or current - progress_state["last_persisted"] >= _PROGRESS_FLUSH_STEP
                or now - progress_state["last_flush"] >= _PROGRESS_FLUSH_INTERVAL
            ):
                if task.id is not None:
                    is_fb = bool(getattr(exec_task, "archive_fallback", False))
                    await download_progress(
                        task.id,
                        current,
                        total,
                        archive_fallback=True if is_fb else None,
                        gid=getattr(task, "gid", None),
                    )
                progress_state["last_persisted"] = current
                progress_state["last_flush"] = now

        if is_download_cancelled(task.id):
            raise DownloadCancelledError("download was cancelled")

        result = await downloader.execute(
            exec_task,
            progress=_on_progress,
        )
        if is_download_cancelled(task.id):
            if result and hasattr(result, "path") and Path(result.path).exists():
                import shutil

                p = Path(result.path)
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            raise DownloadCancelledError("download was cancelled")
        now = datetime.now(UTC)
        # Files are on disk: the task stays ``downloading`` until the ingest
        # pump has actually inserted the gallery (INV-DL-1). ``success`` is
        # written by the pump only after a successful import.
        update_values: dict[str, Any] = {
            "target_path": str(result.path),
            "category": result.category,
            "error_message": None,
            "retry_count": 0,
            "retry_at": None,
            "ingest_status": "pending",
            "ingest_payload": serialize_ingest_payload(result),
            "updated_at": now,
        }
        if getattr(exec_task, "archive_fallback", False):
            update_values["archive_fallback"] = True
        if result.title:
            update_values["title"] = result.title
        if getattr(result, "title_jpn", None):
            update_values["title_jpn"] = result.title_jpn
        if getattr(result, "pages", None):
            update_values["current_page"] = func.coalesce(
                DownloadTaskModel.total_pages, result.pages
            )
            update_values["total_pages"] = func.coalesce(
                DownloadTaskModel.total_pages, result.pages
            )

        async with session_cm() as session, session.begin():
            # Resolve the notification wording *before* the library insert: the
            # gallery does not exist yet, so a fresh download stays ``ok``.
            ingest_payload = update_values["ingest_payload"]
            ingest_payload["notify_old_gid"] = await _resolve_notify_old_gid(
                session, task.gid, replaced_from_gid
            )
            if hasattr(session, "execute"):
                stmt = (
                    update(DownloadTaskModel)
                    .where(
                        DownloadTaskModel.id == task.id,
                        DownloadTaskModel.status == "downloading",
                    )
                    .values(**update_values)
                )
                update_result = await session.execute(stmt)
                is_cancelled = bool(update_result.rowcount == 0)
            else:
                row = await session.get(DownloadTaskModel, task.id)
                if (
                    row is None
                    or row.status != "downloading"
                    or is_download_cancelled(task.id)
                ):
                    is_cancelled = True
                else:
                    is_cancelled = False
                    row.status = "downloading"
                    row.target_path = update_values.get("target_path")
                    row.category = update_values.get("category")
                    row.error_message = None
                    row.retry_count = 0
                    row.retry_at = None
                    row.ingest_status = "pending"
                    row.ingest_payload = update_values.get("ingest_payload")
                    if "archive_fallback" in update_values:
                        row.archive_fallback = update_values["archive_fallback"]
                    if "title" in update_values:
                        row.title = update_values["title"]
                    if "title_jpn" in update_values:
                        row.title_jpn = update_values["title_jpn"]
                    if getattr(result, "pages", None):
                        row.current_page = getattr(row, "total_pages", None) or result.pages
                        row.total_pages = getattr(row, "total_pages", None) or result.pages

            if is_cancelled:
                if result and hasattr(result, "path") and Path(result.path).exists():
                    import shutil

                    p = Path(result.path)
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                raise DownloadCancelledError("download was cancelled")

            await DownloadRepository(session).record_attempt(
                task.id or 0, attempt_no, "success"
            )

        clear_download_cancelled(task.id)
        reset_challenge_count(task.id)
        logger.info(
            "download finished; queued for ingest",
            extra=log_extra(task_id=task.id, gid=task.gid, path=str(result.path)),
        )
    except GalleryReplacedError as exc:
        from .download_prepare import MAX_FOLLOW_HOPS

        if follow_hops >= MAX_FOLLOW_HOPS:
            logger.warning(
                "download replacement hop limit",
                extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
            )
            try:
                async with session_cm() as session, session.begin():
                    row = await session.get(DownloadTaskModel, task.id)
                    if row is not None and row.status != "cancelled":
                        row.status = "failed"
                        row.error_message = HOPS_DETAIL
                        row.retry_count = row.max_retries
                        row.finished_at = datetime.now(UTC)
            except SQLAlchemyError:
                pass
            return
        rewritten = await _apply_replacement(task, exc)
        if rewritten is None:
            await _finalize_replacement_skip(task, exc)
            return
        await _run_download_inner(
            rewritten,
            follow_hops=follow_hops + 1,
            replaced_from_gid=replaced_from_gid or exc.old_gid,
        )
    except DownloadCancelledError:
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row is not None and row.status != "cancelled":
                    row.status = "cancelled"
                    row.finished_at = datetime.now(UTC)
        except SQLAlchemyError:
            pass
        settings = app_state.settings or get_settings()
        try:
            temp = Path(settings.download_root) / f".gv-{task.gid}"
            if temp.exists():
                import shutil

                from .storage_usage import safe_stat_size, storage_tracker

                sz = safe_stat_size(temp)
                shutil.rmtree(temp, ignore_errors=True)
                if sz > 0:
                    storage_tracker.record_download_delta(-sz)
        except OSError:
            pass
        clear_download_cancelled(task.id)
        logger.info("download cancelled", extra=log_extra(gid=task.gid))
    except EhChallengeError as exc:
        http_meta = _extract_http_meta(exc)
        challenge_extra: dict[str, Any] = {
            "task_id": task.id,
            "gid": task.gid,
            "error": str(exc),
        }
        challenge_extra.update(http_meta)
        logger.warning(
            "download challenge encountered; auto-pausing downloads",
            extra=log_extra(**challenge_extra),
        )
        now = datetime.now(UTC)
        count = _bump_challenge_count(task.id)
        over_budget = count >= _MAX_CHALLENGE_PAUSES
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    if over_budget:
                        # Stop the pause/resume/challenge loop, but keep the
                        # remaining retry budget so a manual retry can still
                        # pick the task up later.
                        row.status = "failed"
                        row.retry_at = None
                        row.finished_at = now
                        row.retry_count = min(
                            max(0, row.retry_count or 0), max(0, row.max_retries - 1)
                        )
                        row.error_message = (
                            f"自动暂停失败：302 临时挑战已达上限 "
                            f"({count}/{_MAX_CHALLENGE_PAUSES})"
                        )
                    else:
                        row.status = "pending"
                        row.retry_at = now + timedelta(
                            seconds=retry_backoff(max(1, count))
                        )
                        row.error_message = (
                            f"自动暂停：检测到 ExHentai 302 临时挑战 "
                            f"({count}/{_MAX_CHALLENGE_PAUSES})"
                        )
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, max(1, row.retry_count or 1), "challenged", "EhChallengeError"
                    )
        except SQLAlchemyError as db_exc:
            logger.exception(
                "download status persistence failed on challenge",
                extra=log_extra(
                    task_id=task.id,
                    gid=task.gid,
                    error=str(db_exc) or type(db_exc).__name__,
                ),
            )
        if over_budget:
            logger.error(
                "302 challenge budget exhausted; failing task",
                extra=log_extra(
                    task_id=task.id,
                    gid=task.gid,
                    challenges=count,
                    limit=_MAX_CHALLENGE_PAUSES,
                ),
            )
        sample_path = f"/g/{task.gid}/{task.token}/" if task.token else "/"
        await _trigger_challenge_pause(
            sample_path,
            task_id=task.id,
            gid=task.gid,
            response_meta=http_meta,
        )
    except Exception as exc:
        http_meta = _extract_http_meta(exc)
        fail_extra: dict[str, Any] = {
            "task_id": task.id,
            "gid": task.gid,
            "error": type(exc).__name__,
            "message": str(exc),
        }
        fail_extra.update(http_meta)
        logger.exception(
            "download task failed",
            extra=log_extra(**fail_extra),
        )
        try:
            gone = False
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    now = datetime.now(UTC)
                    auth_failure = "authenticat" in str(exc)
                    gone = isinstance(exc, GalleryGoneError) or "does not exist on ExHentai" in str(
                        exc
                    )
                    not_retryable = (
                        isinstance(exc, (ArchiveNotRetryableError, GalleryGoneError))
                        or gone
                    )
                    row.retry_count += 1
                    if auth_failure or not_retryable or row.retry_count >= row.max_retries:
                        row.status = "failed"
                        row.retry_at = None
                        row.finished_at = now
                        row.retry_count = max(row.retry_count, row.max_retries)
                    else:
                        row.status = "pending"
                        # Always apply exponential backoff for transient errors so a
                        # just-failed task in not re-claimed immediately. The old
                        # `challenge ? backoff : now` caused non-challenge
                        # EhClientError to be retried in <1s, burning the retry budget.
                        row.retry_at = now + timedelta(seconds=retry_backoff(row.retry_count))
                    if exec_task is not None and getattr(exec_task, "archive_fallback", False):
                        row.archive_fallback = True
                    row.error_message = GONE_DETAIL if gone else f"{type(exc).__name__}: {exc}"
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, row.retry_count, "failed", type(exc).__name__
                    )
            if row is not None and row.status == "failed":
                await notify_fn(
                    "fail",
                    task.title or str(task.gid),
                    GONE_DETAIL if gone else type(exc).__name__,
                )
        except SQLAlchemyError as db_exc:
            logger.error(
                "download status persistence failed",
                extra=log_extra(error=str(db_exc) or type(db_exc).__name__),
            )


def _effective_download_concurrency(concurrency: int | None = None) -> int:
    if concurrency is None:
        settings = app_state.settings or get_settings()
        concurrency = getattr(settings, "download_concurrency", 2)
    c = max(1, int(concurrency))
    try:
        engine = app_state.engine
        if engine is not None and getattr(engine.dialect, "name", "") == "sqlite":
            c = 1
    except Exception:  # noqa: BLE001, S110
        pass
    return c


async def _download_worker() -> None:
    global _worker_tasks
    my_event = asyncio.Event()
    _worker_events.add(my_event)
    try:
        while True:
            my_event.clear()
            try:
                # Cooperative drain: if target concurrency decreased, exit after completing current gallery
                current_task = asyncio.current_task()
                _worker_tasks = [t for t in _worker_tasks if not t.done()]
                if current_task is not None and current_task not in _worker_tasks:
                    return
                if len(_worker_tasks) > _target_download_concurrency:
                    if current_task in _worker_tasks:
                        _worker_tasks.remove(current_task)
                    logger.info(
                        "Download worker exiting cooperatively for concurrency drain",
                        extra=log_extra(current=len(_worker_tasks), target=_target_download_concurrency),
                    )
                    return

                # Global pause: stop claiming new galleries (current page finishes)
                try:
                    _settings = app_state.settings or get_settings()
                    if getattr(_settings, "global_paused", False):
                        await asyncio.sleep(5)
                        continue
                except Exception:  # noqa: BLE001, S110
                    pass
                row = None
                poll_timeout = _WORKER_POLL_MAX_SECONDS
                session_factory = _get_background_session_factory()
                if not session_factory:
                    await asyncio.sleep(0.5)
                    continue
                async with session_factory() as session, session.begin():
                    repo = DownloadRepository(session)
                    row = await repo.claim_pending()
                    if row is None:
                        poll_timeout = _idle_poll_timeout(await repo.next_retry_at())
                    if row is not None:
                        task = DownloadTask(
                            row.gid,
                            row.token,
                            row.title or str(row.gid),
                            row.id,
                            row.max_retries,
                            row.mode,
                            row.category or "other",
                            max_pages=row.max_pages,
                            quality=row.quality,
                        )
                if row is not None:
                    try:
                        await run_download(task)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.exception(
                            "run_download unhandled exception",
                            extra=log_extra(task_id=task.id, gid=task.gid, error=str(exc) or type(exc).__name__),
                        )
                        if session_factory and task.id:
                            try:
                                async with session_factory() as session, session.begin():
                                    r = await session.get(DownloadTaskModel, task.id)
                                    if r and r.status not in ("cancelled", "failed"):
                                        now = datetime.now(UTC)
                                        r.retry_count += 1
                                        if r.retry_count >= r.max_retries:
                                            r.status = "failed"
                                            r.retry_at = None
                                            r.finished_at = now
                                        else:
                                            r.status = "pending"
                                            r.retry_at = now + timedelta(seconds=retry_backoff(r.retry_count))
                                        r.error_message = f"UnhandledWorkerError: {exc}"
                                        r.updated_at = now
                            except Exception:  # noqa: BLE001, S110
                                pass
                else:
                    # Bounded wait: the event only short-circuits the timeout, so
                    # a retry whose retry_at becomes due is re-claimed without any
                    # external wakeup (and with no retry scheduled we still poll
                    # at least once per _WORKER_POLL_MAX_SECONDS).
                    try:
                        await asyncio.wait_for(my_event.wait(), timeout=poll_timeout)
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "download worker iteration failed",
                    extra=log_extra(error=str(exc) or type(exc).__name__),
                )
                await asyncio.sleep(2)
    finally:
        _worker_events.discard(my_event)


def adjust_download_concurrency(new_concurrency: int | None = None) -> None:
    global _worker_tasks, _target_download_concurrency
    target = _effective_download_concurrency(new_concurrency)
    _target_download_concurrency = target
    # Keep the downloader's in-flight limit in sync too: it was fixed when the
    # instance was built, so extra workers used to claim a row and then block
    # on the old limit (report 01 P3-5).
    downloader = app_state.downloader
    if downloader is not None and hasattr(downloader, "set_concurrency"):
        downloader.set_concurrency(target)
    _worker_tasks = [t for t in _worker_tasks if not t.done()]
    current = len(_worker_tasks)
    if target > current:
        for _ in range(target - current):
            _worker_tasks.append(asyncio.create_task(_download_worker()))
        logger.info(
            "Adjusted download concurrency",
            extra=log_extra(previous=current, target=target, current=len(_worker_tasks)),
        )
    elif target < current:
        logger.info(
            "Set target download concurrency for cooperative drain",
            extra=log_extra(previous=current, target=target, current=len(_worker_tasks)),
        )
        notify_new_task()


async def stop_download_workers() -> None:
    """Cancel supervisor-owned download workers and wait for them to stop.

    Called on shutdown (before engines are disposed) and whenever the
    supervisor exits, so child workers never outlive their owner.
    """
    global _worker_tasks
    pending = [t for t in _worker_tasks if not t.done()]
    _worker_tasks = [t for t in _worker_tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _worker_tasks = []
    _worker_events.clear()


async def download_worker_loop() -> None:
    """Recover and claim persisted jobs continuously."""
    global _worker_tasks, _target_download_concurrency
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session, session.begin():
            await DownloadRepository(session).recover_orphans()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "download recovery failed",
            extra=log_extra(error=str(exc) or type(exc).__name__),
        )

    adjust_download_concurrency()

    probe_task = asyncio.create_task(challenge_probe_loop())

    try:
        while True:
            await asyncio.sleep(10)
            _worker_tasks = [t for t in _worker_tasks if not t.done()]
            settings = app_state.settings or get_settings()
            target = _effective_download_concurrency(settings.download_concurrency)
            _target_download_concurrency = target
            downloader = app_state.downloader
            if downloader is not None and hasattr(downloader, "set_concurrency"):
                downloader.set_concurrency(target)
            if len(_worker_tasks) < target:
                for _ in range(target - len(_worker_tasks)):
                    _worker_tasks.append(asyncio.create_task(_download_worker()))
    finally:
        # Runs on cancellation *and* on an unexpected crash of the supervisor:
        # without this, orphaned page writers keep running after engine dispose.
        probe_task.cancel()
        await asyncio.gather(probe_task, return_exceptions=True)
        await stop_download_workers()
