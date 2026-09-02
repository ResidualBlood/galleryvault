# GalleryVault Backend

FastAPI + PostgreSQL JSON API for GalleryVault.

[![CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

- API: `http://<host>:8001/api/*`
- Health: `http://<host>:8001/healthz`
- Login/Logout: `POST /login`, `POST /logout` (form/cookie based)

Run the full stack (frontend :8000, backend :8001, PostgreSQL) with `docker-compose.yml` in the repository root, or run development hot-reload with `docker-compose.dev.yml`.

## Default password

On a fresh install (no `AUTH_PASSWORD_HASH` configured) the built-in default
password is **`p1a2s3s4`**. The SPA prompts you to change it in Settings after
login; once changed it is persisted to PostgreSQL.

## Configuration

All settings live in the *Settings* page (persisted to PostgreSQL); secrets
can be protected with optional at-rest encryption via `ENCRYPTION_KEY`.

## Documentation

- Endpoints: `docs/API.md`
- Architecture / development: `docs/DEVELOPMENT.md`
- Full user docs: [GalleryVault Wiki](https://github.com/ResidualBlood/galleryvault/wiki)
