# GalleryVault documentation

> [中文](Home) · **English**

GalleryVault is a self-hosted gallery library for Ehviewer export directories. Files, the index, and favorite mappings stay on the host or NAS. It scans `<gid>-title/` trees and SpiderInfo. **Cookies are recommended** for E-Hentai / ExHentai sync; without them the app still works as a local library. See [Features](Features-EN).

---

## Overview

- Mount Ehviewer `<gid>-title/` trees, CBZ, 7z (images only), and PDF. SpiderInfo / sidecars are read as-is. No unpack-and-rename step.
- With cookies: Discover, ten favorite folders, page or official Archive downloads, GID replacements.
- Manage: same-GID copies, favorite dupes, cross-GID, missing/corrupt pages, optional multi-disk cold CBZ.
- Reader: RTL / dual-page / webtoon; slideshow follows GIF/WebP frame duration. Optional OPDS, at-rest field encryption, and a Telegram bot (paste URLs to enqueue, queue actions, scan / quota / local search with covers).

Downloads go to `downloads/`. Cold archive uses `archive_roots` you configure (`./archive` is not mounted by default). See [Features](Features-EN).

---

## Get started

### A. Existing Ehviewer folders
1. Mount the host folder into the backend (e.g. `/data/Ehviewer:/Ehviewer:ro`).
2. **Settings → Library**: add the container path to library roots, save.
3. Open **Library** (`#/library`) and click **Scan library**.
4. [Compatibility](Compatibility-EN) · [Library](Library-EN#library-library)

### B. Favorite folders
1. **Settings → Site & proxy**: paste cookies, **Test login**.
2. **Favorites** (`#/favorites`): enable folders; incremental download or watch-only.
3. [Favorites](Favorites-EN#favorites-favorites) · [Downloads](Downloads-EN)

### C. Dedupe and GID replacements
1. **Manage → Favorite duplicates** (`#/duplicates/favorites`).
2. **Manage → Cross-GID** (`#/duplicates/cross-gid`).
3. From Favorites open **Updates** (`#/updates`).
4. [Manage](Manage-EN#duplicate-copies--deduplication-duplicates) · [Updates](Favorites-EN#gallery-updates-updates)

### D. Cold archive
1. Mount archive volumes; set `archive_roots` under **Settings → Library**.
2. **Manage → Cold archive** (`#/archive`) → Start archive; later purge archived sources (same button on the Settings storage table).
3. [Deployment](Deployment-EN) · [Cold archive](Manage-EN#cold-archive-archive)

### E. Series and integrity
1. Top nav **Series** (`#/series`).
2. **Manage → Integrity** (`#/integrity`): scan, then repair.
3. [Series](Library-EN#series-series) · [Integrity](Manage-EN#missing-pages--integrity-integrity)

---

## Index

### Usage

- **[Features](Features-EN)** — behaviors by module
- **[Usage](Usage-EN)** — routes and operations
- **[Screenshots](Screenshots-EN)** — main pages
- **[FAQ](FAQ-EN)** — troubleshooting

### Operations

- **[Compatibility](Compatibility-EN)** — directories, SpiderInfo, sidecars, clients
- **[Deployment](Deployment-EN)** — Compose, mounts, reverse proxy, permissions
- **[Backup](Backup-EN)** — `pg_dump` / `pg_restore`
- **[Encryption](Encryption-EN)** — AES-256-GCM, keys, recovery after loss

API and development notes live in the repo: `backend/docs/API.md` and `backend/docs/DEVELOPMENT.md` (not on the GitHub Wiki).

---

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- URL: `http://<host-ip>:8000`
- Default password: `p1a2s3s4` (login opens `#/welcome`; the password must be changed)
- Data directories: `./library`, `./downloads`, `./db-data`, `./cache`

---

## License

[MIT License](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)
