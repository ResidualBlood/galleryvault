# Changelog

All notable changes to GalleryVault are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **ExHentai archive (zip) downloads** — a new download channel that uses GP
  instead of H@H page fetches for large galleries, with a per-task quality
  tier. Three entries share one executor (favorites download area / updates
  area / scheduled scan): `POST /api/archives/preview` shows funds + per-gallery
  original/resample cost & size (read-only, never charges GP), the favorites
  and updates toolbars gained "download original" and "archive download"
  buttons, and the scheduled scan can archive galleries over a page threshold.
  The zip streams on a single connection with Range resume; the requested
  quality + zip URL are persisted so a retry resumes without re-charging GP;
  insufficient GP fails the task immediately. Archive output reuses the standard
  metadata + notification + ingest + update-finalize pipeline. New settings:
  `archive_quality`, `favorites_archive_enabled`, `favorites_archive_max_pages`.
- **Per-task quality override (`download_tasks.quality`)** — the "download
  selected original" / "update selected original" buttons force original-quality
  page-by-page downloads regardless of the global `download_quality` setting;
  `POST /api/downloads` and the download queue accept an optional `quality`.

### Fixed

- **CI `pages` deploy on dev** — the `deploy` job now runs only on `main`;
  dev pushes still run `build` as a preview but no longer attempt to deploy,
  which the `github-pages` environment protection rules rejected with
  "Branch dev is not allowed to deploy to github-pages".

## [1.3.0] - 2026-08-30

### Added

- **GitHub Pages docs site (`docs-site/`)** — a VitePress site renders the
  canonical `docs/wiki/` pages into a website with a sidebar table of contents
  (中文 + English nav), deployed automatically by the `pages` workflow to
  https://hugo.lwnlh.com/galleryvault/. Canonical sources stay in
  `docs/wiki/`; the site is generated per build.
- **Canonical wiki source (`docs/wiki/`)** — the GitHub wiki pages now have a
  canonical, versioned copy in this repo (`docs/wiki/`). `scripts/sync-wiki.sh`
  and the new `sync-wiki` workflow mirror it to the wiki repository;
  `API.md` / `Development.md` / `openapi.json` remain owned by the `sync-docs`
  workflow.
- **Download-title setting (`download_title`)** — chooses which title seeds
  the on-disk download folder name (`<gid>-<title>`): `japanese` (default,
  Ehviewer-style) or `english`. Independent of the display `title_display`
  setting; a changed setting only affects newly downloaded folders.
- **Download folder reuse** — re-running a download now reuses the existing
  `<gid>-…` folder instead of deleting it and starting over, so a changed
  title no longer leaves a second orphaned copy on disk.
- **Long CJK titles can no longer overflow the filesystem limit** — download
  folder names are truncated to 255 UTF-8 bytes at a character boundary
  (previously 180 characters, which could exceed 255 bytes for Japanese text).
- **"Not in favorites" library filter** — the library page's category dropdown
  now offers "Not in favorites", showing local galleries whose gid is not in any
  ExHentai favorite folder (gid-less local archives count as not favorited).
  Pseudo-category `category=__not_fav__`; also honored by the filtered delete.
- **Gallery updates (`#/updates`)** — detects local galleries that ExHentai
  re-uploaded under a new gid (the favorites entry follows the new version, the
  old local copy stays behind). A local gallery whose gid is not favorited but
  whose normalized title matches a favorite item is listed with a check-box
  row showing `old gid → new gid`; selecting rows and hitting "Update selected"
  downloads the new version first, then removes the old local copy. Runs
  automatically after every favorites check and can be triggered manually.
  False positives can be ignored (like the duplicate-copy scan).

### Changed

- **Docs: Telegram `/pause` clarified.** The bot's `/pause` only gates new URL
  intake (URLs pasted while paused are ignored); already-queued and in-flight
  downloads are unaffected. The pause flag is not persisted (auto-resets on
  backend restart). Wiki `Usage` / `Usage-EN` updated accordingly.
- **Reader page images are cached by the browser for an hour.** The page-image
  endpoint (`/api/galleries/{id}/pages/{n}`) used to stream every image fresh
  on each request; it now sends `Cache-Control: public, max-age=3600` so back
  navigation and re-reads reuse the browser cache (thumbnails already had 24 h
  caching). Safe because galleries are read-only and page bytes never change.
- **Multi-word search matches each word independently.** A query such as
  `mimu gif` used to become a single contiguous `%mimu gif%` pattern, so a
  gallery whose title contains both words separately (or in the other order)
  was missed. Free-form text is now split on whitespace and every word must
  appear in the title (each as its own substring, anywhere); single-token and
  CJK-sentence searches behave as before.
- **Gallery detail opens at your reading position.** Without an explicit
  `?page=`, the page thumbnails now start on the pager page containing your
  last reading progress (instead of always page 1), so returning from the
  reader lands on the page you were viewing. An explicit `?page=` is still
  honored; the detail thumbnails keep their default of 30 per page.
- **Search no longer guesses tags from free-form text.** Typing an unrelated
  word used to be auto-promoted into a tag filter when it happened to match a
  local tag name (English) or a tag translation (Chinese), which could drop
  galleries whose titles contain the word but lack the tag. Free-form tokens
  now search titles only; a tag filter is applied only for explicit
  `ns:name` syntax, the tag cloud, or clicking a tag suggestion in the search
  box (which consumes the clicked word from the query).
- **Page size is remembered.** The "per page" selector now persists your
  choice in the browser and carries `page_size` through the gallery → reader
  → gallery round trip, instead of resetting to the default when you come
  back from reading.
- **Reader fullscreen is now image-only.** The fullscreen button (and the `F`
  key) now fullscreens the page image instead of the whole page: the image
  fills the screen (`object-fit: contain`, black background) and the toolbar
  and page navigation are hidden. While fullscreen, paging via `→`/`←`/space
  or clicking the image swaps the image in place instead of re-rendering the
  page (which would drop fullscreen); on the last/first page the reader exits
  fullscreen first. Pressing `Esc` restores the previous fit state and syncs
  the URL to the current page.
- **ExHentai login test now really verifies the session** — `POST
  /api/settings/exhentai/test` answers with meaningful HTTP status codes (200
  logged in, 400 no cookies configured, 401 cookie expired/invalid, 403 no
  exhentai access, 502 upstream failure) and classifies the home page by its
  login markers instead of treating any HTTP 200 as success. A transient
  anti-bot challenge is retried once before reporting a failure.

### Fixed

- **Equal-count favorite replacements are now detected.** The scheduled
  favorites poll skipped the full re-list whenever the cloud count matched the
  locally known gid count, so removing one favorite and adding another (count
  unchanged) was never caught. Consecutive skips are now counted per folder:
  the poll that would be the 5th consecutive skip forces a full re-list and
  resets the counter.
- **The Favorites page never blocks on a cold favorite-count fetch.** The
  first `_favorite_counts_cached()` call used to await ExHentai synchronously
  (up to 10s). The cache is now warmed asynchronously at startup and the first
  request returns immediately, with the real counts arriving via the
  background refresh.
- **A manual download retry resets the retry budget.** `max_retries` is
  restored to 10 on `POST /api/downloads/{id}/retry`, so a task that exhausted
  its automatic budget (`max_retries=0`) can be re-queued instead of staying
  stuck forever.
- **`check_login` no longer misreports an anti-bot challenge as a dead
  session.** ExHentai answers an empty body (no cookies / anti-bot challenge)
  with HTTP 200; `parse_login_state` previously classified it `not_logged_in`,
  prompting a pointless cookie reset. It now returns `failed` so the settings
  test shows "请求失败或反爬挑战" and the operator retries instead of
  re-entering cookies.
- **Telegram bot `/status` is no longer swallowed by the chat allowlist.** The
  real `TelegramNotifier` drops non-forced messages to chats that are not in
  `telegram_chat_ids`; `/pause`, `/resume` and gallery enqueue already passed
  `force=True` but `/status` did not, so an operator whose chat was only in
  `telegram_allowed_user_ids` got no reply. `/status` now forces its reply too.
- **Cloud favorite-removal failures now surface on the Logs page.** Previously
  `remove_favorites` sent every gid in one POST and raised on any non-2xx, so a
  partial failure left no trace of which gids failed. It now chunks requests
  (25/batch, ExHentai's cap), degrades a failed batch to per-gid retries, and
  returns the list of gids that could not be removed; the API response gains a
  `cloud_failed` field and the Logs entry appends `cloud remove failed N:
  gid1,…` with a `failed` status when any gid (cloud or local) fails.
- **Login rate limiting no longer trusts the socket peer, which a client could
  rewrite via `X-Forwarded-For` to rotate buckets and bypass the limit.** The
  bucket now keys on the `X-Real-IP` header — nginx unconditionally overwrites
  it with `$remote_addr`, so it cannot be spoofed through the proxy — and falls
  back to the socket peer only for direct (header-less) access.
  `forwarded-allow-ips` is narrowed to the private docker range
  (`172.16.0.0/12,127.0.0.1`) so only the proxy can rewrite forwarded headers.
- **Empty cached tags no longer wipe a gallery's local tags.** When the gdata
  metadata cache for a gallery had an empty `tags` list (stale or partial
  response), `apply_metadata_to_galleries` still ran the `delete(GalleryTag)`
  for every gallery in the batch, destroying tags that were already synced
  locally. The delete is now gated per-gallery on the cache actually carrying
  tags; galleries with empty cached tags keep their local tags while the rest
  of their metadata is still updated.
- **A cancel landing just as a download finished no longer races the success
  commit.** The cancel route flips the DB row to `cancelled` and arms the
  in-flight flag; if that landed between the last progress callback and the
  final commit, the old success branch either marked the task `success` or
  left a `success` attempt + an "ok" notification behind. The success branch
  now re-checks the row status and the flag inside its transaction and walks
  the shared cancel-cleanup path (temp dir, flag, no "ok" notification); the
  success path always consumes the in-flight flag so a late cancel can never
  leak into a later retry.
- **Galleries over ~10240 pages are no longer truncated.** The page-link
  enumeration fetched the first 512 gallery sub-pages concurrently, then
  walked a serial tail `range(start, 512)` — which was empty once `start`
  reached 512, so any gallery whose gdata `file_count` implied more than 512
  sub-pages silently dropped everything past that point. The serial tail now
  walks page-by-page until the first empty page (with a safety sentinel past
  the estimated page count).
- **Looking up a gallery by id/gid no longer 500s when the two collide.** A
  gallery is addressable by both its DB `id` and its ExHentai `gid`. When one
  gallery's `id` numerically equalled another gallery's `gid`, the old
  `OR`-combined `scalar_one_or_none()` lookup raised `MultipleResultsFound`
  (HTTP 500). The identifier lookups (`_gallery`, `get_by_identifier`,
  `get_for_tag_sync`) now query the primary key first and fall back to `gid`
  only on a miss.
- **Deleting a filter's results no longer breaks on huge libraries.** The
  library's "delete filtered" action used to resolve the whole filter into an
  id list on the client and POST it to `delete-bulk`, which could exceed
  asyncpg's ~32767 parameter limit when thousands of galleries matched. There
  is now a server-side `POST /api/galleries/delete-filtered` endpoint that
  pages the filter itself and deletes in 500-row batches; `delete-bulk` and
  the favorites-remove lookups also chunk their `in_` queries the same way.
- **ExHentai login test no longer false-negatives on a valid session** — the
  probe now requests the member-only `/uconfig.php` page and classifies the
  response body, because ExHentai answers every session state with HTTP 200
  and the public home page carries no login markers: a full page means logged
  in, ExHentai's own `expired login session` body (or an empty anti-bot
  response) means not logged in. A valid session is no longer reported as
  "cookie invalid or expired" while downloads with the same cookies succeed.
- **Manual retry now starts immediately** — retrying a failed/cancelled
  download clears the stale exponential-backoff timestamp, so the task is
  claimed right away instead of waiting out the previous backoff delay.
- **Deleting an in-flight download is safe** — deleting a downloading task now
  signals the running worker before removing its partial folder, instead of
  racing its writes (which could fail page writes and leave error noise).

## [1.2.15] - 2026-08-29

### Added

- **`title_display` now applies everywhere**. Cloud-only favorite items,
  favorites-duplicate groups and the duplicate-copies page used to always show
  the English/raw title; they now resolve the display title from the same
  `title_display` preference (Japanese / English / directory) as the library,
  gallery detail and local favorites. Duplicate-copy records carry the
  Japanese title too, so the page falls back to it after a re-scan.

### Fixed

- **Custom ExHentai base URL input was hidden by CSP**. The Settings / welcome
  "Custom" base-URL choice toggled a URL input via an inline `onchange`
  handler, which the nginx `Content-Security-Policy` (`script-src 'self'`)
  blocked — selecting Custom never revealed the input. The toggle now runs
  through the existing global change delegation, so proxy subdomains (e.g.
  `https://proxy.exhentai.org`) can be entered again.
- **Reader pagination keeps the library search filter**. Thumbnail links,
  prev/next buttons, keyboard/click paging and the next-gallery jump in the
  reader dropped the `q`/`tags`/`tag_mode`/`category` query string, so
  returning to the library after reading lost the active tag filter. All
  reader navigation hashes now carry the search context like the Read button
  already did.

## [1.2.14] - 2026-08-29

### Added

- **Open the original gallery on ExHentai**. The gallery detail page has an
  "Open on ExHentai" button that deep-links to `{base_url}/g/{gid}/{token}/`
  (built from the configured `exhentai_base_url`; hidden for local galleries
  without a token). The Settings/welcome forms now offer the base URL as a
  selector — ExHentai (里站) / E-Hentai (外站) / Custom with a fallback input
  for proxy subdomains — while saving the same `exhentai_base_url` field.
- **Smart search box: mixed tag + text queries**. The library search box now
  accepts free-form combos like `动图 中国` and splits them automatically:
  explicit `ns:name` tokens, Chinese words that map one-to-one onto a tag
  translation (e.g. `动图` → `misc:animated`), and English words that are exact
  tag names all become tag filters (AND), while the rest stays a title keyword.
  The API normalizes the query and the UI adopts the canonical `q`+`tags` form.
- **Multi-tag library search**. The library now supports filtering by several
  tags at once (all must match, `tag_mode=and`). Tag suggestions, tags on the
  gallery detail page and tags in the tag cloud all **append** to the active
  filter instead of replacing it; each active tag shows as a removable pill
  above the grid (per-pill × and a clear-all action). Resubmitting the title
  search keeps the current tag filter. The backend `/api/galleries` endpoint
  already accepted comma-separated `tags` — this change surfaces it in the UI.
- **Background work survives restarts**. Thumbnail generation and tag sync now
  run off a persistent job queue in the database instead of in-memory lists, so
  a container restart continues the remaining work instead of starting over.
  Download progress is persisted in batches too (at most every 20 pages / 5 s)
  instead of once per image, cutting database writes on long galleries by an
  order of magnitude — the Downloads page still shows live progress.
- **Downloads: pages-in-parallel is now a tunable setting**. `page_concurrency`
  (default 4, range 1–16) replaces the hardcoded 8. H@H nodes cap concurrent
  connections per source IP (~4–6), so a high value tripped the cap on lossy
  proxy paths and flooded logs with `ConnectError`; lowering it keeps downloads
  stable on any line. Exposed in the Settings page under Downloads.
- **Downloads: self-healing retries**. Failed tasks now re-enter the queue
  automatically with an exponential backoff (30s → 2m → 8m → 30m → 1h → …
  up to 6h) instead of dying after three attempts; the retry cap is raised to
  `max_retries` = 10 and only the missing pages are re-fetched. A periodic
  sweep re-activates older `failed` tasks that still have retry budget left,
  so the manual retry button is rarely needed. The per-task `retry_count`
  resets once a download succeeds.
- **Downloads: lazy per-page URL resolution**. Image URLs are no longer
  pre-fetched for the whole gallery in one go — every page resolves its own
  fresh keystamp URL right before downloading, and a `403` from an expired
  keystamp (H@H rejects stale signatures) is healed by re-resolving the page
  in place (up to 5 rounds, mirroring Ehviewer_CN_SXJ). Long galleries now
  download continuously instead of failing every 15–20 minutes when the
  batch of pre-signed URLs expired. Persistent failures still escalate to
  the task-level retry so galleries stay complete.

### Changed

- **Telegram bot now uses 30s long polling (was 1s short polling)** and the
  notifier client timeout is raised to 45s to match. `getUpdates` was hammering
  `api.telegram.org` about once per second, flooding logs with one line per
  poll (≈9k lines/6h in production); long polling cuts that to 1 request/30s
  and is gentler on Telegram's API.
- **httpx access logs are filtered down to failures only**. httpx logged one
  INFO line per HTTP request, so successful ExHentai page/`api.php` fetches,
  H@H image downloads and Telegram calls (all `2xx`) flooded stdout — ~96% of
  production log volume. A new `_HttpAccessFilter` in `logging.py` drops
  `2xx`/`3xx` httpx request logs while keeping `4xx`/`5xx` (e.g. H@H `403`
  keystamp misses) and all business WARNING/ERROR lines.
- **`/healthz` heartbeat access logs are silenced**. The docker healthcheck
  polls `/healthz` every ~10s, so uvicorn emitted one line per poll (~8.6k
  lines/day). The filter now drops those while keeping all other uvicorn
  access logs (real API traffic). The filter is attached both to the root
  handler (covers httpx/`galleryvault.*` loggers) **and** to the
  `uvicorn.access` logger itself, because uvicorn installs its own handler
  there with `propagate=False` — access-log records otherwise never reach the
  root handler's filter.
- **Slow-H@H-node watchdog defaults relaxed further** (`image_min_speed_kb_s`
  20 → 10) and the image transfer **read timeout is now 30s (was 15s) with a
  120s total budget**, so large GIFs / animated images survive a slow or
  hiccuping H@H node instead of aborting the whole gallery.

### Fixed

- **Public E-Hentai no longer misclassifies ExHentai-only galleries as
  deleted**. A gallery that only ExHentai exposes returns the same 404/empty
  page on e-hentai.org as a deleted one, which the tag-sync worker used to
  treat as a deletion — reclassifying the gallery as `deleted` and never
  retrying. On the public mirror the worker now suspends such galleries
  instead (category untouched) and switching the base URL back to
  `exhentai.org` in Settings resumes them automatically.
- **Returning from a searched gallery keeps the library filter**. Opening a
  gallery from the library grid carried no query, so the back-to-library link
  dumped you on the unfiltered library. Cover links now pass the active
  `q`/`tags`/`tag_mode`/`category` along, and the back link, Read button,
  thumbnail pager and the reader's back/all-pages links all preserve it.
- **Browse/library search buttons now say "Search"**. They used the library
  page label ("Library" / 画廊库), which read as a navigation button instead of
  the action it performs. The page heading and back-links keep the library
  label.
- **Downloads: `showpage` network errors are now wrapped as retryable
  failures**. A raw `httpx.ConnectTimeout`/`ReadTimeout` from the page-URL
  resolution API used to leak to the download worker as a cryptic
  `ConnectTimeout:` error and — worse — bypassed the 30s challenge backoff, so
  the retries fired back-to-back. Transport errors now surface as
  `EhClientError` (retryable with backoff) and reuse the existing HTML fallback.
- **Log context fields (e.g. `[error='ReadTimeout']`) now actually appear**. The
  `log_extra` helper built a nested `{"extra": {...}}` dict, which set
  `record.extra` instead of `record.context`; the log formatter never read it,
  so every structured field (`error`, `gid`, `page`, …) was silently dropped
  from all log lines. Fixed so failure diagnosis via `docker logs` works.
- **Settings: the "require login" (`auth_required`) toggle can now be saved**.
  `SettingsRequest` never declared the field, so pydantic silently dropped the
  submitted value and the Settings-page checkbox was dead UI since v1.0.0
  (defaults kept login always on, so it went unnoticed). The toggle now
  persists to `user_settings` and takes effect immediately.
- **Frontend proxy: the backend is now resolved over IPv4 only**. The compose
  network can carry IPv6 while the backend listens on IPv4 only (uvicorn
  `--host 0.0.0.0`); the nginx `proxy_pass http://backend:8001` resolved the
  service name once at startup and tried the container's IPv6 address first,
  failing until nginx fell back to IPv4. After every container upgrade/restart
  this produced a burst of `connect() failed` in the nginx logs and intermittent
  502s on the login page — which the SPA reported as "wrong password" even for
  a correct one, because `doLogin` never checks the `/login` response status
  (a failed POST means no session cookie, so the follow-up session check
  returns 401 and the UI shows the "wrong password" toast). The proxy now
  re-resolves the backend per request through Docker's DNS with
  `resolver 127.0.0.11 ipv6=off valid=5s` plus a variable `proxy_pass`, so it
  always uses the reachable IPv4 address.

## [1.2.13] - 2026-08-28

### Added

- **Slow H@H node watchdogs for image downloads**. New settings
  `image_download_timeout_seconds` (default 120), `image_slow_warmup_seconds`
  (default 10) and `image_min_speed_kb_s` (default 50). A single image is
  aborted once it exceeds the total wall-clock budget, or once it averages below
  the minimum throughput after the warm-up window — so a node that trickles a
  few KB/s no longer holds a download worker (and the whole gallery) hostage for
  many minutes. Aborted pages are retried through the existing per-page retry
  plus the persistent worker's 30s backoff, re-downloading only the failed page.
  ExHentai's `509.gif` rate-limit placeholder is now also detected by URL and
  treated as a retryable failure instead of being saved as a page.

### Fixed

- **Reader downloads large pages (e.g. animated WebP) up to ~500× faster**. Page
  images were streamed to the browser in the file's default 8KB buffer chunks,
  and each chunk crosses a threadpool boundary inside the streaming response —
  capping throughput near ~1MB/s. Pages are now read in 256KB chunks, removing
  the per-chunk overhead (measured ~466MB/s vs ~918KB/s on the same file).
  Small images are unaffected.

## [1.2.12] - 2026-08-28

### Changed

- **Telegram notifications are now language-selectable and consistently
  formatted**. A new `telegram_notify_lang` setting (中文 / English, default
  `zh`) drives the language of *all* automatic notifications — download
  success/failure/digest, library scan summary and failure, favorites folder
  checks, Telegram bot replies and the test message — instead of the previous
  mixed Chinese/English copy. Messages are sent with Telegram HTML formatting
  (bold titles, `<code>` gids, uniform emoji prefixes); gallery titles stay
  untranslated. The download digest keeps its 4096-character budget, now
  measured against the rendered text length.

## [1.2.11] - 2026-08-28

### Added

- **JHenTai download directories are scanned natively**: a new
  `JhentaiDirScanner` (storage type `jhentai_dir`) recognizes
  `jiangtian616/JHenTai` download folders — `<gid> - <title>/` with a `metadata`
  JSON — and restores the full gallery identity from it: gid, token, title,
  category, uploader, published time and tags. It is registered ahead of the
  bare-image-folder scanner so the richer metadata wins. Without the metadata
  the same folders already matched the bare scanner (gid inferred from the
  directory name only). **This support is new and not yet validated against
  much real-world data**.

### Docs

- **Favorites modes documented**: the docs (wiki Usage CN/EN, backend
  `docs/USAGE.md`, `docs/API.md`) now explain the difference between
  *incremental* / *watch only* / *force* folder modes, and how to pull down the
  backlog of an already-checked folder (incremental only follows new additions,
  so existing favorites need a one-time **force** check or **Download
  selected**).
- **Recommended workflow added**: README (CN/EN) quick start and wiki Home
  (CN/EN) now show the end-to-end flow — log in to ExHentai → read favorites
  in *watch only* mode (no downloads yet) → scan library → **deduplicate
  before downloading** → start with a *force* check to pull the backlog →
  switch to *incremental* + schedule.
- **Scope declared**: README (CN/EN) and wiki Home (CN/EN) now state the
  project's primary target — galleries downloaded by **Ehviewer_CN_SXJ** with
  a `.ehviewer` (SpiderInfo) metadata file — and list compatible EhViewer-family
  clients (FooIbar/EhViewer, Ehviewer-Overhauled, EhViewer-Apple,
  Ehviewer_OHOS, LRReader, …) plus the reduced-fidelity support for bare image
  folders and CBZ/CBR.

### Fixed

- **Library "Scan library" button works again**: the button on the Library page
  (and the "Scan again" button on the *Duplicate copies* page) silently did
  nothing — the `scanLibrary()` handler they call was removed during the Logs
  page refactor and never restored. Re-added the handler (it triggers
  `POST /api/scan`, shows a toast and refreshes the task logs); the first-run
  welcome wizard's scan button now shares the same code path.
- **Full scan crashed on batches of only gid-less galleries**: the ingest
  lookup built its WHERE clause as `False | column.in_(…)` when a batch had no
  galleries carrying an ExHentai gid (e.g. calibre CBZ exports), which raises
  `TypeError` and failed the whole batch. The condition is now assembled
  explicitly, so gid-less copies ingest correctly.
- **Password change did not actually revoke old sessions**: `change_password`
  rotated `auth_secret` in the database but never applied it to the running
  process (only the password hash was re-synced), so previously issued session
  cookies stayed valid until the next container restart. The new secret is now
  applied immediately and the current user receives a fresh session cookie, so
  their own change does not log them out while all other sessions die at once.
- **"Keep / Keep & delete" on the *Duplicate copies* page failed for paths
  containing an apostrophe**: the copy path was inserted into `data-path` via
  `encodeURIComponent`, which does not escape single quotes, truncating the
  attribute and making the buttons silently no-op. The raw path is now HTML-
  escaped and sent unencoded in the resolve request.
- **A download deleted mid-flight misreported as failed**: if the task row was
  removed while pages were downloading, the completion handler dereferenced
  `None` and logged the download as failed, skipping ingest and the Telegram
  notification even though the gallery was fully written to disk. It now skips
  the (now-orphaned) DB write but still ingests the completed gallery.

### Changed

- **Gallery detail page defaults to 30 thumbnails per page**: the page-size
  default on the gallery detail page is now 30 (was 24) and the per-page
  selector's `24` option became `30` (`PAGE_SIZES` = 5/30/50/100/200/500).
- **Favorites-check Telegram messages show the folder name**: notifications for
  a favorites check (summary, check-failed, per-gallery download-failed) now
  read `Favorites category 3 (folder name): …` when the folder has a name,
  falling back to the bare number otherwise.
- **"Unfavorite and delete downloaded" deletes every copy and reports failures**:
  the favorites dedup action now removes **all** physical copies of a gid across
  the scan roots (including duplicate-copy losers in `duplicate_records`), not
  just the DB row's own path. A gallery row is only deleted when every copy was
  removed successfully — a copy that cannot be deleted (e.g. a read-only mount,
  or an archive file) keeps the row so the next scan cannot resurrect the gallery
  as if it were fresh. Failed paths are reported in the toast **and** recorded on
  the Logs page (new `favorites-remove` / `gallery-delete` activity entries).
  Gallery-page delete and bulk delete share the same code path and now also
  delete single-file (CBZ/CBR) archives, which the previous directory-only
  removal never touched.
- **Library roots are no longer labeled "read-only"**: the Settings label and
  hint were updated, since deletion now removes files under a library root when
  the mount is writable (a read-only mount reports the failure instead of
  silently succeeding). New downloads still never land in library roots.

## [1.2.10] - 2026-08-27

### Added

- **Scan completion Telegram notification reports duplicate copies**: the
  message now appends `N duplicate-copy group(s) found (gid …)` when a scan
  detects the same gallery under more than one scan root, pointing the operator
  at the *Duplicate copies* page. `GET /api/scan` exposes `duplicate_gids`.

### Fixed

- **Scan counters no longer double-count skipped galleries**: a full scan of an
  unchanged library reported `skipped ≈ 2 × galleries` because already-ingested
  single copies were counted in both scan phases. They are now counted once.

## [1.2.9] - 2026-08-27

### Added

- **Duplicate-copy resolution on library scans**: when the same gallery (same
  gid) exists under more than one scan root (an EhViewer download directory, a
  CBZ archive, a manual copy), the scan now collects every copy, picks a winner
  per the new `duplicate_policy` setting and records the rest for review.
  Previously the DB row was silently re-pointed at whichever copy happened to be
  scanned last.
  - `duplicate_policy` (Settings): `keep_first` (default — the already-stored
    copy wins), `prefer_more_pages`, `prefer_newer`, `prefer_larger`,
    `prefer_smaller`, or `manual` (never auto-resolve).
  - New **Duplicate copies** page (`#/duplicates`): lists every physical copy of
    a duplicated gid with cover thumbnail, tags, page count, size and posted
    date, and lets you keep one copy, keep & delete the other copies from disk,
    or dismiss the group (restorable). A scan refreshes the list.
  - Persisted in a new `duplicate_records` table; only gid-bearing copies
    participate (a CBZ whose ExHentai id lives in an external sidecar still
    needs that metadata wired up — see backend roadmap).

## [1.2.8] - 2026-08-27

### Fixed

- **Telegram digest is no longer split during active batches**: the 60-second
  fallback timer used to flush a partial digest while a download batch was still
  running (e.g. "2 completed" mid-batch). It now only flushes buffers that have
  received no new events for the interval, so a bulk run still collapses into a
  single summary when the queue goes idle.
- **Settings re-validation**: merged user settings are now re-validated instead
  of copied with `model_copy`, which skipped pydantic validation. Without
  `ENCRYPTION_KEY`, ExHentai cookies are stored as a plaintext JSON string that
  used to survive loading as a string and crash the backend at startup after
  any settings save.

## [1.2.7] - 2026-08-27

### Changed

- **Telegram download notifications are now a digest by default**: a bulk
  download used to fire one message per gallery success/failure. A new
  `telegram_notify_level` setting (`summary` / `immediate` / `failures_only` /
  `off`, default `summary`) controls this. In `summary` mode terminal download
  events are buffered and flushed as a single "download summary" message as
  soon as the download queue is idle (60s timer + 50-event buffer cap as
  fallbacks); `immediate` keeps the old per-event behaviour; `failures_only`
  sends only final failures; `off` disables automatic notifications while
  keeping the test button and interactive bot. Only final (non-retryable)
  download failures are reported. Scan and favorites notifications are
  unchanged.

## [1.2.6] - 2026-08-27

### Fixed

- **Telegram auto-notifications were silently dropped**: `send_message` required
  an explicit `chat_id`, so the automatic notifications for download success /
  failure and library-scan completion (which don't pass one) were rejected as
  "chat is not allowed" and never delivered. When no `chat_id` is given the
  message now fans out to **every** configured `telegram_chat_ids` chat; the
  "test message" button and the interactive bot behaviour are unchanged.

## [1.2.5] - 2026-08-26

### Changed

- **Smaller backend image**: dropped the never-used `uvicorn[standard]` extras
  (uvloop/httptools/watchfiles/websockets/PyYAML are not imported anywhere),
  trimmed the idle/tk stdlib modules and bytecode caches. The image is roughly
  25MB smaller while remaining a single-stage build for `linux/amd64` and
  `linux/arm64`.

## [1.2.4] - 2026-08-26

### Fixed

- **CSRF origin check accepts IPv6 hosts**: the middleware compared the
  `Origin` hostname against the `Host` header using `split(":", 1)[0]`, which
  splits inside an IPv6 literal — accessing the UI over IPv6
  (e.g. `http://[240e:...]:8000`) rejected every write API call
  (`DELETE`/`POST`/`PUT`) with `Cross-origin request rejected` (403). The Host
  header is now parsed with `urlparse`, so IPv6, IPv4 and hostname origins all
  match correctly.

## [1.2.3] - 2026-08-26

### Fixed

- **Transient ExHentai challenge backoff no longer holds a database
  connection**: the 30s pause before retrying a rate-challenged / reset
  download used to run *inside* the status-update transaction, pinning a
  connection-pool slot and the task row's lock for 30s. With concurrent
  download failures this could exhaust the pool; the backoff now happens after
  the transaction commits.
- **Favorites folder rows are pruned when galleries leave the cloud folder**:
  a successful full check now removes `favorite_items` rows for gids that were
  unfavorited or expunged (they vanish from the ExHentai listing). Previously
  those rows accumulated forever — the scheduled "cloud count unchanged → skip
  re-list" heuristic stopped firing (every poll re-walked the folder) and
  phantom cloud-only items lingered in lists.
- **Favorites metadata-sync progress resets per run**: `total`/`done`/`applied`
  counters accumulated across folders and invocations; the first sync of a
  batch now starts them from zero so the Logs page shows the current run.
- Removed a dead duplicate `return` in the tag-sync enqueue helper.
- `/api/favorites/cover` reads the cached cover file once instead of twice.
- **CI**: the backend image build now waits for the gitleaks secrets-scan job
  before pushing to Docker Hub (previously only the test job gated it).

## [1.2.2] - 2026-08-26

### Added

- **Incremental download ingest**: when a download finishes, the gallery is
  written into the database directly from the download result (title, category,
  tags, token and page facts) — no full library scan, no extra ExHentai fetch.
  The stored storage signature matches the library scanner's fingerprint, so a
  later full scan skips it instead of re-ingesting. The gallery's cover
  thumbnail is queued for background generation (and always generated on
  demand when first viewed).

## [1.2.1] - 2026-08-26

### Added

- **Favorites local/cloud filter**: folder lists can filter by `state=all|local|cloud` (only local, only cloud, or everything).
- **「下载缺失项目」button** on the favorites overview (`POST /api/favorites/download-missing`): spawns a per-folder pass that downloads cover files for every gallery missing one on disk.
- **Cover thumbnails captured from the favorites listing** (migration 0018 `favorite_items.thumb`): `fetch_favorites` parses each gallery's cover thumb URL straight from the glthumb cell, so a folder check warms covers, tags and sizes together without a gdata round-trip.

### Fixed

- **Favorites covers actually appear now**: the thumbnail was parsed from the title link's label (which never contains an `<img>`), so `favorite_items.thumb` was always empty and the cover-heal never downloaded anything. It now parses the separate glthumb `<a><img>` per page and looks up by gid.
- **Production favorites checks silently no-op'd**: the deployed compose never configured ExHentai cookies, so `favorites.php` 302'd to the home page. Configure the cookies in **Settings → ExHentai** (stored encrypted in PostgreSQL via `ENCRYPTION_KEY`); the compose file should **not** set `EXHENTAI_COOKIES`.
- **Favorites listing tag garbage**: cloud-item tags now render namespace/name correctly instead of raw gdata strings.

### Changed

- **Pagination**: the aggressive infinite scroll now applies only to the **gallery library** page; every other gallery list (tags browse, favorite folders) returns to numbered-page pagination with a default of **24 galleries per page** (`PAGE_SIZES` = 5/24/50/100/200/500).
- **Tag chips clamped to two lines** in cards so long tag lists no longer blow up card heights.

## [1.2.0] - 2026-08-26

### Added

- **Download speed + ETA** on the Downloads page (live bytes/s and estimated
  time remaining for active tasks, computed from the downloader's byte stats).
- **Reader fullscreen & fit-to-width**: toggle with a button or the `F` key.
- **Infinite scroll** on the library and favorite-folder grids (an
  IntersectionObserver appends later pages as you scroll; the server-side
  pager stays as a fallback).
- **pg_trgm GIN indexes** on `galleries.title`/`title_jpn` (migration 0015) so
  leading-wildcard `ILIKE` search stays index-assisted at 100k+ gallery scale.

### Changed

- **Page resolution via the `showpage` API** (mirroring Ehviewer_CN_SXJ): after
  the first viewer page yields a `showkey`, remaining page URLs are resolved
  with one lightweight `api.php` POST each, falling back to full HTML on any
  failure. Less bandwidth, more robust to HTML changes.
- **Gallery sub-pages are enumerated concurrently**: the `?p=N` walk is sized
  with the gdata `filecount` and fetched in parallel, with a sequential tail
  for stale counts. Sample downloads (`max_pages`) now resolve only the pages
  they need.
- **Favorites scheduled polls skip the full re-list** when the cloud folder
  count matches the locally recorded count from the last successful check —
  a multi-thousand-item folder no longer re-walks every favorites page.
- **Anti-hijack guard on image downloads**: responses landing outside
  ExHentai's CDN/infra (hath.network / ehgt.org / exhentai.org) are rejected.

### Fixed

- **`.ehviewer` pTokens were empty on every download** — the viewer URL parser
  did not match the current `/s/<pToken>/<gid>-<page>` format, so Ehviewer
  could not resume/preview downloaded galleries offline. Real pTokens are now
  extracted and written.
- **Image downloads stalled up to 60s** on a dead H@H node: a read-idle
  watchdog (15s without bytes) aborts and retries; `Content-Length` is now
  verified so truncated pages are re-fetched instead of written corrupt.
- **Retry hammering during ExHentai IP challenges**: connection resets and
  other transient transport failures now back off 30s before retrying (only
  the text `challenge` triggered backoff before), and `_get` wraps body reads
  so a reset surfaces as a retryable error instead of a raw exception.
- **Preview metadata**: `.ehviewer` now writes real `previewPages`/
  `previewPerPage` (20 per gallery page) instead of `1/1`.

## [1.1.0] - 2026-08-26

### Added

- First-run welcome wizard (`#/welcome`): guided change-password → ExHentai
  cookies → fill-the-library steps, shown while the default password is in use.
  New endpoint `GET /api/onboarding/status`.
- `POST /api/favorites/download-selected`: batch-enqueue downloads for selected
  favorite gids straight from the database (the SPA no longer pages through the
  whole folder).
- Official GitHub Wiki as the documentation site, with a bilingual (EN/中文)
  sidebar and an auto-synced OpenAPI schema.

### Changed

- **Favorites reads are database-first.** After a favorites check warms the
  `gallery_metadata` cache (and cover files land on disk), browsing a folder,
  viewing ignored duplicates and the duplicate-scan enrichment talk to the
  database only — ExHentai is only contacted for gids that were never cached.
- Tag sync now **waits for a running favorites check**: galleries whose
  metadata cache entry isn't populated yet are re-queued and retried (bounded,
  so non-favorites galleries still sync) instead of doing a redundant
  one-by-one ExHentai fetch that the gdata batch is about to cover.
- Remote covers fall back to the on-disk cache even when no thumb URL is
  available, so DB-cached galleries keep their covers without a fetch.

### Fixed

- Remote covers (and thumbnails) failed to cache for the unprivileged app user:
  legacy root-owned `/gv-cache` subdirectories were not writable, so ExHentai
  cover downloads were silently swallowed and cloud galleries showed no cover.
  The entrypoint now chowns the cache tree recursively and cover write errors
  are logged instead of swallowed.

## [1.0.0] - 2026-08-26

First tagged release. GalleryVault is a feature-complete, self-hosted local
gallery library manager with ExHentai integration.

### Added

- Local gallery library: scan Ehviewer export directories, CBZ/CBR archives and
  plain image folders into a persistent, searchable PostgreSQL index.
- Namespaced tag system with a frequency-weighted tag cloud and instant tag
  autocomplete.
- Tag translation via the EhTagTranslation database, including reverse matching
  from Chinese input (typing 巨乳 suggests `big breasts`).
- Full English / Chinese bilingual UI; translations shown for tags in the
  Chinese view.
- ExHentai integration: fetch metadata, categories and tags using your own
  cookies (`ipb_member_id` / `ipb_pass_hash` / `igneous`), HTTP or SOCKS5 proxy.
- Download manager: Ehviewer-style concurrent page downloads, live progress,
  resumable retries, partial downloads (`max_pages`), cancel and bulk retry.
- Favorites monitor: watches the ten ExHentai favorite folders and
  auto-downloads missing galleries (scheduled or on demand), plus per-folder
  grids, duplicate scan with ignore/restore, and metadata caching via the gdata
  API that is reused during library scans.
- Reader with streaming page loads, keyboard/space/click paging, preloading,
  auto-advance to the next gallery and saved reading position; browsable history.
- Activity log page aggregating background tasks (scan, tag sync, thumbnail
  generation, favorites metadata) with running/finished sections.
- Telegram notifications for downloads, scans and favorite sync.
- One-command deployment: two multi-arch (amd64/arm64) Docker Hub images plus
  PostgreSQL with a single `docker compose up`.
- Security: PBKDF2-SHA256 auth with persistent sessions, login rate limiting
  keyed on the real client IP, cross-origin checks, ExHentai domain whitelist,
  optional non-root runtime, and optional at-rest encryption (`ENCRYPTION_KEY`,
  AES-256-GCM) protecting cookies / bot token / password hashes with automatic
  plaintext migration on startup.
- Documentation site as a GitHub Wiki (deployment, usage, backup, encryption,
  API reference, development, FAQ), kept in sync with the backend docs.

[Unreleased]: https://github.com/ResidualBlood/galleryvault/compare/v1.2.15...HEAD
[1.2.15]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.15
[1.2.14]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.14
[1.2.13]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.13
[1.2.12]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.12
[1.2.11]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.11
[1.2.10]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.10
[1.2.9]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.9
[1.2.8]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.8
[1.2.7]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.7
[1.2.6]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.6
[1.2.5]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.5
[1.2.4]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.4
[1.2.3]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.3
[1.2.2]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.2
[1.2.1]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.1
[1.2.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.0
[1.1.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.1.0
[1.0.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.0.0
