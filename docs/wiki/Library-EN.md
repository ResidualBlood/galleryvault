# Browsing & Library

> [中文](Library) · English | Part of the [Usage Guide](Usage-EN) series

Browse, Discover, Series, Library, local lists, tags, and reading history.

## Browse (`#/browse`)

- **Default Landing Page**: The default entry point when no route is specified, displaying a gallery grid ordered from newest to oldest. Infinite scroll automatically loads the next page; the pager at the bottom serves as a fallback. The browser remembers the page size setting.
- **Continue Reading Cards**: The top section displays recently read gallery cards with cover thumbnails, reading progress bars, and percentage indicators. Click a card to resume reading, or click "✕" to mark as unread (resets reading progress and removes the card from Continue Reading and History).
- **Toolbar**:
  - **Namespace Shortcuts**: Quick filter strip for Tag, Artist, Character, Parody, Group, Female, Male, and Language.
  - **Random Gallery**: Click the "🎲" button to jump to a random gallery's detail page.
- **Keyboard Navigation**:
  - Press `/` anywhere to focus the global search box in the top bar; press Enter to jump to the Library and run a title search.
  - The gallery grid supports arrow key navigation: `←` / `→` / `↑` / `↓` to move focus, and `Enter` to open the detail page.
- **Late responses**: After switching views or re-rendering, a response that arrives late from an earlier request is discarded and never overwrites the current view; the same applies to Browse, Tags, the gallery detail page, and the reader.

## Discover (`#/discover`)

Browse and search online galleries on ExHentai.

- **Rankings & Views**: The toolbar provides Popular, Watched, and Toplist views (Yesterday / Month / Year / All-time, corresponding to site `tl=11/12/13/15`). Watched displays a Cookie configuration prompt when no login is present.
- **Filter Criteria**: Supports keyword queries, category checkboxes (based on site category bitmasks), minimum rating filters, and download quality settings (resampled by default, original optional).
- **Gallery Cards**: Displays cover, title, category, page count, and rating, with badges indicating "In Library", "Favorited", or "Not Downloaded" status.
- **Ingestion & Favorites**:
  - Click Download to enqueue download tasks; see [Downloads & Management](Downloads-EN).
  - Add to Favorites allows selecting folders 0–9; **local database records are updated only after cloud confirmation succeeds**.
- **Pagination & Request Rules**:
  - Search, Popular, and Watched use site cursors to load subsequent pages.
  - Toplist always requests `https://e-hentai.org/toplist.php?tl=` with page numbers, ignoring the configured custom ExHentai base URL.
- **Status Warnings**: Distinctly alerts for no results, Sad Panda, empty-body anti-bot responses, 509 quota exhaustion, expired cookies, permission errors, and IP bans; requests do not continue paging when encountering these errors.

## Series (#/series)

- **Automatic Clustering**: Automatically identifies doujinshi and manga series, stripping convention prefixes (such as C100, COMIC1, Reitaisai) to group related works together.
- **Category Filtering**: Defaults to filtering Doujinshi and Manga categories with pagination; click "Show All" to view complete series across all categories.
- **Cloud Collection Backfill**: Aggregates favorited cloud items not yet downloaded locally, marked with dedicated badges, and supports one-click batch download to complete local collections.
- **Manual Adjustments**: Allows manually adding works via gallery GID or favorites, removing mismatched galleries, creating custom series groups, renaming, deleting, and reallocating members between groups.
- **Reorganization**: A filesystem scan automatically triggers series rebuilding upon completion; you can also click "Re-cluster" manually on the page, with background progress and results logged in the Logs page (`#/logs`).
- **Series Covers**: Series cards display corresponding gallery thumbnail covers.

## Library (`#/library`)

The Library is used to browse and search all locally indexed galleries, supporting multi-criteria sorting, status filtering, tag filtering, and batch maintenance.

### Views & Display

- **Title Display Fallback**: When Title Display is configured to Japanese, galleries with an empty Japanese title or a numeric-only GID automatically fall back to the English title, preventing blank titles or raw numeric IDs.
- **Infinite Scroll & Pagination**: Automatically loads the next page when scrolling near the bottom (defaults to 24 items per page; options include 5, 30, 50, 100, 200, and 500 items). The bottom pager remains available as a fallback. The browser remembers the selected page size. If loading fails, a "Click to retry" button appears at the bottom of the list (in the UI language); clicking it retries that load.
- **Cover Navigation**: Click a gallery cover to enter the detail page; see [Gallery Details & Reader](Reading-EN).

### Sorting & Reading Status

| Sort Field | Description |
| :--- | :--- |
| **Ingest Date (Default)** | Ordered descending by the time the gallery was first indexed locally |
| **Posted Date** | Ordered by original site publication time |
| **Title** | Ordered alphabetically and lexicographically by gallery title |
| **Pages** | Ordered ascending or descending by total page count |
| **File Size** | Ordered ascending or descending by total file size |
| **Rating** | Ordered by rating score |

| Reading Status | Filter Scope & Conditions |
| :--- | :--- |
| **All** | Shows all galleries |
| **Unread** | Excludes completed galleries |
| **Reading** | Progress is greater than 0 and not at the last page |
| **Completed** | Reading progress has reached the final page (a 1-page gallery with progress 0 is not completed) |

### Advanced Filters & Saved Searches

- **Advanced Filters Configuration**: Secondary filters are collapsed into an expandable panel displaying an active filter count badge. Expanding it allows configuring:

| Filter Dimension | Description & Matching Rules |
| :--- | :--- |
| **Page Range** | Minimum / maximum page count |
| **Minimum Rating** | ≥2 / ≥3 / ≥4 / ≥4.5 |
| **File Size** | Minimum / maximum file size range |
| **Posted Date** | Start and end publication dates |
| **Uploader** | Case-insensitive substring match |
| **Image Quality** | Original / Resampled |
| **Language** | Shortcut filters matching corresponding `language:` tags |
| **Local Attributes** | Local star rating and local lists |
| **Not in Favorites** | Shows local galleries not present in any ExHentai favorite folder (includes gid-less local archives; older local copies replaced by favorited newer versions are routed to Gallery Updates; equivalent to "All" if favorites were never synced) |

- **Saved Searches**: Supports saving the active filter combinations as a named search (up to approximately 30 entries), which can be applied or deleted from the toolbar.

### Search & Tag Syntax

- **Title Search**:
  - Enter text directly into the search box and press Enter (without namespace syntax) to execute a text search on gallery titles.
  - Multiple keywords separated by spaces perform word-by-word AND matching (each keyword functions as an independent substring, regardless of order or position, e.g., `mimu gif` requires both words to appear).
- **Tag Filtering**:
  - **Suggestion Selection**: Typing in the search box displays tag suggestions; clicking a suggestion adds it to the filter and removes matching keyword tokens from the input box.
  - **Syntax Input**: Supports entering `namespace:name` syntax directly (e.g., `parody:touhou`).
  - **Card Clicking**: Tags on gallery cards can be clicked to add them to positive inclusion filters.
  - **Combination Modes**: The tag filter bar allows toggling between **AND / OR** modes, applicable exclusively to positive include tags.
- **Tag Exclusion**:
  - **Syntax Input**: Enter `-namespace:name` or `-tag` (e.g., `-female:lolicon`).
  - **Quick Addition**: Use Shift / Alt / Ctrl / Cmd + click on a gallery card's tag to add it as an exclude tag (without navigating to the detail page).
  - **Enforcement Rules**: Exclude tags are displayed with a distinct red badge and are strictly enforced as mandatory exclusions, unaffected by the positive AND/OR combination mode.
- **Uploader Filtering & Matching**:
  - **Tag Syntax**: Enter `uploader:Username` to filter for a specific uploader, or `-uploader:Username` to exclude that uploader. The default matching mode (`tag_match=exact`) performs an exact match (matching exact case first, falling back to case-insensitive match); specifying `tag_match=fuzzy` performs substring fuzzy matching on the tag name.
  - **Advanced Filter Field**: The "Uploader" field in the Advanced Filters panel matches against the gallery uploader text column via case-insensitive substring search, functioning independently from tag filtering. For full details on uploader backfilling, see [Gallery Details & Reader](Reading-EN).

### Batch Operations & Safety Limits

- **Batch Add to Favorites**:
  1. Select gallery cards and click "Batch Add to Favorites", then pick folder 0–9.
  2. The backend submits entries to the cloud in chunks of 25.
  3. **Restrictions & Safety**: **Only cloud-confirmed GIDs are updated in the local database** (moving the item to the new favorite folder; a single GID can belong to only one folder). GID-less local archives are skipped with a notification toast.
- **Bulk & Filtered Deletion**:
  - **Selected Deletion**: Select gallery cards to delete them, choosing whether to delete disk files synchronously. If files on disk are retained, galleries move to [Library Maintenance](Manage-EN) under "Recycle Bin → User Deleted" and can be restored. If partial copy deletions fail, records remain synchronized with remaining on-disk files. Paths outside scanned library roots are skipped from complete deletion, and a target that is itself a scan root is likewise refused. Bulk and destructive buttons are disabled while their request is in flight to prevent double submission.
  - **Filtered Deletion**: Deletes all galleries matching the active category, search query, reading status, or tag filter at once; the favorite, read, expunged, media type, and storage type filters also participate in matching. Must have valid filter criteria; unconditional full-library wiping is prohibited. Governed by a 5,000-gallery safety limit (rejects execution with an alert to narrow down filters if exceeded), processed in batches of 500 in the background. If disk storage is read-only, database records are preserved and reported in logs. Matches above 200 require explicit confirmation: API calls must resend `confirm=true` with a `match_count` equal to the current match count, otherwise the request returns 409; the Web UI shows a confirmation dialog stating how many galleries will be deleted and whether disk files are removed too, then resends the request with `confirm` and `match_count` once you confirm.
  - **Last-page fallback**: After bulk or filtered deletion on the last page, if the current page exceeds the new total page count the list moves back one page; if the previous page is still out of range it jumps to the actual last page instead of staying on an empty page.
- **Scan Library**: Triggers a filesystem scan: newly discovered archives are indexed, and missing files move to "Recycle Bin → Scan Missing" (restorable; completely removed from the index only upon permanent deletion). If a scan root is offline, unreadable, traversal fails, or a root that already has galleries yields no candidates this time, this scan skips the "Scan Missing" marking and logs the incomplete root(s), so the whole library is not moved to the recycle bin by mistake. Sends a Telegram notification upon completion; if duplicates are found, prompts to handle them in [Library Maintenance](Manage-EN). Library scans will not start if the system is in a globally paused state. Scan roots are deduplicated (`/library` and `/library/` are the same root); CBZ/RAR/7z archives with no image pages are not ingested and are counted in this scan's error count, and PDFs must yield extractable embedded images — text-only or image-less PDFs are likewise not ingested and count as errors; a corrupt or encrypted archive is parsed and reported once per process and then skipped silently without adding further errors, retried automatically once the file is repaired or replaced, and reported once more after a process restart; rows previously ingested through a symlink that escapes the library root are marked "Scan Missing" on the next complete scan (disk files are untouched, and an incomplete scan does not perform this marking); 7z scanning reads only the archive member table without extracting the whole archive; page count covers every image member and pages follow natural order; directory galleries include each page's name, size, and mtime in their storage signature, so in-place page edits are detected and re-ingested; records written by older releases with only the scanner fingerprint keep the old skip behaviour until that gallery changes again. A numeric prefix in a directory or archive name must be at least 5 digits to be treated as a GID.

## Local Lists (`#/library`)

- **Independent Management**: Local lists are completely decoupled from ExHentai cloud favorites; GID-less local archives (CBZ, directory galleries) can be freely added and organized.
- **Entry & Filtering**: Accessible from the list dropdown on the Library toolbar (URL: `#/library?list_id=<id>`) or from the gallery detail page (`#/gallery/<id>`).
- **List Lifecycle**: Supports creating, renaming, and deleting local lists. Click "New List" in the Library toolbar and enter a name to create one.
- **Gallery Assignment**: Select galleries in the Library and click "Add to List" to assign them in bulk (prompts to create a new list if none is selected). Galleries can also be added or removed with one click on the gallery detail page.

## Tags (`#/tags`)

- **Browsing & Category Filtering**: Search the local tag taxonomy and view usage counts; the top filter strip supports filtering by namespace (All, Tag, Artist, Character, Parody, Group, Female, Male, Language, Category). Uploader tags also belong to the local tag taxonomy (`namespace="uploader"`); see [Gallery Details & Reader](Reading-EN) for backfill rules. The top namespace filter strip remains fixed across pagination.
- **Search & Autocomplete**: The search box supports Chinese autocomplete; selecting a suggestion remains on the tags page and filters the tag cloud for that namespace. Submitting Chinese directly also matches local tags via translations. Click "Search Tags" to query the current page, while the top bar search box performs global gallery searches and jumps to the Library.
- **Tag Integration**: Clicking a tag in the tag cloud or detail page navigates to the Library and appends that tag to active filter criteria (multi-tag AND combination).
- **Language & Pagination**: In Chinese UI mode, tags prioritize displaying translations; multi-value tags (`A | B`) display only the translated portion. Results display a fixed 100 entries per page.

## History (`#/history`)

Lists reading history per gallery (last reading position and timestamp). Each item allows clicking "Read Now" to jump directly to the current progress, or clicking "✕" to mark as unread (clears progress and removes the entry from History and Continue Reading). The reader automatically saves and restores the reading position upon entry.

### History & Progress Cleanup

| Action | Scope of Effect | Impact on Gallery Reading Progress | Safety & Confirmation Requirements |
| :--- | :--- | :--- | :--- |
| **Clear History** | Clears timeline records from history | Does not alter individual gallery reading progress bars | Confirmation modal required; request must include confirmation parameter |
| **Clear Reading Progress** | Resets reading progress for all galleries | All galleries marked as unread (progress reset to 0) and removed from Continue Reading | Confirmation modal required; request must include confirmation parameter |
