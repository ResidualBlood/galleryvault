# API Reference

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
| GET | `/healthz` | no | `{status: "ok"}` — liveness probe (used by the compose healthcheck). |
| GET | `/api/auth/session` | yes | `{authenticated, auth_required, must_change_password}` or `401`. |
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
  "download_quality": "resample",
  "use_hah": false,
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
  "auth_required": true,
  "tag_translation_update_interval_minutes": 720,
  "favorites": [
    {"favcat": 0, "enabled": true, "mode": "incremental", "poll_interval_minutes": 720}
  ]
}
```

Sending `favorites` updates every folder row (enable flag, mode, interval) and
derives `favorites_categories` from the enabled ones.

## Downloads

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/downloads` | Enqueue a gallery. Body: `{gid, token, title, mode, max_pages?}`. `max_pages` (int) requests a partial/sample download — only the first N pages are fetched; it is persisted and honored by the background worker. Returns `202 {id, gid, status}`. |
| GET | `/api/downloads` | List tasks. Query: `page`, `page_size` (≤100), `status` (pending/downloading/success/failed/cancelled). Items include `current_page`/`total_pages` progress and `retry_count`/`max_retries`. |
| POST | `/api/downloads/{task_id}/cancel` | Cancel a pending/active task. An in-flight download is interrupted (page writes stop, the partial temp dir is removed). |
| POST | `/api/downloads/{task_id}/retry` | Re-queue a failed/cancelled/successful task (`{id, status:pending}`). |
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
| POST | `/api/favorites/{favcat}/check` | `202` – scan folder `favcat`. A disabled folder runs check-only (`monitor_only`): records items and sizes but never downloads; an enabled folder downloads missing galleries per its mode. |
| GET | `/api/favorites/check-status` | Per-folder check progress: `{running, categories: {favcat: {running, done, total, error}}, last_error}`. `done`/`total` track the cursor walk. |
| POST | `/api/favorites/compute-sizes` | `202` – fetch sizes for missing galleries in the background so `cloud_size` becomes exact. |

## Galleries (local library)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/galleries` | Search/browse. Query: `page`, `page_size`, `q`, `tags` (csv `ns:name`), `tag_mode` (and/or), `tag_match` (exact/fuzzy), `category` (`doujinshi`, `manga`, `artistcg`, `gamecg`, `western`, `non-h`, `image_set`, `cosplay`, `asianporn`, `misc`, `deleted`). `misc` is the generic bucket — it also holds what used to be `other`; galleries deleted from ExHentai (or without usable coordinates) live under `deleted`. |
| GET | `/api/galleries/random` | `{id}` of a random non-expunged gallery (`404` when empty). |
| GET | `/api/galleries/{identifier}/next` | `{id}` of the next non-expunged gallery (ascending by id) — used by the reader to advance past the last page (`404` when none). |
| GET | `/api/galleries/{identifier}` | Metadata (`file_size` included), page list, tags (each with Chinese `display` when available), `spider_info`. `identifier` may be the DB `id` or the ExHentai `gid`. |
| DELETE | `/api/galleries/{identifier}` | Remove a gallery (cascades to pages, tag links, progress, history). Query `delete_files=true` also deletes the on-disk directory. |
| POST | `/api/galleries/delete-bulk` | Body `{ids: [...], delete_files?: bool}`. Bulk remove galleries by id; returns `{deleted}`. |
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
| GET | `/api/tags/search` | Search local tags. Query `q`, `page`, `page_size` (≤100), `namespace`. Items include `display` (Chinese translation when available) and `usage_count`. With `zh=1`, `q` is matched against Chinese translations (for the tag-autocomplete in the search box). |
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
| GET | `/api/scan` | Current scan status (`running`, `last`). |
| POST | `/api/scan` | `202` – trigger a library scan. |
| GET | `/api/tag-sync/status` | Background tag-sync worker status (`running`, `queued`, `total`, `processed`, `succeeded`, `failed`, `retries`, `interval`, `last_error`, `category_refreshed`, `category_refresh_running`). |
| POST | `/api/tag-sync/start` | `202` – re-queue every gallery still needing a tag sync for a manual full run. |
| POST | `/api/tag-sync/refresh-categories` | `202` – run a one-time category backfill: galleries in the generic bucket that have ExHentai coordinates but were never category-refreshed are re-fetched and classified; galleries 404 on ExHentai are moved to `deleted`. Status is visible via `category_refreshed`/`category_refresh_running` on `/api/tag-sync/status`. |
| GET | `/api/thumbs/status` | Thumbnail generation worker status (`running`, `queued`, `processed`, `succeeded`, `failed`, `total`, `last_error`). |
| POST | `/api/thumbs/generate` | `202` – queue every gallery missing a cover thumbnail for background generation. |

## Errors

- `400`/`422` – invalid input (validation).
- `401` – authentication required (API routes).
- `404` – resource not found.
- `409` – conflict (e.g. download already queued).
- `502` – upstream ExHentai request failed (error detail is scrubbed of cookies/tokens).
- `503` – a backend service (downloader, database) is unavailable.
