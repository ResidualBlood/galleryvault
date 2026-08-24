# Usage Guide

GalleryVault is a private, self-hosted manager for local gallery archives
(Ehviewer exports, CBZ/CBR, plain folders) with optional ExHentai download and
metadata synchronisation. This guide covers day-to-day use of the web UI.

## First start

1. Build and start with Docker Compose (see `docs/DEVELOPMENT.md`).
2. Open `http://<host>:8000` (the frontend). You are redirected to the login
   screen. The JSON API lives on `http://<host>:8001`.
3. Enter the instance password (configured via `AUTH_PASSWORD_HASH` / the
   `auth_password` setting). The session cookie is stored in your browser.

> The password gates the whole instance. There is no per-user account system;
> the cookie simply proves you know the password.

## Navigating the UI

The SPA uses hash routing (`#/library`, `#/gallery/7`, …), so browser refresh
and back/forward work without server round-trips.

### Library (`#/library`)

- Search by title, filter by category, and page through your indexed library.
- Click a cover to open the gallery detail page.
- **扫描库 (Scan library)** triggers a filesystem scan of the configured
  library roots. New archives are indexed; missing ones are expired.

### Gallery detail (`#/gallery/<id>`)

- Shows metadata, tags, and page thumbnails.
- **Read now** opens the reader at your last reading position (or page 1).
- **Sync tags** pulls tags/metadata from ExHentai for this gallery (requires
  configured cookies).

### Reader (`#/reader/<id>/<page>`)

- Streams one page image at a time. Use Previous/Next or the arrow keys.
- Reading progress is saved automatically on each page view.

### Tags (`#/tags`)

- Search the local tag taxonomy and see usage counts; filter by namespace with
  the pills (Tags / Artists / Characters / Parodies / Groups / Languages /
  Categories).
- With the 中文 interface enabled, tags render their Chinese translations;
  markdown icon syntax from the translation database is stripped automatically.
- Results are paginated (100 per page).

### History (`#/history`)

- Lists recent reading positions. **Clear history** wipes the log.

### Downloads (`#/downloads`)

- Lists download tasks with their status (pending / downloading / success /
  failed / cancelled); filter by status pills.
- Active tasks show a **live progress bar** (`current/total` + %); while a
  gallery is still being enumerated an indeterminate bar is shown. The list
  auto-refreshes every 2 seconds, and pages are downloaded concurrently (like
  Ehviewer) so long galleries finish faster.
- **Retry resumes**: re-queuing a task only downloads the pages that failed or
  are missing — pages already on disk (in the temp or final folder) are skipped.
- Pending/active tasks can be **cancelled**; failed/cancelled/success tasks can
  be **retried**, individually or in bulk via checkboxes + Retry selected.
- When a Telegram bot is configured you get a notification on download
  success / failure and when a library scan finishes.

### Library & search

- Gallery lists (Browse / Library) and the gallery-detail thumbnails show a
  **page-size selector (5/20/50/100/200/500, default 20) and numbered
  pagination** at the bottom next to the page numbers.
- The Library search box **autocompletes tags** while you type: English matches
  tag names, and **Chinese input is reverse-matched** against the translation
  table (like Ehviewer_CN_SXJ) — typing 巨乳 suggests `big breasts` etc. Click a
  suggestion to filter the library by that tag.
- Each gallery card has a **checkbox**; check several and use **Delete selected**
  (with confirmation) to remove them. **Delete filtered** removes every gallery
  matching the current search/tag/category filter. Each gallery detail page also
  has a **Delete** button. Deletion asks for confirmation and whether to also
  remove the files on disk.

### Favorites (`#/favorites`)

- Lists the ten ExHentai favorite folders with enable checkbox, mode
  (incremental / monitor_only / force) and polling interval; **保存** writes
  them all at once.
- **同步收藏夹名称** pulls folder names from ExHentai.
- **立即检查** scans that folder and enqueues galleries you do not yet have
  locally. When *download favorites* is enabled in Settings this also runs on
  a schedule.

### Settings (`#/settings`)

- **Library roots**: one filesystem path per line. In Docker these must be
  paths mounted into the container.
- **Account**: toggle *Require login*. **Change password** asks for the current
  and new password; if still on the default `p1a2s3s4`, a banner prompts you to
  change it. Turning *Require login* off disables authentication entirely.
- **ExHentai**: base URL plus `ipb_member_id` / `ipb_pass_hash` / `igneous`
  cookies (exported from a logged-in browser session). **测试登录** validates
  them. Cookies are never echoed back to the UI.
- **Proxy**: HTTP **or** SOCKS5 (not both).
- **Downloads**: root directory, concurrency, quality (普通/原图), H@H network.
- **标签同步**: automatic tag sync after scans / startup, interval, concurrency.
- **Favorites**: enable auto-download and set the polling interval.
- **Telegram**: bot token, chat IDs, allowed user IDs — **发送测试消息** verifies
  the bot can reach the configured chat.
- **翻译自动更新**: interval (minutes, 0 = off) for the backend to pull the
  latest EhTagTranslation release; **立即更新** forces a refresh.

## Configuration

There is **no config.json and no required .env file**. All user-editable
settings (library roots, downloads, proxies, favorites, telegram, tag-sync,
translation interval, `auth_required`) are read and written straight to
PostgreSQL (`app_config.user_settings`). The `auth_secret` and `auth_password_hash`
live in `app_config.runtime_auth`.

On a fresh install `docker compose up` works out of the box:

1. The app connects with `DATABASE_URL` (env, with a Docker default), runs
   migrations, then generates and persists a stable `auth_secret` in the DB so
   sessions survive restarts.
2. No password is configured yet, so the built-in default `p1a2s3s4` works and
   the SPA shows a banner prompting you to set a real one in Settings.
3. After you save Settings (or change the password) the values are persisted in
   the DB and are loaded on every subsequent boot — recreating the container
   no longer loses them.

Secrets such as ExHentai cookies, the Telegram token and the auth password hash
are stored (cookies/token in the DB settings, the hash in `runtime_auth`) and
never echoed back by the API.

## API access

Everything the UI does is available over the JSON API. See `docs/API.md` for
the full endpoint list – useful for scripting, the Telegram bot, or external
integrations.
