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
- This page uses **infinite scroll**: the next page (24 galleries by default)
  is appended as you near the bottom; the numbered pager stays as a fallback.
- Click a cover to open the gallery detail page.
- **Scan library** triggers a filesystem scan of the configured
  library roots. New archives are indexed; missing ones are expired.

### Gallery detail (`#/gallery/<id>`)

- Shows metadata (including gallery size, adaptive units), tags, and page
  thumbnails.
- **Read now** opens the reader at your last reading position (or page 1).
- **Sync tags** pulls tags/metadata for this gallery. When the favorites
  monitor already cached it, the sync is served **from the database cache** (a
  toast says so); otherwise it fetches ExHentai and backfills the cache. The
  detail page also shows which favorite folders the gallery belongs to.

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
- With the Chinese interface enabled, tags render their Chinese translations;
  markdown icon syntax from the translation database is stripped automatically.
  Multi-value tags (`A | B`) keep only their translated values — an untranslated
  English alias is dropped, so e.g. `3-gatsu no lion | march comes in like a lion`
  renders as `3月的狮子`.
- Results are paginated (100 per page, up to 500).

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
- **A finished download is ingested into the index immediately** — the gallery
  row, pages and tags are written straight from the download result (no full
  library scan, no ExHentai round-trip), and its cover thumbnail is generated
  on first view. The stored storage signature matches the scanner fingerprint,
  so a later manual full scan skips it instead of re-ingesting.
- When a Telegram bot is configured you get a notification on download
  success / failure and when a library scan finishes.

### Logs (`#/logs`)

- Shows the **background tasks** (library scan, tag sync, thumbnail generation,
  and the favorites metadata sync/apply that runs after a folder check) in one
  place, split into two sections that size to their content:
  - **Running now**: one row per active task with start time, task
    name, status (`running · done/total`), a live progress bar (indeterminate
    while progress is unknown), a short description, and a **Cancel**
    button — multiple tasks can run at once, each with its own row.
  - **Finished**: every finished/failed/cancelled task with start time,
    task name, a status badge, description, **duration** (finished − started),
    finish time, and the success/failure reason. No progress bar is shown, so a
    finished task is a stable summary rather than a flickering bar.
- The page auto-refreshes every 2 seconds while open. The Logs link also
  appears next to the *Sync tags now* and *Generate now* buttons in Settings.

### Library & search

- Gallery lists (Browse / Library), the gallery-detail thumbnails, History,
  Downloads and the favorite-folder lists all share the same pager: a
  **page-size selector (5/20/50/100/200/500, default 20)** plus numbered
  pagination and a **page-jump box** (type a page number and press Enter /
  blur to jump; `current / total` is shown next to it).
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
  (incremental / monitor-only / force) and polling interval; **Save**
  writes them all at once.
- **Sync folder names** pulls folder names from ExHentai.
- **Check now** scans that folder. A **disabled** folder is check-only (records
  items and sizes, never downloads); an **enabled** folder downloads galleries
  you do not yet have. When *download favorites* is enabled in Settings this
  also runs on a schedule.
- Each folder shows **cloud/local** gallery counts and sizes (cloud size is exact
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
  grid with checkboxes, plus **Download selected** (skipping ones
  already local), **Remove from favorites** and an **All / Local only / Cloud only**
  state filter. Cloud-only galleries show their cover inline with a
  **cloud** badge and real size; local ones use the generated thumbnail and a
  **local** badge. The list is paginated at **24 galleries per page** by
  default. When you arrive from a gallery detail page, a **← Back to gallery**
  link is shown next to **← Favorites**.
- The **Download missing items** button on the Favorites overview (`POST
  /api/favorites/download-missing`) runs a per-folder pass that downloads cover
  files for every gallery missing one on disk — a check captures each cover's
  thumb URL from the listing (stored in `favorite_items.thumb`), and this pass
  warms the disk cache without a gdata round-trip.
- **Manage favorites** (`#/favorites/manage`): **Start duplicate scan** compares every
  favorite gallery (normalized title + artist, e.g. the same work in `[DL版]`,
  `[無修正]` or language re-uploads) and groups duplicates with a progress bar.
  Each group shows the full title; every row shows the cover, local/cloud,
  folder name, posted date, size and translated tags. Filter with
  **All / Local only / Cloud only**, then **Unfavorite** (remove from
  favorites) or **Unfavorite and delete downloaded** (also delete the local
  copies — every physical copy of the gid under the library roots; a copy that
  cannot be deleted, e.g. a read-only mount, is reported in the toast and the
  Logs page, and the gallery row is kept so it is not resurrected as fresh on
  the next scan). Groups that
  merely share a title (same name, different works) are not demoted — select
  their checkboxes and hit **Ignore selected** (next to Clear selection) to hide
  them; the group is struck through in place and disappears on the next scan.
  All ignored groups live on the **Ignored items** page
  (`#/favorites/ignored`, button in the toolbar) where you can batch-restore
  them. The duplicate list is paginated at 20 groups per page.
- Gallery detail pages show an **Unfavorite** button whenever the gallery is in a
  favorite folder.

### Settings (`#/settings`)

- **Library roots**: one filesystem path per line. In Docker these
  must be paths mounted into the container. New downloads never land here, but
  deleting a gallery does remove its files under these roots when the mount is
  writable (a read-only mount reports the failure instead of silently
  succeeding).
- **Downloads**: root directory (where downloads are stored and scanned
  automatically), concurrency, quality (normal/original), H@H network, `max_pages`.
- **Account**: toggle *Require login*. **Change password** asks for the current
  and new password; if still on the default `p1a2s3s4`, a banner prompts you to
  change it. Turning *Require login* off disables authentication entirely.
  Changing the password **revokes every active session** — you have to log in
  again on each device.
- **ExHentai**: base URL plus `ipb_member_id` / `ipb_pass_hash` / `igneous`
  cookies (exported from a logged-in browser session). **Test login** validates
  them. Cookies are never echoed back to the UI.
- **Proxy**: HTTP **or** SOCKS5 (not both).
- **Tag sync**: automatic tag sync after scans / startup, interval, concurrency,
  plus a **Sync tags now** button.
- **Thumbnails**: *Generate thumbnails* switch and **Generate now**
  button; progress appears on the **Logs** page.
- **Telegram**: bot token, chat IDs, allowed user IDs — **Send test message** verifies
  the bot can reach the configured chat.
- **Translation auto-update**: interval (minutes, 0 = off) for the backend to pull the
  latest EhTagTranslation release; **Update now** forces a refresh.

### Downloads (`#/downloads`)

- Each task can be **cancelled** (stops the page writes and removes the partial
  temp dir), **retried**, or **deleted** (removes the task record); bulk
  operations via **Select all / Retry selected / Delete selected**.

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
never echoed back by the API. When the backend runs with `ENCRYPTION_KEY` set,
these values are encrypted at rest (AES-256-GCM); see the project README for
enabling it and for recovering from a lost key.

## API access

Everything the UI does is available over the JSON API. See `docs/API.md` for
the full endpoint list – useful for scripting, the Telegram bot, or external
integrations.
