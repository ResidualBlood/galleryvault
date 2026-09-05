# Favorites & Updates

> [中文](Favorites) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers ExHentai favorites synchronization, monitoring policies, favorites deduplication, and gallery updates in GalleryVault.

## Favorites (`#/favorites`)

- Lists the ten ExHentai favorite folders: an enable toggle, a mode (incremental download / watch only / force download) and the polling interval; **Save** writes it all at once.
- **Sync folder names** pulls the folder names from ExHentai.
- **Check now** scans one folder; **Check all folders** scans them all.
- Each folder shows cloud/local counts and sizes; a **progress ring** appears next to the name while a check is running.
- Every check caches the full metadata (title, tags, category, posted date, size) into the database and **applies the fresh metadata** to already downloaded galleries (tag replacement, category/title/posted/size refresh), skipping when nothing changed, so repeated checks are cheap.
- **Skip heuristic**: after several consecutive checks (5) report an unchanged folder count, the full re-scan is skipped (count-only checks continue) to avoid needless network traffic and missed-detection risk; the moment the count changes, full checks resume automatically.
- Click a folder name to open `#/favorites/<favcat>`: that folder's gallery grid (with **title search**, **multi-criteria sorting**, checkboxes, **select all**, **download selected**, **download selected original**, **archive download selected**, **move selected**, **remove from favorites**, and an **All / local only / cloud only** state filter). **Check now** warms cloud covers onto disk; opening a folder only reads that cache (`<img>` via `/api/favorites/cover`) and does not wait on ExHentai. The list uses numbered pagination with 24 galleries per page by default.
  - **In-folder Search & Sorting**: Top toolbar provides instant title filtering and sorting by last seen, first seen, posted date, title, and size.
  - **Advanced filters**: Provides a collapsible advanced filter panel (aligned with the library) supporting local star rating, page range, file size, posted date, uploader, image quality, language, and local lists, with an active filter count indicator.
  - **Select all**: Inside a favorite folder (`#/favorites/:id`), the toolbar provides "Select All" to the left of "Clear Selection"; selection applies to currently rendered cards only (cards not yet loaded into DOM via infinite scroll are not selected), and clicking again after scrolling merges newly rendered cards into the selection.
  - **Move selected**: Move selected galleries to another favorite folder (0–9), syncing both ExHentai cloud favorites and local records.
  - **Batch downloads & original upgrades**: The toolbar supports three batch download actions, handling already-ingested galleries as follows:
    - **Download selected**: Uningested galleries enqueue normally; already-ingested galleries are still skipped.
    - **Download selected original**: Uningested galleries enqueue as usual; galleries already stored as original are skipped; local resample/unknown copies undergo page-by-page original upgrades, and superseded copies (including CBZ) are deleted upon ingest.
    - **Archive download selected**: Uningested galleries enqueue as usual; galleries already stored as original are skipped; local non-original galleries trigger a `gallery_archive` original upgrade if the user selects the original tier in the cost preview, but remain skipped if resample is selected.
- The **Download missing items** button on the Favorites overview spawns a per-folder pass that downloads cover files for every gallery missing one on disk (shown inline in lists and duplicate groups).
- Configuring **ExHentai cookies** (see [Usage Guide: Cookie Setup](Usage-EN#configuring-exhentai-cookies) or [Settings](Settings-EN) → ExHentai, stored encrypted in the database) is required — checks will fail and no favorites/covers are fetched without them.
- **Archive Downloads & Updates**: Supports downloading or updating selected galleries via ExHentai's official zip channel (with a cost/balance preview popup); for details on execution, Range resumption, and fallback policies, see [Download Management → Archive Downloads](Downloads-EN#archive-downloads-exhentai-archive).

## Favorites Management & Deduplication (`#/favorites/manage`)

- **Scan for duplicate galleries** groups different versions of the same work (DL / uncensored / language re-uploads) so you can bulk **unfavorite** or **unfavorite and delete the local copy** — this deletes every physical copy of the gid under the library roots; if a copy cannot be deleted (e.g. a read-only mount or permission problem) the toast and the Logs page report it, and the gallery row is kept so the next scan does not re-import it as a fresh gallery; false positives can be hidden with **Ignore selected**, and ignored items can be viewed and restored from the **Ignored items** page (`#/favorites/ignored`).

## Gallery Updates (`#/updates`)

- Linked from the top row of the Favorites page (legacy hash `#/updates` remains directly accessible). When ExHentai **re-uploads** a gallery it moves it to a new gid and the favorites entry follows the new version, leaving the old-gid copy on disk. This page lists those "local copy is the old version" galleries (detected by "local gid not in any favorite folder, but normalized title matches a favorite item"), showing `old gid → new gid` per row.
- Check rows and hit **Update selected**: the new version downloads first, then the old local copy is removed (its reading progress resets). If an incremental/force favorites check **already downloaded the new gid**, detection deletes the old copy immediately (the row disappears) — no need to click Update selected. Enqueueing from favorites also pins any existing update row to that download task, and a successful ingest finalizes the same way.
- Detection runs automatically after every favorites check and can be triggered with **Scan now**; false positives can be ignored (ignored rows are never auto-deleted even if the new gid is already local), and ignored items are restored from `#/updates/ignored`.
- When a download task is deleted from the tasks page, its update entry is marked **failed** and kept here; under the **failed** filter you can use **Delete selected** to permanently remove those records (this only cleans the page's history, it never touches the tasks page).

## "download favorites" vs. "enabled"

- **download favorites** in Settings is the global **automatic scheduled check** master switch (checks by polling interval and downloads missing galleries).
- The **enabled** checkbox per folder on the Favorites page decides whether that folder takes part in the scheduled checks and whether it downloads during them (unchecked = record only, never download). New folders are disabled by default and require checking and saving.

For automatic downloads all three must hold: the master switch is on + the folder is checked + the mode is "incremental/force download". A manual **Check now** is not gated by the master switch, but an unchecked folder only records even when checked manually.

With **"Archive large favorites on scheduled scan"** enabled, the scheduled check batch-fetches page counts for its candidates first: galleries above the **archive page threshold** (0 = all) go through the archive channel (tier = "Archive quality"), the rest download page-by-page as usual. If the page-count fetch fails, the check safely falls back to page-by-page. A gallery the archive channel cannot serve (e.g. the selected tier does not exist) also automatically falls back to page-by-page (Settings-toggleable, see [Download Management](Downloads-EN)).

## The Three Modes

Every check records **all** folder galleries into the local set (`favorite_items`); the modes differ only in which galleries are candidates for download:

- **Incremental download**: only downloads galleries **seen for the first time** — gids not yet recorded locally (i.e. newly added to the folder). So after a folder has been checked once, the existing favorites are *not* downloaded by incremental mode (they are already recorded and no longer count as "new").
- **Watch only**: records counts/sizes, never downloads.
- **Force download**: skips the recorded-set filter and queues **every gallery in the folder that is not already in the local library** (the `galleries` table). Galleries already in the library are still skipped, so nothing is re-downloaded.

Incremental and force both skip galleries already in the local library. To pull down an already-checked folder's backlog, temporarily switch the mode to **force download** and run **Check now** (or tick **Download selected** inside `#/favorites/<favcat>`; use **Download selected original** or **Archive download selected** for original upgrades), then switch back to incremental to follow only new additions again.
