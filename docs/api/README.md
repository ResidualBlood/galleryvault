# GalleryVault API 文档入口

> 人读摘要；机器可读 schema 见 [galleryvault-api.yaml](galleryvault-api.yaml)；完整接口说明见仓库 `backend/docs/API.md`（正文 + curl 示例）。

## 概览

- 后端是 FastAPI **纯 JSON API**（无 HTML 页面、无静态文件），容器内监听 `:8001`，由前端 nginx 反代 `/api`、`/login`、`/logout`。装配见 `backend/galleryvault/app/main.py`（`create_app()`，`main.py:60`），路由统一在 `main.py:102-122` 用 `include_router` 注册。
- 机器可读 schema 由 `backend/scripts/export_openapi.py` 从 `app.openapi()` 导出，仓库同时提交 `backend/docs/openapi.json`；本目录的 `galleryvault-api.yaml` 是其 YAML 版本（内容同源）。
- 端点数量：约 150 个操作（含 `HEAD`），分属 25 个 router 文件。

## 鉴权模型

全局中间件 `auth_and_csrf_middleware`（`backend/galleryvault/app/middleware.py`）对 `/api/*` 统一做鉴权 + CSRF 校验；安全响应头见同文件 `SECURITY_HEADERS`。

| 鉴权方式 | 适用端点 | 说明 |
| :--- | :--- | :--- |
| **无鉴权** | `/healthz`、`/metrics`、`GET/POST /login`、`POST /logout` | 见 `middleware.py` 的豁免清单；登录 `POST /login` 为表单 `password` 字段 |
| **会话 Cookie** | 其余全部 `/api/*` | `galleryvault_session`（HttpOnly、SameSite=lax）；未认证返回 `401` |
| **CSRF** | 所有变更类（POST/PUT/PATCH/DELETE） | 校验 `Origin`→`Referer`→`X-CSRF-Token`（cookie `galleryvault_csrf`，前端 `frontend/src/api/client.ts` 自动附带） |
| **HTTP Basic** | `GET /api/opds`、`GET/HEAD /api/galleries/{id}/export.cbz` | 固定用户名 `galleryvault`，密码 = Web 登录密码；返回 `401` + `WWW-Authenticate: Basic realm="GalleryVault OPDS"` |
| **Bearer Token**（伴侣脚本） | 仅 `_BEARER_ALLOWED_ROUTES` 白名单（`middleware.py:37-46`）：`GET /api/auth/session`、`GET /api/eh/status`、`GET /api/favorites/categories`、`POST /api/favorites/add`、`POST /api/favorites/remove`、`POST /api/downloads`、`GET /api/downloads` | 其余敏感端点（设置、改密、token 管理）必须走会话 Cookie |

## 端点清单（按 router 文件，`文件:行` = 处理函数定义处）

除上表特别标注外，下表端点默认 **会话 Cookie** 鉴权。表内 `文件:行` 均相对 `backend/`。

### 认证与会话 — `galleryvault/app/routers/auth.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| POST | `/login` | `login` | `auth.py:103` |
| GET | `/login` | `login_get` | `auth.py:169` |
| POST | `/logout` | `logout` | `auth.py:174` |
| GET | `/api/auth/session` | `auth_session` | `auth.py:182` |
| POST | `/api/auth/api-token` | `create_api_token` | `auth.py:193` |
| GET | `/api/auth/api-token` | `get_api_token` | `auth.py:210` |
| DELETE | `/api/auth/api-token` | `revoke_api_token` | `auth.py:226` |
| GET | `/api/onboarding/status` | `onboarding_status` | `auth.py:243` |
| POST | `/api/auth/change-password` | `change_password` | `auth.py:267` |

### 健康与指标 — `core.py`

| 方法 | 路径 | 处理函数 | 位置 | 鉴权 |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/healthz` | `healthz` | `core.py:18` | 无 |
| GET | `/metrics` | `metrics` | `core.py:29` | 无 |

### 下载 — `downloads.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| POST | `/api/downloads` | `create_download` | `downloads.py:139` |
| POST | `/api/downloads/batch` | `create_downloads_batch` | `downloads.py:170` |
| GET | `/api/downloads` | `list_downloads` | `downloads.py:242` |
| POST | `/api/downloads/clear-success` | `clear_success_downloads` | `downloads.py:322` |
| POST | `/api/downloads/retry-all` | `retry_all_downloads` | `downloads.py:347` |
| POST | `/api/downloads/{task_id}/retry` | `retry_download` | `downloads.py:399` |
| POST | `/api/downloads/{task_id}/cancel` | `cancel_download` | `downloads.py:436` |
| DELETE | `/api/downloads/{task_id}` | `delete_download_task` | `downloads.py:467` |

### 查重 — `duplicates.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/scan/duplicates` | `list_duplicates` | `duplicates.py:80` |
| POST | `/api/scan/duplicates/{gid}/resolve` | `resolve_duplicate` | `duplicates.py:107` |
| POST | `/api/scan/duplicates/{gid}/dismiss` | `dismiss_duplicate` | `duplicates.py:169` |
| POST | `/api/scan/duplicates/{gid}/restore` | `restore_duplicate` | `duplicates.py:182` |
| POST | `/api/scan/duplicates/{gid}/{status}` | `set_duplicate_status_route` | `duplicates.py:195` |
| GET | `/api/scan/duplicates/thumb/{key}` | `duplicate_thumb` | `duplicates.py:214` |
| GET | `/api/library/duplicates/cross-gid` | `list_cross_gid_groups` | `duplicates.py:334` |
| POST | `/api/library/duplicates/cross-gid/{group_id}/dismiss` | `dismiss_cross_gid_duplicate` | `duplicates.py:362` |
| POST | `/api/library/duplicates/cross-gid/{group_id}/restore` | `restore_cross_gid_duplicate` | `duplicates.py:375` |
| POST | `/api/library/duplicates/cross-gid/refresh` | `refresh_cross_gid_groups` | `duplicates.py:388` |

### ExHentai 在线 — `eh.py` / `eh_online.py` / `eh_online_proxy.py` / `eh_progress.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/eh/search` | `eh_search` | `eh.py:207` |
| GET | `/api/eh/galleries/{gid}/{token}` | `eh_online_gallery_detail` | `eh_online.py:295` |
| GET | `/api/eh/galleries/{gid}/{token}/pages` | `eh_online_pages` | `eh_online.py:364` |
| GET | `/api/eh/galleries/{gid}/{token}/pages/{n}/resolve` | `eh_online_resolve_page` | `eh_online.py:391` |
| GET | `/api/eh/status` | `eh_local_status` | `eh_online.py:433` |
| GET | `/api/eh/galleries/{gid}/{token}/pages/{n}/image` | `eh_online_page_image` | `eh_online_proxy.py:43` |
| GET | `/api/eh/galleries/{gid}/{token}/progress` | `eh_online_progress` | `eh_progress.py:83` |
| PUT | `/api/eh/galleries/{gid}/{token}/progress` | `save_eh_online_progress` | `eh_progress.py:100` |
| GET | `/api/eh/history` | `eh_online_history` | `eh_progress.py:126` |

### 收藏夹 — `favorites.py` + `maintain/favorite_duplicates.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/favorites/{favcat}/items` | `favorite_items` | `favorites.py:249` |
| POST | `/api/archives/preview` | `archives_preview` | `favorites.py:440` |
| POST | `/api/favorites/download-selected` | `favorites_download_selected` | `favorites.py:567` |
| POST | `/api/favorites/remove` | `favorites_remove` | `favorites.py:658` |
| POST | `/api/favorites/move` | `favorites_move` | `favorites.py:692` |
| POST | `/api/favorites/add` | `favorites_add` | `favorites.py:751` |
| POST | `/api/favorites/note` | `favorites_set_note` | `favorites.py:784` |
| GET | `/api/favorites/cover` | `favorite_cover` | `favorites.py:846` |
| GET | `/api/favorites/categories` | `favorite_categories` | `favorites.py:907` |
| GET | `/api/favorites/check-status` | `favorites_check_status` | `favorites.py:946` |
| POST | `/api/favorites/download-missing` | `download_missing_favorites` | `favorites.py:952` |
| POST | `/api/favorites/sync-categories` | `sync_favorite_categories` | `favorites.py:970` |
| POST | `/api/favorites/{favcat}/check` | `check_favorites` | `favorites.py:984` |
| POST | `/api/favorites/check-all` | `check_all_favorites` | `favorites.py:995` |
| POST | `/api/favorites/duplicates/scan` | `duplicates_scan` | `maintain/favorite_duplicates.py:41` |
| GET | `/api/favorites/duplicates/status` | `duplicates_status` | `maintain/favorite_duplicates.py:50` |
| GET | `/api/favorites/duplicates/ignored` | `duplicates_ignored_list` | `maintain/favorite_duplicates.py:86` |
| POST | `/api/favorites/duplicates/ignore` | `duplicates_ignore` | `maintain/favorite_duplicates.py:156` |
| DELETE | `/api/favorites/duplicates/ignore` | `duplicates_unignore` | `maintain/favorite_duplicates.py:181` |
| POST | `/api/favorites/duplicates/unignore` | `duplicates_unignore` | `maintain/favorite_duplicates.py:182` |

### 画廊 — `galleries/delete.py`、`galleries/detail.py`、`galleries/listing.py`、`galleries_media.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| DELETE | `/api/galleries/{identifier}` | `delete_gallery` | `galleries/delete.py:34` |
| POST | `/api/galleries/delete-bulk` | `delete_galleries_bulk` | `galleries/delete.py:75` |
| POST | `/api/galleries/delete-filtered` | `delete_galleries_filtered` | `galleries/delete.py:119` |
| GET | `/api/galleries/{identifier}/next` | `gallery_next` | `galleries/detail.py:47` |
| GET | `/api/galleries/{identifier}` | `get_gallery` | `galleries/detail.py:62` |
| PATCH | `/api/galleries/{identifier}/local` | `patch_gallery_local` | `galleries/detail.py:77` |
| POST | `/api/galleries/{identifier}/download-original` | `download_gallery_original` | `galleries/detail.py:119` |
| GET | `/api/galleries/{identifier}/favorite` | `gallery_favorite_status` | `galleries/detail.py:178` |
| POST | `/api/galleries/{identifier}/redownload` | `redownload_gallery` | `galleries/detail.py:220` |
| POST | `/api/galleries/{identifier}/archive` | `archive_gallery` | `galleries/detail.py:269` |
| POST | `/api/galleries/{identifier}/unarchive` | `unarchive_gallery` | `galleries/detail.py:286` |
| POST | `/api/galleries/{identifier}/sync-tags` | `sync_gallery_tags` | `galleries/detail.py:309` |
| GET | `/api/galleries` | `list_galleries` | `galleries/listing.py:40` |
| GET | `/api/galleries/trash` | `list_trash` | `galleries/listing.py:125` |
| GET | `/api/galleries/expunged` | `list_expunged` | `galleries/listing.py:152` |
| POST | `/api/galleries/expunged/redownload` | `redownload_expunged` | `galleries/listing.py:182` |
| POST | `/api/galleries/restore` | `restore_galleries` | `galleries/listing.py:262` |
| POST | `/api/galleries/purge` | `purge_galleries` | `galleries/listing.py:279` |
| GET | `/api/galleries/random` | `random_gallery` | `galleries/listing.py:307` |
| GET | `/api/galleries/{identifier}/export.cbz` | `export_gallery_cbz` | `galleries_media.py:109` |
| GET | `/api/galleries/{identifier}/pages/{page_index}` | `get_page` | `galleries_media.py:175` |
| GET | `/api/galleries/{identifier}/pages/{page_index}/meta` | `get_page_meta` | `galleries_media.py:209` |
| GET | `/api/galleries/{identifier}/thumb/{page_index}` | `get_thumbnail` | `galleries_media.py:280` |

### 本地列表 — `lists.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/lists` | `list_local_lists` | `lists.py:29` |
| POST | `/api/lists` | `create_local_list` | `lists.py:50` |
| PATCH | `/api/lists/{list_id}` | `rename_local_list` | `lists.py:80` |
| DELETE | `/api/lists/{list_id}` | `delete_local_list` | `lists.py:102` |
| POST | `/api/lists/{list_id}/items` | `add_local_list_items` | `lists.py:126` |
| POST | `/api/lists/{list_id}/items/remove` | `remove_local_list_items` | `lists.py:151` |
| GET | `/api/galleries/{identifier}/lists` | `gallery_local_lists` | `lists.py:176` |

### 完整性体检 — `maintain/integrity.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/galleries/integrity` | `list_integrity` | `maintain/integrity.py:38` |
| POST | `/api/galleries/integrity/scan` | `trigger_integrity_scan` | `maintain/integrity.py:91` |

### 通知与 Telegram — `notifications.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/notifications` | `get_notifications` | `notifications.py:26` |
| POST | `/api/notifications/read` | `read_notifications` | `notifications.py:31` |
| POST | `/api/notifications/clear` | `clear_notifications_endpoint` | `notifications.py:36` |
| POST | `/api/telegram/test` | `telegram_test` | `notifications.py:41` |

### OPDS — `opds.py`

| 方法 | 路径 | 处理函数 | 位置 | 鉴权 |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/api/opds` | `opds_catalog` | `opds.py:29` | Basic 或会话 |

### 阅读进度与历史 — `reading.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/galleries/{identifier}/progress` | `gallery_progress` | `reading.py:88` |
| PUT | `/api/galleries/{identifier}/progress` | `save_gallery_progress` | `reading.py:99` |
| GET | `/api/history` | `history` | `reading.py:111` |
| DELETE | `/api/history` | `clear_history` | `reading.py:123` |
| DELETE | `/api/galleries/progress` | `clear_all_gallery_progress` | `reading.py:137` |
| DELETE | `/api/galleries/{identifier}/progress` | `clear_gallery_progress` | `reading.py:151` |

### 保存的搜索 — `saved_searches.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/saved-searches` | `saved_searches_list` | `saved_searches.py:69` |
| POST | `/api/saved-searches` | `saved_searches_add` | `saved_searches.py:83` |
| DELETE | `/api/saved-searches/{search_id}` | `saved_searches_delete` | `saved_searches.py:108` |

### 系列 — `series.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/series` | `list_series` | `series.py:190` |
| POST | `/api/series` | `create_series` | `series.py:246` |
| PATCH | `/api/series/{series_id}` | `rename_series` | `series.py:272` |
| DELETE | `/api/series/{series_id}` | `delete_series` | `series.py:293` |
| POST | `/api/series/{series_id}/items` | `add_series_items` | `series.py:310` |
| GET | `/api/series/{series_id}/cloud-candidates` | `get_series_cloud_candidates` | `series.py:331` |
| POST | `/api/series/{series_id}/cloud-items` | `add_series_cloud_items` | `series.py:351` |
| POST | `/api/series/{series_id}/cloud-items/remove` | `remove_series_cloud_items` | `series.py:372` |
| POST | `/api/series/{series_id}/items/remove` | `remove_series_items` | `series.py:393` |
| POST | `/api/series/rebuild` | `rebuild_series` | `series.py:437` |

### 设置与系统 — `settings.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/settings` | `settings_get` | `settings.py:154` |
| POST | `/api/settings` | `settings_save` | `settings.py:175` |
| GET | `/api/settings/cookie-health` | `settings_cookie_health` | `settings.py:195` |
| POST | `/api/settings/exhentai/test` | `settings_test_exhentai` | `settings.py:212` |
| GET | `/api/system/logs` | `system_logs_get` | `settings.py:498` |
| POST | `/api/system/logs/level` | `system_logs_set_level` | `settings.py:515` |
| DELETE | `/api/system/logs` | `system_logs_clear` | `settings.py:522` |
| GET | `/api/system/logs/download` | `system_logs_download` | `settings.py:529` |
| GET | `/api/system/storage` | `system_storage` | `settings.py:595` |
| POST | `/api/system/purge-archived-sources` | `purge_archived_sources` | `settings.py:606` |

### 标签 — `tags.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/tags/search` | `tag_search` | `tags.py:34` |
| GET | `/api/tags/search/status` | `tag_translation_status` | `tags.py:90` |
| POST | `/api/tags/search/reload` | `tag_translation_reload` | `tags.py:102` |

### 后台任务与归档 — `tasks.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/pause` | `get_pause` | `tasks.py:64` |
| POST | `/api/pause` | `set_pause` | `tasks.py:70` |
| GET | `/api/quota` | `get_quota` | `tasks.py:106` |
| POST | `/api/scan` | `trigger_scan` | `tasks.py:112` |
| GET | `/api/scan` | `scan_status` | `tasks.py:124` |
| GET | `/api/logs` | `background_task_logs` | `tasks.py:130` |
| POST | `/api/logs/{task}/cancel` | `cancel_background_task` | `tasks.py:138` |
| GET | `/api/archive` | `archive_status` | `tasks.py:149` |
| POST | `/api/archive/restore` | `restore_archive` | `tasks.py:159` |
| POST | `/api/archive` | `trigger_archive` | `tasks.py:177` |
| GET | `/api/tag-sync/status` | `tag_sync_status` | `tasks.py:194` |
| POST | `/api/tag-sync/refresh-categories` | `trigger_category_refresh` | `tasks.py:200` |
| POST | `/api/tag-sync/repair-categories` | `repair_categories` | `tasks.py:211` |
| GET | `/api/thumbs/status` | `thumb_status` | `tasks.py:221` |
| POST | `/api/thumbs/generate` | `trigger_thumbnail_generation` | `tasks.py:227` |
| POST | `/api/tag-sync/start` | `trigger_tag_sync` | `tasks.py:303` |

### 更新画廊 — `updates.py`

| 方法 | 路径 | 处理函数 | 位置 |
| :--- | :--- | :--- | :--- |
| GET | `/api/updates` | `gallery_updates_list` | `updates.py:37` |
| POST | `/api/updates/scan` | `gallery_updates_scan` | `updates.py:101` |
| GET | `/api/updates/status` | `gallery_updates_status` | `updates.py:110` |
| POST | `/api/updates/update` | `gallery_updates_run` | `updates.py:133` |
| POST | `/api/updates/ignore` | `gallery_updates_ignore` | `updates.py:145` |
| GET | `/api/updates/ignored` | `gallery_updates_ignored` | `updates.py:161` |
| POST | `/api/updates/unignore` | `gallery_updates_unignore` | `updates.py:170` |
| POST | `/api/updates/delete` | `gallery_updates_delete` | `updates.py:186` |

## 数据模型与错误格式

错误响应体与数据库模型见 [models.md](models.md)。
