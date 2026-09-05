from __future__ import annotations

import re
import zipfile
from collections.abc import Sequence
from pathlib import Path

ZIP_STORED = zipfile.ZIP_STORED


class UnsafeExportPath(ValueError):
    pass


_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def page_archive_name(index: int, suffix: str | None = None) -> str:
    """Format index to a 4-digit zero-padded filename (e.g., 0001.jpg)."""
    ext = (suffix or ".jpg").lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{int(index):04d}{ext}"


def is_cbz_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".cbz"


def cbz_filename(title: str | None, gid: int | None, gallery_id: int) -> str:
    base = (title or "").strip() or (str(gid) if gid else f"gallery-{gallery_id}")
    base = _UNSAFE_NAME.sub("_", base).strip(" .")[:80] or f"gallery-{gallery_id}"
    return f"{base}.cbz"


def resolve_page_file(gallery_dir: Path, member_name: str) -> Path:
    root = gallery_dir.resolve()
    name = (member_name or "").replace("\\", "/")
    if not name or name.startswith(("/", "~")):
        raise UnsafeExportPath(member_name)
    parts = Path(name).parts
    if ".." in parts:
        raise UnsafeExportPath(member_name)
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise UnsafeExportPath(member_name)
    return candidate


def pack_directory_cbz(
    gallery_dir: Path, pages: Sequence[tuple[int, str]], dest: Path
) -> None:
    root = gallery_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=ZIP_STORED) as zf:
        for index, member_name in pages:
            src = resolve_page_file(root, member_name)
            if not src.is_file():
                raise FileNotFoundError(str(src))
            ext = src.suffix.lower() or ".jpg"
            zf.write(src, page_archive_name(index, ext))
