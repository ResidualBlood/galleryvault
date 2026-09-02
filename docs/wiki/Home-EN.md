# GalleryVault (English)

GalleryVault is a private, self-hosted library manager for local gallery
archives. It indexes Ehviewer exports, CBZ/CBR archives and plain image folders
into a searchable web library, and can optionally sync tags and metadata from
ExHentai, download galleries, monitor favorite folders, and translate every tag.
The interface is available in English and Chinese (中文).

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

Open **http://<host>:8000**, log in with the default password **`p1a2s3s4`**
and change it in *Settings*. Configure your ExHentai cookies, run
*Favorites → Check all folders* once, put your galleries in `./library` and hit
*Scan library*.

### Recommended workflow

1. **Log in to ExHentai**: Settings → ExHentai, fill in `ipb_member_id` /
   `ipb_pass_hash` / `igneous` and verify with *Test login* (cookies are stored
   encrypted, never in the compose file).
2. **Read your favorites without downloading**: set the folder mode to *watch
   only* on the Favorites page, then run *Sync folder names* and *Check all
   folders* — metadata (title, tags, cover, size) is cached and the favorite
   set recorded, but **nothing is downloaded**.
3. **Scan the library**: put existing galleries under a library root and hit
   *Scan library*; the metadata cache from step 2 is reused.
4. **Deduplicate first**: group versions of the same work with *Manage
   favorites → Scan for duplicates* (cloud and local items are compared
   together, so duplicates can be unfavorited/ignored before downloading);
   clean up same-gid copies across scan roots on the *Duplicate copies* page.
5. **Start downloading**: switch the folder mode to *force* and run *Check
   now* — every folder gallery **not in the local library** is queued once
   (already-local galleries are skipped).
6. **Switch to incremental + schedule**: once the backlog is down, switch the
   mode back to *incremental* and turn on the **download favorites** master
   switch with an interval (e.g. 10 minutes); newly favorited galleries
   download automatically.

### Scope

GalleryVault is built **primarily for galleries downloaded by
[Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)**: a
`<gid>-<title>/` image folder plus a **`.ehviewer`** metadata file (SpiderInfo
VERSION1/VERSION2 with the gid/token and a per-page pToken), which the scanner
parses to restore the gallery identity exactly.

The `.ehviewer` format originates from Hippo Seven's EhViewer
(`com.hippo.ehviewer.spider.SpiderInfo`), so **any EhViewer-family client
writes a compatible file** and can be ingested directly:

- **Original EhViewer** ([seven332/EhViewer](https://github.com/seven332/EhViewer),
  deprecated); current active branches
  [**FooIbar/EhViewer**](https://github.com/FooIbar/EhViewer) (Material Design 3),
  [**Ehviewer-Overhauled/Ehviewer**](https://github.com/Ehviewer-Overhauled/Ehviewer),
  [**EhViewer-NekoInverter/EhViewer**](https://github.com/EhViewer-NekoInverter/EhViewer),
  [**exzhawk/EhViewer**](https://github.com/exzhawk/EhViewer),
  [**AdNotFound/EhViewer**](https://github.com/AdNotFound/EhViewer),
  [**WarnError/Ehviewer-NekoWhite**](https://github.com/WarnError/Ehviewer-NekoWhite),
  [**NotFaceGUI/EhViewer-Auto-Translation-Ver**](https://github.com/NotFaceGUI/EhViewer-Auto-Translation-Ver),
  [**axlecho/MHViewer**](https://github.com/axlecho/MHViewer) and other forks.
- Cross-platform ports: [**EhViewer-Apple**](https://github.com/felixchaos/EhViewer-Apple)
  (iOS/macOS), [**Ehviewer_OHOS**](https://github.com/suibianqwe/Ehviewer_OHOS)
  (HarmonyOS).
- Companion tools: [**LRReader**](https://github.com/Xslx98/LRReader) (Android,
  a LANraragi client), [**exhentai-manga-manager**](https://github.com/SchneeHertz/exhentai-manga-manager),
  [**ehviewer_manga_manager**](https://github.com/Schweik7/ehviewer_manga_manager)
  (Python CLI), [**LANraragi**](https://github.com/Difegue/LANraragi)'s
  `Ehviewer.pm` metadata plugin.

Other formats:

- **[JHenTai](https://github.com/jiangtian616/JHenTai)** (cross-platform Flutter,
  Android/iOS/Windows/macOS/Linux) download directories are **natively
  supported**: `<gid> - <title>/` plus a `metadata` JSON, so the full gallery
  identity (gid/token/tags/category/published time) is restored on scan.
  **This support is new and not yet validated against much real data** — please
  file an issue with a sample `metadata` file if you hit a parsing problem.
- Reduced fidelity: plain image folders named `<gid>-<title>` **without** an
  `.ehviewer` file and **CBZ/CBR** archives (gid must prefix the file name).
  Galleries without a gid can be browsed but **cannot take part in downloads,
  dedupe or duplicate-copy resolution**.

## Features

**Local gallery library**

- **Scan** Ehviewer export directories, CBZ/CBR archives and plain image
  folders into a persistent, searchable index (PostgreSQL).
- **Format fidelity** — `<gid>-<title>/` + `.ehviewer` (SpiderInfo V1/V2),
  JHenTai `metadata` JSON and CBZ/CBR (+ ComicInfo.xml) all restore the full
  gallery identity; galleries without a gid can be browsed but take no part in
  downloads or dedupe.
- **Duplicate-copy cleanup** — when the same gid appears under several scan
  roots, a `duplicate_policy` (keep-stored / more pages / newer / larger /
  smaller / manual) keeps one copy automatically and lists every other copy on
  a *Duplicate copies* page (keep / keep-and-delete / dismiss).
- **Title display** — `japanese` / `english` / `directory` drives the whole
  UI; downloaded folder names follow the separate *Download title* setting.

**Search & tags**

- **Multi-tag & mixed search** — clicking tags (suggestions / detail page /
  tag cloud) stacks AND/OR filters; exclude `-tag`; the box accepts `动图 中国`
  combos and `ns:name` syntax, tags are opt-in (click a suggestion), and Enter
  runs a plain title search (multi-word = every word must match).
- **Library filters** — sort by ingest / posted / title / pages / size /
  rating; filter by read status, page range and minimum rating; Shift-click a
  card tag to exclude it.
- **Tag translations** — pulls the latest EhTagTranslation database; Chinese
  input reverse-matches (typing 巨乳 suggests `big breasts`); the tags-page
  search box uses the same Chinese autocomplete.
- **Bilingual UI** — English / 中文, switchable at any time; tags show their
  translations in the Chinese view.
- **Tag cloud** — namespace groups (Tag / Artist / Character / Parody / Group
  / Female / Male / Language), size weighted by usage.

**ExHentai integration**

- **Metadata sync** — fetch metadata / categories / tags with your own
  cookies; a gdata batch cache is reused by scans and favorites.
- **Public-mirror safe** — with `e-hentai.org` configured, ExHentai-only
  galleries *pause* tag sync (never misclassified as deleted) and resume when
  the base URL switches back.
- **Favorites monitor & management** — watches the ten folders (incremental /
  watch-only / force modes), auto-downloads missing galleries, per-folder
  lists, a skip heuristic to save bandwidth, and duplicate scan with
  ignore/restore; detail and library pages can add/move favorites (cloud-first).
- **Gallery updates** (`#/updates`) — detects local copies of galleries that
  ExHentai has re-uploaded (a new gid); one click downloads the new version and
  deletes the old local copy. If the new gid is already in the library,
  detection finalizes automatically.
- **Open on ExHentai** — a one-click link to the original gallery from the
  detail page (built from the configured base URL).
- **Cookie health** — startup and periodic probes; expired cookies or no
  ExHentai access show a red top banner linking to Settings.

**Download manager**

- **Ehviewer-style downloads** — concurrent page downloads, live progress,
  resumable retries (missing pages only), partial downloads (`max_pages`),
  cancel and bulk retry; paste URL/`gid/token` on the downloads page (pages or
  archive) and follow newer versions when ExHentai replaced the listing.
- **Archive downloads (ExHentai zip)** — the official whole-gallery zip
  channel: spend GP for big galleries, per-task quality override
  (original/resample), single-connection streaming with Range resume, retries
  never re-charge GP, and a read-only GP cost preview dialog.
- **Global pause & quota** — pause persists (same switch on Web and bot);
  the downloads page shows GP and image quota (~30 min cache).
- **Slow-node watchdog** — per-image total-time budget + warm-up window +
  minimum speed; a sluggish H@H node no longer holds a whole gallery hostage.
- **Self-healing failures** — transient errors re-queue with **exponential
  backoff** (30s → 6h, up to 10 attempts); a periodic sweep re-activates
  failed tasks that still have retry budget.
- **Instant ingestion** — a finished download is written into the index (tags
  and cover included), no full scan; existing download folders are reused.
- **Telegram** — download/scan/favorites notifications (summary / immediate /
  failures-only / off, 中文/English) plus bot control commands (`/pause`
  `/resume` `/status`, paste a gallery URL to enqueue a download).

**Reader & UI**

- **Reader** — one-page streaming, LTR / RTL manga / double-page spread,
  keyboard/space/click paging, `G` to jump, three-page preload, auto-advance
  after the last page, fullscreen and fit modes, 1-hour browser caching, saved
  reading position, and the search context is kept throughout.
- **Browse & history** — newest-gallery browse (random gallery, tag namespace
  strip), **Continue reading** cards, a global top-bar search, a
  reading-history page, an activity log page, and a first-run wizard.
- **Recycle bin & missing pages** — user-deleted / scan-missing galleries are
  restorable; integrity check re-downloads missing pages.

**Security & operations**

- **Security** — PBKDF2 auth, login rate limiting, cross-origin checks and a
  domain whitelist, password change revokes every session; backend runs as
  root by default or drops privileges with `PUID`/`PGID`; optional
  **encryption at rest** (`ENCRYPTION_KEY`, AES-256-GCM).
- **Proxy** — HTTP or SOCKS5 (pick one), used for ExHentai access, downloads
  and translation updates.
- **One-command deployment** — two Docker Hub images plus PostgreSQL with a
  single `docker compose up`; automatic migrations on upgrade and
  `scripts/backup.sh` for backups.

## Where to go next

| Topic | Page |
|-------|------|
| Deployment, volumes, scan-only libraries, TLS | [Deployment](Deployment-EN) |
| Using the UI (browse, reader, tags, downloads, favorites, recycle, settings) | [Usage](Usage-EN) |
| Backup & restore | [Backup](Backup-EN) |
| At-rest encryption & lost-key recovery | [Encryption](Encryption-EN) |
| REST API reference | [API](API) · browsable [openapi.json](openapi.json) |
| Development notes | [Development](Development) |
| Troubleshooting | [FAQ](FAQ-EN) |
| UI screenshots (EN & 中文) | [Screenshots](Screenshots-EN) |

> Pages in Chinese: [首页](Home) · [部署](Deployment) · [使用指南](Usage) ·
> [备份与恢复](Backup) · [静态加密](Encryption) · [常见问题](FAQ) ·
> [界面截图](Screenshots)

## License

[MIT](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE).
