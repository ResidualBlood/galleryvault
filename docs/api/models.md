# GalleryVault 数据模型与错误格式

> 数据库表模型见 `backend/galleryvault/db/models.py`（SQLAlchemy 2.x Declarative）；Pydantic 响应/请求模型见 `backend/galleryvault/app/schemas/`。本文件只写概要与错误体，字段级口径以代码为准。

## 错误响应体

GalleryVault **不采用 RFC 9457（`application/problem+json`）**，而是用自定义的 `{detail, code, details?}` 结构。错误基类与序列化在 `backend/galleryvault/app/exceptions.py`：

- `GalleryVaultError.to_dict()`（`exceptions.py:25`）输出：

```json
{ "detail": "<message>", "code": "<CODE>" }
```

- 有附加信息时追加 `details`（如 `NotFoundError` 会带 `entity`、`identifier`，见 `exceptions.py:67-75`）。
- 全局异常处理器在 `main.py:88-98`：捕获 `GalleryVaultError`，按 `status_code` 返回 `JSONResponse`，body 即 `to_dict()`。

错误码层级（均在 `exceptions.py`）：

| 异常类 | 默认 code | 默认 status |
| :--- | :--- | :--- |
| `GalleryVaultError`（基类） | `INTERNAL_ERROR` | 500 |
| `DomainError` | `DOMAIN_ERROR` | 400 |
| `NotFoundError` | `NOT_FOUND` | 404 |
| `ValidationError` | `VALIDATION_ERROR` | 422 |
| `ConflictError` | `CONFLICT` | 409 |
| `EhClientError` | `EH_CLIENT_ERROR` | 502 |
| `EhClientUnavailableError` | `EH_CLIENT_UNAVAILABLE` | 503 |
| `EhQuotaExceededError` | `EH_QUOTA_EXCEEDED` | 429 |
| `DatabaseError` | `DATABASE_ERROR` | 503 |

典型鉴权失败（无业务异常）：未认证的 `/api/*` 返回 `401 {"detail":"Authentication required"}`（由中间件生成，非上述异常）；CSRF 失败同样 401/403。

## 数据库表（SQLAlchemy 模型）

`backend/galleryvault/db/models.py` 定义 30 张表，`Base` 在 `models.py:25`。按领域分组：

| 表名 | 模型类 | 位置 | 用途 |
| :--- | :--- | :--- | :--- |
| `galleries` | `Gallery` | `models.py:29` | 画廊主记录（gid、标题、分类、页数、评分、存储层等） |
| `gallery_pages` | `GalleryPage` | `models.py:129` | 画廊单页（页号、文件名、hash、大小） |
| `tags` | `Tag` | `models.py:143` | 标签（namespace、name、display） |
| `gallery_tags` | `GalleryTag` | `models.py:159` | 画廊↔标签多对多 |
| `download_tasks` | `DownloadTask` | `models.py:168` | 下载任务（状态、进度、重试） |
| `favorites_monitor` | `FavoritesMonitor` | `models.py:231` | 收藏夹监控配置（每夹模式/间隔） |
| `gallery_updates` | `GalleryUpdate` | `models.py:254` | 重传版本检测结果 |
| `favorite_items` | `FavoriteItem` | `models.py:281` | 收藏夹条目 |
| `gallery_metadata` | `GalleryMetadata` | `models.py:304` | 画廊元数据（jsonb） |
| `local_lists` / `local_list_items` | `LocalList` / `LocalListItem` | `models.py:333/342` | 本地自定义列表 |
| `favorite_duplicate_ignores` | `DuplicateIgnore` | `models.py:353` | 收藏夹查重已忽略组 |
| `duplicate_records` / `duplicate_groups` | `DuplicateRecord` / `DuplicateGroup` | `models.py:369/391` | 同 GID 副本记录与分组 |
| `app_config` | `AppConfig` | `models.py:445` | 运行时键值配置（含持久化 auth secret 等） |
| `reading_progress` / `online_reading_progress` | `ReadingProgress` / `OnlineReadingProgress` | `models.py:454/466` | 本地/在线阅读进度 |
| `reading_history` | `ReadingHistory` | `models.py:487` | 阅读历史 |
| `favorites_check_logs` | `FavoritesCheckLog` | `models.py:502` | 收藏夹检查日志 |
| `download_attempts` | `DownloadAttempt` | `models.py:514` | 下载尝试记录 |
| `background_jobs` | `BackgroundJob` | `models.py:525` | 后台任务记录 |
| `task_runs` | `TaskRun` | `models.py:554` | 任务运行历史（启动时按任务名裁剪） |
| `series` / `series_items` / `series_exclusions` | `Series` / `SeriesItem` / `SeriesExclusion` | `models.py:618/631/643` | 系列聚合 |
| `series_cloud_items` / `series_cloud_exclusions` | `SeriesCloudItem` / `SeriesCloudExclusion` | `models.py:653/665` | 系列云端补全条目 |

迁移由 Alembic 管理（`backend/alembic/versions/`，共 46 个迁移脚本），启动时自动迁移。

## Pydantic 请求/响应模型

`backend/galleryvault/app/schemas/`（`common.py`、`gallery.py`、`updates.py`）存放 API 层 Pydantic 模型；`galleryvault/app/routers/` 内各 router 也内联了不少 `_*Response` 模型（如 `downloads.py` 的 `_DownloadListResponseOut`）。机读 schema 以 `docs/api/galleryvault-api.yaml` 为准。
