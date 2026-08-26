#!/usr/bin/env bash
# Backup the GalleryVault PostgreSQL database with pg_dump (custom format),
# keeping the most recent dumps and pruning older ones.
#
# Usage:  ./scripts/backup.sh          (run from the docker-compose directory)
# Cron:   0 3 * * * cd /path/to/galleryvault && ./scripts/backup.sh
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p backups
stamp="$(date +%Y%m%d_%H%M%S)"

docker compose exec -T db pg_dump -U galleryvault -d galleryvault -Fc \
  > "backups/galleryvault_${stamp}.dump"

# Keep only the 14 most recent dumps.
ls -1t backups/galleryvault_*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "backup written: backups/galleryvault_${stamp}.dump"
