# Browsing & Library

> [中文](Library) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers gallery browsing, discovery, the main library, local lists, tag management, and reading history in GalleryVault.

## Browse (`#/browse`)

- The default landing page (an empty hash / unspecified route also lands here): a grid of the newest galleries, reverse-chronological, with numbered pagination.
- **Continue Reading Cards**: Top section automatically aggregates recently read galleries with cover thumbnails, reading progress bars, one-click resumption, and per-gallery "Mark as unread / ✕" (clears progress and removes the card from Continue Reading / History).
- The **tag namespace strip** on top (Tag / Artist / Character / Parody / Group / Female / Male / Language) and a **random gallery** button (🎲, opens a random gallery's detail page).
- The **global search box** in the top bar jumps to the library and runs the title search on Enter; pressing **`/`** anywhere focuses the search box.
- The gallery grid supports **keyboard arrow navigation** (`←`/`→`/`↑`/`↓` moves focus, `Enter` opens the detail page).

## Discover (`#/discover`)

- Browse / search ExHentai; the toolbar also has **Popular / Watched / Toplist** (Toplist: yesterday / month / year / all-time = site `tl=11/12/13/15`). Watched without a login uses the existing Cookie error state.
- Toolbar: query, category checkboxes (site `f_cats` bitmask), minimum rating, download quality (resample by default, original optional).
- Cards: cover, title, category, page count, rating; stackable badges **in library / favorited / not downloaded**.
- **Download** uses existing `POST /api/downloads`; **Add to favorites** picks folder 0–9 via `POST /api/favorites/add` (**local DB is written only after cloud success**).
- Infinite scroll uses the site `next=gid-ts` cursor, **not** `page=N`; a short TTL cache avoids re-hitting the first page while scrolling.
- No hits, Sad Panda, empty-body anti-bot, 509, and cookie expiry are **shown separately** and never treated as “no results” (which would keep paging). Cookie expiry still uses the top red banner.

## Series (#/series)

- **Automatic Clustering & Event Prefix Stripping**: Automatically clusters doujinshi and manga series while stripping convention and event prefixes (such as C100, COMIC1, Reitaisai) to group related works together.
- **Default Filtering & Pagination**: Filters to Doujinshi and Manga categories by default with pagination; toggle "Show All" to view complete series across all categories.
- **Cloud Un-downloaded Members & One-click Download**: Shows favorited cloud members not yet downloaded locally with distinct badges, supporting one-click batch downloading to complete the collection.
- **Manual Management & Allocation**: Add works via gallery GID or favorites, remove mismatched cloud items from groups, create custom series groups, rename or delete groups, and reassign member galleries between groups.
- **Library Scan Rebuild & Manual Re-clustering**: A filesystem library scan automatically triggers a series rebuild upon completion; you can also manually trigger "Re-cluster" from the series page, with background progress and results logged in the Logs page (`#/logs`).
- **Series Covers**: Series cards reuse the existing `GET /api/favorites/cover` thumbnail endpoint for rendering.

## Library (`#/library`)

- Search by title, filter by category, sort across multiple fields, filter by reading status, and browse indexed galleries.
- **Multi-criteria Sorting**: Order by **Ingest date (default)**, **Posted date**, **Title**, **Pages**, **Size**, and **Rating**, backed by dedicated database indexes for sub-second responses on large collections.
- **Reading Status Filter**: Quickly filter by **All**, **Unread**, **Reading**, or **Completed**; the three are mutually exclusive. Unread excludes completed. Completed requires actually having read (progress > 0 and at the last page; a 1-page gallery with progress 0 is not completed).
- **Collapsible Advanced Filters**: Secondary filters are collapsed into an expandable panel displaying an active filter count badge; expanding it reveals min/max page inputs, minimum rating (≥2 / ≥3 / ≥4 / ≥4.5), size range (MB → bytes), posted date, uploader substring, image quality (original/resample), language shortcuts (existing `language:` tags), local star rating, and local lists. These stick with sort, read status and tag filters.
- **Saved searches**: store the current library filter under a name (about 30 max, in `user_settings.saved_searches` with get+merge so `auth_secret` is kept); apply or delete from the toolbar.
- **Local lists**: independent of ExHentai. Add/remove from the library or detail page; gid-less CBZ archives can join; the library can filter by list (see the dedicated section below).
- **"Not in favorites" filter**: the category dropdown ends with "Not in favorites", showing local galleries whose gid is not in any ExHentai favorite folder (gid-less local archives count as not favorited; older local copies with a newer favorited version are excluded and routed to Gallery Updates instead). Before favorites have ever been synced this item is equivalent to "All".
- This page uses **infinite scroll**: the next page (24 galleries by default) is appended as you near the bottom; the numbered pager at the bottom stays as a fallback. Your page-size choice is remembered across visits.
- Click a cover to open the gallery detail page (see [Gallery Details & Reader](Reading-EN)).
- **Multi-tag filtering (AND / OR) & Exclude Tags (`-tag`)**:
  - Clicking a tag **appends it to the filter**; **Shift / Alt / Ctrl / Cmd + click** on a gallery card's tag **appends it as an exclude tag** (`-namespace:name`, e.g. `Shift+click female:lolicon → -female:lolicon`) — the click uses `stopPropagation` so it won't open the gallery, and the red badge shows the exclusion; excluded tags are honored by **Delete filtered** and sticky navigation;
  - The tag filter bar lets you toggle **AND / OR** mode;
  - Exclude tags (`-namespace:name` or `-tag`, e.g. `-female:lolicon`) are displayed with distinct red badges, excluding matching galleries.
- **Tag filters are opt-in, never guessed**: while you type, tag suggestions appear under the search box — **clicking a suggestion** adds that tag to the filter (and consumes matching query tokens — including partial input such as 「和泉」 when picking 「和泉纱雾」 — so they don't also act as a title keyword; leftover words still search the title). Tags can also be added with explicit `ns:name` syntax (`parody:touhou`) or from the tag cloud / gallery detail page. Pressing Enter without `ns:name` performs a **title text search only** and never auto-promotes words into tag filters.
- **Multi-word search ANDs each word**: the title query splits on whitespace and every word must appear (each as an independent substring, order- and position-independent), so `mimu gif` matches any title containing both mimu and gif. Single-word and CJK-sentence searches behave as before.
- **Batch add to favorites**: after selecting cards, **Add to favorites** picks a folder 0–9 and submits in chunks of 25; **only cloud-confirmed gids are written locally** (add is a move — one gid lives in one favcat); gid-less local archives are skipped with a toast.
- **Bulk & filtered deletion**:
  - Ticking gallery cards reveals a **Delete selected** action, with an option to delete corresponding files on disk (**leaving files on disk sends the row to `#/recycle` → User deleted**, restorable, see [Library Maintenance](Manage-EN); when partial copy deletion fails, records stay consistent with remaining on-disk paths);
  - **Delete filtered** removes all galleries matching the active category, search query, read status, or tag filter at once. A 5,000-row safety guard rejects excessive matches with `409` to prevent accidental library wipes; deletion runs safely in 500-row batches, keeping the DB row and logging a notice if disk files are read-only.
- **Scan library** triggers a filesystem scan: new archives are ingested, and galleries missing from disk go to `#/recycle` → Scan missing (restorable; purge removes them from the index). The completion Telegram notification appends `N duplicate-copy group(s) found (gid …)` when duplicates were detected, pointing to the [Duplicate copies](Manage-EN) page. A **global pause** skips the scan (the trigger returns `paused`).

## Local Lists (`#/library`)

- **Independent of ExHentai**: Local lists are completely decoupled from ExHentai cloud favorites; gid-less local archives (CBZ, directory galleries) can be freely added and organized.
- **Frontend Entry & Filtering**: Accessible from the Library (`#/library`) and Gallery Detail (`#/gallery/<id>`) pages. The list dropdown on the Library toolbar filters galleries by list (URL hash `#/library?list_id=<id>`).
- **List Lifecycle Management**: Supports creating, renaming, and deleting local lists. You can click "New list" on the Library toolbar to create one instantly; the backend API provides full CRUD capabilities (`POST /api/lists`, `PATCH /api/lists/{id}`, `DELETE /api/lists/{id}`).
- **Adding & Removing Galleries**: In the Library, tick galleries and click "Add to list" to batch-assign them (prompts to create a new list if none is selected); on the Gallery Detail page, click the toolbar list buttons to add or remove the gallery from a list with one click.

## Tags (`#/tags`)

- Search the local tag taxonomy and view usage counts; filter by namespace strip (All / Tag / Artist / Character / Parody / Group / Female / Male / Language / Category).
- The namespace filter strip stays intact across page turns.
- The search box supports Chinese autocomplete (same reverse-translation matching as the top bar, e.g. 「巨乳」). **Picking a suggestion stays on the tags page and filters the cloud** (switches to that namespace, queries by English name). Submitting Chinese also matches local tags via translations. The button is “Search tags”. The top-bar search still searches galleries and jumps to the library.
- Clicking a tag in the cloud appends it to the library filter (multi-tag AND); tags on detail pages can also be appended.
- In Chinese UI, tags display translations; multi-value tags display only the translated portion.
- Results are fixed at 100 items per page (API limit 500).

## History (`#/history`)

- Lists reading history per gallery (last reading position and time), with direct "Read Now" shortcuts and per-gallery "✕" mark-as-unread buttons (clears progress and removes the row from History / Continue Reading).
- **Clear history**: clears timeline entries (does not affect progress bookmarks on galleries).
- **Clear reading progress**: resets reading progress for all galleries after confirmation (marks all as unread / progress reset to 0).
- The reading position is saved automatically by the reader and restored when you reopen a gallery / reader.
