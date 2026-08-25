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

> **Before scanning your library into the index, it pays to configure ExHentai
> cookies and run *Favorites → Check all folders* once.** The favorites monitor
> batches every favorited gallery's metadata (tags, category, posted date, size)
> into a database cache via the gdata API. Galleries scanned onto disk that the
> monitor has already seen then reuse that cache directly — no per-gallery
> ExHentai fetch for tag sync — so the first scan and the tag-sync pass complete
> far faster. (The same cache is also refreshed automatically on every later
> folder check.)

## Navigating the UI

The SPA uses hash routing (`#/library`, `#/gallery/7`, …), so browser refresh
and back/forward work without server round-trips.

### Library (`#/library`)

- Search by title, filter by category, and page through your indexed library.
- Click a cover to open the gallery detail page.
- **扫描库 (Scan library)** triggers a filesystem scan of the configured
  library roots. New archives are indexed; missing ones are expired.

### Gallery detail (`#/gallery/<id>`)

- Shows metadata (including gallery size, adaptive units), tags, and page
  thumbnails.
- **Read now** opens the reader at your last reading position (or page 1).
- **Sync tags** pulls tags/metadata from ExHentai for this gallery (requires
  configured cookies).

### Reader (`#/reader/<id>/<page>`)

- Streams one page image at a time. Navigate with **←/→ arrow keys**,
  **space**, or by **clicking the image** (next page), plus the Previous/Next
  buttons.
- **Paging past the last page jumps to the next gallery's first page.**
- The next three pages are preloaded so paging feels instant.
- The bar shows `page / total · size` (adaptive B/KB/MB/GB).
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
  (incremental / 仅监控 monitor_only / force) and polling interval; **保存**
  writes them all at once.
- **同步收藏夹名称** pulls folder names from ExHentai.
- **立即检查** scans that folder. A **disabled** folder is check-only (records
  items and sizes, never downloads); an **enabled** folder downloads galleries
  you do not yet have. When *download favorites* is enabled in Settings this
  also runs on a schedule.
- Each folder shows **云端/本地** gallery counts and sizes (cloud size is exact
  once the missing galleries' sizes have been fetched). A **progress ring**
  appears next to the folder name while a check runs (hover shows walked/total),
  and disappears when the sync completes.
- Every check also caches the full ExHentai metadata (title, tags, category,
  posted date, size) keyed by gid — local galleries are seeded straight from
  the DB and cloud-only gids via the batched gdata API. The fresh metadata is
  then **applied to the on-disk galleries of that folder automatically**:
  `gallery_tags` are replaced and category/title/posted/size are refreshed.
  Nothing is rewritten when the cache hasn't changed since the last sync, so
  repeated checks stay cheap. Galleries scanned onto disk later also reuse this
  cache, so **tag sync and ingestion need no extra ExHentai fetch** for
  galleries the monitor has already seen.
- **Click a folder name** to open `#/favorites/<favcat>`: its galleries as a
  grid with checkboxes, plus **下载所选** (Download selected, skipping ones
  already local) and **移除收藏** (Remove from favorites). Cloud-only galleries
  show their cover inline (batched via the ExHentai gdata API, cached) with a
  **云端** badge and real size; local ones use the generated thumbnail and a
  **本地** badge. When you arrive from a gallery detail page, a **← 返回画廊**
  link is shown next to **← 收藏夹**.
- **收藏夹管理** (`#/favorites/manage`): **开始扫描重复画廊** compares every
  favorite gallery (normalized title + artist, e.g. the same work in `[DL版]`,
  `[無修正]` or language re-uploads) and groups duplicates with a progress bar.
  Each group shows the full title; every row shows the cover, local/cloud,
  folder name, posted date, size and translated tags. Filter with
  **全部 / 只显示本地 / 只显示云端**, then **取消收藏** (remove from favorites)
  or **取消收藏并删除已下载** (also delete the local copies).
- Gallery detail pages show a **取消收藏** button whenever the gallery is in a
  favorite folder.

### Settings (`#/settings`)

- **Library roots** (read-only): one filesystem path per line. In Docker these
  must be paths mounted into the container. New downloads never land here.
- **Downloads**: root directory (where downloads are stored and scanned
  automatically), concurrency, quality (普通/原图), H@H network, `max_pages`.
- **Account**: toggle *Require login*. **Change password** asks for the current
  and new password; if still on the default `p1a2s3s4`, a banner prompts you to
  change it. Turning *Require login* off disables authentication entirely.
- **ExHentai**: base URL plus `ipb_member_id` / `ipb_pass_hash` / `igneous`
  cookies (exported from a logged-in browser session). **测试登录** validates
  them. Cookies are never echoed back to the UI.
- **Proxy**: HTTP **or** SOCKS5 (not both).
- **标签同步**: automatic tag sync after scans / startup, interval, concurrency,
  plus a **立即同步标签** (Sync tags now) button.
- **Thumbnails**: *Generate thumbnails* switch and **立即生成** (Generate now)
  button; progress appears in the Background-tasks bar.
- **Telegram**: bot token, chat IDs, allowed user IDs — **发送测试消息** verifies
  the bot can reach the configured chat.
- **翻译自动更新**: interval (minutes, 0 = off) for the backend to pull the
  latest EhTagTranslation release; **立即更新** forces a refresh.

### Downloads (`#/downloads`)

- Each task can be **cancelled** (stops the page writes and removes the partial
  temp dir), **retried**, or **deleted** (removes the task record); bulk
  operations via **全选 / 重试所选 / 删除所选**.

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
