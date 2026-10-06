# Gallery Details & Reader

> [中文](Reading) · English | Part of the [Usage Guide](Usage-EN) series

Gallery details, tag synchronization, and the web reader.

## Gallery Detail (`#/gallery/<id>`)

### Page Information & Action Entries

| Entry / Area | Description & Supported Actions | Outcome & Constraints |
| :--- | :--- | :--- |
| **Metadata & Tags** | Displays gallery size (adaptive units), categories, tags, and page thumbnails. Clicking a tag jumps to the library and appends it to the active filter (syntax in [Browsing & Library](Library-EN)). If `uploader` namespace tags exist, this group is pinned to the end of all tag groups; omitted when no uploader exists. | Displays local database records only without initiating remote network requests. |
| **Thumbnail List** | Defaults to 30 items per page (switchable between 5 / 30 / 50 / 100 / 200 / 500, persisted across sessions). Supports infinite scroll (a "Load more" button appears after ~5 batches) alongside the bottom pager. | Automatically navigates to the batch matching your last reading progress; an explicit `?page=` query parameter takes precedence. |
| **Reading & Slideshow** | Click "Start reading" to enter the reader at your last recorded page. The top toolbar provides "▶ Slideshow" and interval settings (in seconds) to enter the reader directly in fullscreen auto-advance mode. | Reading progress and preferences are saved automatically; slideshow controls are unavailable in Webtoon mode. |
| **Export CBZ** | Click "Export CBZ" to package and download the full gallery. | On-disk `.cbz` files are served directly; directory galleries are streamed and packed in page order without modifying on-disk storage structures. |
| **Open on ExHentai** | Click "Open on ExHentai" to navigate to the ExHentai gallery page (`{base}/g/{gid}/{token}/`) in a new browser tab. | Requires an active ExHentai login session in the browser; button is hidden if no gallery token is stored locally. |
| **Tag Sync** | Explicitly click "Sync tags" (`POST /api/galleries/{identifier}/sync-tags`) or trigger synchronization via background tasks. | Reuses local metadata cache if available; ExHentai-only galleries pause synchronization when configured with the public mirror (`e-hentai.org`), resuming when switched back to `exhentai.org`. |
| **Local Annotation & Favorites** | The "More" menu supports 1–5 star local ratings, custom notes, and `local:` prefixed tags (which are never overwritten by tag sync). Displays favorite folder badges. | Supports adding unfiled galleries to folders 0–9, moving folders, and removing favorites; updating favorite notes and folder states requires verified ExHentai cloud confirmation before updating local records. |
| **Quality & Upgrade to Original** | Displays quality badges (Original / Resampled) next to favorite folder indicators. For resampled galleries with an ExHentai gid, the toolbar offers "Download original" (page-by-page, zero GP cost) and "Archive-download original" (zip archive package, consumes GP; details in [Downloads](Downloads-EN)). | Deletes the superseded resampled copy automatically upon completion if page counts match; if the storage volume is read-only, prompts for manual deletion while keeping the download task intact. |

### Uploader retrieval and backfill

- **Source & Queue**: Background workers scan unsynced galleries on service startup and during new ingestion, enqueuing them automatically.
- **Automatic Backfill**: Prioritizes local metadata cache reuse; queries batch gdata when cache is absent or forced sync is requested, falling back to gallery HTML parsing if gdata fails or returns incomplete fields.
- **Tag Usage**: Once resolved, the uploader is stored on the gallery record and indexed as a `namespace="uploader"` tag; searchable in the library via exact `uploader:"..."` or prefix `uploader:name*` queries, see [Browsing & Library](Library-EN).

## Reader (`#/reader/<id>/<page>`)

### Reading Modes & Shortcut Operations

The reader streams pages dynamically, offering multiple layout modes and control schemes:

| Mode | Navigation Controls | Display Characteristics & Differences |
| :--- | :--- | :--- |
| **Default (LTR)** | `←` Previous page, `→` / `Space` Next page; click left/right half of reader area | Single page centered and scaled to fit; standard reading order. |
| **Manga (RTL)** | `→` Previous page, `←` / `Space` Next page; click right half for previous, left half for next | Keyboard arrows and touch navigation directions are inverted. |
| **Double Page** | Same navigation as LTR mode | Side-by-side spread on widescreen displays, with page 1 centered as cover. Progress displays `left-right / total`. |
| **Double RTL** | Same navigation as RTL mode | Side-by-side spread ordered right-to-left, with page 1 centered as cover. |
| **Webtoon** | Continuous vertical scroll; click-to-turn, spacebar, and dual spreads are disabled | Vertical continuous strip with lazy image loading (`loading="lazy"`). Scroll position continuously syncs reading progress; page jump (`G`) remains available. |

**Keyboard Shortcuts**:

| Shortcut | Action | Notes & Constraints |
| :--- | :--- | :--- |
| `←` / `→` | Previous / Next page | Automatically inverted in Manga (RTL) mode; disabled in Webtoon mode. |
| `Space` | Next page | Disabled in Webtoon mode. |
| `G` | Focus page jump input / open jump prompt | Directly invokes page jumping even in fullscreen or with hidden toolbars. |
| `F` | Enter / exit image fullscreen | Swaps images in place without exiting fullscreen during page turns. |
| `Esc` | Exit fullscreen | Exits fullscreen mode; halts active slideshow playback and restores pre-fullscreen reader layout. |

**Mobile Touch Gestures**:

| Gesture | Action & Effect | Constraints & Reset |
| :--- | :--- | :--- |
| **Left / Right Tap** | Tap left screen for previous page, right screen for next page (inverted in RTL mode) | Ineffective in Webtoon mode |
| **Double-Tap** | Quickly zooms to 2.2x magnification centered on tap coordinates; double-tap again resets to 1.0x | Ineffective in Webtoon mode |
| **Pinch-to-Zoom** | Supports continuous smooth zoom from 1.0x to 3.5x | Automatically resets when pinched or double-tapped back near 1.0x; ineffective in Webtoon mode |

### Slideshow Auto-Play & Display Controls

- **Start & Controls**: The toolbar provides a "▶" button and an interval input (default 5 seconds, persisted to `gv_slideshow_interval`). Clicking ▶ appends interval parameters to the URL (`?slideshow=<seconds>`), enters image fullscreen, and starts automatic cycling. Toolbars are hidden in fullscreen; pressing `Esc` or clicking fullscreen controls exits fullscreen and terminates playback.
- **Animation Duration Probing**: When the current page is a GIF or WebP animation, the reader calls the page metadata endpoint to calculate total frame delay (`duration_ms`, scanning one full loop, capped at 120 seconds). Playback interval uses `max(user interval, duration_ms + 150ms)` with pre-decoding applied prior to page swaps.
- **Scheduling & Boundary Handling**: Manual paging or tapping active zones cancels the current timer and reschedules for the new page; changing the interval input requires clicking "▶" again to take effect. Turning past the last page stops the slideshow, exits fullscreen, and advances to the next gallery (auto-play does not chain across galleries). Paging backward on the first page neither exits fullscreen nor jumps to the previous gallery.
- **Preloading & Caching**: Opening the reader preloads the next 3 pages (4 pages in double-spread modes); turning pages preloads 1–2 subsequent pages. Cover thumbnails are cached for 24 hours, remaining page thumbnails are cached long-term, and full-resolution images are managed by standard browser caching.
- **Layout Adaptability & Search Context**: The toolbar "Fit" toggle switches between maximum height (~82vh) and full page width. When entering the reader from library searches, page turns, thumbnail selections, and advancing to the next gallery preserve active search queries and tag filter context throughout navigation.
