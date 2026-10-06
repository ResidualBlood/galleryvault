# Library Maintenance

> [中文](Manage) · English | Part of the [Usage Guide](Usage-EN) series

Manage in the top bar lands on `#/recycle`. In-page tabs: **Recycle**, **Duplicate copies**, **Favorite duplicates**, **Cross-GID**, **Integrity**, **Cold archive**. Logs are under More → Logs (`#/logs`).

## Duplicate Copies & Deduplication (`#/duplicates`)

The three dedupe tabs use independent hashes (no `?tab=` parameter):

### Duplicate copies (`#/duplicates`)

When the same gallery (same GID) exists across multiple scan roots (e.g. EhViewer download directory, CBZ archive, manual copy), the scan keeps one copy automatically according to the `duplicate_policy` setting and records extra copies on this tab.

| Policy value (`duplicate_policy`) | Retention rule |
| :--- | :--- |
| `keep_first` (default) | Prioritizes the copy already ingested into the library |
| `prefer_more_pages` | Prioritizes the copy with more pages |
| `prefer_newer` | Prioritizes the copy with a newer posted date |
| `prefer_larger` | Prioritizes the copy with larger file size |
| `prefer_smaller` | Prioritizes the copy with smaller file size |
| `manual` | Requires manual review; no automatic retention |

- **Scan**: Click **Scan library** in the toolbar to rescan the library and refresh the list. When globally paused, the page displays a paused notification and does not trigger a scan.
- **Selection & display**: Each group displays cover thumbnail, tags, page count, size, and posted date, with a "Current" badge indicating the active index target. Groups can be filtered by "All / Pending / Dismissed" status.
- **Execution**:
  - **Keep this copy**: Re-points the library index to this copy.
  - **Keep & delete others**: Retains the selected copy and deletes remaining copy files. Paths are verified via `Path.resolve()` to strictly reside within configured scan roots before deletion to prevent path traversal; deletion is rejected if any path validation fails or if the filesystem is read-only.
- **Dismiss & restore**: Click **Dismiss group** to hide the duplicate group; can be reviewed and restored later via the "Dismissed" filter option.

### Favorite duplicates (`#/duplicates/favorites`)

Groups different re-uploaded versions of the same title across favorite folders (normalized title + artist).

- **Actions**: Supports batch unfavorite, unfavorite and delete local copies, or dismiss group. Dismissed groups can be viewed and restored under `#/favorites/ignored`.
- **Note**: Legacy route `#/favorites/manage` automatically redirects to this page.

### Cross-GID duplicates (`#/duplicates/cross-gid`)

Aggregates local library galleries with cloud favorites across distinct GIDs to identify re-uploads, translations, and revisions:

- **Clustering & scoring**: The algorithm strips doujinshi convention prefixes (e.g. `(C100)`, `(COMIC1☆15)`), scanlation group and circle tags (e.g. `[Group]`), and version suffixes (e.g. `[DL-raw]`, `[Chinese]`, `[Digital]`), extracting the canonical title and the `artist` namespace to score clusters via weighted edit distance and token similarity.
- **Local vs cloud comparison**: Displays local ingested copies (gallery ID, disk path, page count, quality) alongside uningested cloud favorites (cover, posted date).
- **Actions & recomputation**: Supports batch unfavorite of redundant cloud items, deletion of local duplicate copies, or clicking **Dismiss group** (ignored in subsequent scans). Clustering is computed in the background after scans and cached in memory; click **Refresh** to recompute.

## Recycle Bin (`#/recycle`)

- Default landing view of the Manage menu (direct access via `#/recycle` remains available). Two tabs: **User deleted** (removed from library without deleting files from disk) and **Scan missing** (not found on disk during scans).
- **Restore**: Restores selected items back into the library (user-deleted galleries only; scan-missing entries are not restored into the library).
- **Purge**: Prompts for confirmation before deleting disk files. When disk deletion is selected, the item is staged in the Recycle Bin and removed from the index only after disk deletion succeeds; if deletion fails, the item remains in the Recycle Bin. If any copy path falls outside the scan root whitelist, the entire gallery is skipped without deleting sibling files.
- **Semantic protection**: Galleries in the Recycle Bin are not treated as "newer version in library" and will not trigger old version cleanup. Clearing history (`/api/history`) and resetting progress (`/api/galleries/progress`) require `?confirm=true`, prompting a confirmation modal. Deleting files and purging duplicate copies require absolute paths to reside within scan roots or archive roots (`archive_roots`, `archive_root`, `cold_storage_root`); filtered bulk deletion is rejected when no filter criteria are provided.

## Cold archive (`#/archive`)

- Manage tab `#/archive`. First configure `archive_roots` under **Settings → Library** (container paths, one per line) and mount the volumes in Compose. Storage topology and path rules are detailed in [Deployment Guide → Tiered Storage & Multi-Disk Mounting](Deployment-EN#tiered-storage--multi-disk-mounting).
- **Start archive**: Packs ingested galleries into CBZ, selecting the archive root with the most free space. Target path: `{cold}/cbz/{hh}/{ii}/{gid}-{DB English title}.cbz`. `.galleryvault.json` and `ComicInfo.xml` are packaged inside the archive. Volumes are capped at 500 pages and 2GiB; galleries exceeding these limits are packed into `{cold}/dir/{hh}/{ii}/{gid}/` directories. Click **Cancel archive** to stop a running task.
- **Purge archived sources**: After a valid CBZ is generated on cold storage, deletes matching unpacked folders in the hot download directory. Skips tasks in `pending` or `downloading` state. The same action is available in the Settings storage panel; task progress can be monitored in `#/logs`.
- Without configured archive roots or explicit user trigger, the system does not automatically pack archives or delete source files.

## Missing Pages & Integrity (`#/integrity`)

- Access via `#/integrity`. Lists galleries where recorded page count disagrees with files on disk, or that contain corrupt image files (galleries without recorded page counts are excluded). Opening the page does not trigger an automatic scan.
- **Scan missing & corrupt pages** (`POST /api/galleries/integrity/scan`): Click **Scan** in the toolbar to start a background inspection running at 2 worker concurrency:
  - **Magic header & naming validation**: Reads up to 20 bytes of file headers to verify JPEG (`FF D8 FF`), PNG (`89 50 4E 47`), GIF (`47 49 46 38`), and WebP (`RIFF....WEBP`) magic numbers, alongside 4-digit / 8-digit zero-padded naming, detecting truncated images, anti-hotlink 403/503 HTML error pages, and sequence gaps;
  - **Execution tracking**: Writes scan duration, scanned file count, and corrupt gallery count to task history (`#/logs`); displays a paused notice and refrains from starting scans when globally paused.
- **Incremental repair**:
  - Highlights abnormal galleries in red, showing recorded page count alongside valid on-disk image count;
  - Click **Repair** on a gallery card or **Select All & Repair** in the toolbar;
  - Repair re-downloads only missing or validation-failed pages; intact pages are preserved, using the gallery's original quality tier (original or resampled). Detailed logs are available in `#/logs`.

## Logs (`#/logs`)

Split into two tabs:

1. **Task Activity**: Displays background tasks (including library scans, tag synchronization, thumbnail generation, favorite metadata sync, duplicate scans, gallery update checks, and silent maintenance tasks such as orphan thumbnail cleanup, periodic thumbnail seeding, download retry sweeps, Cookie health checks, and storage capacity calibration):
   - **Running**: Start time · task name · `running · done/total` · progress bar · description · **Cancel** button; multiple tasks run side by side.
   - **Completed**: Start time · task name · status badge (success / failed / cancelled) · description & reason · **duration** · finish time; completed tasks do not display progress bars.
   - **Silent tasks & automated observability**: In addition to manually triggered operations, the system tracks periodic background maintenance tasks (orphan thumbnail cleanup, missing thumbnail seeding, failed download exponential backoff retries, Cookie session health checks, and disk usage calibration). Execution duration, details, and status can be inspected in the activity panel.
   - **Idle task history suppression**: High-frequency periodic workers (such as failed download retry sweeps) suppress logging when 0 tasks are awaiting retry, skipping empty records in `task_history` to keep operational logs clear.
2. **System Logs**: Live diagnostic runtime logs from the backend memory ring buffer:
   - **Dynamic log level**: Change global log level (`DEBUG` / `INFO` / `WARNING` / `ERROR`) online without restarting containers;
   - **Real-time filtering & search**: Filter by minimum severity level (`INFO+` / `WARN+` / `ERROR+`) and instant text search;
   - **Exception stack traces & context**: Expandable exception tracebacks with request IDs, worker coroutine context (`gid` / `task_id`), and automated sensitive credential masking (`ipb_*` cookies, Telegram bot token, secrets);
   - **Export logs**: Click **Export Log** to download `galleryvault.log` (ring buffer plus on-disk rotated files via `GET /api/system/logs/download`, restricted to the current log root);
   - **Noise filtering**: Successful httpx requests (2xx/3xx, including Telegram `getUpdates` 30s long-polling) are omitted; 4xx/5xx responses and application WARNING/ERROR events remain logged.

The page auto-refreshes every 2~3 seconds. The "Sync tags now / Generate now / Update translations now" buttons in Settings also leave a trace here.

> Tip: For raw Nginx / backend / database streams use `docker compose logs -f` or `docker logs galleryvault-backend --since 5m`. The default compose stack does not include Dozzle.
