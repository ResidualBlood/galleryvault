# GalleryVault

<p align="center">
  <img src="frontend/assets/icon.svg" alt="GalleryVault Logo" width="96" height="96">
</p>

<p align="center">
  <strong>Self-hosted gallery library</strong><br>
  Index Ehviewer export folders and CBZ · optional E-Hentai / ExHentai favorites sync · local reader
</p>

<p align="center">
  <a href="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml"><img src="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg" alt="Backend CI"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml"><img src="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg" alt="Frontend CI"></a>
  <a href="https://hub.docker.com/u/residualblood"><img src="https://img.shields.io/badge/docker-images-blue?logo=docker" alt="Docker"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/wiki/Home-EN"><img src="https://img.shields.io/badge/docs-wiki-9cf?logo=github" alt="Wiki"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

<p align="center">
  <a href="README.md">中文</a> · <strong>English</strong> · <a href="https://github.com/ResidualBlood/galleryvault/wiki/Home-EN">Wiki</a>
</p>

---

Files, the index, and favorite mappings stay on your machine or NAS. Without cookies it is a local library. Cookies are required for Discover, favorites sync, and downloads.

| Page | Route | What it does |
| :--- | :--- | :--- |
| Browse / Library / Tags | `#/browse` `#/library` `#/tags` | Scan, filter, search, infinite scroll |
| Series | `#/series` | Cluster doujin/manga by title; edit membership |
| Discover | `#/discover` | Popular / Watched / Toplist (needs cookies) |
| Favorites / Updates | `#/favorites` `#/updates` | Watch 10 folders, incremental download, GID replacements |
| Downloads | `#/downloads` | Page-by-page or official Archive zip; exponential backoff |
| Manage | `#/recycle` | Recycle bin, same-GID copies, favorite dupes, cross-GID, integrity, cold archive |
| Reader | `#/reader/...` | RTL / dual-page / webtoon; GIF/WebP slideshow follows frame duration |
| Settings / Logs | `#/settings` `#/logs` | Paths, concurrency, encrypted sessions, background tasks |

Also: local lists and star ratings, OPDS (Tachiyomi / Mihon, …), optional AES-256-GCM for cookies and secrets at rest, optional Telegram bot (paste URLs to enqueue, InlineKeyboard queue, scan / quota / local search).

Screenshots: [Wiki · Screenshots](https://github.com/ResidualBlood/galleryvault/wiki/Screenshots-EN).

---

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. Open `http://<host-ip>:8000` (API binds `127.0.0.1:8001` only, proxied by the frontend).
2. Default password **`p1a2s3s4`**. First login goes to `#/welcome`; you must change it.
3. Put existing galleries in `./library`, then **Scan library** on the Library page. Downloads land in `./downloads`, never in library.

### Volumes

| Host path | Container | Purpose |
| :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql` | PostgreSQL 18 (UID 999 — do not chown to yourself) |
| `./library` | `/library` | Existing library; downloads never write here. Read-only mounts fail deletes and log it |
| `./downloads` | `/downloads` | New downloads, ingested immediately |
| `./cache` | `/gv-cache` | Thumbnail / cover cache |
| `./Archive` | `/archive` | **Optional**; commented out in compose. Set `archive_roots` in Settings after mounting |

To enable cold archive, add e.g. `- ./Archive:/archive`, save Settings, then use **Manage → Cold archive** (`#/archive`). CBZ names are always `gid-english-title.cbz`, independent of the UI title language.

### Environment

Set these on the backend service in `docker-compose.yml`:

- `ENCRYPTION_KEY`: any long random string (not a 32-byte hex key). Encrypts cookies / bot token / password hashes with AES-256-GCM. Losing it makes ciphertext unreadable; see [Encryption](https://github.com/ResidualBlood/galleryvault/wiki/Encryption-EN).
- `AUTH_SECRET`: session HMAC. If unset, generated on first boot and stored in the DB.
- `PUID` / `PGID`: avoid root-owned files on NAS.
- `TRUSTED_PROXIES`: proxy CIDRs, e.g. `127.0.0.1,192.168.1.0/24`.
- `POSTGRES_PASSWORD`: DB password, default `galleryvault`.

Library / download / archive paths are configured in the Web UI, not via env vars.

---

## Docs

- [Usage](https://github.com/ResidualBlood/galleryvault/wiki/Usage-EN) — wizard, cookies, nav
- [Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment-EN) — mounts, Nginx/Caddy, tiered storage
- [Manage](https://github.com/ResidualBlood/galleryvault/wiki/Manage-EN) — dedupe, integrity, cold archive, logs
- [Settings](https://github.com/ResidualBlood/galleryvault/wiki/Settings-EN) — concurrency, archive, OPDS
- [FAQ](https://github.com/ResidualBlood/galleryvault/wiki/FAQ-EN)

Client compatibility (Ehviewer family, JHenTai, OPDS readers): [Compatibility](https://github.com/ResidualBlood/galleryvault/wiki/Compatibility-EN).

---

## Acknowledgements

- Ehviewer_CN_SXJ — directory and SpiderInfo conventions
- EhTagTranslation — tag database
- ehsyringe — translation packaging

---

## Disclaimer

### 1. NSFW / 18+

This software is for organizing media on private hardware. It may be used with adult content. **Only for people of legal adult age.** If you are a minor or local law forbids it, stop using the software.

### 2. Third-party content

GalleryVault **does not host or distribute** media files. E-Hentai / ExHentai access needs your own cookies. You are solely responsible for what you search, download, and store.
