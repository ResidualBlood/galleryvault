# Gallery Details & Reader

> [中文](Reading) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers gallery detail views, tag and metadata synchronization, and web reader capabilities in GalleryVault.

## Gallery Detail (`#/gallery/<id>`)

- Shows metadata (size, adaptive units), tags and page thumbnails.
- Page thumbnails are paginated, **30 per page by default** (switchable to 5/30/50/100/200/500); the choice is remembered and survives the reader round trip.
- **Thumbnails open at your reading position**: without an explicit `?page=`, the pager starts on the page containing your last reading progress (so returning from the reader lands near where you were); an explicit `?page=` always wins.
- **Click a tag** to jump to the library and **append** it to the active tag filter (combine several tags to narrow down).
- **Start reading & Slideshow auto-play**: "Start reading" opens the reader (positioned at your last reading spot); the toolbar also provides a "▶ Slideshow" button and interval input (in seconds) to start hands-free auto-advance directly from the gallery details.
- **Export CBZ**: download this gallery as a CBZ. An on-disk `.cbz` is served as-is; a directory gallery is packed in page order (on-disk format is not rewritten).
- **Open on ExHentai**: opens the corresponding gallery page on ExHentai in a new tab. The link is built from the configured base URL (`{base}/g/{gid}/{token}/`); your browser must be logged in to EH. Not shown for local galleries without a token.
- **Sync tags**: pulls that gallery's tags/metadata from ExHentai, or reuses the favorites cache when available (no network).
- With the **public mirror (e-hentai.org)** configured, ExHentai-only galleries *pause* tag sync instead of being misclassified as deleted (their category is untouched) and resume automatically once Settings switch back to `exhentai.org`.
- **Local rating / note / custom tags**: Grouped under the "More" action menu on the detail page: set 1–5 stars, write notes, and add `local:` tags (EH tags are not overwritten; tag sync keeps `local:`). The library can filter by local stars.
- The favorite folders the gallery belongs to are shown as badges. Galleries support **Add to Favorites** (modal folder selector 0–9; cloud success writes locally and moves the gid out of other folders), **Change Folder** (Move), and **Unfavorite**, with strict cloud-success verification before updating local database records. **Favorite notes** can be edited via EH applyfav / `favnote` (local write only after cloud success) and are shown on the favorites list.
- **Original / resampled**: next to the favorite badges the detail page shows whether the local copy is original or resampled (hidden when unknown). Quality is recorded when a gallery is downloaded and inferred for existing galleries by comparing the local file size against the ExHentai original size — backfilled during the favorites metadata sync (poll / check now / fetch missing) and when a **library scan** completes.
- **Upgrade to original**: galleries that are not already original and have an ExHentai gid get two toolbar buttons —
  - **Download original**: downloads original images page-by-page (no GP, see the [Downloads](Downloads-EN) page for progress); not enqueued when the gallery has no original images on ExHentai.
  - **Archive-download original**: shows a cost/balance preview (locked to the original tier, disabled when original is unavailable or GP is too low) and downloads through the ExHentai archive (zip) channel (see [Downloads](Downloads-EN)).
  - After an original download finishes, the superseded resampled copy is removed automatically (only when the page count matches; if the mount is read-only the task still succeeds and you are told to remove it manually).

## Reader (`#/reader/<id>/<page>`)

- Streams one page at a time. Page with **←/→ arrows**, **space**, or a **left/right tap on the reader area** (except in Webtoon; see below).
- **Keyboard Shortcuts**:
  | Shortcut | Action | Notes |
  |---|---|---|
  | `←` / `→` | Previous / Next page | Automatically inverted in Manga (RTL) mode; unused in Webtoon |
  | `Space` | Next page | Unused in Webtoon |
  | `G` | Focus page jump input / prompt | Opens quick jump prompt in fullscreen or when toolbar is hidden |
  | `F` | Toggle image fullscreen | In-place image swapping without exiting fullscreen |
  | `Esc` | Exit fullscreen | Native browser fullscreen exit; also stops slideshow and restores the pre-fullscreen reader style |
- **Mobile Touch Gestures** (left/right tap and pinch/zoom are unused in Webtoon):
  - **Left / Right Tap**: Previous / Next page (direction inverted in RTL mode).
  - **Double-Tap**: Fast 2.2x zoom focused on the tapped position; double-tap again to reset.
  - **Pinch-to-Zoom**: Continuous 1.0x to 3.5x smooth zoom; double-tap again to reset after zooming (pinch back near 1x also resets).
- **Page Jump Input & `G` Shortcut**: Direct 1-based page number input in the toolbar jumps immediately on Enter; pressing **`G`** anywhere focuses the page jump input or opens a quick jump prompt in fullscreen.
- **Multi-mode reading (LTR / RTL Manga / Double-page / Webtoon)**: The "Mode" toolbar button switches between **Left-to-Right (LTR)**, **Manga (RTL)**, **Double Page**, **Double RTL**, and **Webtoon** with persisted user preference. In RTL mode, key and tap directions invert naturally; in Double-page mode, pairs of pages display side-by-side on wide screens (with solo cover on page 1). Webtoon is a vertical continuous strip (`loading="lazy"`); the visible page is written as reading progress. Click/arrow paging and double-page spreads are not used; the toolbar still supports `G` jump and back-to-details.
- **Adaptive Slideshow (GIF/WebP duration)**:
  - The reader toolbar provides a "▶" start button and an inline interval input (default 5 seconds, persisted to `gv_slideshow_interval`). Clicking ▶ writes `?slideshow=<seconds>` into the URL, **enters image fullscreen**, and starts auto-advance. The button is not a play/pause toggle (it always shows ▶). The toolbar is hidden in fullscreen; **exiting fullscreen (`Esc` or the fullscreen control) stops the slideshow**.
  - **Duration probe**: when the current page type includes GIF or WebP, the reader calls `GET /api/galleries/{id}/pages/{page}/meta` and reads `duration_ms` (sum of per-frame delays; no frame-rate field). The scheduler uses `max(user interval, duration_ms + 150ms)` so at least one full loop can play. Pages are pre-decoded with `img.decode()`; stale swap requests are dropped.
  - Manual paging or left/right taps cancel the current timer and reschedule for the new page (they do not pause). Changing the interval input does nothing until you click ▶ again. Webtoon has no slideshow controls. Past the last page, slideshow stops and fullscreen exits before jumping to the next gallery (it does not keep playing).
- **Advances to the next gallery after the last page** (paging backward on the first page is a no-op: no fullscreen exit and no previous gallery).
- On open, preloads the next three pages (four in double-spread mode); after a page turn, preloads the next 1–2 pages.
- **Browser cache**: the page-image endpoint sets no `Cache-Control` (browser default). Thumbnail cover uses `max-age=86400` (24 h); other page thumbnails use `max-age=31536000, immutable` (~1 year).
- Progress: single page shows `page / total · size` (adaptive B/KB/MB/GB); double-page shows `left-right / total` (no size).
- Reading position is saved automatically.
- **The fullscreen button (or the `F` key) enters image-only fullscreen**: only the page image fills the screen (proportions kept, `object-fit: contain`, black background), and the toolbar and page navigation are hidden. While fullscreen, paging (arrows / space / tap zones) swaps the image in place and **keeps fullscreen active**; paging past the last page exits fullscreen first, then jumps to the next gallery. `Esc` exits fullscreen and syncs the URL.
- **Fit-mode toggle**: the "Fit" button switches between the default (max height ~82vh) and full page width. Leaving fullscreen restores the reader style that was active before entering.
- Galleries opened from a **searched library keep the search context throughout the reader**: after paging (arrows / space / tap zones / thumbnail links / auto-advance to the next gallery) the back-to-details and back-to-library links still carry the active search query and tag filter, so you never land back on an unfiltered library.
