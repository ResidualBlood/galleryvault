# Usage Guide

> [中文](Usage) · English
>
> **Direct Chapters**: [Browsing & Library](Library-EN) · [Gallery Details & Reader](Reading-EN) · [Download Management](Downloads-EN) · [Favorites & Updates](Favorites-EN) · [Library Maintenance](Manage-EN) · [Settings](Settings-EN)

GalleryVault is a single-page application built on hash routing (for example, `#/library`, `#/gallery/7`). Page transitions and interactions are driven entirely by the frontend; page refreshes and browser forward/back navigation operate without requesting a new HTML document.

**Main Navigation Entries**:
- **Desktop Top Navigation**: Browse, Discover, Library, Series, Tags, Downloads, Favorites, and Manage.
- **More Menu**: Groups History, Settings, and Logs.
- **Manage Module**: Clicking "Manage" defaults to the Recycle Bin (`#/recycle`), with in-page tabs for Duplicate Copies (`#/duplicates`), Favorite Duplicates (`#/duplicates/favorites`), Cross-GID Duplicates (`#/duplicates/cross-gid`), Missing Pages / Integrity (`#/integrity`), and Cold Archive (`#/archive`). The legacy route `#/favorites/manage` automatically redirects to Favorite Duplicates for compatibility.
- **Mobile**: Uses a flat hamburger menu displaying all navigation items.

**Top Banner Status Indicators**:

| Indicator | Cause | User Action |
| :--- | :--- | :--- |
| Yellow banner | Global download pause is enabled | Go to Downloads or Settings to resume task execution |
| Orange banner | Connectivity probe failed (network disruption or target site temporarily unavailable) | Check network connectivity and verify whether the target site is reachable |
| Red banner | Cookie expired, account lacks sadpanda clearance, or IP address is banned | Click the banner to open Settings, supply valid cookies, and re-test login |
| Quota warning | ExHentai image download quota exhausted | Pause downloads that consume quota, or wait for the cloud quota reset period |

**In-App Notification Center**:
The bell icon next to the random gallery button serves as the in-app notification center. It logs background events including download completions, download failures, retargeted updates, library scan results, archive progress and status, expired cookies, and IP bans. Background events remain visible in the UI even without Telegram bot integration. The panel provides a one-click clear button, and timestamps reflect the container local timezone.

---

## First-Run Wizard (`#/welcome`)

Right after initial deployment (while the default password is active), logging in automatically directs to the three-step `#/welcome` wizard:

1. **Change default password**: Replace the built-in default password `p1a2s3s4` with a custom master password. This step is mandatory and cannot be skipped; it can also be modified later in Settings.
2. **Connect ExHentai**: Select your base URL (`https://exhentai.org`, `https://e-hentai.org`, or an official domain subdomain) and enter `ipb_member_id`, `ipb_pass_hash`, and `igneous`. Click "Test login" to verify credential validity. If you do not have an account yet, you may skip this step and configure it later in Settings (see [Configuring ExHentai Cookies](#configuring-exhentai-cookies)).
3. **Fill library**: Click "Scan library" to index local media files, or click "Check all folders" to synchronize cloud records. This step is optional.

Completed steps receive a checkmark indicator. Click "Finish setup" to enter the main interface. Configured instances will not force this wizard upon login, though you can revisit it at any time by navigating directly to `#/welcome`.

## Recommended Workflow

For a new deployment, the recommended initial sequence is:

1. **Configure Cookies (optional)**: Enter ExHentai cookies in the wizard or Settings, and verify reachability with "Test login".
2. **Check favorites to sync metadata**: Open [Favorites & Updates](Favorites-EN) (`#/favorites`) and click "Check all folders" to cache cloud gallery metadata and covers into the local database.
3. **Scan the library**: Place existing archives and directories into the `./library` mount, then click "Scan library" in [Browsing & Library](Library-EN). The system indexes archives by matching them against cached cloud metadata.
4. **Clean up duplicates**: Open [Library Maintenance](Manage-EN) → Duplicate Copies (`#/duplicates`) to resolve identical GID archives across multiple paths. Use Favorite Duplicates (`#/duplicates/favorites`; legacy route `#/favorites/manage` remains functional) to inspect multi-version galleries.
5. **Daily usage and reading**: Enable desired favorite folders and set them to "Incremental download"; see [Gallery Details & Reader](Reading-EN) for reading instructions. Navigating into the reader from search results preserves filtering context.

## Configuring ExHentai Cookies

Connecting with ExHentai, synchronizing favorite folders, fetching tags, or downloading galleries requires valid browser login credentials:

1. **Obtain Cookies**:
   - Log into [E-Hentai](https://e-hentai.org) or [ExHentai](https://exhentai.org) using a desktop browser;
   - Press `F12` to open Developer Tools, then switch to the **Application** (Chrome/Edge) or **Storage** (Firefox) tab;
   - Expand **Cookies** on the left panel and select the target site domain;
   - Copy values for the following three fields:
     - `ipb_member_id`: User ID (numeric string);
     - `ipb_pass_hash`: Password hash (32-character hexadecimal string);
     - `igneous`: Secret access token required for `exhentai.org` (generated only for accounts with sadpanda access permissions).
2. **Enter Credentials**:
   - Navigate to step 2 of the `#/welcome` wizard or open the **ExHentai** section in [Settings](Settings-EN) (`#/settings`);
   - Keep the base URL default `https://exhentai.org` (or switch to `https://e-hentai.org` if your account lacks sadpanda clearance; only official domains and their subdomains are accepted);
   - Enter the three fields; saved cookies are masked and never echoed back in plain text.
3. **Connectivity Verification & Health Probes**:
   - Click the **Test login** button to send an authentication check and inspect connection status and permissions;
   - The service automatically runs a probe on startup and every 30 minutes thereafter;
   - If cookies expire, lack clearance, or trigger an IP ban, a red banner appears at the top. If network or remote host issues cause probe failure, an orange banner appears. Click the red banner to navigate directly to Settings to update credentials.

> **Security Note**: Cookies are sensitive credentials. Never commit them to version control, public documentation, or share them. The system supports AES-256-GCM database encryption at rest via the `ENCRYPTION_KEY` environment variable (see [Encryption at Rest](Encryption-EN)).

## Documentation Chapters

For detailed instructions on each functional module, see the dedicated chapters:

- **[Browsing & Library (Library)](Library-EN)**:
  - [Browse (#/browse)](Library-EN#browse-browse) — Default grid browsing, continue reading shelf, keyboard navigation, and global search; landscape card covers use blurred background padding to preserve aspect ratio. Prioritizes cloud remote cover cache, falling back to local first-page images with background fetching on cache miss.
  - [Discover (#/discover)](Library-EN#discover-discover) — Online browsing of ExHentai, Popular, Watched, and Toplist feeds with cursor pagination.
  - [Series (#/series)](Library-EN#series-series) — Doujinshi and Manga filtering, prefix stripping, and title clustering; surfaces un-downloaded cloud favorites with badges and one-click queuing, supports manual series membership management, and rebuilds clusters automatically after library scans.
  - [Library (#/library)](Library-EN#library-library) — Multi-attribute sorting, mutually exclusive reading status filtering, AND/OR multi-tag filtering with `-tag` exclusions, batch favorite additions, and bulk deletion safety fuses.
  - [Local Lists (#/library)](Library-EN#local-lists-library) — Standalone local reading list lifecycle management decoupled from cloud favorites.
  - [Tags (#/tags)](Library-EN#tags-tags) — Tag namespace grouping, frequency sorting, and EhTag Chinese semantic autocomplete.
  - [History (#/history)](Library-EN#history-history) — Reading timeline inspection, history record clearing, and gallery progress resetting.

- **[Gallery Details & Reader (Reading)](Reading-EN)**:
  - [Gallery Detail (#/gallery/<id>)](Reading-EN#gallery-detail-galleryid) — Progress-aware thumbnail grid pagination, direct source links, tag metadata synchronization, quality tier recognition and original image upgrade, and single-gallery CBZ export.
  - [Reader (#/reader/<id>/<page>)](Reading-EN#reader-readeridpage) — Streamed page rendering supporting left-to-right (LTR), Japanese manga right-to-left (RTL), double-page spread, and Webtoon continuous vertical scrolling; supports pinch-to-zoom, `G` jump prompt, `F` fullscreen toggle, and search filter context persistence.

- **[Download Management (Downloads)](Downloads-EN)**:
  - [Downloads (#/downloads)](Downloads-EN#downloads-downloads) — Fast queuing via URL or GID paste, automatic new version tracking, queue status monitoring, global pause control, GP and quota display, resume support, and exponential backoff.
  - [Archive Downloads (ExHentai archive)](Downloads-EN#archive-downloads-exhentai-archive) — Official zip archive channel, GP balance preview, HTTP Range resumption, and automatic fallback to page-by-page downloads.

- **[Favorites & Updates (Favorites)](Favorites-EN)**:
  - [Favorites (#/favorites)](Favorites-EN#favorites-favorites) — Synchronization for 10 cloud favorite folders, metadata updates, skip heuristic, folder search, in-folder sorting, and batch folder moves.
  - [Favorite duplicates (#/duplicates/favorites)](Manage-EN#duplicate-copies--deduplication-duplicates) — Multi-version duplicate inspection across favorite folders; legacy route `#/favorites/manage` remains functional.
  - [Gallery Updates (#/updates)](Favorites-EN#gallery-updates-updates) — GID replacement tracking, queueing new version downloads, and cleaning up old local copies upon successful download.
  - ["download favorites" vs. "enabled"](Favorites-EN#download-favorites-vs-enabled) — Interaction between the global scheduled check switch and per-folder independent enablement.
  - [The Three Modes](Favorites-EN#the-three-modes) — Behavioral differences and data impact across Incremental Download, Watch Only, and Force Download modes.

- **[Library Maintenance (Manage)](Manage-EN)**:
  - [Duplicate copies (#/duplicates)](Manage-EN#duplicate-copies--deduplication-duplicates) — Same-GID multi-path copies, favorite duplicates, and cross-GID deduplication.
  - [Recycle Bin (#/recycle)](Manage-EN#recycle-bin-recycle) — Management of user-deleted galleries and scan-missing galleries, supporting safe restore and permanent purge.
  - [Integrity (#/integrity)](Manage-EN#missing-pages--integrity-integrity) — Corrupt image and missing page scanning with targeted incremental page backfilling.
  - [Cold archive (#/archive)](Manage-EN#cold-archive-archive) — Local directory packaging into CBZ archives, task cancellation, and reverse source cleanup.
  - [Logs (#/logs)](Manage-EN#logs-logs) — Real-time background task monitoring and system runtime log auditing.

- **[Settings (Settings)](Settings-EN)**:
  - [Settings (#/settings)](Settings-EN#settings-settings) — Storage root configuration, download concurrency and watchdog tuning, disk usage distribution, multi-language title preferences, Telegram bot integration, PWA caching, and OPDS client authentication.
  - [What Needs the Network](Settings-EN#what-needs-the-network) — Tiered network access classification matrix (ExHentai cloud operations, GitHub checks, local-only operations, and local-first cached actions).

---

## Old Anchor Migration Table

If you previously bookmarked section anchors from earlier versions of `Usage-EN.md`, refer to this table for their updated locations:

| Old Anchor | Target Document | New Section Anchor |
| :--- | :--- | :--- |
| `#browse-browse` | [Browsing & Library (Library)](Library-EN) | [Browse (#/browse)](Library-EN#browse-browse) |
| `#discover-discover` | [Browsing & Library (Library)](Library-EN) | [Discover (#/discover)](Library-EN#discover-discover) |
| `#系列作品series` | [Browsing & Library (Library)](Library-EN) | [Series (#/series)](Library-EN#series-series) |
| `#history-history` | [Browsing & Library (Library)](Library-EN) | [History (#/history)](Library-EN#history-history) |
| `#first-run-wizard-welcome` | [Usage Guide (Usage)](Usage-EN) | [First-Run Wizard (#/welcome)](Usage-EN#first-run-wizard-welcome) |
| `#library-library` | [Browsing & Library (Library)](Library-EN) | [Library (#/library)](Library-EN#library-library) |
| `#local-lists-library` | [Browsing & Library (Library)](Library-EN) | [Local Lists (#/library)](Library-EN#local-lists-library) |
| `#duplicate-copies-duplicates` | [Library Maintenance (Manage)](Manage-EN) | [Duplicate copies (#/duplicates)](Manage-EN#duplicate-copies--deduplication-duplicates) |
| `#recycle-bin-recycle` | [Library Maintenance (Manage)](Manage-EN) | [Recycle Bin (#/recycle)](Manage-EN#recycle-bin-recycle) |
| `#missing-pages-integrity` | [Library Maintenance (Manage)](Manage-EN) | [Integrity (#/integrity)](Manage-EN#missing-pages--integrity-integrity) |
| `#gallery-detail-galleryid` | [Gallery Details & Reader (Reading)](Reading-EN) | [Gallery Detail (#/gallery/<id>)](Reading-EN#gallery-detail-galleryid) |
| `#reader-readeridpage` | [Gallery Details & Reader (Reading)](Reading-EN) | [Reader (#/reader/<id>/<page>)](Reading-EN#reader-readeridpage) |
| `#tags-tags` | [Browsing & Library (Library)](Library-EN) | [Tags (#/tags)](Library-EN#tags-tags) |
| `#downloads-downloads` | [Download Management (Downloads)](Downloads-EN) | [Downloads (#/downloads)](Downloads-EN#downloads-downloads) |
| `#logs-logs` | [Library Maintenance (Manage)](Manage-EN) | [Logs (#/logs)](Manage-EN#logs-logs) |
| `#favorites-favorites` | [Favorites & Updates (Favorites)](Favorites-EN) | [Favorites (#/favorites)](Favorites-EN#favorites-favorites) |
| `#manage-favorites-favoritesmanage` | [Library Maintenance (Manage)](Manage-EN) | [Favorite duplicates (#/duplicates/favorites)](Manage-EN#duplicate-copies--deduplication-duplicates) |
| `#gallery-updates-updates` | [Favorites & Updates (Favorites)](Favorites-EN) | [Gallery Updates (#/updates)](Favorites-EN#gallery-updates-updates) |
| `#archive-downloads-exhentai-official-zip-channel` | [Download Management (Downloads)](Downloads-EN) | [Archive Downloads (ExHentai archive)](Downloads-EN#archive-downloads-exhentai-archive) |
| `#download-favorites-vs-enabled` | [Favorites & Updates (Favorites)](Favorites-EN) | ["download favorites" vs. "enabled"](Favorites-EN#download-favorites-vs-enabled) |
| `#the-three-modes` | [Favorites & Updates (Favorites)](Favorites-EN) | [The Three Modes](Favorites-EN#the-three-modes) |
| `#settings-settings` | [Settings (Settings)](Settings-EN) | [Settings (#/settings)](Settings-EN#settings-settings) |
| `#what-needs-the-network` | [Settings (Settings)](Settings-EN) | [What Needs the Network](Settings-EN#what-needs-the-network) |
