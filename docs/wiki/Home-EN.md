# GalleryVault Documentation Hub

> [中文](Home) · **English**

Welcome to the official **GalleryVault** documentation. GalleryVault is a **private, self-hosted local gallery asset management system and cloud synchronization hub** designed to keep your media files, index databases, and collection relationships entirely on your own hardware or private NAS.

---

## What it does

- Mount Ehviewer `<gid>-title/` trees and CBZ as-is (SpiderInfo / sidecars). No unpack-and-rename step.
- With cookies: Discover, ten favorite folders, page or official Archive downloads, GID replacements.
- Manage: same-GID copies, favorite dupes, cross-GID, missing/corrupt pages, optional multi-disk cold CBZ.
- Reader: RTL / dual-page / webtoon; slideshow follows GIF/WebP frame duration. Optional OPDS, at-rest field encryption, and a Telegram bot (paste URLs to enqueue, queue actions, scan / quota / local search with covers).

Downloads go to `downloads/`. Cold archive uses `archive_roots` you configure (Archive is not mounted by default). See [Features](Features-EN).

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

## Documentation Navigation

### 📖 User Guides
- **[Features](Features-EN)** — Comprehensive feature matrix, design philosophy, and system architecture
- **[Usage Guide](Usage-EN)** — Searching, reader navigation, download queue, favorites monitoring, deduplication, and recycle bin
- **[Screenshots](Screenshots-EN)** — Interface previews across major modules in English and Chinese
- **[FAQ](FAQ-EN)** — Troubleshooting guides, network tuning, cookie maintenance, and common questions

### ⚙️ Operations & Deployment
- **[Compatibility](Compatibility-EN)** — Directory hierarchies, SpiderInfo V1/V2 formats, Sidecar JSON schemas, and client matrix
- **[Deployment](Deployment-EN)** — Docker Compose quickstart, volume mounts, Nginx/Caddy reverse proxies, and permission setup
- **[Backup & Restore](Backup-EN)** — Database snapshots, cold archive exports, and disaster recovery procedures
- **[Encryption at Rest](Encryption-EN)** — AES-256-GCM database encryption mechanism, key management, and emergency recovery

API and development notes live in the repo: `backend/docs/API.md` and `backend/docs/DEVELOPMENT.md` (not on the GitHub Wiki).

---

## Quick Launch

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- Web Access: `http://<host-ip>:8000`
- Default Password: `p1a2s3s4` (please update in Settings immediately after login)
- Persistent Data: Stored locally in `./library`, `./downloads`, `./db-data`, and `./cache`.

---

## License

Released under the open-source [MIT License](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE).
