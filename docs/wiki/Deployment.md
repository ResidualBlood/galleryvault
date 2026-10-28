# 部署指南

> **中文** · [English](Deployment-EN)

本文说明如何用 Docker Compose 部署 GalleryVault，以及反向代理、存储与权限相关配置。

---

## 生产部署架构拓扑

在典型的生产或私有 NAS 环境中，建议通过反向代理（如 Nginx 或 Caddy）终结 TLS 并将请求分发至 GalleryVault：

```text
               ┌────────────────────────────────────────────────────────┐
               │              公网 / 私网客户端 (Web / OPDS)              │
               └───────────────────────────┬────────────────────────────┘
                                           │ HTTPS (:443) / HTTP
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │          外部反向代理 (Nginx / Caddy / Traefik)         │
               │   - TLS 证书终结 & HSTS 加固                            │
               │   - 透传 Host、X-Real-IP 与 X-Forwarded-Proto           │
               └───────────────────────────┬────────────────────────────┘
                                           │ HTTP (:8000)
    ┌──────────────────────────────────────┴──────────────────────────────────────┐
    │  Docker Compose 容器栈                                                       │
    │                                                                             │
    │  ┌───────────────────────┐              ┌────────────────────────────────┐  │
    │  │ galleryvault-frontend │              │      galleryvault-backend      │  │
    │  │ (SPA 静态托管 + Nginx)  ├─────────────►│       (FastAPI 业务核心)       │  │
    │  │ 端口: 8000             │  反代 /api   │ 端口: 127.0.0.1:8001 (本地环回) │  │
    │  └───────────────────────┘              └───────┬────────────────────────┘  │
    │                                                 │                           │
    │                                                 │ PostgreSQL 协议           │
    │                                                 ▼                           │
    │                                         ┌────────────────────────────────┐  │
    │                                         │        galleryvault-db         │  │
    │                                         │      (PostgreSQL 数据库)       │  │
    │                                         └────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────────────────┘
```

---

## Docker Compose 标准部署

项目根目录的 `docker-compose.yml` 包含完整的三容器拓扑：

| 服务 | 容器名称 | 默认端口映射 | 说明 |
| :--- | :--- | :--- | :--- |
| 前端网关 | `galleryvault-frontend` | `0.0.0.0:8000 -> 80` | 提供前端 SPA 静态托管，反代 API 并处理请求流控 |
| 后端核心 | `galleryvault-backend` | `127.0.0.1:8001 -> 8001` | FastAPI 业务服务，默认仅监听宿主环回接口 |
| 关系数据库 | `galleryvault-db` | 容器内部网络端口 | PostgreSQL 18 数据库，存储索引与系统状态 |

```bash
mkdir -p galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

镜像基于多架构 Manifest（`linux/amd64` 与 `linux/arm64`），Docker 会根据宿主硬件自动匹配。

> 首次登录请访问 `http://<主机IP>:8000`，使用默认口令 **`p1a2s3s4`**。登录后进入 `#/welcome` 向导，必须先改密才能进主界面。仓库 compose 默认 `TZ: Asia/Shanghai`（通知时间戳跟容器时区）。默认口令仅在尚未配置管理员密码时有效，已配置密码后一律无效；OPDS 的 HTTP Basic 认证在未配置密码时同样不接受默认口令。

---

## 存储拓扑与数据卷挂载

### 1. 核心持久化目录

| 本地路径 | 容器内挂载点 | 读写属性 | 功能说明 |
| :--- | :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql` | 读写 (`rw`) | PostgreSQL 18 核心数据（UID 999），保存全量索引与配置（勿设旧路径 `/var/lib/postgresql/data`，官方 PG18 挂载 `/var/lib/postgresql` 即可） |
| `./library` | `/library` | 读写 (`rw`) 或只读 (`ro`) | 主画廊库，存放已有归档，**下载任务绝不写入此目录** |
| `./downloads` | `/downloads` | 读写 (`rw`) | 下载落盘目录，新下载文件在此生成并触发增量入库 |
| `./cache` | `/gv-cache` | 读写 (`rw`) | 缩略图与封面缓存，避免高频请求重复拉取图片 |
| `./archive` | `/archive` | 读写 (`rw`) | **可选**；compose 默认注释。启用后在设置填 `archive_roots` |

### 2. 冷热分层存储、多盘挂载与归档规则

在 NAS 上拥有多块存储池、希望将既有下载目录作为只读扫描库，或利用多块硬盘作为冷归档池时，可在 `docker-compose.yml` 中追加数据卷挂载：

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - ./cache:/gv-cache
      # 额外挂载外部硬盘或多块 NAS 冷存储归档盘：
      - /mnt/storage_pool2/ehviewer_export:/mnt/pool2:ro
      - /mnt/cold_disk1:/archive1:rw
      - /mnt/cold_disk2:/archive2:rw
```

**生效与配置指引**：
1. **更新数据卷**：编辑 `docker-compose.yml` 中的 `backend.volumes` 并重启容器：`docker compose up -d backend`。
2. **多库扫描目录**：打开 Web 界面进入「系统设置 → 资料库 → 库根目录」，在多行文本框中填入只读或既有画廊路径（如 `/mnt/pool2`，每行一个）并保存（需输入当前管理员密码确认），点击「扫描库」开始增量索引。
3. **冷存储多根目录 (`archive_roots`) 与容量负载均衡**：
   - 在「系统设置 → 资料库 → 冷归档目录」中填写多个冷存储挂载点（每行一个路径，例如 `/archive1` 与 `/archive2`）。
   - **动态空间均衡**：冷归档任务通过 `statvfs` 检查各 `archive_roots` 的剩余空间，写入剩余空间 ≥ 预估体积 × 1.2 且空闲空间最多的挂载目录。
4. **命名规范与单卷规格**：
   - 归档文件名与目录名规范、UTF-8 字节截断及临时后缀缓冲规则详见 [兼容性与格式规范 → 格式降级与容错处理](Compatibility#格式降级与容错处理)。
   - 单卷上限为 **500 页且 2GiB**（两项指标均未超出才打包为 CBZ）；超出任一限制时打成冷目录，不打成多卷 CBZ。
5. **安全反向清理已归档源目录 (`purge-archived-sources`)**：
   - 当画廊在冷存储目录成功归档后，可在「系统设置 → 存储面板」点击「清理已归档源目录」（调用 `POST /api/system/purge-archived-sources`）。
   - 系统核对冷存储与热存储两端的画廊 GID，主动跳过处于 `pending` 或 `downloading` 状态的任务，确认已归档后再删除下载目录中对应的散图文件夹以回收磁盘空间。

---

## 反向代理最佳实践

为确保登录限速、防跨站请求伪造（CSRF）与安全认证正常工作，反向代理必须正确透传客户端来源信息。不要剥掉 `Origin`；`Origin: null` 或空 Origin 带会话 Cookie 且无 CSRF token 的 API 变更请求会被拒绝。

### 1. Nginx 完整配置范例

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

    # 客户端上传与单文件大包支持 (如 CBZ 导出与整包传输)
    client_max_body_size 500M;

    # 安全响应头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    location / {
        proxy_pass http://galleryvault_upstream;
        proxy_http_version 1.1;

        # 核心头信息透传 (防 CSRF 拦截与 IP 鉴权关键)
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支持流式传输与长连接
        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

### 2. Caddyfile 完整配置范例

```caddyfile
vault.example.com {
    encode gzip zstd
    
    # 自动证书申请与 HTTPS
    tls admin@example.com

    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        
        # 调优长连接与流式下载超时
        transport http {
            read_timeout 600s
            write_timeout 600s
        }
    }
}
```

---

## 权限管理与非 Root 降权排错 (PUID / PGID)

默认情况下，后端容器以 `root (0:0)` 权限运行。在群晖（Synology）、QNAP 或 TrueNAS 等私有存储环境中，为保证宿主机文件权限一致，推荐配置非 root 映射：

```yaml
    environment:
      - PUID=1000
      - PGID=1000
```

仓库 `docker-compose.yml` 的 backend `environment` 已预留注释项：`PUID` / `PGID`、`ENCRYPTION_KEY`、`AUTH_SECRET`、`TRUSTED_PROXIES`。按需取消注释即可；路径类配置仍只在 Web 设置里改。

### 权限排错指南
- **数据目录被 root 锁定**：若此前曾以 root 启动，请在宿主机执行修复属主：
  ```bash
  chown -R 1000:1000 ./downloads ./library ./cache
  ```
- **数据库容器启动报错 `chown: changing ownership of '/var/lib/postgresql': Operation not permitted`**：
  - **严重警告**：PostgreSQL 官方镜像固定依赖容器内 `postgres` 用户（UID 999）。**切勿对宿主 `./db-data` 目录执行批量 `chown -R 1000:1000`**。若已误改，请将其属主改回 999：
    ```bash
    chown -R 999:999 ./db-data
    ```

---

## 性能调优与并发限流策略

### 1. 受信代理白名单 (`TRUSTED_PROXIES`)
为防止恶意客户端伪造 `X-Forwarded-For` 绕过登录防爆破限速，系统默认仅信任本机环回地址。在反向代理后部署时，请在 `docker-compose.yml` 中明确指定反代所在的 IP 网段：

```yaml
    environment:
      - TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12,192.168.1.0/24
```

### 2. 调度与限流调优指引

可在 Web「系统设置」中微调以下参数以适应不同带宽与网络链路：

- **`download_concurrency`（并发画廊数）**：默认 `2`。建议配置在 `1-4` 之间，避免多画廊并行抢占配额；修改后立即生效，无需重启。
- **`page_concurrency`（单画廊并发页数）**：默认 `4`，上限 `16`。高速稳定链路可适度上调；UDP/代理链路出现抖动时建议下调至 `2-4`。
- **`exhentai_max_concurrency`（全局并发上限）**：默认 `6`，取值范围 `1-32`。系统内部硬限制，严控发往服务端的突发请求密度，保障账号安全。
- **`GV_CHALLENGE_PROBE_INTERVAL`（302 探针间隔）**：默认 `600` 秒。遭遇防爬限制时的探测周期。
- **`GV_MAX_CHALLENGE_PAUSES`（单任务 302 挑战上限）**：默认 `5`。单个任务触发 302 临时挑战并自动暂停的次数上限；达到上限后任务标记为失败并保留剩余重试预算，避免暂停/恢复/再挑战的无限循环。
- **`THUMBNAIL_WORKERS`（缩略图 worker 数）**：默认 `4`，取值范围 `1-16`。

### 3. 数据库连接池调优

针对高并发后台 worker、大批量画廊导入与并发抓取场景，系统基于 SQLAlchemy 异步连接池提供精细化调优环境变量，可按需在 `docker-compose.yml` 或 `.env` 中配置：

| 环境变量 / 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `database_pool_size` | `30` | SQLAlchemy 连接池基础常驻连接数。 |
| `database_max_overflow` | `10` | 突发高并发允许超出的临时连接数。超出部分在连接释放后自动销毁。 |
| `database_pool_timeout` | `30` | 从连接池获取可用连接的超时等待秒数。 |

配合系统的依赖注入生命周期管理与 Unit of Work（UoW）/ 事务与网络 I/O 隔离机制，连接仅在执行具体数据库操作时借出并立即归还，有效防止大规模批量任务和高并发网络 I/O 挂起并耗尽连接池。

---

## 系统更新与升级

```bash
docker compose pull
docker compose up -d
```

Alembic 数据库结构迁移程序会在 `backend` 启动时自动执行，更新数据库表结构与索引。升级前建议执行常规数据库备份以防异常。

---

## 运维工具与离线修复脚本速查

针对多端迁移历史遗留的超长文件名或 GID 叠加污染，可在离线或维护状态下使用内置的 Python 运维脚本进行修复：

### 1. 冷库与本地目录全量修复 (`repair_cold_archives.py`)
- **功能**：检测并剥离如 `[12345] 12345-标题` 的重复前导 GID，分片批量回查云端官方 GData API 并更新 `.galleryvault.json` 索引文件。重命名成功后同步更新数据库中的 `path_hash` 与 `duplicate_records` 的路径/键，避免重复记录失配。
- **参数说明**：
  - `--archive-dir`：扫描与修复的目标归档或画廊根目录路径；
  - `--dry-run`：安全演练模式，仅打印拟修改项与元数据计划，不写入磁盘；
  - `--batch-size`：批量请求 GData 接口的批大小（默认 25）。
- **执行方法**：
  - **宿主机执行**（本地开发或宿主 Python 环境）：
    ```bash
    # 演练预览：
    python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive --dry-run

    # 正式执行：
    python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive
    ```
  - **Docker 容器内执行**（推荐生产部署方式）：
    ```bash
    # 演练预览（注意将 /archive 替换为容器内挂载的实际冷存储路径）：
    docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive --dry-run

    # 正式执行：
    docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive
    ```

### 2. CBZ 超长文件名 243 字节对齐 (`repair_cbz_filenames.py`)
- **功能**：遍历目标目录中的历史 CBZ 文件，按 243 字节文件名限制进行截断对齐，规避文件系统错误。
- **环境要求**：脚本位于仓库根目录 `scripts/repair_cbz_filenames.py`，**未打包进 Docker 镜像**，须在宿主机直接调用 Python 执行。
- **参数说明**：
  - `--target-dir`：待处理的 CBZ 归档目录路径；
  - `--max-bytes`：字节截断上限（默认 243 字节）；
  - `--dry-run`：安全演练模式，仅打印拟截断重命名的文件列表。
- **宿主机执行**：
  ```bash
  # 演练预览：
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive --dry-run

  # 正式执行：
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```
