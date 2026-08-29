# GalleryVault (English)

GalleryVault is a private, self-hosted library manager for local gallery
archives. It indexes Ehviewer exports, CBZ/CBR archives and plain image folders
into a searchable web library, and can optionally sync tags and metadata from
ExHentai, download galleries, monitor favorite folders, and translate every tag.
The interface is available in English and Chinese (中文).

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

Open **http://<host>:8000**, log in with the default password **`p1a2s3s4`**
and change it in *Settings*. Configure your ExHentai cookies, run
*Favorites → Check all folders* once, put your galleries in `./library` and hit
*Scan library*.

### Recommended workflow

1. **Log in to ExHentai**: Settings → ExHentai, fill in `ipb_member_id` /
   `ipb_pass_hash` / `igneous` and verify with *Test login* (cookies are stored
   encrypted, never in the compose file).
2. **Read your favorites without downloading**: set the folder mode to *watch
   only* on the Favorites page, then run *Sync folder names* and *Check all
   folders* — metadata (title, tags, cover, size) is cached and the favorite
   set recorded, but **nothing is downloaded**.
3. **Scan the library**: put existing galleries under a library root and hit
   *Scan library*; the metadata cache from step 2 is reused.
4. **Deduplicate first**: group versions of the same work with *Manage
   favorites → Scan for duplicates* (cloud and local items are compared
   together, so duplicates can be unfavorited/ignored before downloading);
   clean up same-gid copies across scan roots on the *Duplicate copies* page.
5. **Start downloading**: switch the folder mode to *force* and run *Check
   now* — every folder gallery **not in the local library** is queued once
   (already-local galleries are skipped).
6. **Switch to incremental + schedule**: once the backlog is down, switch the
   mode back to *incremental* and turn on the **download favorites** master
   switch with an interval (e.g. 10 minutes); newly favorited galleries
   download automatically.

### Scope

GalleryVault is built **primarily for galleries downloaded by
[Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)**: a
`<gid>-<title>/` image folder plus a **`.ehviewer`** metadata file (SpiderInfo
VERSION1/VERSION2 with the gid/token and a per-page pToken), which the scanner
parses to restore the gallery identity exactly.

The `.ehviewer` format originates from Hippo Seven's EhViewer
(`com.hippo.ehviewer.spider.SpiderInfo`), so **any EhViewer-family client
writes a compatible file** and can be ingested directly:

- **Original EhViewer** ([seven332/EhViewer](https://github.com/seven332/EhViewer),
  deprecated); current active branches
  [**FooIbar/EhViewer**](https://github.com/FooIbar/EhViewer) (Material Design 3),
  [**Ehviewer-Overhauled/Ehviewer**](https://github.com/Ehviewer-Overhauled/Ehviewer),
  [**EhViewer-NekoInverter/EhViewer**](https://github.com/EhViewer-NekoInverter/EhViewer),
  [**exzhawk/EhViewer**](https://github.com/exzhawk/EhViewer),
  [**AdNotFound/EhViewer**](https://github.com/AdNotFound/EhViewer),
  [**WarnError/Ehviewer-NekoWhite**](https://github.com/WarnError/Ehviewer-NekoWhite),
  [**NotFaceGUI/EhViewer-Auto-Translation-Ver**](https://github.com/NotFaceGUI/EhViewer-Auto-Translation-Ver),
  [**axlecho/MHViewer**](https://github.com/axlecho/MHViewer) and other forks.
- Cross-platform ports: [**EhViewer-Apple**](https://github.com/felixchaos/EhViewer-Apple)
  (iOS/macOS), [**Ehviewer_OHOS**](https://github.com/suibianqwe/Ehviewer_OHOS)
  (HarmonyOS).
- Companion tools: [**LRReader**](https://github.com/Xslx98/LRReader) (Android,
  a LANraragi client), [**exhentai-manga-manager**](https://github.com/SchneeHertz/exhentai-manga-manager),
  [**ehviewer_manga_manager**](https://github.com/Schweik7/ehviewer_manga_manager)
  (Python CLI), [**LANraragi**](https://github.com/Difegue/LANraragi)'s
  `Ehviewer.pm` metadata plugin.

Other formats:

- **[JHenTai](https://github.com/jiangtian616/JHenTai)** (cross-platform Flutter,
  Android/iOS/Windows/macOS/Linux) download directories are **natively
  supported**: `<gid> - <title>/` plus a `metadata` JSON, so the full gallery
  identity (gid/token/tags/category/published time) is restored on scan.
  **This support is new and not yet validated against much real data** — please
  file an issue with a sample `metadata` file if you hit a parsing problem.
- Reduced fidelity: plain image folders named `<gid>-<title>` **without** an
  `.ehviewer` file and **CBZ/CBR** archives (gid must prefix the file name).
  Galleries without a gid can be browsed but **cannot take part in downloads,
  dedupe or duplicate-copy resolution**.

## Feature highlights

- **Local gallery library** — scan Ehviewer exports, CBZ/CBR archives and image
  folders into a persistent PostgreSQL index.
- **Tags & translation** — namespaced tag cloud, instant autocomplete, and
  EhTagTranslation-based translations (Chinese input reverse-matches).
- **ExHentai integration** — metadata/category/tags via your own cookies, HTTP
  or SOCKS5 proxy.
- **Download manager** — concurrent page downloads, live progress, resumable
  retries, `max_pages`, cancel and bulk retry. Image URLs are resolved lazily
  per page (fresh keystamp) so long galleries keep downloading even when a
  pre-signed URL would have expired mid-run.
- **Favorites monitor** — watches the ten ExHentai favorite folders,
  auto-downloads missing galleries, metadata cache reused by scans, duplicate
  scan with ignore/restore.
- **Reader & history** — streaming paging, keyboard/space/click, auto-advance,
  saved reading position.
- **Telegram notifications** (download digest by default), activity log page,
  optional at-rest encryption
  (`ENCRYPTION_KEY`, AES-256-GCM), non-root runtime, rate limiting.

## Where to go next

| Topic | Page |
|-------|------|
| Deployment, volumes, scan-only libraries, TLS | [Deployment](Deployment-EN) |
| Using the UI (browse, reader, tags, downloads, favorites, settings) | [Usage](Usage-EN) |
| Backup & restore | [Backup](Backup-EN) |
| At-rest encryption & lost-key recovery | [Encryption](Encryption-EN) |
| REST API reference | [API](API) · browsable [openapi.json](openapi.json) |
| Development notes | [Development](Development) |
| Troubleshooting | [FAQ](FAQ-EN) |
| UI screenshots (EN & 中文) | [Screenshots](Screenshots-EN) |

> Pages in Chinese: [首页](Home) · [部署](Deployment) · [使用指南](Usage) ·
> [备份与恢复](Backup) · [静态加密](Encryption) · [常见问题](FAQ) ·
> [界面截图](Screenshots)

## License

[MIT](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE).
