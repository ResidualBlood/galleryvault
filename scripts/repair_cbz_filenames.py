#!/usr/bin/env python3
"""
scripts/repair_cbz_filenames.py

Scans galleries in the database whose storage_path points to cold archive
(e.g., {cold_root}/cbz/..., {cold_root}/ungid/..., or cold:*), recalculates
the expected destination path using the updated safe_title and byte-truncation
rules (Linux 255 bytes / 251 bytes base for .cbz), and if the filename has
changed:
  1. Atomically renames the file/directory on disk (os.replace).
  2. Updates galleries.storage_path in the database.

Safety:
  - Defaults to --dry-run mode (no disk modification, no DB commit).
  - Explicit --execute required to apply changes.
  - Skips safely if destination path already exists or source is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add backend directory to sys.path so galleryvault can be imported directly
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from galleryvault.config import get_settings
from galleryvault.db.models import Gallery
from galleryvault.services.cold_archive import compute_cold_path, resolve_archive_roots
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("repair_cbz_filenames")


def parse_cold_storage_info(
    storage_path: str,
    configured_cold_roots: list[Path],
    override_cold_root: Path | None = None,
) -> tuple[Path | str, str, bool] | None:
    """Parse cold storage root, sub-scheme and relative components from storage_path.

    Returns:
        tuple of (cold_root, partition_relative_or_format, is_prefix_form) or None.
    """
    raw = storage_path.strip()
    if not raw:
        return None

    # Handle logical prefix form e.g. "cold:cbz/..." or "cold:dir/..."
    if raw.startswith("cold:"):
        inner = raw[5:].lstrip("/")
        parts = inner.split("/")
        if len(parts) >= 4 and parts[0] in {"cbz", "dir", "ungid"}:
            if override_cold_root:
                return override_cold_root, inner, True
            return "cold", inner, True
        return None

    # Handle absolute or relative filesystem paths
    p = Path(raw)
    parts = p.parts
    # Pattern: ... / (cbz | ungid | dir) / {hh} / {ii} / {filename}
    if len(parts) >= 4:
        sub_type = parts[-4]
        if sub_type in {"cbz", "ungid", "dir"}:
            # Validate {hh} and {ii} are 2-char hexadecimal
            hh, ii = parts[-3], parts[-2]
            if len(hh) == 2 and len(ii) == 2:
                inferred_root = Path(*parts[:-4]) if len(parts) > 4 else Path("/")
                cold_root = override_cold_root or inferred_root
                return cold_root, sub_type, False

    # Check if path is under any configured cold root
    for cr in configured_cold_roots:
        try:
            rel = p.relative_to(cr)
            rel_parts = rel.parts
            if len(rel_parts) >= 4 and rel_parts[0] in {"cbz", "ungid", "dir"}:
                return (override_cold_root or cr), rel_parts[0], False
        except ValueError:
            continue

    return None


async def repair_cbz_filenames(
    db_url: str,
    execute: bool,
    cold_root_override: Path | None = None,
    limit: int | None = None,
) -> None:
    configured_roots = resolve_archive_roots()

    logger.info(
        "Connecting to database: %s", db_url.split("@")[-1] if "@" in db_url else db_url
    )
    logger.info("Configured archive roots: %s", [str(r) for r in configured_roots])
    if cold_root_override:
        logger.info("Cold root override: %s", cold_root_override)
    logger.info(
        "Mode: %s",
        "EXECUTE (modifying disk & DB)" if execute else "DRY-RUN (read-only preview)",
    )

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    total_scanned = 0
    cold_archived_count = 0
    needs_repair_count = 0
    repaired_count = 0
    skipped_missing_source = 0
    skipped_conflict = 0
    skipped_error = 0

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
        logger.info(
            "Found %d gallery records with non-empty storage_path", total_scanned
        )

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

            # Check if this is a CBZ file or directory
            is_cbz = raw_path.lower().endswith(".cbz") or gallery.storage_type == "cbz"

            # Recalculate destination path with updated rules
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
                # Logical prefix form: cold:cbz/hh/ii/name.cbz
                rel_computed = computed.relative_to(Path("/cold_placeholder"))
                expected_storage_path = f"cold:{rel_computed}"
            else:
                expected_storage_path = str(computed)

            if expected_storage_path == raw_path:
                # Already conforms to new rules
                continue

            needs_repair_count += 1
            old_p = Path(raw_path)
            new_p = Path(expected_storage_path)

            logger.info(
                "[NEEDS REPAIR] Gallery ID %d | GID %s\n  Old: %s\n  New: %s",
                gallery.id,
                gallery.gid,
                raw_path,
                expected_storage_path,
            )

            if not execute:
                continue

            # In execute mode: perform file check, disk rename, and DB update
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
        elif execute:
            logger.info("No DB changes to commit.")

    await engine.dispose()

    logger.info("================ Summary ================")
    logger.info("Total galleries scanned:    %d", total_scanned)
    logger.info("Cold archived galleries:    %d", cold_archived_count)
    logger.info("Galleries needing repair:   %d", needs_repair_count)
    if execute:
        logger.info("Successfully repaired:      %d", repaired_count)
        logger.info("Skipped (source missing):   %d", skipped_missing_source)
        logger.info("Skipped (target conflict):  %d", skipped_conflict)
        logger.info("Skipped (disk error):       %d", skipped_error)
    else:
        logger.info("Run with --execute to perform atomic rename and update DB.")
    logger.info("=========================================")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair cold archive CBZ filenames truncated by old 80-character limit."
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
    # Ensure async driver if standard postgresql:// provided
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    cold_root_override = Path(args.cold_root).resolve() if args.cold_root else None

    asyncio.run(
        repair_cbz_filenames(
            db_url=db_url,
            execute=execute,
            cold_root_override=cold_root_override,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    main()
