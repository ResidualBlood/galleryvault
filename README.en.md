# GalleryVault

GalleryVault is a private, self-hosted library manager for local gallery archives. It indexes Ehviewer exports, CBZ/CBR archives and plain image folders into a searchable web library, and can optionally sync tags and metadata from ExHentai, download galleries, monitor favorite folders, and translate every tag. The interface is available in English and Chinese (中文).

[![Backend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)

[中文](README.md) · **English** · [📖 Documentation](https://github.com/ResidualBlood/galleryvault/wiki/Home-EN)

---

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. Run `docker compose up -d` to launch the stack.
2. Open **http://<host>:8000** for the web UI (JSON API at `:8001`).
3. Log in with default password **`p1a2s3s4`** and change it in *Settings*.
4. Put galleries into `./library` (mounted at `/library`) and click *Scan library*.

> To sync metadata or download from ExHentai, configure your account cookies in *Settings → ExHentai*; see the [Wiki Usage Guide](https://github.com/ResidualBlood/galleryvault/wiki/Usage-EN).

## Screenshots

| English UI | Chinese UI |
|------------|------------|
| **Library** | **Gallery library** |
| <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> | <img src="docs/screenshots/library_zh.png" alt="Chinese library UI" width="420"> |
| **Tag cloud** | **Tag cloud** |
| <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> | <img src="docs/screenshots/tags_zh.png" alt="Chinese tag cloud page" width="420"> |
| **Favorites dedupe** | **收藏夹查重** |
| <img src="docs/screenshots/fav_dedupe_en.png" alt="Favorites dedupe page" width="420"> | <img src="docs/screenshots/fav_dedupe_zh.png" alt="Chinese favorites dedupe page" width="420"> |

## Documentation

Full documentation is available on the **[GitHub Wiki](https://github.com/ResidualBlood/galleryvault/wiki)**:

- **[Usage Guide](https://github.com/ResidualBlood/galleryvault/wiki/Usage-EN)** — Browse, search, reader, downloads, favorites & deduplication, PWA & settings
- **[Deployment Guide](https://github.com/ResidualBlood/galleryvault/wiki/Deployment-EN)** — Docker Compose, volume mounts, permissions, encryption at rest, hardening & backups
- **[API & Development](https://github.com/ResidualBlood/galleryvault/wiki/API)** — REST API specifications and [Development guide](https://github.com/ResidualBlood/galleryvault/wiki/Development)

## Acknowledgements

- **Ehviewer_CN_SXJ** ([github.com/xiaojieonly/Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)) — Reference for directory structure and download conventions.
- **EhTagTranslation** ([github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)) — Tag translation database and update mechanism.
- **ehsyringe** ([github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)) — Curation and export format of translation data.

## Disclaimer

ExHentai integration requires your own account cookies. Please use responsibly and respect site rules and rate limits.
