# Online Reading

> [中文](Online-Reading) · English | Part of the [Usage](Usage-EN) series

Browse ExHentai galleries online and read them while keeping server-side EH image usage at zero.

## Online browsing (`#/online`)

The legacy link `#/discover` opens the same page.

- **List types**: Search, Popular, Watched, and Toplist (yesterday / month / year / all).
- **Filters**: keyword, category checkboxes (the site category mask), minimum rating; the list defaults can be pinned in Settings.
- **Cards**: cover, title, category, page count, rating, plus badges for “in library”, “favorited”, “downloading x/y / queued / failed”.
- **Views and tags**: the Online list switches between grid / list / table in place, with the preference remembered per page (no table on narrow screens). List rows and table rows show the first 4 / 3 tags plus `+N`; grid cards hide tags by default and reveal them in an overlay on hover or focus. Clicking a tag re-runs the search with ExHentai's exact `ns:"name$"` syntax and refills the search box; long-press or right-click copies the raw `ns:name`. The Chinese UI shows the backend translation, the English UI the raw name.
- **Where list tags come from**: tags on the Online list are parsed from the tag nodes of each row in the ExHentai listing HTML, so they cost **no extra EH request** and take no page / gdata / favorites concurrency slot. Whether tags appear depends on your **site listing display mode**: modes that render tags include them, while Minimal / Thumbnail-like modes return none — the card then shows an explicit “no tags” placeholder and never issues another request just to fill tags. The number of tags per row is likewise bounded by the site listing layout.
- **Quick actions**: hover on desktop, long-press on mobile opens an action sheet for read / favorite / download without opening the detail page first.
- **State messages**: no results, login required, human verification, banned IP, and exhausted image quota each get an inline explanation and a link to Settings; errors are never treated as an empty result and paged through.
- **API fields**: each `GET /api/eh/search` result carries `tags[]` (each with `namespace` / `name` / `display`), `posted`, and `uploader` in addition to `gid` / `token` / `title` / `url` / `thumb` / `category` / `pages` / `rating` and the local badges. All of them come from the same listing parse with no extra EH request; `tags[]` may be empty for the reason above.

## Online detail (`#/online/g/<gid>/<token>`)

Cover and both titles, category / uploader / posted / pages / size / rating, then the action row (read · continue · favorite · download), namespace-grouped tags, and thumbnails.

- A newer version is announced with a jump link; when the gallery is already in the local library, “Open local copy” is shown.
- “Open on official page” opens `{site}/g/{gid}/{token}/` in a new tab using the browser's own EH session.
- Thumbnails lazy-load per preview page; clicking one starts at that page.

## Reader and the two image channels

The reader route is `#/online/g/<gid>/<token>/read/<page>`; page `0` means “resume the stored online progress”.

| Mode | Image path | Server cost | When to use |
| :--- | :--- | :--- | :--- |
| **Browser direct** (default) | The backend only resolves the single-page image URL; `<img>` fetches it straight from the H@H node | One light resolve per page (global EH page concurrency 6); **no server image concurrency or bandwidth** | Default; networks that can reach `*.hath.network` |
| **Server proxy** (fallback) | Images are proxied through `…/pages/<n>/image` | Spends server image concurrency (12) and the image cache (512 MB default cap) | Per device, only when the browser cannot reach H@H (blocked port, TLS interception, …) |

- Switch it in **Settings → Reader → Online image channel** (`gv_online_image_mode`; stored in the browser of that device only).
- Concurrency and preload: resolve and proxy share the “online concurrency” cap (default 3, `online_reader_concurrency`); the reader preloads at most 2 pages, so page turns cannot amplify resolve requests.
- Resolved URLs are cached server-side for 10 minutes (the H@H signature lives 15 minutes); an expired or failed image is resolved again, and a failure is retried twice on another node.
- Still failing: the page offers “use the server proxy on this device” and “open on the official page”; the reader never falls back silently.
- Image quota exhausted (509 / 429): preloading pauses and shows quota usage; it resumes afterwards instead of retrying in a loop.
- Online reading shares the layout modes (single-page LTR / RTL, double-page, double-page RTL, webtoon) and shortcuts with the local reader; see [Gallery detail & reading](Reading-EN).

## Privacy and network

- Resolving uses the EH account configured on the server; **your browser does not send EH cookies**, and no cookie is written into the page or a script.
- In direct mode the H@H node sees your browser's egress IP; image requests send no Referer.
- Resolved image URLs are time-limited and only used for the current reading session; they are never stored in the database, reading history, or exports.
- In proxy mode images pass through the GalleryVault server, so they **do** spend the server image budget and disk cache.
- The companion script only talks to the GalleryVault address you enter; it never reads or uploads EH login cookies.

## Favorites, downloads, and progress

- **Favorite**: choose a folder 0–9; the local state flips to favorited only after the cloud confirms it, otherwise it stays unchanged and shows an error. The default folder is configurable in Settings.
- **Download**: one click enqueues with the default quality, or pick resample / original on the detail page; once downloaded the gallery enters the local library and the online card shows “in library”.
- **Progress**: online progress is stored server-side per gallery (gid + token); “Browse” shows an “Online continue reading” strip, and both history and continue-reading store only the page number, never image URLs.

## Companion script (optional, zero server quota)

The companion script injects a panel into the **official E-Hentai / ExHentai gallery page** with:

- in-library / favorite / download state (queries only your GalleryVault local library, never EH);
- download to GalleryVault (resample / original);
- favorite to GalleryVault (optional folder);
- open the online gallery in GalleryVault.

The script does not implement a reader and copies no third-party code; for reading enhancements on the official page pair it with [Comic Looms](https://github.com/MapoMagpie/comic-looms) (MIT). On this path every EH request comes from your own browser and **spends no server-side EH quota**.

### Install

1. Install **Tampermonkey** or **Violentmonkey** on the desktop (mobile below).
2. Open `/galleryvault-companion.user.js` on your GalleryVault instance (the build artifact ships with the frontend), create a new script in the manager and paste it, or install the file directly.
3. Chrome / Edge (MV3) require the user-scripts permission on the extension details page (Chrome 138+ **Allow User Scripts**, older versions developer mode); otherwise the cross-site request API is unavailable.
4. Generate a token first in **Settings → Account & security → Companion script API token**: the plaintext is shown once, copy it immediately; revoking it invalidates any script using it at once.
5. Open any EH gallery page and fill in the GalleryVault address and API token in the panel. Both stay in the script manager and are never written into the page or logs.

The API token only reaches the endpoints the script needs (session state, local library status, favorite categories, add / remove favorite, create / query download tasks); every other endpoint returns `403`. The script reads no EH cookies and never renders the token into the page.

### Mobile

| Platform | Availability |
| :--- | :--- |
| Android | Firefox for Android (Tampermonkey / Violentmonkey) and Edge for Android (Tampermonkey from the add-on store) work; Kiwi Browser is discontinued. |
| iOS | Safari needs the Userscripts / Stay extension with per-site permission; `GM_xmlhttpRequest` semantics differ from desktop. |

Mobile support is best-effort; desktop Tampermonkey / Violentmonkey is the supported path.

## See also

- Settings groups and the network catalog: [Settings](Settings-EN)
- Online list and local library: [Library](Library-EN)
- Reader layouts and shortcuts: [Gallery detail & reading](Reading-EN)
- Download queue and archive: [Downloads](Downloads-EN)
