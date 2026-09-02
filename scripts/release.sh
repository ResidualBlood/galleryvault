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

DRY_RUN=false
TAG=""

for arg in "$@"; do
  case "${arg}" in
    --dry-run|-n)
      DRY_RUN=true
      ;;
    --help|-h)
      echo "Usage: $0 [vX.Y.Z] [--dry-run]"
      echo "Example: $0 v1.5.0"
      echo "         $0 --dry-run"
      exit 0
      ;;
    v[0-9]*|[0-9]*)
      TAG="${arg}"
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [vX.Y.Z] [--dry-run]"
      exit 1
      ;;
  esac
done

# If no tag provided in dry-run mode, read current version from pyproject.toml
if [[ -z "${TAG}" ]]; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    if [[ -f "${BACKEND_DIR}/pyproject.toml" ]]; then
      CURRENT_VER=$(grep -E '^version = "[0-9]+\.[0-9]+\.[0-9]+"' "${BACKEND_DIR}/pyproject.toml" | cut -d '"' -f 2)
      TAG="v${CURRENT_VER}"
      echo "==> No tag specified for dry-run. Using current backend version: ${TAG}"
    else
      TAG="v1.5.0"
    fi
  else
    echo "Error: Release tag is required."
    echo "Usage: $0 <vX.Y.Z> [--dry-run]"
    echo "Example: $0 v1.5.0"
    exit 1
  fi
fi

# Ensure 'v' prefix
if [[ ! "${TAG}" =~ ^v ]]; then
  TAG="v${TAG}"
fi

if [[ ! "${TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]]; then
  echo "Error: Tag must be in semver format (e.g. v1.5.0), got: ${TAG}"
  exit 1
fi

RAW_VERSION="${TAG#v}"
TODAY=$(date +%Y-%m-%d)

echo "==> Preparing release ${TAG} (raw: ${RAW_VERSION}, date: ${TODAY})..."

# Check working directories
for d in "${META_DIR}" "${BACKEND_DIR}" "${FRONTEND_DIR}"; do
  if [[ ! -d "${d}" ]]; then
    echo "Error: Repository directory not found: ${d}"
    exit 1
  fi
  if [[ -n "$(git -C "${d}" status --porcelain)" ]]; then
    if [[ "${DRY_RUN}" == "true" ]]; then
      echo "==> [DRY RUN Warning] Uncommitted changes found in ${d}."
    else
      echo "Error: Uncommitted changes found in ${d}."
      echo "Please commit or stash your changes before releasing."
      exit 1
    fi
  fi
done

CHANGELOG="${META_DIR}/CHANGELOG.md"
RELEASE_NOTES="GalleryVault release ${TAG}"
if [[ -f "${CHANGELOG}" ]]; then
  # Extract Unreleased section text
  EXTRACTED_NOTES=$(awk '/^## \[Unreleased\]/{flag=1; next} /^## \[/{flag=0} flag' "${CHANGELOG}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  if [[ -n "${EXTRACTED_NOTES}" ]]; then
    RELEASE_NOTES="${EXTRACTED_NOTES}"
  fi
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "--------------------------------------------------"
  echo "[DRY RUN] Release workflow preview:"
  echo "  1. Update ${BACKEND_DIR}/pyproject.toml version -> ${RAW_VERSION}"
  echo "  2. Update ${META_DIR}/CHANGELOG.md [Unreleased] -> [${RAW_VERSION}] - ${TODAY}"
  echo "  3. Commit backend version bump on main"
  echo "  4. Commit meta changelog update on main"
  echo "  5. Create git tags on main:"
  echo "     - Meta:     git tag -a ${TAG} -m \"Release ${TAG}\""
  echo "     - Backend:  git tag ${TAG}"
  echo "     - Frontend: git tag ${TAG}"
  echo "  6. Create GitHub releases:"
  echo "     - Meta:     gh release create ${TAG} --title \"${TAG}\" (with CHANGELOG notes)"
  echo "     - Backend:  gh release create ${TAG} --title \"${TAG}\""
  echo "     - Frontend: gh release create ${TAG} --title \"${TAG}\""
  echo "--------------------------------------------------"
  echo "[DRY RUN] Release Notes Preview:"
  echo "${RELEASE_NOTES}"
  echo "--------------------------------------------------"
  echo "[DRY RUN] Completed successfully. No changes applied."
  exit 0
fi

# 1. Update pyproject.toml
PYPROJECT="${BACKEND_DIR}/pyproject.toml"
if [[ -f "${PYPROJECT}" ]]; then
  sed -i -E "s/^version = \"[0-9]+\.[0-9]+\.[0-9]+\"/version = \"${RAW_VERSION}\"/" "${PYPROJECT}"
  git -C "${BACKEND_DIR}" add pyproject.toml
  git -C "${BACKEND_DIR}" commit -m "chore: align pyproject version with releases (${TAG})" || true
fi

# 2. Update CHANGELOG.md
if [[ -f "${CHANGELOG}" ]]; then
  sed -i "s/^## \[Unreleased\]/## [Unreleased]\n\n## [${RAW_VERSION}] - ${TODAY}/" "${CHANGELOG}"
  git -C "${META_DIR}" add CHANGELOG.md
  git -C "${META_DIR}" commit -m "docs: release ${TAG} changelog" || true
fi

# 3. Create tags
git -C "${META_DIR}" tag -a "${TAG}" -m "Release ${TAG}" || true
git -C "${BACKEND_DIR}" tag "${TAG}" || true
git -C "${FRONTEND_DIR}" tag "${TAG}" || true

echo "==> Release ${TAG} prepared and tagged across all 3 repositories."
echo "==> Next steps: push commits and tags to GitHub, then run gh release create."
