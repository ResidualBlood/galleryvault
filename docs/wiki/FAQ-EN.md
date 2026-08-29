# FAQ

## Settings keeps showing "Generating thumbnails…"?

It now shows the **live status** (generating / finished / hint text), read from
`/api/thumbs/status`. If thumbnails really are stuck, check the thumbnail task
on the Logs page (`#/logs`), or trigger it again with *Generate now*.

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

## The reader is slow to open large / animated (WebP) pages?

Pages are streamed straight from the backend to the browser. Older versions
sent them in the file's default 8KB chunks, and every chunk crosses a
threadpool boundary inside the streaming response — capping large-file
throughput at ~1MB/s (most noticeable for animated WebP, which can be tens of
MB per page). This is fixed by reading 256KB chunks instead (measured
~918KB/s → ~466MB/s on the same file, roughly 500× faster); small images are
unaffected.

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

See [Encryption → Recovering from a lost key](Encryption-EN).

## How do I change the port / bind a domain?

Edit the `ports` mapping in `docker-compose.yml` (e.g. `8000:80` →
`8080:80`) and run `docker compose up -d`. Domain binding is handled by nginx /
a reverse proxy — see [Deployment → Security hardening](Deployment-EN).

## Write operations (delete/submit) fail with "Cross-origin request rejected" when accessed over IPv6?

A bug in v1.2.3 and earlier: the CSRF origin check parsed the `Host` header with
`split(":", 1)[0]`, which splits inside an IPv6 literal (e.g.
`[240e:...]:8000`), so the `Origin` never matched the `Host` and every write
(`DELETE`/`POST`/`PUT`) returned 403. Fixed in v1.2.4 (`Host` is parsed with
`urlparse`). Upgrade to operate over IPv6, or access via a hostname / reverse
proxy instead.

## Favorites aren't auto-downloading?

All three must hold: the **download favorites** master switch in Settings is on
+ the folder is **enabled** on the Favorites page + the mode is "incremental"
or "force download". See [Usage → Favorites](Usage-EN).

## Favorites check succeeds but no covers / the list is empty?

- The backend needs **ExHentai cookies** configured (Settings → ExHentai →
  fill in `ipb_member_id` / `ipb_pass_hash` / `igneous` and use "Test login").
  They are stored **encrypted in the database** (`ENCRYPTION_KEY`) — do **not**
  set `EXHENTAI_COOKIES` in `docker-compose.yml`. Without cookies `favorites.php`
  redirects to the home page and the check silently records nothing.
- Cover thumbnails are captured from the listing's thumbnail cells during a
  check (`favorite_items.thumb`); run **Download missing items** on the
  Favorites overview (or let the scheduled sync) to download the cover files
  to the disk cache.

## The page shows a different number per page?

The gallery library uses **infinite scroll** (24 galleries per page, more as
you scroll; page size selectable at the bottom). Favorite folders use numbered
pagination with a 24-per-page default; the tag browse page uses numbered
pagination fixed at 100 per page (no page-size selector). If you still see an
old layout, hard-refresh (Ctrl+Shift+R) to load the new `assets/app.js`.

## How do I search by several tags at once?

Clicking a tag in the suggestions, on the gallery detail page or in the tag
cloud **appends** it to the active filter (all selected tags must match — AND),
instead of replacing it. The bar above the grid shows each active tag as a
removable pill (per-pill ×, an `AND` badge and a clear-all action); resubmitting
the title search keeps the current tag filter.

You can also type a mixed query in the box: e.g. `动图 中国` is split
automatically — `动图` is recognized as the tag `animated` (one-to-one Chinese
translation lookup) and combined (AND) with the keyword `中国`. `ns:name`
syntax (`parody:touhou`) and English tag names (`animated`) work too.

## Does my search filter survive reading and coming back?

Yes. When you open a gallery from a **searched library** (including tag
filters), the search context is kept throughout the **reader** — no matter how
you page (arrows / space / click / thumbnail links / auto-advance to the next
gallery) — so the back-to-details and back-to-library links still carry the
active query and tag filter, and you never land on an unfiltered library.

## How do I jump to the original gallery on ExHentai?

The gallery detail page has an **Open on ExHentai** button next to *Start
reading* that opens `{base_url}/g/{gid}/{token}/` in a new tab (your browser
must be logged in to EH); it is hidden for local galleries without a token. The
base URL is chosen in Settings (里站 / 外站 / custom).

## Will ExHentai-only galleries be misdeleted when I use the public mirror?

No. A gallery that only ExHentai exposes returns the same 404 as a deleted one
on `e-hentai.org`, but it is **not** treated as deleted: tag sync is *paused*
and the category stays untouched. Switching the base URL back to `exhentai.org`
in Settings **resumes** the sync automatically.

## How do I set the base URL (里站 / 外站)?

Settings → ExHentai → Base URL is a dropdown: `exhentai.org` (里站, full
functionality) / `e-hentai.org` (外站, some ExHentai-only galleries are not
visible) / Custom (proxy subdomain). The change takes effect **immediately**,
no restart needed.

Choosing **Custom** reveals a URL input (for a proxy subdomain such as
`https://proxy.exhentai.org`); only `exhentai.org` / `e-hentai.org` and their
subdomains are accepted — saving any other host fails.

## Which pages honour the title-display setting?

Settings → Downloads → **Title display**: `japanese` (default, Japanese title
preferred) / `english` / `directory` (folder name). The library, browse,
gallery detail, favorites (including cloud-only items), favorites-duplicates
and the duplicate-copies page all show the title according to this setting.
Downloaded folder names are **not** affected by it — they follow the separate
**Download title** setting in the same Downloads group: `japanese` (default,
`gid-<japanese title>`) or `english` (`gid-<english title>`). Existing
download folders are reused as-is; switching the setting never renames or
re-downloads them.
