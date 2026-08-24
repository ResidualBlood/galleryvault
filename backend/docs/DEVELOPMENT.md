# Development Guide

This document explains how GalleryVault is structured. The project is split
into **two independent git repositories**: this backend (JSON API + PostgreSQL)
and the [`galleryvault-frontend`](../frontend) repo (a static SPA served by
nginx). This file covers the backend.

## Architecture overview

```
Browser ── :8000 ──▶ nginx (frontend repo: static SPA, proxies /api,/login,/logout)
                          │
Browser ── :8001 ──▶ FastAPI app (galleryvault/app/main.py)  ──▶ PostgreSQL
                          │
                    /api/* JSON routes (galleryvault.api)
```

- **Frontend** (`galleryvault-frontend` repo) is a build-free vanilla-JS SPA
  served by nginx on port 8000. nginx reverse-proxies `/api`, `/login` and
  `/logout` to the backend service (`http://backend:8001`).
- **Backend** (this repo) is a **pure JSON API** on port 8001 (container
  port 8000): no HTML pages, no static files.
- **Database**: PostgreSQL 16 runs alongside the backend in the same
  `docker-compose.yml`; its data persists in `./db-data` (next to the compose
  file).

Key points:

- **Authentication is cookie-based.** The `authentication` middleware
  (`galleryvault/app/main.py`) returns `401` JSON for unauthenticated `/api/*`
  requests; the SPA detects the `401` and shows the login form. Login is
  performed by `POST /login` (form-encoded) which sets the session cookie, and
  `POST /logout` clears it. `/healthz`, `/login`, `/logout` are exempt.
- **CSRF**: the legacy double-submit CSRF token is only needed for browser HTML
  forms. The SPA only issues `application/json` requests to `/api/*` (excluded
  from the CSRF check), so no CSRF token is required.

## Project layout

```
backend/  (this git repository)
galleryvault/
  app/
    main.py            # FastAPI app, all JSON route handlers
  api/                 # canonical API reference (re-exports handlers + routes)
  auth/                # password hashing + session cookies
  config.py            # Settings model + DB persistence
  db/                  # SQLAlchemy models, repositories, session
  scanners/            # ehviewer / zip / rar / folder scanners + registry
  services/
    downloader.py      # ExHentai download engine (concurrent pages, resume, max_pages)
    eh_client.py       # ExHentai HTML scraper (httpx) + EhClientError/GalleryGoneError
    favorites.py       # favorite-folder monitor + download queue
    ingest.py          # metadata ingestion from scan results
    library.py         # filesystem scanning / expiry
    tag_sync.py        # per-gallery tag & category sync, category backfill
    tag_translation.py # EhTagTranslation database loading + translation lookups
    telegram.py        # TelegramNotifier (async client)
    telegram_bot.py    # long-poll bot for incoming commands
  logging.py
alembic/               # database migrations (0001..0011)
tests/                 # pytest suite
docs/                  # this guide, USAGE.md, API.md
Dockerfile
docker-compose.yml     # frontend (:8000) + backend (:8001) + db (./db-data)
pyproject.toml

frontend/  (separate git repository, sibling directory)
index.html             # SPA shell (hash-routed)
assets/
  app.js               # vanilla-JS SPA (no build step, no CDN dependency)
  styles.css
nginx.conf             # static serving + /api proxy to backend:8000
Dockerfile
```

The frontend is intentionally **build-free**: `app.js` is plain ES2020 and
`styles.css` is plain CSS, loaded directly by the browser. This keeps the
project free of any Node toolchain and works fully offline.

## Running locally (without Docker)

1. Create a virtualenv with Python 3.12 and install:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Start PostgreSQL and export the connection string, e.g.:

   ```bash
   export DATABASE_URL=postgresql+asyncpg://galleryvault:galleryvault@localhost:5432/galleryvault
   export AUTH_SECRET=dev-secret
   export AUTH_PASSWORD_HASH=$(python -c "from galleryvault.auth import hash_password; print(hash_password('changeme'))")
   ```

3. Apply migrations and run the API:

   ```bash
   alembic upgrade head
   uvicorn galleryvault.app.main:app --reload --port 8001
   ```

4. Serve the frontend separately (from the `galleryvault-frontend` repo),
   pointing `/api`, `/login`, `/logout` at `http://localhost:8001`.

## Building the container

```bash
docker-compose build
docker-compose up -d
```

This builds the backend image (this directory) and the frontend image
(`../frontend`), starts PostgreSQL with persistence in `./db-data`, and maps
frontend to host port 8000 and backend to host port 8001.

The container is the **authoritative** runtime: `docker cp` edits to a running
container do **not** persist. Always `docker-compose build` after changing
`galleryvault/` (backend) or `../frontend` (frontend).

## Testing

```bash
# inside the container (or a venv with the same DB configured)
python -m pytest tests -q -p no:cacheprovider
```

`tests/test_auth.py` exercises the auth gate, the JSON API contract, and the
SPA fallback page. `test_scanners.py`, `test_p1_services.py`, and
`test_latest_requirements.py` cover the library/scanning services. The tests
run against a real PostgreSQL (the container's `DATABASE_URL`); the
`db_isolated` autouse fixture stubs the DB-backed auth bootstrap and disables
the background worker loops so they don't interfere with the test event loop.

## Database migrations

Schema changes go through Alembic:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Migrations are applied automatically on container boot (`CMD` runs
`alembic upgrade head` before uvicorn), so `docker compose pull && up -d` is a
complete upgrade. Notable migrations: `0009` added the `category_refreshed_at`
column (one-time category backfill), `0010` merged `other` into `misc` and
moved coordinate-less galleries to `deleted`, and `0011` added
`download_tasks.max_pages` so partial/sample downloads survive the worker.

## Tag translations (标签翻译)

**是后端实现的**，前端只负责按语言切换显示。

- 后端模块 `galleryvault/services/tag_translation.py` 在启动时调用
  `load_translations()` 将翻译库加载到内存 `_TRANSLATIONS`。
- 加载顺序（后者覆盖前者）：
  1. 镜像内捆绑的 `galleryvault/data/tag_translations.json`（约 2.1 MB，来自
     EhTagTranslation / ehsyringe 导出的 `{"data":[{"namespace","data":[{"key","name"}]}]}` 格式）
  2. 用户覆盖文件 `galleryvault/tag_translations.json`（若存在）
  3. 环境变量 `TAG_TRANSLATIONS_FILE` 指向的外部文件（推荐在 Docker 下使用，
     例如挂载宿主机文件）
  4. 显式传入的 `path` 参数（单元测试使用）
- `translate_tag()` / `translated_tag()` 查询内存表，命中则通过
  `clean_display()` 去掉翻译文本里可能嵌套的 markdown 图标语法
  `![alt](https://...webp)`（注射器数据库里有 69 条此类记录，例如
  `![贝合图标](...tribadism.webp)贝合` → `贝合`），并截断至 60 字符。
- API 在三个地方返回中文 `display` 字段：`GET /api/galleries` 每项的 `tags[]`、
  `GET /api/galleries/{id}` 的 `tags[]`、`GET /api/tags/search` 的 `items[]`。
- 前端 `frontend/assets/app.js` 的 `tagText(tag)` 在 `localStorage.gv_lang==='zh'`
  时显示 `tag.display`，否则显示 `tag.name`；命名空间标签
  `NAMESPACE_LABELS_ZH` 同样来自后端常量。

与 **e 站注射器（EhTagTranslation / ehsyringe）同步**：

- **内置自动更新（推荐）**：后端后台任务每
  `TAG_TRANSLATION_UPDATE_INTERVAL_MINUTES`（默认 720，`0` 关闭）解析
  [`EhTagTranslation/Database`](https://github.com/EhTagTranslation/Database)
  最新 release 的 `db.text.json` 资产并热加载（`load_translations(reset=True)`）。
  可在 Settings 里“立即更新”或查看状态。注意 `db.text.json` 内部 `data` 是
  `{name: zh}` 字典、值为 `{name,intro,links}` 对象，`merge_translation_data`
  已兼容该格式与旧版 `{key,name}` 列表 / 扁平映射三种输入。
- **手动挂载（离线环境）**：把下载好的 JSON 放到 `galleryvault/data/tag_translations.json`
  或挂载到 `TAG_TRANSLATIONS_FILE`，重建以捆绑，或通过环境变量热加载。

```bash
# 手动获取最新翻译库
curl -L https://github.com/EhTagTranslation/Database/releases/latest/download/db.text.json \
  -o ./tag_translations.json
# docker-compose.yml 增加：
#   environment:
#     TAG_TRANSLATIONS_FILE: /app/tag_translations.json
#   volumes:
#     - ./tag_translations.json:/app/tag_translations.json:ro
docker-compose up -d app
```

可通过容器日志确认加载：`docker logs exhentai_app_1 | grep "tag translations"`。

## Conventions

- Keep route handlers in `galleryvault/app/main.py`. Each handler is a plain
  `async def`; the `galleryvault/api` package documents them.
- All errors returned to the client are `HTTPException` (or `_db_error` for
  SQLAlchemy failures). Never leak raw exception text – secrets/cookies are
  already scrubbed in `logging.py`.
- Do not commit cookies, `.env`, `TEMP/*`, or `media/`. (There is no longer a
  `config.json`; settings persist in the database.)
