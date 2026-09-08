#!/usr/bin/env python3
"""
backend/galleryvault/scripts/repair_cold_archives.py

Scans cold archived galleries in the database, identifies files with double GID
prefixes (e.g., {gid}-{gid}-... or contaminated title paths), computes the canonical
storage path using current safe_title and strip_gid_prefix rules, and renames files
on disk while updating galleries.storage_path in the database.

Safety:
  - Defaults to --dry-run mode (read-only preview).
  - Requires --execute to perform atomic renames and commit DB changes.
  - Skips safely if destination exists or source is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from galleryvault.config import get_settings
from galleryvault.db.models import Gallery
from galleryvault.services.cold_archive import compute_cold_path, resolve_archive_roots

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("repair_cold_archives")


def parse_cold_storage_info(
    storage_path: str,
    configured_cold_roots: list[Path],
    override_cold_root: Path | None = None,
) -> tuple[Path | str, str, bool] | None:
    """Parse cold storage root, sub-scheme and relative components from storage_path."""
    raw = storage_path.strip()
    if not raw:
        return None

    if raw.startswith("cold:"):
        inner = raw[5:].lstrip("/")
        parts = inner.split("/")
        if len(parts) >= 4 and parts[0] in {"cbz", "dir", "ungid"}:
            if override_cold_root:
                return override_cold_root, inner, True
            return "cold", inner, True
        return None

    p = Path(raw)
    parts = p.parts
    if len(parts) >= 4:
        sub_type = parts[-4]
        if sub_type in {"cbz", "ungid", "dir"}:
            hh, ii = parts[-3], parts[-2]
            if len(hh) == 2 and len(ii) == 2:
                inferred_root = Path(*parts[:-4]) if len(parts) > 4 else Path("/")
                cold_root = override_cold_root or inferred_root
                return cold_root, sub_type, False

    for cr in configured_cold_roots:
        try:
            rel = p.relative_to(cr)
            rel_parts = rel.parts
            if len(rel_parts) >= 4 and rel_parts[0] in {"cbz", "ungid", "dir"}:
                return (override_cold_root or cr), rel_parts[0], False
        except ValueError:
            continue

    return None


async def repair_cold_archives(
    db_url: str | AsyncEngine | async_sessionmaker[AsyncSession],
    execute: bool = False,
    cold_root_override: Path | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Inspect and repair double GID filenames and contaminated cold archive paths."""
    configured_roots = resolve_archive_roots()

    should_dispose = False
    if isinstance(db_url, str):
        url = db_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        should_dispose = True
    elif isinstance(db_url, AsyncEngine):
        engine = db_url
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    else:
        session_factory = db_url

    total_scanned = 0
    cold_archived_count = 0
    double_gid_count = 0
    needs_repair_count = 0
    repaired_count = 0
    skipped_missing_source = 0
    skipped_conflict = 0
    skipped_error = 0

    try:
        async with session_factory() as session:
            query = (
                select(Gallery)
                .where(Gallery.storage_path.isnot(None), Gallery.storage_path != "")
                .order_by(Gallery.id)
            )
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            galleries = result.scalars().all()
            total_scanned = len(galleries)

            for gallery in galleries:
                raw_path = gallery.storage_path
                cold_info = parse_cold_storage_info(
                    raw_path,
                    configured_roots,
                    override_cold_root=cold_root_override,
                )
                if not cold_info:
                    continue

                cold_archived_count += 1
                cold_root, _sub_type, is_prefix = cold_info

                is_cbz = raw_path.lower().endswith(".cbz") or gallery.storage_type == "cbz"

                try:
                    computed = compute_cold_path(
                        cold_root
                        if not isinstance(cold_root, str) or cold_root != "cold"
                        else Path("/cold_placeholder"),
                        is_cbz=is_cbz,
                        gid=gallery.gid,
                        title=gallery.title,
                        stable=gallery.path_hash,
                    )
                except (ValueError, TypeError, OSError) as exc:
                    logger.warning(
                        "Failed to compute cold path for Gallery ID %d (gid=%s): %s",
                        gallery.id,
                        gallery.gid,
                        exc,
                    )
                    continue

                if is_prefix and isinstance(cold_root, str) and cold_root == "cold":
                    rel_computed = computed.relative_to(Path("/cold_placeholder"))
                    expected_storage_path = f"cold:{rel_computed}"
                else:
                    expected_storage_path = str(computed)

                filename = Path(raw_path).name
                has_double_gid = False
                if gallery.gid is not None:
                    gid_s = str(gallery.gid)
                    if filename.startswith(f"{gid_s}-{gid_s}-") or f"{gid_s}_{gid_s}_" in filename:
                        has_double_gid = True
                        double_gid_count += 1

                if expected_storage_path == raw_path:
                    continue

                needs_repair_count += 1
                old_p = Path(raw_path)
                new_p = Path(expected_storage_path)

                tag_log = "[DOUBLE GID]" if has_double_gid else "[PATH MISMATCH]"
                logger.info(
                    "%s Gallery ID %d | GID %s\n  Old: %s\n  New: %s",
                    tag_log,
                    gallery.id,
                    gallery.gid,
                    raw_path,
                    expected_storage_path,
                )

                if not execute:
                    continue

                if not old_p.exists():
                    logger.warning(
                        "[SKIP: SOURCE MISSING] Gallery ID %d: source file not found on disk: %s",
                        gallery.id,
                        old_p,
                    )
                    skipped_missing_source += 1
                    continue

                if new_p.exists() and new_p != old_p:
                    logger.error(
                        "[SKIP: CONFLICT] Gallery ID %d: target file already exists on disk: %s",
                        gallery.id,
                        new_p,
                    )
                    skipped_conflict += 1
                    continue

                try:
                    new_p.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(old_p, new_p)
                    gallery.storage_path = expected_storage_path
                    repaired_count += 1
                    logger.info(
                        "[SUCCESS] Renamed on disk and updated DB for Gallery ID %d",
                        gallery.id,
                    )
                except OSError as exc:
                    logger.error(
                        "[ERROR] Failed to rename on disk for Gallery ID %d (%s -> %s): %s",
                        gallery.id,
                        old_p,
                        new_p,
                        exc,
                    )
                    skipped_error += 1

            if execute and repaired_count > 0:
                await session.commit()
                logger.info(
                    "Successfully committed DB changes for %d galleries.", repaired_count
                )
    finally:
        if should_dispose:
            await engine.dispose()

    summary = {
        "total_scanned": total_scanned,
        "cold_archived": cold_archived_count,
        "double_gid_detected": double_gid_count,
        "needs_repair": needs_repair_count,
        "repaired": repaired_count,
        "skipped_missing_source": skipped_missing_source,
        "skipped_conflict": skipped_conflict,
        "skipped_error": skipped_error,
    }

    logger.info("================ Summary ================")
    logger.info("Total galleries scanned:    %d", summary["total_scanned"])
    logger.info("Cold archived galleries:    %d", summary["cold_archived"])
    logger.info("Double GID detected:        %d", summary["double_gid_detected"])
    logger.info("Galleries needing repair:   %d", summary["needs_repair"])
    if execute:
        logger.info("Successfully repaired:      %d", summary["repaired"])
        logger.info("Skipped (source missing):   %d", summary["skipped_missing_source"])
        logger.info("Skipped (target conflict):  %d", summary["skipped_conflict"])
        logger.info("Skipped (disk error):       %d", summary["skipped_error"])
    else:
        logger.info("Run with --execute to perform atomic rename and update DB.")
    logger.info("=========================================")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair cold archive double GID filenames and contaminated storage paths."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--execute",
        action="store_true",
        help="Execute disk rename and commit DB changes. Without this flag, runs in dry-run mode.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without modifying disk or DB (default).",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database URL (defaults to DATABASE_URL env var or Settings.database_url).",
    )
    parser.add_argument(
        "--cold-root",
        type=str,
        default=None,
        help="Override cold archive root path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of galleries to process.",
    )

    args = parser.parse_args()
    execute = bool(args.execute)

    settings = get_settings()
    db_url = args.db_url or os.environ.get("DATABASE_URL") or settings.database_url

    cold_root_override = Path(args.cold_root).resolve() if args.cold_root else None

    asyncio.run(
        repair_cold_archives(
            db_url=db_url,
            execute=execute,
            cold_root_override=cold_root_override,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    main()
