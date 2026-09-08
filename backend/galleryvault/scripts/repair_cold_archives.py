#!/usr/bin/env python3
"""
backend/galleryvault/scripts/repair_cold_archives.py

Scans galleries in the database, cleanses contaminated titles (via cache, GData API,
or strip_gid_prefix), repairs cold archive CBZ files with double GID prefixes, and
repairs local unarchived gallery directories or files.

Safety:
  - Defaults to --dry-run mode (read-only preview).
  - Requires --execute to perform atomic renames and commit DB changes.
  - Skips safely if destination exists or source is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from galleryvault.config import get_settings
from galleryvault.db.models import Gallery, GalleryMetadata
from galleryvault.scanners.ehviewer import strip_gid_prefix
from galleryvault.services.cold_archive import (
    compute_cold_path,
    resolve_archive_roots,
    safe_title,
)
from galleryvault.services.downloader import gallery_dirname

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("repair_cold_archives")

EXHENTAI_API_CHUNK_SIZE = 25


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


async def fetch_gdata_batch(
    pairs: list[tuple[int, str]],
    base_url: str = "https://api.e-hentai.org",
    client: httpx.AsyncClient | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> dict[int, dict[str, Any]]:
    """Batch-fetch gallery metadata via the ExHentai ``gdata`` API.

    Chunks into batches of 25 items and protects concurrency with asyncio.Semaphore(6).
    """
    if not pairs:
        return {}

    sem = semaphore if semaphore is not None else asyncio.Semaphore(6)
    results: dict[int, dict[str, Any]] = {}

    async def _fetch_chunk(
        http_client: httpx.AsyncClient, chunk_pairs: list[tuple[int, str]]
    ) -> list[dict[str, Any]]:
        async with sem:
            payload = {
                "method": "gdata",
                "gidlist": [[int(gid), token] for gid, token in chunk_pairs],
                "namespace": 1,
            }
            try:
                resp = await http_client.post(
                    f"{base_url.rstrip('/')}/api.php",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GalleryVault/1.0",
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("gmetadata", []) or []
                logger.warning(
                    "GData API batch request failed with HTTP %s", resp.status_code
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("GData API batch request failed: %s", exc)
            return []

    chunks = [
        pairs[i : i + EXHENTAI_API_CHUNK_SIZE]
        for i in range(0, len(pairs), EXHENTAI_API_CHUNK_SIZE)
    ]

    async def _run_all(http_client: httpx.AsyncClient) -> None:
        tasks = [_fetch_chunk(http_client, chunk) for chunk in chunks]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        for chunk_res in chunk_results:
            if isinstance(chunk_res, list):
                for item in chunk_res:
                    if not item or item.get("error") or item.get("gid") is None:
                        continue
                    gid = int(item["gid"])
                    results[gid] = {
                        "token": item.get("token") or "",
                        "title": html.unescape(item.get("title", "") or "").strip(),
                        "title_jpn": (
                            html.unescape(item["title_jpn"]).strip()
                            if item.get("title_jpn")
                            else None
                        ),
                        "category": item.get("category") or None,
                        "file_count": int(item.get("filecount") or 0),
                        "file_size": int(item.get("filesize") or 0) or None,
                        "tags": item.get("tags", []) or [],
                        "uploader": item.get("uploader") or None,
                        "rating": float(item.get("rating") or 0) or None,
                    }

    if client is not None:
        await _run_all(client)
    else:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            await _run_all(http_client)

    return results


def is_title_contaminated(
    title: str | None,
    title_jpn: str | None = None,
    gid: int | None = None,
) -> bool:
    """Determine whether gallery title or title_jpn needs cleansing."""
    if not title:
        return False
    # 1. Leading GID prefix (e.g. {gid}-, {gid}_, {gid} )
    if strip_gid_prefix(title, gid) != title:
        return True
    # 2. Leading digits followed by delimiter (generic numeric prefix)
    if re.match(r"^\d{4,9}[-\s_]", title):
        return True
    # 3. Double GID in title
    if gid is not None and (f"{gid}-{gid}-" in title or f"{gid}_{gid}_" in title):
        return True
    # 4. Scanner fallback: title_jpn is missing but title contains Japanese kana
    return bool(not title_jpn and re.search(r"[\u3040-\u309f\u30a0-\u30ff]", title))


def fallback_cleanse_titles(
    title: str | None,
    title_jpn: str | None = None,
    gid: int | None = None,
) -> tuple[str, str | None]:
    """Fallback title cleansing when cache and GData are not available.

    Uses strip_gid_prefix to strip leading GID, and preserves/fills title_jpn
    if the cleaned title contains Japanese text and title_jpn was empty.
    """
    raw_title = (title or "").strip()
    clean_title = strip_gid_prefix(raw_title, gid).strip()
    if not clean_title:
        clean_title = raw_title

    clean_jpn = (title_jpn or "").strip() or None
    # If title_jpn is empty and stripped title has Japanese kana, preserve as title_jpn
    if (
        not clean_jpn
        and re.search(r"[\u3040-\u309f\u30a0-\u30ff]", clean_title)
        and not clean_title.isdigit()
    ):
        clean_jpn = clean_title

    return clean_title, clean_jpn


async def repair_cold_archives(
    db_url: str | AsyncEngine | async_sessionmaker[AsyncSession] | Any,
    execute: bool = False,
    cold_root_override: Path | None = None,
    limit: int | None = None,
    fix_titles: bool = True,
    fix_cold: bool = True,
    fix_local: bool = True,
    http_client: httpx.AsyncClient | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> dict[str, int]:
    """Inspect and repair contaminated titles, cold archive CBZ files, and local directories."""
    settings = get_settings()
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

    titles_cleansed = 0
    titles_cache_hits = 0
    titles_gdata_hits = 0
    titles_fallback = 0

    local_needs_repair_count = 0
    local_repaired_count = 0
    local_skipped_missing_source = 0
    local_skipped_conflict = 0
    local_skipped_error = 0

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

            # =========================================================================
            # Phase 1: DB Title Cleansing (Cache -> GData Batch API -> Fallback Strip)
            # =========================================================================
            if fix_titles and galleries:
                contaminated_galleries = [
                    g
                    for g in galleries
                    if is_title_contaminated(g.title, g.title_jpn, g.gid)
                ]

                cached_metadata_by_gid: dict[int, GalleryMetadata] = {}
                candidate_gids = [
                    g.gid for g in contaminated_galleries if g.gid is not None
                ]
                if candidate_gids:
                    try:
                        meta_query = select(GalleryMetadata).where(
                            GalleryMetadata.gid.in_(candidate_gids)
                        )
                        meta_res = await session.execute(meta_query)
                        for m in meta_res.scalars().all():
                            cached_metadata_by_gid[m.gid] = m
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(
                            "gallery_metadata query skipped or unsupported: %s", exc
                        )

                cleansed_map: dict[int, tuple[str, str | None, str]] = {}
                need_gdata_pairs: list[tuple[int, str]] = []
                need_gdata_galleries: list[Gallery] = []

                for g in contaminated_galleries:
                    gid = g.gid
                    cached_m = cached_metadata_by_gid.get(gid) if gid else None
                    c_hit_title: str | None = None
                    c_hit_jpn: str | None = None

                    if cached_m and cached_m.title:
                        raw_c_title = cached_m.title.strip()
                        if (
                            raw_c_title
                            and strip_gid_prefix(raw_c_title, gid) == raw_c_title
                            and not re.match(r"^\d{4,9}[-\s_]", raw_c_title)
                        ):
                            c_hit_title = raw_c_title
                            c_hit_jpn = (
                                cached_m.title_jpn.strip()
                                if cached_m.title_jpn
                                else None
                            )
                            if not c_hit_jpn:
                                _, fb_j = fallback_cleanse_titles(
                                    g.title, g.title_jpn, gid
                                )
                                c_hit_jpn = fb_j

                    if c_hit_title:
                        cleansed_map[g.id] = (c_hit_title, c_hit_jpn, "cache")
                    else:
                        token = g.token or (cached_m.token if cached_m else None)
                        if gid and token:
                            need_gdata_pairs.append((gid, token))
                            need_gdata_galleries.append(g)
                        else:
                            fb_t, fb_j = fallback_cleanse_titles(
                                g.title, g.title_jpn, gid
                            )
                            cleansed_map[g.id] = (fb_t, fb_j, "fallback")

                if need_gdata_pairs:
                    base_url = (
                        settings.exhentai_base_url
                        if hasattr(settings, "exhentai_base_url")
                        else "https://api.e-hentai.org"
                    )
                    gdata_results = await fetch_gdata_batch(
                        need_gdata_pairs,
                        base_url=base_url,
                        client=http_client,
                        semaphore=semaphore,
                    )
                else:
                    gdata_results = {}

                for g in need_gdata_galleries:
                    gm = gdata_results.get(g.gid) if g.gid else None
                    if gm and gm.get("title"):
                        clean_api_title = strip_gid_prefix(gm["title"], g.gid).strip()
                        if clean_api_title:
                            cleansed_map[g.id] = (
                                clean_api_title,
                                gm.get("title_jpn"),
                                "gdata",
                            )
                            continue
                    fb_t, fb_j = fallback_cleanse_titles(g.title, g.title_jpn, g.gid)
                    cleansed_map[g.id] = (fb_t, fb_j, "fallback")

                for g in contaminated_galleries:
                    if g.id not in cleansed_map:
                        continue
                    new_t, new_j, src = cleansed_map[g.id]
                    if new_t == g.title and new_j == g.title_jpn:
                        continue

                    titles_cleansed += 1
                    if src == "cache":
                        titles_cache_hits += 1
                    elif src == "gdata":
                        titles_gdata_hits += 1
                    else:
                        titles_fallback += 1

                    logger.info(
                        "[TITLE CLEANSED: %s] Gallery ID %d | GID %s\n  Old: %r (jpn: %r)\n  New: %r (jpn: %r)",
                        src.upper(),
                        g.id,
                        g.gid,
                        g.title,
                        g.title_jpn,
                        new_t,
                        new_j,
                    )

                    g.title = new_t
                    g.title_jpn = new_j

                    if execute and g.gid:
                        try:
                            m_rec = cached_metadata_by_gid.get(g.gid)
                            if not m_rec and hasattr(session, "get"):
                                m_rec = await session.get(GalleryMetadata, g.gid)
                            if m_rec:
                                m_rec.title = new_t
                                if new_j:
                                    m_rec.title_jpn = new_j
                                if g.gid in gdata_results:
                                    gr = gdata_results[g.gid]
                                    if gr.get("category"):
                                        m_rec.category = gr["category"]
                                    if gr.get("tags"):
                                        m_rec.tags = gr["tags"]
                                    if gr.get("file_count"):
                                        m_rec.file_count = gr["file_count"]
                                    if gr.get("file_size"):
                                        m_rec.file_size = gr["file_size"]
                            elif g.gid in gdata_results and hasattr(session, "add"):
                                gr = gdata_results[g.gid]
                                new_meta = GalleryMetadata(
                                    gid=g.gid,
                                    token=gr.get("token") or g.token,
                                    title=new_t,
                                    title_jpn=new_j,
                                    category=gr.get("category"),
                                    tags=gr.get("tags"),
                                    file_count=gr.get("file_count"),
                                    file_size=gr.get("file_size"),
                                )
                                session.add(new_meta)
                                cached_metadata_by_gid[g.gid] = new_meta
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Failed to update gallery_metadata for GID %s: %s",
                                g.gid,
                                exc,
                            )

            # =========================================================================
            # Phase 2: Cold CBZ & Local Directory/CBZ Renaming
            # =========================================================================
            for gallery in galleries:
                raw_path = gallery.storage_path
                if not raw_path:
                    continue

                cold_info = parse_cold_storage_info(
                    raw_path,
                    configured_roots,
                    override_cold_root=cold_root_override,
                )

                if cold_info:
                    if not fix_cold:
                        continue
                    cold_archived_count += 1
                    cold_root, _sub_type, is_prefix = cold_info
                    is_cbz = (
                        raw_path.lower().endswith(".cbz")
                        or gallery.storage_type == "cbz"
                    )

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
                        if (
                            filename.startswith(f"{gid_s}-{gid_s}-")
                            or f"{gid_s}_{gid_s}_" in filename
                            or re.match(r"^\d+-\d+-", filename)
                        ):
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

                else:
                    # Local unarchived gallery (directory or non-cold CBZ)
                    if not fix_local or gallery.gid is None:
                        continue

                    old_p = Path(raw_path)
                    is_cbz = (
                        raw_path.lower().endswith(".cbz")
                        or gallery.storage_type == "cbz"
                    )
                    download_mode = getattr(settings, "download_title", "japanese")

                    if is_cbz:
                        expected_name = f"{gallery.gid}-{safe_title(strip_gid_prefix(gallery.title, gallery.gid))}.cbz"
                    else:
                        expected_name = gallery_dirname(
                            gallery.gid,
                            gallery.title_jpn,
                            gallery.title,
                            mode=download_mode,
                        )

                    has_double_gid = False
                    gid_s = str(gallery.gid)
                    if (
                        old_p.name.startswith(f"{gid_s}-{gid_s}-")
                        or f"{gid_s}_{gid_s}_" in old_p.name
                        or re.match(r"^\d+-\d+-", old_p.name)
                    ):
                        has_double_gid = True

                    new_p = old_p.parent / expected_name
                    expected_storage_path = str(new_p)

                    needs_local_repair = has_double_gid or (
                        expected_storage_path != raw_path
                        and (
                            strip_gid_prefix(old_p.name, gallery.gid) != old_p.name
                            or re.match(r"^\d{4,9}[-\s_]", old_p.name)
                        )
                    )

                    if not needs_local_repair or expected_storage_path == raw_path:
                        continue

                    local_needs_repair_count += 1
                    tag_log = (
                        "[LOCAL DOUBLE GID]"
                        if has_double_gid
                        else "[LOCAL PATH MISMATCH]"
                    )
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
                            "[SKIP: SOURCE MISSING] Local Gallery ID %d: source not found on disk: %s",
                            gallery.id,
                            old_p,
                        )
                        local_skipped_missing_source += 1
                        continue

                    if new_p.exists() and new_p != old_p:
                        logger.error(
                            "[SKIP: CONFLICT] Local Gallery ID %d: target already exists on disk: %s",
                            gallery.id,
                            new_p,
                        )
                        local_skipped_conflict += 1
                        continue

                    try:
                        new_p.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(old_p, new_p)
                        gallery.storage_path = expected_storage_path
                        local_repaired_count += 1
                        logger.info(
                            "[SUCCESS] Renamed local path and updated DB for Gallery ID %d",
                            gallery.id,
                        )
                    except OSError as exc:
                        logger.error(
                            "[ERROR] Failed to rename local path for Gallery ID %d (%s -> %s): %s",
                            gallery.id,
                            old_p,
                            new_p,
                            exc,
                        )
                        local_skipped_error += 1

            if execute and (
                repaired_count > 0 or local_repaired_count > 0 or titles_cleansed > 0
            ):
                await session.commit()
                logger.info(
                    "Successfully committed DB changes (repaired cold: %d, repaired local: %d, cleansed titles: %d).",
                    repaired_count,
                    local_repaired_count,
                    titles_cleansed,
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
        "titles_cleansed": titles_cleansed,
        "titles_cache_hits": titles_cache_hits,
        "titles_gdata_hits": titles_gdata_hits,
        "titles_fallback": titles_fallback,
        "local_needs_repair": local_needs_repair_count,
        "local_repaired": local_repaired_count,
        "local_skipped_missing_source": local_skipped_missing_source,
        "local_skipped_conflict": local_skipped_conflict,
        "local_skipped_error": local_skipped_error,
    }

    logger.info("================ Summary ================")
    logger.info("Total galleries scanned:    %d", summary["total_scanned"])
    logger.info("Titles cleansed:            %d", summary["titles_cleansed"])
    logger.info("  - Cache hits:             %d", summary["titles_cache_hits"])
    logger.info("  - GData API hits:         %d", summary["titles_gdata_hits"])
    logger.info("  - Fallback stripped:      %d", summary["titles_fallback"])
    logger.info("Cold archived galleries:    %d", summary["cold_archived"])
    logger.info("Double GID detected (cold): %d", summary["double_gid_detected"])
    logger.info("Cold CBZ needing repair:    %d", summary["needs_repair"])
    logger.info("Local items needing repair: %d", summary["local_needs_repair"])
    if execute:
        logger.info("Cold CBZ repaired:          %d", summary["repaired"])
        logger.info("Local items repaired:       %d", summary["local_repaired"])
        logger.info(
            "Skipped (source missing):   %d",
            summary["skipped_missing_source"]
            + summary["local_skipped_missing_source"],
        )
        logger.info(
            "Skipped (target conflict):  %d",
            summary["skipped_conflict"] + summary["local_skipped_conflict"],
        )
        logger.info(
            "Skipped (disk error):       %d",
            summary["skipped_error"] + summary["local_skipped_error"],
        )
    else:
        logger.info("Run with --execute to perform atomic rename and update DB.")
    logger.info("=========================================")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair gallery titles, cold archive CBZ files, and local directories."
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
        "--fix-titles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Cleanse and update contaminated titles using cache, GData API, or strip_gid_prefix.",
    )
    parser.add_argument(
        "--fix-cold",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Repair cold archive CBZ files with double GID or path mismatch.",
    )
    parser.add_argument(
        "--fix-local",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Repair local non-cold archive directories or files.",
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
            fix_titles=args.fix_titles,
            fix_cold=args.fix_cold,
            fix_local=args.fix_local,
        )
    )


if __name__ == "__main__":
    main()
