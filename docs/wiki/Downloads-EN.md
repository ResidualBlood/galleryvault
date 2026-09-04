# Download Management

> [中文](Downloads) · English | Part of the [Usage Guide](Usage-EN) series

This guide covers GalleryVault's download management page, task queue controls, automatic self-healing, and ExHentai official zip archive downloads.

## Downloads (`#/downloads`)

- **Batch URL & GID/Token Enqueue**: Paste one or more gallery URLs or `gid/token` lines. **Enqueue pages** can override image quality; **Archive download** opens the same GP/tier preview as Favorites. Task titles follow the Title display setting (English/Japanese) instead of `gid xxx`.
- **Follow newer versions**: if ExHentai marks the listing as replaced, the download switches to the new gid (max 5 hops). Only the replacement link after the banner is followed — **Parent links are ignored**. 404/deleted galleries fail without retry, with plain-language errors in the list and Telegram. Gallery-detail “download original for this copy” does not follow.
- **Global pause**: the page toggle and Telegram `/pause` are the same switch (see [Settings](Settings-EN)); **after pause, no new pages are claimed; the current in-flight page finishes**, claiming and scans stop; it survives restart; Bot matches the web pause. The yellow top bar stacks with the Cookie red bar.
- **GP & image quota**: the page header shows a cached GP balance and Image Limit (~30 min TTL); above ~80% the top banner warns you to pause (avoid 509).
- Lists download tasks with their status (waiting / downloading / success / failed / cancelled), filterable by status.
- A **channel badge** next to each task title marks how it downloads: archive tasks show "Archive · Original/Resample" (or "Fallback pages" if an archive failure falls back to page-by-page), plain H@H page-by-page downloads show "Page-by-page", so the two channels are easy to tell apart.
- Active tasks show a **live progress bar** (`current/total` + percentage); the list auto-refreshes every 2 seconds.
- **Retries are resumable**: only the missing/failed pages are fetched; pages already on disk are skipped.
- **Failures self-heal**: a transient error (image timeout, ExHentai challenge, throttled H@H node) re-queues the task automatically with an **exponential backoff** (30s → 2m → 8m → 30m → 1h → … up to 6h), retried up to 10 times before the task is marked `failed`; a periodic sweep also re-activates older `failed` tasks that still have retry budget left, so the manual retry button is rarely needed.
- Waiting and downloading tasks (both pending and downloading) can be **cancelled** (the worker will not write to disk once cancelled); failed/cancelled/successful tasks can be **retried** (individually or in bulk with checkboxes).
- **Clear all successful**: one click removes every `success` task record (the confirm dialog shows the count). This only clears the task list; **ingested gallery files are not deleted**. Failed, cancelled, and in-progress tasks are left alone.
- **A finished download is ingested into the index immediately** — the gallery row, pages and tags are written straight from the download result (cover thumbnail generated on first view), with **no full library scan**. The stored signature matches the scanner, so a later manual scan skips it.
- With Telegram configured, you get notified on download success/failure and scan completion; download notifications default to a **summary** digest (a bulk run collapses into one message), switchable to immediate / failures-only / off in Settings.

## Archive Downloads (ExHentai archive)

The official zip channel packs the whole gallery into a zip file on the server (spending **GP**) and the client streams it on a single connection — far faster than per-page H@H fetches for large galleries. Three entries share one executor:

- The **"Archive download selected" / "Archive update selected"** buttons in the `#/favorites/<favcat>` and `#/updates` toolbars open a **cost preview** first (read-only, never charges GP): the current GP balance on top, then a row per gallery with original/resample cost and size, tiers that cost more than the balance marked red. Pick a tier and confirm to enqueue. Original = full-resolution originals; Resample = the server's fixed one-level resample (the default tier — cheaper in GP and bandwidth).
- **"Download selected original" / "Update selected original"** still download page-by-page but **force original quality** regardless of the global quality setting.
- **Scheduled scan**: with "Archive large favorites on scheduled scan" and a **page threshold** enabled in Settings, automatic favorites checks send galleries over the threshold through the archive channel (using the "Archive quality" tier) and keep the rest page-by-page. Threshold 0 = everything archived.
- Archive tasks occupy a `download_concurrency` slot and share the same FIFO queue as page-by-page tasks; if the same gid already has a pending task, the archive button reports a skip.
- **Reliability**: the zip resumes via HTTP Range; `quality + zip URL` are persisted under `.gv-{gid}/.archive.json`, so a retry **only resumes — it never re-packs or re-charges GP**; a corrupt zip is deleted and re-packed; when the archive channel cannot serve the gallery (selected tier unavailable, insufficient GP, corrupt zip) the download **falls back to page-by-page by default** (no GP cost, H@H carries the traffic) — disable "Fall back to page-by-page if archive is unavailable" in Settings to fail the task immediately instead, without burning automatic retries. On completion the archive goes through the same finishing pipeline as page-by-page downloads: `.ehviewer` / `.galleryvault.json` metadata, Telegram notification, immediate ingest, and old-version cleanup for gallery updates.
