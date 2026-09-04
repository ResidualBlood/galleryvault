# Gallery Details & Reader

> [中文](Reading) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers gallery detail views, tag and metadata synchronization, and web reader capabilities in GalleryVault.

## Gallery Detail (`#/gallery/<id>`)

- Shows metadata (size, adaptive units), tags and page thumbnails.
- Page thumbnails are paginated, **30 per page by default** (switchable to 5/30/50/100/200/500); the choice is remembered and survives the reader round trip.
- **Thumbnails open at your reading position**: without an explicit `?page=`, the pager starts on the page containing your last reading progress (so returning from the reader lands near where you were); an explicit `?page=` always wins.
- **Click a tag** to jump to the library and **append** it to the active tag filter (combine several tags to narrow down).
- **Start reading** opens the reader (positioned at your last reading spot).
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

- Streams one page at a time. Page with **←/→ arrows**, **space** or **click**.
- **Page Jump Input & `G` Shortcut**: Direct page number input in the toolbar jumps immediately on Enter; pressing **`G`** anywhere focuses the page jump input or opens a quick jump prompt in fullscreen.
- **Multi-mode reading (LTR / RTL Manga / Double-page / Webtoon)**: The "Mode" toolbar button switches between **Left-to-Right (LTR)**, **Manga (RTL)**, **Double Page**, **Double RTL**, and **Webtoon** with persisted user preference. In RTL mode, key and tap directions invert naturally; in Double-page mode, pairs of pages display side-by-side on wide screens (with solo cover on page 1). Webtoon is a vertical continuous strip (`loading="lazy"`); the visible page is written as reading progress. Click/arrow paging and double-page spreads are not used; the toolbar still supports `G` jump and back-to-details.
- **Mobile Touch Gestures**: Supports double-tap zoom (2.2x) and two-finger pinch-to-zoom.
- **Advances to the next gallery after the last page**.
- Preloads the next three pages (four pages in double-spread mode), so paging is instant.
- **Page images are browser-cached for an hour**: going back a page or re-reading a gallery reuses the browser cache instead of downloading again; thumbnails are cached for 24 h.
- The progress bar shows `page / total · size` (adaptive B/KB/MB/GB).
- Reading position is saved automatically.
- **The fullscreen button (or the `F` key) enters image-only fullscreen**: only the page image fills the screen (proportions kept, `object-fit: contain`, black background), and the toolbar and page navigation are hidden. While fullscreen, paging (arrows / space / click) swaps the image in place and **keeps fullscreen active**; paging past the last page or back to the first exits fullscreen first. `Esc` exits and restores the previous fit mode, syncing the URL to the current page.
- **Fit-mode toggle**: the "Fit" button in the reader toolbar cycles through the display modes (default: scale to page width), which helps with pages of unusual aspect ratios; leaving fullscreen restores the mode that was active before entering.
- Galleries opened from a **searched library keep the search context throughout the reader**: after paging (arrows / space / click / thumbnail links / auto-advance to the next gallery) the back-to-details and back-to-library links still carry the active search query and tag filter, so you never land back on an unfiltered library.
