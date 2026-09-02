#!/usr/bin/env bash
# Mirror the canonical docs (docs/wiki + backend docs/API.* / DEVELOPMENT.md)
# into the VitePress source dir (docs-site/src), which is generated and
# gitignored.  Run from the repository root (or anywhere).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_DIR="$REPO_ROOT/docs/wiki"
# VitePress root = docs-site, pages are generated flat into it.
DST_DIR="$REPO_ROOT/docs-site"
# Backend reference docs are at backend/docs in the monorepo.
BACKEND_DOCS="${BACKEND_DOCS:-$REPO_ROOT/backend/docs}"

mkdir -p "$DST_DIR"

# wiki pages: every .md except the GitHub-wiki-only _Sidebar.md
find "$SRC_DIR" -maxdepth 1 -name '*.md' ! -name '_Sidebar.md' -exec cp {} "$DST_DIR/" \;

# API reference / development notes from the backend repo
cp "$BACKEND_DOCS/API.md" "$DST_DIR/API.md" 2>/dev/null || true
cp "$BACKEND_DOCS/DEVELOPMENT.md" "$DST_DIR/Development.md" 2>/dev/null || true

# Landing page: the Chinese Home page serves as the site index.
cp "$SRC_DIR/Home.md" "$DST_DIR/index.md"

# Escape bare angle brackets (`<host>`, `<gid>` …) so VitePress renders them
# as text instead of parsing them as (broken) HTML.
python3 "$REPO_ROOT/docs-site/scripts/escape-bare-html.py" "$DST_DIR"

echo "docs-site synced: $(ls "$DST_DIR"/*.md | wc -l) pages"
