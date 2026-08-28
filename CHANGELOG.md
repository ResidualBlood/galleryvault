# Changelog

All notable changes to GalleryVault are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed

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

[Unreleased]: https://github.com/ResidualBlood/galleryvault/compare/v1.2.3...HEAD
[1.2.3]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.3
[1.2.2]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.2
[1.2.1]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.1
[1.2.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.0
[1.1.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.1.0
[1.0.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.0.0
