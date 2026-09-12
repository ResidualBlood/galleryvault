#!/usr/bin/env python3
"""Rewrite relative README images/links so Docker Hub Overview can render them.

GitHub README keeps relative paths. Hub does not resolve them, so CI should
pipe README.md through this before peter-evans/dockerhub-description.

Usage:
  GITHUB_REPOSITORY=ResidualBlood/galleryvault GITHUB_SHA=<sha> \\
    python3 scripts/readme-for-dockerhub.py README.md > /tmp/README.dockerhub.md
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def abs_url(path: str, *, file_base: str, blob_base: str) -> str:
    raw = path.strip()
    if not raw or raw.startswith(("#", "mailto:", "data:", "http://", "https://")):
        return path
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw):
        return path
    cleaned = raw.split("#", 1)
    rel = cleaned[0].lstrip("./")
    suffix = f"#{cleaned[1]}" if len(cleaned) == 2 else ""
    if rel.endswith(".md") or rel.endswith(".MD"):
        return f"{blob_base}{rel}{suffix}"
    return f"{file_base}{rel}{suffix}"


def rewrite(text: str, *, file_base: str, blob_base: str) -> str:
    def img_src(match: re.Match[str]) -> str:
        return match.group(1) + abs_url(
            match.group(2), file_base=file_base, blob_base=blob_base
        ) + match.group(3)

    def md_img(match: re.Match[str]) -> str:
        return match.group(1) + abs_url(
            match.group(2), file_base=file_base, blob_base=blob_base
        ) + match.group(3)

    def href(match: re.Match[str]) -> str:
        return match.group(1) + abs_url(
            match.group(2), file_base=file_base, blob_base=blob_base
        ) + match.group(3)

    text = re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)(")', img_src, text, flags=re.I)
    text = re.sub(r'(!\[[^\]]*\]\()([^)\s]+)(\))', md_img, text)
    text = re.sub(r'(<a\b[^>]*\bhref=")([^"]+)(")', href, text, flags=re.I)
    return text


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "README.md")
    repo = os.environ.get("GITHUB_REPOSITORY", "ResidualBlood/galleryvault")
    ref = os.environ.get("GITHUB_SHA") or os.environ.get("GITHUB_REF_NAME") or "main"
    file_base = f"https://raw.githubusercontent.com/{repo}/{ref}/"
    blob_base = f"https://github.com/{repo}/blob/{ref}/"
    sys.stdout.write(
        rewrite(src.read_text(encoding="utf-8"), file_base=file_base, blob_base=blob_base)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
