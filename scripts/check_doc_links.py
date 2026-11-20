#!/usr/bin/env python3
"""Check relative Markdown links (and optionally docs/ paths in code comments).

Usage:
  check_doc_links.py --root DIR [--json] [--anchors] [--code-comments]

Exit codes: 0 = no broken links, 1 = broken links, 2 = refused/unusable root.

The check is read-only, bounded (file count, per-file bytes, report size) and
uses only the Python standard library. External URLs, mail links and pure
in-page anchors are skipped; relative links are resolved from the Markdown
file that contains them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

MAX_FILES = 5000
MAX_BYTES = 2 * 1024 * 1024
MAX_CODE_FILES = 2000
MAX_CODE_BYTES = 512 * 1024
MAX_REPORT = 200

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}

LINK_RE = re.compile(r"(?<!!)\[(?:[^\[\]]|\[[^\]]*\])*\]\(([^()\s]*(?:\([^()]*\)[^()\s]*)*)\)")
IMAGE_RE = re.compile(r"!\[(?:[^\[\]]|\[[^\]]*\])*\]\(([^()\s]*(?:\([^()]*\)[^()\s]*)*)\)")
FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+[^`]*`+")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CODE_EXTS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".kt", ".rb", ".sh", ".bash",
}
CODE_REF_RE = re.compile(r"(?:^|[\s\"'`(<\[=:;])((?:\./)?docs/[A-Za-z0-9._~%/-]+)")
DOC_HEADING_CHARS = re.compile(r"[^\w\- \u4e00-\u9fff]")


def rel(root: Path, path: Path) -> str:
    return Path(os.path.relpath(path, root)).as_posix()


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = DOC_HEADING_CHARS.sub("", text)
    return text.replace(" ", "-")


def iter_files(root: Path, suffixes, limit: int, skip_dirs=None):
    """Yield files under root with bounded traversal; returns (files, truncated)."""
    skip = SKIP_DIRS if skip_dirs is None else skip_dirs
    found = 0
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip and not d.startswith(".git"))
        for name in sorted(names):
            if not any(name.endswith(suffix) for suffix in suffixes):
                continue
            if found >= limit:
                return True
            found += 1
            yield Path(base) / name
    return False


def strip_code(text: str) -> str:
    """Blank fenced code blocks and inline code so examples are not treated as links."""
    lines = text.splitlines()
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        match = FENCE_RE.match(line)
        if match:
            mark = match.group(2)[0]
            if fence is None:
                fence = mark
            elif fence == mark:
                fence = None
            out.append("")
            continue
        if fence is not None:
            out.append("")
            continue
        out.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


def link_targets(raw: str) -> str | None:
    target = raw.strip()
    if not target:
        return None
    if target.startswith("<") and ">" in target:
        target = target[1:target.index(">")]
    else:
        # Drop an optional Markdown title: (path "title").
        target = target.split()[0]
    return target or None


def anchors_of(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    found: set[str] = set()
    for line in strip_code(text).splitlines():
        match = HEADING_RE.match(line)
        if match:
            found.add(slugify(match.group(1)))
    return found


def check_markdown(root: Path, path: Path, check_anchors: bool, broken: list[dict], counter: list[int]) -> None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    cleaned = strip_code(text)
    line_starts = [0]
    for match in re.finditer(r"\n", cleaned):
        line_starts.append(match.end())

    def line_of(offset: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for pattern in (LINK_RE, IMAGE_RE):
        for match in pattern.finditer(cleaned):
            target = link_targets(match.group(1))
            counter[0] += 1
            if target is None:
                continue
            if target.startswith("#") or target.startswith("//") or SCHEME_RE.match(target):
                continue
            path_part, _, fragment = target.partition("#")
            path_part = unquote(path_part.split("?")[0])
            if not path_part:
                continue
            resolved = (path.parent / path_part).resolve() if not path_part.startswith("/") else (root / path_part.lstrip("/")).resolve()
            if not resolved.exists():
                broken.append({
                    "file": rel(root, path),
                    "line": line_of(match.start()),
                    "target": target,
                    "reason": "missing",
                })
                continue
            if check_anchors and fragment and resolved.is_file() and resolved.suffix.lower() == ".md":
                if slugify(fragment) not in anchors_of(resolved):
                    broken.append({
                        "file": rel(root, path),
                        "line": line_of(match.start()),
                        "target": target,
                        "reason": "missing-anchor",
                    })


def check_code_comments(root: Path, path: Path, broken: list[dict], counter: list[int]) -> None:
    try:
        if path.stat().st_size > MAX_CODE_BYTES:
            return
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    markers = ("#", "//", "/*", "*", "--")
    for number, line in enumerate(text.splitlines(), 1):
        if "docs/" not in line or not any(marker in line for marker in markers):
            continue
        for match in CODE_REF_RE.finditer(line):
            raw = match.group(1).rstrip(".,;:)]}>'\"`")
            if not raw:
                continue
            counter[0] += 1
            target = raw.partition("#")[0]
            target = target[2:] if target.startswith("./") else target
            resolved = (root / target).resolve()
            if not resolved.exists():
                broken.append({
                    "file": rel(root, path),
                    "line": number,
                    "target": raw,
                    "reason": "missing",
                })


def run(root: Path, check_anchors: bool, scan_code: bool) -> dict:
    broken: list[dict] = []
    markdown_counter = [0]
    code_counter = [0]
    checked_files = 0
    truncated = False

    for path in iter_files(root, (".md",), MAX_FILES):
        checked_files += 1
        check_markdown(root, path, check_anchors, broken, markdown_counter)

    if scan_code:
        for path in iter_files(root, tuple(CODE_EXTS), MAX_CODE_FILES):
            check_code_comments(root, path, broken, code_counter)

    total = len(broken)
    shown = broken[:MAX_REPORT]
    return {
        "root": str(root),
        "mode": "doc-links",
        "status": "warn" if total else "pass",
        "checked_files": checked_files,
        "links": markdown_counter[0],
        "code_refs": code_counter[0] if scan_code else 0,
        "broken_count": total,
        "broken": shown,
        "overflow": max(0, total - len(shown)),
        "truncated": truncated,
        "warnings": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check relative Markdown links and code-comment docs/ paths.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    parser.add_argument("--anchors", action="store_true", help="also validate #anchors in Markdown links")
    parser.add_argument("--code-comments", action="store_true", help="scan docs/ paths in code comments")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(json.dumps({"root": str(root), "status": "refused", "error": "ROOT_NOT_FOUND"}, ensure_ascii=False))
        return 2

    report = run(root, args.anchors, args.code_comments)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["broken"]:
        print(f"broken links: {report['broken_count']} in {report['checked_files']} markdown file(s)")
        for item in report["broken"]:
            print(f"{item['file']}:{item['line']}: {item['target']} ({item['reason']})")
        if report["overflow"]:
            print(f"... {report['overflow']} more")
    else:
        print(f"ok: {report['checked_files']} markdown file(s), {report['links']} link(s) checked")
    return 1 if report["broken_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
