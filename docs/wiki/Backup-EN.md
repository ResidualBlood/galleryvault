# Backup & Restore

The database is the only state that must be backed up (gallery index, settings,
history; thumbnails and the gallery files themselves are rebuildable).

## Backup

`scripts/backup.sh` in a full git clone runs `pg_dump` online (do not stop services). **A directory that only curled `docker-compose.yml` does not have this script** — use `pg_dump` below, or clone the repo.

```bash
# Full clone:
./scripts/backup.sh        # writes backups/galleryvault_<timestamp>.dump, keeps the 14 most recent

# Equivalent:
docker compose exec -T db pg_dump -U galleryvault -Fc galleryvault > backups/galleryvault_$(date +%Y%m%d).dump
```

Recommended via cron, for example:

```
0 3 * * * cd /path/to/galleryvault && ./scripts/backup.sh
```

## Restore

There is no `restore.sh`; restore with the commands on this page. Stop backend before restore, then `pg_restore -c --if-exists`:

```bash
docker compose exec -T db pg_restore -U galleryvault -d galleryvault -c --if-exists \
  < backups/galleryvault_<timestamp>.dump
```

> Restoring overwrites the current database. If the backup predates encryption,
> just set `ENCRYPTION_KEY` again afterwards — see
> [Encryption](Encryption-EN).

## The key in backups

With [encryption at rest](Encryption-EN) enabled, cookies / tokens in the
database backup are ciphertext. **The backup does not contain the key** — keep
`ENCRYPTION_KEY` in a password manager, separate from the backup. If the key is
lost, see [Encryption at Rest → Recovering from a lost key](Encryption-EN#recovering-from-a-lost-key).

---

## Cold Storage Multi-Root Directories & Naming Conventions (`archive_roots`)

GalleryVault supports distributing cold CBZ archives across multiple disks or NAS shares to reduce hot storage usage. Archives and sidecars stored on cold storage volumes represent persistent assets and should be included in regular backup routines.

### 1. Multi-Root Storage & Dynamic Capacity Balancing (`statvfs`)
- Configuration of multiple archive mount points, `archive_roots` settings, `statvfs`-based dynamic capacity balancing, and safe source cleanup are detailed in [Deployment Guide → Tiered Storage & Multi-Disk Mounting](Deployment-EN#2-tiered-storage--multi-disk-mounting).
- When running safe source purging (`POST /api/system/purge-archived-sources`), the system skips tasks in active downloading states and removes unpacked source images only after cold archives are verified.

### 2. Canonical English Naming & 243-Byte Boundary (`gid-gallery.title.cbz`)
- Cold archives use official English/Romanized titles to maintain compatibility across operating systems and network transfer protocols (SMB, NFS, WebDAV, rsync).
- Detailed specifications for the 243-byte base filename truncation limit, 12-byte temporary suffix headroom, and 247-byte directory limits are tabulated in [Compatibility and Scope → Graceful Degradation & Fallback](Compatibility-EN#graceful-degradation--fallback).

---

## Offline Full Repair & Metadata Sanitization Tools

When external migrations or legacy tools leave archives with stacked GID prefixes or overlong filenames, offline maintenance scripts are available in the repository. Complete parameter definitions and command examples are provided in [Deployment Guide → Offline Maintenance & Repair Utilities](Deployment-EN#offline-maintenance--repair-utilities).

### 1. Cold Archive & Local Directory Repair (`repair_cold_archives.py`)
- **Applicability**: Strips duplicate leading GID prefixes (such as `[12345] 12345-Title`) and queries upstream GData APIs to reconstruct `.galleryvault.json` sidecar indexes.
- **Safety**: Supports `--dry-run` simulation mode; recommended to run inside the backend Docker container. See [Deployment Guide → Cold Archive & Local Directory Repair](Deployment-EN#1-cold-archive--local-directory-repair-repair_cold_archivespy).

### 2. CBZ Filename Truncation Alignment (`repair_cbz_filenames.py`)
- **Applicability**: Scans target directories and truncates legacy CBZ filenames to 243 bytes, resolving filesystem boundary errors.
- **Requirements**: Located at repository root `scripts/`, not packaged into the container image; must be run directly on the host. See [Deployment Guide → CBZ Filename 243-Byte Boundary Alignment](Deployment-EN#2-cbz-filename-243-byte-boundary-alignment-repair_cbz_filenamespy).
