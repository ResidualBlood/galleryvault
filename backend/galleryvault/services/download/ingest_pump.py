"""Post-download ingest, cold-archive hook and the DB-driven ingest pump."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...app.state import app_state
from ...config import get_settings
from ...db.models import DownloadTask as DownloadTaskModel
from ...db.models import Gallery, GalleryUpdate
from ...db.repository import DownloadRepository
from ...logging import log_extra
from ...scanners import registry
from ...scanners.base import GalleryMeta, PageInfo
from ...scanners.ehviewer import IMAGE_EXTENSIONS, natural_key
from ..deletion import (
    collapse_same_stem_pages,
    prune_merged_stale_pages,
    remove_superseded_copy,
)
from ..duplicate_resolver import (
    DEFAULT_DUPLICATE_POLICY,
    Copy,
    ResolvedGroup,
)
from ..ingest import GalleryIngestService
from ..messages import download_ingest_fail_detail, normalize_lang
from . import wake
from .notify import record_archive_notification, record_download_notification

logger = logging.getLogger("galleryvault.services.download_worker")


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
    session_cm = wake._get_background_session_factory()
    if session_cm is None:
        logger.warning(
            "cannot register superseded copy without a session factory",
            extra=log_extra(gid=gid, path=str(old_path)),
        )
        return

    from ...db.repositories.duplicates import DuplicateGroupRepository

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

    from ...app import dependencies

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
        session_cm = wake._get_background_session_factory()
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
            from ..updates_worker import finalize_updates_for_new_gid

            await finalize_updates_for_new_gid(int(result.gid))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gallery update finalize after ingest failed",
                extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__),
            )
        try:
            settings = app_state.settings or get_settings()
            auto_archive = bool(getattr(settings, "auto_archive_downloads", True))
            from ..cold_archive import resolve_archive_roots

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
                from ...app.dependencies import spawn_task

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
    session_cm = wake._get_background_session_factory()
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
        from .. import cold_archive

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
    session_cm = wake._get_background_session_factory()
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
    session_cm = wake._get_background_session_factory()
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

