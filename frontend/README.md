# GalleryVault Frontend

Vanilla-JS Single-Page Application (hash-routed, no build step, no CDN
dependency) for GalleryVault. Served by nginx on port 8000; nginx reverse-proxies
`/api`, `/login` and `/logout` to the backend (`http://backend:8001`, host port
8001).

[![CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

- `index.html` — SPA entry shell
- `assets/core.js` — routing, auth, HTTP client (`api`), render view hooks
- `assets/state.js` — centralized reactive states, selections, timers, constants
- `assets/utils.js` — utility functions, formatting, pagination, infinite scroll
- `assets/components.js` — UI components (cards, skeletons, status indicators, modal dialogs)
- `assets/events.js` — global event delegations & keyboard shortcuts
- `assets/i18n.js` & `assets/locales/` — on-demand dynamic multilingual loader & packs (EN/中文)
- `assets/views/` — modular views (browse, library, gallery, reader, favorites, downloads, tags, history, settings, logs, updates, duplicates, welcome)
- `assets/app.js` — lightweight bootstrapping entrypoint (29 lines)
- `assets/styles.css` — design tokens, responsive layout, theme
- `nginx.conf` — static serving + proxy config

## Run

The `docker-compose.yml` in the repository root builds/runs this image as
the `frontend` service and publishes it on host port 8000. Standalone:

```bash
docker build -t galleryvault-frontend .
docker run --rm -p 8000:80 galleryvault-frontend
```

Backend must be reachable at `http://backend:8001` (in compose) or adjust
`nginx.conf` `proxy_pass` for local development.

## Documentation

- Full user docs: [GalleryVault Wiki](https://github.com/ResidualBlood/galleryvault/wiki)
