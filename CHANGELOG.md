# Changelog

All notable changes to GalleryVault are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Cold storage CBZ & hot download directory naming convention** (`docs/wiki/Settings.md`, `docs/wiki/Settings-EN.md`, `docs/wiki/Deployment.md`, `docs/wiki/Deployment-EN.md`): 明确落盘命名规则约定：设置 `download_title` 仅控制下载热目录 `download_root` 新建文件夹命名（无日文标题时自动 fallback 英文），Archive 冷库归档 CBZ 文件名固定采用英文 `gallery.title`（带 gid 前缀，如 `gid-title.cbz`）且不跟随 `download_title` 设置，以保证跨系统兼容性与备份稳定性。
- **Favorites batch download & original upgrade behavior documentation** (`docs/wiki/Favorites.md`, `docs/wiki/Favorites-EN.md`): 完善收藏夹批量下载对已入库画廊的升级与跳过规则说明：普通「下载所选」已入库仍跳过（skip）；「下载所选原图」已是 original 跳过，本地 resample/unknown 则逐页 original 升级入库并在 ingest 后删除旧副本（含 CBZ）；「归档下载所选」已是 original 跳过，本地非 original 且用户选 original 档则触发 `gallery_archive` original 升级，选 resample 档仍跳过；未入库画廊照旧正常下载。
- **Cold storage volume and directory renamed to Archive** (`docker-compose.yml`, `docker-compose.dev.yml`, `frontend/assets/locales/`, `docs/wiki/`): 将冷库卷挂载与目录命名规范为 `./Archive:/archive`，前端设置提示路径示例更新为 `/archive`，设置项展示对齐为「归档 / Archive」，保持可选与默认关闭（不自动归档、不删源）。
- **Cold storage settings default-off & compose volume commented** (`backend/galleryvault/config.py`, `frontend/assets/views/settings.js`, `docker-compose.yml`, `docker-compose.dev.yml`): 冷存储归档相关配置（`cold_storage_root`、`auto_archive_downloads`、`archive_delete_source`）默认全关闭，前端设置控件并入资料库分区且仅显式勾选生效；docker-compose 中冷库卷挂载与环境变量改为可选注释。

### Fixed

- **Downloads page-by-page task quality badge** (`frontend/assets/views/downloads.js`): 下载页逐页下载任务（非归档通道）支持根据 `quality` 字段显示原图 / 重采样（`original` / `resample`）画质 Badge。
- **Gitleaks false positive allowlist** (`.gitleaks.toml`, `.gitleaksignore`): gitleaks 忽略 test_logging 历史假阳性。


## [1.8.0] - 2026-09-05

### Added

- **Series cloud items & manual exclusions** (`backend/alembic/versions/0032_series_cloud_items.py`, `backend/alembic/versions/0033_series_cloud_exclusions.py`, `backend/`, `frontend/assets/views/series.js`): 系列作品支持展示云端未下载收藏，并可通过 GID 或收藏夹快速手工添加；未下载画廊提供云端角标与一键下载，且支持将误匹配项目手工移出云端。
- **Series grouping & management** (`backend/`, `frontend/assets/views/series.js`): 新增系列作品独立页（`#/series`），支持基于标题规范化与作者前缀的自动成组规则、扫库自动重构及手工建组/改名/删组/画廊调配。
- **Series rebuild task log** (`backend/galleryvault/app/routers/series.py`, `frontend/assets/views/logs.js`): 系列重新整理写入日志页。

### Changed

- **Cover hit/miss logging** (`backend/galleryvault/services/favorites_worker.py`, `backend/galleryvault/app/routers/favorites.py`, `backend/galleryvault/app/routers/galleries.py`): 封面 miss/回源/降级打 INFO，命中不刷屏。
- **Series auto matching rule & pagination** (`backend/galleryvault/services/series.py`, `backend/galleryvault/db/repositories/series.py`, `frontend/assets/views/series.js`): 系列作品默认按同人/漫画分类过滤并支持分页与「显示全部」切换；自动聚类支持循环剥离展会与活动前缀。
- **Gallery card cover presentation** (`frontend/assets/styles.css`, `frontend/assets/views/`): 画廊卡片封面（Browse/Library/Discover/Favorites/Recycle/Integrity 与继续阅读）调整为 contain 前景并叠加高斯模糊同图铺底，横向封面不再裁切（槽位保持 3:4）；画廊详情页缩略图与重复副本小图维持 cover 裁切。

### Fixed

- **Remote cover fallback on miss** (`backend/galleryvault/app/routers/galleries.py`): 浏览封面 miss 先本地 0.jpg，后台拉 remote-covers。
- **Series cloud cover API routing** (`backend/galleryvault/app/routers/series.py`, `backend/galleryvault/db/repositories/series.py`): 系列云端卡片封面改走 `/api/favorites/cover` 统一缓存与鉴权代理。
- **Remote cover fallback for gallery card covers** (`backend/galleryvault/app/routers/galleries.py`, `backend/galleryvault/services/favorites_worker.py`, `backend/galleryvault/services/thumbnails.py`): 有 gid 的卡片封面改用 EH 原 thumb 缓存（`remote-covers`），内页 thumb 保持不变。
- **Gallery detail back navigation** (`frontend/assets/views/`): 详情/阅读器返回完整来路（如 `#/favorites/1` 而非收藏夹根）。
- **Duplicate thumbnail key path validation** (`backend/galleryvault/app/routers/duplicates.py`): 校验 `GET /api/scan/duplicates/thumb/{key}` 的 key，拒绝空、斜杠与路径穿越，解析路径严格限制在缩略图根目录内。
- **CBZ export authentication & temp path confinement** (`backend/galleryvault/app/middleware.py`, `backend/galleryvault/app/routers/galleries.py`): CBZ 导出不再放行 Basic Auth，对齐常规会话鉴权；临时导出文件锚定在 `download_root/.exports` 受控目录且响应后自动清理。
- **Pending download cancellation & abort before write** (`backend/galleryvault/app/routers/downloads.py`, `backend/galleryvault/services/download_worker.py`): `pending` 状态下载任务支持取消标记；下载 worker 在任务执行前后及写入前校验取消状态，确保取消后立即中断且不落盘。
- **Multi-copy partial deletion DB-disk consistency** (`backend/galleryvault/services/deletion.py`): 多副本画廊本地删除出现部分失败时，同步更新 DB 仅移除已成功删除的副本路径，避免 DB 记录指向已删磁盘路径。
- **System log download path confinement** (`backend/galleryvault/app/routers/settings.py`, `backend/galleryvault/logging.py`): 日志下载与文件路径解析严格限制在配置的系统日志根目录下，防止越界读取。

## [1.7.1] - 2026-09-04

### Added

- **Clear notifications** (`frontend/assets/views/components/notifications.js`, `backend/routers/notifications.py`): 通知面板支持「清空」（`POST /api/notifications/clear`），可一键清除所有应用内通知。
- **Favorites folder filters** (`frontend/assets/views/favorites.js`, `frontend/assets/utils.js`, `frontend/assets/events.js`, `backend/`): 收藏夹详情可折叠高级筛选（对齐画廊库），支持本地星级评分、页面范围、文件大小、发布日期、上传者、画质、语言、本地列表筛选与排序。

### Changed

- **Settings sections reorganized** (`frontend/assets/views/settings.js`, `frontend/assets/styles.css`): 设置页划分为账户、界面（含 `title_display`）、站点与代理、资料库、下载常用设置、下载高级选项（折叠）、标签、缩略图与 Telegram 设置（折叠）等独立分区。
- **Gallery detail local fields collapsed under More** (`frontend/assets/views/gallery.js`): 画廊详情本地字段（本地星级、笔记、自定义标签等）收纳到「更多」操作菜单/折叠面板后。

### Fixed

- **Notification timestamp timezone** (`backend/services/notifications.py`): 通知 `created_at` 采用容器本地时区（`datetime.now().astimezone()`，非 UTC 截断）。
- **Top bar z-index** (`frontend/assets/styles.css`): 顶栏层级调整为 `z-index: 30`，避免画廊复选框盖住通知面板。

### Performance

- **Library exact tag filtering by tag_id** (`backend/`): 书库精确标签筛选改走内部 `tag_id` 查询，提升大库标签检索效率。
- **Favorites exact tag filtering by tag_id** (`backend/`): 收藏夹列表与书库共用 tag 谓词，精确点选走 `tag_id`。


## [1.7.0] - 2026-09-04

### Added

- **OPDS & CBZ HTTP Basic auth** (`backend/`): Added HTTP Basic authentication support for `GET /api/opds` and `GET /api/galleries/{id}/export.cbz` using fixed username `galleryvault` and the web login password. Session cookie authentication remains supported; failed or missing credentials return `401` with `WWW-Authenticate: Basic realm="GalleryVault OPDS"`. Other `/api/*` endpoints remain cookie-only.
- **Favorites select-all** (`frontend/assets/views/favorites.js`, `frontend/assets/events.js`): Added "Select All" button to the `/favorites/:id` toolbar (left of Clear Selection) to select currently rendered gallery cards; scrolling to load more cards allows clicking again to append newly rendered cards.

### Fixed

- **Disk usage calculation & settings responsiveness** (`backend/`, `frontend/`): `GET /api/system/storage` no longer executes synchronous directory traversals (`os.walk`) on request; library size is queried from DB `storage_size`, volume metrics read from `shutil.disk_usage`, and downloads/cache use in-memory snapshots with live mutation deltas alongside periodic background `du` calibration. Settings UI returns sub-second and displays computing status while actively polling.
- **Downloads page jump focus polling preservation** (`frontend/assets/views/downloads.js`): Skipped periodic 2s polling re-render when the pagination jump input (`#dl-pages .page-jump`) is actively focused, preventing active input elements from being destroyed and losing focus while typing a page number.
- **Pagination page jump input** (`frontend/assets/utils.js`, `frontend/assets/events.js`): Changed pager jump input to text (`inputmode="numeric"`) with jump triggered on Enter keypress or blur on value change, preventing premature `change` events on `type="number"` inputs from causing premature full-page re-renders and lost focus while typing.
- **Discover card badges position** (`frontend/assets/styles.css`): Moved gallery card status badges from top-right to bottom-left to prevent overlap with batch selection checkboxes.
- **Duplicate copies import & management scan feedback** (`backend/`, `frontend/`):
  - Fixed duplicate record synchronization failing silently during library scan due to invalid relative import `ResolvedGroup` (`ModuleNotFoundError`), restoring duplicate group persistence to `duplicate_records`.
  - In Management → Duplicate Copies (`#/duplicates`): scanning now checks global pause state before polling logs, automatically polls until scan completion before reloading the duplicate list, and restores active pill highlight styling when toggling All / Pending / Dismissed filters.

### Changed

- **Top-bar layout spacing** (`frontend/assets/styles.css`): Adjusted desktop topbar spacing (`gap: 10px`), prevented random browse icon button and notification bell wrapper from shrinking, and refined search bar flex layout.
- **Gallery details collapsible metadata panels** (`frontend/assets/views/gallery.js`, `frontend/assets/styles.css`): Reorganized local rating, custom tags, local note, favorite note, and related lists into 5 independent `<details>` collapsible panels on the gallery detail page (`#/gallery/:id`). Panels remain closed by default without auto-expanding, keeping controls always in the DOM and matching library details/summary styling.
- **Library advanced filters collapsible toolbar** (`frontend/`): Collapsed secondary library filter controls (sort order, read status, page/size/date ranges, uploader, quality, language, rating, list) into a native `<details>` toolbar menu displaying active filter count and expanding automatically when query parameters are active.
- **Documentation information architecture refactoring** (`README.md`, `README.en.md`, `docs/wiki/`, `docs-site/`): Refactored project documentation into a single-screen README, modular wiki handbook (Features, Compatibility, Library, Reading, Downloads, Favorites, Manage, Settings), pure-operations Deployment guide, FAQ stripped of how-to guides, and aligned Pages / VitePress navigation.
- **Pages CI build & caching** (`.github/workflows/pages.yml`): Pages workflow adjusted to hourly schedule + push to `main` only (`dev` push disabled); schedule runs compare git diff against last successful run and skip redundant builds if documentation/site files are unchanged; exact `node_modules` cache restore added to skip `npm ci` entirely on cache hit. Shallow checkout (`fetch-depth: 1`) and Vite cache restore/save (`docs-site/.vitepress/cache`, `node_modules/.vite`).
- **Archive fallback channel badge** (`backend/`, `frontend/`): `GET /api/downloads` surfaces `archive_fallback`; the Downloads page badge displays "回退逐页" / "Fallback pages" instead of the archive quality tier when an archive download fails and falls back to page-by-page (`mode` unchanged).
- **Navigation top-bar & management tabs** (`frontend/`): Desktop top navigation condensed to Browse, Discover, Library, Tags, Downloads, Favorites, Management, and "More" dropdown (History, Settings, Logs). Management tab shell (`#/recycle`, `#/integrity`, `#/duplicates`) unifies Recycle Bin, Integrity Check, and Duplicate Finder; mobile hamburger menu keeps a flat structure. Existing routes and hash URLs remain backward-compatible.


## [1.6.1] - 2026-09-03

### Added

- **Discover Popular / Watched / Toplist** (`GET /api/eh/search?list=`, `#/discover`): same parser, badges, 90s cache, download/favorite buttons; paths `/popular`, `/watched`, `/toplist.php?tl=` (11/12/13/15); cursor still `next=gid-ts`.
- **Library filters**: size (bytes), posted date, uploader, `image_quality`, language shortcuts via `language:` tags, local star rating, local list; sticky query.
- **Saved searches** (`user_settings.saved_searches`, get+merge, max 30) and **local lists** (`local_lists` / `local_list_items`, CBZ without gid allowed).
- **Local rating / note / `local:` tags** and **favorite notes** (`favorite_items.note`; EH HTML parse when present; edit via applyfav `favnote`, cloud-success only).
- **PWA** (shell-only service worker, no gallery image cache), **light theme** (`gv_theme`), **disk dashboard** (`GET /api/system/storage`), **notification persistence** (`cache/notifications.json`), **7z/PDF scanners** (py7zr / pypdf), **OPDS** (`GET /api/opds`, cookie auth), Bot `/stats`.
- **Webtoon reader mode** (`frontend/assets/views/reader-webtoon.js`, `reader.js`): vertical continuous scroll with `loading="lazy"` and IntersectionObserver progress (`PUT /api/galleries/{id}/progress`, 0-based). Mode cycles LTR → RTL → Double → Double RTL → Webtoon; click/arrow paging and double-page layout are not applied in webtoon. Toolbar keeps `G` jump and back-to-details.
- **Single-gallery CBZ export** (`GET /api/galleries/{id}/export.cbz`, `services/export_cbz.py`): existing `.cbz` is streamed as-is; directory galleries are packed in page order with `ZIP_STORED` to a tempfile. Member paths must stay inside the gallery directory (zip-slip → 400); missing files → 404. Detail page has an Export CBZ button; writes an `export-cbz` task log.
- **In-app notification center** (`services/notifications.py`, `GET/POST /api/notifications`): memory ring (maxlen 100) for download complete/fail, library scan complete/fail, and cookie expiry — recorded even when Telegram is off or unconfigured. Cookie entries are deduped per state. Top-bar bell + unread badge + dropdown; poll ≥15s. Cookie red banner is unchanged.
- **Telegram bot `/help` `/queue` `/cancel`** (`services/telegram_bot.py`, `messages.py`): `/help` lists pause/resume/status/help/queue/cancel and paste-URL enqueue; `/queue` summarizes pending/running/failed (capped under 4096); `/cancel <id|gid>` uses the same cancel path as `POST /api/downloads/{task_id}/cancel` and replies when not found. Unknown non-URL text replies with help (`force=True`).
- **ExHentai discover search page** (`app/routers/eh.py`, `services/eh_client.py`, frontend `views/discover.js`): new `#/discover` browses/searches ExHentai (not Popular/Watched/Toplist). `GET /api/eh/search` (`q`, `category` as site `f_cats` mask, `min_rating`, `next=gid-ts` cursor — never `page=N`) parses listing HTML like favorites, JOINs local library/favorite badges, and caches the EH payload 90s. Cards show cover/title/category/pages/rating with stackable 已入库/已收藏/未下载 badges; one-click download (`POST /api/downloads`, default resample) and favorite (`POST /api/favorites/add`, cloud-success only). Sad Panda / empty-body challenge / 509 / cookie expiry are distinct from “no hits”; `remoteapi.php` 302 is not cookie failure.

### Changed

- **Usage documentation** (`docs/wiki/Usage.md`, `docs/wiki/Usage-EN.md`): Added dedicated section for Local Lists (`#/library`) and documented the Ignored items page entry (`#/favorites/ignored`).

### Fixed

- **Fresh install default password login deadlock** (`auth.py`): `verify_login_password` now compares against `DEFAULT_PASSWORD` (`p1a2s3s4`) when no password/hash is configured (`effective is None`), unlocking fresh deployments.
- **Trusted proxies runtime settings reactivity** (`auth.py`): `is_trusted_proxy` now prioritizes runtime settings from `app_state.settings` before falling back to `get_settings()`, properly enforcing client IP resolution.
- **Favorites check failure record signature mismatch** (`services/favorites_worker.py`): corrected `FavoritesRepository.checked` call on check failure from 3 arguments to 2, ensuring failure timestamps are recorded in the database.
- **Reader premature gallery navigation on unset total** (`frontend/assets/views/reader.js`): `advance`, `retreat`, and `readerSwapPage` now guard against invalid or non-positive `app.readerTotal`, preventing shortcut keys from jumping galleries before pages are loaded.
- **ExHentai cookie health classification & notification separation** (`services/eh_client.py`, `services/notifications.py`, `frontend/assets/core.js`, `frontend/assets/locales/`): Empty or blank HTTP 200 responses on `exhentai.org` / `*.exhentai.org` are now classified as `no_exhentai_access` after two probe attempts; empty responses on `e-hentai.org` or unknown hosts surface as `failed`. `check_login` retries once on transport errors or empty/blank 200 bodies, while Sad Panda responses immediately return `no_exhentai_access`. In-app notifications (`kind="cookie_no_access"`) and top banners now cleanly distinguish expired cookies (`not_logged_in`) from missing access rights (`no_exhentai_access`), removing misleading expired notices.
- **Alembic 0030 revision length** (`alembic/versions/0030_favorites_monitor_enabled_default.py`): 0030 原 revision 超过 alembic_version varchar(32) 导致升级失败，已缩短为 `0030_favmon_enabled_default`。
- **New favorites folders defaulted to enabled** (`db/models.py`, `alembic/versions/0030_favorites_monitor_enabled_default.py`, `app/routers/settings.py`): new `favorites_monitor` rows default to disabled (`enabled=False`, opt-in) in database server default, model, and settings router; existing rows remain unchanged.
- **Discover toplist returned 404** (`services/eh_client.py`, `app/routers/eh.py`): `exhentai.org/toplist.php` does not exist (404); toplist requests now hit `https://e-hentai.org/toplist.php` with explicit cookies passed from settings. Toplist pagination now uses page numbers `p=N` (`_TOPLIST_CURSOR_RE`, `0 <= p < 200`) instead of `next=gid-ts` cursor, detects next page links via `_toplist_next_cursor`, and router validates numeric cursors for toplist mode.
- **Discover compact covers were empty** (`services/eh_client.py`): e-hentai Compact `glthumb` cover is `https://ehgt.org/w/…/….webp` and not inside the title `<a>`; parse listing cells (`glthumb` / `gl1e` / `gl3t`) like Ehviewer_CN_SXJ, rewrite `/w/` thumbs to `ehgt.org`, and skip chrome icons (`/g/t.png`). CSP still ehgt-only.
- **Discover listing thumbs blocked by CSP** (`services/eh_client.py`, `frontend/nginx.conf`, `views/discover.js`, `frontend/sw.js`): rewrite preview thumbs to `https://ehgt.org/...` like Ehviewer_CN_SXJ `getFixedPreviewThumbUrl`; CSP `img-src` allows `https://ehgt.org` only (not exhentai hosts); in-library cards use `/api/galleries/{id}/thumb/0`, others render ehgt URLs with `referrerpolicy="no-referrer"`. Non-ehgt hosts are dropped when rewrite fails; http ehgt URLs are upgraded to https. Installed PWAs drop the old document CSP via `gv-shell-v3`.
- **7z scan extracts images only** (`scanners/sevenzip.py`): `scan()` validates every member path then `read(targets=…)` / `extract(targets=…)` image suffixes only; non-images such as `payload.bin` stay packed so junk or path-bomb 7z cannot fill the temp disk. `open_page` still extracts a single file.
- **PWA js/css no longer cache-first** (`frontend/sw.js`): script/style assets are network-first and refresh the cache on success (offline falls back to cache); cache name `gv-shell-v2` so installed clients drop the old shell. `/api/` and gallery images still bypass the SW.
- **Quota near-limit copy** now uses `quotaNearLimit` on the yellow banner; `GET /api/quota` OpenAPI documents `gp` + `image_limit`.
- **Bot `/cancel` only cancels pending/downloading** (`services/telegram_bot.py`): `/cancel <id|gid>` no longer reports success for failed/success/cancelled tasks; gid lookup uses the latest in-progress or queued row.
- **Discover search covers used `blank.gif`** (`services/eh_client.py`): thumbnail-mode listings with `src="blank.gif"` + `data-src` now skip placeholder gifs (`blank.gif` / `509.gif`) and prefer `data-src`, so discover cards keep the real ehgt cover.

## [1.6.0] - 2026-09-03

### Added

- **Download paste titles, archive button, follow newer version, 404 notices** (`services/download_prepare.py`, `app/routers/downloads.py`, `services/eh_client.py`, `services/telegram_bot.py`, frontend `views/downloads.js`): paste/bot enqueue now fills English+Japanese titles (`download_tasks.title_jpn`, list follows `title_display`); download page has page-by-page and archive buttons (archive reuses GP preview with gid+token); replaced listings follow the new gid (max 5 hops, not gallery-original); 404/deleted fail without retry with plain-language Telegram/UI copy; bot replies include the title.
- **Library batch add to favorites + page/rating range UI + Chinese exclude** (`app/routers/favorites.py`, `frontend/views/library.js`, `frontend/assets/components.js`, `frontend/assets/events.js`, `frontend/assets/utils.js`, `frontend/assets/locales/`, `alembic/versions/0027_gallery_trash.py`): Library now supports selecting multiple galleries and batch adding to a chosen favorite folder via `POST /api/favorites/add` (chunked 25, `successful_gids` cloud-first, skips without GID with toast); toolbar adds `page_min/page_max/min_rating` inputs (sticky via `libraryContext`/`tagFilterHash`); Chinese exclude tag `-female:巨乳` verified via `test_batch2_library_search` (SQL ilike with Unicode).
- **Global pause (persistent) + GP/Quota cache + Recycle Bin + Missing pages体检** (`config.py`, `app/schemas.py`, `app/routers/tasks.py`, `app/routers/galleries.py`, `db/models.py`, `db/repositories/galleries.py`, `services/deletion.py`, `services/download_worker.py`, `services/downloader.py`, `services/scan_worker.py`, `services/telegram_bot.py`, `services/eh_client.py`, `frontend/assets/views/downloads.js`, `frontend/assets/views/recycle.js`, `frontend/assets/views/integrity.js`, `frontend/assets/core.js`, `frontend/assets/locales/`): Added `global_paused` (persisted via `app_config.user_settings` with `get()`+merge, survives restart via `update_runtime_settings`, `POST /api/pause` + `GET /api/pause`, download worker claim pause + per-page dispatch pause + scan pause (returns `paused` not 423), Telegram `/pause`/`/resume` sync same flag, top banner stacks with Cookie banner + downloads page toggle updates `app.paused` instantly; `GET /api/quota` cached **GP + Image Limits** 30 min TTL (low-frequency, not per-page, `image_limit`/`image_limits`); `Gallery.trashed`/`trashed_at` + `alembic 0027` + `POST /api/galleries/{id}/favorite` deprecated note, `GET /api/galleries/trash`/`expunged`/`integrity` + `POST /api/galleries/restore`/`purge` (purge uses `delete_galleries_local(..., delete_files, trash=False)`), `GET /api/galleries/integrity` page_count vs `gallery_pages` only (excludes `page_count is None`, `file_count` mismatch and `max_pages` truncation via `DownloadTask`), frontend Recycle/Integrity pages with `selRecycle`/`selIntegrity`.
- **Multi-criteria library sorting, reading status filtering & exclude tags** (`app/routers/galleries.py`, `db/repositories/galleries.py`, `alembic/versions/0026_gallery_sort_indexes.py`, frontend `views/library.js`, `utils.js`, `components.js`, `events.js`, `styles.css`, `locales/`): Added database sorting by posted date, title (follows `title_display` / `coalesce(title_jpn,title)`), page count, file size, rating, and ingest date; reading status filtering (`unread`/`reading`/`completed`); exclude tag filtering (`-namespace:name` or `-tag`) with distinct pill rendering, gallery card tag click (Shift/Ctrl/Alt adds exclude `-ns:name`), and tag AND/OR mode toggle; sticky propagation of `order_by`/`read_status`/`tag_match`/`min_rating`/`page_min`/`page_max` across navigation and infinite scroll; additive database indexes (`rating`, `page_count`, `file_size`).
- **In-folder favorite title search & multi-field sorting** (`app/routers/favorites.py`, `db/repositories/favorites.py`, frontend `views/favorites.js`, `locales/`): Favorite folder views now support instant title text search and sorting by last seen, first seen, posted date, title, and size.
- **Cookie health background probe & top banner alert** (`services/eh_client.py`, `app/lifespan.py`, `app/routers/settings.py`, `app/routers/auth.py`, frontend `core.js`, `locales/`): Added `probe_cookie_health` (via `check_login`, not `remoteapi.php`) with startup, on-save and 30-min periodic probes (`cookie_health_loop`), `GET /api/settings/cookie-health`, and automatic top banner warnings when ExHentai cookies expire or lose access; login now eagerly refreshes health once (and polls every 10 min) so a late startup probe does not hide the banner.
- **Download page batch URL & gid/token enqueue** (frontend `views/downloads.js`, `styles.css`, `locales/`): Added top paste box supporting single or multi-line gallery URLs and `gid/token` pairs with optional quality tier override (`resample`/`original`), batch enqueueing, 409 duplicate queue detection, and summary toast reporting.
- **Gallery detail Add to Favorites & Folder Switching** (`app/routers/favorites.py`, `services/eh_client.py`, `app/schemas.py`, frontend `views/gallery.js`, `components.js`, `locales/`): Added `POST /api/favorites/add` and `EhClient.add_favorite`/`add_favorites` targeting ExHentai popup act (`gallerypopups.php?act=addfav`), writing to DB `favorite_items` only upon confirmed cloud success; gallery detail page now presents "Add to Favorites / 加入收藏" and "Change Folder / 更改收藏夹" modals with 0–9 folder selection.
- **Reader page jump input & `G` keyboard shortcut** (frontend `views/reader.js`, `events.js`, `styles.css`, `locales/`): Reader toolbar now features direct page number input with Enter / form submission jumping, and `G` shortcut key to focus the jump input or prompt in fullscreen mode.
- **Home/Browse page "Continue Reading" cards & single gallery progress clearing** (`app/routers/galleries.py`, frontend `views/browse.js`, `views/history.js`, `styles.css`, `locales/`): Browse view now renders a "Continue Reading / 继续阅读" grid of recently read galleries with cover thumbnails, progress bars, one-click reader resumption, and per-gallery "Mark as unread / ✕" progress reset.

### Changed

- **Tags page Chinese autocomplete** (`frontend/views/tags.js`, `frontend/assets/events.js`, `frontend/assets/locales/`): the tags search box now uses the same CJK tag-suggest dropdown as the top bar; picking a suggestion stays on `#/tags` and filters the cloud (namespace + English name). Submitting Chinese uses `zh=1` and keeps only local tags (`usage_count>0`). Button/placeholder renamed to 「搜索标签」 / "Search tags". Top-bar search is unchanged.

### Fixed

- **Review-fix batch (P0–P2)** (`updates`/`favorites`/`downloader`/`eh_client`/`reader`/`recycle`/`quota`): recycle-bin gids no longer finalize/hard-delete old copies; gallery* downloads fail on `replaced_by` instead of 0-page success; replacement parse ignores Parent-before-hint; pause/cancel re-checked while waiting to acquire the page semaphore (unclaimed pages stop; in-flight page finishes); Bot pause reads `app_state.settings.global_paused`; favorites add is a move (cloud-success only; add exception does not treat unconfirmed gids as success; mid-loop abort still returns already-succeeded gids) and remove keeps cloud failures; trashed/expunged favorites show as cloud and can be re-downloaded; gdata `file_size` is not written onto `Gallery.file_size`; quality infer still fetches gdata when seeded metadata lacks `file_size`; prepare follows HTML replacement banners even when gdata/cache have titles (HTML first, gdata only on HTML failure); unread/reading/completed are mutually exclusive; reader jump input is no longer wiped and double-page suffix shows `p1-p2 / total`; cookie health GET re-probes after 10 min and `failed` is not treated as expired; recycle tab selection/restore; download paste drops unparseable lines; GP vs Image Limit cache freshness is split (IL fetch failure or empty/None uses 60s TTL); replacement hops use `>= 5` with a distinct error; mark-read uses `upsert_progress`; gallery detail progress is 1-based; integrity no longer hides missing pages via historical `max_pages` tasks; FAQ pause wording matches Usage.
- **Mark as unread left Continue Reading intact** (`db/repositories/galleries.py`): `DELETE /api/galleries/{id}/progress` now also deletes that gallery's `reading_history` row, so Browse Continue Reading and the History list drop the card instead of reloading the old page number after refresh.
- **Favorite folder page showed only `#N`** (`frontend/assets/views/favorites.js`): folder detail `#/favorites/<favcat>` now uses the ExHentai folder name from `/api/favorites/categories` (same source as the overview table), with `#N` as a badge.
- **Tag suggest left partial query as title search** (`frontend/assets/events.js`): clicking a suggestion now consumes tokens that are substrings of the selected tag (CJK any length, ASCII length ≥2), so 「和泉」 + 「和泉纱雾」 no longer ANDs a leftover title keyword. Top bar, library, and browse share this path; tags-page suggest unchanged.
- **Favorites check no longer applied metadata / inferred quality / recorded Tasks history** (`services/favorites_worker.py`): `favorite_size_sync` again runs `apply_metadata_to_galleries`, infers `image_quality` from local size vs gdata, and writes a `metadata` row to task history when the last in-flight folder finishes.
- **Favorites folder open blocked on remote covers** (`services/favorites_worker.py`, `app/routers/favorites.py`): restoring the pre-`8daeeb5` contract — a folder check/`download-missing` warms `/gv-cache/remote-covers/{gid}.img`, and `#/favorites/<favcat>` returns `cover_url=/api/favorites/cover` instead of downloading+base64-inlining covers on the request path. Cache reads accept both `.img` and `.jpg`. `favorite_size_sync` no longer calls the missing `gids_for_favcat`.
- **Pause overwrote user settings** (`app/routers/tasks.py:53`, `services/telegram_bot.py:81`, `services/settings_service.py:63`): `POST /api/pause` and Telegram `/pause` now `get()` then merge `{"global_paused": …}` before `save()`, so a pause no longer wipes `exhentai_cookies`/`library_roots`/`download_root`. Added `global_paused` to `update_runtime_settings` allowlist so the flag hydrates from DB on restart (persistent).
- **Purge left files behind and soft-delete toast showed 0** (`app/routers/galleries.py:520/1006/1035`, `services/deletion.py`, `frontend/views/recycle.js:61`, `frontend/views/library.js:234`): `POST /api/galleries/purge` now calls `delete_galleries_local(..., delete_files, trash=False)` so `delete_files=true` actually removes on-disk copies (scan won't re-ingest); `delete_files` is forwarded from frontend `recyclePurge()` `confirm(deleteFiles)`. `delete-bulk`/`delete-filtered` `deleted` now counts `trashed` as well, so "no-file-delete → trash" toasts no longer show `已删除: 0`.
- **Pause only stopped claim, not new pages; scan 423 too broad** (`services/downloader.py:341`, `services/download_worker.py:433`, `app/routers/tasks.py:154`): download `Downloader._download_pages` now checks `global_paused` before dispatching each new page (current pages finish, new pages wait 1 s), `POST /api/scan` when paused returns `{"status":"paused"}` (202) instead of 423.
- **Integrity false positives and missing max_pages exclusion** (`db/repositories/galleries.py:677`): `page_count is None` and `file_count != page_count` no longer reported; `max_pages` intentional truncation ( `DownloadTask.max_pages == Gallery.page_count` ) excluded; added `DownloadTask` exists check.
- **Image Limit not shown and Usage docs wrong about pause** (`services/eh_client.py:1457`, `app/routers/tasks.py:85`, `frontend/views/downloads.js:58`, `frontend/core.js:18`, `frontend/events.js:125`, `docs/wiki/Usage.md:181`, `docs/wiki/Usage-EN.md:421`): `EhClient.fetch_image_limits()` parses homepage `Image Limit` box, `GET /api/quota` now returns `image_limit`/`image_limits` alongside GP (same 30 min cache, low-frequency), downloads page shows `GP + Image Quota` with >80% banner warning, top yellow pause banner stacks with Cookie red banner, `toggle-pause` updates `app.paused` instantly, and Usage docs corrected to "global pause persistent, stops claim + new pages, survives restart".
- **Gallery updates left stale after incremental download** (`services/updates_worker.py`, `services/favorites_worker.py`, `services/download_worker.py`): a new gid already ingested by favorites incremental/force download (or already in the library) is now treated as a finished update — detection and ingest delete the old local copy instead of leaving a pending `#/updates` row. Favorites enqueue pins existing update rows to the live download task; an in-flight task found during detect is stored as `downloading`. Ignored rows are never auto-finalized.
- **Filtered delete 500 on title search & read-status misalignment** (`app/routers/galleries.py:194/878`, `app/schemas.py`, `frontend/views/library.js`, `frontend/utils.js`): Fixed `ValueError: too many values to unpack` where `delete_galleries_filtered` unpacked 3 values from `_resolve_search_tokens` (now 4 with `explicit_exc`), causing 500 when deleting with a title query; `q` with `-ns:name` now correctly routes to `exclude_tags`. `FilteredDeleteRequest` now carries `read_status`/`order_by`/`exclude_tags`/`tag_match` and delete forwards `read_status`/`min_rating`/`page_min`/`page_max` to `list_page`, so "delete current filter" while filtered to `unread` no longer deletes `completed` galleries.
- **Cookie banner not shown after login due to async probe race & missing periodic poll** (`services/eh_client.py`, `app/lifespan.py`, `frontend/core.js`, `app/routers/auth.py`): `probe_cookie_health` remains via `check_login`; added `cookie_health_loop` (30 min) with startup probe and shutdown cleanup. Frontend now refreshes `GET /api/settings/cookie-health` once after login (when `cookie_health.state=="unknown"`) and polls every 10 min, updating the top `⚠️ Cookie 已失效` banner immediately.
- **Gallery card invalid nested links & list page import hot path / filter stickiness** (`frontend/assets/components.js:48`, `frontend/assets/events.js:111`, `backend/galleryvault/db/repositories/galleries.py:1`, `frontend/assets/utils.js:120`): Replaced nested `<a>` inside `<a class="gc">` with `<span data-action="filter-tag" role="button">` and `stopPropagation` so tag clicks never trigger gallery navigation or browser DOM splitting; extracted `_title_sort_column()` to avoid per-sort `import app_state` in `list_page` hot path; `libraryContext()` and `tagFilterHash()` now carry `min_rating`/`page_min`/`page_max`/`min_pages`/`max_pages` so tag clicks and detail back-navigation preserve advanced filters; added `Shift/Ctrl+click` tag → `-ns:name` exclude with `stopPropagation` and Usage docs for it.
- **Continue reading cover URL and 409 duplicate queue detection** (frontend `views/browse.js`, `views/downloads.js`, `core.js`): Fixed cover image URL path to `/api/galleries/{id}/thumb/0`, attached `res.status` to `api()` thrown errors, and correctly detected duplicate 409 conflict messages on URL queueing.
- **Reader fullscreen jump prompt and dynamic favorite URL base** (`views/reader.js`, `app/routers/favorites.py`, `app/routers/galleries.py`): Pressing `G` in fullscreen mode or when the jump input is hidden now properly prompts for page number; favorite item URL dynamically formats from configured `exhentai_base_url` instead of hardcoded host.
- **ExHentai cloud favorite add consistency & error isolation** (`app/routers/galleries.py`, `app/routers/favorites.py`): Replaced legacy non-existent repository calls with cloud-first verification, ensuring local database records are never updated when cloud ExHentai requests fail.

## [1.5.1] - 2026-09-02

### Added

- **Clear all successful download tasks** (`POST /api/downloads/clear-success`, downloads UI): one-click bulk delete of `status=success` task rows (confirmation shows the count). Ingested gallery files are not touched; failed/cancelled/in-progress tasks stay.

### Fixed

- **Favorites duplicate scan crash on cached tags** (`services/favorites_worker.py`): `_parse_gdata_tags` treated `metadata_map` dict tags (`{namespace, name}`) as gdata strings and called `.strip()` on them (`AttributeError` at enriching, UI `error N/N`). Parser now accepts dict / `[ns, name]` / `"ns:name"`.
- **System Logs no longer flooded by Telegram long-poll** (`logging.py`): `_HttpAccessFilter` (drop httpx 2xx/3xx) is now attached to the in-memory RingBuffer as well as stdout/file. The runtime logs page was still showing `getUpdates` 200 every 30s because the filter never reached the buffer the UI reads.

### Changed

- **Dev dependency lower bounds** (`backend/pyproject.toml`): `pytest-xdist>=3.8.0,<4`, `ruff>=0.16.5,<1`, `pre-commit>=4.6.2,<5` (Dependabot #17/#18/#19).
- **Pages Actions bumps** (`.github/workflows/pages.yml`): `configure-pages` v5→v6, `upload-pages-artifact` v3→v5, `deploy-pages` v4→v5 (closed Dependabot #7/#8 plus matching deploy action).
- **CI skip noise**: `ci-backend` ignores `backend/docs/**`; `ci-frontend` ignores markdown. Image build/merge runs only when Dockerfile / runtime source / dependency files change (tests-only and docs-only commits no longer push Docker Hub).
- **Monorepo layout**: backend and frontend live in one repository (`ResidualBlood/galleryvault`); CI path-filters `ci-backend.yml` / `ci-frontend.yml`, and a single `v*` tag publishes both images. Archived `galleryvault-backend` / `galleryvault-frontend` remotes are read-only.
- **Dependency updates & CI action bumps** (`.github/workflows/`, `backend/pyproject.toml`, `backend/requirements.txt`, `.github/dependabot.yml`): Bumped `actions/download-artifact` from v4 to v8, `actions/upload-artifact` from v4 to v7, and `astral-sh/setup-uv` from v5 to v7 in GitHub Actions workflows. Updated backend dependencies `httpx` (`>=0.28.1,<1`), `rarfile` (`>=4.5,<5`), `cryptography` (`>=50.0.1,<51`), `pytest` (`>=9.1.1,<10`), and `pytest-cov` (`>=7.1.0,<8`). Configured Dependabot target branch to `dev`.

## [1.5.0] - 2026-09-02

### Added

- **Multi-mode reader with RTL Manga, Double-page spread & mobile gestures** (frontend `views/reader.js`, `styles.css`, `locales/`): Added LTR, RTL Manga, and wide-screen Double-page spread modes with persisted preference, directional preloading, responsive layout, double-tap zoom, and mobile pinch-to-zoom gestures.
- **Modal dialog accessibility & Focus Trapping** (frontend `components.js`): Standardized `trapModalFocus` across modal dialogs with `role="dialog"`, `aria-modal="true"`, Tab/Shift+Tab focus cycling, Escape closing, and focus restoration to the trigger element.
- **Local development hot-reload compose** (`docker-compose.dev.yml`): Added `docker-compose.dev.yml` with source mounting, `uvicorn --reload` support and isolated database volume for zero-build hot-reloading in local development.
- **Configurable runtime user permissions via PUID/PGID** (`entrypoint.sh`, `docker-compose.yml`, `docs/wiki/Deployment.md`): Backend container now defaults to running directly as `root (0:0)` for zero-configuration startup when unconfigured, with integer validation, dynamic user/group allocation, marker permission hardening, and support for custom user/group privilege dropping when `PUID` and `PGID` environment variables (e.g. `1000:1000`) are provided.
- **Rolling file logging, crash hydration & log download export** (`logging.py`, `app/routers/settings.py`, `config.py`, frontend `views/logs.js`, `locales/`): Added `RotatingFileHandler` support (10MB × 3 backups, max 30MB disk cap) saving to `./cache/logs/galleryvault.log`, startup memory hydration preloading recent logs into the expanded 2000-entry RingBuffer on container restart, and `GET /api/system/logs/download` with a frontend "Export Log / 导出日志" button for zero-friction diagnostic archiving.
- **Batch move favorite galleries endpoint & UI modal** (`app/routers/favorites.py`, `services/eh_client.py`, `db/repository.py`, `app/schemas.py`, frontend `components.js`, `views/favorites.js`, `locales/`): Added `POST /api/favorites/move` endpoint supporting batch chunking (25/batch) to move selected galleries to target ExHentai favorite folders (0–9) via `POST /favorites.php` (`ddact=favX`), with local DB `favorite_items` updates and frontend modal folder selector.
- **Structured logging, diagnostic ring buffer & dynamic log level APIs** (`logging.py`, `app/routers/settings.py`, `app/schemas.py`, frontend `views/logs.js`, `styles.css`): Added exception traceback formatting, ANSI terminal colors, sensitive credential masking (`ipb_*` cookies, Telegram tokens, passwords/secrets), background worker correlation context (`bind_log_context`), an in-memory RingBuffer with `GET /api/system/logs`, `POST /api/system/logs/level` (dynamic runtime log level adjustment without restart), `DELETE /api/system/logs`, and a real-time System Runtime Logs viewer tab in the web UI.
- **Optional Dozzle container recipe** (`docs/wiki/Deployment.md`): Documented optional Dozzle integration recipe for real-time multi-container log viewing with read-only Docker socket mount and security guidelines.

### Fixed

- **Reader double-page spread slot persistence & single-spread retreat** (frontend `views/reader.js`, `styles.css`): Fixed missing second image slot in DOM when retreating from a single-page spread (such as an odd-numbered final page) back to dual-page spreads in fullscreen mode, ensuring permanent two-slot DOM layout, dynamic visibility toggle, and touch-point dynamic transform origin computation for 2.2x double-tap zoom.
- **Reader fullscreen DOM preservation & seamless mode switching** (frontend `views/reader.js`): Fixed full-page container teardown during single cover ↔ double spread and reading mode transitions, preserving the top-level `.reader` fullscreen DOM state without browser fullscreen interruptions.
- **Unified double-page spread navigation & step alignment** (frontend `views/reader.js`): Unified pagination logic across toolbar buttons, arrow keys, and side clicks via `getReaderNav`, standardizing odd-numbered spread pagination (`[1-2]`, `[3-4]`) and aligning `prev`/`next` steps across direct URL/history jumps.
- **Mobile fullscreen double-page layout specificity** (frontend `styles.css`): Added high-specificity CSS rules under `@media (max-width: 640px)` for `.reader:fullscreen .reader-spread img` to properly apply full-width vertical column stacking on narrow viewports without 50vw distortion.
- **Reader toolbar misclick prevention & fullscreen exit on last page** (frontend `views/reader.js`): Excluded `.reader-bar` and `.nav` areas from page-flip click handlers to avoid accidental page turns when clicking page counter labels or toolbar spacing. Added `exitReaderFullscreen()` before advancing to the next gallery on the last page.
- **Concurrent cold-start in-flight task sharing for favorite counts** (backend `services/favorites_worker.py`, `tests/test_favorites_worker_helpers.py`): Replaced boolean refresh flag with shared `_fav_counts_refresh_task` in-flight task awaiting for `wait_on_cold=True`, ensuring concurrent cold starts return populated counts without duplicate requests.
- **Test monkeypatch target & shutdown engine dispose logging** (backend `tests/test_l_items.py`, `app/main.py`): Fixed `test_l8` cache monkeypatch target pointing to `favorites_worker` module, and added diagnostic warning logging to lifespan database engine disposal.
- **ExHentai viewer link extraction & non-gallery 404 isolation** (`services/eh_client.py`, `tests/test_latest_requirements.py`): Scoped gallery page collection strictly to the target gallery GID (`rf"/s/[0-9a-fA-F]+/{gid}-\d+"`), ignoring external gallery links referenced in user comments. Isolated 404 handling so only `/g/` gallery root returns `GalleryGoneError`, while sub-page `/s/` and archive endpoint 404s surface as retryable `EhClientError`.
- **Pytest unawaited coroutines & Connection._cancel warnings** (`app/main.py`, `tests/test_l_items.py`, `tests/test_delete_local.py`): Fixed unawaited `refresh_favorite_counts` coroutine in test mock callbacks, added missing `@pytest.mark.asyncio` across chunked query tests, and added graceful `engine.dispose()` during lifespan shutdown.
- **Container logging permissions, rotated log hydration & multiline traceback parsing** (`entrypoint.sh`, `logging.py`, `app/lifespan.py`, `app/routers/settings.py`): Ensured `/gv-cache/logs` is created with `app:app` (uid 10001) ownership before privilege dropping. Enhanced `hydrate_from_file` to merge rotated history backups (`.log.X`) in chronological order and parse multiline exception tracebacks via a state machine without truncation. Moved log hydration to the asynchronous startup lifespan.
- **Exception traceback loss in log formatters & workers** (`logging.py`, `services/download_worker.py`, `services/scan_worker.py`, `services/tag_sync_worker.py`): Fixed `_Formatter` ignoring `record.exc_info` and `record.stack_info`, and replaced opaque `error=type(exc).__name__` across backend workers with `logger.exception` and full error context.
- **Reader URL sync without hashchange loops** (frontend `views/reader.js`): `syncReaderUrl` now uses `history.replaceState` instead of assigning `location.hash`, avoiding a second `hashchange` → `renderReader` pass and history-stack growth.
- **Hidden double-page slot empty src** (frontend `views/reader.js`, `styles.css`): Omit `src` on the unused second image when the last spread is a single page; fullscreen single-image layout uses `:has`.
- **Favorite-count refresh cancellation** (backend `services/favorites_worker.py`): `asyncio.shield` plus a done callback so cancelling the caller does not drop the in-flight fetch and spawn a duplicate.
- **Favorites move cloud-first consistency & favcat dedupe** (backend `app/routers/favorites.py`, `db/repository.py`): Local DB updates only for cloud-confirmed `successful_gids`; two-phase cleanup before unique `(favcat, gid)` writes.
- **Lifespan settings whitelist, translation updater & shutdown** (backend `app/lifespan.py`, `services/settings_service.py`): Startup loads settings via `update_runtime_settings`; `refresh_services` restarts or cancels the translation updater; shutdown guards missing `aclose` and clears service pointers.

### Changed

- **Removed unused leftover files**: dropped empty `galleryvault/api/` package (stale facade note, zero imports) and frontend `smoke.spec.js` (Playwright smoke not wired into CI).
- **Backend main.py slimming & AppState SSOT architecture** (backend `galleryvault/app/`): Slimmed `app/main.py` from 1246 lines to <100 lines pure application factory. Extracted `app/middleware.py` (authentication & CSRF), `app/lifespan.py` (startup/shutdown & background worker lifecycle), and established `app/state.py` (`app_state`) as the single source of truth for runtime services and database session factories. Removed all facade re-exports and monkeypatch lookup anti-patterns across routers and workers, with strict AST guard tests (`tests/test_no_main_facade.py`) enforcing architecture boundaries.
- **Database repository domain modularization** (`db/repositories/`, `db/repository.py`): Modularized `repository.py` into clean DDD domain submodules (`galleries.py`, `favorites.py`, `downloads.py`, `updates.py`, `jobs.py`, `settings.py`, `base.py`) while preserving full backward-compatible re-exports on `galleryvault.db.repository`.
- **Worker & router test coverage expansion** (`tests/test_scan_worker.py`, `tests/test_tag_sync_worker.py`, `tests/test_duplicates_router.py`, `tests/test_favorites_worker_helpers.py`): Added unit and integration tests boosting backend code coverage to >62% with zero runtime warnings.
- **Lifespan modularization & worker lifecycle extraction** (`app/lifespan.py`, `app/main.py`): Extracted database pool warmup, active-check temporary partial downloads cleanup, and graceful worker shutdown to `galleryvault.app.lifespan` while keeping full backward compatibility on `app.main` for monkeypatched tests and routers.
- **ExHentai API chunking constantization** (`services/eh_client.py`, `services/favorites_worker.py`): Replaced hardcoded chunk size `25` across favorites delete/move and metadata resolution with `EXHENTAI_API_CHUNK_SIZE`.
- **Frontend modal promise safety** (`assets/components.js`): Added `settled` guards for archive preview async callbacks and ensured move dialog confirm button disables when no selectable target folders exist.
- **Startup & connection pool acceleration** (`app/main.py`): `seed_thumbnails` now runs as a non-blocking spawned background task instead of synchronously blocking the FastAPI lifespan and `/healthz` readiness. The database connection pool is pre-warmed on startup (`SELECT 1`) to eliminate cold connection latency on the first client request.
- **Tag reverse-search autocomplete acceleration** (`services/tag_translation.py`): `search_zh` now queries against a pre-built, pre-cased flat list `_ZH_SEARCH_ENTRIES` in namespace priority order with early-exit on limit, replacing full-table regex cleaning (`clean_display`) and case-folding on every keystroke.
- **Thumbnail generation & Pillow DCT decoding** (`services/thumbnails.py`): JPEG thumbnail generation now uses Pillow's fast `.draft('RGB', ...)` DCT-scale decoding for large image inputs and drops the redundant multi-pass `optimize=True` Huffman overhead during JPEG encoding.
- **Query performance & Anti-Join rewrite** (`db/repository.py`): Rewrote `exclude_favorited` in `list_page` from `NOT IN (subquery)` to correlated `NOT EXISTS` anti-joins, enabling direct PostgreSQL index seeks on `favorite_items` and `gallery_updates`.
- **Nginx compression & Frontend parallelization** (`nginx.conf`, frontend `views/reader.js`, `views/browse.js`, `views/gallery.js`): Nginx now enables on-the-fly Gzip compression (`level 5`) across static CSS/JS assets and JSON APIs. The reader view caches gallery metadata in memory (`app.readerGallery`) across page flips within the same gallery, avoiding redundant full gallery manifest GET requests. View initialization calls in browse and gallery views run in parallel via `Promise.allSettled`.

## [1.4.1] - 2026-09-01

### Added

- **Clear all gallery reading progress endpoint and UI button** (`routers/galleries.py`, `db/repository.py`, frontend `history.js`, `events.js`): Added `DELETE /api/galleries/progress` to reset reading progress across all galleries with confirmation dialog on the History page, alongside `DELETE /api/galleries/{identifier}/progress` for single-gallery resets.

### Fixed

- **Gallery grid keyboard navigation for ArrowUp/ArrowDown** (frontend `assets/events.js`): Fixed keyboard navigation on gallery card grids where `ArrowUp` and `ArrowDown` previously moved focus by single steps (`±1`) identically to `ArrowLeft`/`ArrowRight`. Grid column count is now dynamically computed from layout styles (`gridTemplateColumns`) or row offsets, correctly moving focus vertically across rows (`±cols`).
- **Download worker GalleryGoneError (404) terminal classification** (`services/download_worker.py`): When an online gallery is removed (HTTP 404 / `GalleryGoneError`), the download worker now treats it as a non-retryable terminal failure, marks it `failed` immediately, and exhausts the retry count (`retry_count = max_retries`) so periodic sweeps do not repeatedly retry deleted galleries.
- **Settings refresh state synchronization & Telegram bot task cancellation** (`services/settings_service.py`, `app/main.py`): `refresh_services()` in `settings_service` now delegates to `main._refresh_services()` (or synchronously updates both `app_state` and `main.app.state`), ensuring background workers (`download_worker`) and `get_downloader()`/`get_eh_client()` immediately adopt the newly created client instead of holding closed client references (`RuntimeError: Cannot send a request, as the client has been closed.`). `start_telegram_bot` now cancels previous polling tasks across both `app.state` and `app_state.extra` so polling loops do not leak on closed clients after saving settings.

## [1.4.0] - 2026-09-01

### Fixed

- **Multi-chapter and bilingual gallery update normalization** (`services/updates_worker.py`, `db/repository.py`, `alembic/versions/0025_gallery_metadata_versioning.py`): `normalize_update_title` now strips multi-chapter/episode ranges, volume/part/date ranges, and bilingual separator segments. `GalleryRepository.list_page` and `FavoritesRepository.favcats_for_gid` now track active superseded updates so local galleries with newer versions in favorites are not misclassified under `__not_fav__`.
- **Download ingest tuple tags** (`services/download_worker.py`): `ingest_downloaded_gallery` previously called `.items()` on `result.tags`, crashing with `AttributeError` when given the tuple-of-tuples tag format returned by `Downloader.execute`. Tag unpacking now supports `tuple`, `list`, and `dict` formats. Completed download tasks now also align `current_page = total_pages`.
- **Unit of Work transaction semantics** (`db/uow.py`): `async_sessionmaker` was mis-detected as an external session, so `get_uow` never committed. Factory vs session is now distinguished by `isinstance(AsyncSession)` + callable check with `_began` tracking, and `from_factory`/`from_session` are available.
- **Download progress + SQLite concurrency** (`services/download_worker.py`, `db/repository.py`): `task.id=None` no longer crashes `download_progress`/`is_download_cancelled`; `claim_pending`/`BackgroundJob.claim` fall back without `FOR UPDATE SKIP LOCKED` on SQLite and the download worker limits itself to 1 worker there.
- **App state double-write** (`app/main.py`, `app/state.py`): `app_state` is the single source of truth, `app.state` is mirrored; `_refresh_services` and `startup` now keep `library_service`/`tag_service`/`thumbnail_service` in sync.
- **Background task leaks** (`services/*_worker.py`): `asyncio.create_task(persist_history)` not tracked by `shutdown` — all fire-and-forget history persists now go through `spawn_task`.
- **Archive validation unified** (`scanners/archive.py`, `services/downloader.py`): Zip-Slip/symlink checks share `_is_symlink`/`_is_unsafe_path`/`validate_archive_member`; `CbrRarScanner` now checks symlinks on both `scan` and `open_page` with `is_relative_to`.
- **Observability double-count** (`observability.py`): drop unlabeled `gv_http_requests_total` bump and dedupe `HELP`/`TYPE` per base name.
- **Thumbnail meta mismatch** (`services/thumbnail_worker.py`): `_meta` now maps to `GalleryMeta` (`file_count`/`file_size`/`path`/`posted_at`/`storage_signature`).
- **Downloader cross-filesystem** (`services/downloader.py`): `temp.rename` → `shutil.move` + `to_thread`.
- **EhClient parity** (`services/eh_client.py`): `await response.aread()`, JSON-string cookies accepted, `fetch_gallery_cover` respects `image_semaphore` for `hath.network`/`ehgt.org`, `tag_sync_concurrency` clamped to 8 in the worker, `download_archive` 416 only succeeds when `offset==total` (oversized partials are cleared and retried).
- **Filtered delete guard** (`app/routers/galleries.py:738`): `POST /api/galleries/delete-filtered` caps the matched set at 5000 rows (409 when exceeded; refine filter or delete in batches) to prevent full-library wipe on empty filters; paging is 500-row batches.
- **Duplicate resolution no longer blocks the event loop** (`routers/duplicates.py:118`): `shutil.rmtree`/`unlink`/`is_dir` now run via `run_in_threadpool`.
- **Favorites cover is non-blocking** (`routers/favorites.py:598`): `is_file`/`write_bytes`/`replace` via `run_in_threadpool`, served as `FileResponse` with `Cache-Control: public, max-age=86400`.
- **Translation updater tracking** (`app/main.py:754`): `asyncio.create_task(_translation_update_loop())` now goes through `spawn_task` so `shutdown` waits for it.
- **Category backfill restored** (`services/tag_sync_worker.py:234`): `category_refresh_once` was a stub — restored full one-time 大分类 backfill (`pending_category_refresh_ids` → `TagSyncService.refresh_category`, `GalleryGoneError` → `mark_tag_not_visible`/`deleted`, `category_refreshed`/`category_refresh_running` status, 0.3s pacing).
- **Frontend filtered-delete tag mode** (`frontend assets/views/library.js:55`): default `tag_mode` corrected from `or` to `and` to match `renderLibrary`.
- **Frontend infinite scroll leak** (`frontend assets/utils.js:27`): `IntersectionObserver` now `disconnect()`s before `sentinel.remove()` on `finished`.
- **Frontend checkbox duplication** (`frontend assets/components.js:6`): `renderCardCheckboxes` now guards with `dataset.bound` to avoid stacking listeners.
- **Frontend archive dialog leak** (`frontend assets/components.js:99`): `keydown` listener is now removed in `close()` (not only on Escape).
- **Frontend API empty-body handling** (`frontend assets/core.js:55`): `204` or `content-length: 0` short-circuits; non-JSON error bodies fall back to `res.text()` so Chinese `detail` is not lost.
- **2026-08-31 fullstack review — P0 archive ordering** (`services/downloader.py:672`): `sorted(rglob, key=name)` mis-ordered non-zero-padded zips (`2.jpg` before `10.jpg`) and ignored subdirectories; now `natural_key(relative_path)` ensures page-accurate renaming.
- **P1 `esc()` single-quote** (`frontend assets/core.js:25`): missing `'` escape allowed `data-tag`/`data-gi` attribute breakout; now `&#39;` and `window.GV` namespace guards `esc`/`api`/`router` for future `type=module`.
- **P1 dual-state mirror** (`app/main.py:516,857,923`): extract `sync_state()` + `_create_services()` factory, `app_state` is canonical, `app.state` is legacy monkeypatch alias (tests still pass), `get_current_settings` prefers `app_state`, startup no longer double-writes per-service; `assert` guard added.
- **P1 long-gallery tail truncation** (`services/eh_client.py:750`): `gallery_pages+2` hard stop dropped; tail now walks until two consecutive empty pages (5000-offset hard cap) so stale `gdata` under-report no longer truncates 40+ pages.
- **P1 global pollution** (`frontend index.html:40`, `assets/app.js:30`): add `window.GV = {app, esc, api, router}` convergence and document script order; plan `type=module` for next iteration.
- **P2 origin_url** (`services/eh_client.py:1058`): `showpage` now `urljoin(response.url, html.unescape(...))` so protocol-relative `//exhentai.org/...` is not malformed.
- **P2 SSRF guard** (`services/eh_client.py:356`): `parse_gallery_url` rejects non-`exhentai.org`/`e-hentai.org` hosts (user pastes `https://evil.com/g/...`) before `gid/token` are used.
- **P2 download retry backoff** (`services/download_worker.py:368`): non-`challenge` `EhClientError` now always gets `retry_backoff()` (was `now` → instant re-queue by 60s sweep, burning retries); `claim_pending`/`sweep_auto_retry` alias added for SQLite `SKIP LOCKED` parity.
- **P2 Cookie Secure auto** (`app/routers/auth.py:62`, `app/main.py:1138`): `auth_cookie_secure` now auto-enables when `X-Forwarded-Proto: https` or `request.url.scheme == https`, so TLS deployments without `AUTH_COOKIE_SECURE=True` still get `Secure` cookies.
- **P2 CSRF Referer fallback** (`app/main.py:1160`): `/api/` writes now check `Origin` → `Referer` → `X-CSRF-Token` (with `X-Forwarded-Host` support); `Sec-Fetch-Site: cross-site` still 403; CSRF cookie (`galleryvault_csrf`) is set on GET (30-day `lax`, non-`httponly`) for future `X-CSRF-Token` validation.
- **P2 `Referer`/`X-CSRF-Token` for old browsers**: non-`Origin` POSTs that lack `Sec-Fetch-Site` no longer bypass; `/api/` mutation without `Origin`/`Referer` requires valid `X-CSRF-Token` if cookie is present.
- **P2 infinite scroll abort** (`frontend assets/utils.js:11`): `stopInfinite()` now aborts `AbortController` + removes sentinel; `startInfinite` stores `{observer, controller, sentinel}` and drops `fetchPage` results if route changed or container detached.
- **P2 browse error boundary** (`frontend assets/views/browse.js:26`): `Promise.all` split into separate `try` blocks so `browse-ns` tag cloud still renders when `galleryGrid` fails, and `galleryGrid` itself retries 422 with clamped `page_size`.
- **P2 keyboard** (`frontend assets/events.js:234`): arrow navigation now `closest('.gc')` so focus on `.gc-wrap`/`img` still works; `prefPageSize` clamps `1–500` (was unbounded → 422 on `?page_size=9999`); `reader.js` click now advances on `.reader` background and `toggleReaderFit` only toggles `reader-fit` class (no inline `style.width` leak).
- **P2 Telegram bot** (`app/main.py:884`): `_start_telegram_bot` now `_spawn(..., "telegram bot")` with `spawned_tasks` tracking + `CancelledError` swallow guard; `translation` load is `_spawn(asyncio.to_thread(...))` so `/healthz` is not blocked by `load_translations`.
- **P2 favorites poll interval** (`services/favorites_worker.py:444`): `favorites_poll_interval_seconds` (non-existent) → `favorites_poll_interval_minutes * 60`; `run_favorites_check` now tolerates test stubs missing `favorites_archive_*` via `getattr(..., default)` and uses `_main_settings()` to avoid `app_state` stub pollution.
- **P2 skeleton/cover UX** (`frontend assets/components.js:46`, `assets/utils.js:203`, `assets/views/library.js:32`, `assets/styles.css:74`): `library` initial uses `renderSkeleton(8)`; `galleryCard` no-cover uses `var(--panel-2)` placeholder with `t("noCover")` (added to `zh.js`/`en.js`); `library`/`history` fixed `renderError` double escaping; `input:focus` now shows `var(--focus-ring)` like `.btn`.
- **P2 encryption error message** (`app/routers/settings.py:144`): `ENCRYPTION_KEY not configured` → `encryption not enabled` (no deployment detail leak); `secrets.py` documents fixed `_SALT` as at-rest (not auth) and lack of rotation script.
- **2026-09-01 已删除误判三合一修复**（`services/eh_client.py:667`, `services/tag_sync_worker.py:234,383`, `services/updates_worker.py:24`, `services/favorites_worker.py:417`）：
  - **空体挑战误判为已删除**：`fetch_gallery_metadata` `/g/{gid}/{token}/` 收到空体/挑战页（`200 len 0` 或 `/?poni` 302 后小页）时曾直接 `GalleryGoneError` → `mark_tag_synced(category="deleted")` 批量污染；现补与 `fetch_gallery` 同款鉴别（`url.path` 校验 + `_is_auth_failure_page` + 空体 `EhClientError`），并在 `tag_sync` 两处 `GalleryGoneError` 前增加 `_confirm_gone` 经 `fetch_gmetadata` 的 `expunged` 双源确认（`false`/`None` 则重入队而非打 `deleted`）。
  - **已删除自愈**：新增 `GalleryRepository.repair_deleted_misclassified`（`db/repository.py:700`），对 `category=deleted` 且 `gallery_metadata.expunged=false` 或仍在 `favorite_items` 的记录清 `tags_synced_at/category_refreshed_at` 并回写真实分类（生产 40→7 真删，其余回队待重同步）。
  - **更新画廊漏扫**：`normalize_update_title` 补 `中国翻译/汉化/漢化/无修正/翻譯版` 等 9 个变体，去除全半角/标点更稳；`favorites_worker.run_favorites_check` 成功后自动 `spawn detect_gallery_updates`，避免新 `gid` 已入收藏但旧本地仍停在 `deleted`。
  - **更新画廊立即检测跨域误拒**（`backend 7d819bd` `frontend 83703bd`）：`app/main.py:1180` `Origin/Referer` vs `Host` 曾 `netloc`（含 `:8000`）比对，而 `nginx Host $host` 丢端口恒不等（`192.168.1.123` vs `192.168.1.123:8000`）→ `403 Cross-origin request rejected`；改为 `hostname` 比对 + `X-Forwarded-Host`，`frontend nginx.conf` 改 `$http_host`，`core.js` 对 `POST/PUT/DELETE/PATCH` 自动带 `X-CSRF-Token`。

### Changed

- **Proxy trust is now a whitelist** (`config.py` `trusted_proxies`, `auth.py`): `X-Forwarded-For`/`X-Real-IP` are only trusted when the peer is loopback or listed in `trusted_proxies` (CIDR or IP); private ranges are no longer implicitly trusted. `trusted_proxies` is now editable via `POST /api/settings` (and `tag_translation_update_interval_minutes` added to the allowed set).
- **Tag sync concurrency bounded** (`services/tag_sync_worker.py`): worker concurrency is clamped to 8 regardless of `tag_sync_concurrency` (settings still allow 1–32, but the worker never exhausts the httpx pool).
- **Input validation tightened**: login password truncated to 256 chars, `POST /api/galleries/{id}/progress` rejects `current_page < 0`, `POST /api/galleries/{id}/favorite` validates `favcat 0–9`.

### Security

- **Password hash downgrade blocked** (`auth.py`): `verify_password` now rejects `pbkdf2_sha256` with `<200k` iterations (was `<100k`).
- **At-rest encryption guard** (`app/main.py`, `routers/settings.py`): startup warns when `ENCRYPTION_KEY` is missing; `POST /api/settings` refuses to persist `exhentai_cookies` in plaintext (422) until the key is configured.

## [1.3.2] - 2026-08-31

### Fixed

- **Infinite retry loop on archive fallback**: When an archive zip failed validation (e.g., incorrect page count) or returned 404/410 (such as H@H rate limits "You have clocked too many downloaded bytes"), the fallback to page-by-page downloading wiped the temporary directory. If the page-by-page attempt subsequently failed, the next retry would wipe the progress and mistakenly retry the archive download from scratch. The fallback state is now persisted via a `.archive_fallback` marker, and the downloader directly falls back to page-by-page on `ArchiveExpiredError`, ensuring smooth resumes without endless cycles, GP bleeding, or stalls.

### Changed

- **ExHentai requests now send a full browser fingerprint** (backend `eh_client.py`): mirror Ehviewer_CN_SXJ's ChromeRequestBuilder — default client sends the browser `Accept` (`image/avif,image/webp,...`) and `Accept-Language` headers; `showpage`/`gdata` POSTs add `Origin` (+ `Referer` on showpage). ExHentai's anti-abuse fingerprints the whole header set, and the bare httpx defaults read as scripted traffic (reduces IP challenges like the 2026-08-31 outage).
- **Frontend Optimization (Phase 0-3) fully delivered and merged into `dev`**: modular architecture (monolithic app.js refactored into core/state/utils/components/events/views/locales), Design Tokens & `.btn` component system, mobile hamburger navigation, accessibility & keyboard shortcuts (`/` search focus, arrow card navigation), CSS content-visibility & IO virtual scroll, on-demand i18n locale loading, full 9-link navigation, full CI syntax-check, and Playwright smoke suite. See FRONTEND_OPTIMIZATION_PLAN.md.

### Added

- **Archive download falls back to page-by-page when unavailable** — when the
  ExHentai archive channel cannot serve a gallery (the selected quality tier
  does not exist, GP too low, archive corrupt), the download now automatically
  switches to the page-by-page channel (no GP cost, H@H carries the traffic)
  instead of failing the whole task. New setting `archive_fallback_pages`
  (default on) in the Settings page; turn it off to restore fail-immediately
  without burning automatic retries.

- **Delete failed gallery-update records** — the gallery-updates page gains a
  "delete selected" button on the failed filter, removing those records for
  good via `POST /api/updates/delete`. Only `failed`/`ignored`/`pending` rows
  are deletable (the repository guards against rows with a live download
  task), and deleting a download task on the tasks page still keeps its failed
  update record visible so it can be reviewed or removed here.

- **Original-quality upgrade from the gallery detail page** — the detail page
  now shows whether the local copy is original (原图) or resampled (重采样)
  next to its favorite categories, and offers two upgrade actions when the
  gallery is not already original: **下载原图** (page-by-page, no GP) and
  **归档形式下载原图** (ExHentai archive channel, cost/balance preview locked to
  the original tier). When an original download finishes, the superseded
  resampled copy is removed automatically (page-count guarded, best-effort).
  Quality is recorded at download time and inferred for existing galleries by
  comparing the local storage size against the ExHentai original size —
  backfilled during the favorites metadata sync and at the end of a library
  scan for galleries no favorite folder covers.

### Fixed

- **Gallery delete now removes files even for (former) library roots** — the
  `delete_files` path no longer gated on `_in_scan_roots`; any gallery's
  `storage_path` is now attempted for deletion (rmtree / unlink) when
  requested. This makes it possible to clean disk copies after removing a
  library root from Settings (previously only the DB row was removed).

- **Duplicate-copy snapshots dropped the Japanese title** — copies already
  ingested that were folded into a duplicate group by signature (content
  unchanged, so the scan skips them) never carried `title_jpn`: `ExistingGallery`
  had no such field and `existing_rows` did not select `Gallery.title_jpn`. Under
  the Japanese display preference the cleanup page then fell back to the romaji
  title even though the on-disk folder was named with the Japanese title. The
  field is now carried through, so re-running a library scan restores the
  Japanese titles on the duplicate-copy page.

- **In-place original upgrade left the old resampled pages behind** — when an
  original-quality download merged into the folder of an existing resampled
  copy whose pages used a different file extension (e.g. old `.webp` next to
  the new `.jpg`/`.png`), both files survived for the same page, doubling the
  gallery's `page_count`/`storage_size` in the database. The stale per-page
  copy is now pruned before ingest, keeping exactly the new original pages.

- **"Archive-download original" on the gallery detail page reported no
  archives available** — the dialog passed the local library id to
  `/api/archives/preview`, which expects ExHentai gids, so the preview came
  back empty even for galleries with an original tier. The dialog now previews
  with the gallery's gid while the enqueue still uses the local id.

- **The gallery-updates page "select all" checkbox was pushed to the far right
  of the toolbar** — `.toolbar input { min-width: 180px }` also stretched the
  checkbox (a toolbar `<input type="checkbox">`). A CSS exception restores the
  natural checkbox width.

- **Deleting a download task could leave its gallery-update entry stuck
  "downloading" forever** — removing a task from the downloads page deleted the
  `download_tasks` row while the `gallery_updates` row it was pinned to stayed
  in `downloading` (the update finalizer looks the task up by id and found
  nothing, so it silently skipped it). The updates page then showed stale
  in-progress entries that could never be retried. Deleting a download task now
  marks any gallery-update row pinned to it as `failed` ("download task
  removed"), and the finalizer marks orphaned updates `failed` as a fallback,
  so the entry stays actionable (retry / ignore).

## [1.3.1] - 2026-08-30

### Added

- **ExHentai archive (zip) downloads** — a new download channel that uses GP
  instead of H@H page fetches for large galleries, with a per-task quality
  tier. Three entries share one executor (favorites download area / updates
  area / scheduled scan): `POST /api/archives/preview` shows funds + per-gallery
  original/resample cost & size (read-only, never charges GP), the favorites
  and updates toolbars gained "download original" and "archive download"
  buttons, and the scheduled scan can archive galleries over a page threshold.
  The zip streams on a single connection with Range resume; the requested
  quality + zip URL are persisted so a retry resumes without re-charging GP;
  insufficient GP fails the task immediately. Archive output reuses the standard
  metadata + notification + ingest + update-finalize pipeline. New settings:
  `archive_quality`, `favorites_archive_enabled`, `favorites_archive_max_pages`.
- **Per-task quality override (`download_tasks.quality`)** — the "download
  selected original" / "update selected original" buttons force original-quality
  page-by-page downloads regardless of the global `download_quality` setting;
  `POST /api/downloads` and the download queue accept an optional `quality`.
- **Download tasks page distinguishes archive vs page-by-page** — `GET
  /api/downloads` now returns each task's `mode` and `quality`; the tasks page
  badges archive downloads ("Archive · Original/Resample") and marks plain
  H@H page-by-page downloads with a "Page-by-page" badge (zh/en).

### Fixed

- **Archive (zip) downloads showed no speed / ETA in the tasks UI** — the
  archive download path only forwarded page progress to the DB and never fed
  the downloader's live byte stats (`_record_bytes`), so `/api/downloads`
  returned no `speed_stats` for archive tasks and the tasks page rendered them
  without a speed or ETA (unlike page-by-page downloads). The zip-stream
  callback now records byte/progress deltas the same way the page-by-page
  path does.
- **Slow backend startup from a recursive cache chown** — `entrypoint.sh`
  walked the whole thumbnail cache (`chown -R` over 14 GB / hundreds of
  thousands of files, ~4s) on every container boot even though runtime writes
  already come from the `app` user. The recursive repair now runs once,
  tracked by a `.gv-ownership` marker in the cache volume, and is skipped on
  later boots (a reset/emptied cache has no marker, so it re-runs). Backend
  start-to-healthy drops from ~11s to ~7s.
- **Archive cost-preview showed a bogus "available GP" balance** — archiver.php
  no longer renders a `You have X GP` balance row (ExHentai layout change), so
  the fallback regex grabbed the original tier's `Download Cost` (e.g. 59,782
  GP) and reported it as the account balance. `funds` is now parsed only from
  an explicit balance row, and the real balance is read from the GP exchange
  page (`exchange.php?t=gp`, `Available: N kGP`); the archive-download dialog
  and the downloader's funds gate both use that value.
- **Archive cost-preview showed N/A tiers as "0 GP · 0 B"** — an unavailable
  tier (archiver.php `N/A`) reported cost/size 0 with `*_available` false, so
  the dialog rendered a misleading zero-cost entry flagged "insufficient GP".
  `/api/archives/preview` now returns `null` cost/size for unavailable tiers
  and the dialog renders a muted `N/A`; a genuine GP shortage still shows the
  real cost/size with the warning.
- **Archive cost-preview crashed on unavailable tiers (500)** — when a gallery's
  archiver page shows `Estimated Size: N/A` for a tier (e.g. a gallery that does
  not qualify for a resample archive), `_parse_archive_size` crashed with an
  `AttributeError`, turning the archive-download preview into `Internal Server
  Error`. The parser now yields 0 for unparseable sizes, `N/A` tiers have their
  download URL cleared (so they are never charged or downloaded), and the
  preview's `original_available` / `resample_available` checks require a real
  download URL in addition to sufficient GP.
- **Archive cost-preview dialog was transparent** — `.gv-modal` set
  `background: var(--panel-1)`, a CSS variable that is never defined, so the
  declaration was invalid and the modal body rendered transparent over the 55%
  black overlay (text hard to read). Now uses the defined `--panel` color.
- **Page-size selector showed the wrong value** — `prefPageSize()` defaults to
  24 but the `PAGE_SIZES` dropdown only offers `[5,30,50,100,200,500]`, so the
  select had no matching option and rendered "5" while the list actually showed
  24 (or any other out-of-list) items. `pageSizeSelect` now appends the current
  value as an option so the label always matches reality.
- **Chinese UI: archive/original buttons fell back to English** — the favorites
  ("download selected original" / "archive download selected") and updates
  ("update selected original" / "archive update selected") toolbar buttons were
  missing their `zh` i18n keys, so `t()` fell back to English on the Chinese UI.
  Added the four keys (`favDlOrig`, `favDlArchive`, `updOrig`, `updArchive`).
- **CI `pages` deploy on dev** — the `deploy` job now runs only on `main`;
  dev pushes still run `build` as a preview but no longer attempt to deploy,
  which the `github-pages` environment protection rules rejected with
  "Branch dev is not allowed to deploy to github-pages".
- **Duplicate-copies page tags lost their Chinese translation** — the
  `/api/scan/duplicates` response returned each copy's tags as plain
  `{namespace, name}` without the translated `display` field (every other page
  fills it server-side via `translated_tag`), so `tagText()` on the Chinese UI
  fell back to the untranslated English tag name. The cleanup page now fills
  `display` like the gallery/favorites endpoints; existing duplicate records
  are translated on the fly, no rescan needed.
- **Ignored favorites-duplicates list tags had no translation** — the
  `#/favorites/manage` ignored-duplicates list returned tags as plain
  `{namespace, name}` for both local and cloud items, so the Chinese UI showed
  English tag names. `/api/favorites/duplicates/ignored` now fills `display`
  the same way as the duplicate-scan results.

### Changed

- **Docs (Deployment, zh/en)**: mounting multiple existing gallery folders, and
  the note that `LIBRARY_ROOTS` / `DOWNLOAD_ROOT` compose env vars are only
  startup defaults overridden by the DB-backed Settings page (production
  compose dropped the now-unused `LIBRARY_ROOTS` var).

## [1.3.0] - 2026-08-30

### Added

- **GitHub Pages docs site (`docs-site/`)** — a VitePress site renders the
  canonical `docs/wiki/` pages into a website with a sidebar table of contents
  (中文 + English nav), deployed automatically by the `pages` workflow to
  https://hugo.lwnlh.com/galleryvault/. Canonical sources stay in
  `docs/wiki/`; the site is generated per build.
- **Canonical wiki source (`docs/wiki/`)** — the GitHub wiki pages now have a
  canonical, versioned copy in this repo (`docs/wiki/`). `scripts/sync-wiki.sh`
  and the new `sync-wiki` workflow mirror it to the wiki repository;
  `API.md` / `Development.md` / `openapi.json` remain owned by the `sync-docs`
  workflow.
- **Download-title setting (`download_title`)** — chooses which title seeds
  the on-disk download folder name (`<gid>-<title>`): `japanese` (default,
  Ehviewer-style) or `english`. Independent of the display `title_display`
  setting; a changed setting only affects newly downloaded folders.
- **Download folder reuse** — re-running a download now reuses the existing
  `<gid>-…` folder instead of deleting it and starting over, so a changed
  title no longer leaves a second orphaned copy on disk.
- **Long CJK titles can no longer overflow the filesystem limit** — download
  folder names are truncated to 255 UTF-8 bytes at a character boundary
  (previously 180 characters, which could exceed 255 bytes for Japanese text).
- **"Not in favorites" library filter** — the library page's category dropdown
  now offers "Not in favorites", showing local galleries whose gid is not in any
  ExHentai favorite folder (gid-less local archives count as not favorited).
  Pseudo-category `category=__not_fav__`; also honored by the filtered delete.
- **Gallery updates (`#/updates`)** — detects local galleries that ExHentai
  re-uploaded under a new gid (the favorites entry follows the new version, the
  old local copy stays behind). A local gallery whose gid is not favorited but
  whose normalized title matches a favorite item is listed with a check-box
  row showing `old gid → new gid`; selecting rows and hitting "Update selected"
  downloads the new version first, then removes the old local copy. Runs
  automatically after every favorites check and can be triggered manually.
  False positives can be ignored (like the duplicate-copy scan).

### Changed

- **Docs: Telegram `/pause` clarified.** The bot's `/pause` only gates new URL
  intake (URLs pasted while paused are ignored); already-queued and in-flight
  downloads are unaffected. The pause flag is not persisted (auto-resets on
  backend restart). Wiki `Usage` / `Usage-EN` updated accordingly.
- **Reader page images are cached by the browser for an hour.** The page-image
  endpoint (`/api/galleries/{id}/pages/{n}`) used to stream every image fresh
  on each request; it now sends `Cache-Control: public, max-age=3600` so back
  navigation and re-reads reuse the browser cache (thumbnails already had 24 h
  caching). Safe because galleries are read-only and page bytes never change.
- **Multi-word search matches each word independently.** A query such as
  `mimu gif` used to become a single contiguous `%mimu gif%` pattern, so a
  gallery whose title contains both words separately (or in the other order)
  was missed. Free-form text is now split on whitespace and every word must
  appear in the title (each as its own substring, anywhere); single-token and
  CJK-sentence searches behave as before.
- **Gallery detail opens at your reading position.** Without an explicit
  `?page=`, the page thumbnails now start on the pager page containing your
  last reading progress (instead of always page 1), so returning from the
  reader lands on the page you were viewing. An explicit `?page=` is still
  honored; the detail thumbnails keep their default of 30 per page.
- **Search no longer guesses tags from free-form text.** Typing an unrelated
  word used to be auto-promoted into a tag filter when it happened to match a
  local tag name (English) or a tag translation (Chinese), which could drop
  galleries whose titles contain the word but lack the tag. Free-form tokens
  now search titles only; a tag filter is applied only for explicit
  `ns:name` syntax, the tag cloud, or clicking a tag suggestion in the search
  box (which consumes the clicked word from the query).
- **Page size is remembered.** The "per page" selector now persists your
  choice in the browser and carries `page_size` through the gallery → reader
  → gallery round trip, instead of resetting to the default when you come
  back from reading.
- **Reader fullscreen is now image-only.** The fullscreen button (and the `F`
  key) now fullscreens the page image instead of the whole page: the image
  fills the screen (`object-fit: contain`, black background) and the toolbar
  and page navigation are hidden. While fullscreen, paging via `→`/`←`/space
  or clicking the image swaps the image in place instead of re-rendering the
  page (which would drop fullscreen); on the last/first page the reader exits
  fullscreen first. Pressing `Esc` restores the previous fit state and syncs
  the URL to the current page.
- **ExHentai login test now really verifies the session** — `POST
  /api/settings/exhentai/test` answers with meaningful HTTP status codes (200
  logged in, 400 no cookies configured, 401 cookie expired/invalid, 403 no
  exhentai access, 502 upstream failure) and classifies the home page by its
  login markers instead of treating any HTTP 200 as success. A transient
  anti-bot challenge is retried once before reporting a failure.

### Fixed

- **Equal-count favorite replacements are now detected.** The scheduled
  favorites poll skipped the full re-list whenever the cloud count matched the
  locally known gid count, so removing one favorite and adding another (count
  unchanged) was never caught. Consecutive skips are now counted per folder:
  the poll that would be the 5th consecutive skip forces a full re-list and
  resets the counter.
- **The Favorites page never blocks on a cold favorite-count fetch.** The
  first `_favorite_counts_cached()` call used to await ExHentai synchronously
  (up to 10s). The cache is now warmed asynchronously at startup and the first
  request returns immediately, with the real counts arriving via the
  background refresh.
- **A manual download retry resets the retry budget.** `max_retries` is
  restored to 10 on `POST /api/downloads/{id}/retry`, so a task that exhausted
  its automatic budget (`max_retries=0`) can be re-queued instead of staying
  stuck forever.
- **`check_login` no longer misreports an anti-bot challenge as a dead
  session.** ExHentai answers an empty body (no cookies / anti-bot challenge)
  with HTTP 200; `parse_login_state` previously classified it `not_logged_in`,
  prompting a pointless cookie reset. It now returns `failed` so the settings
  test shows "请求失败或反爬挑战" and the operator retries instead of
  re-entering cookies.
- **Telegram bot `/status` is no longer swallowed by the chat allowlist.** The
  real `TelegramNotifier` drops non-forced messages to chats that are not in
  `telegram_chat_ids`; `/pause`, `/resume` and gallery enqueue already passed
  `force=True` but `/status` did not, so an operator whose chat was only in
  `telegram_allowed_user_ids` got no reply. `/status` now forces its reply too.
- **Cloud favorite-removal failures now surface on the Logs page.** Previously
  `remove_favorites` sent every gid in one POST and raised on any non-2xx, so a
  partial failure left no trace of which gids failed. It now chunks requests
  (25/batch, ExHentai's cap), degrades a failed batch to per-gid retries, and
  returns the list of gids that could not be removed; the API response gains a
  `cloud_failed` field and the Logs entry appends `cloud remove failed N:
  gid1,…` with a `failed` status when any gid (cloud or local) fails.
- **Login rate limiting no longer trusts the socket peer, which a client could
  rewrite via `X-Forwarded-For` to rotate buckets and bypass the limit.** The
  bucket now keys on the `X-Real-IP` header — nginx unconditionally overwrites
  it with `$remote_addr`, so it cannot be spoofed through the proxy — and falls
  back to the socket peer only for direct (header-less) access.
  `forwarded-allow-ips` is narrowed to the private docker range
  (`172.16.0.0/12,127.0.0.1`) so only the proxy can rewrite forwarded headers.
- **Empty cached tags no longer wipe a gallery's local tags.** When the gdata
  metadata cache for a gallery had an empty `tags` list (stale or partial
  response), `apply_metadata_to_galleries` still ran the `delete(GalleryTag)`
  for every gallery in the batch, destroying tags that were already synced
  locally. The delete is now gated per-gallery on the cache actually carrying
  tags; galleries with empty cached tags keep their local tags while the rest
  of their metadata is still updated.
- **A cancel landing just as a download finished no longer races the success
  commit.** The cancel route flips the DB row to `cancelled` and arms the
  in-flight flag; if that landed between the last progress callback and the
  final commit, the old success branch either marked the task `success` or
  left a `success` attempt + an "ok" notification behind. The success branch
  now re-checks the row status and the flag inside its transaction and walks
  the shared cancel-cleanup path (temp dir, flag, no "ok" notification); the
  success path always consumes the in-flight flag so a late cancel can never
  leak into a later retry.
- **Galleries over ~10240 pages are no longer truncated.** The page-link
  enumeration fetched the first 512 gallery sub-pages concurrently, then
  walked a serial tail `range(start, 512)` — which was empty once `start`
  reached 512, so any gallery whose gdata `file_count` implied more than 512
  sub-pages silently dropped everything past that point. The serial tail now
  walks page-by-page until the first empty page (with a safety sentinel past
  the estimated page count).
- **Looking up a gallery by id/gid no longer 500s when the two collide.** A
  gallery is addressable by both its DB `id` and its ExHentai `gid`. When one
  gallery's `id` numerically equalled another gallery's `gid`, the old
  `OR`-combined `scalar_one_or_none()` lookup raised `MultipleResultsFound`
  (HTTP 500). The identifier lookups (`_gallery`, `get_by_identifier`,
  `get_for_tag_sync`) now query the primary key first and fall back to `gid`
  only on a miss.
- **Deleting a filter's results no longer breaks on huge libraries.** The
  library's "delete filtered" action used to resolve the whole filter into an
  id list on the client and POST it to `delete-bulk`, which could exceed
  asyncpg's ~32767 parameter limit when thousands of galleries matched. There
  is now a server-side `POST /api/galleries/delete-filtered` endpoint that
  pages the filter itself and deletes in 500-row batches; `delete-bulk` and
  the favorites-remove lookups also chunk their `in_` queries the same way.
- **ExHentai login test no longer false-negatives on a valid session** — the
  probe now requests the member-only `/uconfig.php` page and classifies the
  response body, because ExHentai answers every session state with HTTP 200
  and the public home page carries no login markers: a full page means logged
  in, ExHentai's own `expired login session` body (or an empty anti-bot
  response) means not logged in. A valid session is no longer reported as
  "cookie invalid or expired" while downloads with the same cookies succeed.
- **Manual retry now starts immediately** — retrying a failed/cancelled
  download clears the stale exponential-backoff timestamp, so the task is
  claimed right away instead of waiting out the previous backoff delay.
- **Deleting an in-flight download is safe** — deleting a downloading task now
  signals the running worker before removing its partial folder, instead of
  racing its writes (which could fail page writes and leave error noise).

## [1.2.15] - 2026-08-29

### Added

- **`title_display` now applies everywhere**. Cloud-only favorite items,
  favorites-duplicate groups and the duplicate-copies page used to always show
  the English/raw title; they now resolve the display title from the same
  `title_display` preference (Japanese / English / directory) as the library,
  gallery detail and local favorites. Duplicate-copy records carry the
  Japanese title too, so the page falls back to it after a re-scan.

### Fixed

- **Custom ExHentai base URL input was hidden by CSP**. The Settings / welcome
  "Custom" base-URL choice toggled a URL input via an inline `onchange`
  handler, which the nginx `Content-Security-Policy` (`script-src 'self'`)
  blocked — selecting Custom never revealed the input. The toggle now runs
  through the existing global change delegation, so proxy subdomains (e.g.
  `https://proxy.exhentai.org`) can be entered again.
- **Reader pagination keeps the library search filter**. Thumbnail links,
  prev/next buttons, keyboard/click paging and the next-gallery jump in the
  reader dropped the `q`/`tags`/`tag_mode`/`category` query string, so
  returning to the library after reading lost the active tag filter. All
  reader navigation hashes now carry the search context like the Read button
  already did.

## [1.2.14] - 2026-08-29

### Added

- **Open the original gallery on ExHentai**. The gallery detail page has an
  "Open on ExHentai" button that deep-links to `{base_url}/g/{gid}/{token}/`
  (built from the configured `exhentai_base_url`; hidden for local galleries
  without a token). The Settings/welcome forms now offer the base URL as a
  selector — ExHentai (里站) / E-Hentai (外站) / Custom with a fallback input
  for proxy subdomains — while saving the same `exhentai_base_url` field.
- **Smart search box: mixed tag + text queries**. The library search box now
  accepts free-form combos like `动图 中国` and splits them automatically:
  explicit `ns:name` tokens, Chinese words that map one-to-one onto a tag
  translation (e.g. `动图` → `misc:animated`), and English words that are exact
  tag names all become tag filters (AND), while the rest stays a title keyword.
  The API normalizes the query and the UI adopts the canonical `q`+`tags` form.
- **Multi-tag library search**. The library now supports filtering by several
  tags at once (all must match, `tag_mode=and`). Tag suggestions, tags on the
  gallery detail page and tags in the tag cloud all **append** to the active
  filter instead of replacing it; each active tag shows as a removable pill
  above the grid (per-pill × and a clear-all action). Resubmitting the title
  search keeps the current tag filter. The backend `/api/galleries` endpoint
  already accepted comma-separated `tags` — this change surfaces it in the UI.
- **Background work survives restarts**. Thumbnail generation and tag sync now
  run off a persistent job queue in the database instead of in-memory lists, so
  a container restart continues the remaining work instead of starting over.
  Download progress is persisted in batches too (at most every 20 pages / 5 s)
  instead of once per image, cutting database writes on long galleries by an
  order of magnitude — the Downloads page still shows live progress.
- **Downloads: pages-in-parallel is now a tunable setting**. `page_concurrency`
  (default 4, range 1–16) replaces the hardcoded 8. H@H nodes cap concurrent
  connections per source IP (~4–6), so a high value tripped the cap on lossy
  proxy paths and flooded logs with `ConnectError`; lowering it keeps downloads
  stable on any line. Exposed in the Settings page under Downloads.
- **Downloads: self-healing retries**. Failed tasks now re-enter the queue
  automatically with an exponential backoff (30s → 2m → 8m → 30m → 1h → …
  up to 6h) instead of dying after three attempts; the retry cap is raised to
  `max_retries` = 10 and only the missing pages are re-fetched. A periodic
  sweep re-activates older `failed` tasks that still have retry budget left,
  so the manual retry button is rarely needed. The per-task `retry_count`
  resets once a download succeeds.
- **Downloads: lazy per-page URL resolution**. Image URLs are no longer
  pre-fetched for the whole gallery in one go — every page resolves its own
  fresh keystamp URL right before downloading, and a `403` from an expired
  keystamp (H@H rejects stale signatures) is healed by re-resolving the page
  in place (up to 5 rounds, mirroring Ehviewer_CN_SXJ). Long galleries now
  download continuously instead of failing every 15–20 minutes when the
  batch of pre-signed URLs expired. Persistent failures still escalate to
  the task-level retry so galleries stay complete.

### Changed

- **Telegram bot now uses 30s long polling (was 1s short polling)** and the
  notifier client timeout is raised to 45s to match. `getUpdates` was hammering
  `api.telegram.org` about once per second, flooding logs with one line per
  poll (≈9k lines/6h in production); long polling cuts that to 1 request/30s
  and is gentler on Telegram's API.
- **httpx access logs are filtered down to failures only**. httpx logged one
  INFO line per HTTP request, so successful ExHentai page/`api.php` fetches,
  H@H image downloads and Telegram calls (all `2xx`) flooded stdout — ~96% of
  production log volume. A new `_HttpAccessFilter` in `logging.py` drops
  `2xx`/`3xx` httpx request logs while keeping `4xx`/`5xx` (e.g. H@H `403`
  keystamp misses) and all business WARNING/ERROR lines.
- **`/healthz` heartbeat access logs are silenced**. The docker healthcheck
  polls `/healthz` every ~10s, so uvicorn emitted one line per poll (~8.6k
  lines/day). The filter now drops those while keeping all other uvicorn
  access logs (real API traffic). The filter is attached both to the root
  handler (covers httpx/`galleryvault.*` loggers) **and** to the
  `uvicorn.access` logger itself, because uvicorn installs its own handler
  there with `propagate=False` — access-log records otherwise never reach the
  root handler's filter.
- **Slow-H@H-node watchdog defaults relaxed further** (`image_min_speed_kb_s`
  20 → 10) and the image transfer **read timeout is now 30s (was 15s) with a
  120s total budget**, so large GIFs / animated images survive a slow or
  hiccuping H@H node instead of aborting the whole gallery.

### Fixed

- **Public E-Hentai no longer misclassifies ExHentai-only galleries as
  deleted**. A gallery that only ExHentai exposes returns the same 404/empty
  page on e-hentai.org as a deleted one, which the tag-sync worker used to
  treat as a deletion — reclassifying the gallery as `deleted` and never
  retrying. On the public mirror the worker now suspends such galleries
  instead (category untouched) and switching the base URL back to
  `exhentai.org` in Settings resumes them automatically.
- **Returning from a searched gallery keeps the library filter**. Opening a
  gallery from the library grid carried no query, so the back-to-library link
  dumped you on the unfiltered library. Cover links now pass the active
  `q`/`tags`/`tag_mode`/`category` along, and the back link, Read button,
  thumbnail pager and the reader's back/all-pages links all preserve it.
- **Browse/library search buttons now say "Search"**. They used the library
  page label ("Library" / 画廊库), which read as a navigation button instead of
  the action it performs. The page heading and back-links keep the library
  label.
- **Downloads: `showpage` network errors are now wrapped as retryable
  failures**. A raw `httpx.ConnectTimeout`/`ReadTimeout` from the page-URL
  resolution API used to leak to the download worker as a cryptic
  `ConnectTimeout:` error and — worse — bypassed the 30s challenge backoff, so
  the retries fired back-to-back. Transport errors now surface as
  `EhClientError` (retryable with backoff) and reuse the existing HTML fallback.
- **Log context fields (e.g. `[error='ReadTimeout']`) now actually appear**. The
  `log_extra` helper built a nested `{"extra": {...}}` dict, which set
  `record.extra` instead of `record.context`; the log formatter never read it,
  so every structured field (`error`, `gid`, `page`, …) was silently dropped
  from all log lines. Fixed so failure diagnosis via `docker logs` works.
- **Settings: the "require login" (`auth_required`) toggle can now be saved**.
  `SettingsRequest` never declared the field, so pydantic silently dropped the
  submitted value and the Settings-page checkbox was dead UI since v1.0.0
  (defaults kept login always on, so it went unnoticed). The toggle now
  persists to `user_settings` and takes effect immediately.
- **Frontend proxy: the backend is now resolved over IPv4 only**. The compose
  network can carry IPv6 while the backend listens on IPv4 only (uvicorn
  `--host 0.0.0.0`); the nginx `proxy_pass http://backend:8001` resolved the
  service name once at startup and tried the container's IPv6 address first,
  failing until nginx fell back to IPv4. After every container upgrade/restart
  this produced a burst of `connect() failed` in the nginx logs and intermittent
  502s on the login page — which the SPA reported as "wrong password" even for
  a correct one, because `doLogin` never checks the `/login` response status
  (a failed POST means no session cookie, so the follow-up session check
  returns 401 and the UI shows the "wrong password" toast). The proxy now
  re-resolves the backend per request through Docker's DNS with
  `resolver 127.0.0.11 ipv6=off valid=5s` plus a variable `proxy_pass`, so it
  always uses the reachable IPv4 address.

## [1.2.13] - 2026-08-28

### Added

- **Slow H@H node watchdogs for image downloads**. New settings
  `image_download_timeout_seconds` (default 120), `image_slow_warmup_seconds`
  (default 10) and `image_min_speed_kb_s` (default 50). A single image is
  aborted once it exceeds the total wall-clock budget, or once it averages below
  the minimum throughput after the warm-up window — so a node that trickles a
  few KB/s no longer holds a download worker (and the whole gallery) hostage for
  many minutes. Aborted pages are retried through the existing per-page retry
  plus the persistent worker's 30s backoff, re-downloading only the failed page.
  ExHentai's `509.gif` rate-limit placeholder is now also detected by URL and
  treated as a retryable failure instead of being saved as a page.

### Fixed

- **Reader downloads large pages (e.g. animated WebP) up to ~500× faster**. Page
  images were streamed to the browser in the file's default 8KB buffer chunks,
  and each chunk crosses a threadpool boundary inside the streaming response —
  capping throughput near ~1MB/s. Pages are now read in 256KB chunks, removing
  the per-chunk overhead (measured ~466MB/s vs ~918KB/s on the same file).
  Small images are unaffected.

## [1.2.12] - 2026-08-28

### Changed

- **Telegram notifications are now language-selectable and consistently
  formatted**. A new `telegram_notify_lang` setting (中文 / English, default
  `zh`) drives the language of *all* automatic notifications — download
  success/failure/digest, library scan summary and failure, favorites folder
  checks, Telegram bot replies and the test message — instead of the previous
  mixed Chinese/English copy. Messages are sent with Telegram HTML formatting
  (bold titles, `<code>` gids, uniform emoji prefixes); gallery titles stay
  untranslated. The download digest keeps its 4096-character budget, now
  measured against the rendered text length.

## [1.2.11] - 2026-08-28

### Added

- **JHenTai download directories are scanned natively**: a new
  `JhentaiDirScanner` (storage type `jhentai_dir`) recognizes
  `jiangtian616/JHenTai` download folders — `<gid> - <title>/` with a `metadata`
  JSON — and restores the full gallery identity from it: gid, token, title,
  category, uploader, published time and tags. It is registered ahead of the
  bare-image-folder scanner so the richer metadata wins. Without the metadata
  the same folders already matched the bare scanner (gid inferred from the
  directory name only). **This support is new and not yet validated against
  much real-world data**.

### Docs

- **Favorites modes documented**: the docs (wiki Usage CN/EN, backend
  `docs/USAGE.md`, `docs/API.md`) now explain the difference between
  *incremental* / *watch only* / *force* folder modes, and how to pull down the
  backlog of an already-checked folder (incremental only follows new additions,
  so existing favorites need a one-time **force** check or **Download
  selected**).
- **Recommended workflow added**: README (CN/EN) quick start and wiki Home
  (CN/EN) now show the end-to-end flow — log in to ExHentai → read favorites
  in *watch only* mode (no downloads yet) → scan library → **deduplicate
  before downloading** → start with a *force* check to pull the backlog →
  switch to *incremental* + schedule.
- **Scope declared**: README (CN/EN) and wiki Home (CN/EN) now state the
  project's primary target — galleries downloaded by **Ehviewer_CN_SXJ** with
  a `.ehviewer` (SpiderInfo) metadata file — and list compatible EhViewer-family
  clients (FooIbar/EhViewer, Ehviewer-Overhauled, EhViewer-Apple,
  Ehviewer_OHOS, LRReader, …) plus the reduced-fidelity support for bare image
  folders and CBZ/CBR.

### Fixed

- **Library "Scan library" button works again**: the button on the Library page
  (and the "Scan again" button on the *Duplicate copies* page) silently did
  nothing — the `scanLibrary()` handler they call was removed during the Logs
  page refactor and never restored. Re-added the handler (it triggers
  `POST /api/scan`, shows a toast and refreshes the task logs); the first-run
  welcome wizard's scan button now shares the same code path.
- **Full scan crashed on batches of only gid-less galleries**: the ingest
  lookup built its WHERE clause as `False | column.in_(…)` when a batch had no
  galleries carrying an ExHentai gid (e.g. calibre CBZ exports), which raises
  `TypeError` and failed the whole batch. The condition is now assembled
  explicitly, so gid-less copies ingest correctly.
- **Password change did not actually revoke old sessions**: `change_password`
  rotated `auth_secret` in the database but never applied it to the running
  process (only the password hash was re-synced), so previously issued session
  cookies stayed valid until the next container restart. The new secret is now
  applied immediately and the current user receives a fresh session cookie, so
  their own change does not log them out while all other sessions die at once.
- **"Keep / Keep & delete" on the *Duplicate copies* page failed for paths
  containing an apostrophe**: the copy path was inserted into `data-path` via
  `encodeURIComponent`, which does not escape single quotes, truncating the
  attribute and making the buttons silently no-op. The raw path is now HTML-
  escaped and sent unencoded in the resolve request.
- **A download deleted mid-flight misreported as failed**: if the task row was
  removed while pages were downloading, the completion handler dereferenced
  `None` and logged the download as failed, skipping ingest and the Telegram
  notification even though the gallery was fully written to disk. It now skips
  the (now-orphaned) DB write but still ingests the completed gallery.

### Changed

- **Gallery detail page defaults to 30 thumbnails per page**: the page-size
  default on the gallery detail page is now 30 (was 24) and the per-page
  selector's `24` option became `30` (`PAGE_SIZES` = 5/30/50/100/200/500).
- **Favorites-check Telegram messages show the folder name**: notifications for
  a favorites check (summary, check-failed, per-gallery download-failed) now
  read `Favorites category 3 (folder name): …` when the folder has a name,
  falling back to the bare number otherwise.
- **"Unfavorite and delete downloaded" deletes every copy and reports failures**:
  the favorites dedup action now removes **all** physical copies of a gid across
  the scan roots (including duplicate-copy losers in `duplicate_records`), not
  just the DB row's own path. A gallery row is only deleted when every copy was
  removed successfully — a copy that cannot be deleted (e.g. a read-only mount,
  or an archive file) keeps the row so the next scan cannot resurrect the gallery
  as if it were fresh. Failed paths are reported in the toast **and** recorded on
  the Logs page (new `favorites-remove` / `gallery-delete` activity entries).
  Gallery-page delete and bulk delete share the same code path and now also
  delete single-file (CBZ/CBR) archives, which the previous directory-only
  removal never touched.
- **Library roots are no longer labeled "read-only"**: the Settings label and
  hint were updated, since deletion now removes files under a library root when
  the mount is writable (a read-only mount reports the failure instead of
  silently succeeding). New downloads still never land in library roots.

## [1.2.10] - 2026-08-27

### Added

- **Scan completion Telegram notification reports duplicate copies**: the
  message now appends `N duplicate-copy group(s) found (gid …)` when a scan
  detects the same gallery under more than one scan root, pointing the operator
  at the *Duplicate copies* page. `GET /api/scan` exposes `duplicate_gids`.

### Fixed

- **Scan counters no longer double-count skipped galleries**: a full scan of an
  unchanged library reported `skipped ≈ 2 × galleries` because already-ingested
  single copies were counted in both scan phases. They are now counted once.

## [1.2.9] - 2026-08-27

### Added

- **Duplicate-copy resolution on library scans**: when the same gallery (same
  gid) exists under more than one scan root (an EhViewer download directory, a
  CBZ archive, a manual copy), the scan now collects every copy, picks a winner
  per the new `duplicate_policy` setting and records the rest for review.
  Previously the DB row was silently re-pointed at whichever copy happened to be
  scanned last.
  - `duplicate_policy` (Settings): `keep_first` (default — the already-stored
    copy wins), `prefer_more_pages`, `prefer_newer`, `prefer_larger`,
    `prefer_smaller`, or `manual` (never auto-resolve).
  - New **Duplicate copies** page (`#/duplicates`): lists every physical copy of
    a duplicated gid with cover thumbnail, tags, page count, size and posted
    date, and lets you keep one copy, keep & delete the other copies from disk,
    or dismiss the group (restorable). A scan refreshes the list.
  - Persisted in a new `duplicate_records` table; only gid-bearing copies
    participate (a CBZ whose ExHentai id lives in an external sidecar still
    needs that metadata wired up — see backend roadmap).

## [1.2.8] - 2026-08-27

### Fixed

- **Telegram digest is no longer split during active batches**: the 60-second
  fallback timer used to flush a partial digest while a download batch was still
  running (e.g. "2 completed" mid-batch). It now only flushes buffers that have
  received no new events for the interval, so a bulk run still collapses into a
  single summary when the queue goes idle.
- **Settings re-validation**: merged user settings are now re-validated instead
  of copied with `model_copy`, which skipped pydantic validation. Without
  `ENCRYPTION_KEY`, ExHentai cookies are stored as a plaintext JSON string that
  used to survive loading as a string and crash the backend at startup after
  any settings save.

## [1.2.7] - 2026-08-27

### Changed

- **Telegram download notifications are now a digest by default**: a bulk
  download used to fire one message per gallery success/failure. A new
  `telegram_notify_level` setting (`summary` / `immediate` / `failures_only` /
  `off`, default `summary`) controls this. In `summary` mode terminal download
  events are buffered and flushed as a single "download summary" message as
  soon as the download queue is idle (60s timer + 50-event buffer cap as
  fallbacks); `immediate` keeps the old per-event behaviour; `failures_only`
  sends only final failures; `off` disables automatic notifications while
  keeping the test button and interactive bot. Only final (non-retryable)
  download failures are reported. Scan and favorites notifications are
  unchanged.

## [1.2.6] - 2026-08-27

### Fixed

- **Telegram auto-notifications were silently dropped**: `send_message` required
  an explicit `chat_id`, so the automatic notifications for download success /
  failure and library-scan completion (which don't pass one) were rejected as
  "chat is not allowed" and never delivered. When no `chat_id` is given the
  message now fans out to **every** configured `telegram_chat_ids` chat; the
  "test message" button and the interactive bot behaviour are unchanged.

## [1.2.5] - 2026-08-26

### Changed

- **Smaller backend image**: dropped the never-used `uvicorn[standard]` extras
  (uvloop/httptools/watchfiles/websockets/PyYAML are not imported anywhere),
  trimmed the idle/tk stdlib modules and bytecode caches. The image is roughly
  25MB smaller while remaining a single-stage build for `linux/amd64` and
  `linux/arm64`.

## [1.2.4] - 2026-08-26

### Fixed

- **CSRF origin check accepts IPv6 hosts**: the middleware compared the
  `Origin` hostname against the `Host` header using `split(":", 1)[0]`, which
  splits inside an IPv6 literal — accessing the UI over IPv6
  (e.g. `http://[240e:...]:8000`) rejected every write API call
  (`DELETE`/`POST`/`PUT`) with `Cross-origin request rejected` (403). The Host
  header is now parsed with `urlparse`, so IPv6, IPv4 and hostname origins all
  match correctly.

## [1.2.3] - 2026-08-26

### Fixed

- **Transient ExHentai challenge backoff no longer holds a database
  connection**: the 30s pause before retrying a rate-challenged / reset
  download used to run *inside* the status-update transaction, pinning a
  connection-pool slot and the task row's lock for 30s. With concurrent
  download failures this could exhaust the pool; the backoff now happens after
  the transaction commits.
- **Favorites folder rows are pruned when galleries leave the cloud folder**:
  a successful full check now removes `favorite_items` rows for gids that were
  unfavorited or expunged (they vanish from the ExHentai listing). Previously
  those rows accumulated forever — the scheduled "cloud count unchanged → skip
  re-list" heuristic stopped firing (every poll re-walked the folder) and
  phantom cloud-only items lingered in lists.
- **Favorites metadata-sync progress resets per run**: `total`/`done`/`applied`
  counters accumulated across folders and invocations; the first sync of a
  batch now starts them from zero so the Logs page shows the current run.
- Removed a dead duplicate `return` in the tag-sync enqueue helper.
- `/api/favorites/cover` reads the cached cover file once instead of twice.
- **CI**: the backend image build now waits for the gitleaks secrets-scan job
  before pushing to Docker Hub (previously only the test job gated it).

## [1.2.2] - 2026-08-26

### Added

- **Incremental download ingest**: when a download finishes, the gallery is
  written into the database directly from the download result (title, category,
  tags, token and page facts) — no full library scan, no extra ExHentai fetch.
  The stored storage signature matches the library scanner's fingerprint, so a
  later full scan skips it instead of re-ingesting. The gallery's cover
  thumbnail is queued for background generation (and always generated on
  demand when first viewed).

## [1.2.1] - 2026-08-26

### Added

- **Favorites local/cloud filter**: folder lists can filter by `state=all|local|cloud` (only local, only cloud, or everything).
- **「下载缺失项目」button** on the favorites overview (`POST /api/favorites/download-missing`): spawns a per-folder pass that downloads cover files for every gallery missing one on disk.
- **Cover thumbnails captured from the favorites listing** (migration 0018 `favorite_items.thumb`): `fetch_favorites` parses each gallery's cover thumb URL straight from the glthumb cell, so a folder check warms covers, tags and sizes together without a gdata round-trip.

### Fixed

- **Favorites covers actually appear now**: the thumbnail was parsed from the title link's label (which never contains an `<img>`), so `favorite_items.thumb` was always empty and the cover-heal never downloaded anything. It now parses the separate glthumb `<a><img>` per page and looks up by gid.
- **Production favorites checks silently no-op'd**: the deployed compose never configured ExHentai cookies, so `favorites.php` 302'd to the home page. Configure the cookies in **Settings → ExHentai** (stored encrypted in PostgreSQL via `ENCRYPTION_KEY`); the compose file should **not** set `EXHENTAI_COOKIES`.
- **Favorites listing tag garbage**: cloud-item tags now render namespace/name correctly instead of raw gdata strings.

### Changed

- **Pagination**: the aggressive infinite scroll now applies only to the **gallery library** page; every other gallery list (tags browse, favorite folders) returns to numbered-page pagination with a default of **24 galleries per page** (`PAGE_SIZES` = 5/24/50/100/200/500).
- **Tag chips clamped to two lines** in cards so long tag lists no longer blow up card heights.

## [1.2.0] - 2026-08-26

### Added

- **Download speed + ETA** on the Downloads page (live bytes/s and estimated
  time remaining for active tasks, computed from the downloader's byte stats).
- **Reader fullscreen & fit-to-width**: toggle with a button or the `F` key.
- **Infinite scroll** on the library and favorite-folder grids (an
  IntersectionObserver appends later pages as you scroll; the server-side
  pager stays as a fallback).
- **pg_trgm GIN indexes** on `galleries.title`/`title_jpn` (migration 0015) so
  leading-wildcard `ILIKE` search stays index-assisted at 100k+ gallery scale.

### Changed

- **Page resolution via the `showpage` API** (mirroring Ehviewer_CN_SXJ): after
  the first viewer page yields a `showkey`, remaining page URLs are resolved
  with one lightweight `api.php` POST each, falling back to full HTML on any
  failure. Less bandwidth, more robust to HTML changes.
- **Gallery sub-pages are enumerated concurrently**: the `?p=N` walk is sized
  with the gdata `filecount` and fetched in parallel, with a sequential tail
  for stale counts. Sample downloads (`max_pages`) now resolve only the pages
  they need.
- **Favorites scheduled polls skip the full re-list** when the cloud folder
  count matches the locally recorded count from the last successful check —
  a multi-thousand-item folder no longer re-walks every favorites page.
- **Anti-hijack guard on image downloads**: responses landing outside
  ExHentai's CDN/infra (hath.network / ehgt.org / exhentai.org) are rejected.

### Fixed

- **`.ehviewer` pTokens were empty on every download** — the viewer URL parser
  did not match the current `/s/<pToken>/<gid>-<page>` format, so Ehviewer
  could not resume/preview downloaded galleries offline. Real pTokens are now
  extracted and written.
- **Image downloads stalled up to 60s** on a dead H@H node: a read-idle
  watchdog (15s without bytes) aborts and retries; `Content-Length` is now
  verified so truncated pages are re-fetched instead of written corrupt.
- **Retry hammering during ExHentai IP challenges**: connection resets and
  other transient transport failures now back off 30s before retrying (only
  the text `challenge` triggered backoff before), and `_get` wraps body reads
  so a reset surfaces as a retryable error instead of a raw exception.
- **Preview metadata**: `.ehviewer` now writes real `previewPages`/
  `previewPerPage` (20 per gallery page) instead of `1/1`.

## [1.1.0] - 2026-08-26

### Added

- First-run welcome wizard (`#/welcome`): guided change-password → ExHentai
  cookies → fill-the-library steps, shown while the default password is in use.
  New endpoint `GET /api/onboarding/status`.
- `POST /api/favorites/download-selected`: batch-enqueue downloads for selected
  favorite gids straight from the database (the SPA no longer pages through the
  whole folder).
- Official GitHub Wiki as the documentation site, with a bilingual (EN/中文)
  sidebar and an auto-synced OpenAPI schema.

### Changed

- **Favorites reads are database-first.** After a favorites check warms the
  `gallery_metadata` cache (and cover files land on disk), browsing a folder,
  viewing ignored duplicates and the duplicate-scan enrichment talk to the
  database only — ExHentai is only contacted for gids that were never cached.
- Tag sync now **waits for a running favorites check**: galleries whose
  metadata cache entry isn't populated yet are re-queued and retried (bounded,
  so non-favorites galleries still sync) instead of doing a redundant
  one-by-one ExHentai fetch that the gdata batch is about to cover.
- Remote covers fall back to the on-disk cache even when no thumb URL is
  available, so DB-cached galleries keep their covers without a fetch.

### Fixed

- Remote covers (and thumbnails) failed to cache for the unprivileged app user:
  legacy root-owned `/gv-cache` subdirectories were not writable, so ExHentai
  cover downloads were silently swallowed and cloud galleries showed no cover.
  The entrypoint now chowns the cache tree recursively and cover write errors
  are logged instead of swallowed.

## [1.0.0] - 2026-08-26

First tagged release. GalleryVault is a feature-complete, self-hosted local
gallery library manager with ExHentai integration.

### Added

- Local gallery library: scan Ehviewer export directories, CBZ/CBR archives and
  plain image folders into a persistent, searchable PostgreSQL index.
- Namespaced tag system with a frequency-weighted tag cloud and instant tag
  autocomplete.
- Tag translation via the EhTagTranslation database, including reverse matching
  from Chinese input (typing 巨乳 suggests `big breasts`).
- Full English / Chinese bilingual UI; translations shown for tags in the
  Chinese view.
- ExHentai integration: fetch metadata, categories and tags using your own
  cookies (`ipb_member_id` / `ipb_pass_hash` / `igneous`), HTTP or SOCKS5 proxy.
- Download manager: Ehviewer-style concurrent page downloads, live progress,
  resumable retries, partial downloads (`max_pages`), cancel and bulk retry.
- Favorites monitor: watches the ten ExHentai favorite folders and
  auto-downloads missing galleries (scheduled or on demand), plus per-folder
  grids, duplicate scan with ignore/restore, and metadata caching via the gdata
  API that is reused during library scans.
- Reader with streaming page loads, keyboard/space/click paging, preloading,
  auto-advance to the next gallery and saved reading position; browsable history.
- Activity log page aggregating background tasks (scan, tag sync, thumbnail
  generation, favorites metadata) with running/finished sections.
- Telegram notifications for downloads, scans and favorite sync.
- One-command deployment: two multi-arch (amd64/arm64) Docker Hub images plus
  PostgreSQL with a single `docker compose up`.
- Security: PBKDF2-SHA256 auth with persistent sessions, login rate limiting
  keyed on the real client IP, cross-origin checks, ExHentai domain whitelist,
  optional non-root runtime, and optional at-rest encryption (`ENCRYPTION_KEY`,
  AES-256-GCM) protecting cookies / bot token / password hashes with automatic
  plaintext migration on startup.
- Documentation site as a GitHub Wiki (deployment, usage, backup, encryption,
  API reference, development, FAQ), kept in sync with the backend docs.

[Unreleased]: https://github.com/ResidualBlood/galleryvault/compare/v1.7.1...HEAD
[1.7.1]: https://github.com/ResidualBlood/galleryvault/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/ResidualBlood/galleryvault/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/ResidualBlood/galleryvault/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.6.0
[1.5.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.5.0
[1.2.15]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.15
[1.2.14]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.14
[1.2.13]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.13
[1.2.12]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.12
[1.2.11]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.11
[1.2.10]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.10
[1.2.9]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.9
[1.2.8]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.8
[1.2.7]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.7
[1.2.6]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.6
[1.2.5]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.5
[1.2.4]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.4
[1.2.3]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.3
[1.2.2]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.2
[1.2.1]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.1
[1.2.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.2.0
[1.1.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.1.0
[1.0.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.0.0
