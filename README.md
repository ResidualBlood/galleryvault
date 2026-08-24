# GalleryVault

A private, self-hosted manager for local gallery archives (Ehviewer exports,
CBZ/CBR, plain folders) with optional ExHentai download and metadata sync.

**This repository is the deployment entry point.** It runs the two published
Docker Hub images with one `docker compose up`:

| Service | Image | Host port |
|---------|-------|-----------|
| Frontend (SPA, nginx) | `residualblood/galleryvault-frontend` | **8000** |
| Backend (FastAPI JSON API) | `residualblood/galleryvault-backend` | **8001** |
| PostgreSQL | `postgres:16-alpine` | internal |

Source code lives in two separate repositories:

- Backend: https://github.com/ResidualBlood/galleryvault-backend
- Frontend: https://github.com/ResidualBlood/galleryvault-frontend

## Quick start

```bash
docker compose up -d
```

Open `http://<host>:8000` (the SPA). Login with the **default password
`p1a2s3s4`** and change it in Settings (the SPA prompts you to). The JSON API
is on `http://<host>:8001`.

> The default password only applies on a fresh install (no password hash
> configured yet). Once you change it in Settings it is stored in PostgreSQL
> and survives restarts.

## Data

- **PostgreSQL data** persists in `./db-data` (next to this compose file).
- **Library**: put your galleries under `./library` (mounted at `/library`).
- **Downloads**: downloaded galleries go to `./downloads` (mounted at
  `/downloads`). The backend scans both directories by default.

Add extra volumes in `docker-compose.yml` and a library root in Settings for
more library directories.

## Configuration

All settings (library roots, ExHentai cookies, proxies, downloads, favorites,
Telegram, tag-sync, translation interval, auth) are configured in the **Settings
page** of the SPA and persisted to PostgreSQL — no `.env` or `config.json`
required.

## Building from source

```bash
git clone https://github.com/ResidualBlood/galleryvault-backend
cd galleryvault-backend
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## Docs

- API reference and usage: `galleryvault-backend/docs/`