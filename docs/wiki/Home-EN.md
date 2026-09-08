# GalleryVault Documentation Hub

> [中文](Home) · **English**

Welcome to the official **GalleryVault** documentation. GalleryVault is a **private, self-hosted local gallery asset management system and cloud synchronization hub** designed to keep your media files, index databases, and collection relationships entirely on your own hardware or private NAS.

---

## Core Strengths & Key Advantages

- ⚡ **Native Ehviewer Compatibility & Zero Migration Overhead**: Directly mount Ehviewer multi-tier export directories without unpacking or renaming files; seamlessly parses SpiderInfo (V1/V2) and Sidecar metadata files on ingestion.
- 🔄 **Deep Cloud Metadata Integration**: Automatically syncs tags, artists, groups, and categories; provides incremental favorite folder monitoring, download scheduling, and deletion safeguards.
- 🎯 **Lifecycle Tracking & Intelligent Deduplication**: Exclusive tracking for re-uploaded works (detecting newly assigned GIDs) with one-click in-place upgrades; built-in cross-GID clustering and duplicate audits eliminate redundant translations and copycat uploads.
- 🛡️ **Fine-Grained Concurrency & Self-Healing Watchdogs**: Concurrent streaming and official whole-gallery archive (zip) downloads with Range resume capabilities (never re-charging GP); automated watchdogs for slow H@H nodes and 302 anti-abuse challenge probe recovery.
- 🔒 **Enterprise-Grade Privacy & Encryption at Rest**: AES-256-GCM field-level database encryption (`ENCRYPTION_KEY`) ensures sensitive tokens and credentials are encrypted at rest; 10-year persistent signed sessions survive container reboots.
- 📖 **Immersive Reading & Open Interoperability**: Multiple reading modes (Japanese RTL, LTR, Webtoon cascade, dual-page) and animation-aware slideshows for GIF/WebP; built-in standard OPDS catalog for third-party mobile readers.

---

## Typical User Journeys

Select the journey that best fits your workflow:

### Journey A: Ingest Existing Ehviewer Export Directories
1. In `docker-compose.yml`, mount your existing Ehviewer download directory into the backend container (e.g., `/data/Ehviewer:/Ehviewer:ro`).
2. Add the container path in *Settings → Library roots* and save.
3. Click **Scan library**. GalleryVault automatically reads `.ehviewer` or sidecar metadata to build a high-performance PostgreSQL index.
4. See **[Compatibility and Formats](Compatibility-EN)** and **[Usage Guide: Library Management](Usage-EN#library-library)**.

### Journey B: Cloud Favorites Privatization & Incremental Sync
1. Enter your account credentials under *Settings → ExHentai* and verify connection status with *Test login*.
2. Navigate to *Favorites*, enabling "Incremental download" or "Watch only" mode on target folders.
3. GalleryVault periodically monitors changes in the background, preheats cover caches, and enqueues downloads.
4. See **[Usage Guide: Favorites & Monitoring](Usage-EN#favorites-favorites)** and **[Download Management](Downloads-EN)**.

### Journey C: Multi-Version Deduplication & Lifecycle Maintenance
1. Open the *Favorites Dedupe* view to automatically detect redundant versions, duplicate languages, or re-compressed uploads; remove unnecessary favorites or delete local files in one click.
2. Open the *Gallery Updates* view to audit items re-uploaded to the cloud with newly assigned GIDs; download updated versions and clean up obsolete local archives in a single step.
3. See **[Usage Guide: Deduplication](Usage-EN#duplicate-copies-duplicate-copies)** and **[Gallery Updates](Favorites-EN#gallery-updates-updates)**.

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

### 🛠️ API & Development
- **[API Reference](API)** — Complete REST API specifications and OpenAPI definitions
- **[Development Guide](Development)** — Local setup, Dev Compose hot reloading, and automated test suites

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
