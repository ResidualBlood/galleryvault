# Library Maintenance

> [中文](Manage) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers GalleryVault's maintenance tools, including deduplication (three tabs: duplicate copies, favorite duplicates, cross-GID duplicates), the recycle bin, missing page and corrupt image integrity checks, and runtime diagnostic logs.

## Duplicate Copies & Deduplication (`#/duplicates`)

- Accessible via "Management" → "Duplicates" in desktop navigation (legacy hash `#/duplicates` remains directly usable, defaulting to the "Duplicate copies" tab). The view provides three sub-tabs with dedicated direct links:
  - **Duplicate copies** (`#/duplicates?tab=copies`): When the same gallery (same gid) exists under **more than one scan root** (an EhViewer download directory, a CBZ archive, a manual copy), the scan keeps one copy automatically per the **duplicate-copy policy** (`duplicate_policy` in Settings) and records every other copy on this tab. Policies: `keep_first` (default — the already-stored copy wins), `prefer_more_pages`, `prefer_newer`, `prefer_larger` / `prefer_smaller`, `manual` (never auto-resolve — everything is listed for manual review). Each duplicate group shows every copy with a cover thumbnail, tags, page count, size and posted date (a *current* badge marks the active copy). Actions: **Keep this copy** (re-point the index at it), **Keep & delete others** (delete other copies' files from disk — paths restricted to scan roots), **Dismiss group** (hide it; restorable). The **Scan library** button triggers an immediate scan and refreshes the list upon completion (shows a paused notice when globally paused instead of starting a scan); pill filters for All / Pending / Dismissed display active highlights.
  - **Favorite duplicates** (`#/duplicates?tab=favorites`): Groups different re-uploaded versions of the same title within ExHentai favorite folders (normalized title + artist match); supports bulk unfavoriting, unfavoriting while deleting local copies, or ignoring groups. See the [Favorites](Favorites-EN) guide for details.
  - **Cross-GID duplicates** (`#/duplicates?tab=cross-gid`): Aggregates local library galleries with ExHentai cloud-only favorites across different GIDs (stripping event prefixes and normalizing titles and artists); cards display category, page count, and cover thumbnail; supports selecting items to bulk unfavorite, dismiss false positives, or delete downloaded local copies. Duplicates are clustered asynchronously after library scans and stored in an in-memory cache for sub-second page loads, with a manual "Refresh" button available.

## Recycle Bin (`#/recycle`)

- Default landing view of the "Management" navigation tab (legacy hash `#/recycle` remains directly usable). Two tabs: **User deleted** (library delete without removing files) and **Scan missing** (not found on disk during a scan).
- **Restore** puts galleries back in the library (user-deleted only; scan-missing ghosts are not restored into the library); **Purge** asks again whether to delete files on disk (purged-with-files will not be re-ingested on scan).
- Galleries in the recycle bin are **not** treated as “newer version already local” and will not trigger a hard-delete of the old copy.

## Missing Pages & Integrity (`#/integrity`)

- Accessible via the "Management" tab bar in desktop navigation (legacy hash `#/integrity` remains directly usable). Lists galleries whose recorded `page_count` disagrees with pages on disk, or that contain corrupt image files (unset page counts are excluded). Entering the page does **not** trigger an automatic full scan, keeping large libraries responsive.
- Split scan and repair workflow:
  - **Scan missing & corrupt pages** (`POST /api/galleries/integrity/scan`): Triggers a background scan task checking image magic headers (JPEG/PNG/WebP/GIF header validation) and 4-digit / 8-digit zero padding with ~30 concurrency; records execution duration and summary into task history (`#/logs`); skips scan when globally paused.
  - **Repair / re-download**: Select problematic galleries to re-download only missing and corrupt pages (inheriting original quality tier).

## Logs (`#/logs`)

Split into two tabs:

1. **Task Activity**: Displays background tasks (library scan, tag sync, thumbnail generation, favorites metadata sync):
   - **Running**: start time · task name · `running · done/total` · progress bar · description · **Cancel** button; multiple tasks run side by side.
   - **Finished**: start time · task name · status badge (success / failed / cancelled) · description & reason · **duration** · finish time; finished tasks no longer show a progress bar.
2. **System Logs**: Live diagnostic runtime logs from backend memory ring buffer:
   - **Dynamic log level**: Change runtime log level (`DEBUG` / `INFO` / `WARNING` / `ERROR`) on the fly without restarting containers;
   - **Real-time filtering & search**: Filter by minimum severity level (`INFO+`, `WARN+`, `ERROR+`) and instant text search;
   - **Exception tracebacks & context**: Expandable exception tracebacks, request IDs, worker correlation context (`gid` / `task_id`), and automated sensitive credential masking (`ipb_*` cookies, Telegram bot token, secrets);
   - **Export logs**: the **Export Log** button downloads `galleryvault.log` (ring buffer plus on-disk rotation via `GET /api/system/logs/download`, only files within the current log root) for sharing diagnostics;
   - **Noise filter**: successful httpx requests (2xx/3xx, including Telegram `getUpdates` 30s long-poll) are omitted; 4xx/5xx and business WARNING/ERROR (bot poll failures, notification send failures) are kept.

The page auto-refreshes every 2~3 seconds. The "Sync tags now / Generate now / Update translations now" buttons in Settings also leave a trace here.

> Tip: To inspect raw real-time container streams across Nginx, backend, and PostgreSQL side by side, see the [Deployment](Deployment-EN) guide for an optional Dozzle configuration recipe.
