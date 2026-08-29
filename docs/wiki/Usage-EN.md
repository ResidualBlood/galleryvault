# Usage Guide

The SPA uses hash routing (`#/library`, `#/gallery/7`, …), so browser refresh
and back/forward need no server round trip.

## First-run wizard (`#/welcome`)

Right after a fresh deploy (while the default password is still in use) the
login flow lands on `#/welcome`, a three-step wizard:

1. **Change the default password** — replace the built-in `p1a2s3s4` with a
   strong password of your own (required; you can also do it from Settings).
2. **Connect ExHentai** — pick the base URL (ExHentai 里站 / E-Hentai 外站 /
   Custom proxy subdomain) and fill in the `ipb_member_id` / `ipb_pass_hash` /
   `igneous` cookies, with a *Test login* button. (optional)
3. **Fill your library** — *Scan library* or *Check all folders*. (optional)

Completed steps get a ✓; **Finish setup** enters the app. On an already
configured instance login does not force the wizard — visit `#/welcome`
manually to revisit it.

## Library (`#/library`)

- Search by title, filter by category, and browse the indexed galleries with
  pagination.
- This page uses **infinite scroll**: the next page (24 galleries by default)
  is appended as you near the bottom; the numbered pager at the bottom stays
  as a fallback. Your page-size choice is remembered across visits.
- Click a cover to open the gallery detail page.
- **Multi-tag filtering (AND)**: clicking a tag in the suggestions, on the
  gallery detail page or in the tag cloud **appends** it to the active filter
  (all selected tags must match) instead of replacing the existing filter. The
  filter bar above the grid shows each active tag as a removable pill (per-pill
  ×) plus an "AND" badge and a clear-all action; resubmitting the title search
  keeps the current tag filter.
- **Tag filters are opt-in, never guessed**: while you type, tag suggestions
  appear under the search box — **clicking a suggestion** adds that tag to the
  filter (and consumes the clicked word from the query text so it doesn't also
  act as a title keyword). Tags can also be added with explicit `ns:name`
  syntax (`parody:touhou`) or from the tag cloud / gallery detail page.
  Pressing Enter without `ns:name` performs a **title text search only** and
  never auto-promotes words into tag filters.
- **Multi-word search ANDs each word**: the title query splits on whitespace
  and every word must appear (each as an independent substring, order- and
  position-independent), so `mimu gif` matches any title containing both
  mimu and gif. Single-word and CJK-sentence searches behave as before.
- **Scan library** triggers a filesystem scan: new archives are ingested, and
  galleries that are missing are soft-deleted (they come back after a rescan
  once the directory is restored). The completion Telegram notification
  appends `N duplicate-copy group(s) found (gid …)` when duplicates were
  detected, pointing to the Duplicate copies page.

## Duplicate copies (`#/duplicates`)

- When the same gallery (same gid) exists under **more than one scan root**
  (an EhViewer download directory, a CBZ archive, a manual copy), the scan
  keeps one copy automatically per the **duplicate-copy policy** (`duplicate_policy`
  in Settings) and records every other copy on this page.
- Policies: `keep_first` (default — the already-stored copy wins),
  `prefer_more_pages`, `prefer_newer`, `prefer_larger`, `prefer_smaller`,
  `manual` (never auto-resolve — everything is listed for manual review).
- Each duplicate group shows every copy with a cover thumbnail, tags, page
  count, size and posted date; the copy the index currently points at carries a
  *current* badge.
- Actions: **Keep this copy** (re-point the index at it), **Keep & delete
  others** (delete the other copies' files from disk — paths are restricted to
  the scan roots), **Dismiss group** (hide it; restorable).
- The **Scan library** button re-scans immediately to refresh the list;
  dismissed groups stay hidden until the on-disk copies actually change.

## Gallery detail (`#/gallery/<id>`)

- Shows metadata (size, adaptive units), tags and page thumbnails.
- Page thumbnails are paginated, **30 per page by default** (switchable to
  5/30/50/100/200/500); the choice is remembered and survives the reader
  round trip.
- **Thumbnails open at your reading position**: without an explicit `?page=`,
  the pager starts on the page containing your last reading progress (so
  returning from the reader lands near where you were); an explicit `?page=`
  always wins.
- **Click a tag** to jump to the library and **append** it to the active tag
  filter (combine several tags to narrow down).
- **Start reading** opens the reader (positioned at your last reading spot).
- **Open on ExHentai**: opens the corresponding gallery page on ExHentai in a
  new tab. The link is built from the configured base URL
  (`{base}/g/{gid}/{token}/`); your browser must be logged in to EH. Not shown
  for local galleries without a token.
- **Sync tags**: pulls that gallery's tags/metadata from ExHentai, or reuses
  the favorites cache when available (no network).
- With the **public mirror (e-hentai.org)** configured, ExHentai-only galleries
  *pause* tag sync instead of being misclassified as deleted (their category is
  untouched) and resume automatically once Settings switch back to
  `exhentai.org`.
- The favorite folders the gallery belongs to are shown as badges, with an
  **Unfavorite** button.

## Reader (`#/reader/<id>/<page>`)

- Streams one page at a time. Page with **←/→ arrows**, **space** or **click**.
- **Advances to the next gallery after the last page**.
- Preloads the next three pages, so paging is instant.
- **Page images are browser-cached for an hour**: going back a page or
  re-reading a gallery reuses the browser cache instead of downloading again;
  thumbnails are cached for 24 h.
- The progress bar shows `page / total · size` (adaptive B/KB/MB/GB).
- Reading position is saved automatically.
- **The fullscreen button (or the `F` key) enters image-only fullscreen**: only
  the page image fills the screen (proportions kept, `object-fit: contain`,
  black background), and the toolbar and page navigation are hidden. While
  fullscreen, paging (arrows / space / click) swaps the image in place and
  **keeps fullscreen active**; paging past the last page or back to the first
  exits fullscreen first. `Esc` exits and restores the previous fit mode,
  syncing the URL to the current page.
- Galleries opened from a **searched library keep the search context throughout
  the reader**: after paging (arrows / space / click / thumbnail links /
  auto-advance to the next gallery) the back-to-details and back-to-library
  links still carry the active search query and tag filter, so you never land
  back on an unfiltered library.

## Tags (`#/tags`)

- Search the local tag set and see usage counts; filter with the group bar on
  top (All / Tag / Artist / Character / Parody / Group / Female / Male /
  Language / Category).
- **The group filter stays visible across pages.**
- **Clicking a tag in the cloud** opens the library and **appends** the tag to
  the active filter (multi-tag AND combination); tags on the gallery detail
  page append the same way.
- In the Chinese UI, tags show their translations; multi-value tags (`A | B`)
  only show the translated part (untranslated English aliases are hidden).
- Results are fixed at 100 per page (no page-size selector; the API ceiling is
  500).

## Downloads (`#/downloads`)

- Lists download tasks with their status (waiting / downloading / success /
  failed / cancelled), filterable by status.
- Active tasks show a **live progress bar** (`current/total` + percentage); the
  list auto-refreshes every 2 seconds.
- **Retries are resumable**: only the missing/failed pages are fetched; pages
  already on disk are skipped.
- **Failures self-heal**: a transient error (image timeout, ExHentai challenge,
  throttled H@H node) re-queues the task automatically with an **exponential
  backoff** (30s → 2m → 8m → 30m → 1h → … up to 6h), retried up to 10 times
  before the task is marked `failed`; a periodic sweep also re-activates older
  `failed` tasks that still have retry budget left, so the manual retry button
  is rarely needed.
- Waiting/downloading tasks can be **cancelled**; failed/cancelled/successful
  tasks can be **retried** (individually or in bulk with checkboxes).
- **A finished download is ingested into the index immediately** — the gallery
  row, pages and tags are written straight from the download result (cover
  thumbnail generated on first view), with **no full library scan**. The stored
  signature matches the scanner, so a later manual scan skips it.
- With Telegram configured, you get notified on download success/failure and
  scan completion; download notifications default to a **summary** digest (a
  bulk run collapses into one message), switchable to immediate / failures-only
  / off in Settings.

## Logs (`#/logs`)

A single place for background tasks (library scan, tag sync, thumbnail
generation, favorites metadata sync), split into two sections:

- **Running**: start time · task name · `running · done/total` · progress bar ·
  description · **Cancel** button; multiple tasks run side by side.
- **Finished**: start time · task name · status badge (success / failed /
  cancelled) · description & reason · **duration** · finish time; finished tasks
  no longer show a progress bar.

The page auto-refreshes every 2 seconds. The "Sync tags now / Generate now /
Update translations now" buttons in Settings also leave a trace here.

## Favorites (`#/favorites`)

- Lists the ten ExHentai favorite folders: an enable toggle, a mode
  (incremental download / watch only / force download) and the polling
  interval; **Save** writes it all at once.
- **Sync folder names** pulls the folder names from ExHentai.
- **Check now** scans one folder; **Check all folders** scans them all.
- Each folder shows cloud/local counts and sizes; a **progress ring** appears
  next to the name while a check is running.
- Every check caches the full metadata (title, tags, category, posted date,
  size) into the database and **applies the fresh metadata** to already
  downloaded galleries (tag replacement, category/title/posted/size refresh),
  skipping when nothing changed, so repeated checks are cheap.
- Click a folder name to open `#/favorites/<favcat>`: that folder's gallery
  grid (checkboxes, **download selected**, **remove from favorites**, and an
  **All / local only / cloud only** state filter), with inline cloud covers
  and real sizes for cloud galleries. The list uses numbered pagination with
  24 galleries per page by default.
- The **Download missing items** button on the Favorites overview spawns a
  per-folder pass that downloads cover files for every gallery missing one on
  disk (shown inline in lists and duplicate groups).
- Configuring **ExHentai cookies** (Settings → ExHentai, stored encrypted in
  the database) is required — checks will fail and no favorites/covers are
  fetched without them.
- **Manage favorites** (`#/favorites/manage`): **Scan for duplicate galleries**
  groups different versions of the same work (DL / uncensored / language
  re-uploads) so you can bulk **unfavorite** or **unfavorite and delete the
  local copy** — this deletes every physical copy of the gid under the library
  roots; if a copy cannot be deleted (e.g. a read-only mount or permission
  problem) the toast and the Logs page report it, and the gallery row is kept
  so the next scan does not re-import it as a fresh gallery; false positives
  can be hidden with **Ignore selected**, and ignored items can be restored
  from a separate page.

### "download favorites" vs. "enabled"

- **download favorites** in Settings is the global **automatic scheduled check**
  master switch (checks by polling interval and downloads missing galleries).
- The **enabled** checkbox per folder on the Favorites page decides whether that
  folder takes part in the scheduled checks and whether it downloads during
  them (unchecked = record only, never download).

For automatic downloads all three must hold: the master switch is on + the
folder is checked + the mode is "incremental/force download". A manual **Check
now** is not gated by the master switch, but an unchecked folder only records
even when checked manually.

### The three modes

Every check records **all** folder galleries into the local set
(`favorite_items`); the modes differ only in which galleries are candidates for
download:

- **Incremental download**: only downloads galleries **seen for the first time**
  — gids not yet recorded locally (i.e. newly added to the folder). So after a
  folder has been checked once, the existing favorites are *not* downloaded by
  incremental mode (they are already recorded and no longer count as "new").
- **Watch only**: records counts/sizes, never downloads.
- **Force download**: skips the recorded-set filter and queues **every gallery
  in the folder that is not already in the local library** (the `galleries`
  table). Galleries already in the library are still skipped, so nothing is
  re-downloaded.

Incremental and force both skip galleries already in the local library. To pull
down an already-checked folder's backlog, temporarily switch the mode to
**force download** and run **Check now** (or tick **Download selected** inside
`#/favorites/<favcat>`), then switch back to incremental to follow only new
additions again.

## Settings (`#/settings`)

- **Library roots**: one filesystem path per line; new downloads
  are never written here. Deleting a gallery removes its files under these
  roots when the mount is writable; on a read-only mount the deletion fails and
  is reported in the toast and on the Logs page.
- **Downloads**: root directory, concurrent galleries, **pages in parallel per
  gallery** (default 4 — H@H nodes cap concurrent connections per source IP, so
  values much above 4-6 trip the cap and cause connection errors on lossy
  lines; keep it low for stability, raise it only on a clean line), image
  quality (normal/original), H@H network, `max_pages`. Slow-H@H-node watchdogs:
  **image max time** (seconds), **image slow warmup** (seconds) and **image min
  speed** (KB/s) — a single image is aborted once it exceeds the total
  wall-clock budget, or once it averages below the minimum throughput after the
  warm-up window, and is retried with backoff instead of holding the whole
  gallery hostage.
- **Title display** (in the Downloads group): `japanese` (default, Japanese
  title preferred) / `english` / `directory` (folder name). The library,
  browse, gallery detail, favorites (including cloud-only items),
  favorites-duplicates and duplicate-copies pages all show titles according to
  this setting.
- **Download title** (in the Downloads group): controls how downloaded folders
  are named — `japanese` (default, `gid-<Japanese title>`) or `english`
  (`gid-<English title>`). Independent of the display *Title display* setting;
  existing download folders are reused as-is, switching never renames or
  re-downloads them.
- **Account**: change password (this **revokes every logged-in session**) and
  toggle *Require login*.
- **ExHentai**: base URL and `ipb_member_id` / `ipb_pass_hash` / `igneous`
  cookies, with a **Test login** button; cookies are never echoed back.
- **Proxy**: HTTP or SOCKS5 (choose one).
- **Tag sync**: automatic sync after scans/startup, interval and concurrency,
  and a **Sync tags now** button.
- **Thumbnails**: auto-generation toggle, **Generate now**, and the **live
  thumbnail status**.
- **Telegram**: bot token, chat ID, allowed user IDs, **notification level**
  (summary / immediate / failures-only / off) and **notification language**
  (中文 / English) — download, scan, favorites-check and bot-reply
  notifications all use the selected language, formatted as Telegram HTML
  (bold titles, mono gids); gallery titles are never translated. A **Send test
  message** button verifies the bot can reach the chat.
- **Telegram bot control commands** (send from an **allowed user ID**):
  `/pause` pauses the queue (nothing is enqueued while paused), `/resume`
  resumes, `/status` shows the pause state; **pasting a gallery URL** (e.g.
  `https://exhentai.org/g/2325283/d3722b6aa8/`) parses the gid/token and
  enqueues it for download immediately, replying with a confirmation.
- **Translation auto-update**: interval (minutes, 0 = off) and **Update now**.
