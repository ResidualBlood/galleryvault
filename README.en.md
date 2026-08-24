# 📚 GalleryVault

> A private, self-hosted library manager for local gallery archives — with
> ExHentai download, tag-sync and translation built in.

GalleryVault indexes **Ehviewer exports, CBZ/CBR archives and plain image
folders** into a searchable web library, and can optionally **sync tags &
metadata from ExHentai**, **download galleries**, **monitor your favorite
folders**, and **translate every tag** — all behind a simple password, with a
polished English/中文 interface.

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

[中文（默认）](README.md) · **English**

---

## Screenshots

| English UI | 中文界面 |
|------------|----------|
| **Library** | **画廊库** |
| <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> | <img src="docs/screenshots/library_zh.png" alt="画廊库界面" width="420"> |
| **Tag cloud** | **标签云** |
| <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> | <img src="docs/screenshots/tags_zh.png" alt="标签云页面" width="420"> |

---

## ✨ Features

| | |
|---|---|
| 🗂️ **Local gallery library** | Scan Ehviewer export directories, CBZ/CBR files and plain image folders into a persistent, searchable index (PostgreSQL). |
| 🏷️ **Tag cloud & search** | Namespaced tags (Artist / Character / Parody / Group / Language / Category / Misc…), a weighted tag cloud, and instant tag autocomplete. |
| 🌐 **Tag translations** | Pulls the latest EhTagTranslation release — Chinese input reverse-matches the translation table, so typing 巨乳 suggests `big breasts`. |
| 🆎 **Bilingual UI** | Full English and 中文 interface, switchable any time; tags render their translations in the 中文 view. |
| 🌠 **ExHentai integration** | Login with your own cookies (表站 or 里站) to fetch metadata, categories and tags for every gallery. |
| ⬇️ **Download manager** | Concurrent page downloads like Ehviewer, live progress bars, resumable retries (only missing pages), partial/sample downloads (`max_pages`), cancel & bulk retry. |
| ⭐ **Favorites monitor** | Watches your ten ExHentai favorite folders and auto-downloads anything you don't have yet — on a schedule or on demand. |
| 📖 **Reader & history** | Streams one page at a time, saves your reading position, and keeps a browsable history. |
| 🔔 **Telegram alerts** | Get notified on download success/failure, scan completion, and favorite sync. |
| 🗑️ **Orphan cleanup** | Galleries deleted from ExHentai (or with no usable coordinates) are grouped under **Deleted** automatically. |
| 🔒 **Private & simple** | Single-password auth with persistent sessions, secure settings storage, and an optional "no login" mode. |
| 🐳 **One-command deploy** | Two published Docker Hub images + PostgreSQL run with a single `docker compose up`. |

---

## Quick start

```bash
git clone https://github.com/ResidualBlood/galleryvault
cd galleryvault
docker compose up -d
```

1. Open **http://\<host\>:8000** — the web UI.
2. Log in with the default password **`p1a2s3s4`** and change it in *Settings*
   (a banner reminds you until you do).
3. Put your galleries in `./library` (mounted at `/library`), hit **Scan library**,
   and start reading.

> The JSON API is available on **http://\<host\>:8001**.

---

## Data & volumes

| Path | Purpose |
|------|---------|
| `./db-data` | PostgreSQL data (index, settings, history) — survives container recreation |
| `./library` | Your gallery archives (mounted at `/library`, scanned by default) |
| `./downloads` | Galleries downloaded from ExHentai (mounted at `/downloads`) |

Add more library directories in *Settings → Library roots* (each path must be
mounted into the container in `docker-compose.yml`).

---

## Configuration

There is **no `config.json` and no `.env`** to hand-edit. Every setting lives
in the *Settings* page and is persisted to PostgreSQL:

- **Library roots** — one filesystem path per line.
- **Account** — change password, toggle *Require login*.
- **ExHentai** — base URL (表站/里站), `ipb_member_id` / `ipb_pass_hash` /
  `igneous` cookies, with a **Test login** button. Cookies are never echoed back.
- **Proxy** — HTTP or SOCKS5.
- **Downloads** — root, concurrency, image quality, H@H network, `max_pages`.
- **Tag sync** — automatic sync after scans/startup, interval, concurrency.
- **Favorites** — auto-download toggle and polling interval.
- **Telegram** — bot token, chat IDs, allowed user IDs, **send test message**.
- **Translation** — auto-update interval and **Update now** button.

Secrets (cookies, bot token, password hash) are stored in PostgreSQL and never
exposed through the API.

---

## Architecture

The project is split into two source repositories that publish the Docker
images used here:

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

The frontend is a dependency-free vanilla-JS single-page app (no build step,
no CDN); the backend runs Alembic migrations on boot, so upgrades are a single
`docker compose pull && docker compose up -d`.

### Building from source

```bash
git clone https://github.com/ResidualBlood/galleryvault-backend
cd galleryvault-backend
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

---

## Usage highlights

- **Library** (`#/library`) — search by title, filter by category, page-size
  selector (5…500), multi-select delete (files on disk optional), tag-based
  autocomplete filtering.
- **Tags** (`#/tags`) — namespace pills, weighted tag cloud, usage counts, and
  per-tag drill-down into the library.
- **Gallery** (`#/gallery/<id>`) — metadata, translated tags, page thumbnails,
  **Read now**, **Sync tags**.
- **Reader** (`#/reader/<id>/<page>`) — arrow-key navigation with auto-saved
  reading position.
- **Downloads** (`#/downloads`) — live progress, cancel/retry, bulk operations.
- **Favorites** (`#/favorites`) — the ten favorite folders with modes and
  scheduling.

---

## Documentation

- [API reference](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/API.md)
- [Usage guide](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/USAGE.md)
- [Development notes](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/DEVELOPMENT.md)

---

## Disclaimer

Use responsibly. ExHentai integration requires **your own** account cookies and
should respect the site's rules and rate limits.