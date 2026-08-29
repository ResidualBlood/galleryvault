# Changelog

All notable changes to GalleryVault are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
  access logs (real API traffic).
- **Slow-H@H-node watchdog defaults relaxed further** (`image_min_speed_kb_s`
  20 → 10) and the image transfer **read timeout is now 30s (was 15s) with a
  120s total budget**, so large GIFs / animated images survive a slow or
  hiccuping H@H node instead of aborting the whole gallery.

### Fixed

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

[Unreleased]: https://github.com/ResidualBlood/galleryvault/compare/v1.2.13...HEAD
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
