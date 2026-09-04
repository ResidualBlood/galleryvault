# Library Maintenance

> [中文](Manage) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers GalleryVault's maintenance tools, including duplicate copy resolution, the recycle bin, missing page integrity checks, and runtime diagnostic logs.

## Duplicate Copies (`#/duplicates`)

- Accessible via the "Management" tab bar in desktop navigation (legacy hash `#/duplicates` remains directly usable). When the same gallery (same gid) exists under **more than one scan root** (an EhViewer download directory, a CBZ archive, a manual copy), the scan keeps one copy automatically per the **duplicate-copy policy** (`duplicate_policy` in Settings) and records every other copy on this page.
- Policies: `keep_first` (default — the already-stored copy wins), `prefer_more_pages`, `prefer_newer`, `prefer_larger`, `prefer_smaller`, `manual` (never auto-resolve — everything is listed for manual review).
- Each duplicate group shows every copy with a cover thumbnail, tags, page count, size and posted date; the copy the index currently points at carries a *current* badge.
- Actions: **Keep this copy** (re-point the index at it), **Keep & delete others** (delete the other copies' files from disk — paths are restricted to the scan roots), **Dismiss group** (hide it; restorable).
- The **Scan library** button triggers an immediate scan and refreshes the list upon completion (shows a paused notice when globally paused instead of starting a scan); pill filters for All / Pending / Dismissed display active highlights; dismissed groups stay hidden until the on-disk copies actually change.

## Recycle Bin (`#/recycle`)

- Default landing view of the "Management" navigation tab (legacy hash `#/recycle` remains directly usable). Two tabs: **User deleted** (library delete without removing files) and **Scan missing** (not found on disk during a scan).
- **Restore** puts galleries back in the library (user-deleted only; scan-missing ghosts are not restored into the library); **Purge** asks again whether to delete files on disk (purged-with-files will not be re-ingested on scan).
- Galleries in the recycle bin are **not** treated as “newer version already local” and will not trigger a hard-delete of the old copy.

## Missing Pages (`#/integrity`)

- Accessible via the "Management" tab bar in desktop navigation (legacy hash `#/integrity` remains directly usable). Lists galleries whose recorded `page_count` disagrees with pages on disk (unset page counts are excluded).
- **Repair / re-download** only fetches the missing pages.

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
