#!/usr/bin/env bash
# ==============================================================================
# scripts/release.sh — GalleryVault unified release automation tool
# Usage: ./scripts/release.sh [vX.Y.Z] [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
META_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${META_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

TAG="${1:-}"
DRY_RUN=false
if [[ "${2:-}" == "--dry-run" ]] || [[ "${TAG}" == "--dry-run" ]]; then
  if [[ "${TAG}" == "--dry-run" ]]; then TAG="${2:-}"; fi
  DRY_RUN=true
fi

if [[ -z "${TAG}" ]]; then
  echo "Usage: $0 <vX.Y.Z> [--dry-run]"
  echo "Example: $0 v1.5.0"
  exit 1
fi

# Ensure tag has 'v' prefix
if [[ ! "${TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]]; then
  echo "Error: Tag must be in semver format with 'v' prefix (e.g. v1.5.0), got: ${TAG}"
  exit 1
fi

RAW_VERSION="${TAG#v}"

echo "==> Preparing release ${TAG} (raw version: ${RAW_VERSION})..."

# Check working directories
for d in "${META_DIR}" "${BACKEND_DIR}" "${FRONTEND_DIR}"; do
  if [[ ! -d "${d}" ]]; then
    echo "Error: Repository directory not found: ${d}"
    exit 1
  fi
  if [[ -n "$(git -C "${d}" status --porcelain)" ]]; then
    echo "Error: Uncommitted changes found in ${d}."
    echo "Please commit or stash your changes before releasing."
    exit 1
  fi
done

echo "==> All repositories clean."

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "[DRY RUN] Would update backend/pyproject.toml to version = \"${RAW_VERSION}\""
  echo "[DRY RUN] Would verify tests and create git tags: ${TAG}"
  echo "[DRY RUN] Dry run complete."
  exit 0
fi

# 1. Update pyproject.toml version
PYPROJECT="${BACKEND_DIR}/pyproject.toml"
if [[ -f "${PYPROJECT}" ]]; then
  sed -i -E "s/^version = \"[0-9]+\.[0-9]+\.[0-9]+\"/version = \"${RAW_VERSION}\"/" "${PYPROJECT}"
  git -C "${BACKEND_DIR}" add pyproject.toml
  git -C "${BACKEND_DIR}" commit -m "chore: align pyproject version with releases (${TAG})" || true
fi

echo "==> Version bumped in backend/pyproject.toml."
echo "==> Done. Ready to create tags on main upon merging dev."
