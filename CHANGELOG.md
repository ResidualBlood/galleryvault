# Changelog

All notable changes to GalleryVault are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-08-26

### Added

- First-run welcome wizard (`#/welcome`): guided change-password → ExHentai
  cookies → fill-the-library steps, shown while the default password is in use.
  New endpoint `GET /api/onboarding/status`.
- `POST /api/favorites/download-selected`: batch-enqueue downloads for selected
  favorite gids straight from the database (the SPA no longer pages through the
  whole folder).
- Official GitHub Wiki as the documentation site, with a bilingual (EN/中文)
  sidebar and an auto-synced OpenAPI schema.

### Changed

- **Favorites reads are database-first.** After a favorites check warms the
  `gallery_metadata` cache (and cover files land on disk), browsing a folder,
  viewing ignored duplicates and the duplicate-scan enrichment talk to the
  database only — ExHentai is only contacted for gids that were never cached.
- Tag sync now **waits for a running favorites check**: galleries whose
  metadata cache entry isn't populated yet are re-queued and retried (bounded,
  so non-favorites galleries still sync) instead of doing a redundant
  one-by-one ExHentai fetch that the gdata batch is about to cover.
- Remote covers fall back to the on-disk cache even when no thumb URL is
  available, so DB-cached galleries keep their covers without a fetch.

### Fixed

- Remote covers (and thumbnails) failed to cache for the unprivileged app user:
  legacy root-owned `/gv-cache` subdirectories were not writable, so ExHentai
  cover downloads were silently swallowed and cloud galleries showed no cover.
  The entrypoint now chowns the cache tree recursively and cover write errors
  are logged instead of swallowed.

## [1.0.0] - 2026-08-26

First tagged release. GalleryVault is a feature-complete, self-hosted local
gallery library manager with ExHentai integration.

### Added

- Local gallery library: scan Ehviewer export directories, CBZ/CBR archives and
  plain image folders into a persistent, searchable PostgreSQL index.
- Namespaced tag system with a frequency-weighted tag cloud and instant tag
  autocomplete.
- Tag translation via the EhTagTranslation database, including reverse matching
  from Chinese input (typing 巨乳 suggests `big breasts`).
- Full English / Chinese bilingual UI; translations shown for tags in the
  Chinese view.
- ExHentai integration: fetch metadata, categories and tags using your own
  cookies (`ipb_member_id` / `ipb_pass_hash` / `igneous`), HTTP or SOCKS5 proxy.
- Download manager: Ehviewer-style concurrent page downloads, live progress,
  resumable retries, partial downloads (`max_pages`), cancel and bulk retry.
- Favorites monitor: watches the ten ExHentai favorite folders and
  auto-downloads missing galleries (scheduled or on demand), plus per-folder
  grids, duplicate scan with ignore/restore, and metadata caching via the gdata
  API that is reused during library scans.
- Reader with streaming page loads, keyboard/space/click paging, preloading,
  auto-advance to the next gallery and saved reading position; browsable history.
- Activity log page aggregating background tasks (scan, tag sync, thumbnail
  generation, favorites metadata) with running/finished sections.
- Telegram notifications for downloads, scans and favorite sync.
- One-command deployment: two multi-arch (amd64/arm64) Docker Hub images plus
  PostgreSQL with a single `docker compose up`.
- Security: PBKDF2-SHA256 auth with persistent sessions, login rate limiting
  keyed on the real client IP, cross-origin checks, ExHentai domain whitelist,
  optional non-root runtime, and optional at-rest encryption (`ENCRYPTION_KEY`,
  AES-256-GCM) protecting cookies / bot token / password hashes with automatic
  plaintext migration on startup.
- Documentation site as a GitHub Wiki (deployment, usage, backup, encryption,
  API reference, development, FAQ), kept in sync with the backend docs.

[Unreleased]: https://github.com/ResidualBlood/galleryvault/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.1.0
[1.0.0]: https://github.com/ResidualBlood/galleryvault/releases/tag/v1.0.0
