# Deployment

## Docker Compose

The `docker-compose.yml` in the repository root runs three services with fixed
container names:

| Service | Container name | Host port |
|---------|----------------|-----------|
| Frontend nginx SPA | `galleryvault-frontend` | 8000 |
| FastAPI backend | `galleryvault-backend` | 127.0.0.1:8001 (loopback only) |
| PostgreSQL | `galleryvault-db` | internal |

```bash
docker compose up -d
```

The images on Docker Hub are multi-arch manifests for `linux/amd64` and
`linux/arm64`; `docker compose pull` fetches the architecture that matches the
host automatically.

> All three services set `restart: always` (containers restart automatically on
> an abnormal exit) and log rotation (json-file driver, ≤10MB per file, 3 files
> kept, ≤30MB total).

Then open `http://<host>:8000` and log in with the default password
`p1a2s3s4` — **change it in Settings right away** (the default is for first
login only).

> For local development and live-reload environment (Dev Compose), see [Development](Development#dev-compose).

## Data directories

| Path | Purpose |
|------|---------|
| `./db-data` | PostgreSQL data (index, settings, history) — survives container recreation |
| `./library` | **Library**: your existing archives (Ehviewer exports, CBZ/CBR). New downloads never land here; deleting a gallery removes its files here when the mount is writable |
| `./downloads` | **Download directory**: galleries downloaded from ExHentai, scanned automatically (hot folder names follow `download_title`, falling back to English if no Japanese title) |
| `./cache` | **Thumbnail cache** (generated), never written into the galleries |
| `./Archive` | **Archive** (optional, commented in compose by default): tiered archive destination (cold storage CBZ files are consistently named `gid-<English title>.cbz`, not following `download_title`); multiple volumes can be mounted (e.g. `./Archive:/archive`, `./Archive2:/archive2`); uncomment and configure in Settings to enable |

> To mount several host directories and use other Ehviewer download folders as
> **scan-only** libraries, see below.

## Using other Ehviewer download folders as scan-only libraries

If you have several folders of Ehviewer downloads and want them all scanned
while **new downloads only land in `download_root`**, mount each one into the
backend container (use `:ro` when you don't need to delete galleries in it) and
add the in-container path under *Settings → Library roots*:

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - /mnt/your/ehviewer/download-folder:/Ehviewer2:ro   # added
      - ./cache:/gv-cache
```

1. Add a line under `backend.volumes` in `docker-compose.yml` (any host path,
   any in-container path such as `/Ehviewer2`).
2. Restart the backend: `docker compose up -d backend`.
3. In *Settings → Library roots* add that in-container path (one
   per line) and save.
4. Click **Scan library** to index it (saving settings does not auto-scan).

`library_roots` are library roots: galleries are indexed and tag-synced
normally, but downloads only ever go to `download_root` and are never written
into these folders. Deleting a gallery **removes its files under these roots
when the mount is writable**; on a read-only mount the deletion fails and is
reported in the toast and on the Logs page (the DB row is kept so the next scan
does not re-import it as a fresh gallery).

> **Multiple existing gallery folders**: add one volume per folder (give each a
> unique in-container path such as `/gallery1`, `/gallery2`), then list each
> in-container path in *Settings → Library roots* (one per line).
> `download_root` is always included in the library roots automatically, so you
> don't need to repeat it.

> **Path configuration is in Settings**: compose no longer sets path env vars
> (such as `DOWNLOAD_ROOT` or `COLD_STORAGE_ROOT`); configure paths in Settings
> (persisted to the DB). Fresh installs default to `download_root=/downloads`
> and `library_roots` containing `/library` before settings are first saved.

## Security hardening

The backend binds `127.0.0.1:8001` by default and is only reachable through
the nginx frontend proxy; login is rate-limited per real client IP (10 attempts
/ 60 s) and `/api` is throttled at 30 r/s (implemented by the frontend nginx
`limit_req`).

> **Trusted proxy whitelist `TRUSTED_PROXIES`**: `X-Forwarded-For` / `X-Real-IP` are only trusted when the direct peer is `127.0.0.1` / `::1` / `testclient` or listed in `TRUSTED_PROXIES` (single IP or CIDR, e.g. `10.0.0.0/8,192.168.1.10`). Private ranges are **not** implicitly trusted — set the whitelist to your reverse-proxy's IP range when behind a proxy to avoid spoofed XFF bypassing the login rate limit.

### TLS (optional)

To serve the UI over HTTPS, terminate TLS at nginx (or in front of it with
Caddy / a reverse proxy) and set `AUTH_COOKIE_SECURE=true`:

```yaml
    environment:
      AUTH_COOKIE_SECURE: "true"   # backend service
```

The frontend image ships a TLS template (the commented section of
`nginx.conf`): mount your certificate into the container, point
`ssl_certificate` at it, and add HSTS once HTTPS is live.

### At-rest encryption (optional)

Setting the `ENCRYPTION_KEY` environment variable stores cookies / tokens /
password hashes encrypted with AES-256-GCM. See [Encryption](Encryption-EN).

### ExHentai cookies (required for favorites / cloud sync)

Favorites checks, cover fetching and downloads all depend on an ExHentai
session. Configure the cookies in the **first-run wizard** or **Settings →
ExHentai** (`ipb_member_id` / `ipb_pass_hash` / `igneous`, verified with "Test
login"); they are stored **encrypted in the database** (via `ENCRYPTION_KEY`)
and never echoed back. For instructions on obtaining cookies, see [Usage Guide: Cookie Setup](Usage-EN#configuring-exhentai-cookies).

> Note: **do not** set an `EXHENTAI_COOKIES` environment variable in
> `docker-compose.yml` — the database is the single source of truth for
> settings. Without cookies, favorites checks redirect to the home page and
> silently record nothing (no covers, empty lists), which is easy to mistake
> for a network/anti-abuse problem.

### Custom Permissions / Non-root runtime (PUID / PGID)

The backend image supports configurable runtime user identity via environment variables:
- **Default (no `PUID`/`PGID` set)**: Runs directly as `root (0:0)` with zero setup and no manual host permission adjustments required. Note that in root mode, newly downloaded archives and system logs will be owned by `root` on the host.
- **Custom unprivileged user (NAS / standard Linux host, recommended)**: Set `PUID` and `PGID` in `docker-compose.yml` (e.g. `PUID=1000`, `PGID=1000`). The container validates parameters, drops privileges at startup, and automatically aligns ownership on `/downloads` and `/gv-cache`. To allow gallery deletions under library roots (e.g. `./library`), ensure the host directory is writable by that UID (e.g. `chown -R 1000:1000 <host-folder>`).

> **Note**: `./db-data` belongs to postgres (UID 999) — **do not chown it**, as this will cause the database container to fail on boot.

### Optional: View container logs in real time with Dozzle

If you prefer viewing live multi-container log streams (Nginx, FastAPI backend, PostgreSQL) side by side in a web browser, you can append a lightweight [Dozzle](https://github.com/amir20/dozzle) container (~10MB memory usage) to your `docker-compose.yml`:

```yaml
  dozzle:
    image: amir20/dozzle:latest
    container_name: galleryvault-dozzle
    restart: always
    environment:
      DOZZLE_NO_ANALYTICS: "true"
      DOZZLE_LEVEL: "info"
      DOZZLE_FILTER: "name=galleryvault*"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    ports:
      # Recommended to bind to loopback or private LAN only; protect with reverse proxy if accessed publicly
      - "127.0.0.1:8888:8080"
```

> **Security Note**: Keep the `:ro` (read-only) flag on `/var/run/docker.sock`, and bind only to `127.0.0.1` loopback or access via an SSH tunnel / authenticated reverse proxy to avoid exposing Docker daemon endpoints directly to the public network.

## Upgrading

```bash
docker compose pull
docker compose up -d
```

Database migrations (Alembic) run automatically when the backend starts — no
manual step needed. Images use the `:latest` tag, so `pull` fetches new
releases.

> Do **not** overwrite your local `docker-compose.yml` with
> `curl -o docker-compose.yml` — it likely contains your customizations (ports,
> volume mounts, `ENCRYPTION_KEY`, …). If you need a newer compose template,
> back it up first and merge the changes by hand.
