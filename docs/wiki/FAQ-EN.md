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
**No.** The scanner extracts and validates image byte streams in memory, without creating temporary residual files on host storage.

---

## 2. Credentials, Cookies & Security

### 1. Are all devices logged out when the administrator password is changed?
**Yes.** This is an intentional security design: changing the password immediately revokes all persisted session credentials across all devices, requiring re-authentication.

### 2. What happens if I lose my `ENCRYPTION_KEY`?
Database encryption uses mathematically irreversible AES-256-GCM. **A lost key cannot be recovered**. Refer to **[Encryption at Rest → Recovering from a Lost Key](Encryption-EN#recovering-from-a-lost-key)** for emergency reset procedures.

### 3. Top banner shows "Cookie expired" or "No ExHentai access"?
System probes run periodically in the background:
- **Cookie expired**: The session has ended. Go to *Settings → ExHentai*, supply fresh cookies, and click *Test login*.
- **No ExHentai access**: Account lacks required tier privileges or `igneous` is missing. You can switch to the public domain `e-hentai.org`. During these alerts, background sync pauses safely to prevent data corruption.

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
- `ReadTimeout`: An upstream H@H node stalled; the watchdog will drop it and retry.
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

---

## 5. Reader, Tags & Client Ecosystem

### 1. Why are certain tags untranslated?
Tag translations are sourced directly from the authoritative [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database). Unregistered tags or rare author names display in their original language. You can fetch updates at any time via *Update translations now* on the Logs page.

### 2. Do search filters persist after reading and returning?
**Yes.** The reader preserves search filter contexts. Navigating through pages and returning to the library retains all active multi-tag filters, sorting criteria, and scroll positions.

### 3. How do I connect third-party mobile readers (Tachiyomi / Mihon / Panels)?
GalleryVault provides a standard OPDS catalog endpoint at `GET /api/opds`. Add the OPDS feed in your reader client using HTTP Basic authentication (username: `galleryvault`, password: your administrator web password).

### 4. Does "Add to Home Screen" (PWA) download galleries for offline use?
**No.** The PWA caches the web interface shell and static assets only to deliver app-like responsiveness. Galleries and images stream on demand to avoid filling mobile storage.
