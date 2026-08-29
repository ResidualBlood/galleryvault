# API Reference

> Interactive schema: `docs/openapi.json` (auto-exported via
> `python scripts/export_openapi.py`, viewable with any OpenAPI viewer).

All endpoints (except `/healthz`, `/login`, `/logout`) require an
authenticated session cookie. Unauthenticated `/api/*` requests receive
`401 {"detail":"Authentication required"}`. The SPA obtains the cookie via
`POST /login`.

- **Base URL**: `http://<host>:8001`
- **Content-Type**: `application/json` (except `POST /login`, which is
  `application/x-www-form-urlencoded`).
- **Auth**: session cookie `galleryvault_session` (HttpOnly, SameSite=lax).

## Authentication

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/healthz` | no | `{status: "ok"}` — liveness probe (used by the compose healthcheck). `503` when the database is unreachable. |
| GET | `/metrics` | no | Prometheus-text request counters (`gv_http_requests_total`, `gv_http_errors_total`). |
| GET | `/api/auth/session` | yes | `{authenticated, auth_required, must_change_password}` or `401`. |
| GET | `/api/onboarding/status` | yes | `{password_default, exhentai_configured, library_count}` — setup progress for the first-run wizard. |
| POST | `/login` | no | Form field `password`. Success sets the session cookie and redirects (`303`) to `/`; failure redirects to `/login?error=1`. |
| POST | `/logout` | no | Clears the session cookie, redirects to `/login`. |
| POST | `/api/auth/change-password` | yes | JSON `{current, new}`. `403` if current is wrong; `204` on success. Persists the new hash in the DB so it survives restarts. |

Login is **password-only**. `must_change_password` is `true` when login is
required and no password hash is configured anywhere (the built-in default
`p1a2s3s4` is in effect); the SPA shows a banner that links to Settings.
Turning off login entirely is done by disabling `auth_required` in Settings (or
`AUTH_REQUIRED=false` in the environment), which lets the API through without a
session —
in that mode `must_change_password` is always `false`.

Example login (curl):

```bash
curl -c cookies.txt -X POST http://localhost:8001/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'password=YOUR_PASSWORD'
```

Subsequent calls pass the cookie:

```bash
curl -b cookies.txt http://localhost:8001/api/settings
```

## Settings

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/settings` | Public subset of effective settings (library roots, proxies, quality, favorites, tag-sync, Telegram status, …). |
| POST | `/api/settings` | Persist settings. See `SettingsRequest` fields below. |
| POST | `/api/settings/exhentai/test` | Validate the configured ExHentai cookies. Returns `{status, message}`. |
| POST | `/api/telegram/test` | Send a test message to every configured `telegram_chat_ids`. Returns `{ok, results}`. `422` if the bot token or chat IDs are missing. |

`POST /api/settings` body (all fields optional):

```json
{
  "library_roots": ["/library"],
  "exhentai_base_url": "https://exhentai.org",
  "exhentai_cookies": {"ipb_member_id": "...", "ipb_pass_hash": "...", "igneous": "..."},
  "http_proxy": null, "socks5_proxy": null,
  "download_root": "/downloads",
  "download_concurrency": 2,
  "page_concurrency": 4,
  "download_quality": "resample",
  "use_hah": false,
  "image_download_timeout_seconds": 120,
  "image_slow_warmup_seconds": 30,
  "image_min_speed_kb_s": 20,
  "title_display": "japanese",
  "favorites_categories": [0, 5],
  "download_favorites_enabled": false,
  "favorites_poll_interval_minutes": 720,
  "auto_sync_tags": true,
  "tag_sync_interval_seconds": 1.5,
  "tag_sync_concurrency": 4,
  "telegram_bot_token": null,
  "telegram_chat_ids": ["12345"],
  "telegram_allowed_user_ids": [67890],
  "telegram_notify_level": "summary",
  "telegram_notify_lang": "zh",
  "duplicate_policy": "keep_first",
  "auth_required": true,
  "tag_translation_update_interval_minutes": 720,
  "favorites": [
    {"favcat": 0, "enabled": true, "mode": "incremental", "poll_interval_minutes": 720}
  ]
}
```

Sending `favorites` updates every folder row (enable flag, mode, interval) and
derives `favorites_categories` from the enabled ones.

`telegram_notify_level` controls download notifications: `summary` (default,
buffers terminal download events into a single digest flushed when the queue is
idle), `immediate` (one message per event, the legacy behaviour),
`failures_only` (only final failures), or `off` (no automatic notifications).

`telegram_notify_lang` selects the language of Telegram notification copy:
`zh` (default) or `en`. All notifications (downloads, library scans, favorites
checks and the Telegram bot replies) share this language; gallery titles are
always shown untranslated.

`duplicate_policy` decides how the library scan resolves a gallery (same gid)
found under more than one scan root: `keep_first` (default, the already-stored
copy wins), `prefer_more_pages`, `prefer_newer`, `prefer_larger`,
`prefer_smaller`, or `manual` (never auto-resolve — everything is reported for
manual cleanup on the *Duplicate copies* page). All duplicates are recorded in
`duplicate_records` regardless of policy.

## Downloads

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/downloads` | Enqueue a gallery. Body: `{gid, token, title, mode, max_pages?}`. `max_pages` (int) requests a partial/sample download — only the first N pages are fetched; it is persisted and honored by the background worker. Returns `202 {id, gid, status}`. |
| GET | `/api/downloads` | List tasks. Query: `page`, `page_size` (≤500), `status` (pending/downloading/success/failed/cancelled). Items include `current_page`/`total_pages` progress and `retry_count`/`max_retries`. |
| POST | `/api/downloads/{task_id}/cancel` | Cancel a pending/active task. An in-flight download is interrupted (page writes stop, the partial temp dir is removed). |
| POST | `/api/downloads/{task_id}/retry` | Re-queue a failed/cancelled/successful task (`{id, status:pending}`). Retries are otherwise automatic: transient failures re-queue with an exponential backoff up to `max_retries` (default 10), and a periodic sweep re-activates `failed` tasks that still have budget left. |
| DELETE | `/api/downloads/{task_id}` | `204` – permanently remove a download task and its attempt log. |

```bash
curl -b cookies.txt -X POST http://localhost:8001/api/downloads \
  -H 'Content-Type: application/json' \
  -d '{"gid": 12345, "token": "abcdef", "title": "Example", "mode": "full"}'
```

## Favorites (ExHentai)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/favorites/categories` | The ten favorite folders with `enabled`/`mode`, plus `cloud_count` (live folder size from the favorites page header), `local_count`/`local_size` (galleries already local, from `favorite_items`), `cloud_size` (exact: local real size + fetched sizes of missing galleries, with an average estimate for the unfetched tail). |
| POST | `/api/favorites/categories` | Body `{favcat, enabled?, mode?}` to update one folder. |
| POST | `/api/favorites/sync-categories` | Refresh folder names from ExHentai. |
| POST | `/api/favorites/{favcat}/check` | `202` – scan folder `favcat`. A disabled folder runs check-only (`monitor_only`): records items and sizes but never downloads; an enabled folder downloads missing galleries per its mode. Mode semantics: `incremental` enqueues only gids never recorded in `favorite_items` (new additions), `monitor_only` never downloads, and `force` skips the recorded-set filter and enqueues every folder gallery not already in the local library (`galleries` table). Both `incremental` and `force` skip already-local galleries. |
| POST | `/api/favorites/check-all` | `202` – check every configured folder at once (spawns one check per favcat). |
| GET | `/api/favorites/check-status` | Per-folder check progress: `{running, categories: {favcat: {running, done, total, error}}, last_error}`. `done`/`total` track the cursor walk. |
| POST | `/api/favorites/compute-sizes` | `202` – fetch sizes for missing galleries in the background so `cloud_size` becomes exact. |
| GET | `/api/favorites/metadata-status` | Favorites metadata sync/apply worker status (`running`, `stage` (sync/apply), `done`, `total`, `applied`, `last_error`). |
| GET | `/api/favorites/cover` | Query `gid` + `token`. Fetches and caches a remote gallery cover (served as the image bytes); `404` when the gallery has no usable cover. |
| GET | `/api/favorites/{favcat}/items` | Paginated folder galleries (`page`, `page_size`, optional `state` = `all`/`local`/`cloud` to filter by whether the gallery is already local). Each row: `favcat`, `gid`, `token`, `title`, `url`, `first_seen_at`, `state` (`local`/`cloud`), and when the gallery is local `gallery_id`, `category`, `page_count`, `cover_url`, `file_size`, `tags`. Cloud-only galleries get their metadata (real `file_size`, `title_jpn`, `tags`, category) via the batched gdata API and an inline `cover_data` base64 thumbnail, so a folder page renders with a single request. |
| POST | `/api/favorites/download-missing` | `202` – spawns a per-folder `_favorite_size_sync` pass that downloads cover files for every gallery in the folder missing a cover on disk (using the thumb URL captured from the favorites listing). |
| POST | `/api/favorites/remove` | Body `{gids: [...], delete_local?: bool}`. Remove galleries from ExHentai favorites (all folders, `favorites.php` `ddact=delete` like SXJ) and from local `favorite_items`; `delete_local` also deletes on-disk galleries — every physical copy of a gid under the scan roots, and the `duplicate_records` row once all copies are gone. A gallery row is kept when any copy fails to delete (avoids resurrection on the next scan). Returns `{cloud_ok, cloud_removed, local_removed, deleted_local_galleries, failed_deletions}`. |
| POST | `/api/favorites/duplicates/scan` | `202` – background scan grouping favorite items into duplicate sets (same normalized title + same artist). |
| GET | `/api/favorites/duplicates/status` | Scan progress (`stage`, `done`, `total`) and result `groups` (`key`, `artist`, `items: [{favcat, gid, token, title, url, gallery_id, file_size, posted_at, first_seen_at, title_jpn, cover_data, tags}]`), `group_count`, `item_count`, plus `ignored` (previously hidden groups, restorable). Cloud items are enriched via the batched gdata API (cover, size, posted date, tags); local items' posted dates are persisted onto `galleries.posted_at`. |
| POST | `/api/favorites/duplicates/ignore` | Body `{key, title?, gids?}` – hide a duplicate group from every later scan. |
| DELETE | `/api/favorites/duplicates/ignore?key=` | Restore a previously ignored group. |
| GET | `/api/favorites/duplicates/ignored` | List the currently ignored duplicate groups (each with `key`, `title`, `items`) so they can be restored. |
| GET | `/api/galleries/{identifier}/favorite` | Which favorite folders a gallery is in: `{gid, favorite: bool, favcats: [...]}`.

## Galleries (local library)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/galleries` | Search/browse. Query: `page`, `page_size`, `q`, `tags` (csv `ns:name`), `tag_mode` (and/or), `tag_match` (exact/fuzzy), `category` (`doujinshi`, `manga`, `artistcg`, `gamecg`, `western`, `non-h`, `image_set`, `cosplay`, `asianporn`, `misc`, `deleted`). `q` supports **smart parsing**: whitespace-separated tokens that are `ns:name` syntax, a Chinese word mapping one-to-one onto a tag translation, or an exact tag name are promoted to tag filters (AND with any explicit `tags`), the rest stays a title keyword; the response carries the normalized `q`/`tags` plus a `resolved` flag. `misc` is the generic bucket — it also holds what used to be `other`; galleries deleted from ExHentai (or without usable coordinates) live under `deleted`. |
| GET | `/api/galleries/random` | `{id}` of a random non-expunged gallery (`404` when empty). |
| GET | `/api/galleries/{identifier}/next` | `{id}` of the next non-expunged gallery (ascending by id) — used by the reader to advance past the last page (`404` when none). |
| GET | `/api/galleries/{identifier}` | Metadata (`file_size` included), page list, tags (each with Chinese `display` when available), `spider_info`, and `eh_url` (deep link `{base_url}/g/{gid}/{token}/` built from the configured base URL; empty for local galleries without a token). `identifier` may be the DB `id` or the ExHentai `gid`. |
| DELETE | `/api/galleries/{identifier}` | Remove a gallery (cascades to pages, tag links, progress, history). Query `delete_files=true` also deletes the on-disk files (directory or single archive); the row is kept when deletion fails. |
| POST | `/api/galleries/delete-bulk` | Body `{ids: [...], delete_files?: bool}`. Bulk remove galleries by id; `delete_files` also deletes on-disk files, keeping each row whose files failed to delete. Returns `{deleted, failed_deletions}`. Ids are processed in 500-row batches to stay under asyncpg's parameter limit. |
| POST | `/api/galleries/delete-filtered` | Body `{q?, category?, tags?, tag_mode?, tag_match?, delete_files?}`. Remove every gallery matching the current library filter (same semantics as `GET /api/galleries`). The backend pages the filter and deletes in 500-row batches, so the client never sends a huge id list. Returns `{deleted, matched, failed_deletions}`. |
| GET | `/api/galleries/{identifier}/pages/{page_index}` | Stream one page image (`image/jpeg`/`image/png`/…). |
| GET | `/api/galleries/{identifier}/thumb/{page_index}` | Serve a cached static JPEG thumbnail for a page (generated on first access into `/gv-cache/thumbs`, `Cache-Control` + `ETag`). |
| GET | `/api/galleries/{identifier}/progress` | Reading progress (`current_page`, `total_pages`). |
| PUT | `/api/galleries/{identifier}/progress` | Body `{current_page, total_pages}` – records progress and history. |
| POST | `/api/galleries/{identifier}/sync-tags` | Sync tags from ExHentai. |

Example:

```bash
curl -b cookies.txt 'http://localhost:8001/api/galleries?q=myth&page=1&page_size=24'
```

## History & Tags

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/history` | Reading history (`page`, `page_size`). |
| DELETE | `/api/history` | Clear history (`204`). |
| GET | `/api/tags/search` | Search local tags. Query `q`, `page`, `page_size` (≤500), `namespace`. Items include `display` (Chinese translation when available) and `usage_count`. With `zh=1`, `q` is matched against Chinese translations (for the tag-autocomplete in the search box). |
| GET | `/api/tags/search/status` | Tag translation auto-update status (`entries`, `last`, `last_error`, `source`, `interval_minutes`). |
| POST | `/api/tags/search/reload` | `202` – download the latest EhTagTranslation release (`db.text.json`) and reload translations now. |

Tag translations are updated **in the backend** from the latest
[`EhTagTranslation/Database`](https://github.com/EhTagTranslation/Database)
release (the same source ehsyringe uses). A background task runs every
`TAG_TRANSLATION_UPDATE_INTERVAL_MINUTES` (default 720, `0` disables); a manual
refresh is available via the button in Settings. Markdown icon syntax
(`![alt](url)`) embedded in translations is stripped for display.

## Library scan, tag-sync & thumbnails

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/scan` | Current scan status (`running`, `started_at`, `completed_at`, `scanned`, `persisted`, `success`, `errors`, `expunged`, `duplicates`, `duplicate_gids`, `last`). |
| POST | `/api/scan` | `202` – trigger a library scan. |
| GET | `/api/scan/duplicates` | Duplicate-copy groups found by the last scan. Each group (`gid`, `status` (`open`/`dismissed`), `policy`, `winner_path`) lists every physical copy with `path`, `key`, `gallery_id`, `storage_type`, `title`, `page_count`, `file_size`, `posted_at`, `is_current`, `tags`. |
| POST | `/api/scan/duplicates/{gid}/resolve` | Body `{path, delete_others?}` – make `path` the stored copy (the gallery row is re-pointed at it). With `delete_others=true` the other copies are deleted from disk (paths must be inside the scan roots and listed in the group) and the group is dropped. |
| POST | `/api/scan/duplicates/{gid}/dismiss` | Hide a duplicate group (survives rescans until the copies actually change). |
| POST | `/api/scan/duplicates/{gid}/restore` | Bring a dismissed group back. |
| GET | `/api/scan/duplicates/thumb/{key}` | Lazily-generated JPEG cover thumbnail for one copy (cached under `/gv-cache/thumbs/dup/{key}/0.jpg`). |
| GET | `/api/tag-sync/status` | Background tag-sync worker status (`running`, `queued`, `total`, `processed`, `succeeded`, `failed`, `retries`, `interval`, `last_error`, `category_refreshed`, `category_refresh_running`). |
| POST | `/api/tag-sync/start` | `202` – re-queue every gallery still needing a tag sync for a manual full run. |
| POST | `/api/tag-sync/refresh-categories` | `202` – run a one-time category backfill: galleries in the generic bucket that have ExHentai coordinates but were never category-refreshed are re-fetched and classified; galleries 404 on ExHentai are moved to `deleted`. Status is visible via `category_refreshed`/`category_refresh_running` on `/api/tag-sync/status`. |
| GET | `/api/thumbs/status` | Thumbnail generation worker status (`running`, `queued`, `processed`, `succeeded`, `failed`, `total`, `last_error`). |
| POST | `/api/thumbs/generate` | `202` – queue every gallery missing a cover thumbnail for background generation. |
| GET | `/api/logs` | Aggregated activity log: `{running: [...], finished: [...]}`. `running` lists the live background tasks (each with `task` (scan/tag-sync/thumbs/metadata), `started_at`, `done`, `total`, `stage`, `cancellable`); `finished` is the latest-first history of completed tasks with `task`, `started_at`, `completed_at`, `status` (success/failed/cancelled), `reason`, `done`, `total`. |
| POST | `/api/logs/{task}/cancel` | `202` – request cancellation of a running background task (`scan`, `tag-sync`, `thumbs`, `metadata`). The worker stops at the next safe point; the queue is drained for queue-based tasks. |

## Errors

- `400`/`422` – invalid input (validation).
- `401` – authentication required (API routes).
- `404` – resource not found.
- `409` – conflict (e.g. download already queued).
- `502` – upstream ExHentai request failed (error detail is scrubbed of cookies/tokens).
- `503` – a backend service (downloader, database) is unavailable.
