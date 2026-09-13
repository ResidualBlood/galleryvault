"""SSOT for GalleryVault .galleryvault.json sidecar metadata."""

from __future__ import annotations

import json
import logging
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SIDECAR_FILENAME = ".galleryvault.json"

CATEGORIES = (
    "manga",
    "misc",
    "cosplay",
    "doujinshi",
    "artistcg",
    "gamecg",
    "western",
    "non-h",
    "image_set",
    "asianporn",
    "deleted",
    "other",
)

# ExHentai "Misc" and our generic fallback are the same bucket; unknown or
# unclassifiable galleries land here too.
GENERIC_CATEGORY = "misc"

__all__ = [
    "CATEGORIES",
    "GENERIC_CATEGORY",
    "SIDECAR_FILENAME",
    "build_galleryvault_json",
    "normalize_category",
    "normalize_p_tokens",
    "normalize_posted",
    "normalize_quality",
    "normalize_tags",
    "normalize_title_jpn",
    "parse_datetime_utc",
    "parse_galleryvault_json",
    "read_galleryvault_json",
    "write_galleryvault_json",
]


def normalize_tags(tags_input: Any) -> list[dict[str, str]]:
    """Normalize tags into a list of {namespace, name} dicts."""
    if not tags_input or isinstance(tags_input, (str, bytes)):
        return []
    tags: list[dict[str, str]] = []
    for item in tags_input:
        if isinstance(item, dict):
            ns = str(item.get("namespace", "misc") or "misc").strip()
            name = str(item.get("name", "")).strip()
            if name:
                tags.append({"namespace": ns, "name": name})
        elif isinstance(item, (tuple, list)):
            if len(item) >= 2:
                ns = str(item[0] or "misc").strip() or "misc"
                name = str(item[1] or "").strip()
            elif len(item) == 1:
                ns = "misc"
                name = str(item[0] or "").strip()
            else:
                continue
            if name:
                tags.append({"namespace": ns, "name": name})
        elif isinstance(item, str):
            val = item.strip()
            if not val:
                continue
            if ":" in val:
                ns, name = val.split(":", 1)
                tags.append({"namespace": ns.strip() or "misc", "name": name.strip()})
            else:
                tags.append({"namespace": "misc", "name": val})
    return tags


def normalize_category(value: object) -> str | None:
    """Normalize category name to lowercase stripped string or fallback to generic."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    candidate = raw.casefold().replace(" ", "_")
    if candidate == "other":
        # 'other' (our generic bucket) and ExHentai's 'misc' are the same class.
        return GENERIC_CATEGORY
    if candidate in CATEGORIES:
        return candidate
    compact = candidate.replace("_", "")
    if compact in CATEGORIES:
        return compact
    return GENERIC_CATEGORY


def normalize_quality(quality: str | None) -> str | None:
    """Normalize image quality to 'original' | 'resample' | None."""
    if not quality:
        return None
    val = str(quality).strip().lower()
    if val in {"original", "resample"}:
        return val
    return None


def normalize_p_tokens(tokens: Sequence[str | None] | None) -> list[str]:
    """Normalize p_tokens into a dense array where missing tokens are empty strings."""
    if not tokens:
        return []
    return [str(x).strip() if x is not None else "" for x in tokens]


def normalize_title_jpn(title_jpn: str | None) -> str:
    """Normalize Japanese title; convert pure numeric titles to empty string."""
    if not title_jpn:
        return ""
    val = str(title_jpn).strip()
    if val.isdigit():
        return ""
    return val


def parse_datetime_utc(posted: Any) -> datetime | None:
    """Parse various datetime representations into a UTC-aware datetime."""
    if posted is None:
        return None
    if isinstance(posted, datetime):
        if posted.tzinfo is not None:
            return posted.astimezone(UTC)
        return posted.replace(tzinfo=UTC)
    if isinstance(posted, (int, float)):
        try:
            return datetime.fromtimestamp(float(posted), tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(posted, str):
        val = posted.strip()
        if not val:
            return None
        if not ("-" in val or ":" in val or "T" in val):
            try:
                num = float(val)
                return datetime.fromtimestamp(num, tz=UTC)
            except (ValueError, OSError, OverflowError):
                pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        iso_val = val[:-1] + "+00:00" if val.endswith("Z") else val
        try:
            dt = datetime.fromisoformat(iso_val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
            return dt
        except ValueError:
            pass
        try:
            num = float(val)
            return datetime.fromtimestamp(num, tz=UTC)
        except (ValueError, OSError, OverflowError):
            pass
    return None


def normalize_posted(posted: Any) -> str | None:
    """Normalize posted timestamp to ISO 8601 string with trailing 'Z' or None."""
    dt = parse_datetime_utc(posted)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def build_galleryvault_json(
    gid: int | None = None,
    token: str | None = None,
    tags: Sequence[dict[str, Any] | str] | None = None,
    p_tokens: Sequence[str | None] | None = None,
    title: str | None = None,
    title_jpn: str | None = None,
    category: str | None = None,
    quality: str | None = None,
    *,
    uploader: str | None = None,
    posted: Any | None = None,
    rating: float | None = None,
    file_count: int | None = None,
    file_size: int | None = None,
    site: str | None = None,
    extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> bytes:
    """Build unified .galleryvault.json (version 1) bytes."""
    clean_gid: int | None = None
    if gid is not None:
        try:
            clean_gid = int(gid)
        except (ValueError, TypeError):
            clean_gid = None

    clean_token: str | None = str(token).strip() if token else None

    clean_rating: float | None = None
    if rating is not None:
        try:
            clean_rating = float(rating)
        except (ValueError, TypeError):
            clean_rating = None

    clean_file_count: int | None = None
    if file_count is not None:
        try:
            clean_file_count = int(file_count)
        except (ValueError, TypeError):
            clean_file_count = None

    clean_file_size: int | None = None
    if file_size is not None:
        try:
            clean_file_size = int(file_size)
        except (ValueError, TypeError):
            clean_file_size = None

    clean_site = str(site).strip() if site else None
    clean_uploader = str(uploader).strip() if uploader else None

    data: dict[str, Any] = {
        "version": 1,
        "gid": clean_gid,
        "token": clean_token,
        "title": str(title) if title is not None else "",
        "title_jpn": normalize_title_jpn(title_jpn),
        "category": normalize_category(category),
        "quality": normalize_quality(quality),
        "tags": normalize_tags(tags),
        "p_tokens": normalize_p_tokens(p_tokens),
        "uploader": clean_uploader,
        "posted": normalize_posted(posted),
        "rating": clean_rating,
        "file_count": clean_file_count,
        "file_size": clean_file_size,
        "site": clean_site,
    }

    if extra:
        for k, v in extra.items():
            if k not in data:
                data[k] = v
    if kwargs:
        for k, v in kwargs.items():
            if k not in data:
                data[k] = v

    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return payload.encode("utf-8")


def parse_galleryvault_json(data: dict[str, Any] | str | bytes) -> dict[str, Any]:
    """Parse and normalize .galleryvault.json data from dict, str, or bytes.

    Fully compatible with legacy downloader format (has quality, lacks gid/token/p_tokens)
    and legacy cold-archive format (has gid/token/p_tokens, lacks quality, optional category).
    Preserves unknown extra keys for forward compatibility.
    """
    if isinstance(data, (bytes, bytearray)):
        raw = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        raw = json.loads(data)
    elif isinstance(data, dict):
        raw = dict(data)
    else:
        raise TypeError(f"Expected dict, str, or bytes, got {type(data).__name__}")

    if not isinstance(raw, dict):
        raise TypeError("Parsed JSON content is not a dictionary")

    version_raw = raw.get("version")
    try:
        version = int(version_raw) if version_raw is not None else 1
    except (ValueError, TypeError):
        version = 1

    clean_gid: int | None = None
    if raw.get("gid") is not None:
        try:
            clean_gid = int(raw["gid"])
        except (ValueError, TypeError):
            clean_gid = None

    token_raw = raw.get("token")
    token = str(token_raw).strip() if token_raw else None

    title = str(raw.get("title") or "")
    title_jpn = normalize_title_jpn(raw.get("title_jpn"))
    category = normalize_category(raw.get("category"))
    quality = normalize_quality(raw.get("quality"))
    tags = normalize_tags(raw.get("tags"))
    p_tokens = normalize_p_tokens(raw.get("p_tokens"))

    uploader = str(raw.get("uploader")).strip() if raw.get("uploader") else None
    posted = normalize_posted(raw.get("posted"))

    rating_raw = raw.get("rating")
    try:
        rating = float(rating_raw) if rating_raw is not None else None
    except (ValueError, TypeError):
        rating = None

    file_count_raw = raw.get("file_count")
    try:
        file_count = int(file_count_raw) if file_count_raw is not None else None
    except (ValueError, TypeError):
        file_count = None

    file_size_raw = raw.get("file_size")
    try:
        file_size = int(file_size_raw) if file_size_raw is not None else None
    except (ValueError, TypeError):
        file_size = None

    site = str(raw.get("site")).strip() if raw.get("site") else None

    result: dict[str, Any] = {
        "version": version,
        "gid": clean_gid,
        "token": token,
        "title": title,
        "title_jpn": title_jpn,
        "category": category,
        "quality": quality,
        "tags": tags,
        "p_tokens": p_tokens,
        "uploader": uploader,
        "posted": posted,
        "rating": rating,
        "file_count": file_count,
        "file_size": file_size,
        "site": site,
    }

    standard_keys = set(result.keys())
    for k, v in raw.items():
        if k not in standard_keys:
            result[k] = v

    return result


def read_galleryvault_json(source: Path | str | zipfile.ZipFile) -> dict[str, Any] | None:
    """Read and parse .galleryvault.json from directory, CBZ/ZIP, or json file.

    Returns parsed dictionary on success, or None if missing or corrupt.
    """
    try:
        if isinstance(source, zipfile.ZipFile):
            if SIDECAR_FILENAME in source.namelist():
                raw = source.read(SIDECAR_FILENAME)
                return parse_galleryvault_json(raw)
            return None

        p = Path(source)
        if not p.exists():
            return None

        if p.is_dir():
            gv_file = p / SIDECAR_FILENAME
            if gv_file.is_file():
                return parse_galleryvault_json(gv_file.read_bytes())
            return None

        if p.name == SIDECAR_FILENAME or p.suffix.lower() == ".json":
            return parse_galleryvault_json(p.read_bytes())

        if p.suffix.lower() in {".cbz", ".zip"}:
            with zipfile.ZipFile(p, "r") as zf:
                if SIDECAR_FILENAME in zf.namelist():
                    return parse_galleryvault_json(zf.read(SIDECAR_FILENAME))
                return None
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError, ValueError, UnicodeDecodeError) as exc:
        logger.debug("Failed to read sidecar from %s: %s", source, exc)
        return None

    return None


def write_galleryvault_json(
    target_dir: Path | str,
    gid: int | None = None,
    token: str | None = None,
    tags: Sequence[dict[str, Any] | str] | None = None,
    p_tokens: Sequence[str | None] | None = None,
    title: str | None = None,
    title_jpn: str | None = None,
    category: str | None = None,
    quality: str | None = None,
    *,
    uploader: str | None = None,
    posted: Any | None = None,
    rating: float | None = None,
    file_count: int | None = None,
    file_size: int | None = None,
    site: str | None = None,
    extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Path:
    """Write unified .galleryvault.json into target directory."""
    data_bytes = build_galleryvault_json(
        gid=gid,
        token=token,
        tags=tags,
        p_tokens=p_tokens,
        title=title,
        title_jpn=title_jpn,
        category=category,
        quality=quality,
        uploader=uploader,
        posted=posted,
        rating=rating,
        file_count=file_count,
        file_size=file_size,
        site=site,
        extra=extra,
        **kwargs,
    )
    dest_dir = Path(target_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / SIDECAR_FILENAME
    out_file.write_bytes(data_bytes)
    return out_file
