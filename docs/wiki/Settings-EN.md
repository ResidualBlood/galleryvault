# Settings

> [中文](Settings) · English | Part of the [Usage](Usage-EN) series

Settings groups, save rules, per-group fields, OPDS, Telegram Bot, and which operations need network access.

## Settings (`#/settings`)

Settings are organised into 13 groups. The group navigation sits on the left (a drawer on mobile), with a search box over key names, labels, and help text at the top.

**Save rules**:

- Each group saves independently and **submits only the keys changed in that group**; untouched or hidden keys keep their values instead of being written back as defaults.
- Keys marked security-sensitive (login required, trusted proxies, download root, library roots) need the current admin password (or an explicit confirmation when no password is set); otherwise the API returns `428`.
- Credential fields (EH cookies, Telegram bot token, API token) are write-only; the UI shows configured / not configured instead of the value.
- Action buttons (test login, generate thumbnails, sync tags, generate token, …) are separated from value fields; feature pages keep their own shortcuts.

| Group | Contents | Storage |
| :--- | :--- | :--- |
| 1 Appearance & language | Theme, UI language, title display, list page size | Browser / backend |
| 2 Reader | Reading mode, fit, slideshow interval, online image channel | Browser |
| 3 E-Hentai site & network | Site URL, cookies, proxies, H@H toggle, online concurrency/cache, page concurrency cap | Backend / env |
| 4 Online browsing & quick actions | Default favorite folder, online list defaults | Browser |
| 5 Library | Library roots, duplicate policy, thumbnail generation | Backend |
| 6 Downloads | Download root, concurrency, quality, title naming, slow-transfer thresholds, global pause mirror | Backend |
| 7 Favorite sync | Favorite auto-download, archive toggle and page threshold; per-folder settings stay on the Favorites page | Backend |
| 8 Archive & cold storage | Archive roots, auto archive, delete source after archiving, archive quality and fallback pages | Backend |
| 9 Tags | Auto sync, translation updates, category repair | Backend |
| 10 Notifications | Telegram bot and chats | Backend |
| 11 Account & security | Access control, password, sessions, API token, logout | Backend |
| 12 Integrations | Companion script, Comic Looms, OPDS address | — |
| 13 Storage & system | Storage panel, largest galleries, logs entry, PWA | — |

### 1. Appearance & language

| Setting | Field / values | Notes and defaults |
| :--- | :--- | :--- |
| Theme | `gv_theme` | The ◐ button switches dark / light / follow-system (`system`); persisted in local storage, dark by default. |
| UI language | `gv_lang` | Chinese / English; also updates `<html lang>`. |
| Title display | `title_display` | `japanese` / `english` / `directory` for the library, browse, detail, favorites, favorite dedup, and duplicate pages. Default `japanese` (falls back to English). |
| Page size | `gv_page_size` | List page size; list pages keep a quick selector. |

### 2. Reader

| Setting | Field / values | Notes and defaults |
| :--- | :--- | :--- |
| Reading mode | `gv_reader_mode` | Single-page LTR / RTL, double-page, double-page RTL, webtoon; quick switch stays in the reader. |
| Image fit | `gv_reader_fit` | Fit height / width / original; the old frontend kept this in memory only, now it persists per device. |
| Slideshow interval | `gv_slideshow_interval` | Seconds; shared by the reader and the gallery detail page. |
| Online image channel | `gv_online_image_mode` | `direct` (default: the browser fetches from H@H, no server image quota) / `proxy` (server proxy, enabled per device only when direct fails). See [Online Reading](Online-Reading-EN#reader-and-the-two-image-channels). |

### 3. E-Hentai site & network

| Setting | Parameter / field | Notes and defaults |
| :--- | :--- | :--- |
| ExHentai base URL | `exhentai_base_url` | Only `exhentai.org` / `e-hentai.org` and their subdomains. |
| Cookie authentication | `ipb_member_id`<br>`ipb_pass_hash`<br>`igneous` | Verified with “Test login”; fields are write-only and the status is exposed as `exhentai_cookie_configured`. See [Usage → ExHentai cookie setup](Usage-EN#configure-exhentai-cookies). |
| Connectivity probe | Periodic | At startup and every 30 minutes; invalid cookie / no ExHentai access / banned IP shows a red bar, network failure an orange bar, both linking to Settings. |
| Network proxy | `http_proxy` / `socks5_proxy` | Mutually exclusive; filling both is rejected. |
| Use H@H nodes | `use_hah` | Whether EH requests carry the H@H preference (`uh` cookie), deciding whether images come from H@H nodes or the main site. |
| Online concurrency | `online_reader_concurrency` | Shared cap for online resolve and proxy, default 3 (1–16). |
| Online cache limit | `online_cache_max_mb` | Image cache used only by the proxy fallback, default 512 MB. |
| EH page concurrency cap | `exhentai_max_concurrency` | Read-only; set by `EXHENTAI_MAX_CONCURRENCY` (1–32, default 6). EH page / gdata / favorites requests share this budget. |
| 302 probe interval | `GV_CHALLENGE_PROBE_INTERVAL` | Environment variable, default 600 s. |
| Max challenge pauses per task | `GV_MAX_CHALLENGE_PAUSES` | Environment variable, default 5; the task then fails with its remaining retry budget preserved. |
| Security headers | All responses | The backend adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, and `Content-Security-Policy` (`frame-ancestors 'none'`, `worker-src 'self'`; only `img-src` is widened for online images). |

### 4. Online browsing & quick actions

| Setting | Field / values | Notes and defaults |
| :--- | :--- | :--- |
| Default favorite folder | `gv_default_favcat` | Target folder for the online card / detail quick favorite; the first favorite asks once and can remember it. |
| Online list defaults | `gv_online_defaults` | List type, Toplist period, and minimum rating; the old frontend only wrote these into the URL and never remembered them. |

### 5. Library

| Setting | Parameter / values | Notes and constraints |
| :--- | :--- | :--- |
| Library roots | `library_roots` | One path per line; defaults to `/library` and `/downloads`. A trailing slash does not affect deduplication; a scan root itself is never a valid deletion target. Read-only warnings are exposed via `library_root_warnings`. |
| Duplicate policy | `duplicate_policy` | Default keep rule for same-GID copies (`keep_first` / `prefer_more_pages` / `prefer_newer`, plus manual selection); the duplicates page links here. |
| Thumbnail generation | `generate_thumbnails` | Auto-generate toggle plus “Generate now” with live status; worker count comes from `THUMBNAIL_WORKERS` (1–16, default 4). |
| Archives and documents | `.7z` / `.pdf` | `.7z` indexes images only and decompresses pages in memory (128 MB per page); `.pdf` extracts embedded images and skips images over 128 MB or failed extractions. |

### 6. Downloads

| Setting | Parameter / values | Notes and defaults |
| :--- | :--- | :--- |
| Download root | `download_root` | Hot directory for new tasks; security-sensitive. |
| Concurrent galleries | `download_concurrency` | Number of gallery tasks running at once; applies immediately. |
| Archive transfer concurrency | Fixed cap | Official archive zip streaming uses at most 2 connections, independent of gallery concurrency; resumed transfers reuse the requested links. |
| Pages per gallery | `page_concurrency` | Images fetched at once for one gallery, default `4`. H@H nodes limit per-IP concurrency, so a high value causes connection errors. |
| Download quality | `download_quality` | Resample / original. |
| Download title naming | `download_title` | Only names new folders under the download root: `japanese` (default, `gid-japanese title`) or `english`; independent of the UI title display, and existing folders are not renamed. |
| Slow H@H watchdog | `image_download_timeout_seconds`<br>`image_slow_warmup_seconds`<br>`image_min_speed_kb_s` | Per-image time limit, warm-up window, and minimum rate (default 30 s warm-up, below 10 KB/s is throttled); also applies to archive zip transfers. |
| Global pause | `global_paused` | Shared with the Downloads page button and Telegram `/pause` / `/resume`; mirrored here with a link. |

### 7. Favorite sync

| Setting | Field / values | Notes and defaults |
| :--- | :--- | :--- |
| Favorite auto-download | `download_favorites_enabled` | Master switch; when off, folders are checked but never downloaded. |
| Favorite archiving | `favorites_archive_enabled` | Large galleries found by the scheduled check use the official archive channel. |
| Archive page threshold | `favorites_archive_max_pages` | `0` means all. |
| Per-folder settings | `favorites[].enabled` / `.mode` / `.poll_interval_minutes` | Maintained on the Favorites page; Settings only links there. |

### 8. Archive & cold storage

| Setting | Parameter / values | Notes and constraints |
| :--- | :--- | :--- |
| Cold storage roots | `archive_roots` | One path per line (e.g. `/archive`); empty disables archiving, and the legacy `cold_storage_root` becomes a single entry. Mounting and capacity balancing: [Deployment → Tiered storage](Deployment-EN#2-tiered-storage--multi-disk-mounting). |
| Automatic archiving | `auto_archive_downloads` | Off by default. |
| Delete source after archiving | `archive_delete_source` | Off by default. |
| Cold archive limits | Fixed | A single volume holds **500 pages and 2 GiB** (AND); beyond that a cold directory is created instead of one CBZ. CBZ path `{cold}/cbz/{hh}/{ii}/{gid}-{DB English title}.cbz` with `.galleryvault.json` inside. Entry point: **Manage → Cold archive** (`#/archive`). |
| Archive quality | `archive_quality` | Default quality tier for official archive downloads. |
| Fall back to per-page | `archive_fallback_pages` | On by default; when the archive channel is unavailable, fall back to per-page download without spending GP. |
| Purge leftovers | Storage action | Removes leftover files from archived source directories, skipping pending / downloading tasks. |

### 9. Tags

| Setting | Field / action | Notes and behaviour |
| :--- | :--- | :--- |
| Automatic tag sync | `auto_sync_tags` / `tag_sync_interval_seconds` / `tag_sync_concurrency` | Syncs tag metadata after scans or startup; “Sync tags now” is available. |
| Translation auto-update | `tag_translation_update_interval_minutes` | `0` disables (default 720); “Update now” and status are provided. |
| Local category repair | Offline action | Re-derives categories from local `.galleryvault.json` tags without network access. |

### 10. Notifications

- **Basics**: `telegram_bot_token` (write-only), `telegram_chat_ids`, `telegram_allowed_user_ids`, plus “Send test message”; with a token configured, the command menu is registered at startup.
- **Notification options**: `telegram_notify_level` (summary / instant / failures only / off) and `telegram_notify_lang` (Chinese / English). Downloads, scans, favorite checks, 302 challenge alerts, and bot replies all follow that language. Messages use Telegram HTML (bold titles, monospace GIDs) and keep gallery titles untranslated.

**Command table** (allowed user IDs only; type `/` in the chat for the menu):

| Category | Commands | Notes |
| :--- | :--- | :--- |
| System & ops | `/status`<br>`/ping`<br>`/cookie`<br>`/quota`<br>`/storage`<br>`/scan`<br>`/help` | Runtime and queue overview; latency test; cookie validity; image quota and GP; disk usage; library scan; command help. |
| Downloads & queue | `/queue`<br>`/pause`<br>`/resume`<br>`/retry <id/all>`<br>`/cancel <id/gid>`<br>`/clear`<br>`/stats` | Queue with action buttons; global pause and resume; retry failures; cancel tasks; clear success records; library count and queue snapshot. |
| Background tasks | `/tasks`<br>`/kill <name>` | Long-running task list; interrupt a task. |
| Library | `/search <keyword>`<br>`/info <gid>`<br>`/random`<br>`/redownload <gid>` | Local search and paging; gallery details and cover; random gallery; re-download. |
| Favorites | `/fav_sync`<br>`/fav_download [0-9]`<br>`/fav_check` | Sync folder categories; download missing items from one folder; full update check. |

**Global pause and URL handling**:

- `/pause` persists in `app_config.user_settings` and survives restarts; no new galleries are claimed, the page already in flight finishes, and the queue is kept. The Downloads page pause button and the bot share `GET/POST /api/pause`.
- Pasting a gallery URL into the chat resolves the GID and token, enqueues it unless paused, and replies with a confirmation and title; 404 / deleted galleries are not enqueued.

### 11. Account & security

| Setting | Field / action | Notes and defaults |
| :--- | :--- | :--- |
| Login required | `auth_required` | Toggles authentication; security-sensitive. |
| Change password | — | Revokes every logged-in session. |
| Session lifetime | `galleryvault_session`<br>`galleryvault_csrf` | Default 10 years (`315360000` s); changing the password or resetting the signing key invalidates existing sessions. |
| Security confirmation | Current password / explicit confirmation | Changing login required, trusted proxies, download root, or library roots needs the admin password, or an explicit confirmation when no password is configured (otherwise `428`). |
| Login protection | `429` / `Retry-After` | Five consecutive failures start exponential backoff (5 s up to 15 min); a separate per-IP limit allows 10 attempts per minute. Counters are per process and reset on restart. |
| Companion script API token | Generate / revoke | Bearer authentication for the companion userscript. Plaintext is shown once (`POST /api/auth/api-token`); `GET` reports configured state and creation time; `DELETE` revokes immediately. Only a logged-in session may manage it — a Bearer token cannot create or revoke tokens. See [Online Reading → Companion script](Online-Reading-EN#companion-script-optional-zero-server-quota). |
| Logout | — | Clears the session cookie; also available in the top bar. |

### 12. Integrations

| Feature | Protocol / path | Authentication and behaviour |
| :--- | :--- | :--- |
| Companion script | `/galleryvault-companion.user.js` | Injects state, download, favorite, and open buttons on official EH gallery pages; authenticates with the API token and only reaches whitelisted endpoints. |
| Reading enhancement | Comic Looms | Reader enhancements on the official page come from a third-party script; this project neither bundles nor copies its code. |
| OPDS catalog | `GET /api/opds` | Returns up to 50 recently ingested galleries (Atom XML); acquisition entries point to `GET /api/galleries/{id}/export.cbz`. |
| OPDS auth | HTTP Basic | Username is fixed to `galleryvault` (not an EH account), password is the web login password; cookies also work. Unauthenticated requests return `401` with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`. |
| CBZ export | `GET/HEAD /api/galleries/{id}/export.cbz` | Same Basic auth or cookie session as OPDS; regular `/api/*` requests still accept cookie sessions only. |

### 13. Storage & system

| Feature | Notes |
| :--- | :--- |
| Disk usage table | Shows library, cold, downloads, and cache paths, item counts, used space, and free space, plus the 10 largest galleries. Opening Settings does not scan the whole disk; statistics do not cross mount points and hard links count once. |
| Runtime logs | Log level and filters stay on the logs page (`#/logs`); Settings only links there. |
| PWA | Installable to the home screen; the Service Worker caches the app shell and static assets (network-first) and explicitly does not cache gallery images or `/api/` responses. |

## Which operations use the network

| Network target | Operation | Conditions and behaviour |
| :--- | :--- | :--- |
| **ExHentai / E-Hentai** | Online browsing and search | Search, Popular, Watched, and Toplist; results are briefly cached server-side (60 s / 120 s). |
| | Online reading (direct) | The backend resolves one image URL per page (page budget); the browser fetches it from H@H, spending no server image concurrency or bandwidth. |
| | Online reading (proxy fallback) | Images are relayed by this server, spending server image concurrency (12) and cache; off by default, enabled per device. |
| | Per-page downloads | Concurrency-limited; original and normal requests are controlled separately and fetched through H@H nodes. |
| | Official archive downloads | Spends GP or quota and fetches the site's archive directly. |
| | Tag and metadata sync | Batched gdata calls for metadata, online categories, and quality probes. |
| | Two-way favorite management | Periodically pulls cloud folders, counts, and lists; submits add / remove / move / note changes to the cloud. |
| | Cookie probe and quota check | At startup and every 30 minutes; only a valid session page (`/uconfig.php` member page) counts as healthy; anti-bot challenges (Challenge / 509) trigger recovery probes. |
| | New-version downloads | Fetching the new GID's gallery data when an update task is created. |
| **GitHub API (`api.github.com`)** | EhTag translation database | Checks for and downloads EhTag updates. |
| **Telegram Bot API (`api.telegram.org`)** | Notifications and interaction | Push notifications and long-polling bot commands (requires a bot token). |
| **Fully offline** | Gallery detail and local reading | Detail pages read the local database; the reader loads local files only. |
| | Library maintenance and cold archive | Filesystem scans, CBZ archiving and source cleanup, OPDS catalog and CBZ export, trash operations. |
| | Favorite update pre-filter | Text matching against local records and titles; no outbound request. |
| | Local category repair | Re-derives categories from local `.galleryvault.json` tags. |
| **Local-first cache exceptions** | Detail and enqueue preparation | Detail prefers the local database; enqueue preparation reuses local metadata and only calls gdata when missing. |
| | Cover and quota cache | Remote covers check the local cache first; GP and quota are not re-requested while cached. |
| | PWA resource cache | The Service Worker caches pages and static assets network-first and never caches gallery images or `/api/` responses. |
