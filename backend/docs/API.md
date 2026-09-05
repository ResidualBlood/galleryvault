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
- **HTTP Basic Auth**: Supported *only* on `GET /api/opds`. Fixed username `galleryvault` (not an ExHentai account); password is the web login password. Missing or invalid credentials on this endpoint return `401 Unauthorized` with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`. Session cookies remain valid. All other `/api/*` routes (including CBZ export) are cookie-only.

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

For the OPDS feed, HTTP Basic authentication is also accepted (username `galleryvault`, password is the web login password):

```bash
curl -H "Authorization: Basic <base64(galleryvault:password)>" http://localhost:8001/api/opds
```

## Settings

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/settings` | Public subset of effective settings (library roots, proxies, quality, favorites, tag-sync, Telegram status, …). |
| POST | `/api/settings` | Persist settings. See `SettingsRequest` fields below. |
| GET | `/api/settings/cookie-health` | Probe or return current ExHentai Cookie login status (`{state, detail, checked_at}`). Cached ~10 min then re-probes. States: `ok`, `not_logged_in` (session expired), `no_exhentai_access` (lacks ExHentai access, e.g. empty/blank 200 on exhentai.org or Sad Panda; distinct from expired session), or `failed` (network/site error, or empty 200 on e-hentai.org / unknown hosts). |
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
  "download_title": "japanese",
  "archive_quality": "resample",
  "favorites_archive_enabled": false,
  "favorites_archive_max_pages": 0,
  "archive_fallback_pages": true,
  "use_hah": false,
  "image_download_timeout_seconds": 120,
  "image_slow_warmup_seconds": 30,
  "image_min_speed_kb_s": 10,
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
  "trusted_proxies": ["192.168.1.0/24"],
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

## ExHentai search (discover)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/eh/search` | Live ExHentai listing. Query: `q`, `category` (`f_cats` 0–1023 or comma-separated names), `min_rating` (`f_srdd`), `next` (`gid-ts` cursor), `list` (`search` default / `popular` / `watched` / `toplist`), `tl` for toplist (11 yesterday / 12 month / 13 year / 15 all-time). Paths: `/`, `/popular`, `/watched`, `/toplist.php?tl=`. **Never** `page=N`. Response `{state, items, next, list, tl}`. `state` is `ok` / `empty` / `not_logged_in` / `no_exhentai_access` / `challenge` / `rate_limited`. A 302 through `remoteapi.php` is `challenge`, not cookie failure. Items include local badges from `galleries` + `favorite_items`. EH payload cached 90s (errors 15s) keyed by query+list+cursor. Download/favorite reuse `POST /api/downloads` and `POST /api/favorites/add` (not `POST /api/galleries/{id}/favorite`). |

## Downloads

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/downloads` | Enqueue a gallery. Body: `{gid, token, title, mode, max_pages?, quality?}`. `max_pages` (int) requests a partial/sample download — only the first N pages are fetched; it is persisted and honored by the background worker. `quality` (`resample`/`original`) overrides the global `download_quality` for this task (page-by-page original downloads ignore H@H and fetch full-size images). Returns `202 {id, gid, status}`. |
| GET | `/api/downloads` | List tasks. Query: `page`, `page_size` (≤500), `status` (pending/downloading/success/failed/cancelled). Items include `current_page`/`total_pages` progress and `retry_count`/`max_retries`. |
| POST | `/api/downloads/{task_id}/cancel` | Cancel a pending or downloading task. An in-flight download is interrupted (page writes stop, partial files are removed; the worker does not write to disk upon cancellation). Cancel latency is bounded by the page-progress ticks (at most one in-flight page finishes first). |
| POST | `/api/downloads/{task_id}/retry` | Re-queue a failed/cancelled/successful task (`{id, status:pending}`). Retries are otherwise automatic: transient failures re-queue with an exponential backoff up to `max_retries` (default 10), and a periodic sweep re-activates `failed` tasks that still have budget left. |
| DELETE | `/api/downloads/{task_id}` | `204` – permanently remove a download task and its attempt log. |
| POST | `/api/downloads/clear-success` | Remove every task with `status=success`. Returns `{deleted}`. Does not delete ingested gallery files. |

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
| GET | `/api/favorites/{favcat}/items` | Paginated folder galleries (`page`, `page_size`, optional `state` = `all`/`local`/`cloud`, `q` = title search, `order_by` = `last_seen_desc`/`first_seen_desc`/`posted_at_desc`/`title_asc`/`file_size_desc`). Each row: `favcat`, `gid`, `token`, `title`, `url`, `first_seen_at`, `state` (`local`/`cloud`), and when the gallery is local (not expunged/trashed) `gallery_id`, `category`, `page_count`, `cover_url`, `file_size`, `tags`. Cloud-only galleries get cached metadata (`file_size`, `title_jpn`, `tags`, category) and `cover_url=/api/favorites/cover?gid=&token=` (disk-first; the check/`download-missing` pass warms `/gv-cache/remote-covers/{gid}.img`). The items response does not download covers. |
| POST | `/api/favorites/download-missing` | `202` – spawns a per-folder `_favorite_size_sync` pass that downloads cover files for every gallery in the folder missing a cover on disk (using the thumb URL captured from the favorites listing). |
| POST | `/api/favorites/remove` | Body `{gids: [...], delete_local?: bool}`. Remove galleries from ExHentai favorites (all folders, `favorites.php` `ddact=delete` like SXJ, chunked 25/batch with per-gid retry). Local `favorite_items` (and `delete_local` on-disk deletes) apply only to cloud-successful gids; `cloud_failed` keep their local rows. Returns `{cloud_ok, cloud_removed, cloud_failed, local_removed, deleted_local_galleries, failed_deletions}`. |
| POST | `/api/favorites/move` | Body `{gids: [...], target_favcat: int}` (0-9). Move galleries to another ExHentai favorite folder (`favorites.php` `ddact=favX`, chunked 25/batch with per-gid retry) and update local `favorite_items`. Returns `{gids, target_favcat, cloud_ok, cloud_moved, cloud_failed, local_moved}`. |
| POST | `/api/favorites/add` | Body `{gid?: int, token?: str, target_favcat: int, note?: str, items?: [{gid, token, title, note}]}`. Add galleries to an ExHentai favorite folder (`gallerypopups.php?act=addfav`; EH move — one gid one folder). Local write only for `successful_gids`, then migrate out of other local folders. Auth/network failure does not mark already-succeeded gids as failed. Returns `{gids, target_favcat, cloud_ok, cloud_added, cloud_failed, successful_gids, local_added}`. |
| POST | `/api/favorites/note` | Body `{gid, note, token?, favcat?}`. Update favnote via the same addfav channel; **local `favorite_items.note` is written only after cloud success**. |
| POST | `/api/favorites/download-selected` | Body `{gids: [...], archive?: bool, quality?: string}` — `202`; enqueues each selected **cloud-only** favorite gid (`{queued, skipped}`). Trashed/expunged local copies count as cloud (can re-download). `quality` applies to page-by-page as well as archive; `archive: true` uses the ExHentai zip channel. |
| POST | `/api/favorites/duplicates/scan` | `202` – background scan grouping favorite items into duplicate sets (same normalized title + same artist). |
| GET | `/api/favorites/duplicates/status` | Scan progress (`stage`, `done`, `total`) and result `groups` (`key`, `artist`, `items: [{favcat, gid, token, title, url, gallery_id, file_size, posted_at, first_seen_at, title_jpn, cover_data, tags}]`), `group_count`, `item_count`, plus `ignored` (previously hidden groups, restorable). Cloud items are enriched via the batched gdata API (cover, size, posted date, tags); local items' posted dates are persisted onto `galleries.posted_at`. |
| POST | `/api/favorites/duplicates/ignore` | Body `{key, title?, gids?}` – hide a duplicate group from every later scan. |
| DELETE | `/api/favorites/duplicates/ignore?key=` | Restore a previously ignored group. |
| POST | `/api/favorites/duplicates/unignore` | Body `{key, title?, gids?}` – restore an ignored duplicate group (alias for DELETE ignore). |
| GET | `/api/favorites/duplicates/ignored` | List the currently ignored duplicate groups (each with `key`, `title`, `items`) so they can be restored. |
| POST | `/api/favorites/sync` | Force refresh and sync favorites metadata cache. |
| GET | `/api/galleries/{identifier}/favorite` | Which favorite folders a gallery is in: `{gid, favorite: bool, favcats: [...]}`. |

## Archives (ExHentai zip channel)

ExHentai's official archive download: the server packs the whole gallery into a
zip (charging GP) and the client streams it on a single connection, which is
much faster than per-page H@H fetches for large galleries. Tasks created with
`archive: true` (or `mode` containing `"archive"`) run through this channel.
The executor reads `archiver.php`, requests the zip once (the returned URL is
persisted under `.gv-{gid}/.archive.json` so retries resume with a Range request
instead of re-charging GP), streams it, unzips, renames images by page order and
writes the same `.ehviewer`/`.galleryvault.json` metadata as a page-by-page
download. Insufficient GP fails the task immediately without retries.

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/archives/preview` | Body `{gids: [...]}`. Read-only, **does not charge GP**: returns `{funds, items:[{gid, title, resample_cost, resample_size, original_cost, original_size, resample_available, original_available}]}`. Tokens are resolved from `favorite_items` (and gallery-update rows); unavailable gids are omitted and per-gallery fetch failures carry an `error` field. |

The scheduled favorites check uses the archive channel when
`favorites_archive_enabled` is on: galleries whose `filecount` exceeds
`favorites_archive_max_pages` (0 = all) are archived with the `archive_quality`
tier, the rest download page-by-page.

## Gallery updates (re-uploaded versions)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/updates` | Re-upload tracking. Query `page`, `page_size`, `state` (`active` = everything except ignored, `all`, `pending`, `downloading`, `failed`, `ignored`). Each row: `id`, `gallery_id` (old local copy), `old_gid`, `new_gid`, `title`, `favcat`, `favcat_name`, `status` (`pending`/`downloading`/`failed`/`ignored`), `error_message`, `detected_at`, `updated_at`, `cover_url`. Detection: a local gallery whose gid is not in any favorite folder but whose normalized title matches a favorite item. If the new gid is already in the local library, detection finalizes immediately (deletes the old copy; ignored rows are left alone). An in-flight download for the new gid is pinned onto the update row (`downloading`) so the finalize loop can close it. |
| POST | `/api/updates/scan` | `202` – trigger a detection scan now (also runs automatically after every favorites check). |
| GET | `/api/updates/status` | Detection/update status: `{detecting, last_detected_at, last_run, last_error, last_found, counts: {pending, downloading, failed, ignored}}`. |
| POST | `/api/updates/update` | Body `{ids: [...], archive?: bool, quality?: string}` – `202`; enqueues the new-gid download for each pending row (`{started, skipped}`). If the new gid is already local, the old copy is deleted immediately (no extra download). `archive: true` uses the ExHentai archive channel with the given quality tier. When the download finishes, the old local copy is deleted (files + row, cascade-deleting the update row). |
| POST | `/api/updates/ignore` | Body `{ids: [...]}` – mark rows ignored (hidden from the active list, restorable). |
| POST | `/api/updates/unignore` | Body `{ids: [...]}` – restore ignored rows to `pending`. |
| GET | `/api/updates/ignored` | Paginated list of currently ignored rows (for the restore page). |
| POST | `/api/updates/delete` | Body `{ids: [...]}` – permanently remove failed/ignored update records (`200 {deleted}`). |

## Galleries (local library)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/galleries` | Search/browse. Query: `page`, `page_size`, `q`, `tags` (csv `ns:name`), `tag_mode` (and/or), `tag_match` (exact/fuzzy), `category` (including `__not_fav__`), `read_status`, `min_rating`, `page_min`/`page_max`, `size_min`/`size_max` (bytes, `coalesce(storage_size,file_size)`), `posted_from`/`posted_to`, `uploader` (substring), `image_quality` (`original`/`resample`), `min_local_rating` (1–5), `list_id`. Language shortcuts are ordinary `language:` tags. |
| GET | `/api/galleries/categories` | Count of galleries per category dictionary, including `__not_fav__` and total `all`. |
| GET | `/api/galleries/random` | `{id}` of a random non-expunged gallery (`404` when empty). |
| GET | `/api/galleries/{identifier}/next` | `{id}` of the next non-expunged gallery (ascending by id) — used by the reader to advance past the last page (`404` when none). |
| GET | `/api/galleries/{identifier}` | Metadata including `local_rating` / `local_note`, page list, tags (`local:` custom tags live alongside EH tags), `spider_info`, and `eh_url`. |
| PATCH | `/api/galleries/{identifier}/local` | Body `{local_rating?, local_note?, local_tags?}`. Local stars 1–5 (null clears), note, and `local:` tags only — does not replace ExHentai tags. |
| GET | `/api/galleries/{identifier}/lists` | Local lists that contain this gallery. |
| POST | `/api/galleries/{identifier}/download-original` | `202` – enqueue download for original quality. Body `{archive?: bool}` (supports page-by-page or ExHentai archive channel). Superseded resampled copy is removed upon completion. |
| POST | `/api/galleries/{identifier}/redownload` | `202` – enqueue redownloading this gallery (`mode=gallery` or `gallery_archive`; does not follow replacement chains). |
| POST | `/api/galleries/{identifier}/favorite` | Body `{favcat: int}` (0-9). Modify the ExHentai favorite category folder for this gallery. |
| POST | `/api/galleries/{identifier}/read` | Mark gallery as read (`upsert_progress` to last page). |
| DELETE | `/api/galleries/{identifier}` | Remove a gallery (cascades to pages, tag links, progress, history). Query `delete_files=true` also deletes on-disk files; partial disk deletion failure returns `500` with `failed_paths` and `deleted_paths` in the body, removing deleted copy paths from DB and keeping the row if residual copies remain. |
| POST | `/api/galleries/delete-bulk` | Body `{ids: [...], delete_files?: bool}`. Bulk remove galleries by id; `delete_files` also deletes on-disk files, keeping each row whose files failed to delete. Returns `{deleted, failed_deletions}`. Ids are processed in 500-row batches to stay under asyncpg's parameter limit. |
| POST | `/api/galleries/delete-filtered` | Body `{q?, category?, tags?, tag_mode?, tag_match?, delete_files?}`. Remove every gallery matching the current library filter (same semantics as `GET /api/galleries`). The backend pages the filter and deletes in 500-row batches, so the client never sends a huge id list. Returns `{deleted, matched, failed_deletions}`. When `matched` exceeds 5000 the request is rejected with `409` (refine the filter or delete in batches). |
| GET | `/api/galleries/{identifier}/export.cbz` | Download the gallery as a CBZ (requires session cookie authentication). An on-disk `.cbz` is streamed with `FileResponse`; a directory gallery is packed in page order (`ZIP_STORED`) to a tempfile. Member paths must resolve inside the gallery directory (zip-slip → `400`); missing files → `404`. Records an `export-cbz` task log. |
| GET | `/api/galleries/{identifier}/pages/{page_index}` | Stream one page image (`image/jpeg`/`image/png`/…). |
| GET | `/api/galleries/{identifier}/thumb/{page_index}` | Serve a cached static JPEG thumbnail for a page (generated on first access into `/gv-cache/thumbs`, `Cache-Control` + `ETag`). |
| GET | `/api/galleries/{identifier}/progress` | Reading progress (`current_page`, `total_pages`). |
| PUT | `/api/galleries/{identifier}/progress` | Body `{current_page, total_pages}` – records progress and history. |
| DELETE | `/api/galleries/{identifier}/progress` | Clear reading progress and that gallery's history row (`204`). Removes it from Continue Reading / History. |
| DELETE | `/api/galleries/progress` | Clear / reset reading progress for all galleries (`204`). |
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

## Series

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/series` | Paged list of series groups: `{items, total, page, page_size}`. Query: `page` (default 1), `page_size` (default 25), `show_all` (0 = doujinshi/manga only, 1 = all categories). Members include local galleries and cloud-only favorites with `cover_url` (`/api/favorites/cover`). |
| POST | `/api/series` | Body `{name}` — create a manual series group (`201`). |
| GET | `/api/series/{series_id}` | Series group details and member list (`404` if missing). |
| PATCH | `/api/series/{series_id}` | Body `{name}` — rename a series group. |
| DELETE | `/api/series/{series_id}` | Delete a series group and its memberships. |
| POST | `/api/series/{series_id}/items` | Body `{gallery_ids: [...], gids: [...]}` — add local galleries or gids to the series. |
| POST | `/api/series/{series_id}/items/remove` | Body `{gallery_ids: [...], gids: [...]}` — remove local galleries or gids from the series. |
| GET | `/api/series/{series_id}/cloud-candidates` | Query `q` (optional) — search cloud favorites candidates eligible to add to this series. |
| POST | `/api/series/{series_id}/cloud-items` | Body `{gids: [...]}` — add cloud-only favorite members to the series. |
| POST | `/api/series/{series_id}/cloud-items/remove` | Body `{gids: [...]}` — remove cloud members from the series. |
| POST | `/api/series/rebuild` | Trigger full series re-clustering and rebuild; logs progress to task history as `series-rebuild`. |

## Library scan, tag-sync & thumbnails

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/scan` | Current scan status (`running`, `started_at`, `completed_at`, `scanned`, `persisted`, `success`, `errors`, `expunged`, `duplicates`, `duplicate_gids`, `last`). |
| POST | `/api/scan` | `202` – trigger a library scan. |
| GET | `/api/scan/duplicates` | Duplicate-copy groups found by the last scan. Each group (`gid`, `status` (`open`/`dismissed`), `policy`, `winner_path`) lists every physical copy with `path`, `key`, `gallery_id`, `storage_type`, `title`, `page_count`, `file_size`, `posted_at`, `is_current`, `tags`. |
| POST | `/api/scan/duplicates/{gid}/resolve` | Body `{path, delete_others?}` – make `path` the stored copy (the gallery row is re-pointed at it). With `delete_others=true` the other copies are deleted from disk (paths must be inside the scan roots and listed in the group) and the group is dropped. |
| POST | `/api/scan/duplicates/{gid}/dismiss` | Hide a duplicate group (survives rescans until the copies actually change). |
| POST | `/api/scan/duplicates/{gid}/restore` | Bring a dismissed group back. |
| GET | `/api/scan/duplicates/thumb/{key}` | Lazily-generated JPEG cover thumbnail for one copy (cached under `/gv-cache/thumbs/dup/{key}/0.jpg`). Invalid keys (`..`, slashes, or absolute paths) return `404`. |
| GET | `/api/tag-sync/status` | Background tag-sync worker status (`running`, `queued`, `total`, `processed`, `succeeded`, `failed`, `retries`, `interval`, `last_error`, `category_refreshed`, `category_refresh_running`). |
| POST | `/api/tag-sync/start` | `202` – re-queue every gallery still needing a tag sync for a manual full run. |
| POST | `/api/tag-sync/refresh-categories` | `202` – run a one-time category backfill: galleries in the generic bucket that have ExHentai coordinates but were never category-refreshed are re-fetched and classified; galleries 404 on ExHentai are moved to `deleted`. Status is visible via `category_refreshed`/`category_refresh_running` on `/api/tag-sync/status`. |
| GET | `/api/thumbs/status` | Thumbnail generation worker status (`running`, `queued`, `processed`, `succeeded`, `failed`, `total`, `last_error`). |
| POST | `/api/thumbs/generate` | `202` – queue every gallery missing a cover thumbnail for background generation. |
| GET | `/api/notifications` | In-app notification ring (maxlen 100): `{items, unread_count}`. Loaded from `cache/notifications.json` on startup and rewritten on change; write failures are logged only. |
| POST | `/api/notifications/read` | Mark every item read; returns the same shape as GET with `unread_count: 0`. |
| POST | `/api/notifications/clear` | Clear every notification; returns `{items: [], unread_count: 0}`. |
| GET | `/api/opds` | OPDS Atom catalog of recently ingested galleries (supports session cookie or HTTP Basic auth). Acquisition links `GET /api/galleries/{id}/export.cbz`. |
| GET | `/api/system/storage` | Library / downloads / cache usage. Missing roots report `bytes: 0` (not 500). `largest` is the top 10 by DB `storage_size`. |
| GET | `/api/saved-searches` | Named library filters stored in `user_settings.saved_searches` (get+merge, max 30). |
| POST | `/api/saved-searches` | Body `{name, query}`. |
| DELETE | `/api/saved-searches/{id}` | Remove one saved search. |
| GET | `/api/lists` | Local lists (`id`, `name`, `count`). Independent of ExHentai. |
| POST | `/api/lists` | Body `{name}`. |
| PATCH | `/api/lists/{id}` | Rename. |
| DELETE | `/api/lists/{id}` | Delete list and memberships. |
| POST | `/api/lists/{id}/items` | Body `{gallery_ids}` — add (CBZ without gid allowed). |
| POST | `/api/lists/{id}/items/remove` | Body `{gallery_ids}`. |
| GET | `/api/quota` | Cached GP + Image Limit. JSON `{gp, image_limit: {current, limit}, image_limits, checked_at, error, cached}`. |
| GET | `/api/logs` | Aggregated activity log: `{running: [...], finished: [...]}`. `running` lists the live background tasks (each with `task` (scan/tag-sync/thumbs/metadata), `started_at`, `done`, `total`, `stage`, `cancellable`); `finished` is the latest-first history of completed tasks with `task`, `started_at`, `completed_at`, `status` (success/failed/cancelled), `reason`, `done`, `total`. |
| POST | `/api/logs/{task}/cancel` | `202` – request cancellation of a running background task (`scan`, `tag-sync`, `thumbs`, `metadata`). The worker stops at the next safe point; the queue is drained for queue-based tasks. |
| GET | `/api/system/logs` | In-memory diagnostic ring buffer (`level` filter, optional `q` text search). Items include timestamp, level, logger, message, and extras (request id, worker context); secrets are masked. httpx 2xx/3xx access lines (including Telegram `getUpdates` long-poll) are omitted; 4xx/5xx and business logs are kept. |
| POST | `/api/system/logs/level` | Body `{level}` (`DEBUG`/`INFO`/`WARNING`/`ERROR`) — change the process log level without restart. |
| DELETE | `/api/system/logs` | Clear the in-memory ring buffer (`204`). |
| GET | `/api/system/logs/download` | Download `galleryvault.log` (rotated file under configured log root plus recent memory lines) as an attachment. The file path must resolve within the log root (`403` if out-of-bounds, `404` if missing). |

## Errors

- `400`/`422` – invalid input (validation).
- `401` – authentication required (API routes).
- `404` – resource not found.
- `409` – conflict (e.g. download already queued).
- `502` – upstream ExHentai request failed (error detail is scrubbed of cookies/tokens).
- `503` – a backend service (downloader, database) is unavailable.
