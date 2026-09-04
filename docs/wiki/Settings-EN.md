# Settings

> [中文](Settings) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers GalleryVault's system settings, client and OPDS integration, Telegram bot commands, and network access behavior across features.

## Settings (`#/settings`)

- **Library roots**: one filesystem path per line; new downloads are never written here. Deleting a gallery removes its files under these roots when the mount is writable; on a read-only mount the deletion fails and is reported in the toast and on the Logs page.
- **Downloads**: root directory, concurrent galleries, **pages in parallel per gallery** (default 4 — H@H nodes cap concurrent connections per source IP, so values much above 4-6 trip the cap and cause connection errors on lossy lines; keep it low for stability, raise it only on a clean line), image quality (normal/original), **archive quality** (default tier for archive downloads), **fall back to page-by-page if archive is unavailable** (on by default — a gallery the archive channel cannot serve downloads page-by-page, no GP cost), H@H network, `max_pages`. Slow-H@H-node watchdogs: **image max time** (seconds), **image slow warmup** (seconds) and **image min speed** (KB/s) — a single image is aborted once it exceeds the total wall-clock budget, or once it averages below the minimum throughput after the warm-up window, and is retried with backoff instead of holding the whole gallery hostage. The downloads group also carries **archive page threshold** (0 = all) and the **"archive large favorites on scheduled scan"** toggle.
- **Title display** (in the Downloads group): `japanese` (default, Japanese title preferred) / `english` / `directory` (folder name). The library, browse, gallery detail, favorites (including cloud-only items), favorites-duplicates and duplicate-copies pages all show titles according to this setting.
- **Download title** (in the Downloads group): controls how downloaded folders are named — `japanese` (default, `gid-<Japanese title>`) or `english` (`gid-<English title>`). Independent of the display *Title display* setting; existing download folders are reused as-is, switching never renames or re-downloads them.
- **Account**: change password (this **revokes every logged-in session**) and toggle *Require login*.
- **ExHentai**: base URL and `ipb_member_id` / `ipb_pass_hash` / `igneous` cookies, with a **Test login** button; cookies are never echoed back. A health probe runs at startup and every 30 minutes; expired cookies or no ExHentai access show distinct red top banners linking to Settings (also refreshed once right after login). For setup instructions, see [Usage Guide: Cookie Setup](Usage-EN#configuring-exhentai-cookies).
- **Proxy**: HTTP or SOCKS5 (choose one).
- **Tag sync**: automatic sync after scans/startup, interval and concurrency, and a **Sync tags now** button.
- **Thumbnails**: auto-generation toggle, **Generate now**, and the **live thumbnail status**.
- **Telegram**: bot token, chat ID, allowed user IDs, **notification level** (summary / immediate / failures-only / off) and **notification language** (中文 / English) — download, scan, favorites-check and bot-reply notifications all use the selected language, formatted as Telegram HTML (bold titles, mono gids); gallery titles are never translated. A **Send test message** button verifies the bot can reach the chat.
- **Disk usage**: the Settings page shows library / downloads / cache usage and the 10 largest galleries. Library size is queried directly from DB `storage_size`, volume metrics from `disk_usage`, and downloads/cache use in-memory snapshots with live mutation deltas alongside periodic background `du` calibration, returning sub-second without synchronous disk traversal on page load. Missing directories report 0.
- **PWA**: add to home screen. The service worker caches only the html/css/js shell (js/css **network-first**, then update the cache; offline falls back to cache), **not gallery images or `/api/`**.
- **Light theme**: ◐ in the top bar; `localStorage gv_theme=dark|light`, default dark.
- **7z / PDF scan**: library scan accepts `.7z` (py7zr, images only) and `.pdf` (embedded images; skip with a warning if none).
- **OPDS & CBZ export**: `GET /api/opds` (atom+xml) lists recent ingestions with acquisition links to `GET /api/galleries/{id}/export.cbz`. Both endpoints support HTTP Basic authentication (fixed username `galleryvault`, not an EH account; password is the web login password) for third-party reader clients (Tachiyomi, Panels, Chunky, etc.); session cookie authentication remains fully supported. Missing or invalid credentials return `401 Unauthorized` with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`. All other `/api/*` routes remain cookie-only.
- **Telegram bot control commands** (send from an **allowed user ID**): `/help` lists commands, `/queue` shows a pending/running/failed summary, `/stats` library count plus queue pending/downloading/failed, `/cancel <id|gid>` cancels a task (replies when not found), and unknown non-URL text gets a help reply; `/pause` pauses intake (URLs pasted while paused are ignored, not enqueued), `/resume` re-enables intake, `/status` shows the pause state; `/pause` is a **global pause** (persisted to `app_config.user_settings`, survives restart): it **stops claiming new galleries and does not claim new pages** (the current in-flight page finishes; queued galleries are kept and resume later), and pauses **auto scans** and **Web-triggered scans** (trigger returns `paused`). The Web downloads page toggle and bot `/pause`/`/resume` operate **the same switch** (`GET/POST /api/pause`); after a web pause the Bot matches it, and the top yellow pause banner stacks with the Cookie red banner. **Pasting a gallery URL** (e.g. `https://exhentai.org/g/2325283/d3722b6aa8/`) parses the gid/token and enqueues it immediately. The bot reply includes the **gallery title** (and old→new gid if the listing was replaced; 404/deleted is reported and not queued).
- **Translation auto-update**: interval (minutes, 0 = off) and **Update now**.

## What Needs the Network

| Class | Operation | Note |
| --- | --- | --- |
| Fetches from ExHentai | Discover page search | Fetches from ExHentai |
| Fetches from ExHentai | Popular | Fetches from ExHentai |
| Fetches from ExHentai | Watched | Fetches from ExHentai |
| Fetches from ExHentai | Toplist | Fetches from ExHentai |
| Fetches from ExHentai | Download execution (gdata / gallery page / showpage / H@H) | Fetches from ExHentai |
| Fetches from ExHentai | Original images fullimg.php | Fetches from ExHentai |
| Fetches from ExHentai | Archive archiver.php | Fetches from ExHentai |
| Fetches from ExHentai | Archive preview & GP check | Fetches from ExHentai |
| Fetches from ExHentai | Quota home.php / exchange.php | Fetches from ExHentai |
| Fetches from ExHentai | Cookie test | Fetches from ExHentai |
| Fetches from ExHentai | Favorites full sync favorites.php + gdata | Fetches from ExHentai |
| Fetches from ExHentai | Sync category names | Fetches from ExHentai |
| Fetches from ExHentai | Add / remove / move favorites & notes (writes DB after cloud success) | Writes local DB only after cloud success |
| Fetches from ExHentai | Missing cover thumbnails | Fetches from ExHentai |
| Fetches from ExHentai | Tag sync button & background worker | Fetches from ExHentai |
| Fetches from ExHentai | Category "other" backfill | Fetches from ExHentai |
| Fetches from ExHentai | Quality tier backfill | Fetches from ExHentai |
| Fetches from GitHub (not EH) | EhTag translation updates | Accesses GitHub Releases, not ExHentai |
| Local only | Library list & search | Does not contact EH |
| Local only | Reader | Does not contact EH |
| Local only | Thumbnails | Does not contact EH |
| Local only | Reading progress & history | Does not contact EH |
| Local only | Local ratings & private tags | Does not contact EH |
| Local only | Export CBZ | Does not contact EH |
| Local only | Recycle bin & delete | Does not contact EH |
| Local only | Filesystem scan | Does not contact EH |
| Local only | Gallery updates page (local comparison) | Local comparison, does not contact EH |
| Local only | Deduplication | Does not contact EH |
| Local only | Local lists | Does not contact EH |
| Local only | Chinese tag completion | Does not contact EH |
| Local only | System logs | Does not contact EH |
| Local only | Disk usage | Does not contact EH |
| Local only | OPDS | Does not contact EH |
| Local first | Download enqueue (gdata only if metadata missing) | Remote gdata only when missing |
| Local first | Gallery detail view | Reads local DB only |
| Local first | Covers / category counts / quotas | Cached locally first |
