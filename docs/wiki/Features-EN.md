# Features

> [中文](Features) · English

This document provides a comprehensive overview of GalleryVault's feature set and architecture highlights.

## Local gallery library

- **Scan** — Scans Ehviewer export directories, CBZ/CBR/7z/PDF archives, and plain image folders into a persistent, searchable PostgreSQL index. `.7z` extracts image suffixes only.
- **Format fidelity** — `<gid>-<title>/` + `.ehviewer` (SpiderInfo V1/V2), JHenTai `metadata` JSON, and CBZ/CBR (+ ComicInfo.xml) restore full gallery identity; galleries without a gid can be browsed but take no part in downloads or dedupe.
- **Local lists / stars / notes** — Independent of EH; gid-less CBZ archives can join lists; library can filter by local list and star rating.
- **Duplicate-copy cleanup** — When the same gid appears under several scan roots, a `duplicate_policy` (keep-stored / more pages / newer / larger / smaller / manual) keeps one copy automatically and lists every other copy on the *Duplicate copies* page.
- **Title display** — `japanese` / `english` / `directory` settings drive the whole UI; downloaded folder names follow the independent *Download title* setting.

## Search & tags

- **Multi-tag & mixed search** — Clicking tags (suggestions / detail page / tag cloud) stacks AND/OR filters; exclude `-tag`; search box accepts `动图 中国` combos and `ns:name` syntax, tags are opt-in (click a suggestion), and Enter runs a plain title search (multi-word AND).
- **Library filters** — Sort by ingest / posted / title / pages / size / rating; filter by read status, page/size/posted/uploader/quality/language, local stars and lists; saved searches; Shift-click a card tag to exclude.
- **Tag translations** — Pulls the latest EhTagTranslation database; Chinese input reverse-matches (typing 巨乳 suggests `big breasts`); tags page search box uses the same Chinese autocomplete.
- **Bilingual UI** — English / 中文, switchable at any time; tags show their translations in the Chinese view.
- **Tag cloud** — Namespace groups (Tag / Artist / Character / Parody / Group / Female / Male / Language), size weighted by usage.

## ExHentai integration

- **Metadata sync** — Fetches metadata / categories / tags with your own cookies; a gdata batch cache is reused by scans and favorites.
- **Public-mirror safe** — With `e-hentai.org` configured, ExHentai-only galleries *pause* tag sync (never misclassified as deleted) and resume when the base URL switches back.
- **Favorites monitor & management** — Watches the ten folders (incremental / watch-only / force modes), auto-downloads missing galleries, per-folder lists, skip heuristic to save bandwidth, and duplicate scan with ignore/restore; detail and library pages can add/move favorites (cloud-first).
- **Gallery updates** (`#/updates`) — Detects local copies of galleries that ExHentai has re-uploaded (a new gid); one click downloads the new version and deletes the old local copy. If the new gid is already in the library, detection finalizes automatically.
- **Open on ExHentai** — A one-click link to the original gallery from the detail page (built from configured base URL).
- **Cookie health** — Startup and periodic probes; expired cookies or no ExHentai access show distinct red top banners linking to Settings.
- **Discover** (`#/discover`) — Search/browse ExHentai in the Web UI (including Popular / Watched / Toplist); one-click download or add-to-favorites (cloud-success only).

## Download manager

- **Ehviewer-style downloads** — Concurrent page downloads, live progress, resumable retries (missing pages only), partial downloads (`max_pages`), cancel and bulk retry; paste URL/`gid/token` on the downloads page (pages or archive) and follow newer versions when ExHentai replaced the listing.
- **Archive downloads (ExHentai zip)** — Official whole-gallery zip channel: spend GP for big galleries, per-task quality override (original/resample), single-connection streaming with Range resume, retries never re-charge GP, and a read-only GP cost preview dialog.
- **Global pause & quota** — Pause persists (same switch on Web and bot); downloads page shows GP and image quota (~30 min cache).
- **Slow-node watchdog** — Per-image total-time budget + warm-up window + minimum speed; a sluggish H@H node no longer holds a whole gallery hostage.
- **Self-healing failures** — Transient errors re-queue with **exponential backoff** (30s → 6h, up to 10 attempts); periodic sweep re-activates failed tasks that still have retry budget.
- **Instant ingestion** — Finished downloads are written into the index (tags and cover included), no full scan; existing download folders are reused.
- **Telegram & in-app notifications** — Download/scan/favorites notices (summary / immediate / failures-only / off); bot commands (`/help`, `/queue`, `/cancel`, `/stats`, `/pause`, `/resume`, `/status`), paste a URL to enqueue. Top-bar bell works without Telegram.

## Reader & UI

- **Reader** — One-page streaming, LTR / RTL manga / double-page / **webtoon**, keyboard/space/click paging, `G` to jump, three-page preload, auto-advance after the last page, fullscreen and fit modes, saved reading position.
- **Browse & history** — Newest-gallery browse, **Continue reading**, top-bar search, reading history, activity log, first-run wizard.
- **Recycle bin & missing pages** — User-deleted / scan-missing galleries are restorable; integrity check re-downloads missing pages.
- **PWA / light theme / CBZ export / OPDS** — Add to home screen caches UI shell only; detail page can export CBZ; OPDS (`GET /api/opds`) and CBZ export (`GET /api/galleries/{id}/export.cbz`) support HTTP Basic authentication (username `galleryvault`, password is web login password; failed attempts return 401 with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`; Cookie remains supported). Other `/api/*` routes remain cookie-only.

## Security & operations

- **Security** — PBKDF2 auth, login rate limiting, cross-origin checks and domain whitelist, password change revokes every session; backend runs as root by default or drops privileges with `PUID`/`PGID`; optional **encryption at rest** (`ENCRYPTION_KEY`, AES-256-GCM).
- **Proxy** — HTTP or SOCKS5 (pick one), used for ExHentai access, downloads and translation updates.
- **One-command deployment** — Two Docker Hub images plus PostgreSQL with a single `docker compose up`; automatic migrations on upgrade and `scripts/backup.sh` for backups.
