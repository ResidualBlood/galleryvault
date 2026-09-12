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

### 1. Multi-Root Storage & Dynamic Capacity Balancing (`statvfs`)

GalleryVault supports distributing cold CBZ archives across multiple disks or NAS shares:

- **Configuration**: Specify multiple cold storage mount points under **Settings → Library → Cold archive roots** (one path per line, e.g., `/archive1` and `/archive2`).
- **Dynamic Space Balancing**: A cold archive task checks free space on every configured root via `statvfs` and writes to the volume with enough headroom and the most free space.
- **Intelligent Routing**: New CBZ archives are automatically routed to the storage volume with the largest available free space, achieving automated load balancing across heterogeneous drives without manual intervention.

### 2. Canonical English Naming & 243-Byte Boundary (`gid-gallery.title.cbz`)

- **Cross-Platform Compatibility**: Cold archives strictly adhere to official English/Romanized titles (`gid-gallery.title.cbz`) to avoid character set corruption, illegal escapes, or filesystem incompatibilities across Linux, Windows, macOS, and network protocols (SMB, NFS, WebDAV, rsync).
- **243-Byte Truncation Limit**: Base filenames are strictly truncated to an upper limit of **243 UTF-8 bytes**, reserving 12 bytes of headroom for the temporary `.cbz.partial` staging suffix. This prevents filenames from exceeding the 255-byte boundary and completely eliminates Linux ext4 `[Errno 36] File name too long` errors.
- **Safe Source Purge (`purge-archived-sources`)**: Once a gallery is successfully archived as CBZ in cold storage, administrators can execute "Purge archived sources" from **Settings → Storage** (`POST /api/system/purge-archived-sources`). This operation validates GID consistency across hot and cold storage, actively skips tasks in pending/downloading states, and safely purges loose image directories to reclaim disk space.

---

## Offline Full Repair & Metadata Sanitization Tools

When external migrations, third-party exporters, or historical operations introduce dirty state (such as overlong filenames, stacked leading GID prefixes, or corrupted metadata sidecars), offline maintenance scripts are available in the repository.

### 1. Cold Archive & Local Directory Repair (`repair_cold_archives.py`)

Located at `backend/galleryvault/scripts/repair_cold_archives.py`, this script performs deep health inspection, prefix deduplication, and metadata reconstruction across cold CBZ archives and local gallery folders.

- **Core Capabilities**:
  - **`--dry-run` Simulation Mode**: Inspects corrupt or malformed paths and previews planned renames and metadata updates without modifying any files on disk.
  - **Strip Redundant Leading GIDs**: Detects and strips duplicate GID prefixes caused by multi-hop imports (e.g. `[12345] 12345-Title` or `12345-12345-Title`), restoring canonical `gid-title` naming.
  - **Dual GID Contamination Sanitization**: Cleanses both loose directory structures and cold CBZ packages, purging nested GID anomalies from filenames and internal index entries.
  - **Chunked Upstream GData Re-validation**: Collects sanitized GIDs and performs chunked batch queries against the upstream GData API, fetching authoritative titles, tags, and category taxonomies to rewrite pristine `.galleryvault.json` sidecar files.

- **Usage**:
  ```bash
  # 1. Dry run: preview planned sanitation without touching disk
  python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive --dry-run

  # 2. Execute: strip redundant GIDs, rewrite sidecars, and clean archives
  python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive
  ```

### 2. CBZ Filename Truncation Alignment (`repair_cbz_filenames.py`)

Located at `scripts/repair_cbz_filenames.py`, this script aligns legacy CBZ filenames with current filesystem boundary constraints.

- **Core Capabilities**:
  - **243-Byte Boundary Alignment**: Scans target archive directories and truncates legacy CBZ filenames to 243 UTF-8 bytes (leaving 12 bytes of headroom for `.cbz.partial` to stay strictly within the 255-byte limit).
  - **Eliminating Errno 36**: Completely eliminates `[Errno 36] File name too long` errors induced by multi-byte CJK titles during archiving or syncing.

- **Usage** (repo root `scripts/`; **not** inside the backend image):
  ```bash
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive --dry-run
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```
