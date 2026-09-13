# Library Maintenance

> [中文](Manage) · English | Part of the [Usage Guide](Usage-EN) series

Manage in the top bar lands on `#/recycle`. In-page tabs: **Recycle**, **Duplicate copies**, **Favorite duplicates**, **Cross-GID**, **Integrity**, **Cold archive**. Logs are under More → Logs (`#/logs`).

## Duplicate Copies & Deduplication (`#/duplicates`)

- The three dedupe tabs use **separate hashes** (no `?tab=`):
  - **Duplicate copies** (`#/duplicates`): When the same gallery (same gid) exists under **more than one scan root** (an EhViewer download directory, a CBZ archive, a manual copy), the scan keeps one copy automatically per the **duplicate-copy policy** (`duplicate_policy` in Settings) and records every other copy on this tab. Policies: `keep_first` (default — the already-stored copy wins), `prefer_more_pages`, `prefer_newer`, `prefer_larger` / `prefer_smaller`, `manual` (never auto-resolve — everything is listed for manual review). Each duplicate group shows every copy with a cover thumbnail, tags, page count, size and posted date (a *current* badge marks the active copy). Actions: **Keep this copy** (re-point the index at it), **Keep & delete others** (delete other copies' files from disk — paths are strictly validated with `Path.resolve()` against scan roots to prevent path traversal), **Dismiss group** (hide it; restorable). The **Scan library** button triggers an immediate scan and refreshes the list upon completion (shows a paused notice when globally paused instead of starting a scan); pill filters for All / Pending / Dismissed display active highlights.
  - **Favorite duplicates** (`#/duplicates/favorites`): Groups different re-uploaded versions of the same title in favorite folders (normalized title + artist). Bulk unfavorite, unfavorite+delete local copies, or ignore a group. Legacy `#/favorites/manage` opens the same page. Ignored items: `#/favorites/ignored`.
  - **Cross-GID duplicates** (`#/duplicates/cross-gid`): Aggregates local library galleries with cloud-only favorites across different GIDs (translations, revisions, uncensored uploads):
    - **Clustering & Scoring Mechanism**: The algorithm automatically strips doujinshi convention prefixes (e.g. `(C100)`, `(COMIC1☆15)`), scanlation group/circle tags (e.g. `[Group]`), and version suffixes (e.g. `[DL-raw]`, `[Chinese]`, `[Digital]`), extracting the canonical title and the `artist` namespace. A multi-tier Levenshtein distance and token similarity scoring algorithm identifies cluster candidates.
    - **Cloud vs. Local Comparison**: Within each cluster card, the interface displays local copies (annotated with gallery ID, storage path, physical page count, and image quality tier) side-by-side with uningested ExHentai cloud favorite entries (showing remote cover and posted date). Users can easily assess quality differences and make informed decisions: keep the optimal version, batch unfavorite redundant cloud items, safely purge duplicate local copies, or click **Dismiss group** to permanently ignore false positives (persisted across future scans). Clustered results are calculated asynchronously after library scans and stored in an in-memory cache for sub-second loads, with a manual **Refresh** button available.

## Recycle Bin (`#/recycle`)

- Default landing view of the "Management" navigation tab (legacy hash `#/recycle` remains directly usable). Two tabs: **User deleted** (library delete without removing files) and **Scan missing** (not found on disk during a scan).
- **Restore** puts galleries back in the library (user-deleted only; scan-missing ghosts are not restored into the library); **Purge** asks again whether to delete files on disk (purged-with-files will not be re-ingested on scan).
- Galleries in the recycle bin are **not** treated as “newer version already local” and will not trigger a hard-delete of the old copy.
- **High-Risk Deletion Guards & Secondary Confirmation**: Destructive operations are protected with defense-in-depth safety checks — clearing reading history (`/api/history`) and wiping global reading progress (`/api/galleries/progress`) require passing an explicit `?confirm=true` query parameter, accompanied by a front-end modal dialog; file deletion and duplicate cleanup strictly validate absolute paths against allowed root whitelists, which have been expanded to include archive roots (`archive_roots`, `archive_root`, and `cold_storage_root`) to safely manage and prune redundant cold-archive galleries without path-traversal risks; and filtered bulk deletion strictly rejects empty filter conditions to prevent unintentional full-library wiping.

## Cold archive (`#/archive`)

- Last Manage tab (`#/archive`). First set `archive_roots` under Settings → Library (one container path per line) and mount the volumes in compose (default `./archive:/archive` is commented out).
- **Start archive**: pack ingested galleries into CBZ, picking the root with the most free space. Names are always `gid-english-title.cbz` plus a `.galleryvault.json` sidecar. A volume is capped at **500 pages and 2GiB** (AND); larger galleries split. **Cancel archive** stops a run in progress.
- **Purge archived sources**: after a valid CBZ exists on the cold side, delete the matching unpacked folder in the hot download root. Skips `pending` / `downloading` tasks. The same button is on the Settings storage table. Progress shows on `#/logs`.
- Nothing is packed or deleted until you configure roots and start a run.

## Missing Pages & Integrity (`#/integrity`)

- Accessible via the "Management" tab bar in desktop navigation (legacy hash `#/integrity` remains directly usable). Lists galleries whose recorded `page_count` disagrees with pages on disk, or that contain corrupt image files (unset page counts are excluded). Entering the page does **not** trigger an automatic full scan, keeping large libraries responsive.
- **Split Scan & Incremental Repair Workflow**:
  - **Scan missing & corrupt pages** (`POST /api/galleries/integrity/scan`): Click **Scan** in the toolbar to initiate a background inspection. The scanner processes on-disk files at 2 worker concurrency:
     - **Magic Header Validation**: Reads the file header (up to 20 bytes in the implementation) to verify JPEG (`FF D8 FF`), PNG (`89 50 4E 47`), GIF (`47 49 46 38`), and WebP (`RIFF....WEBP`) signatures, alongside 4-digit / 8-digit zero-padding filename checks. This catches truncated image downloads, cloud anti-hotlink 403/503 HTML error pages inadvertently saved as images, and zero-padded sequence misalignments.
    - **Execution Tracking**: Total scan time, scanned file counts, and detected corrupt galleries are recorded in task history (`#/logs`). If globally paused, the page displays a paused notification and refrains from scheduling workers.
  - **Incremental Missing/Corrupt Page Repair**:
    - Galleries with issues are highlighted in red, showing the delta between cataloged page count and valid on-disk images;
    - Users can click **Repair** on an individual card or **Select All & Repair** in the toolbar for batch self-healing;
    - Repairs are dispatched through an incremental patch pipeline that **only re-downloads missing or signature-corrupted pages**, reusing the gallery's configured quality tier (resample or original) while leaving intact pages untouched. This immediately heals the archive while conserving ExHentai download limits and bandwidth.

## Logs (`#/logs`)

Split into two tabs:

1. **Task Activity**: Displays background tasks (including library scan, tag sync, thumbnail generation, favorites metadata sync, duplicate scans, gallery update detection, as well as silent inspection and maintenance tasks such as orphan thumbnail cleanup, periodic thumbnail seeding, download retry sweep, Cookie health checks, and storage calibration):
   - **Running**: start time · task name · `running · done/total` · progress bar · description · **Cancel** button; multiple tasks run side by side.
   - **Finished**: start time · task name · status badge (success / failed / cancelled) · description & reason · **duration** · finish time; finished tasks no longer show a progress bar.
   - **Silent Tasks & Automated Observability**: In addition to front-end initiated actions, the system comprehensively tracks and displays periodic background tasks (such as orphan thumbnail cleanup, missing thumbnail seeding, failed download exponential backoff retry sweeps, Cookie session health checks, and storage usage calibration). Whether running or completed, their execution progress, duration, and status are clearly visible in the task activity list.
   - **Idle Task History Suppression**: To prevent poll noise from flooding the audit trail, periodic background workers (such as failed download retry sweeps) suppress logging when there are 0 tasks awaiting retry, skipping empty completion records in `task_history` so critical operational events and errors remain prominent.
2. **System Logs**: Live diagnostic runtime logs from backend memory ring buffer:
   - **Dynamic log level**: Change runtime log level (`DEBUG` / `INFO` / `WARNING` / `ERROR`) on the fly without restarting containers;
   - **Real-time filtering & search**: Filter by minimum severity level (`INFO+`, `WARN+`, `ERROR+`) and instant text search;
   - **Exception tracebacks & context**: Expandable exception tracebacks, request IDs, worker correlation context (`gid` / `task_id`), and automated sensitive credential masking (`ipb_*` cookies, Telegram bot token, secrets);
   - **Export logs**: the **Export Log** button downloads `galleryvault.log` (ring buffer plus on-disk rotation via `GET /api/system/logs/download`, only files within the current log root) for sharing diagnostics;
   - **Noise filter**: successful httpx requests (2xx/3xx, including Telegram `getUpdates` 30s long-poll) are omitted; 4xx/5xx and business WARNING/ERROR (bot poll failures, notification send failures) are kept.

The page auto-refreshes every 2~3 seconds. The "Sync tags now / Generate now / Update translations now" buttons in Settings also leave a trace here.

> Tip: For raw Nginx / backend / database streams use `docker compose logs -f` or `docker logs galleryvault-backend --since 5m`. The default compose stack does not include Dozzle.
