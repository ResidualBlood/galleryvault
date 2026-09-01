# Development Guide

This document explains how GalleryVault is structured. The project is split
into **two independent git repositories**: this backend (JSON API + PostgreSQL)
and the [`galleryvault-frontend`](../frontend) repo (a static SPA served by
nginx). This file covers the backend.

## Architecture overview

```
Browser ── :8000 ──▶ nginx (frontend repo: static SPA, proxies /api,/login,/logout)
                          │
Browser ── :8001 ──▶ FastAPI app (galleryvault/app/main.py + app/routers)  ──▶ PostgreSQL
                          │
                    /api/* JSON routes (galleryvault.app.routers)
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
  `POST /logout` clears it. `/healthz`, `/metrics`, `/login`, `/logout` are
  exempt.
- **CSRF**: the legacy double-submit CSRF token is only needed for browser HTML
  forms. The SPA only issues `application/json` requests to `/api/*` (excluded
  from the CSRF check), so no CSRF token is required.
- **Observability**: `GET /metrics` (exempt from auth) exposes Prometheus-style
  counters (requests, download/scan/tag-sync activity); every request carries a
  `X-Request-ID` correlation header (echoed in responses and structured logs),
  so a failing request can be traced across the nginx / backend / DB boundary.
- **Favorites skip heuristic**: `FAVORITES_SKIP_LIMIT` (default 5) — after five
  consecutive checks report an unchanged cloud folder count, the full re-scan
  is skipped (count-only checks continue); the first changed count re-enables
  full checks.

## Project layout

```
backend/  (this git repository)
galleryvault/
  app/
    main.py            # FastAPI assembly: lifespan, middleware, shared task state,
                       #   background workers, auth routes
    routers/           # route handlers split by domain
      core.py tasks.py settings.py downloads.py favorites.py galleries.py tags.py
  api/                 # package note; authoritative reference is docs/API.md
  auth/                # password hashing + session cookies
  config.py            # Settings model + DB persistence
  db/                  # SQLAlchemy models, repositories, session
  logging.py           # structured log formatter
  observability.py     # request-id middleware + /metrics counters
  secrets.py           # at-rest encryption (ENCRYPTION_KEY)
  scanners/            # ehviewer / zip / rar / folder scanners + registry
  services/
    downloader.py      # ExHentai download engine (concurrent pages, resume, max_pages, cancel)
    eh_client.py       # ExHentai HTML scraper (httpx) + GalleryGoneError + favorites paging/sizes
    favorites.py       # favorite-folder monitor + download queue (check-only when disabled)
    ingest.py          # metadata ingestion from scan results
    library.py         # filesystem scanning / expiry
    tag_sync.py        # per-gallery tag & category sync, category backfill
    tag_translation.py # EhTagTranslation database loading + translation lookups
    telegram.py        # TelegramNotifier (async client)
    telegram_bot.py    # long-poll bot for incoming commands
    thumbnails.py      # static JPEG thumbnail generation + on-disk cache
alembic/               # database migrations (0001..0014)
tests/                 # pytest suite
docs/                  # this guide, API.md
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
the background worker loops (including `_thumbnail_worker_loop`) so they
don't interfere with the test event loop.

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
moved coordinate-less galleries to `deleted`, `0011` added
`download_tasks.max_pages` so partial/sample downloads survive the worker,
`0012` added `favorite_items.file_size` for exact cloud-size estimates,
`0015` added pg_trgm title indexes, `0018` added `favorite_items.thumb`
(cover URLs captured from the favorites listing), `0021` added the
`background_jobs` table backing the thumbnail / tag-sync queues, and `0025`
added `gallery_metadata` versioning columns (`parent_gid`, `newer_gid`,
`is_replaced`) for multi-chapter update tracking.

## Background job queues

Thumbnail generation and tag sync use a **persistent queue** (`background_jobs`,
one row per `(job_type, gallery_id)` with a `pending`/`claimed` status) instead
of an in-memory `asyncio.Queue`, so queued work survives a restart and a future
multi-process deployment can claim safely. `BackgroundJobsRepository` exposes
`enqueue`/`enqueue_many` (idempotent via a unique constraint),
`claim` (`FOR UPDATE SKIP LOCKED` + a `lease_until` that expires a row back to
`pending` when the claiming worker died — recovered at worker start by
`mark_stale`), `requeue` (retry, bumping `attempts`; `next_attempt_at` defers),
`complete` (deletes the row) and `clear` (used by the cancel API). Tag-sync
network-failure retries count down against the persisted `attempts` column, so
a restart does not reset a poisoned gallery's retry budget.

Related throughput improvements: download progress is batched to at most one
`download_tasks` write every 20 pages / 5 s instead of once per page, the
Chinese tag autocomplete (`search_zh`) and translation-table rebuilds run off
the event loop, and the library scan's heavy work already runs in the
threadpool via `run_in_threadpool`.

## Thumbnails

`services/thumbnails.py` renders static JPEG thumbnails (max 240px wide) into
a dedicated cache dir (`thumbnail_cache_dir`, default `/gv-cache/thumbs`, a
volume mounted at `/gv-cache`) keyed by gallery id + page index. Animated
formats become static first frames. Nothing is ever written into the gallery
archives. A background worker (`_thumbnail_worker_loop`, 4 concurrent) claims
galleries from `background_jobs` (seeded at boot and after each download) and
generates every missing page; progress is exposed via
`GET /api/thumbs/status`. Gallery cover art and the detail-page thumbnail grid
load `/api/galleries/{id}/thumb/{page}` instead of the full-size page.

## Favorites

- `fetch_favorites` walks ExHentai's `next` cursor (not `page=`), calling a
  `progress` callback with the walked count; per-folder check progress lives in
  `favorites_check_state` (see `GET /api/favorites/check-status`).
- A **disabled** folder runs check-only (`monitor_only`): it records items and
  fetches sizes but never downloads. Only enabled folders download.
- `remember_many` upserts in 500-row batches (a single INSERT for a folder with
  thousands of galleries exceeds the asyncpg parameter limit). A successful
  full check also prunes `favorite_items` rows for gids no longer in the cloud
  folder (unfavorited / expunged), keeping the recorded set in sync so the
  scheduled "cloud count unchanged" skip keeps working.
- `cloud_size` = local real size + fetched sizes of missing galleries
  (`favorite_items.file_size`, via `_favorite_size_sync`) + an average estimate
  for the unfetched tail.

## Building & deploying

This is a local deployment: build the two images locally (fast, dependency
layer is cached), then `docker compose up -d` — no need to wait for CI.

```bash
cd /mnt/GalleryVault/backend && docker build -t residualblood/galleryvault-backend:latest .
cd /mnt/GalleryVault/frontend && docker build -t residualblood/galleryvault-frontend:latest .
cd /mnt/ehviewer && docker compose up -d backend frontend
```

`git push` afterwards runs CI (test + lint + build-push to Docker Hub) for
other machines. Runtime containers are authoritative: `docker cp` edits do not
persist across recreation.

## Tag translations

**Implemented in the backend**; the frontend only switches the display by
language.

- The backend module `galleryvault/services/tag_translation.py` calls
  `load_translations()` at startup to load the translation database into the
  in-memory `_TRANSLATIONS` dict.
- Load order (later sources override earlier ones):
  1. The bundled `galleryvault/data/tag_translations.json` (~2.1 MB, exported
     from EhTagTranslation / ehsyringe in the
     `{"data":[{"namespace","data":[{"key","name"}]}]}` format).
  2. A user override file `galleryvault/tag_translations.json` (if present).
  3. An external file pointed to by the `TAG_TRANSLATIONS_FILE` environment
     variable (recommended under Docker, e.g. by mounting a host file).
  4. An explicit `path` argument (used by the unit tests).
- `translate_tag()` / `translated_tag()` query the in-memory table; on a hit,
  `clean_display()` strips any nested markdown icon syntax
  `![alt](https://...webp)` the translation database may contain (69 such
  records, e.g. `![贝合图标](...tribadism.webp)贝合` → `贝合`) and truncates
  the result to 60 characters.
- The API returns Chinese `display` fields in three places: `GET /api/galleries`
  per-item `tags[]`, `GET /api/galleries/{id}` `tags[]`, and
  `GET /api/tags/search` `items[]`.
- The frontend `frontend/assets/app.js` `tagText(tag)` shows `tag.display`
  when `localStorage.gv_lang==='zh'` and `tag.name` otherwise; the namespace
  labels `NAMESPACE_LABELS_ZH` also come from the backend constants.

**Syncing with EhTagTranslation / ehsyringe**:

- **Built-in auto-update (recommended)**: a backend background task parses the
  latest `db.text.json` asset from the
  [`EhTagTranslation/Database`](https://github.com/EhTagTranslation/Database)
  release every `TAG_TRANSLATION_UPDATE_INTERVAL_MINUTES` (default 720, `0`
  disables it) and hot-reloads it (`load_translations(reset=True)`). You can
  trigger it manually with *Update now* in Settings or check its status there.
  Note that `db.text.json`'s `data` is a `{name: zh}` dict whose values are
  `{name,intro,links}` objects; `merge_translation_data` is compatible with
  that format and with the older `{key,name}` list / flat mapping as well.
- **Manual mount (offline environments)**: put the downloaded JSON in
  `galleryvault/data/tag_translations.json` or mount it at
  `TAG_TRANSLATIONS_FILE`; rebuild to bundle it, or hot-load it via the env var.

```bash
# fetch the latest translation database manually
curl -L https://github.com/EhTagTranslation/Database/releases/latest/download/db.text.json \
  -o ./tag_translations.json
# docker-compose.yml:
#   environment:
#     TAG_TRANSLATIONS_FILE: /app/tag_translations.json
#   volumes:
#     - ./tag_translations.json:/app/tag_translations.json:ro
docker-compose up -d app
```

You can confirm loading in the container logs:
`docker logs galleryvault-backend | grep "tag translations"`.

## Conventions

- Keep route handlers in `galleryvault/app/routers/` (one module per domain).
  Handlers reference the shared state / helpers on `galleryvault.app.main`
  via `main.X` at call time — that keeps `monkeypatch.setattr(main, ...)` in
  the tests working. Each handler is a plain `async def`.
- All errors returned to the client are `HTTPException` (or `_db_error` for
  SQLAlchemy failures). Never leak raw exception text – secrets/cookies are
  already scrubbed in `logging.py`.
- Do not commit cookies, `.env`, `TEMP/*`, or `media/`. (There is no longer a
  `config.json`; settings persist in the database.)
