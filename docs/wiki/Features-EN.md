# Features

> [中文](Features) · **English**

Behaviors by module. Architecture:

```
┌─────────────────────────────────────────────────────────────┐
│  SPA  :8000                                                  │
│  Browse · Discover · Library · Series · Tags · Downloads     │
│  Favorites · Manage(recycle/dup/integrity/archive) · Reader  │
└──────────────┬───────────────────────────────▲──────────────┘
               │ /api proxy                    │
┌──────────────▼───────────────────────────────┴──────────────┐
│  FastAPI  127.0.0.1:8001                                     │
│  Scan Ehviewer/CBZ  ·  Downloads/Archive  ·  Favorites      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
          PostgreSQL (optional field encryption)
```

---

## 1. Scanning and formats

- **Ehviewer directories**: scans `<gid>-<title>/` and parses `.ehviewer` (SpiderInfo V2; unmarked V1 is readable) for gid, token, and per-page pTokens. Title, category, and tags are not in SpiderInfo — they come from the folder name, `.galleryvault.json`, or gdata. No unpack-and-rename.
- **Other formats**: CBZ and CBR (embedded `ComicInfo.xml`), JHenTai page-download `metadata` JSON (archive `ametadata` is not scanned), and `.galleryvault.json` inside cold CBZ/directories.
- **7z / PDF / gid-less folders**: `.7z` indexes image members only (non-images stay packed) and opens pages from memory with a 128MB per-page cap; `.pdf` extracts embedded images (oversize images are skipped). Gid-less image folders still browse and rate.
- **Hot / cold storage**: new downloads go to the hot directory; archive roots can be mounted separately. Archiving does not run unless started.
- **Local organization**: custom lists, star ratings, and notes, independent of the site.

## 2. Versions and dedupe

- **Updates**: detects a new GID after a cloud re-upload; download the new version and remove the old local copy in one step.
- **Cross-GID dedupe**: clusters alternative translations, quality variants, or duplicate favorites; bulk remove is available.
- **Same-GID copies**: when the same gid appears under multiple mounts, one copy is kept per policy (already stored / most pages / largest / newest / manual).
- **Title display**: Japanese / English / directory name, independent of download folder naming.

## 3. Site and favorites

- **gdata**: fetches category, tags, and rating with the user's cookies; results are cached.
- **Ten favorite folders**: each folder can be Incremental download, Watch only, or Force download, with its own polling interval. Scheduled checks enqueue new items according to the mode.
- **Site URL**: must be `exhentai.org`, `e-hentai.org`, or a subdomain (any other hostname returns 422). Tag sync for ExHentai-only listings is paused on the public site.
- **Cookie probe**: runs at startup and on a timer; the top bar reports expiry.
- **Discover**: Popular, Watched, Toplist; download or add to favorites.

## 4. Downloads

- **Page-by-page**: configurable concurrency, live progress, missing pages only.
- **Official Archive**: zip channel, spends GP; single-connection stream with Range resume; **retries never re-charge GP**.
- **Slow nodes**: per-image timeout, warmup window, minimum throughput; slow H@H nodes are dropped.
- **Backoff**: 30 seconds up to 6 hours, at most 10 attempts.
- **302**: the queue pauses on a challenge; a probe runs every 10 minutes by default and resumes when cleared.
- **Ingest**: finished downloads are indexed and given a cover without a full library scan.

## 5. Reader and search

- **Layout**: right-to-left, left-to-right, webtoon, dual-page.
- **Navigation**: keyboard, tap zones, `G` jump, prefetch; the next gallery opens after the last page. In webtoon, wheel/touch scroll is used (arrow keys and left/right tap zones do not page).
- **Slideshow**: GIF/WebP `duration_ms` (sum of per-frame delays via binary scan, **capped at 120 seconds**); interval is `max(user interval, duration + 150ms)`. Starting slideshow enters fullscreen; exiting fullscreen stops it.
- **Tag search**: EhTagTranslation database; autocomplete, AND/OR, `-tag` exclusion, and reverse lookup (e.g. Chinese input can match `long hair`).
- **OPDS**: `GET /api/opds` with HTTP Basic, for Tachiyomi, Mihon, and Panels.
- **Recycle bin**: user-deleted or scan-missing galleries can be restored.

## 6. Security and deployment

- **AES-256-GCM**: with `ENCRYPTION_KEY`, cookies, tokens, and password hashes are stored encrypted.
- **Sessions**: the signing secret is stored in the database and survives container restarts; changing the password revokes every session. Cookies default to a 10-year lifetime.
- **PUID / PGID**: unprivileged runtime on NAS. CSRF protection (including `Origin: null` / cookied requests with no Origin). `TRUSTED_PROXIES`. 128MB per-page archive cap.
- **Docker**: AMD64 / ARM64 images, PostgreSQL 18, Alembic migrations.

## 7. Telegram Bot

- After a bot token is configured, startup registers the Telegram `/` menu; copy follows the notification language.
- Paste a gallery URL in chat (trailing/surrounding slashes are fine) to enqueue; `/queue` uses InlineKeyboard for pause / retry / cancel; `/pause` `/resume` share the Web downloads switch.
- `/status` queue overview, `/storage` disk usage, `/quota` image quota and GP, `/cookie` cookie health — same figures as the Web UI.
- `/search` with pagination, `/info` `/random` send details and a cover (same 5-step cover fallback as the Web UI), `/scan` triggers a library scan, `/fav_sync` `/fav_download` `/fav_check` operate on favorites.
