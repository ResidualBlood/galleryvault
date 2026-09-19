<div align="center">

<img src="frontend/assets/icon.svg" alt="GalleryVault Logo" width="96" height="96">

# GalleryVault

**Self-hosted gallery library for Ehviewer export directories**

[![Backend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki/Home-EN)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

[Quick start](#quick-start) · [Features](#features) · [Wiki](https://github.com/ResidualBlood/galleryvault/wiki/Home-EN) · [中文](README.md)

</div>

---

Mount Ehviewer export directories and browse them in the browser. Renaming or re-packing is not required. With cookies configured, Discover, favorite-folder sync, and downloads are available; without cookies the app still works as a local library. Files remain on the host.

## Features

📁 **Directory scanning** — Native `<gid>-title/` trees, `.ehviewer` (SpiderInfo V1/V2), JHenTai `metadata`, CBZ/CBR, 7z (images only), and PDF. New downloads are written to `downloads/` and do not modify library.

⭐ **Favorites and Discover** — Each of the ten favorite folders can incremental-download or watch only. Discover provides Popular, Watched, and Toplist. When a re-upload changes the GID, the local copy can be replaced in one step.

🧹 **Dedupe, integrity, and cold archive** — Same-GID copies, favorite-folder duplicates, cross-GID clusters (different translations or quality), series grouping, and missing-page / corrupt-image checks. Additional disks can store cold-archive CBZ files.

📖 **Reader** — Right-to-left, dual-page, and webtoon. The slideshow follows GIF/WebP frame duration. OPDS works with Tachiyomi / Mihon. An optional Telegram bot enqueues a gallery from a pasted URL.

🔐 **Encryption** — With `ENCRYPTION_KEY` set, cookies, bot token, and password hashes are stored with AES-256-GCM. Changing the password revokes all sessions.

<p align="center">
  <img src="docs/screenshots/library_en.png" alt="Library" width="270">
  <img src="docs/screenshots/reader_en.png" alt="Reader" width="270">
  <img src="docs/screenshots/fav_dedupe_en.png" alt="Favorite duplicates" width="270">
</p>

More screenshots: [Wiki · Screenshots](https://github.com/ResidualBlood/galleryvault/wiki/Screenshots-EN)

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. Open `http://<host-ip>:8000` (the API binds `127.0.0.1:8001` and is reverse-proxied by the frontend).
2. Default password is **`p1a2s3s4`**. The first login goes to `#/welcome`; the password must be changed.
3. Place existing galleries in `./library` and click **Scan library**. Subsequent downloads are written to `./downloads`, not library.

### Volumes

| Host path | Container | Purpose |
| :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql` | PostgreSQL 18 data directory (UID 999; do not chown. **Do not use `/var/lib/postgresql/data`; do not set `PGDATA`**) |
| `./library` | `/library` | Existing galleries. Downloads are never written here. On a read-only mount, deletes fail and are logged |
| `./downloads` | `/downloads` | New downloads; ingested as soon as they finish |
| `./cache` | `/gv-cache` | Thumbnail and cover cache |
| `./archive` | `/archive` | Optional; commented out in compose. After enabling, set `archive_roots` in Settings (one container path per line) |

Cold archive: uncomment `- ./archive:/archive`, save `archive_roots` in Settings, then run **Manage → Cold archive** (`#/archive`). CBZ filenames are `gid-english-title.cbz`. Disk balancing and source cleanup: [Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment-EN).

### Environment

Set these on the backend service in `docker-compose.yml`:

- `ENCRYPTION_KEY`: a long random string (not a 32-byte hex key). Cookies, bot token, and password hashes are then stored with AES-256-GCM. If the key is lost, ciphertext cannot be decrypted; see [Encryption](https://github.com/ResidualBlood/galleryvault/wiki/Encryption-EN).
- `AUTH_SECRET`: session signing key. If unset, the first boot generates one and stores it in the database.
- `PUID` / `PGID`: on NAS hosts, keeps downloaded files from being owned by root.
- `TRUSTED_PROXIES`: reverse-proxy CIDRs, e.g. `127.0.0.1,192.168.1.0/24`.
- `POSTGRES_PASSWORD`: database password, default `galleryvault`.

Library, download, and archive roots, and concurrency, are configured in the web UI. Connection-pool tuning: [Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment-EN).

## Docs

| Doc | Contents |
| --- | --- |
| [Usage](https://github.com/ResidualBlood/galleryvault/wiki/Usage-EN) | wizard, cookies, navigation |
| [Features](https://github.com/ResidualBlood/galleryvault/wiki/Features-EN) | feature notes |
| [Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment-EN) | mounts, Nginx/Caddy, archive storage |
| [Manage](https://github.com/ResidualBlood/galleryvault/wiki/Manage-EN) | dedupe, integrity, cold archive |
| [Compatibility](https://github.com/ResidualBlood/galleryvault/wiki/Compatibility-EN) | Ehviewer family, JHenTai, OPDS |
| [FAQ](https://github.com/ResidualBlood/galleryvault/wiki/FAQ-EN) | common issues |

Feedback: [Discussions](https://github.com/ResidualBlood/galleryvault/discussions) · [Issues](https://github.com/ResidualBlood/galleryvault/issues)

## Acknowledgements

- [Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ) — directory layout and SpiderInfo
- [EhTagTranslation](https://github.com/EhTagTranslation/Database) — tag translation database
- [EhSyringe](https://github.com/EhTagTranslation/EhSyringe) — translation data packaging

## Disclaimer

This software is for organizing media on private hardware and may be used with adult content. **It is intended only for users of legal adult age where local law permits.** GalleryVault does not host or distribute media files. Access to E-Hentai / ExHentai requires the user's own cookies. The user is solely responsible for what is searched, downloaded, and stored.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ResidualBlood/galleryvault&type=Date)](https://star-history.com/#ResidualBlood/galleryvault&Date)

---

<div align="center">

If GalleryVault helps you, a ⭐ Star is appreciated

Made with ❤️ by [ResidualBlood](https://github.com/ResidualBlood/)

</div>
