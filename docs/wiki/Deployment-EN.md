# Deployment Guide

> [中文](Deployment) · **English**

GalleryVault features a modular containerized architecture. This guide covers everything from standard Docker Compose setup to typical production network topologies, reverse proxy configurations, and storage performance tuning.

---

## Production Architecture Topology

In a typical production or private NAS deployment, it is strongly recommended to terminate TLS via an external reverse proxy (such as Nginx or Caddy) and forward traffic to GalleryVault:

```text
               ┌────────────────────────────────────────────────────────┐
               │           Public / LAN Clients (Web & OPDS)            │
               └───────────────────────────┬────────────────────────────┘
                                           │ HTTPS (:443) / HTTP
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │         External Reverse Proxy (Nginx / Caddy)          │
               │   - TLS Certificate Termination & HSTS                  │
               │   - Forwards Host, X-Real-IP, and X-Forwarded-Proto     │
               └───────────────────────────┬────────────────────────────┘
                                           │ HTTP (:8000)
    ┌──────────────────────────────────────┴──────────────────────────────────────┐
    │  Docker Compose Container Stack                                             │
    │                                                                             │
    │  ┌───────────────────────┐              ┌────────────────────────────────┐  │
    │  │ galleryvault-frontend │              │      galleryvault-backend      │  │
    │  │ (SPA Web + Nginx)     ├─────────────►│      (FastAPI Business Core)   │  │
    │  │ Port: 8000            │ Proxies /api │ Port: 127.0.0.1:8001 (Loopback)│  │
    │  └───────────────────────┘              └───────┬────────────────────────┘  │
    │                                                 │                           │
    │                                                 │ PostgreSQL Protocol       │
    │                                                 ▼                           │
    │                                         ┌────────────────────────────────┐  │
    │                                         │        galleryvault-db         │  │
    │                                         │     (PostgreSQL Database)      │  │
    │                                         └────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────────────────┘
```

---

## Docker Compose Standard Deployment

The repository's `docker-compose.yml` provisions three integrated services:

| Service | Container Name | Port Mapping | Purpose |
| :--- | :--- | :--- | :--- |
| Frontend Gateway | `galleryvault-frontend` | `0.0.0.0:8000 -> 80` | Static SPA hosting, internal API proxy, and request rate limiting |
| Backend Core | `galleryvault-backend` | `127.0.0.1:8001 -> 8001` | FastAPI core service, bound only to host loopback interface |
| Relational DB | `galleryvault-db` | Internal port only | PostgreSQL 18 database storing indexes, histories, and settings |

```bash
mkdir -p galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

Pre-built Docker Hub images are distributed as multi-arch manifests (`linux/amd64` and `linux/arm64`), which automatically pull the architecture matching your host.

> Open `http://<host-ip>:8000` with the default password **`p1a2s3s4`**. Login goes to the `#/welcome` wizard; you must change the password before the main UI. The shipped compose sets `TZ: Asia/Shanghai` (notification timestamps follow the container TZ).

---

## Storage Topology & Volume Mounts

### 1. Persistent Storage Roots

| Local Host Path | Container Path | Access Mode | Purpose |
| :--- | :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql` | Read-Write (`rw`) | PostgreSQL 18 data (UID 999); stores primary index and credentials (mount to `/var/lib/postgresql`; do not use legacy `/var/lib/postgresql/data`) |
| `./library` | `/library` | `rw` or `ro` | Primary library root for existing archives; **downloads never land here** |
| `./downloads` | `/downloads` | Read-Write (`rw`) | Target directory for active downloads; automatically indexed |
| `./cache` | `/gv-cache` | Read-Write (`rw`) | Thumbnail and cover image cache; saves external bandwidth |
| `./archive` | `/archive` | Read-Write (`rw`) | **Optional**; commented out in compose. Set `archive_roots` in Settings after mounting |

### 2. Tiered Storage & Multi-Disk Mounting

To mount multiple storage pools on your NAS or scan existing collections without downloading into them:

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - ./cache:/gv-cache
      # Additional disk volumes or network shares:
      - /mnt/storage_pool2/ehviewer_export:/mnt/pool2:ro
      - /mnt/cold_archive/disk1:/archive1:rw
```

**Steps to Apply**:
1. Add paths under `backend.volumes` in `docker-compose.yml` and restart the backend: `docker compose up -d backend`.
2. Open *Settings → Library roots*, enter the container paths (e.g. `/mnt/pool2`, one per line), and save.
3. Click **Scan library**. All mounted roots will be aggregated into the central library view.

---

## Reverse Proxy Best Practices

To ensure rate limiting, CSRF protections, and session authentication function properly, the reverse proxy must pass client identity headers correctly.

### 1. Nginx Configuration Sample

```nginx
# /etc/nginx/conf.d/galleryvault.conf

upstream galleryvault_upstream {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name vault.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vault.example.com;

    ssl_certificate     /etc/ssl/certs/vault.example.com.crt;
    ssl_certificate_key /etc/ssl/private/vault.example.com.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    client_max_body_size 500M;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    location / {
        proxy_pass http://galleryvault_upstream;
        proxy_http_version 1.1;

        # Mandatory headers for CSRF validation and IP throttling
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

### 2. Caddyfile Configuration Sample

```caddyfile
vault.example.com {
    encode gzip zstd
    tls admin@example.com

    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        
        transport http {
            read_timeout 600s
            write_timeout 600s
        }
    }
}
```

---

## User Permissions & Troubleshooting (PUID / PGID)

By default, the backend container operates as `root (0:0)`. On dedicated NAS systems (Synology, QNAP, TrueNAS), specifying custom user mappings is recommended:

```yaml
    environment:
      - PUID=1000
      - PGID=1000
```

The shipped `docker-compose.yml` already comments these backend env vars: `PUID` / `PGID`, `ENCRYPTION_KEY`, `AUTH_SECRET`, `TRUSTED_PROXIES`. Uncomment as needed. Library / download / archive paths stay in the Web UI.

### Permission Troubleshooting
- **Files Locked by Root**: If previously run under root, reassign ownership on the host:
  ```bash
  chown -R 1000:1000 ./downloads ./library ./cache
  ```
- **Database Boot Error `Operation not permitted`**:
  - **Important Warning**: The PostgreSQL image strictly relies on container user `postgres` (UID 999). **Never run `chown -R 1000:1000` against `./db-data`**. If changed accidentally, restore ownership to 999:
    ```bash
    chown -R 999:999 ./db-data
    ```

---

## Tuning & Concurrency Safeguards

### 1. Trusted Proxies (`TRUSTED_PROXIES`)
To prevent spoofed `X-Forwarded-For` headers from bypassing brute-force login throttles, only loopback addresses are trusted by default. Behind an external reverse proxy, explicitly define your proxy network range:

```yaml
    environment:
      - TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12,192.168.1.0/24
```

### 2. Concurrency Tuning Guide

Tune these parameters in *Settings* based on your network conditions:

- **`download_concurrency`**: Default `2`. Sets the number of simultaneously downloading galleries.
- **`page_concurrency`**: Default `4` (max `16`). Adjust according to proxy stability; reduce to `2-4` if connection drops occur over UDP/proxy hops.
- **`exhentai_max_concurrency`**: Default `6`. Hard global cap protecting your account from burst traffic triggers.
- **`GV_CHALLENGE_PROBE_INTERVAL`**: Default `600` seconds. Background probe cycle when auto-paused by anti-bot challenges.

### 3. Database Connection Pool Tuning

For high-concurrency background workers, mass gallery imports, and batch fetching workflows, SQLAlchemy async connection pool parameters can be tuned via environment variables in `docker-compose.yml` or `.env`:

| Environment Variable / Key | Default | Description |
| --- | --- | --- |
| `database_pool_size` | `30` | SQLAlchemy connection pool base permanent connection capacity. |
| `database_max_overflow` | `10` | Maximum temporary overflow connections allowed during concurrency bursts, automatically closed once returned. |
| `database_pool_timeout` | `30` | Timeout (in seconds) to wait when acquiring an available connection from the pool. |

Working in tandem with dependency injection lifecycle management and Unit of Work (UoW) / transaction and network I/O isolation, database sessions are acquired only during active DB operations and released immediately, preventing large-scale batch tasks and slow network I/O from exhausting the pool.

---

## Upgrades

```bash
docker compose pull
docker compose up -d
```

Alembic schema migrations run automatically during backend container initialization.

---

## Offline Maintenance & Repair Utilities

To clean up legacy issues from multi-device migrations (such as overlong filenames or stacked GID contamination), built-in Python maintenance scripts can be executed directly inside the backend container or on the host:

### 1. Cold Archive & Local Directory Repair (`repair_cold_archives.py`)
- **Function**: Automatically strips redundant leading GIDs (e.g. `[12345] 12345-Title`), queries the upstream official GData API in batches to clean up and rebuild `.galleryvault.json` sidecar indexes.
- **Parameters**:
  - `--archive-dir`: Container path of the cold archive or gallery directory to scan and repair;
  - `--dry-run`: Dry-run simulation mode; prints planned renames and metadata updates without modifying disk;
  - `--batch-size`: Batch size for querying the upstream GData API (default 25).
- **Single-line command in container**:
  ```bash
  # Dry-run preview:
  docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive1 --dry-run

  # Execute cleanup:
  docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive1
  ```

### 2. CBZ Filename 243-Byte Boundary Alignment (`repair_cbz_filenames.py`)
- **Function**: Scans and aligns legacy CBZ filenames to the Linux ext4 243-byte boundary standard, completely eliminating `[Errno 36] File name too long`.
- **Parameters**:
  - `--target-dir`: Target directory containing legacy CBZ archives;
  - `--max-bytes`: Maximum filename length in bytes (default 243 bytes);
  - `--dry-run`: Dry-run simulation mode; prints planned truncations only.
- **Host Execution** (script is located at repository root `scripts/`, **not packaged into container image**):
  ```bash
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive --dry-run
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```
