# GalleryVault Documentation Hub

> [中文](Home) · **English**

Welcome to the official **GalleryVault** documentation. GalleryVault is a **private, self-hosted local gallery asset management system and cloud synchronization hub** designed to keep your media files, index databases, and collection relationships entirely on your own hardware or private NAS.

---

## Core Strengths & Key Advantages

- ⚡ **Native Ehviewer Compatibility & Zero Migration Overhead**: Directly mount Ehviewer multi-tier export directories without unpacking or renaming files; seamlessly parses SpiderInfo (V1/V2) and Sidecar metadata files on ingestion.
- 🧊 **Cold & Hot Tiered Storage Architecture**: High-speed hot download buffer coupled with automated multi-root cold storage archiving (`archive_roots`) with space-balanced CBZ generation; offers safe reverse purge of uncompressed source directories (`purge-archived-sources`) protected by active download locks.
- 📚 **Series Management & Automated Clustering**: Automatically strips convention prefixes (C100, COMIC1, etc.) and series markers to cluster related works; supports manual curation, batch membership editing, and automatic library-wide re-clustering.
- 🩺 **Gallery Integrity Inspection & One-Click Repair**: Deep disk-integrity scanning with magic header validation (defending against GIF/WebP truncation and corrupt payloads), providing one-click diff re-downloading for missing/corrupted pages with background breakpoint self-healing.
- 🎯 **Lifecycle Tracking & Intelligent Deduplication**: Exclusive tracking for re-uploaded works (detecting newly assigned GIDs) with one-click in-place upgrades; built-in cross-GID clustering and duplicate audits eliminate redundant translations and copycat uploads.
- 🔄 **Deep Cloud Metadata Integration**: Automatically syncs tags, artists, groups, and categories; provides incremental favorite folder monitoring, download scheduling, instant local category self-healing (`repair-categories`), and deletion safeguards.
- 🛡️ **Fine-Grained Concurrency & Self-Healing Watchdogs**: Concurrent streaming and official whole-gallery archive (zip) downloads with Range resume capabilities (never re-charging GP); automated watchdogs for slow H@H nodes and 302 anti-abuse challenge probe recovery.
- 🔒 **Enterprise-Grade Privacy & Encryption at Rest**: AES-256-GCM field-level database encryption (`ENCRYPTION_KEY`) ensures sensitive tokens and credentials are encrypted at rest; 10-year persistent signed sessions survive container reboots.
- 📖 **Immersive Reading & Open Interoperability**: Multiple reading modes (Japanese RTL, LTR, Webtoon cascade, dual-page) and animation-aware slideshows for GIF/WebP; built-in standard OPDS catalog for third-party mobile readers.

---

## Cold & Hot Tiered Storage Architecture at a Glance

GalleryVault employs a tiered storage architecture balancing rapid ingestion throughput with massive, cost-efficient long-term preservation:

| Tier | Path / Mount Point | Role & Characteristics | I/O Behavior |
| :--- | :--- | :--- | :--- |
| **Hot Storage** | `downloads/` | High-speed working buffer for active downloads and uncompressed pages | Frequent random writes, stream extraction, immediate reading |
| **Cold Storage** | `archive/` (multiple `archive_roots`) | Long-term archival volumes holding standardized single-volume CBZ files (`gid-gallery.title.cbz`) with `.galleryvault.json` sidecars | Primarily read-only, balanced write distribution by free disk space, scalable across disks/NAS |
| **Lifecycle Purge** | `purge-archived-sources` | Safely purges uncompressed source folders in hot storage once CBZ archiving succeeds | Active task locks, multi-source GID verification, real-time physical space reclamation |

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

### Journey C: Multi-Version Deduplication & Cross-GID Governance
1. Open the *Favorites Dedupe* view to automatically detect redundant versions, duplicate languages, or re-compressed uploads; remove unnecessary favorites or delete local files in one click.
2. Switch to *Cross-GID Duplicates* to cluster separate GIDs representing the same work (translations, revisions), reviewing cloud status and keeping preferred releases.
3. Open the *Gallery Updates* view to audit items re-uploaded to the cloud with newly assigned GIDs; download updated versions and clean up obsolete local archives in a single step.
4. See **[Usage Guide: Deduplication](Usage-EN#duplicate-copies-duplicate-copies)** and **[Gallery Updates](Favorites-EN#gallery-updates-updates)**.

### Journey D: Tiered Archiving & Safe Source Purging
1. Under *Settings → Library*, configure one or multiple cold storage target directories (`archive_roots`).
2. Enable automatic archiving or trigger it manually; works will be compressed into standardized CBZ archives and distributed across balanced volumes.
3. Once archived, click *Purge archived sources* in the Storage section to cleanly remove the hot raw directories without risking active downloads.
4. See **[Deployment: Tiered Storage](Deployment-EN#cold-and-hot-tiered-storage-architecture)** and **[Operations](Manage-EN)**.

### Journey E: Series Management & Integrity Inspection
1. Open the *Series* view to explore automatically clustered doujinshi or serialized manga, or manually create new series to aggregate local and cloud works.
2. Open the *Integrity* view to run full-library scans checking image magic headers and metadata consistency; batch re-download any missing or corrupted pages in one click.
3. See **[Usage Guide: Series](Usage-EN#series-series)** and **[Integrity Inspection](Manage-EN#integrity-inspection-integrity)**.

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
