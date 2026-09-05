# GalleryVault

> [中文](Home) · English

GalleryVault is a private, self-hosted local gallery library. Your files and collection stay on your machine; you don't hand the library to someone else.

It indexes Ehviewer export folders, CBZ/CBR archives, and image directories into a searchable web library, with automatic series clustering and cloud-missing member tracking. Optionally sync tags and metadata from ExHentai, download galleries, and watch favorites. Reader, search, tag cloud, and tag translation share a Chinese/English UI; deploy with Docker Compose.

## Quick start

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. Run `docker compose up -d` to launch the stack.
2. Open `http://<host>:8000` to access the web UI.
3. Log in with the default password `p1a2s3s4` and change it in *Settings*.
4. Put galleries into `./library` and click *Scan library* to begin.

> **Workflow**: For best results, follow the "Cache metadata first → Scan library → Deduplicate → Batch/incremental download" workflow; see **[Usage Guide: Recommended workflow](Usage-EN#recommended-workflow)**.  
> **Compatibility**: Supports all Ehviewer forks, JHenTai metadata, CBZ/CBR archives, and more; see **[Compatibility](Compatibility-EN)**.

## Documentation

- **User Guides**:
  - **[Usage Guide](Usage-EN)** — Browsing & multi-tag search, web reader, download manager, favorites monitoring & deduplication, recycle bin, PWA & settings
  - **[Features](Features-EN)** — Comprehensive feature list and design highlights
  - **[Screenshots](Screenshots-EN)** — Overview of all main UI pages in English and Chinese
  - **[FAQ](FAQ-EN)** — Frequently asked questions and troubleshooting tips
- **Operations & Deployment**:
  - **[Deployment](Deployment-EN)** — Docker Compose setup, volume mounts, permission handling, reverse proxy TLS, hardening & upgrades
  - **[Backup & Restore](Backup-EN)** — Database and configuration backup/restore procedures
  - **[Encryption at rest](Encryption-EN)** — AES-256-GCM encryption for credentials and recovery steps
- **API & Development**:
  - **[API Reference](API)** — Complete REST API specifications and OpenAPI definitions
  - **[Development](Development)** — Project architecture, codebase layout, and testing standards

## License

[MIT](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE).
