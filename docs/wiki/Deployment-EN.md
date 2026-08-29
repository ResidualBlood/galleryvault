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

## Data directories

| Path | Purpose |
|------|---------|
| `./db-data` | PostgreSQL data (index, settings, history) — survives container recreation |
| `./library` | **Library**: your existing archives (Ehviewer exports, CBZ/CBR). New downloads never land here; deleting a gallery removes its files here when the mount is writable |
| `./downloads` | **Download directory**: galleries downloaded from ExHentai, scanned automatically |
| `./cache` | **Thumbnail cache** (generated), never written into the galleries |

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

> **Permissions**: the backend runs as the in-container `app` user (uid 10001),
> so the mounted host directories must be readable by it. Before mounting, the
> cleanest fix is `chown -R 10001:10001 <host-folder>`; deleting galleries also
> needs the directory to be writable by uid 10001 (on a read-only mount deletion
> fails honestly). `./db-data` belongs to postgres (999) — **do not chown it**.

## Security hardening

The backend binds `127.0.0.1:8001` by default and is only reachable through
the nginx frontend proxy; login is rate-limited per real client IP (10 attempts
/ 60 s) and `/api` is throttled at 30 r/s.

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
and never echoed back.

**How to obtain these cookies?**

1. Log in to **e-hentai.org** in your browser (an e-hentai account is required),
   press `F12` → **Application → Storage → Cookies → https://e-hentai.org**, and
   copy the values of **`ipb_member_id`** and **`ipb_pass_hash`**.
2. To access **exhentai.org** (the "里站": unhidden galleries / restricted
   areas), also copy **`igneous`** from the Cookies of `https://exhentai.org` in
   a session that has exhentai access — this cookie only exists for accounts
   granted access; skip it if you only use the public mirror.
3. Enter them in Settings and verify with *Test login*.

> Note: **do not** set an `EXHENTAI_COOKIES` environment variable in
> `docker-compose.yml` — the database is the single source of truth for
> settings. Without cookies, favorites checks redirect to the home page and
> silently record nothing (no covers, empty lists), which is easy to mistake
> for a network/anti-abuse problem.

### Non-root runtime

The backend image runs as an unprivileged user (`app`, uid 10001). On startup
it fixes ownership of `/downloads` and `/gv-cache` and drops privileges. To let
gallery deletion remove files under a library root (e.g. `./library`), make that
directory writable by the in-container `app` user (host
`chown -R 10001:10001` or group-write permission); otherwise deletion fails and
is reported honestly.

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
