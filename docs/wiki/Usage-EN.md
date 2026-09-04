# Usage Guide

The SPA uses hash routing (`#/library`, `#/gallery/7`, …), so browser refresh
and back/forward need no server round trip. Desktop top navigation features
Browse, Discover, Library, Tags, Downloads, Favorites, and "Management", with
History, Settings, and Logs organized under the "More" dropdown. Management embeds
shared tabs for Recycle Bin (`#/recycle`), Duplicate Copies (`#/duplicates`), and
Missing Pages (`#/integrity`); clicking "Management" opens `#/recycle`, and all
legacy hash URLs remain backward-compatible (the mobile hamburger menu keeps a
flat structure). The top banner can stack a yellow
global-pause bar, a red Cookie-expired / no-access bar, and an image-quota warning. The bell
next to 🎲 is the **in-app notification center** (download complete/fail, library
scan complete/fail, cookie expiry / no access — visible even without Telegram; polled about
every 15s). The Cookie red banner is unchanged.

## Browse (`#/browse`)

- The default landing page (an empty hash / unspecified route also lands
  here): a grid of the newest galleries, reverse-chronological, with numbered
  pagination.
- **Continue Reading Cards**: Top section automatically aggregates recently read
  galleries with cover thumbnails, reading progress bars, one-click resumption,
  and per-gallery "Mark as unread / ✕" (clears progress and removes the
  card from Continue Reading / History).
- The **tag namespace strip** on top (Tag / Artist / Character / Parody /
  Group / Female / Male / Language) and a **random gallery** button (🎲, opens
  a random gallery's detail page).
- The **global search box** in the top bar jumps to the library and runs the
  title search on Enter; pressing **`/`** anywhere focuses the search box.
- The gallery grid supports **keyboard arrow navigation** (`←`/`→`/`↑`/`↓`
  moves focus, `Enter` opens the detail page).

## Discover (`#/discover`)

- Browse / search ExHentai; the toolbar also has **Popular / Watched / Toplist** (Toplist: yesterday / month / year / all-time = site `tl=11/12/13/15`). Watched without a login uses the existing Cookie error state.
- Toolbar: query, category checkboxes (site `f_cats` bitmask), minimum rating, download quality (resample by default, original optional).
- Cards: cover, title, category, page count, rating; stackable badges **in library / favorited / not downloaded**.
- **Download** uses existing `POST /api/downloads`; **Add to favorites** picks folder 0–9 via `POST /api/favorites/add` (**local DB is written only after cloud success**).
- Infinite scroll uses the site `next=gid-ts` cursor, **not** `page=N`; a short TTL cache avoids re-hitting the first page while scrolling.
- No hits, Sad Panda, empty-body anti-bot, 509, and cookie expiry are **shown separately** and never treated as “no results” (which would keep paging). Cookie expiry still uses the top red banner.

## History (`#/history`)

- Lists reading history per gallery (last reading position and time), with direct
  "Read Now" shortcuts and per-gallery "✕" mark-as-unread buttons (clears
  progress and removes the row from History / Continue Reading).
- **Clear history**: clears timeline entries (does not affect progress bookmarks on galleries).
- **Clear reading progress**: resets reading progress for all galleries after confirmation (marks all as unread / progress reset to 0).
- The reading position is saved automatically by the reader and restored when you reopen a gallery / reader.

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

- Search by title, filter by category, sort across multiple fields, filter by reading status, and browse indexed galleries.
- **Multi-criteria Sorting**: Order by **Ingest date (default)**, **Posted date**, **Title**, **Pages**, **Size**, and **Rating**, backed by dedicated database indexes for sub-second responses on large collections.
- **Reading Status Filter**: Quickly filter by **All**, **Unread**, **Reading**, or **Completed**; the three are mutually exclusive. Unread excludes completed. Completed requires actually having read (progress > 0 and at the last page; a 1-page gallery with progress 0 is not completed).
- **Page count & rating range**: the toolbar has min/max page inputs and a minimum rating (≥2 / ≥3 / ≥4 / ≥4.5). Also: size range (MB → bytes), posted date, uploader substring, image quality (original/resample), language shortcuts (existing `language:` tags), local star rating, and local lists. These stick with sort, read status and tag filters.
- **Saved searches**: store the current library filter under a name (about 30 max, in `user_settings.saved_searches` with get+merge so `auth_secret` is kept); apply or delete from the toolbar.
- **Local lists**: independent of ExHentai. Add/remove from the library or detail page; gid-less CBZ archives can join; the library can filter by list (see the dedicated section below).
- **"Not in favorites" filter**: the category dropdown ends with "Not in
  favorites", showing local galleries whose gid is not in any ExHentai favorite
  folder (gid-less local archives count as not favorited; older local copies with
  a newer favorited version are excluded and routed to Gallery Updates instead).
  Before favorites have ever been synced this item is equivalent to "All".
- This page uses **infinite scroll**: the next page (24 galleries by default)
  is appended as you near the bottom; the numbered pager at the bottom stays
  as a fallback. Your page-size choice is remembered across visits.
- Click a cover to open the gallery detail page.
- **Multi-tag filtering (AND / OR) & Exclude Tags (`-tag`)**:
  - Clicking a tag **appends it to the filter**; **Shift / Alt / Ctrl / Cmd + click** on a gallery card's tag **appends it as an exclude tag** (`-namespace:name`, e.g. `Shift+click female:lolicon → -female:lolicon`) — the click uses `stopPropagation` so it won't open the gallery, and the red badge shows the exclusion; excluded tags are honored by **Delete filtered** and sticky navigation;
  - The tag filter bar lets you toggle **AND / OR** mode;
  - Exclude tags (`-namespace:name` or `-tag`, e.g. `-female:lolicon`) are displayed with distinct red badges, excluding matching galleries.
- **Tag filters are opt-in, never guessed**: while you type, tag suggestions
  appear under the search box — **clicking a suggestion** adds that tag to the
  filter (and consumes matching query tokens — including partial input such as
  「和泉」 when picking 「和泉纱雾」 — so they don't also act as a title keyword;
  leftover words still search the title). Tags can also be added with explicit `ns:name`
  syntax (`parody:touhou`) or from the tag cloud / gallery detail page.
  Pressing Enter without `ns:name` performs a **title text search only** and
  never auto-promotes words into tag filters.
- **Multi-word search ANDs each word**: the title query splits on whitespace
  and every word must appear (each as an independent substring, order- and
  position-independent), so `mimu gif` matches any title containing both
  mimu and gif. Single-word and CJK-sentence searches behave as before.
- **Batch add to favorites**: after selecting cards, **Add to favorites** picks
  a folder 0–9 and submits in chunks of 25; **only cloud-confirmed gids are
  written locally** (add is a move — one gid lives in one favcat); gid-less
  local archives are skipped with a toast.
- **Bulk & filtered deletion**:
  - Ticking gallery cards reveals a **Delete selected** action, with an option
    to delete corresponding files on disk (**leaving files on disk sends the
    row to `#/recycle` → User deleted**, restorable);
  - **Delete filtered** removes all galleries matching the active category,
    search query, read status, or tag filter at once. A 5,000-row safety guard rejects
    excessive matches with `409` to prevent accidental library wipes; deletion
    runs safely in 500-row batches, keeping the DB row and logging a notice
    if disk files are read-only.
- **Scan library** triggers a filesystem scan: new archives are ingested, and
  galleries missing from disk go to `#/recycle` → Scan missing (restorable;
  purge removes them from the index). The completion Telegram notification
  appends `N duplicate-copy group(s) found (gid …)` when duplicates were
  detected, pointing to the Duplicate copies page. A **global pause** skips
  the scan (the trigger returns `paused`).

## Local Lists (`#/library`)

- **Independent of ExHentai**: Local lists are completely decoupled from ExHentai cloud favorites; gid-less local archives (CBZ, directory galleries) can be freely added and organized.
- **Frontend Entry & Filtering**: Accessible from the Library (`#/library`) and Gallery Detail (`#/gallery/<id>`) pages. The list dropdown on the Library toolbar filters galleries by list (URL hash `#/library?list_id=<id>`).
- **List Lifecycle Management**: Supports creating, renaming, and deleting local lists. You can click "New list" on the Library toolbar to create one instantly; the backend API provides full CRUD capabilities (`POST /api/lists`, `PATCH /api/lists/{id}`, `DELETE /api/lists/{id}`).
- **Adding & Removing Galleries**: In the Library, tick galleries and click "Add to list" to batch-assign them (prompts to create a new list if none is selected); on the Gallery Detail page, click the toolbar list buttons to add or remove the gallery from a list with one click.

## Duplicate copies (`#/duplicates`)

- Accessible via the "Management" tab bar in desktop navigation (legacy hash `#/duplicates` remains directly usable). When the same gallery (same gid) exists under **more than one scan root**
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
- The **Scan library** button triggers an immediate scan and refreshes the list upon completion (shows a paused notice when globally paused instead of starting a scan); pill filters for All / Pending / Dismissed display active highlights; dismissed groups stay hidden until the on-disk copies actually change.

## Recycle Bin (`#/recycle`)

- Default landing view of the "Management" navigation tab (legacy hash `#/recycle` remains directly usable). Two tabs: **User deleted** (library delete without removing files) and **Scan
  missing** (not found on disk during a scan).
- **Restore** puts galleries back in the library (user-deleted only; scan-missing
  ghosts are not restored into the library); **Purge** asks again whether
  to delete files on disk (purged-with-files will not be re-ingested on scan).
- Galleries in the recycle bin are **not** treated as “newer version already
  local” and will not trigger a hard-delete of the old copy.

## Missing pages (`#/integrity`)

- Accessible via the "Management" tab bar in desktop navigation (legacy hash `#/integrity` remains directly usable). Lists galleries whose recorded `page_count` disagrees with pages on disk
  (unset page counts are excluded).
- **Repair / re-download** only fetches the missing pages.

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
- **Export CBZ**: download this gallery as a CBZ. An on-disk `.cbz` is served as-is; a directory gallery is packed in page order (on-disk format is not rewritten).
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
- **Local rating / note / custom tags**: 1–5 stars, a note, and `local:` tags on the detail page (EH tags are not overwritten; tag sync keeps `local:`). The library can filter by local stars.
- The favorite folders the gallery belongs to are shown as badges. Galleries support **Add to Favorites** (modal folder selector 0–9; cloud success writes locally and moves the gid out of other folders), **Change Folder** (Move), and **Unfavorite**, with strict cloud-success verification before updating local database records. **Favorite notes** can be edited via EH applyfav / `favnote` (local write only after cloud success) and are shown on the favorites list.
- **Original / resampled**: next to the favorite badges the detail page shows
  whether the local copy is original or resampled (hidden when unknown).
  Quality is recorded when a gallery is downloaded and inferred for existing
  galleries by comparing the local file size against the ExHentai original
  size — backfilled during the favorites metadata sync (poll / check now /
  fetch missing) and when a **library scan** completes.
- **Upgrade to original**: galleries that are not already original and have an
  ExHentai gid get two toolbar buttons —
  - **Download original**: downloads original images page-by-page (no GP, see
    the Downloads page for progress); not enqueued when the gallery has no
    original images on ExHentai.
  - **Archive-download original**: shows a cost/balance preview (locked to the
    original tier, disabled when original is unavailable or GP is too low) and
    downloads through the ExHentai archive (zip) channel.
  - After an original download finishes, the superseded resampled copy is
    removed automatically (only when the page count matches; if the mount is
    read-only the task still succeeds and you are told to remove it manually).

## Reader (`#/reader/<id>/<page>`)

- Streams one page at a time. Page with **←/→ arrows**, **space** or **click**.
- **Page Jump Input & `G` Shortcut**: Direct page number input in the toolbar jumps immediately on Enter; pressing **`G`** anywhere focuses the page jump input or opens a quick jump prompt in fullscreen.
- **Multi-mode reading (LTR / RTL Manga / Double-page / Webtoon)**: The "Mode" toolbar button switches between **Left-to-Right (LTR)**, **Manga (RTL)**, **Double Page**, **Double RTL**, and **Webtoon** with persisted user preference. In RTL mode, key and tap directions invert naturally; in Double-page mode, pairs of pages display side-by-side on wide screens (with solo cover on page 1). Webtoon is a vertical continuous strip (`loading="lazy"`); the visible page is written as reading progress. Click/arrow paging and double-page spreads are not used; the toolbar still supports `G` jump and back-to-details.
- **Mobile Touch Gestures**: Supports double-tap zoom (2.2x) and two-finger pinch-to-zoom.
- **Advances to the next gallery after the last page**.
- Preloads the next three pages (four pages in double-spread mode), so paging is instant.
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
- **Fit-mode toggle**: the "Fit" button in the reader toolbar cycles through
  the display modes (default: scale to page width), which helps with pages of
  unusual aspect ratios; leaving fullscreen restores the mode that was active
  before entering.
- Galleries opened from a **searched library keep the search context throughout
  the reader**: after paging (arrows / space / click / thumbnail links /
  auto-advance to the next gallery) the back-to-details and back-to-library
  links still carry the active search query and tag filter, so you never land
  back on an unfiltered library.

## Tags (`#/tags`)

- Search the local tag taxonomy and view usage counts; filter by namespace strip (All / Tag / Artist / Character / Parody / Group / Female / Male / Language / Category).
- The namespace filter strip stays intact across page turns.
- The search box supports Chinese autocomplete (same reverse-translation matching as the top bar, e.g. 「巨乳」). **Picking a suggestion stays on the tags page and filters the cloud** (switches to that namespace, queries by English name). Submitting Chinese also matches local tags via translations. The button is “Search tags”. The top-bar search still searches galleries and jumps to the library.
- Clicking a tag in the cloud appends it to the library filter (multi-tag AND); tags on detail pages can also be appended.
- In Chinese UI, tags display translations; multi-value tags display only the translated portion.
- Results are fixed at 100 items per page (API limit 500).

## Downloads (`#/downloads`)

- **Batch URL & GID/Token Enqueue**: Paste one or more gallery URLs or `gid/token` lines. **Enqueue pages** can override image quality; **Archive download** opens the same GP/tier preview as Favorites. Task titles follow the Title display setting (English/Japanese) instead of `gid xxx`.
- **Follow newer versions**: if ExHentai marks the listing as replaced, the download switches to the new gid (max 5 hops). Only the replacement link after the banner is followed — **Parent links are ignored**. 404/deleted galleries fail without retry, with plain-language errors in the list and Telegram. Gallery-detail “download original for this copy” does not follow.
- **Global pause**: the page toggle and Telegram `/pause` are the same switch
  (see Settings); **after pause, no new pages are claimed; the current in-flight
  page finishes**, claiming and scans stop; it survives restart; Bot matches the web
  pause. The yellow top bar stacks with the Cookie red bar.
- **GP & image quota**: the page header shows a cached GP balance and Image
  Limit (~30 min TTL); above ~80% the top banner warns you to pause (avoid 509).
- Lists download tasks with their status (waiting / downloading / success /
  failed / cancelled), filterable by status.
- A **channel badge** next to each task title marks how it downloads: archive
  tasks show "Archive · Original/Resample" (or "Fallback pages" if an archive
  failure falls back to page-by-page), plain H@H page-by-page downloads show
  "Page-by-page", so the two channels are easy to tell apart.
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
- **Clear all successful**: one click removes every `success` task record (the
  confirm dialog shows the count). This only clears the task list; **ingested
  gallery files are not deleted**. Failed, cancelled, and in-progress tasks are
  left alone.
- **A finished download is ingested into the index immediately** — the gallery
  row, pages and tags are written straight from the download result (cover
  thumbnail generated on first view), with **no full library scan**. The stored
  signature matches the scanner, so a later manual scan skips it.
- With Telegram configured, you get notified on download success/failure and
  scan completion; download notifications default to a **summary** digest (a
  bulk run collapses into one message), switchable to immediate / failures-only
  / off in Settings.

## Logs (`#/logs`)

Split into two tabs:

1. **Task Activity**: Displays background tasks (library scan, tag sync, thumbnail generation, favorites metadata sync):
   - **Running**: start time · task name · `running · done/total` · progress bar · description · **Cancel** button; multiple tasks run side by side.
   - **Finished**: start time · task name · status badge (success / failed / cancelled) · description & reason · **duration** · finish time; finished tasks no longer show a progress bar.
2. **System Logs**: Live diagnostic runtime logs from backend memory ring buffer:
   - **Dynamic log level**: Change runtime log level (`DEBUG` / `INFO` / `WARNING` / `ERROR`) on the fly without restarting containers;
   - **Real-time filtering & search**: Filter by minimum severity level (`INFO+`, `WARN+`, `ERROR+`) and instant text search;
    - **Exception tracebacks & context**: Expandable exception tracebacks, request IDs, worker correlation context (`gid` / `task_id`), and automated sensitive credential masking (`ipb_*` cookies, Telegram bot token, secrets);
    - **Export logs**: the **Export Log** button downloads `galleryvault.log` (ring buffer plus on-disk rotation via `GET /api/system/logs/download`) for sharing diagnostics;
    - **Noise filter**: successful httpx requests (2xx/3xx, including Telegram `getUpdates` 30s long-poll) are omitted; 4xx/5xx and business WARNING/ERROR (bot poll failures, notification send failures) are kept.

The page auto-refreshes every 2~3 seconds. The "Sync tags now / Generate now / Update translations now" buttons in Settings also leave a trace here.

> Tip: To inspect raw real-time container streams across Nginx, backend, and PostgreSQL side by side, see the [Deployment](Deployment) guide for an optional Dozzle configuration recipe.

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
- **Skip heuristic**: after several consecutive checks (5) report an unchanged
  folder count, the full re-scan is skipped (count-only checks continue) to
  avoid needless network traffic and missed-detection risk; the moment the
  count changes, full checks resume automatically.
- Click a folder name to open `#/favorites/<favcat>`: that folder's gallery
  grid (with **title search**, **multi-criteria sorting**, checkboxes, **select all**, **download selected**, **download selected original**,
  **archive download selected**, **move selected**, **remove from favorites**, and an
  **All / local only / cloud only** state filter). **Check now** warms cloud
  covers onto disk; opening a folder only reads that cache (`<img>` via
  `/api/favorites/cover`) and does not wait on ExHentai. The list uses numbered pagination with
  24 galleries per page by default.
  - **In-folder Search & Sorting**: Top toolbar provides instant title filtering and sorting by last seen, first seen, posted date, title, and size.
  - **Select all**: Inside a favorite folder (`#/favorites/:id`), the toolbar provides "Select All" to the left of "Clear Selection"; selection applies to currently rendered cards only (cards not yet loaded into DOM via infinite scroll are not selected), and clicking again after scrolling merges newly rendered cards into the selection.
  - **Move selected**: Move selected galleries to another favorite folder (0–9),
    syncing both ExHentai cloud favorites and local records.
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
  can be hidden with **Ignore selected**, and ignored items can be viewed and restored from
  the **Ignored items** page (`#/favorites/ignored`).
- **Gallery updates** (`#/updates`, linked from the top row of the Favorites
  page): when ExHentai **re-uploads** a gallery it moves it to a new gid and the
  favorites entry follows the new version, leaving the old-gid copy on disk.
  This page lists those "local copy is the old version" galleries (detected by
  "local gid not in any favorite folder, but normalized title matches a
  favorite item"), showing `old gid → new gid` per row. Check rows and hit
  **Update selected**: the new version downloads first, then the old local copy
  is removed (its reading progress resets). If an incremental/force favorites
  check **already downloaded the new gid**, detection deletes the old copy
  immediately (the row disappears) — no need to click Update selected.
  Enqueueing from favorites also pins any existing update row to that download
  task, and a successful ingest finalizes the same way. Detection runs
  automatically after every favorites check and can be triggered with **Scan
  now**; false positives can be ignored (ignored rows are never auto-deleted
  even if the new gid is already local), and ignored items are restored from
  `#/updates/ignored`.
  When a download task is deleted from the tasks page, its update entry is
  marked **failed** and kept here; under the **failed** filter you can use
  **Delete selected** to permanently remove those records (this only cleans the
  page's history, it never touches the tasks page).
- **Archive downloads (ExHentai official zip channel)**: the server packs the
  whole gallery into a zip (spending **GP**) and the client streams it on a
  single connection — far faster than per-page H@H fetches for large galleries.
  Three entries share one executor:
  - The **"Archive download selected" / "Archive update selected"** buttons in
    the `#/favorites/<favcat>` and `#/updates` toolbars open a **cost preview**
    first (read-only, never charges GP): the current GP balance on top, then a
    row per gallery with original/resample cost and size, tiers that cost more
    than the balance marked red. Pick a tier and confirm to enqueue. Original =
    full-resolution originals; Resample = the server's fixed one-level resample
    (the default tier — cheaper in GP and bandwidth).
  - **"Download selected original" / "Update selected original"** still download
    page-by-page but **force original quality** regardless of the global quality
    setting.
  - **Scheduled scan**: with "Archive large favorites on scheduled scan" and a
    **page threshold** enabled in Settings, automatic favorites checks send
    galleries over the threshold through the archive channel (using the
    "Archive quality" tier) and keep the rest page-by-page. Threshold 0 =
    everything archived.
  - Archive tasks occupy a `download_concurrency` slot and share the same
    FIFO queue as page-by-page tasks; if the same gid already has a pending task,
    the archive button reports a skip.
  - **Reliability**: the zip resumes via HTTP Range; `quality + zip URL` are
    persisted under `.gv-{gid}/.archive.json`, so a retry **only resumes — it
    never re-packs or re-charges GP**; a corrupt zip is deleted and re-packed;
    when the archive channel cannot serve the gallery (selected tier
    unavailable, insufficient GP, corrupt zip) the download **falls back to
    page-by-page by default** (no GP cost, H@H carries the traffic) — disable
    "Fall back to page-by-page if archive is unavailable" in Settings to fail
    the task immediately instead, without burning automatic retries.
    On completion the archive goes through the same finishing pipeline as
    page-by-page downloads: `.ehviewer` / `.galleryvault.json` metadata, Telegram
    notification, immediate ingest, and old-version cleanup for gallery updates.

### "download favorites" vs. "enabled"

- **download favorites** in Settings is the global **automatic scheduled check**
  master switch (checks by polling interval and downloads missing galleries).
- The **enabled** checkbox per folder on the Favorites page decides whether that
  folder takes part in the scheduled checks and whether it downloads during
  them (unchecked = record only, never download). New folders are disabled by default and require checking and saving.

For automatic downloads all three must hold: the master switch is on + the
folder is checked + the mode is "incremental/force download". A manual **Check
now** is not gated by the master switch, but an unchecked folder only records
even when checked manually.

With **"Archive large favorites on scheduled scan"** enabled, the scheduled check
batch-fetches page counts for its candidates first: galleries above the
**archive page threshold** (0 = all) go through the archive channel (tier =
"Archive quality"), the rest download page-by-page as usual. If the page-count
fetch fails, the check safely falls back to page-by-page. A gallery the archive
channel cannot serve (e.g. the selected tier does not exist) also automatically
falls back to page-by-page (Settings-toggleable).

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
  quality (normal/original), **archive quality** (default tier for archive
  downloads), **fall back to page-by-page if archive is unavailable** (on by
  default — a gallery the archive channel cannot serve downloads page-by-page,
  no GP cost), H@H network, `max_pages`. Slow-H@H-node watchdogs:
  **image max time** (seconds), **image slow warmup** (seconds) and **image min
  speed** (KB/s) — a single image is aborted once it exceeds the total
  wall-clock budget, or once it averages below the minimum throughput after the
  warm-up window, and is retried with backoff instead of holding the whole
  gallery hostage. The downloads group also carries **archive page threshold**
  (0 = all) and the **"archive large favorites on scheduled scan"** toggle.
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
  cookies, with a **Test login** button; cookies are never echoed back. A
  health probe runs at startup and every 30 minutes; expired cookies or no
  ExHentai access show distinct red top banners linking to Settings (also refreshed
  once right after login).
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
- **Disk usage**: the Settings page shows library / downloads / cache usage and the 10 largest galleries by DB `storage_size` (no `du` of the whole library). Missing directories report 0.
- **PWA**: add to home screen. The service worker caches only the html/css/js shell (js/css **network-first**, then update the cache; offline falls back to cache), **not gallery images or `/api/`**.
- **Light theme**: ◐ in the top bar; `localStorage gv_theme=dark|light`, default dark.
- **7z / PDF scan**: library scan accepts `.7z` (py7zr, images only) and `.pdf` (embedded images; skip with a warning if none).
- **OPDS**: after login, `GET /api/opds` (atom+xml) lists recent ingestions with acquisition links to `export.cbz`.
- **Telegram bot control commands** (send from an **allowed user ID**):
  `/help` lists commands, `/queue` shows a pending/running/failed summary,
  `/stats` library count plus queue pending/downloading/failed,
  `/cancel <id|gid>` cancels a task (replies when not found), and unknown
  non-URL text gets a help reply;
  `/pause` pauses intake (URLs pasted while paused are ignored, not enqueued),
  `/resume` re-enables intake, `/status` shows the pause state; `/pause` is a
  **global pause** (persisted to `app_config.user_settings`, survives
  restart): it **stops claiming new galleries and does not claim new pages**
  (the current in-flight page finishes; queued galleries are kept and resume
  later), and pauses **auto scans** and **Web-triggered scans** (trigger returns
  `paused`). The Web downloads page toggle and bot `/pause`/`/resume` operate
  **the same switch** (`GET/POST /api/pause`); after a web pause the Bot matches
  it, and the top yellow pause banner stacks with
  the Cookie red banner. **Pasting a gallery URL** (e.g.
  `https://exhentai.org/g/2325283/d3722b6aa8/`) parses the gid/token and
  enqueues it immediately. The bot reply includes the **gallery title** (and
  old→new gid if the listing was replaced; 404/deleted is reported and not queued).
- **Translation auto-update**: interval (minutes, 0 = off) and **Update now**.

## What needs the network

| Class | Operation | Note |
| --- | --- | --- |
| Fetches from ExHentai | 发现页搜索 | Fetches from ExHentai |
| Fetches from ExHentai | Popular | Fetches from ExHentai |
| Fetches from ExHentai | Watched | Fetches from ExHentai |
| Fetches from ExHentai | Toplist | Fetches from ExHentai |
| Fetches from ExHentai | 下载执行（gdata / 画廊页 / showpage / H@H） | Fetches from ExHentai |
| Fetches from ExHentai | 原图 fullimg.php | Fetches from ExHentai |
| Fetches from ExHentai | Archive archiver.php | Fetches from ExHentai |
| Fetches from ExHentai | Archive 预览+GP | Fetches from ExHentai |
| Fetches from ExHentai | 配额 home.php / exchange.php | Fetches from ExHentai |
| Fetches from ExHentai | Cookie 测试 | Fetches from ExHentai |
| Fetches from ExHentai | 收藏全量同步 favorites.php+gdata | Fetches from ExHentai |
| Fetches from ExHentai | 同步分类名 | Fetches from ExHentai |
| Fetches from ExHentai | 加入/移出/移动收藏与 Note（云端成功后写 DB） | 云端成功后写 DB，Fetches from ExHentai |
| Fetches from ExHentai | 未下载封面 | Fetches from ExHentai |
| Fetches from ExHentai | 标签同步按钮/worker | Fetches from ExHentai |
| Fetches from ExHentai | 分类 other 回填 | Fetches from ExHentai |
| Fetches from ExHentai | 画质回填 | Fetches from ExHentai |
| Fetches from ExHentai | EhTag 词库走 GitHub 非 EH | GitHub, not EH |
| Local only | 图库列表搜索 | Does not contact EH |
| Local only | 阅读器 | Does not contact EH |
| Local only | 缩略图 | Does not contact EH |
| Local only | 进度/历史 | Does not contact EH |
| Local only | 本地评分私有标签 | Does not contact EH |
| Local only | 导出 CBZ | Does not contact EH |
| Local only | 删除回收站 | Does not contact EH |
| Local only | 扫盘 | Does not contact EH |
| Local only | 版本更新页（本地对比） | 本地对比，Does not contact EH |
| Local only | 查重 | Does not contact EH |
| Local only | 书单 | Does not contact EH |
| Local only | 中文标签联想 | Does not contact EH |
| Local only | 日志 | Does not contact EH |
| Local only | 磁盘 | Does not contact EH |
| Local only | OPDS | Does not contact EH |
| Local first | 下载入队缺元数据才 gdata | 缺元数据才打远端 gdata |
| Local first | 详情页打开只读 DB | 只读本地 DB |
| Local first | 封面/分类计数/配额先缓存 | 优先读本地缓存 |
