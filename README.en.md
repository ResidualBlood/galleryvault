# GalleryVault

GalleryVault is a private, self-hosted library manager for local gallery archives. It indexes Ehviewer exports, CBZ/CBR archives and plain image folders into a searchable web library, and can optionally sync tags and metadata from ExHentai, download galleries, monitor favorite folders, and translate every tag. The interface is available in English and Chinese (中文).

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)

[中文](README.md) · **English** · [📖 Online docs](https://github.com/ResidualBlood/galleryvault/wiki)

---

## Features

- **Local gallery library** — scans Ehviewer exports, CBZ/CBR archives and
  plain image folders into a searchable local index (PostgreSQL);
  auto-dedupes same-gid copies across scan roots.
- **Search & tags** — stackable multi-tag (AND) filters, mixed tag+text
  queries, Chinese tag translations with reverse lookup, bilingual UI.
- **ExHentai integration** — sync metadata and tags with your own cookies;
  favorites monitoring with auto-download and dedupe; auto-update re-uploaded
  galleries; one-click *Open on ExHentai*.
- **Download manager** — Ehviewer-style concurrent downloads, resumable
  retries, self-healing failures, instant ingestion on completion; ExHentai
  archive (zip) downloads that trade GP for speed with resume without
  re-charging; Telegram notifications and bot commands.
- **Reader & UI** — streaming reader (fullscreen, auto-advance), reading
  history, activity log, first-run wizard.
- **Security & operations** — PBKDF2 auth, optional encryption at rest
  (AES-256-GCM), non-root runtime; one-command deploy and one-click backup.

## Screenshots

| English UI | Chinese UI |
|------------|------------|
| **Library** | **Gallery library** |
| <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> | <img src="docs/screenshots/library_zh.png" alt="Chinese library UI" width="420"> |
| **Tag cloud** | **Tag cloud** |
| <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> | <img src="docs/screenshots/tags_zh.png" alt="Chinese tag cloud page" width="420"> |
| **Favorites dedupe** | **收藏夹查重** |
| <img src="docs/screenshots/fav_dedupe_en.png" alt="Favorites dedupe page" width="420"> | <img src="docs/screenshots/fav_dedupe_zh.png" alt="Chinese favorites dedupe page" width="420"> |

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. Open **http://\<host\>:8000** — the web UI.
2. Log in with the default password **`p1a2s3s4`** and change it in *Settings*.
3. (Optional) Configure your ExHentai cookies and run *Favorites → Check all folders* once — the cached metadata makes scanning much faster.
4. Put your galleries in `./library` (mounted at `/library`), hit *Scan library*, and start reading.

> On first start Docker creates the `./library`, `./downloads`, `./cache` and
> `./db-data` directories automatically; the downloaded `docker-compose.yml`
> can be customized (ports, volume mounts, `ENCRYPTION_KEY`, …).

> The JSON API is available at **http://\<host\>:8001**.

### Obtaining the ExHentai cookies (`ipb_member_id` / `ipb_pass_hash` / `igneous`)

1. Log in to **e-hentai.org** in your browser (an e-hentai account is required), press `F12` → **Application → Storage → Cookies**, and copy **`ipb_member_id`** and **`ipb_pass_hash`** from `https://e-hentai.org`.
2. To also access **exhentai.org** (the "里站"), copy **`igneous`** from the Cookies of `https://exhentai.org` — this cookie only exists for accounts granted exhentai access; skip it if you only use the public mirror.
3. Enter the three values in *Settings → ExHentai* (or the first-run wizard) and verify with *Test login*; cookies are stored encrypted and never echoed back.

### Recommended workflow

Cache your favorite metadata first (*watch only* + *Check all folders*), scan
the library, dedupe, download the backlog with *force*, then switch back to
incremental for automatic follow-ups. Full steps in the
[Wiki → Usage guide](https://github.com/ResidualBlood/galleryvault/wiki/Usage).

### Scope

- **Natively supported** are download directories from the Ehviewer family
  (`.ehviewer`, fully compatible across the main forks) and
  [JHenTai](https://github.com/jiangtian616/JHenTai) (`metadata`); scanning
  restores the full gallery identity. CBZ/CBR archives and plain image folders
  without `.ehviewer` are supported with reduced fidelity (galleries without a
  gid can be browsed but take no part in downloads/dedupe). The full
  compatibility list lives on the
  [Wiki → Home](https://github.com/ResidualBlood/galleryvault/wiki/Home).
- The downloader additionally writes a `.galleryvault.json` sidecar
  (category/title/tags), readable on scan and rebuild.

## Data and volumes

| Path | Purpose |
|------|---------|
| `./db-data` | PostgreSQL data (index, settings, history) — survives container recreation |
| `./library` | **Library**: your existing archives, mounted at `/library`. New downloads never land here; deleting a gallery removes its files here when the mount is writable |
| `./downloads` | **Download directory**: galleries downloaded from ExHentai, mounted at `/downloads`, scanned automatically |
| `./cache` | **Thumbnail cache** (generated), mounted at `/gv-cache` |

Library roots (one path per line) and the download root are configured separately in *Settings*; mounting other Ehviewer download folders as **scan-only libraries** is described in the [Wiki → Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment).

> **Permissions**: the backend container runs as the `app` user (uid **10001**). Before mounting an existing directory or adding archives, make sure the host directory is **readable** by uid 10001 (writable too for gallery deletion): run `chown -R 10001:10001 ./library ./downloads` before the first `docker compose up`. `./cache` is handled automatically; **`./db-data` belongs to postgres (uid 999) — never chown it**.

## Upgrading

```bash
docker compose pull
docker compose up -d
```

Database migrations (Alembic) run automatically when the backend starts. Images
use the `:latest` tag, so `pull` fetches new releases.

> Do **not** overwrite your local `docker-compose.yml` with
> `curl -o docker-compose.yml` — it likely contains your customizations (ports,
> volume mounts, `ENCRYPTION_KEY`, …). If you need a newer compose template,
> back it up first and merge the changes by hand.

## Security

The default password `p1a2s3s4` is for first login only — change it before exposing the instance publicly. The backend API binds `127.0.0.1:8001` by default; optional **encryption at rest** (`ENCRYPTION_KEY`, AES-256-GCM) protects cookies / token / password hashes — keep the key separate from the database backup. The public-deployment checklist, TLS and lost-key recovery are in [Wiki → Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) and [Wiki → Encryption](https://github.com/ResidualBlood/galleryvault/wiki/Encryption).

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

The frontend is a dependency-free vanilla-JavaScript SPA (no build step, no CDN). The backend runs Alembic migrations automatically on boot, so upgrading is a single `docker compose pull && docker compose up -d`.

## Documentation

Full docs live on the **[📖 Wiki](https://github.com/ResidualBlood/galleryvault/wiki)**:

- [Deployment](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) — compose, volumes, scan-only libraries, hardening, TLS, upgrades
- [Usage guide](https://github.com/ResidualBlood/galleryvault/wiki/Usage) — browse, reader, tags, downloads, favorites, logs, settings
- [Backup & restore](https://github.com/ResidualBlood/galleryvault/wiki/Backup)
- [Encryption at rest](https://github.com/ResidualBlood/galleryvault/wiki/Encryption) — ENCRYPTION_KEY and lost-key recovery
- [API reference](https://github.com/ResidualBlood/galleryvault/wiki/API)
- [Development](https://github.com/ResidualBlood/galleryvault/wiki/Development)
- [FAQ](https://github.com/ResidualBlood/galleryvault/wiki/FAQ)
- [Screenshots](https://github.com/ResidualBlood/galleryvault/wiki/Screenshots) — overview of the main UI pages (EN & 中文)

Product discussions & feedback: [Discussions](https://github.com/ResidualBlood/galleryvault/discussions)

## Acknowledgements

- **Ehviewer_CN_SXJ** ([github.com/xiaojieonly/Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)) — reference for the export directory structure and naming conventions, concurrent page download and resume, and Chinese tag-translation reverse lookup.
- **EhTagTranslation** ([github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)) — tag translation database and update mechanism.
- **ehsyringe** — curation and export format of the translation data.

Backend built on **FastAPI / Starlette / Uvicorn**, **SQLAlchemy / asyncpg / Alembic**, **httpx**, **Pydantic**; infrastructure is **PostgreSQL, nginx, Docker**.

## Disclaimer

ExHentai integration requires your own account cookies. Please use it responsibly and respect the site's rules and rate limits.
