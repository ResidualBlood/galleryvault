# Frequently Asked Questions (FAQ)

> [中文](FAQ) · **English**

Troubleshooting notes, grouped by topic.

---

## Quick Index
- [1. Installation & Deployment Troubleshooting](#1-installation--deployment-troubleshooting)
- [2. Credentials, Cookies & Security](#2-credentials-cookies--security)
- [3. Download Pipeline & Concurrency](#3-download-pipeline--concurrency)
- [4. Library Management, Deduplication & Updates](#4-library-management-deduplication--updates)
- [5. Reader, Tags & Client Ecosystem](#5-reader-tags--client-ecosystem)

---

## 1. Installation & Deployment Troubleshooting

### 1. Behind a reverse proxy or across subnets, write operations fail with "Cross-origin request rejected"?
- **Cause**: CSRF protection validates client origin against the host header. Mutations fail (HTTP 403) when proxies strip `Origin`, when clients pass `Origin: null` (sandboxed iframes), or when requests carry session cookies without valid CSRF tokens.
- **Remediation**: Configure reverse proxies to forward the Host header and preserve `Origin` (e.g. `proxy_set_header Host $http_host;` in Nginx). If behind private reverse proxy subnets, configure `TRUSTED_PROXIES` in `docker-compose.yml`.
- **Details**: See **[Deployment Guide → Security Hardening](Deployment-EN#reverse-proxy-best-practices)**.

### 2. How do I change external ports or bind a custom domain?
- **Scenario**: Port conflicts or binding custom domains with TLS.
- **Remediation**: Adjust the host port mapping for `galleryvault-frontend` in `docker-compose.yml` (e.g. `"8888:80"`). For custom domains and HTTPS, terminate TLS with an external reverse proxy (Nginx or Caddy) pointing to the frontend port.
- **Details**: See **[Deployment Guide → Compose Service Definitions & Environment](Deployment-EN#1-compose-service-definitions--environment)**.

### 3. PostgreSQL container fails to boot with `Operation not permitted`?
- **Cause**: The official PostgreSQL image runs strictly under container UID 999 (`postgres`). Changing ownership of `./db-data` on the host to non-999 users causes permission failures.
- **Remediation**: Do not run a blanket `chown` for normal host users. Restore host permissions with `chown -R 999:999 ./db-data`.
- **Details**: See **[Deployment Guide → Permission Mapping Standards (PUID / PGID)](Deployment-EN#permission-mapping-standards-puid--pgid)**.

### 4. Does scanning a 7z archive extract all files to disk?
- **Mechanism**: Scans inspect archive headers and index image entries only; full extraction into the library directory is never performed. Individual pages decompress in memory on demand.
- **Limits**: Uncompressed single-page size is capped at **128MB**; oversize pages return HTTP 404. Formats such as `.cbr` and `.rar` require host-installed `unrar` or libarchive to enable parsing.
- **Details**: Format support and limits are documented in **[Client Compatibility & Metadata Specifications → Archive Format Support Matrix](Compatibility-EN#1-archive-format-support-matrix)**.

### 5. PostgreSQL 18 container fails to start after an upgrade?
- **Cause**: `postgres:18-alpine` stores database files under a versioned subdirectory of `/var/lib/postgresql`. Retaining the legacy mount `/var/lib/postgresql/data` or setting `PGDATA` triggers directory non-empty errors and terminates the container.
- **Remediation**: Mount host `./db-data` directly to `/var/lib/postgresql` without setting `PGDATA`. For clean setups, execute `docker compose up -d`.
- **Details**: See **[Deployment → Storage topology](Deployment-EN#storage-topology--volume-mounts)**.

---

## 2. Credentials, Cookies & Security

### 1. Are all devices logged out when the administrator password is changed?
- **Cause**: Password modifications invalidate all active persisted session tokens immediately.
- **Result**: All signed-in clients must re-authenticate with the new password.

### 2. What happens if I lose my `ENCRYPTION_KEY`?
- **Cause**: Static encryption utilizes AES-256-GCM; ciphertext cannot be decrypted without the key.
- **Remediation**: Reset `runtime_auth` credentials to revert administrator password to `p1a2s3s4` and regenerate `auth_secret`; clear old encrypted cookies and tokens, then re-enter them in Settings.
- **Details**: See **[Encryption at Rest → Recovering from a Lost Key](Encryption-EN#recovering-from-a-lost-key)** for complete commands and impact notes.

### 3. Top banner shows a Cookie / probe alert?
System background probes run at startup and every 30 minutes:
- **Cookie expired** (red): Session terminated. Enter fresh cookies under Settings → ExHentai and select **Test login**.
- **No ExHentai access** (red): Account lacks privileges or has invalid `igneous`. Switch domain to `e-hentai.org`.
- **IP banned** (red): Upstream reported an IP ban or rate block; wait or change egress nodes (not an `igneous` issue).
- **Probe failed** (orange): Network timeout or upstream fluctuation; cookies may still be valid.
Red-banner states pause cloud sync tasks to protect local library integrity.

### 4. Why shouldn't credentials be configured via environment variables?
- **Cause**: PostgreSQL functions as the single source of truth (SSOT). Hardcoding credentials in environment files leads to configuration divergence.
- **Remediation**: Save settings in the Web UI. When `ENCRYPTION_KEY` is active, sensitive fields are encrypted at rest automatically.

---

## 3. Download Pipeline & Concurrency

### 1. Downloads auto-pause with a 302 challenge warning?
- **Cause**: Upstream rate-limiting triggered; the system suspends downloads to protect accounts from bans.
- **Remediation**: Probes run every 10 minutes by default; queues resume automatically once restrictions clear.

### 2. Do archive downloads re-charge GP on resumes or retry?
- **Mechanism**: Generated archive tasks persist their download URL in task metadata. Standard HTTP Range resumes and retries reuse this URL without re-applying for upstream packaging.
- **Exceptions**: If upstream archive files expire, corrupt, or are explicitly regenerated by the user, re-applying upstream will deduct GP according to site policies.

### 3. How do I troubleshoot `image download request failed` errors?
- **Cause**: Network jitter, H@H node drops, or proxy timeouts. The pipeline applies exponential backoff retries (30s up to 6h).
- **Remediation**:
  Check backend logs on host:
  ```bash
  docker logs galleryvault-backend --since 6h | grep -E "download task failed|page download failed"
  ```
  - `ReadTimeout`: H@H node timed out; watchdog skips or rotates nodes.
  - `ConnectTimeout` / `RemoteProtocolError`: Proxy link instability; verify proxy quality or reduce `page_concurrency` under Settings.

### 4. Why does an in-flight page keep downloading after clicking Pause?
- **Cause**: Pausing stops dispatching new pages and tasks. In-flight image downloads finish their byte stream to guarantee valid on-disk files.

---

## 4. Library Management, Deduplication & Updates

### 1. Do galleries disappear if their mount path is removed from Settings?
- **Cause**: Removing directory paths tells scanners to bypass that location during future scans.
- **Result**: Existing gallery index rows and metadata in PostgreSQL remain preserved.

### 2. Can deleted galleries be restored?
- **Without deleting files from disk**: Gallery moves to the Recycle Bin and can be restored with one click.
- **With disk file deletion**: Gallery is staged in the Recycle Bin first and unindexed only after on-disk files are fully removed. Deletion failures keep items in the Recycle Bin. If any copy sits outside configured scan roots, **the entire gallery is skipped**. Read-only mounts preserve records and report failures.
- **Details**: See **[Library Maintenance Guide → Recycle Bin & Deletion Protection](Manage-EN#recycle-bin--deletion-protection)**.

### 3. Why does an updated gallery still appear under Updates after downloading?
- **Cause**: Once a replacement gallery GID completes downloading, an update verification check is required.
- **Remediation**: Click **Scan now**; the system verifies the new version on disk and purges the obsolete copy. Ignored entries are preserved without deletion.

### 4. What is Cross-GID Deduplication?
- **Mechanism**: Strips convention prefixes, scanlation tags, and version suffixes to cluster matching works across different GIDs based on core title and `artist` namespace similarity.
- **Operation**: Compare local ingested copies against upstream bookmark entries under Manage → Duplicates → Cross-GID. Select preferred versions to remove remote bookmarks, delete local copies, or ignore groups.

### 5. How do I resolve "File name too long" / "[Errno 36]" errors during archiving or downloads?
- **Cause**: Linux filesystems enforce a 255-byte limit per filename component. Multi-byte UTF-8 titles combined with temporary staging suffixes like `.cbz.partial` (12 bytes) trigger `[Errno 36]`.
- **Standards**: Base filenames are constrained to ≤ 243 bytes, and directory names to ≤ 247 bytes. Details in **[Client Compatibility & Metadata Specifications → CBZ / CBR Archives & Specifications](Compatibility-EN#2-cbz--cbr-archives--specifications)**.
- **Remediation**: Align legacy archive filenames using the host tool in the repo root (not bundled in backend image):
  ```bash
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive --dry-run
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```
  See **[Deployment Guide → Maintenance Tools & Offline Repair Scripts Reference](Deployment-EN#maintenance-tools--offline-repair-scripts-reference)**.

### 6. How do I batch-clean duplicated leading GID prefixes (e.g., `[12345] 12345-Title`)?
- **Cause**: External migrations or scraping tools often stack prefixes (e.g. `[12345] 12345-Title`), causing malformed title parsing.
- **Remediation**: Use `repair_cold_archives.py` to sanitize names and re-query ExHentai GData to refresh `.galleryvault.json`:
  ```bash
  # Dry-run inspection
  docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive --dry-run

  # Execute cleanup
  docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive
  ```
  Background context is under **[Backup & Restore → Offline Full Repair & Metadata Sanitization Tools](Backup-EN#offline-full-repair--metadata-sanitization-tools)**; complete options are under **[Deployment Guide → Maintenance Tools & Offline Repair Scripts Reference](Deployment-EN#maintenance-tools--offline-repair-scripts-reference)**.

### 7. How does multi-root cold storage (`archive_roots`) balance capacity across multiple disks?
- **Balancing**: Configure multiple paths under Settings → Library. Archiving inspects available disk space using `statvfs` and writes new CBZs to the volume with the largest free capacity. Single archives are capped at 500 pages and 2GiB, exceeding which generates an uncompressed cold directory.
- **Purge Source Directories**: Select the purge button in the Storage panel (`POST /api/system/purge-archived-sources`). Pending/downloading tasks are skipped; loose images are removed only when complete CBZs exist in cold roots.
- **Details**: Mount patterns are documented in **[Deployment Guide → Tiered Storage & Multi-Disk Mounting](Deployment-EN#2-tiered-storage--multi-disk-mounting)**.

### 8. How do I detect missing pages or corrupted image archives in the library?
- **Inspection**: Open Manage → Integrity (`#/integrity`) and click **Scan missing pages & corrupt images**. Checks evaluate magic binary headers (JPEG/PNG/GIF/WebP) and sequential numbering.
- **Remediation**: Corrupted items are highlighted in red. Click **Repair** or **Select all and repair** to re-download only missing or damaged pages with the original quality tier.

---

## 5. Reader, Tags & Client Ecosystem

### 1. Why are certain tags untranslated?
- **Cause**: Translations are sourced from EhTagTranslation/Database; missing entries display original English tags.
- **Remediation**: Click **Update now** under Settings → Tags. Background progress is visible on the Logs page.

### 2. Do search filters persist after reading and returning?
- **Behavior**: Yes. The reader maintains browsing context; returning from reading preserves multi-tag filters, sorting criteria, and page positions.

### 3. How do I connect third-party mobile readers (Tachiyomi / Mihon / Panels)?
- **Remediation**: The system exposes standard OPDS feeds (`GET /api/opds`). Connect using HTTP Basic authentication with username `galleryvault` and your administrator password.

### 4. Does "Add to Home Screen" (PWA) download galleries for offline use?
- **Behavior**: No. The PWA shell caches interface styling and app frames; gallery assets stream on demand to avoid consuming local device storage.

### 5. What can the Telegram bot do, and where are the commands listed?
- **Capabilities**: Configure tokens and allowed user IDs under Settings → Telegram. It supports pasting gallery URLs to enqueue downloads, `/queue` queue operations, `/status` `/storage` `/quota` `/cookie` system probes, and `/search` `/info` `/random` library queries.
- **Command Reference**: The complete command list is under **[Settings → Telegram bot control commands](Settings-EN#settings-settings)**.
