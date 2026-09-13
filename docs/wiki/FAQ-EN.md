# Frequently Asked Questions (FAQ)

> [中文](FAQ) · **English**

This document organizes common troubleshooting scenarios and operational questions for GalleryVault by domain.

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
This is GalleryVault's built-in CSRF protection verifying client origin against the host header. When deploying behind external proxies (Nginx, Caddy, Cloudflare), ensure the proxy forwards the incoming host header (e.g. `proxy_set_header Host $http_host;`). In addition, configure `TRUSTED_PROXIES` in `docker-compose.yml` with your proxy CIDR range. See **[Deployment Guide → Security Hardening](Deployment-EN#reverse-proxy-best-practices)**.

### 2. How do I change external ports or bind a custom domain?
Adjust the external port mapping for `galleryvault-frontend` in `docker-compose.yml` (e.g. `"8888:80"`). For custom domain names and HTTPS certificates, terminating TLS at an external Nginx or Caddy proxy is recommended.

### 3. PostgreSQL container fails to boot with `Operation not permitted`?
The official PostgreSQL image relies strictly on container UID 999 (`postgres`). **Never run a blanket `chown` on `./db-data`** for normal host users. If accidentally modified, restore ownership on the host: `chown -R 999:999 ./db-data`.

### 4. Does scanning a 7z archive extract all files to disk?
**It does not unpack the whole archive into the library.** Scans read image members only. Opening a page extracts that one file into a temp directory and deletes it afterwards. Non-image files stay packed. `.cbr` / `.rar` also need host `unrar` or libarchive, or the scan fails.

### 5. PostgreSQL 18 container fails to start after an upgrade?
Official `postgres:18-alpine` stores data under a versioned subdirectory of `/var/lib/postgresql`. The shipped `docker-compose.yml` bind-mounts host `./db-data` to `/var/lib/postgresql`. **Do not set `PGDATA`**, and do not keep the old mount `/var/lib/postgresql/data` (a non-empty data directory check will exit the container). Fresh installs just need `docker compose up -d`. See **[Deployment → Storage topology](Deployment-EN#storage-topology--volume-mounts)**.

---

## 2. Credentials, Cookies & Security

### 1. Are all devices logged out when the administrator password is changed?
**Yes.** This is an intentional security design: changing the password immediately revokes all persisted session credentials across all devices, requiring re-authentication.

### 2. What happens if I lose my `ENCRYPTION_KEY`?
Database encryption uses mathematically irreversible AES-256-GCM. **A lost key cannot be recovered**. Refer to **[Encryption at Rest → Recovering from a Lost Key](Encryption-EN#recovering-from-a-lost-key)** for emergency reset procedures.

### 3. Top banner shows a Cookie / probe alert?
System probes run at startup and every 30 minutes:
- **Cookie expired** (red): The session has ended. Go to *Settings → ExHentai*, supply fresh cookies, and click *Test login*.
- **No ExHentai access** (red): Account lacks required privileges or `igneous` is missing. You can switch to `e-hentai.org`.
- **IP banned** (red): The site reported an IP ban or temporary block — not a missing `igneous`. Change egress or wait.
- **Probe failed** (orange): Network or site error; the Cookie may still be valid.
Red-banner states pause cloud sync to prevent local data corruption.

### 4. Why shouldn't credentials be configured via environment variables?
The PostgreSQL database serves as the single source of truth (SSOT) for application settings. Hardcoding secrets in environment files risks silent discrepancies; settings should be maintained in the Web UI, where they are automatically encrypted at rest when `ENCRYPTION_KEY` is configured.

---

## 3. Download Pipeline & Concurrency

### 1. Downloads auto-pause with a 302 challenge warning?
This occurs when the upstream service applies temporary anti-scraping rate limits. GalleryVault automatically suspends the queue to protect your account. Background probes check every 10 minutes (configurable via `GV_CHALLENGE_PROBE_INTERVAL`), and the queue **resumes automatically once the restriction is lifted**.

### 2. Do archive downloads re-charge GP on resumes or retry?
**Never.** When an archive download starts, the assigned download URL is cached in local task metadata. Range resumes or error retries reuse this exact URL and **never charge GP again**.

### 3. How do I troubleshoot `image download request failed` errors?
This indicates transient upstream connectivity issues, slow H@H nodes, or proxy drops. The system automatically retries with exponential backoff (30s up to 6h). Inspect logs using:
```bash
docker logs galleryvault-backend --since 6h | grep -E "download task failed|page download failed"
```
- `ReadTimeout`: An upstream H@H node stalled; the watchdog drops it. If the page has no node key, HTML is parsed for a replacement node.
- `ConnectTimeout` / `RemoteProtocolError`: Proxy link instability. Check proxy node quality or lower `page_concurrency` in Settings.

### 4. Why does an in-flight page keep downloading after clicking Pause?
Clicking Pause stops claiming new pages or tasks from the pool. Images currently mid-transfer finish their byte stream safely to prevent corrupt files on disk.

---

## 4. Library Management, Deduplication & Updates

### 1. Do galleries disappear if their mount path is removed from Settings?
**No.** Removing a path simply excludes it from subsequent scanning sweeps. Already ingested metadata and gallery records remain intact in the database.

### 2. Can deleted galleries be restored?
- If deleted **without** checking "Delete files from disk", the gallery moves to the Recycle Bin and can be restored with a single click.
- If deleted with disk purge checked, files are permanently deleted from storage.

### 3. Why does an updated gallery still appear under Updates after downloading?
Once the newly assigned GID is fully downloaded into the library, clicking **Scan now** deletes the obsolete local archive and dismisses the update record. If marked as "Ignored", it remains unchanged.

### 4. What is Cross-GID Deduplication?
Different translation groups or quality variants of the same artwork often carry distinct GIDs online. Cross-GID deduplication clusters these works together locally, allowing you to easily identify duplicates, select the best version, and purge redundant copies.

### 5. How do I resolve "File name too long" / "[Errno 36]" errors during archiving or downloads?
- **Root Cause**: Linux ext4 and most modern filesystems impose a strict 255-byte limit per filename component. Multi-byte CJK characters consume 3 bytes each in UTF-8. Legacy character-based truncation often overflowed 255 bytes when saving long titles or appending temporary suffixes like `.cbz.partial`, triggering operating system `[Errno 36] File name too long` exceptions.
- **Current Standard**: GalleryVault enforces a **243-byte truncation standard** on base filenames (leaving 12 bytes for the `.cbz.partial` staging suffix, ensuring the total length never exceeds 255 bytes). Directory names are clamped to 247 bytes.
- **Fixing existing archives**: `scripts/repair_cbz_filenames.py` lives in the git repo root and is **not copied into the backend image**. On a host with a full clone:
  ```bash
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive --dry-run
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```
  Inside the container, use `repair_cold_archives.py` (next item) for sidecar/GID cleanup.

### 6. How do I batch-clean duplicated leading GID prefixes (e.g., `[12345] 12345-Title`)?
- **Cause**: Exports from third-party tools or repeated multi-hop migrations can introduce redundant leading GID prefixes into directory names or cold archive CBZ files (e.g. `[12345] 12345-Title` or `12345-12345-Title`), causing malformed title indexing or polluted archive indices.
- **Remediation**: The repository provides an offline batch repair tool `backend/galleryvault/scripts/repair_cold_archives.py`. Supporting a `--dry-run` safety flag, it strips redundant leading GIDs from directory and CBZ names, cleans up nested GID patterns, and queries the upstream GData API in batch chunks to re-verify and sanitize metadata (see **[Backup & Restore → Offline Full Repair & Metadata Sanitization Tools](Backup-EN#offline-full-repair--metadata-sanitization-tools)**).

### 7. How does multi-root cold storage (`archive_roots`) balance capacity across multiple disks?
- **Configuration**: In **Settings → Library → Cold archive roots**, enter multiple mount paths (one path per line, e.g., `/archive1` and `/archive2`).
- **Dynamic Load Balancing**: When cold archiving is triggered, the backend checks free space on every configured root via `statvfs` and writes the new CBZ to the volume with the most free space (and enough headroom). A volume is capped at 500 pages and 2GiB; larger galleries split.

### 8. How do I detect missing pages or corrupted image archives in the library?
- Open **Manage → Integrity** (`#/integrity`) and click **Scan missing pages & corrupt images**.
- The scan checks image magic headers (JPEG / PNG / GIF / WebP) and 4/8-digit zero-padded names; it does not unpack whole archives into the library.
- Review the red list, then **Repair** or **Select all and repair**. Only missing or corrupt pages are re-downloaded, keeping the original quality tier.

---

## 5. Reader, Tags & Client Ecosystem

### 1. Why are certain tags untranslated?
Tag translations come from [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database). Unknown tags stay in the original language. Click **Update now** under **Settings → Tags**. Progress shows on Logs; the button is not on the Logs page.

### 2. Do search filters persist after reading and returning?
**Yes.** The reader preserves search filter contexts. Navigating through pages and returning to the library retains all active multi-tag filters, sorting criteria, and scroll positions.

### 3. How do I connect third-party mobile readers (Tachiyomi / Mihon / Panels)?
GalleryVault provides a standard OPDS catalog endpoint at `GET /api/opds`. Add the OPDS feed in your reader client using HTTP Basic authentication (username: `galleryvault`, password: your administrator web password).

### 4. Does "Add to Home Screen" (PWA) download galleries for offline use?
**No.** The PWA caches the web interface shell and static assets only to deliver app-like responsiveness. Galleries and images stream on demand to avoid filling mobile storage.

### 5. What can the Telegram bot do, and where are the commands listed?
Fill in the token / chat ID / allowed user IDs under **Settings → Telegram**. Startup then registers the client command menu. Paste a gallery URL in chat to enqueue; `/queue` uses InlineKeyboard; `/status` `/storage` `/quota` `/cookie` probe the system; `/search` `/info` `/random` query the local library (covers included). Full command table: **[Settings → Telegram bot control commands](Settings-EN#settings-settings)**.
