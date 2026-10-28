# Settings

> [中文](Settings) · English | Part of the [Usage Guide](Usage-EN) series

System settings, OPDS, Telegram bot commands, and which operations need the network.

## Settings (`#/settings`)

### Account & Interface

| Setting | Field / Values | Description & Defaults |
| :--- | :--- | :--- |
| Change Password | - | Changing the password revokes all active logged-in sessions. |
| Security Confirmation | Current password / explicit confirmation | Changing "Require Login", "Trusted Proxies", "Download Root", or "Library Roots" requires the current administrator password; when no password is configured, an explicit confirmation is required once. Saves without confirmation are rejected (API returns `428`). |
| Login Protection | `429` / `Retry-After` | After 5 consecutive failed logins for the single administrator account, exponential backoff applies (from 5 seconds up to 15 minutes); logins during backoff return `429` with `Retry-After`. A separate per-IP limit allows 10 attempts per minute. Counters are process-local, so multiple workers count independently and a restart clears them. |
| Require Login | Toggle | Toggles authentication enforcement. |
| Session Expiration | `galleryvault_session`<br>`galleryvault_csrf` | Web session and CSRF cookies default to a 10-year expiration (`315360000` seconds); changing the password or resetting secrets immediately invalidates all active sessions. |
| Title Display | `japanese`<br>`english`<br>`directory` | Title display policy across library, browse, details, favorites, favorites duplicate checks, and duplicate copies pages. Default is `japanese` (Japanese preferred, falls back to English). |
| Theme | `gv_theme` | Top-bar ◐ icon toggles light or dark theme, persisted to local storage; defaults to dark (`dark`). |

### Site & Proxy

| Setting | Parameter / Field | Description & Defaults |
| :--- | :--- | :--- |
| ExHentai Base URL | `exhentai_base_url` | Only `exhentai.org` / `e-hentai.org` or their subdomains are supported. |
| Cookie Authentication | `ipb_member_id`<br>`ipb_pass_hash`<br>`igneous` | Verified via **Test login**; cookie values are never echoed back. For setup steps, see [Usage Guide: Cookie Setup](Usage-EN#configuring-exhentai-cookies). |
| Health Probe | Periodic Probe | Runs at startup and every 30 minutes thereafter; expired cookies, missing ExHentai access, or IP bans show a red banner, while network probe failures show an orange banner, both linking to Settings. |
| Proxy | HTTP / SOCKS5 | Configure server address and port (choose one). |
| Security Headers | All responses | The backend adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, and a `Content-Security-Policy` (including `frame-ancestors 'none'` and `worker-src 'self'`) to API and page responses. |

### Library & Storage

| Setting | Parameter / Value | Description & Constraints |
| :--- | :--- | :--- |
| Library Roots | Path list | One filesystem path per line, defaulting to `/library` and `/downloads`. Scans cover all paths; deleting a gallery deletes its files when mounted writable, or fails with errors on toast and Logs if read-only. Trailing slashes do not affect deduplication; a scan root itself is never a valid delete/purge target. |
| Cold Archive | `archive_roots` | Multi-line filesystem paths (e.g. `/archive`). Blank disables cold archiving; legacy `cold_storage_root` upgrades to a one-item list. By default, auto-archive and deleting source files are disabled. For mounting and capacity balancing, see [Deployment Guide → Tiered Storage](Deployment-EN#2-tiered-storage--multi-disk-mounting). |
| Cold Archive Spec | Specifications | Single volume is capped at **500 pages and 2GiB** (AND); exceeding either creates a cold directory instead of a single-volume CBZ. CBZ path is `{cold}/cbz/{hh}/{ii}/{gid}-{DB English title}.cbz` with internal `.galleryvault.json`. Managed at **Manage → Cold archive** (`#/archive`). |
| Purge Residue | Storage action | The Settings storage table provides "Purge archived source directory files", automatically skipping tasks in pending or downloading states. |
| Disk Usage | Metrics | Displays library, cold, downloads, and cache paths, item counts, used space, and disk free; lists the 10 largest galleries. Opening Settings does not walk the entire disk. Measurements do not cross mount points and hard-linked files are counted once. |
| Archives & Documents | `.7z` / `.pdf` | Recognizes `.7z` (images only, in-memory extract per page, 128MB cap) and `.pdf` (extracts embedded images, skipping single images over 128MB or galleries without extractable images). |

### Downloads Common & Advanced

**Common Download Settings**:

| Setting | Parameter / Value | Description & Defaults |
| :--- | :--- | :--- |
| Download Root | `download_root` | Target hot directory where new download tasks write files. |
| Concurrent Galleries | Numeric | Maximum number of gallery download tasks running concurrently; changes take effect immediately without a restart. |
| Archive Transfer Concurrency | Fixed cap | Official archive zip streaming is capped at 2 concurrent transfers, independent of "Concurrent Galleries"; an interrupted task resumes with its existing URL. |
| Pages in Parallel per Gallery | Numeric | Concurrent image download limit per gallery, default `4`. H@H nodes cap concurrent connections per source IP, so high values on unstable connections cause connection errors. |
| Image Quality | Normal / Original | Default image download quality. |
| Archive Quality | Quality tier | Default tier requested for official archive download channels. |
| Fall Back to Page-by-Page | Toggle | Default on. When official archive channels are unavailable, automatically falls back to page-by-page downloads without deducting GP. |

**Download Title & Advanced Options**:

- **Download Title**: Controls folder naming only for newly created folders in the hot download directory (`download_root`) — `japanese` (default, `gid-<Japanese title>`, falling back to English when absent) or `english` (`gid-<English title>`). Independent of the interface "Title Display" setting (cold storage CBZ files always use database English titles); existing download folders are reused without renaming or re-downloading.
- **Advanced Options (Collapsed)**:
  - H@H toggle and archive default quality.
  - `favorites_archive_max_pages`: Favorite archive page threshold (`0` = all).
  - Archive large favorites on scheduled scans.
  - Slow H@H watchdogs: image max time, warmup window, and minimum KB/s rate (defaults: 30-second warmup, below 10KB/s is treated as throttled); the same watchdog applies to archive zip transfers.
  - Global EH request concurrency: environment variable `EXHENTAI_MAX_CONCURRENCY` (1–32, default 6).
  - 302 challenge probe interval: environment variable `GV_CHALLENGE_PROBE_INTERVAL` (default 600 seconds).
  - Per-task 302 challenge pause limit: environment variable `GV_MAX_CHALLENGE_PAUSES` (default 5; once reached, the task is marked failed with its remaining retry budget preserved).

### Tags & Thumbnails

| Setting | Field / Action | Description & Behavior |
| :--- | :--- | :--- |
| Tag Sync | Toggle / Interval / Concurrency | Automatically syncs tag metadata after scans or startup; includes "Sync tags now" action. |
| Translation Auto-Update | Interval (minutes) | `0` disables; provides "Update now" action on this page. |
| Local Category Repair | Offline action | Reclassifies galleries mislabeled as Misc/Other using local `.galleryvault.json` tags without internet access. |
| Thumbnail Generation | Toggle / Action | Auto-generation toggle and "Generate now" action with real-time status; periodically generates missing thumbnails for new galleries and sweeps orphaned thumbnail cache entries no longer in the database. Worker count is controlled by environment variable `THUMBNAIL_WORKERS` (1–16, default 4). |

### OPDS & PWA

| Feature | Protocol / Path | Authentication & Behavior |
| :--- | :--- | :--- |
| OPDS Catalog | `GET /api/opds` | Returns up to 50 most recently ingested galleries (Atom XML format), with acquisition links to `GET /api/galleries/{id}/export.cbz`. |
| OPDS Authentication | HTTP Basic | Supports HTTP Basic authentication with fixed username `galleryvault` (not an EH account) and web login password; session cookies also supported. Missing or invalid credentials return `401 Unauthorized` with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`. |
| CBZ Export | Export API | `GET/HEAD /api/galleries/{id}/export.cbz` accepts HTTP Basic authentication (username `galleryvault`, administrator password) or a session cookie, just like the OPDS catalog; regular `/api/*` requests still require cookie-based sessions. |
| PWA Offline Support | Service Worker | Supports adding to home screen. Page documents and the HTML/CSS/JS shell use a network-first strategy (cached on success, falling back to cache offline); explicitly does not cache gallery images or `/api/` endpoints. |

### Telegram Bot Configuration & Commands

**Bot Configuration**:

- **Basic Configuration**: Configure bot token, chat ID, and allowed user IDs; provides "Send test message" to verify connectivity. Startup automatically registers client command menus with Telegram once a token is set.
- **Notification Options**: Notification levels support "Summary / Immediate / Failures only / Off"; notification language supports "中文 / English". Download, scan, favorites check, 302 challenge alerts (🚨 triggered / ✅ resolved), and bot replies use this language. Messages use Telegram HTML format (bold titles, monospace GID); gallery titles remain untranslated.

**Control Commands** (Allowed user IDs only; type `/` in chat to view menu):

| Category | Commands | Description |
| :--- | :--- | :--- |
| System & Ops | `/status`<br>`/ping`<br>`/cookie`<br>`/quota`<br>`/storage`<br>`/scan`<br>`/help` | View runtime status and queue overview; test latency; check cookie health; inspect image quota and GP (shows `暂无数据` in Chinese and "Quota unavailable" in English when no data is returned); view disk usage; trigger library scan; view command help. |
| Queue & Download | `/queue`<br>`/pause`<br>`/resume`<br>`/retry <id/all>`<br>`/cancel <id/gid>`<br>`/clear`<br>`/stats` | View queue and actions; global pause and resume; retry failed tasks; cancel task; clear completed history; view library count and queue snapshot. |
| Background Tasks | `/tasks`<br>`/kill <name>` | View running long-running jobs; terminate specified task. |
| Library | `/search <query>`<br>`/info <gid>`<br>`/random`<br>`/redownload <gid>` | Paginated local search; view gallery details and cover; pick random gallery; re-download specified gallery. |
| Favorites | `/fav_sync`<br>`/fav_download [0-9]`<br>`/fav_check` | Synchronize favorite categories; download missing items in designated favorite; full favorites update check. |

**Global Pause & URL Enqueueing**:

- **Global Pause Semantics**: `/pause` is a global pause persisted in `app_config.user_settings` that survives service restarts. When activated, it stops claiming new galleries and halts claiming new page images (the current in-flight page completes); queued tasks remain intact and resume when unpaused. It also pauses scheduled auto-scans and web-triggered manual scans (which return `paused`). The web downloads page toggle and bot `/pause` / `/resume` share the same switch (`GET/POST /api/pause`); top yellow pause banners and red cookie banners can stack.
- **Pasting Gallery URLs**: Pasting a gallery URL in chat (e.g. `https://exhentai.org/g/2325283/d3722b6aa8/`) automatically extracts GID and token and enqueues the download immediately if not paused. The bot replies with confirmation and gallery title (noting GID replacement if a newer version is detected; reports failure if 404 or deleted). URLs pasted during global pause are ignored and not enqueued. Non-URL text receives `/help`.

## What Needs the Network

| Network Target | Operation | Conditions & Behavior |
| :--- | :--- | :--- |
| **ExHentai / E-Hentai Origin** | Discover & Search | Accesses standard search, Popular, Watched, and Toplist; includes short-term backend caching (60s / 120s). |
| | Standard Page Download | Concurrency capped, original and normal requests controlled separately, fetched via H@H nodes. |
| | Archive Download | Deducts GP or quota to pull pre-packed files directly from origin. |
| | Tag & Metadata Sync | Batch calls gdata API to retrieve metadata, online categories, and quality detection info. |
| | Favorites Two-Way Management | Periodically synchronizes cloud categories, counts, and lists; submits additions, removals, category moves, or note edits. |
| | Cookie Keepalive & Quota | Startup and 30-minute periodic health checks; a probe is considered healthy only when the member page markers are present — unknown or blank HTTP 200 pages count as failure and are retried without clearing the configured cookies; automatic recovery probe after challenge/509 blocks; inspects GP and image quota. |
| | New Version Downloads | Pulls gallery data for new GIDs when one-click update initiates a new download task. |
| **GitHub API (`api.github.com`)** | EhTag Translation Database | Checks and downloads EhTag translation updates. |
| **Telegram Bot API (`api.telegram.org`)** | Notifications & Interaction | Push notifications and bot long-polling interaction (requires configured Bot Token). |
| **Pure Local Offline (No Network)** | Gallery Details & Reading | Details page reads local database; reader loads only local files without contacting origin. |
| | Library Maintenance & Cold Archive | Scans local disks, CBZ cold packaging and source residue purge, OPDS feed and CBZ export, recycle bin operations. |
| | Favorites Update Screening | Text matching and normalization against local records and titles, with zero external network traffic. |
| | Local Category Repair | Reclassifies gallery categories using local `.galleryvault.json` tags without accessing the internet. |
| **Local-First Cache Exceptions** | Details & Enqueue Preparation | Details prioritize local database; download preparation reuses local metadata and queries gdata only when missing. |
| | Cover & Quota Caching | Remote covers check local cache first before requesting origin; GP and quota reuse valid cached values. |
| | PWA Asset Caching | Service worker caches page documents and the static HTML/CSS/JS shell with a network-first strategy; explicitly does not cache gallery images or `/api/` endpoint responses. |
