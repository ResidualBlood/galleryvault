# Download Management

> [中文](Downloads) · English | Part of the [Usage Guide](Usage-EN) series

Download queue, retries, and ExHentai's official zip archive channel.

## Downloads (`#/downloads`)

The download management view oversees queued, downloading, and historical tasks, providing quota monitoring, status filtering, and batch operations.

### Enqueue Methods & Image Quality

The "Add Download" modal at the top supports multi-line URL or `gid/token` batch enqueueing.

| Enqueue Method | Input Format | Quality Determination Rule | Behavior & Constraints |
| :--- | :--- | :--- | :--- |
| **Page-by-page** | Multi-line URLs or `gid/token` | Explicitly choose Original or Resampled; defaults to the global image quality setting (resampled if unspecified) | Fetches images sequentially across H@H nodes. Automatically follows replacement galleries (up to 5 hops); "Download original for this copy" on detail pages does not follow replacements; 404/deleted galleries abort immediately with explicit prompts |
| **Archive download** | Multi-line URLs or `gid/token` | Select Original or Resampled in the popup cost preview window | Uses the official ExHentai archive channel, streaming a single zip package over one connection; consumes account GP |

Task titles are parsed into Japanese or English based on the "Title display" configuration in Settings.

### Status, Badges & Task Operations

The task list refreshes automatically every 2 seconds and supports filtering by status; idle refreshes update only changed rows instead of redrawing the whole table.

| Task Status | Channel Badge | Progress Display | Available Operations | Behavior Boundary |
| :--- | :--- | :--- | :--- | :--- |
| **Waiting (pending)** | Page-by-page · Original/Resample<br>Archive · Original/Resample | Queued waiting | Cancel | Once cancelled, background workers perform no disk writes |
| **Downloading (downloading)** | Page-by-page · Original/Resample<br>Archive · Original/Resample<br>Fallback pages | Live progress bar (current/total, percentage, speed, and ETA) | Pause (global), Cancel | Global pause halts claiming of new pages while current in-flight pages finish; cancelling stops all page writers first, then removes the `.gv-<gid>` temp directory and releases its usage accounting |
| **Success (success)** | Corresponding channel badge (marked with archive ok / pending / fail when entering cold storage) | 100% | Retry, Clear record | Clearing successful tasks only removes entries from the task list and does not delete ingested gallery files; retrying re-enqueues the task |
| **Failed (failed)** | Corresponding channel badge | Paused at failure progress | Retry (single or batch with checkboxes) | Only missing or failed pages are downloaded; completed pages are skipped; clears backoff count and triggers immediate retry |
| **Cancelled (cancelled)** | Corresponding channel badge | Paused at cancellation progress | Retry (single or batch with checkboxes) | Reactivates task to continue downloading unfinished pages |

The toolbar action "Retry all tasks" clears backoff counters on pending, failed, and cancelled tasks and immediately re-enqueues them. "Clear all successful" prompts with a confirmation dialog showing the affected count, then purges all successful task records from the list. Bulk and destructive buttons are disabled while their request is in flight to prevent double submission.

### Execution Control & Risk Safeguards

- **Global Pause**: The system automatically triggers a global pause upon encountering ExHentai 302 anti-abuse verification challenges (`remoteapi.php`). The web interface toggle and Telegram `/pause` command control the same switch. When pause is active, background workers stop claiming new pages and suspend directory scans, while in-flight page transfers finish downloading. The pause state persists across container restarts. Each task counts 302 challenges independently without consuming its normal retry budget; once the limit is reached (default 5, environment variable `GV_MAX_CHALLENGE_PAUSES`), the task is marked failed with its remaining retry budget preserved, and can be recovered with a manual retry.
- **Quota Monitoring**: The header displays cached GP balances and image limits (Image Limit, refreshed roughly every 30 minutes). When image limit consumption exceeds approximately 80%, a yellow warning banner appears on the top bar recommending pausing downloads to avoid triggering HTTP 509.

### Retry Mechanism & Integrity Verification

- **Resumable Gap Filling**: Retries strictly fetch missing or failed pages; pages already saved to disk and verified are skipped.
- **Image Integrity Verification**: Verifies file magic bytes upon writing to disk, supporting JPEG, PNG, WebP, and GIF animation magic bytes `b"GIF8"`, preventing HTML error pages or disguised corrupted files from entering the library.
- **Node Rotation**: When encountering single-page transfer errors or slow nodes, the request sends the failed node key to the scheduler to switch to another node. If the page provides no node key, HTML is parsed and task state is updated before switching nodes.
- **Exponential Backoff & 429/509 Rate-Limit Backoff**: Transient network errors trigger exponential backoff retry intervals (30s, 2m, 8m, 30m, 1h, up to 6h), marking the task failed after 10 cumulative attempts. HTTP 429/509 responses are classified as quota/rate-limit errors: the client records the server's `Retry-After` (60 seconds when absent) and the task is re-queued with exponential backoff instead of being retried immediately as a single-page transient error. Failed tasks are not automatically resurrected by a background sweep; recover them with **Retry** or **Retry all tasks** on the Downloads page (which resets the backoff counters).

### Task Completion & Notifications

- **Immediate Ingestion**: Upon download completion, gallery records, page entries, and tags are written directly to the database with cover thumbnails generated as needed, bypassing full library scans. Stored file signatures match the scanner, so subsequent manual scans skip these folders automatically. If a full library scan is running, download ingestion is deferred and processed automatically after the scan finishes; it is not dropped.
- **Telegram Notifications**: When Telegram Bot is configured, the system pushes notifications on download completion, download failure, version replacements, or 404 deletions. Notifications default to summary digest mode, with options in Settings to switch to immediate, failures-only, or disabled.

## Archive Downloads (ExHentai archive)

The official ExHentai archive channel packages the entire gallery into a single zip file on the server. Clients stream the file over a single connection, providing an efficient path for large galleries.

### Trigger Entries

- **Favorites & Updates**: In Favorites (`#/favorites/<favcat>`) or Updates (`#/updates`), click "Archive download selected" or "Archive update selected" in the toolbar.
- **Scheduled Automatic Archiving**: Enable "Archive large favorites on scheduled scan" in Settings and define a page threshold. During scheduled favorite sweeps, galleries exceeding the threshold use the archive channel (with the specified archive quality), while galleries below the threshold use page-by-page downloads. Setting the threshold to 0 routes all galleries through the archive channel.

### Cost Preview

Initiating an archive download opens a read-only cost preview modal without deducting GP in advance:
- Displays current available GP balance at the top;
- Lists each gallery's estimated cost and file size for Original and Resampled tiers;
- Displays a red missing-tier warning if the server does not provide a specific tier.

### Enqueue Confirmation

After selecting a quality tier (Original or Resampled) in the preview modal and confirming, tasks enter the download queue:
- Original tier downloads full native resolution; Resampled tier downloads the server's single resampled edition;
- Archive tasks share the download queue with page-by-page tasks; archive zip streaming itself is capped at 2 concurrent transfers, independent of `download_concurrency` (which takes effect immediately when changed);
- If a gallery already has a pending page-by-page or archive task, re-adding prompts and skips the duplicate.

### Resumable Transfer

Archive downloads support HTTP Range resumable transfers:
- Assigned quality and zip download URLs are persisted in temporary metadata within the gallery directory;
- Interrupted downloads or manual retries reuse the existing URL for resuming without re-applying on the server and without charging GP again;
- The whole transfer is protected by the low-speed watchdog: after the warm-up window (default 30 seconds), an average rate below the configured floor (default 10KB/s) aborts the transfer as throttled, and it can be resumed by retrying.

### Re-packaging

If a downloaded zip file is corrupted or fails verification, the system deletes the corrupted local file, reapplies to the server, and requests a fresh download URL.
If the task's quality tier changes between attempts (for example resample to original), the cached zip URL is discarded and the archive is requested again for the new tier, which may consume GP again.

### Page-by-page Fallback

When the archive channel cannot serve the gallery (selected tier unavailable, insufficient account GP, or persistently corrupt archive packages):
- **Fallback Enabled (Default)**: Automatically falls back to page-by-page downloads over H@H nodes without deducting GP. The task state updates to fallback pages and displays the "Fallback pages" badge.
- **Fallback Disabled**: When "Fall back to page-by-page if archive is unavailable" is turned off in Settings, failing archive tasks are marked failed directly without fallback, preserving automatic retry attempts.

### Completion & Ingestion

When an archive zip completes downloading, it executes the standard finalization pipeline: writes `.ehviewer` and `.galleryvault.json` metadata, sends notifications, ingests immediately into the database, and deletes superseded version files if the task was a gallery update.
