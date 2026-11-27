# GalleryVault 架构

> 面向接手开发者的模块划分与数据流。用户向功能说明见 wiki [功能特性](../wiki/Features.md)；后端更细的说明见 `backend/docs/DEVELOPMENT.md`。

## 总览

Monorepo：`backend/`（FastAPI JSON API + PostgreSQL）+ `frontend/`（Vue 3 + Vite + TS SPA，nginx 服务）+ `docs/`（文档）。拓扑：

```
Browser ── :8000 ──▶ nginx (frontend/: SPA + 反代 /api,/login,/logout)
                        │
Browser ── :8001 ──▶ FastAPI (backend/galleryvault/app/main.py + routers) ──▶ PostgreSQL
```

后端是纯 JSON API（`backend/galleryvault/app/main.py:82` 创建 `FastAPI(title="GalleryVault")`）；前端 SPA 由 nginx 服务并反代 `/api`、`/login`、`/logout`。

## 后端模块划分（`backend/galleryvault/`）

| 包/模块 | 职责 | 关键文件 |
| :--- | :--- | :--- |
| `app/` | 应用装配与横切：工厂、中间件、异常、生命周期、全局状态 | `app/main.py`、`app/middleware.py`、`app/exceptions.py`、`app/state.py`、`app/lifespan.py` |
| `app/routers/` | HTTP 路由，按领域拆分（`galleries/`、`maintain/` 为子包） | `app/routers/*.py`（见 [API 文档](../api/README.md)） |
| `app/schemas/` | Pydantic 请求/响应模型 | `app/schemas/{common,gallery,updates}.py` |
| `app/core/` | 应用核心协作对象（EhClient 管理、任务分发、UoW） | `app/core/eh_client_manager.py`、`task_dispatcher.py`、`uow.py` |
| `config.py` | `Settings`（pydantic-settings），全部环境变量与默认值 | `config.py` |
| `db/` | SQLAlchemy 模型、session、repository、UoW | `db/models.py`、`db/session.py`、`db/repository.py`、`db/repositories/` |
| `services/` | 业务用例，按领域分包 | `services/{download,eh,favorites,reading,library,cold,maintain,tgbot,tasks}/` |
| `scanners/` | 文件系统扫描（Ehviewer 目录、CBZ/RAR/7z/PDF） | `scanners/` |
| `metadata/` | SpiderInfo / sidecar 元数据解析 | `metadata/` |
| `scripts/` | 运维/导出脚本（含 `export_openapi.py`） | `scripts/` |
| `alembic/` | 数据库迁移（46 个版本） | `alembic/versions/` |

`services/` 是按领域拆包后的业务层；旧的平铺模块通过 re-export 保留兼容（见 HANDOFF 2026-11-15 记录）。`services/tgbot/` 是 Telegram Bot 控制面。

## 关键横切设计

- **鉴权/CSRF**：全局中间件 `auth_and_csrf_middleware`（`app/middleware.py`）；会话 Cookie + 双提交 CSRF，Bearer 白名单见同文件 `_BEARER_ALLOWED_ROUTES`。
- **全局状态**：`app_state`（`app/state.py`）持有 settings、engine、task_manager、eh_client 等单例；`create_app()` 时装配。
- **后台 worker**：`app/workers.py` + `services/tasks` 的任务管理器；下载/标签同步/收藏检查/缩略图/更新检测等后台任务通过 `app/state.py` 的 `task_manager` 调度。
- **EH 客户端**：`app/core/eh_client_manager.py` 管理 ExHentai 客户端生命周期；`services/eh/` 实现解析与请求。

## 前端模块划分（`frontend/src/`）

| 目录 | 职责 |
| :--- | :--- |
| `router/` | hash 路由表（`routes.ts`）+ 守卫；旧锚点别名保留 |
| `views/` | 每屏一个目录（browse/online/library/gallery/reader/series/tags/history/downloads/logs/settings/favorites/duplicates/updates/recycle/integrity/archive） |
| `components/` | 设计系统原语 `ui/`、画廊数据视图 `gallery/`、标签 `tags/`、外壳 `shell/`、动作 `actions/` |
| `stores/` | Pinia（auth/settings/ui/library/favorites/downloads/online） |
| `api/` | HTTP client + 全部端点声明（按领域分组） |
| `i18n/` + `locales/` | vue-i18n，构建期预编译（zh/en） |
| `reader/` | 阅读器页源抽象（local / online-direct / online-proxy） |

前端权威说明见 `frontend/README.md`（基础组件、视图切换、tag 规则、API client 契约）；设计 token 见 `frontend/docs/design/DESIGN.md`。

## 数据流（核心链路）

1. **扫描入库**：`scanners/` 扫 `<gid>-标题/` 或压缩包 → 解析 `metadata/` → 写入 `galleries`/`gallery_pages`/`tags` → 缩略图 worker 生成封面。
2. **下载**：`POST /api/downloads` 入队 → `services/download` worker 逐页/官方 Archive 下载 → 落盘 → 入库（`services/library`）→ 通知。
3. **收藏同步**：`services/favorites` 定时检查 → 云端确认后写 `favorite_items` → 按模式入队下载。
4. **阅读**：前端 reader 经 `GET /api/galleries/{id}/pages/{n}` 取本地页；在线模式浏览器直连 H@H（后端只解析 URL），回退走 `eh_online_proxy`。
