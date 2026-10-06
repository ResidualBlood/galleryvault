# GalleryVault documentation

> [中文](Home) · **English**

GalleryVault is a self-hosted gallery library designed for Ehviewer export directories. Files, indexes, and favorite mappings remain on the local machine or NAS. The system scans `<gid>-title/` trees and SpiderInfo metadata. Without cookies configured, it operates as a local gallery library; configuring cookies unlocks online discovery, favorites synchronization, gallery downloads, and re-upload update detection. For complete feature details, see [Features](Features-EN).

---

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- Access: `http://<host-ip>:8000`
- Default password: `p1a2s3s4` (login opens `#/welcome`; the password must be changed on first login)
- Data directories: `./library`, `./downloads`, `./db-data`, `./cache`

---

## Overview

- Local capabilities: Directly mount Ehviewer `<gid>-title/` directories, CBZ, 7z (extract images), and PDF files; reads SpiderInfo and sidecar metadata without unpacking or mass-renaming.
- Online capabilities (cookies required): Online Discover page, synchronization across ten favorite folders, per-page and official Archive downloads, re-upload update detection, and GID replacement migrations.
- Maintenance & archiving: Same-GID duplicate copy cleanup, favorite folder deduplication, cross-GID deduplication, missing/corrupt page integrity inspections, and multi-disk cold storage CBZ archiving.
- Reader & extensions: Built-in RTL, dual-page, webtoon reader with slideshow playback matching animated GIF/WebP frame durations; supports OPDS, field-level encryption at rest, and Telegram Bot remote control.

Downloads are saved to `downloads/`; cold archives are saved to configured `archive_roots` directories. For details, see [Features](Features-EN).

---

## Get started

### A. Existing Ehviewer folders
1. Mount the host directory into the backend container in your compose file (e.g., `/data/Ehviewer:/Ehviewer:ro`).
2. Open **Settings → Library**, add the container path to library roots, and save.
3. Open **Library** (`#/library`) and click **Scan library**.
4. See [Compatibility](Compatibility-EN) and [Library](Library-EN#library-library).

### B. Favorite folders
1. Open **Settings → Site & proxy**, enter cookies, and click **Test login** to verify status.
2. Open **Favorites** (`#/favorites`), enable target folders, and select incremental download or watch-only mode.
3. See [Favorites](Favorites-EN#favorites-favorites) and [Downloads](Downloads-EN).

### C. Dedupe and GID replacements
1. Open **Manage → Favorite duplicates** (`#/duplicates/favorites`) or **Cross-GID duplicates** (`#/duplicates/cross-gid`) to clean up redundant items.
2. In Favorites, click **Gallery updates** (`#/updates`) to detect re-uploaded galleries and migrate status.
3. See [Manage](Manage-EN#duplicate-copies--deduplication-duplicates) and [Gallery updates](Favorites-EN#gallery-updates-updates).

### D. Cold archive
1. Mount archive storage volumes in compose, and configure `archive_roots` under **Settings → Library**.
2. Open **Manage → Cold archive** (`#/archive`) to execute archiving; afterward, clean up archived source directories via the Settings storage table.
3. See [Deployment](Deployment-EN) and [Cold archive](Manage-EN#cold-archive-archive).

### E. Series and integrity
1. Open **Series** (`#/series`) in the top navigation to view aggregated works in the same series.
2. Open **Manage → Missing pages / Integrity** (`#/integrity`) to run gallery integrity scans and repair downloads.
3. See [Series](Library-EN#series-series) and [Missing pages / Integrity](Manage-EN#missing-pages--integrity-integrity).

---

## Index

### Getting Started

- **[Usage](Usage-EN)** — Web routes, first-time setup wizard, recommended workflows, and legacy anchor migration table
- **[Features](Features-EN)** — System capabilities by module, operational prerequisites, and topology
- **[Screenshots](Screenshots-EN)** — Screenshot index of core features and primary interfaces

### Usage

- **[Library](Library-EN)** — Gallery library browsing, Discover page, local list, advanced filtering, and reading history
- **[Reading](Reading-EN)** — Gallery detail view, tag synchronization, reader modes, shortcuts, and slideshow playback
- **[Downloads](Downloads-EN)** — Download queue, status badges, retry mechanisms, and official Archive downloads
- **[Favorites](Favorites-EN)** — Favorite folder management, synchronization modes, deduplication, and update detection
- **[Manage](Manage-EN)** — Duplicate copy cleanup, cross-GID deduplication, trash bin, cold archive, and integrity logs
- **[Settings](Settings-EN)** — System settings, storage panel, Telegram Bot commands, and network operation catalog

### Operations

- **[Deployment](Deployment-EN)** — Compose configuration, storage topology, permission controls, tuning, and repair scripts
- **[Compatibility](Compatibility-EN)** — Client support matrix, directory topology, metadata specifications, and naming limits
- **[Backup](Backup-EN)** — Database backup and restore, encryption key custody, archive backup, and operational notes
- **[Encryption](Encryption-EN)** — AES-256-GCM field encryption principles, key responsibilities, and recovery after key loss
- **[FAQ](FAQ-EN)** — Common troubleshooting questions, root causes, and resolution steps

Development and API documentation live in the repository at `backend/docs/API.md` and `backend/docs/DEVELOPMENT.md`.

---

## License

[MIT License](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)
