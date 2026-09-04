# Usage Guide

> [中文](Usage) · English
>
> **Direct Chapters**: [Browsing & Library](Library-EN) · [Gallery Details & Reader](Reading-EN) · [Download Management](Downloads-EN) · [Favorites & Updates](Favorites-EN) · [Library Maintenance](Manage-EN) · [Settings](Settings-EN)

GalleryVault is built as a single-page application (SPA) using hash routing (such as `#/library`, `#/gallery/7`), meaning page navigation, browser refresh, and history traversal require no extra server round-trips.

Desktop top navigation includes Browse, Discover, Library, Tags, Downloads, Favorites, and "Management". History, Settings, and Logs are organized under the "More" dropdown. Clicking "Management" opens the Recycle Bin directly, with embedded tabs for Recycle Bin (`#/recycle`), Duplicate Copies (`#/duplicates`), and Missing Pages (`#/integrity`), while all legacy hash routes remain fully backward-compatible. Mobile layouts provide a clean, flat navigation menu.

The top banner stacks a yellow global-pause bar, a red Cookie-expired / no-access warning, and image quota alerts when necessary. The bell next to 🎲 serves as the **in-app notification center** (download completions/failures, library scan results, and cookie status polled every 15 seconds, visible even without Telegram configured; the Cookie red warning bar remains displayed; supports one-click "Clear"; timestamps follow the container local TZ rather than UTC truncation).

---

## First-Run Wizard (`#/welcome`)

Right after initial deployment (while the default password is still active), logging in automatically directs to the three-step `#/welcome` wizard:

1. **Change default password**: Replace the built-in password `p1a2s3s4` with a strong master password (mandatory, can also be modified later in Settings).
2. **Connect ExHentai**: Select your base URL (ExHentai or E-Hentai mirror / custom proxy) and fill in `ipb_member_id` / `ipb_pass_hash` / `igneous` cookies, verifiable via "Test login" (optional; see [Configuring ExHentai Cookies](#configuring-exhentai-cookies) below).
3. **Fill library**: Click "Scan library" or "Check all folders" to begin indexing (optional).

Completed steps receive a ✓ indicator. Click "Finish setup" to enter the main interface. Configured instances will not force this wizard upon login, though you can revisit it at any time by navigating directly to `#/welcome`.

## Recommended Workflow

For optimal metadata accuracy and minimal network bandwidth consumption, follow this recommended sequence:

1. **Configure Account Cookies (Optional but Recommended)**: Connect your ExHentai account via the welcome wizard or Settings and verify login connectivity.
2. **Cache Favorites Metadata First**: Navigate to [Favorites & Updates](Favorites-EN) (`#/favorites`) and click "Check all folders" (or configure periodic polling) to pre-warm remote metadata and cover images into local database storage.
3. **Scan Local Library**: Place your local gallery archives into the `./library` directory and click "Scan library" in [Browsing & Library](Library-EN). Local archives will match against pre-cached cloud metadata with high fidelity.
4. **Deduplication & Maintenance**: Open [Library Maintenance](Manage-EN) → Duplicate Copies (`#/duplicates`) to resolve cross-directory duplicates per policy; open [Favorites & Updates](Favorites-EN) → Manage Favorites (`#/favorites/manage`) to identify multi-version uploads.
5. **Incremental Tracking & Reading**: Enable desired favorite folders with "Incremental download" to track fresh uploads automatically; read locally in [Gallery Details & Reader](Reading-EN) with search context retention across multiple reading modes.

## Configuring ExHentai Cookies

Connecting with ExHentai, synchronizing favorite folders, fetching tags, or downloading galleries requires your browser session cookies:

1. **Obtain Cookies**:
   - Log into [E-Hentai](https://e-hentai.org) or [ExHentai](https://exhentai.org) using your desktop browser;
   - Press `F12` to open Developer Tools, then navigate to the **Application** (Chrome/Edge) or **Storage** (Firefox) tab;
   - Expand **Cookies** on the left panel and select the site domain;
   - Locate and copy values for the following three keys:
     - `ipb_member_id`: User ID (numeric string);
     - `ipb_pass_hash`: Password hash (32-character hexadecimal string);
     - `igneous`: Secret access token required for exhentai.org (requires account access permissions).
2. **Fill into GalleryVault**:
   - Navigate to step 2 of the `#/welcome` wizard or open the **ExHentai** section in [Settings](Settings-EN) (`#/settings`);
   - Keep the base URL as `https://exhentai.org` (or switch to `https://e-hentai.org` if your account lacks sadpanda clearance);
   - Paste the values into their corresponding fields (cookies are masked and never echoed back).
3. **Test Connectivity & Health Probes**:
   - Click **Test login** to verify cookie validity immediately;
   - The service automatically runs a connectivity probe on startup and every 30 minutes thereafter;
   - If cookies expire or lack ExHentai privileges, a red top alert banner appears with a direct link to Settings.

> **Security Note**: Cookies contain sensitive session credentials. Never commit them to git repositories, public documentation, or unencrypted logs. GalleryVault supports AES-256-GCM database encryption at rest via `ENCRYPTION_KEY` (see [Encryption at rest](Encryption-EN)).

## Documentation Chapters

The usage guide is divided into the following dedicated chapters:

- **[Browsing & Library (Library)](Library-EN)**:
  - [Browse (#/browse)](Library-EN#browse-browse) — Default landing grid, continue reading cards, keyboard navigation, and global instant search; landscape gallery card covers are no longer cropped, using blurred background padding.
  - [Discover (#/discover)](Library-EN#discover-discover) — Browse ExHentai online, Popular / Watched / Toplist feeds, and cursor pagination.
  - [Series (#/series)](Library-EN#series-series) — Title and artist rule-based auto grouping, scan rebuild, and manual series curation.
  - [Library (#/library)](Library-EN#library-library) — Multi-index sorting, mutually exclusive reading status filters, AND/OR multi-tag filtering with `-tag` exclusions, batch actions, and deletion safety guards.
  - [Local Lists (#/library)](Library-EN#local-lists-library) — Independent local lists lifecycle, decoupled from ExHentai cloud favorites.
  - [Tags (#/tags)](Library-EN#tags-tags) — Tag namespace strips, frequency analysis, and EhTag Chinese search suggestions.
  - [History (#/history)](Library-EN#history-history) — Reading history timeline and progress management.

- **[Gallery Details & Reader (Reading)](Reading-EN)**:
  - [Gallery Detail (#/gallery/<id>)](Reading-EN#gallery-detail-galleryid) — Progress-aware thumbnail pagination, direct ExHentai links, tag sync, quality tier inference, and CBZ export.
  - [Reader (#/reader/<id>/<page>)](Reading-EN#reader-readeridpage) — Streamed page rendering, LTR / RTL Manga / Double-page / Webtoon modes, pinch-to-zoom, `G` jump prompt, `F` image fullscreen, and persistent search context.

- **[Download Management (Downloads)](Downloads-EN)**:
  - [Downloads (#/downloads)](Downloads-EN#downloads-downloads) — Batch URL/GID queueing, automatic re-upload version following, live progress, global pause, GP/quota gauges, and exponential backoff self-healing.
  - [Archive Downloads (ExHentai archive)](Downloads-EN#archive-downloads-exhentai-archive) — Official zip channel, GP balance preview, HTTP Range resumption, and automatic fallback to page-by-page.

- **[Favorites & Updates (Favorites)](Favorites-EN)**:
  - [Favorites (#/favorites)](Favorites-EN#favorites-favorites) — Monitoring 10 favorite folders, automatic metadata application, skip heuristic, folder search, and batch moves.
  - [Favorites Management & Deduplication (#/favorites/manage)](Favorites-EN#favorites-management--deduplication-favoritesmanage) — Multi-version deduplication across folders, batch removal, and physical file deletion.
  - [Gallery Updates (#/updates)](Favorites-EN#gallery-updates-updates) — Intelligent re-upload detection (GID changes), background download, and automatic superseded local copy cleanup.
  - ["download favorites" vs. "enabled"](Favorites-EN#download-favorites-vs-enabled) — Logical matrix of global scheduled scanning versus per-folder enablement.
  - [The Three Modes](Favorites-EN#the-three-modes) — Incremental download, watch only, and force download mechanics.

- **[Library Maintenance (Manage)](Manage-EN)**:
  - [Duplicate Copies (#/duplicates)](Manage-EN#duplicate-copies-duplicates) — Cross-directory duplicate copy resolution policies (keep first / newest / largest / most pages or manual).
  - [Recycle Bin (#/recycle)](Manage-EN#recycle-bin-recycle) — User deleted vs scan missing tabs, restorable rows, and permanent purging.
  - [Missing Pages (#/integrity)](Manage-EN#missing-pages-integrity) — File page-count discrepancy audits and one-click page repair.
  - [Logs (#/logs)](Manage-EN#logs-logs) — Live background task progress, runtime ring buffer logs, dynamic level adjustments, masking, and log export.

- **[Settings (Settings)](Settings-EN)**:
  - [Settings (#/settings)](Settings-EN#settings-settings) — Storage directory paths, download watchdog thresholds, title preferences, Telegram bot controls, PWA, themes, and OPDS / third-party reader configuration.
  - [What Needs the Network](Settings-EN#what-needs-the-network) — Detailed network access classification matrix (ExHentai, GitHub, local-only, and local-first operations).

---

## Old Anchor Migration Table

If you have bookmarked specific section anchors from earlier versions of `Usage-EN.md`, refer to this table for their new locations:

| Old Anchor | Target Document | New Section Anchor |
| :--- | :--- | :--- |
| `#browse-browse` | [Browsing & Library (Library)](Library-EN) | [Browse (#/browse)](Library-EN#browse-browse) |
| `#discover-discover` | [Browsing & Library (Library)](Library-EN) | [Discover (#/discover)](Library-EN#discover-discover) |
| `#history-history` | [Browsing & Library (Library)](Library-EN) | [History (#/history)](Library-EN#history-history) |
| `#first-run-wizard-welcome` | [Usage Guide (Usage)](Usage-EN) | [First-Run Wizard (#/welcome)](Usage-EN#first-run-wizard-welcome) |
| `#library-library` | [Browsing & Library (Library)](Library-EN) | [Library (#/library)](Library-EN#library-library) |
| `#local-lists-library` | [Browsing & Library (Library)](Library-EN) | [Local Lists (#/library)](Library-EN#local-lists-library) |
| `#duplicate-copies-duplicates` | [Library Maintenance (Manage)](Manage-EN) | [Duplicate Copies (#/duplicates)](Manage-EN#duplicate-copies-duplicates) |
| `#recycle-bin-recycle` | [Library Maintenance (Manage)](Manage-EN) | [Recycle Bin (#/recycle)](Manage-EN#recycle-bin-recycle) |
| `#missing-pages-integrity` | [Library Maintenance (Manage)](Manage-EN) | [Missing Pages (#/integrity)](Manage-EN#missing-pages-integrity) |
| `#gallery-detail-galleryid` | [Gallery Details & Reader (Reading)](Reading-EN) | [Gallery Detail (#/gallery/<id>)](Reading-EN#gallery-detail-galleryid) |
| `#reader-readeridpage` | [Gallery Details & Reader (Reading)](Reading-EN) | [Reader (#/reader/<id>/<page>)](Reading-EN#reader-readeridpage) |
| `#tags-tags` | [Browsing & Library (Library)](Library-EN) | [Tags (#/tags)](Library-EN#tags-tags) |
| `#downloads-downloads` | [Download Management (Downloads)](Downloads-EN) | [Downloads (#/downloads)](Downloads-EN#downloads-downloads) |
| `#logs-logs` | [Library Maintenance (Manage)](Manage-EN) | [Logs (#/logs)](Manage-EN#logs-logs) |
| `#favorites-favorites` | [Favorites & Updates (Favorites)](Favorites-EN) | [Favorites (#/favorites)](Favorites-EN#favorites-favorites) |
| `#manage-favorites-favoritesmanage` | [Favorites & Updates (Favorites)](Favorites-EN) | [Favorites Management & Deduplication (#/favorites/manage)](Favorites-EN#favorites-management--deduplication-favoritesmanage) |
| `#gallery-updates-updates` | [Favorites & Updates (Favorites)](Favorites-EN) | [Gallery Updates (#/updates)](Favorites-EN#gallery-updates-updates) |
| `#archive-downloads-exhentai-official-zip-channel` | [Download Management (Downloads)](Downloads-EN) | [Archive Downloads (ExHentai archive)](Downloads-EN#archive-downloads-exhentai-archive) |
| `#download-favorites-vs-enabled` | [Favorites & Updates (Favorites)](Favorites-EN) | ["download favorites" vs. "enabled"](Favorites-EN#download-favorites-vs-enabled) |
| `#the-three-modes` | [Favorites & Updates (Favorites)](Favorites-EN) | [The Three Modes](Favorites-EN#the-three-modes) |
| `#settings-settings` | [Settings (Settings)](Settings-EN) | [Settings (#/settings)](Settings-EN#settings-settings) |
| `#what-needs-the-network` | [Settings (Settings)](Settings-EN) | [What Needs the Network](Settings-EN#what-needs-the-network) |
