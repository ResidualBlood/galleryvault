# Settings

> [中文](Settings) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers GalleryVault's system settings, client and OPDS integration, Telegram bot commands, and network access behavior across features.

## Settings (`#/settings`)

- **Account**: change password (this **revokes every logged-in session**) and toggle *Require login*. Web session cookies (`galleryvault_session`) and CSRF cookies (`galleryvault_csrf`) default to a 10-year expiration (`315360000` seconds) for persistent login; changing the password or resetting the secret immediately invalidates all active sessions.
- **Interface**:
  - **Title display**: `japanese` (default, Japanese title preferred) / `english` / `directory` (folder name). The library, browse, gallery detail, favorites (including cloud-only items), favorites-duplicates and duplicate-copies pages all show titles according to this setting.
- **Site & Proxy**:
   - **ExHentai**: base URL (only `exhentai.org` / `e-hentai.org` or a subdomain) and `ipb_member_id` / `ipb_pass_hash` / `igneous` cookies, with a **Test login** button; cookies are never echoed back. A health probe runs at startup and every 30 minutes; expired cookies, no ExHentai access, or an IP ban show red top banners; network/site probe failures show orange. All link to Settings (also refreshed once right after login). For setup instructions, see [Usage Guide: Cookie Setup](Usage-EN#configuring-exhentai-cookies).
  - **Proxy**: HTTP or SOCKS5 (choose one).
- **Library**:
   - **Library roots**: one filesystem path per line. Defaults include `/library` and `/downloads` (new downloads still go only to `download_root`, but scans include downloads). Deleting a gallery removes its files under these roots when the mount is writable; on a read-only mount the deletion fails and is reported in the toast and on the Logs page.
- **Archive / Cold storage**: same Library fieldset as library roots. Multi-line `archive_roots` (e.g. `/archive`, `/archive2`); blank = off. Legacy `cold_storage_root` is upgraded to a one-item list. Writes pick the root with free space ≥ estimate × 1.2 and the most free space; scans include every archive root. Auto-archive and delete-source default off. CBZ path is `{cold}/cbz/{hh}/{ii}/{gid}-{DB English title}.cbz`, ignoring `download_title`; `.galleryvault.json` is inside the zip. A single volume is capped at **500 pages and 2GiB** (AND); larger galleries become a cold directory, not multi-volume CBZ. Packing and purge live on **Manage → Cold archive** (`#/archive`); the Settings storage table has the same purge button and skips pending/downloading tasks.
- **Disk usage**: four rows — **library / cold / downloads / cache** (path, item counts, used, disk free). Library/cold show gallery and image counts; cache shows an approximate thumbnail count. Opening Settings does not walk the whole disk. The 10 largest galleries are listed below.
- **Downloads (Common)**: root directory, concurrent galleries, **pages in parallel per gallery** (default 4 — H@H nodes cap concurrent connections per source IP, so values much above 4-6 trip the cap and cause connection errors on lossy lines; keep it low for stability, raise it only on a clean line), image quality (normal/original), **archive quality** (default tier for archive downloads), **fall back to page-by-page if archive is unavailable** (on by default — a gallery the archive channel cannot serve downloads page-by-page, no GP cost); **Download title**: controls folder naming only for newly created folders in the **hot download directory** (`download_root`) — `japanese` (default, `gid-<Japanese title>`, falling back to English when no Japanese title exists) or `english` (`gid-<English title>`). Independent of the display *Title display* setting (cold storage CBZ files always use the English title regardless of this setting); existing download folders are reused as-is, switching never renames or re-downloads them.
- **Downloads Advanced (Collapsed)**: H@H toggle, archive quality, `favorites_archive_max_pages` (0 = all), archive large favorites on scheduled scan, fall back to page-by-page if archive is unavailable. Slow-H@H watchdogs: image max time, warmup window, min KB/s. 302 probe interval: `GV_CHALLENGE_PROBE_INTERVAL` (default 600s).
- **Tags**:
  - **Tag sync**: automatic sync after scans/startup, interval and concurrency, **Sync tags now**.
  - **Translation auto-update**: interval (minutes, 0 = off) and **Update now** (this page, not Logs).
  - **Local category repair**: no network; rewrites Misc/Other from local metadata / `.galleryvault.json`.
- **Thumbnails**: auto-generation toggle, **Generate now**, and the **live thumbnail status**. The background engine includes automated maintenance tasks: **orphan thumbnail cleanup** (periodically sweeps the cache directory to remove orphaned files whose galleries no longer exist in the database, reclaiming storage) and a **periodic seeding mechanism** (regularly checks and seeds missing cover and page thumbnail generation jobs for newly ingested or incomplete galleries), ensuring cache completeness without accumulating stale files.
- **Telegram (Collapsed)**: bot token, chat ID, allowed user IDs, **notification level** (summary / immediate / failures-only / off) and **notification language** (中文 / English) — download, scan, favorites-check, 302 challenge alerts (🚨 trigger/✅ clearance), and bot-reply notifications all use the selected language, formatted as Telegram HTML (bold titles, mono gids); gallery titles are never translated. A **Send test message** button verifies the bot can reach the chat. After a token is configured, startup auto-registers the Telegram command menu.
- **PWA**: add to home screen. The service worker caches only the html/css/js shell (js/css **network-first**, then update the cache; offline falls back to cache), **not gallery images or `/api/`**.
- **Light theme**: ◐ in the top bar; `localStorage gv_theme=dark|light`, default dark.
- **7z / PDF scan**: library scan accepts `.7z` (py7zr, images only) and `.pdf` (embedded images; skip with a warning if none).
- **OPDS & CBZ export**: `GET /api/opds` (atom+xml) lists the **50 most recently ingested** galleries with acquisition links to `GET /api/galleries/{id}/export.cbz`. The OPDS endpoint supports HTTP Basic authentication (fixed username `galleryvault`, not an EH account; password is the web login password) for third-party reader clients; session cookie authentication remains fully supported. Missing or invalid credentials return `401 Unauthorized` with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`. CBZ export and all other `/api/*` routes require standard session cookies.
- **Telegram bot control commands** (allowed user IDs only; type `/` in chat to see the menu):

  | Group | Commands |
  | :--- | :--- |
   | System | `/status` runtime + queue overview; `/ping` latency; `/cookie` cookie health; `/quota` image quota and GP; `/storage` disk usage; `/scan` trigger library scan; `/help` command list |
  | Queue | `/queue` + InlineKeyboard; `/pause` `/resume` global pause; `/retry <id/all>`; `/cancel <id/gid>` (replies when not found); `/clear` completed history; `/stats` library count + queue snapshot |
  | Tasks | `/tasks` running jobs; `/kill <name>` interrupt |
  | Library | `/search <query>` paginated local search; `/info <gid>` details + cover (5-step fallback); `/random`; `/redownload <gid>` |
  | Favorites | `/fav_sync` categories; `/fav_download [0-9]` missing items; `/fav_check` full update check |

  `/pause` is a **global pause** (persisted to `app_config.user_settings`, survives restart): it **stops claiming new galleries and does not claim new pages** (the current in-flight page finishes; queued galleries are kept and resume later), and pauses **auto scans** and **Web-triggered scans** (trigger returns `paused`). The Web downloads page toggle and bot `/pause`/`/resume` operate **the same switch** (`GET/POST /api/pause`); the yellow pause banner stacks with the Cookie red banner. URLs pasted while paused are ignored, not enqueued. **Pasting a gallery URL** (e.g. `https://exhentai.org/g/2325283/d3722b6aa8/`, extra surrounding slashes are fine) parses the gid/token and enqueues it immediately. The bot reply includes the **gallery title** (and old→new gid if the listing was replaced; 404/deleted is reported and not queued). Unknown non-URL text gets `/help`.

## What Needs the Network

| Class | Operations |
| --- | --- |
| ExHentai | Discover (search / Popular / Watched / Toplist), downloads (gdata / gallery page / H@H / original / Archive / GP & quota), test login, favorites sync and add/remove/move, missing covers, tag sync, online category backfill, quality backfill |
| GitHub | EhTag “Update now” (not EH) |
| Local only | Library search, reader, thumbnails, progress/history, local stars and lists, CBZ export, recycle bin, disk scan, updates comparison, dedupe, logs, disk usage, OPDS, **local category repair** |
| Local first | Enqueue hits gdata only if metadata is missing; detail reads DB; covers/quota use cache first |
