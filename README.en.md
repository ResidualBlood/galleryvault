# GalleryVault

GalleryVault is a private, self-hosted library manager for local gallery archives. It indexes Ehviewer exports, CBZ/CBR archives and plain image folders into a searchable web library, and can optionally sync tags and metadata from ExHentai, download galleries, monitor favorite folders, and translate every tag. The interface is available in English and Chinese (中文).

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

[中文](README.md) · **English**

---

## Features

- **Local gallery library** — Scan Ehviewer export directories, CBZ/CBR files and plain image folders into a persistent, searchable index (PostgreSQL).
- **Tag cloud and search** — Namespaced tags (artist, character, parody, group, language, category, misc, …), a frequency-weighted tag cloud, and instant tag autocomplete.
- **Tag translations** — Pulls the latest EhTagTranslation database; Chinese input reverse-matches the translation table (typing 巨乳 suggests `big breasts`).
- **Bilingual interface** — Full English and Chinese interface, switchable at any time; tags render their translations in the Chinese view.
- **ExHentai integration** — Use your own cookies (e-hentai.org or exhentai.org) to fetch metadata, categories and tags for every gallery.
- **Download manager** — Ehviewer-style concurrent page downloads, live progress, resumable retries (missing pages only), partial downloads (`max_pages`), cancel and bulk retry.
- **Favorites monitor** — Watches the ten ExHentai favorite folders and auto-downloads galleries you do not have yet (scheduled or on demand); **Check all folders** runs them all at once.
- **Favorites management** — Each folder gets its own gallery grid (checkboxes, bulk download / remove from favorites, inline cloud covers), a one-click Unfavorite plus folder badges on gallery detail pages, and a **duplicate scan** that groups the same work across versions (DL, uncensored, language re-uploads) for bulk unfavoriting or deleting local copies — with false-positive **ignore/restore** and pagination.
- **Metadata cache & auto-sync** — Folder checks batch every favorited gallery's metadata (tags, category, posted date, size) into a database cache via the gdata API; galleries scanned onto disk reuse it with no extra ExHentai fetch, and fresh metadata is applied to on-disk galleries automatically after every check.
- **Reader and history** — Streams one page at a time with keyboard/space/click paging, preloads the next three pages, advances to the next gallery after the last page, saves your reading position, and keeps a browsable history.
- **Telegram notifications** — Get notified on download success/failure, scan completion, and favorite sync.
- **Orphan cleanup** — Galleries deleted from ExHentai (or without usable coordinates) are automatically grouped under the Deleted category.
- **Security and privacy** — Single-password auth (PBKDF2-SHA256, 310k iterations) with persistent sessions, login rate limiting against brute force, cross-origin checks and an ExHentai domain whitelist, secure settings storage, and an optional no-login mode.
- **One-command deployment** — Two published Docker Hub images plus PostgreSQL run with a single `docker compose up`.

## Screenshots

| English UI | Chinese UI |
|------------|------------|
| **Library** | **Gallery library** |
| <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> | <img src="docs/screenshots/library_zh.png" alt="Chinese library UI" width="420"> |
| **Tag cloud** | **Tag cloud** |
| <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> | <img src="docs/screenshots/tags_zh.png" alt="Chinese tag cloud page" width="420"> |

## Quick start

```bash
git clone https://github.com/ResidualBlood/galleryvault
cd galleryvault
docker compose up -d
```

1. Open **http://\<host\>:8000** — the web UI.
2. Log in with the default password **`p1a2s3s4`** and change it in *Settings* (a banner reminds you until you do).
3. **Recommended: configure your ExHentai cookies and run *Favorites → Check all folders* once before scanning the library.** The favorites monitor batches every favorited gallery's metadata (tags, category, posted date, size) into a database cache via the gdata API; galleries scanned onto disk that the monitor has already seen then reuse that cache directly — no per-gallery ExHentai fetch for tag sync — so scanning and tag sync are much faster.
4. Put your galleries in `./library` (mounted at `/library`), hit *Scan library*, and start reading.

> The JSON API is available at **http://\<host\>:8001**.

## Data and volumes

| Path | Purpose |
|------|---------|
| `./db-data` | PostgreSQL data (index, settings, history) — survives container recreation |
| `./library` | **Read-only library**: your existing archives (Ehviewer exports, CBZ/CBR), mounted at `/library`. New downloads never land here |
| `./downloads` | **Download directory**: galleries downloaded from ExHentai, mounted at `/downloads`, scanned automatically |
| `./cache` | **Thumbnail cache** (generated), mounted at `/gv-cache`; never written into the galleries |

The library roots and the download root are configured separately in *Settings* (`library_roots`, read-only, one path per line) and `download_root` (download target); the download directory is always scanned. Additional library paths must be mounted into the container in `docker-compose.yml`.

## Configuration

All settings are configured in the *Settings* page and persisted to PostgreSQL — there is no `config.json` or `.env` to hand-edit:

- **Library roots** — one filesystem path per line.
- **Account** — change password, toggle *Require login*.
- **ExHentai** — base URL (e-hentai.org / exhentai.org), `ipb_member_id` / `ipb_pass_hash` / `igneous` cookies, with a *Test login* button. Cookies are never echoed back.
- **Proxy** — HTTP or SOCKS5.
- **Downloads** — root directory, concurrency, image quality, H@H network, `max_pages`.
- **Tag sync** — automatic sync after scans/startup, interval and concurrency.
- **Favorites** — auto-download toggle and polling interval.
- **Telegram** — bot token, chat IDs, allowed user IDs, *Send test message*.
- **Translation** — auto-update interval and *Update now* button.

Secrets (cookies, bot token, password hash) are stored in PostgreSQL and never exposed through the API.

## Architecture

The project is split into two source repositories that publish the Docker images used here:

```
┌────────────┐   :8000   ┌──────────────────────┐   :8001   ┌────────────────┐
│  Browser   │ ────────▶ │ nginx SPA (vanilla JS)│ ────────▶ │ FastAPI backend │ ─▶ PostgreSQL
└────────────┘           │  /api,/login,/logout  │           └────────────────┘
                         └──────────────────────┘
```

| Component | Repository | Docker image | Host port |
|-----------|------------|--------------|-----------|
| Frontend (nginx SPA) | [galleryvault-frontend](https://github.com/ResidualBlood/galleryvault-frontend) | `residualblood/galleryvault-frontend` | **8000** |
| Backend (FastAPI + asyncpg) | [galleryvault-backend](https://github.com/ResidualBlood/galleryvault-backend) | `residualblood/galleryvault-backend` | **8001** |
| Database | — | `postgres:16-alpine` | internal |

The frontend is a dependency-free vanilla-JavaScript single-page app (no build step, no CDN). The backend runs Alembic migrations automatically on boot, so upgrading is a single `docker compose pull && docker compose up -d`.

### Building from source

```bash
git clone https://github.com/ResidualBlood/galleryvault-backend
cd galleryvault-backend
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## Acknowledgements

Gallery format compatibility and translation features build on the following open-source projects:

- **Ehviewer_CN_SXJ** — the Chinese fork of Ehviewer ([github.com/xiaojieonly/Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)). Its export directory structure and naming conventions (`<gid>-<title>`, `.ehviewer` metadata files, `.thumb` thumbnails), concurrent page download and resume behavior, and Chinese tag-translation reverse lookup are the reference for this project.
- **EhTagTranslation** — tag translation database and update mechanism ([github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)).
- **ehsyringe** — curation and export format of the translation data.

The backend is built on the following open-source components:

- **FastAPI**, **Starlette**, **Uvicorn** — web framework and ASGI server
- **SQLAlchemy**, **asyncpg**, **Alembic** — database ORM, driver and migrations
- **httpx** — async HTTP client
- **Pydantic** — data validation and configuration

Infrastructure: **PostgreSQL**, **nginx**, **Docker**.

## Public deployment checklist

Before exposing an instance to the public internet:

1. **Use a strong password.** The default `p1a2s3s4` is for first login only — change it in Settings. Login is rate-limited out of the box (10 attempts / 60 s per IP), and nginx throttles `/login` (10 r/min) and `/api` (30 r/s) per client IP.
2. **Enable TLS.** Terminate HTTPS at a reverse proxy / Caddy in front of nginx and set `AUTH_COOKIE_SECURE=true`; otherwise the password and session cookie travel in plaintext. Add HSTS once HTTPS is live.
3. **Only expose port 8000.** The compose file binds the backend API to `127.0.0.1:8001` (loopback only) — keep it that way and route all API traffic through the nginx frontend.
4. **Built-in defenses (no setup needed):** login rate limiting, cross-origin checks on state-changing `/api` calls, an `exhentai_base_url` whitelist (exhentai.org / e-hentai.org only), `HttpOnly + SameSite=Lax` session cookies, and PBKDF2-SHA256 (310k iterations) password hashing.
5. **Recommended hardening:** run containers as non-root, give PostgreSQL its own strong password, and avoid mounting system-critical paths as library/downloads roots.

## Documentation

- [API reference](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/API.md)
- [Usage guide](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/USAGE.md)
- [Development notes](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/DEVELOPMENT.md)

## Disclaimer

ExHentai integration requires your own account cookies. Please use it responsibly and respect the site's rules and rate limits.