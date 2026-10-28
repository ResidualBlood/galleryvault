# Favorites & Updates

> [中文](Favorites) · English | Part of the [Usage Guide](Usage-EN) series

ExHentai favorite-folder sync, watch modes, favorite dedupe, and re-uploaded GID replacement management.

## Favorites (`#/favorites`)

- **Prerequisites**: Requires configured ExHentai cookies (see [Usage Guide: Cookie Setup](Usage-EN#configuring-exhentai-cookies) or [Settings](Settings-EN) → ExHentai; stored encrypted in the database). Without cookies, checks will fail and cannot read favorite contents or covers.
- **Overview & Basic Controls**:
  - Lists the 10 ExHentai favorite folders (folders 0–9), displaying cloud count, local count, and disk usage; a progress ring appears beside the folder name while a check is running. If the cloud counts page cannot be parsed, that result is treated as unknown (never as 0), the list falls back to the recorded cloud count, and the unknown result is cached only briefly (about 60 seconds) before retrying.
  - **Sync folder names**: Pulls cloud custom folder names from ExHentai.
  - **Check now**: Manually scans the selected folder; **Check all folders**: Checks all folders at once.
  - **Save**: Saves modifications to folder enable toggles, watch modes, and polling intervals all at once.
  - **Download missing items**: Spawns an overview pass across all checked folders to complete missing local cover thumbnail cache files on disk (25 per batch; for list display and duplicate group inlining). Triggering it again while a favorites metadata sync is already running returns 409 instead of starting a second pass.
- **Metadata Caching & Skip Rules**:
  - Every check fetches full metadata (title, tags, category, posted date, size) and caches it in the local database; for already downloaded local galleries, fresh metadata is applied automatically (updating tags, category, title, posted date, and size), skipping when nothing changed. When a fetched payload omits fields (some entries lack title, posted date, size, or tags), the cached values are kept instead of being overwritten with empties, and a true `expunged` flag stays true.
  - Checks automatically warm cloud covers into local disk cache. Opening a folder subsequently reads local disk only (`/api/favorites/cover?gid={gid}&token={token}`) without waiting on external requests.
  - **Skip heuristic (scheduled polling only)**: During scheduled checks, if live cloud count matches known local count, full re-scanning is skipped immediately; after 4 consecutive skips, the 5th check forces a full scan. If live cloud count changes, the counter resets immediately and a full scan runs (clicking "Check now" never triggers skips, running a full check directly).
  - **Truncated listing protection**: A failed page fetch or an early-ended listing fails the whole check without deleting local records; if one check returns fewer than 50% of the recorded items and at least 20 items are recorded, pruning is skipped for that run and a warning is logged, so a truncated page is not mistaken for a mass unfavorite. The next successful full check prunes items that really disappeared.
  - **Folder emptied in the cloud**: When the favorites page header reports 0 items and the listing page parsed successfully, the folder is treated as confirmed empty and the recorded local rows are pruned; a parse failure or a listing judged truncated never prunes.
- **Folder Gallery Grid (`#/favorites/<favcat>`)**:
  - Click a folder name to open the gallery grid view (24 items per page by default, with infinite scrolling and a bottom pager fallback).
  - **Search & Sorting**: Top toolbar provides real-time title filtering; supports multi-criteria sorting by first added date, last added date (default), posted date, title, and file size.
  - **Filtering**: Supports All, Local only, and Cloud only state filters; provides a collapsible advanced filter panel (local star rating, page count range, file size, posted date, uploader, image quality, language, and local lists).
  - **Select All & Move**: Toolbar provides "Select All" for currently rendered cards (scroll down to load new cards and click again to merge into selection); supports batch moving to other favorite folders (folders 0–9), syncing local records after ExHentai cloud confirmation succeeds.
- **Batch Download & Original Upgrade Rules**:

| Action Button | Quality Rule | Uningested Gallery (Not in Library) | Ingested Gallery (Already Local) |
| :--- | :--- | :--- | :--- |
| **Download selected** | Follows global setting (default resample) | Enqueues normally | Skipped (not re-queued; remains skipped even if global setting is original, preventing duplicate upgrades) |
| **Download selected original** | Forces page-by-page original quality | Enqueues normally | Skipped if local copy is already original; enqueues page-by-page original upgrade if local copy is resample/unknown, deleting superseded copies (including CBZ) upon ingest |
| **Archive download selected** | Tier (original or resample) chosen in cost preview popup | Enqueues normally | Skipped if local copy is already original; triggers archive original upgrade if local copy is non-original and original tier is selected, deleting old copy upon ingest; skipped if resample tier is selected |

For official archive channel cost previews, Range resumption, and fallback policies, see [Download Management → Archive Downloads (ExHentai Archive)](Downloads-EN#archive-downloads-exhentai-archive).

## Favorite duplicates (`#/duplicates/favorites`)

- **Entry**: Located under **Manage → Favorite duplicates** (legacy path `#/favorites/manage` redirects here automatically).
- **Scanning & Actions**:
  - Click **Scan for duplicate galleries**; different versions of the same work (digital editions, uncensored releases, different language versions) are grouped and displayed by work.
  - Supports batch **Remove from favorites**, or **Remove from favorites and delete local copy** (deletes all physical files and CBZ copies for that gallery GID under library roots).
- **Safety & Read-Only Protection**:
  - Favorite removals update local records only after cloud confirmation succeeds.
  - Logout, rate-limit, or ban pages returned by the cloud are treated as failures: local favorite state and files stay unchanged, and failed GIDs never update local records (the API lists them under `cloud_failed`).
  - If underlying storage is mounted read-only and physical file deletion fails, an alert is displayed and logged while database records are retained, preventing future scans from misidentifying the gallery as a new item.
- **False Positive Management**: Click **Ignore selected** for items that do not require processing; view and restore ignored entries under `#/favorites/ignored`.

## Gallery Updates (`#/updates`)

- **Entry & Detection**:
  - Accessible via the top row of the Favorites page, or directly at `#/updates`.
  - When an ExHentai gallery is re-uploaded, the cloud creates a new GID and the favorites entry follows the new version, while local storage retains the old GID copy. This page lists local galleries holding superseded versions (matching rule: local gallery GID is not contained in any current favorite folder, but normalized title matches an existing favorite entry), displaying `old GID → new GID` per row.
  - Detection runs automatically after each favorites check, and can also be triggered manually with **Scan now**.
- **Update Workflow & Old Copy Clean-up**:
  - Supports selecting items to execute **Update selected** (quality follows global setting), **Update selected original** (forces page-by-page original), or **Archive update selected** (tier selected via popup).
  - When updating, the system downloads the new version first; **superseded local files are deleted only after the new version is downloaded and ingested successfully** (reading progress resets accordingly).
  - If an incremental or forced check has already downloaded the new GID gallery into the library, detection automatically removes superseded local copies (the corresponding entry in the Updates page clears automatically). When batch-downloading from the favorites page, matching update rows are linked to the download task and superseded copies are automatically cleaned up upon ingest.
- **Failures & Ignore Handling**:
  - If a running update download task is deleted from the task management page, the update entry is marked as **failed** and retained here; filter by **Failed** and click **Delete selected** to clear failure records (clears update list records only without affecting download task history). After bulk deletion on the last page, if the current page exceeds the new total page count the list moves back to the previous page.
  - Click **Ignore selected** for false positives (ignored items will not auto-delete superseded local copies even if the new version is ingested); restore ignored items under `#/updates/ignored`. The default (active) view's `total` excludes ignored entries.

## "download favorites" vs. "enabled"

- **download favorites (Global Setting)**: System setting master switch for automatic scheduled checks; controls whether background workers perform automated checks and downloads by polling intervals.
- **enabled (Folder Option)**: Per-folder toggle in favorites configuration; controls whether the folder participates in scheduled checks, and whether downloads are allowed during checks (unchecked folders only record metadata and never download). Newly added or disabled folders are unchecked by default and require manual activation and saving.
- **Automatic Download Trigger Conditions**:
  All three conditions must be satisfied simultaneously for the system to automatically download missing galleries:
  1. Global **download favorites** master switch in System Settings is turned on;
  2. Target favorite folder has its **enabled** checkbox turned on;
  3. Target favorite folder run mode is set to **incremental download** or **force download**.
- **Manual Check Behavior**:
  Clicking "Check now" manually is not gated by the global **download favorites** master switch; however, if the target folder is not toggled "enabled", manual checks still only record metadata without triggering downloads.
- **Large Gallery Archive Download Integration**:
  When "Archive large favorites on scheduled scan" is enabled:
  - Candidates filtered by automatic checks batch-fetch total page counts in advance.
  - Items with page counts exceeding the "archive page threshold" (set to 0 for all galleries) switch automatically to ExHentai official archive full package downloads (quality tier follows "Archive quality"), while galleries below threshold continue page-by-page.
  - If page count fetching fails, it falls back safely to page-by-page download; if the official archive channel cannot obtain the specified tier package, it defaults to page-by-page download (fallback toggleable in Settings; see [Download Management](Downloads-EN)).

## The Three Modes

Every check records all galleries within the folder into the local database (`favorite_items` table). The three modes differ only in candidate download scope and existing local item handling:

| Mode | Records Metadata | Candidate Download Scope | Existing Local Item Handling |
| :--- | :--- | :--- | :--- |
| **Incremental download** | Yes (full recording) | Galleries **seen for the first time** only (new GID previously absent in local records) | Galleries already existing in the local library are skipped directly |
| **Watch only** | Yes (full recording) | Does not download any galleries (candidate scope is empty) | No downloads performed |
| **Force download** | Yes (full recording) | All galleries in folder **not present in local gallery library (`galleries` table)** | Galleries already existing in the local library are skipped directly without duplicate downloads |

**Backlog Favorites in Incremental Mode**:
- In incremental download mode, once a folder has completed a check, all existing backlog galleries are written into local records. Even if not previously downloaded, they are no longer treated as "first seen", and therefore **will not trigger downloads in incremental mode**.
- To download already-recorded historical backlog galleries, temporarily switch folder mode to **force download** and click "Check now" (or tick target galleries within `#/favorites/<favcat>` and click "Download selected" / "Download selected original" / "Archive download selected"). Once all queued downloads finish, switch back to **incremental download** to resume tracking only newly added favorites.
