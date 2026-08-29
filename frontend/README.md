# GalleryVault Frontend

Vanilla-JS Single-Page Application (hash-routed, no build step, no CDN
dependency) for GalleryVault. Served by nginx on port 8000; nginx reverse-proxies
`/api`, `/login` and `/logout` to the backend (`http://backend:8001`, host port
8001).

[![CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

- `index.html` — SPA shell
- `assets/app.js` — the app (i18n EN/中文, browse, library, tags, downloads,
  favorites, gallery updates, settings, reader)
- `assets/styles.css` — theme
- `nginx.conf` — static serving + proxy config

## Run

The `docker-compose.yml` in the **galleryvault** repository builds this image as
the `frontend` service and publishes it on host port 8000. Standalone:

```bash
docker build -t galleryvault-frontend .
docker run --rm -p 8000:80 galleryvault-frontend
```

Backend must be reachable at `http://backend:8001` (in compose) or adjust
`nginx.conf` `proxy_pass` for local development.

## Documentation

- Full user docs: [GalleryVault Wiki](https://github.com/ResidualBlood/galleryvault/wiki)
