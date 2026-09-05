# FAQ

## Why aren't some tags translated?

Translations come from
[EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)
(fetched automatically). Tags not covered by that database (mostly obscure
artists / original titles) stay as-is; multi-value tags (`A | B`) only show the
translated part and untranslated aliases are hidden. You can refresh manually
via *Update translations now* on the Logs page.

## After removing a library directory, do its galleries disappear?

A scan only soft-deletes (`expunged`) galleries that are still under a scanned
root but weren't seen this pass. Removing a directory from Settings alone does
not affect existing galleries; adding the directory back and rescanning
restores them. To avoid false expunges, remove the path from *Library roots*
before removing the directory.

## A download failed; the logs say `image download request failed`?

That's a **transient network failure** (ExHentai / H@H node or your proxy link),
not an app bug — retry it from the Downloads page. To diagnose, check the
backend logs (on the fixed build each line carries an `[error='...']` suffix):

```bash
docker logs galleryvault-backend --since 6h | grep -E "download task failed|page download failed"
```

- `[error='ReadTimeout']` → a H@H node stalled / is too slow; try another node
  or a different time window.
- `[error='ConnectTimeout']` / `[error='ConnectError']` /
  `[error='RemoteProtocolError']` → the proxy path is unstable. If you route
  through a UDP proxy such as Hysteria 2, jitter on the international link can
  drop long-lived streams — prefer a TCP-based protocol (VLESS+TCP / Reality /
  Shadowsocks / Trojan), or lower `page_concurrency`.
- `EhClientError: ExHentai request failed` → transient network error on a
  page/API request; it already backs off 30s and retries on its own.

## Downloads don't use concurrency / are slow?

- `download_concurrency` in Settings controls how many galleries download at
  once.
- The backend enforces a **global ExHentai concurrency cap**
  (`exhentai_max_concurrency`, default 6) to avoid triggering anti-bot; on
  rate limits (429/509) it backs off and retries.

## All devices logged out after I changed the password?

Yes, by design: changing the password **revokes every logged-in session**, so
each device has to log in again.

## Can't log in / password error?

- The default password is `p1a2s3s4` for first login — change it afterwards.
- If you turned off *Require login* in Settings, auth is bypassed (direct
  access, no password needed).

## I lost my key?

See [Encryption at Rest → Recovering from a lost key](Encryption-EN#recovering-from-a-lost-key).

## How do I change the port / bind a domain?

Change port mappings in `docker-compose.yml`; for reverse proxy configuration and domain binding see [Deployment → Security hardening](Deployment-EN#security-hardening).

## Write operations (delete/submit) fail with "Cross-origin request rejected" behind reverse proxy or across subnets?

This is CSRF protection detecting host mismatch across proxy boundaries; ensure the reverse proxy forwards the `Host` header (e.g. `proxy_set_header Host $http_host;`) or configure `TRUSTED_PROXIES`. See [Deployment → Security hardening](Deployment-EN#security-hardening).

## Red top banner says cookie is invalid or no ExHentai access?

A probe runs at startup and every 30 minutes, plus once right after login. The red top banner distinguishes two states:
- **Cookie expired**: session is expired; follow the banner to Settings, re-enter cookies and use *Test login*.
- **No ExHentai access**: account lacks ExHentai access (empty/blank 200 response on exhentai.org or Sad Panda); check account permissions, configure `igneous`, or switch base URL to `e-hentai.org`.

Cloud sync pauses while the cookie is invalid or lacks access.

## Can I get a deleted gallery back?

**Without deleting files** → see [Gallery Management → Recycle bin](Manage-EN#recycle-bin-and-restoring-galleries) *User deleted* to restore. Missing on disk after a scan → *Scan missing*. **Purge with delete files** cannot be undone from that page (a later scan will not re-ingest it).

## I hit Pause — why are downloads / scans still running?

After pause, no new pages are claimed; the current in-flight page finishes.
No new tasks are claimed. Scans return `paused`. The downloads-page toggle and Telegram
`/pause` `/resume` are the same switch (web pause matches the Bot) and survive
restart. See [Downloads → Global pause and resuming tasks](Downloads-EN#global-pause-and-resuming-tasks).

## Discover vs the local library?

`#/discover` browses and searches live ExHentai listings online; the library (`#/library`) manages galleries stored locally. See [Library & Browsing → Discover](Library-EN#discover-discover).

## Does Add to Home Screen download galleries onto the phone?

**No.** The PWA caches the UI shell only; js/css are network-first (cache on
offline fallback) and never cache gallery images or `/api/`.

## How do I use OPDS?

Third-party reader clients can connect to the OPDS catalog via HTTP Basic authentication (fixed username `galleryvault`, password is the web login password). Note that Basic auth is strictly limited to `GET /api/opds`; CBZ archive exports and all other `/api/*` endpoints require standard session cookies, are no longer unauthenticated, and do not accept Basic credentials. For details, see [Settings → OPDS & CBZ export](Settings-EN#settings-settings).

## Does scanning a 7z unpack the whole archive?

**No.** Only image suffixes are extracted; everything else stays packed.

## Downloads page warns that image quota is near the limit?

That is ExHentai Image Limit (cached ~30 min with GP). Above ~80% the top
banner warns you — pause to avoid HTTP 509.

## Do archive download retries or Range resumes charge GP multiple times?

**No**. When an archive download starts, the ExHentai zip URL is persisted under the task's metadata (`.archive.json`). Any subsequent resume (HTTP Range) or error retry continues with the same URL and **never charges GP again**. If an archive channel is completely unavailable, the task falls back cleanly to page-by-page downloading over H@H (which costs 0 GP).

## Incremental already downloaded the new version, but Gallery updates still lists it?

If the new gid is already in the local library, **Scan now** deletes the old copy and the row disappears — no need to click Update selected. Ignored rows are never auto-deleted. Favorites enqueue / ingest also pin and finalize the update row. See [Favorites & Updates → Gallery updates](Favorites-EN#gallery-updates-updates).

## Favorites aren't auto-downloading?

All three must hold: the **download favorites** master switch in Settings is on
+ the folder is **enabled** on the Favorites page (new folders are disabled by default and require checking and saving) + the mode is "incremental"
or "force download". See [Favorites & Updates → Favorites](Favorites-EN#favorites-favorites).

## Favorites check succeeds but no covers / the list is empty?

- The backend needs **ExHentai cookies** configured (Settings → ExHentai →
  fill in `ipb_member_id` / `ipb_pass_hash` / `igneous` and use "Test login").
  They are stored **encrypted in the database** (`ENCRYPTION_KEY`) — do **not**
  set `EXHENTAI_COOKIES` in `docker-compose.yml`. Without cookies `favorites.php`
  redirects to the home page and the check silently records nothing.
- **Check now** warms covers onto disk (`/gv-cache/remote-covers/{gid}.img`)
  in the background; opening a folder only reads that cache (`<img>` via
  `/api/favorites/cover`) and does not wait on ExHentai. Large folders fill in
  over time. Use **Download missing items** on the overview if some covers are
  still absent.

## How do I search by several tags at once?

Multiple tags can be combined with AND / OR modes and `-tag` exclusions. For usage details, see [Library & Browsing → Library](Library-EN#library-library).

## Does my search filter survive reading and coming back?

Yes. When you open a gallery from a searched library, the search context and tag filters are preserved across reader paging and back navigation. See [Gallery Detail & Reader → Reader](Reading-EN#reader-readeridpage).

## How do I jump to the original gallery on ExHentai?

The gallery detail page provides an "Open on ExHentai" button for galleries with a token (requires browser logged in to EH). See [Gallery Detail & Reader → Gallery Detail](Reading-EN#gallery-detail-galleryid).

## Will ExHentai-only galleries be misdeleted when I use the public mirror?

No. A gallery that only ExHentai exposes returns the same 404 as a deleted one
on `e-hentai.org`, but it is **not** treated as deleted: tag sync is *paused*
and the category stays untouched. Switching the base URL back to `exhentai.org`
in Settings **resumes** the sync automatically.

## How do I set the base URL (里站 / 外站)?

In Settings → ExHentai → Base URL, choose between `exhentai.org` (里站), `e-hentai.org` (外站), or a custom proxy domain. Changes take effect immediately. See [Settings → Settings](Settings-EN#settings-settings).

## Which pages honour the title-display setting?

Controls title display (Japanese / English / directory) across library, browse, detail, and favorites views independently from download folder naming. See [Settings → Settings](Settings-EN#settings-settings).
