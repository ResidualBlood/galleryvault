#!/usr/bin/env bash
# Sync the canonical wiki source under docs/wiki/ to the GitHub wiki repository.
#
# Canonical source of truth: <repo>/docs/wiki/  (edited here, committed to meta repo)
# Target:                   ResidualBlood/galleryvault.wiki  (local clone)
#
# API.md / Development.md / openapi.json are NOT managed here — the sync-docs
# workflow pushes them from galleryvault-backend. They are excluded from rsync.
#
# Usage:
#   ./scripts/sync-wiki.sh             sync (pull wiki, mirror docs/wiki, push)
#   ./scripts/sync-wiki.sh --dry-run   show what would change without pushing
#
# Prerequisites:
#   - local wiki clone at /mnt/GalleryVault/wiki (override with GV_WIKI_DIR)
#   - GitHub PAT: /root/gh_token, or override with GH_TOKEN
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WIKI_DIR="${GV_WIKI_DIR:-/mnt/GalleryVault/wiki}"
SRC_DIR="$REPO_ROOT/docs/wiki"
REMOTE="https://github.com/ResidualBlood/galleryvault.wiki.git"
TOKEN="${GH_TOKEN:-$(cat /root/gh_token 2>/dev/null || true)}"
TOKEN="$(printf '%s' "$TOKEN" | tr -d '\r\n')"

if [[ -z "$TOKEN" ]]; then
  echo "error: no GitHub token found (set GH_TOKEN or /root/gh_token)" >&2
  exit 1
fi
if [[ ! -d "$SRC_DIR" ]]; then
  echo "error: canonical source not found: $SRC_DIR" >&2
  exit 1
fi

# 1. Pull latest wiki state.
git -C "$WIKI_DIR" pull -q origin master

# 2. Mirror the canonical pages into the wiki clone (deletes stray pages,
#    keeps the API files owned by the sync-docs workflow untouched).
rsync -a --delete \
  --exclude='.git' \
  --exclude='API.md' --exclude='Development.md' --exclude='openapi.json' \
  "$SRC_DIR/" "$WIKI_DIR/"

if ! git -C "$WIKI_DIR" status --porcelain | grep -q .; then
  echo "wiki: no changes"
  exit 0
fi

echo "wiki: pending changes:"
git -C "$WIKI_DIR" status --short

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "wiki: dry-run, skipping commit/push"
  exit 0
fi

# 3. Commit and push via one-time token URL (does not touch the git config).
git -C "$WIKI_DIR" add -A
git -C "$WIKI_DIR" commit -q -m "docs: sync wiki from galleryvault/docs/wiki"
PUSH_URL="https://ResidualBlood:${TOKEN}@${REMOTE#https://}"
git -C "$WIKI_DIR" push -q "$PUSH_URL" HEAD:master

echo "wiki: synced"
