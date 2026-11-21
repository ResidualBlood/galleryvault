# GalleryVault 配置项

> 唯一事实来源是 `backend/galleryvault/config.py` 的 `Settings`（pydantic-settings，`model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)`）。环境变量名 = 字段名（大小写不敏感）；下表只列常用项，完整默认值与校验见 `config.py`。

## 数据库

| 字段（环境变量） | 默认值 | 说明 |
| :--- | :--- | :--- |
| `database_url` | `postgresql+asyncpg://galleryvault:galleryvault@db:5432/galleryvault` | 主库连接串 |
| `database_pool_size` / `database_max_overflow` / `database_pool_timeout` | 30 / 10 / 30 | API 连接池 |
| `database_statement_timeout_ms` / `database_lock_timeout_ms` / `database_idle_in_tx_timeout_ms` | 30000 / 5000 / 60000 | 语句/锁/空闲事务上限 |
| `worker_database_pool_size` 等 | 5 / 5 / 30 | worker 独立连接池 |

## 存储路径

| 字段 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `library_roots` | `["/library", "/downloads"]` | 库扫描根（容器内路径） |
| `download_root` | `/downloads` | 下载落盘目录 |
| `cold_storage_root` | `""` | 冷存储根（未配置时回退 `archive_roots`） |
| `archive_roots` | `[]` | 归档根（多盘，每行一个） |
| `thumbnail_cache_dir` | `/gv-cache/thumbs` | 缩略图缓存 |
| `log_file` / `log_max_bytes` / `log_backup_count` | 无 / 10MB / 3 | 日志文件与轮转 |

## 鉴权与安全

| 字段 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `auth_required` | `True` | 是否要求登录 |
| `auth_cookie_name` | `galleryvault_session` | 会话 Cookie 名 |
| `auth_session_ttl` | 2592000（30 天） | 会话有效期（秒） |
| `auth_password` / `auth_password_hash` | 无 | 初始密码/密码哈希（凭据：只写“值放哪”，不写值；运行时保存在 `app_config`） |
| `auth_secret` | 无 | 会话签名密钥（持久化到 DB，重启保持登录） |
| `trusted_proxies` | `[]` | 反向代理信任网段 |
| `PUID` / `PGID`（经 Compose 传参） | — | 降权运行 |

## ExHentai 与下载

| 字段 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `exhentai_base_url` | `https://exhentai.org` | 里站基址（校验只允许 `exhentai.org` / `e-hentai.org` 域名） |
| `exhentai_cookies` | `{}` | Cookie（JSON 对象；加密存储，见 wiki [静态加密](../wiki/Encryption.md)） |
| `http_proxy` / `socks5_proxy` | 无 | 代理（二者只能配一个，`config.py:185`） |
| `download_quality` | `resample` | 下载画质（`original`/`resample`） |
| `archive_quality` | `resample` | Archive 通道画质 |
| `download_concurrency` | 2 | 下载并发 |
| `page_concurrency` | 4 | 页并发 |
| `exhentai_max_concurrency` | 6 | 全后台 EH 请求并发上限 |
| `image_download_timeout_seconds` / `image_slow_warmup_seconds` / `image_min_speed_kb_s` | 120 / 30 / 10 | 图片下载看门狗 |

## 收藏 / 标签 / 通知 / Telegram

| 字段 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `favorites_poll_interval_minutes` | 720 | 收藏夹全局轮询（前端每夹可调，最小 10 分钟） |
| `favorites_categories` | `[0..9]` | 启用的收藏夹 |
| `favorites_cloud_open` | `app` | 云端条目打开方式（`app`/`external`） |
| `favorites_archive_enabled` / `favorites_archive_max_pages` / `archive_fallback_pages` | False / 0 / True | 定时收藏走 Archive 通道的阈值与回退 |
| `duplicate_policy` | `keep_first` | 同 GID 副本保留策略 |
| `auto_sync_tags` / `tag_sync_interval_seconds` / `tag_sync_concurrency` | True / 1.5 / 4 | 标签同步 |
| `telegram_bot_token` / `telegram_chat_ids` / `telegram_allowed_user_ids` | 无 | Telegram Bot（token 为凭据，只写“值放哪”） |
| `telegram_notify_level` / `telegram_notify_lang` | `summary` / `zh` | 通知级别/语言 |
| `global_paused` | False | 全局暂停开关 |

## 前端偏好（localStorage，非环境变量）

- `gv_theme`（dark/light/system）、`gv_lang`（zh/en）、`gv_page_size`、`gv_view_mode`（每页视图模式）——见 `frontend/src/stores/settings.ts:7-9` 与 `frontend/src/composables/useViewMode.ts`。

## 凭据位置（只写“在哪”，不写值）

- 测试登录口令：`local-credentials` 的 `galleryvault-test.env`（见项目 AGENTS.md「环境与端口」+ skill `galleryvault-maintenance`）。
- 生产口令：HANDOFF.md §1（本地、gitignore）；禁止抄进被跟踪文件。
- E-Hentai Cookie：测试用本地 `TEMP/cookies.txt`（见项目 AGENTS.md「环境与端口」，gitignore）。

> 项目根 AGENTS.md 与 HANDOFF.md 均被 `.gitignore` 忽略、含内网信息，只读、不得抄进被跟踪文档。
