# Features

> [中文](Features) · **English**

Key capabilities, prerequisites, and core constraints by module. The system consists of a SPA frontend, FastAPI backend, and PostgreSQL database; see [Deployment Guide](Deployment-EN) for component topology and reverse proxy setups.

---

## 1. Scanning and formats

- **Ehviewer directory scanning**: Scans `<gid>-<title>/` directory structures and parses `.ehviewer` files (SpiderInfo V2 and unversioned V1) to extract GID, token, and per-page pTokens. Titles, categories, and tags are supplemented via directory names, `.galleryvault.json`, or remote gdata without unpacking or renaming.
- **Multiple archive formats**: Supports CBZ and CBR archives (including embedded `ComicInfo.xml`), JHenTai page-download directory `metadata` JSON, and cold archive `.galleryvault.json` metadata.
- **7z / PDF / GID-less folders**: `.7z` archives index image members only with in-memory page decompression; `.pdf` extracts embedded image streams; both enforce a 128MB per-page decompression/extraction cap. Image directories without GIDs support local browsing, custom tags, and star ratings.
- **Tiered hot/cold storage**: Newly downloaded galleries are stored in the hot data directory; archive roots support multi-disk mounting and capacity balancing. Archiving must be initiated manually and never runs silently.
- **Local library organization**: Provides custom reading lists, star ratings, reading progress tracking, and local notes fully offline.
- **Detailed references**: See [Compatibility & Format Specifications](Compatibility-EN) for support matrices and naming rules; see [Library & Browsing](Library-EN) for browsing and local management.

## 2. Versions and dedupe

- **Cloud re-upload detection (Updates)**: Detects new GIDs assigned when galleries are re-uploaded to the cloud. Supports one-click download of the new version with safe deletion of the old local copy upon confirmed completion.
- **Cross-GID deduplication clustering**: Clusters and identifies alternate translations, quality variants, and duplicate entries across favorite folders based on gallery attributes, supporting bulk review and cleanup.
- **Same-GID duplicate cleanup**: When identical galleries reside across multiple mount points or paths, redundant copies can be cleaned based on retention policies (stored item, most pages, largest size, newest import, or manual selection).
- **Multi-tier title display**: Switches between Japanese original title, English title, and local directory name, decoupled from underlying filesystem folder naming.
- **Detailed references**: See [Favorites Management](Favorites-EN) for version updates and favorite deduplication; see [Library Management & Maintenance](Manage-EN) for duplicate cleanup and safe deletion.

## 3. Site and favorites

- **Metadata synchronization (gdata)**: Queries cloud categories, tags, ratings, and uploader metadata using configured site cookies, caching results locally.
- **Ten favorite folders**: Independently manages 10 site favorite folders. Each folder can be assigned an "Incremental download", "Watch only", or "Force download" mode with its own polling schedule, enqueuing galleries accordingly.
- **Allowed domain constraints**: Restricts outbound API and gallery requests to `exhentai.org`, `e-hentai.org`, and their subdomains; all other hostnames return HTTP 422. Tag sync for ExHentai-exclusive galleries is paused when running in public site mode.
- **Cookie health monitoring**: Checks cookie connectivity and permissions at startup and on background intervals, displaying warning alerts in the top navigation bar when cookies expire or fail.
- **Discovery views**: Integrates Popular, Watched, and Toplist discovery views, supporting direct download enqueuing and adding to favorites.
- **Detailed references**: See [Favorites Management](Favorites-EN) for favorite modes and synchronization rules; see [Library & Browsing](Library-EN) for discovery views.

## 4. Downloads

- **Concurrent page downloads**: Configurable gallery-level and page-level download concurrency, displaying real-time task progress and status badges; retries fetch missing pages only.
- **Official archive channel**: Downloads official zip archives consuming account GP; uses single-connection streaming with HTTP Range resume; retries reuse existing task URLs without re-deducting GP (except when re-requesting corrupted archives or when the quality tier changes between attempts).
- **H@H node selection & eviction**: Features per-image timeout watchdogs, warmup windows, and minimum transfer rate thresholds, automatically evicting unresponsive or slow H@H nodes.
- **Exponential backoff retries**: Temporarily failed tasks retry with stepped backoff from 30 seconds up to 6 hours, capped at 10 attempts per task; after the cap the task stays failed and is not resurrected automatically — recover it with Retry or Retry all tasks.
- **Quota challenge protection**: Automatically pauses the download queue upon encountering HTTP 302 challenges; background probes run every 10 minutes and automatically resume downloads once restrictions clear. HTTP 429/509 responses are retried as quota/rate-limit errors with backoff and carry the server's `Retry-After` (60 seconds when absent).
- **Direct download ingest**: Automatically indexes completed downloads and generates cover caches without triggering a full library rescan.
- **Detailed references**: See [Download Management & Archiving](Downloads-EN) for queue operations, status badges, and archive boundaries.

## 5. Reader and search

- **Multiple reading layouts**: Supports Right-to-Left (RTL), Left-to-Right (LTR), Vertical Webtoon, and Dual-Page layouts.
- **Navigation & shortcuts**: Supports keyboard shortcuts, screen tap zones, `G` key page jump, and background prefetching. Webtoon mode uses mouse wheel or touch scrolling, disabling horizontal paging keys and tap zones.
- **Animated slideshow**: Parses frame durations for GIF and WebP animations (binary scan capped at 120 seconds per image), automatically adjusting slideshow intervals to image duration; enters fullscreen on start and exits slideshow when fullscreen is closed.
- **Advanced tag search**: Integrates the EhTagTranslation database; supports autocomplete suggestions, AND/OR logic, `-tag` exclusion syntax, and reverse search matching English tags from non-English queries.
- **OPDS catalog feed**: Provides a `GET /api/opds` catalog endpoint and `GET/HEAD /api/galleries/{id}/export.cbz` acquisition endpoint, both accepting HTTP Basic authentication (unauthenticated requests return 401 with `WWW-Authenticate: Basic`); compatible with reader clients such as Tachiyomi, Mihon, and Panels.
- **Safe deletion & recycle bin**: Deleted or missing galleries are moved to the recycle bin directory, supporting on-demand restoration or permanent removal.
- **Detailed references**: See [Gallery Details & Reading](Reading-EN) for reader settings and shortcuts; see [Library & Browsing](Library-EN) for search syntax; see [Library Management & Maintenance](Manage-EN) for recycle bin operations.

## 6. Security and deployment

- **Data encryption at rest**: With `ENCRYPTION_KEY` configured, cookies, access tokens, and sensitive credentials are encrypted using AES-256-GCM.
- **Persistent security sessions**: Session signing secrets are persisted in PostgreSQL, preserving logins across container restarts; changing passwords immediately invalidates all active sessions.
- **Permissions & proxy hardening**: Supports unprivileged execution with configurable `PUID` and `PGID`; enforces CSRF protection; supports trusted reverse proxy CIDRs via `TRUSTED_PROXIES`; limits archive page decompression to 128MB.
- **Authentication & settings hardening**: Failed logins apply account-level exponential backoff (from 5 failures, up to 15 minutes) and return `429` + `Retry-After`; changing security-sensitive settings (require login, trusted proxies, download root, library roots) requires the current administrator password or an explicit confirmation (the API returns `428`); API responses carry baseline security headers including `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and CSP `frame-ancestors 'none'`.
- **Containerized deployment**: Provides AMD64 and ARM64 dual-architecture Docker images with integrated PostgreSQL and automated Alembic database migrations at startup.
- **Detailed references**: See [Deployment Guide](Deployment-EN) for deployment, storage topology, and reverse proxy examples; see [Encryption at Rest](Encryption-EN) for key security and disaster recovery.

## 7. Telegram Bot

- **System notifications & integration**: Automatically registers command menus with Telegram upon bot token configuration; notification language matches the system interface language.
- **Quick download & task management**: Sending a gallery URL directly enqueues the task; the `/queue` command offers an interactive keyboard to manage task states; `/pause` and `/resume` integrate directly with the global web download switch.
- **Remote status monitoring**: Queries queue progress, remaining disk space, GP quota, and cookie health via `/status`, `/storage`, `/quota`, and `/cookie`.
- **Search & remote library maintenance**: Supports `/search` with pagination, `/info` and `/random` with gallery details and covers (reusing the 5-step cover fallback logic), `/scan` for triggering library scans, and `/fav_sync`, `/fav_download`, and `/fav_check` for managing favorites.
- **Detailed references**: See [Settings](Settings-EN#telegram-bot-control-commands) for bot configuration options, command tables, and permission constraints.
