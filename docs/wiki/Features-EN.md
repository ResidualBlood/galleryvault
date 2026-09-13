# Features

> [中文](Features) · **English**

This document systematically details GalleryVault's core architecture, feature matrix, and engineering design highlights.

---

## Architecture & Core Philosophy

GalleryVault is not a generic e-book reader, but a dedicated private archival and synchronization system tailored for digital gallery assets, high-fidelity metadata, and distributed sync workflows.

```
┌─────────────────────────────────────────────────────────────┐
│  SPA  :8000                                                  │
│  Browse · Discover · Library · Series · Tags · Downloads     │
│  Favorites · Manage(recycle/dup/integrity/archive) · Reader  │
└──────────────┬───────────────────────────────▲──────────────┘
               │ /api proxy                    │
┌──────────────▼───────────────────────────────┴──────────────┐
│  FastAPI  127.0.0.1:8001                                     │
│  Scan Ehviewer/CBZ  ·  Downloads/Archive  ·  Favorites      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
          PostgreSQL (optional field encryption)
```

---

## Detailed Feature Matrix

### 1. Local Asset Archiving & High-Fidelity Parsing
- **Zero-Friction Ehviewer Ingestion**: Directly scans standard `<gid>-<title>/` directory trees, parsing `.ehviewer` metadata files (SpiderInfo V1 & V2) to restore gid, token, category, and page indexes without file moves or extraction.
- **Multi-Format Ingestion**: Full compatibility with CBZ and CBR archives (with embedded `ComicInfo.xml`), JHenTai `metadata` JSON files, and standardized `.galleryvault.json` sidecar files in tiered cold storage.
- **7z / PDF and gid-less folders**: `.7z` scans image members only (non-images stay packed); `.pdf` extracts embedded images. Gid-less image folders still browse and rate.
- **Tiered Cold/Hot Storage**: Decouples the active download workspace (hot tier) from read-only archival pools (cold storage), allowing seamless archive migrations on demand.
- **Custom Local Taxonomy**: Organizes media collections using local star ratings, custom reading lists, and private notes completely independent of external providers.

### 2. Intelligent Lifecycle Tracking & Deduplication
- **Re-Upload Version Tracking (Updates)**: Continuously checks for re-uploaded works or upgraded listings (detecting newly assigned GIDs), allowing one-click upgrades that fetch the new version while removing obsolete local archives.
- **Cross-GID Clustering & Deduplication**: Analyzes gallery clusters across different scan roots and cloud favorite folders, grouping alternative translations, duplicate uploads, or re-compressed variants for rapid batch resolution.
- **Duplicate-Copy Cleanup**: When identical GIDs appear across multiple mount paths, automated policies (keep stored / most pages / largest / newest / manual) retain the preferred copy and purge redundant files.
- **Independent Title Rendering**: Supports switching title displays across Japanese, English, and directory naming styles without modifying file names on disk or altering download destination paths.

### 3. Deep Cloud Metadata Integration
- **Batch Metadata Caching (gdata)**: Efficiently retrieves category information, ratings, and tag sets using user credentials, backed by persistent caching to avoid redundant requests.
- **10 Independent Favorite Folders**: Configures independent sync policies ("Incremental download", "Watch only", or "Scheduled poll") for each folder, queueing new additions automatically.
- **Public & Private Domain Adaptability**: Switches cleanly between `exhentai.org`, `e-hentai.org`, and custom proxy mirrors; safely pauses tag sync for restricted listings under public domains to prevent false deletions.
- **Active Credential Probing**: Automatically validates credential status on boot and during periodic cycles, alerting users through top banners before background sync jobs stall.
- **Integrated Discover View**: Explores live cloud listings (Popular, Watched, Top lists) directly from the Web interface, enabling one-click ingestion or remote favoriting.

### 4. Resilient Concurrency Pipeline & Self-Healing
- **Dual-Mode Download Engine**:
  - **Concurrent Page Streaming**: Fine-grained concurrency limits, real-time progress monitors, and resumable retries (downloading missing pages only).
  - **Official Archive Downloads**: Utilizes official whole-gallery zip streams via GP quotas, supporting single-connection transfers with Range resume capabilities that **never re-charge GP on retry**.
- **Slow-Node Watchdog**: Monitors individual image timeouts, transfer warm-up windows, and minimum throughput thresholds, automatically dropping stalling H@H nodes.
- **Exponential Backoff Recovery**: Transient network anomalies, proxy disruptions, or server timeouts trigger automatic exponential backoff retries (30 seconds up to 6 hours, up to 10 attempts).
- **Anti-Abuse 302 Protection**: Detects temporary 302 challenge redirects, automatically suspends the download queue to safeguard credentials, and polls background probes (default 10-minute intervals) to resume when cleared.
- **Instant Ingestion**: Completed downloads are indexed into the database and their thumbnails cached immediately, bypassing full library rescans.

### 5. Immersive Reading & Open Interoperability
- **Versatile Reader**:
  - **Layout Modes**: Right-to-Left (Japanese manga), Left-to-Right, vertical continuous cascade (webtoon mode), and dual-page split viewing.
  - **Controls & Navigation**: Keyboard shortcuts, touch tap zones, `G` key jump navigation, multi-page prefetching, and auto-advance to the next gallery after the last page. In Webtoon, wheel/touch vertical scroll is used (arrow keys and left/right tap zones do not page).
- **Adaptive Slideshow**: Probes GIF/WebP `duration_ms` (sum of per-frame delays) and uses `max(user interval, duration + 150ms)`. Starting slideshow enters fullscreen; exiting fullscreen stops it.
- **Advanced Tag Search**: Powered by the EhTagTranslation multi-language database; supports tag autocomplete, AND/OR logic combinations, exclusion filters (`-tag`), and multi-language reverse-lookup (e.g. typing Chinese suggests English equivalents).
- **Standard OPDS Catalog**: Exposes a standard OPDS endpoint (`GET /api/opds`) with HTTP Basic authentication for direct access in Tachiyomi, Mihon, and Panels.
- **Recycle Bin & Audit Log**: Safely stages user-deleted or offline items in a restorable recycle bin with complete activity logs.

### 6. Security & deployment
- **AES-256-GCM Database Encryption**: Encrypts sensitive credentials, cookies, and tokens at rest when `ENCRYPTION_KEY` is configured.
- **10-Year Persistent Sessions**: Persists session cookie signing secrets in the database across container rebuilds and updates; immediate session invalidation on password updates.
- **Unprivileged Runtime (PUID / PGID)**: Configurable runtime user and group mappings prevent host permission issues on private NAS environments; strict CSRF protection with trusted proxy whitelisting (`TRUSTED_PROXIES`).
- **Turnkey Containerization**: Multi-architecture Docker Hub images (AMD64 / ARM64) with PostgreSQL 18 and built-in Alembic migrations for single-command deployments.

### 7. Telegram Bot operations
- **Auto-registered command menu**: after a bot token is configured, startup registers the Telegram `/` menu; copy follows the notification language.
- **Downloads & queue**: paste a gallery URL in chat (trailing/surrounding slashes are fine) to enqueue immediately; `/queue` uses InlineKeyboard for pause / retry / cancel; `/pause` `/resume` share the Web downloads global-pause switch.
- **Health probes**: `/status` queue overview, `/storage` disk usage, `/quota` image quota and GP, `/cookie` cookie health — aligned with the Web UI.
- **Local library**: `/search` with pagination, `/info` `/random` send details and a cover (same 5-step cover fallback as the Web UI), `/scan` triggers a library scan, `/fav_sync` `/fav_download` `/fav_check` automate favorites.
