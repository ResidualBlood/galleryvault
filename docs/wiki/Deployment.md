# 部署指南

> **中文** · [English](Deployment-EN)

GalleryVault 采用模块化容器架构设计。本文档提供从基础 Docker Compose 到典型生产架构拓扑、反向代理配置与存储调优的完整部署指引。

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
| 关系数据库 | `galleryvault-db` | 容器内部网络端口 | PostgreSQL 16 数据库，存储索引与系统状态 |

```bash
mkdir -p galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

镜像基于多架构 Manifest（`linux/amd64` 与 `linux/arm64`），Docker 会根据宿主硬件自动匹配。

> 首次登录请访问 `http://<主机IP>:8000`，使用默认口令 **`p1a2s3s4`** 登录，并在「设置」中立即修改密码。

---

## 存储拓扑与数据卷挂载

### 1. 核心持久化目录

| 本地路径 | 容器内挂载点 | 读写属性 | 功能说明 |
| :--- | :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql/data` | 读写 (`rw`) | PostgreSQL 核心数据（UID 999），保存全量索引与配置 |
| `./library` | `/library` | 读写 (`rw`) 或只读 (`ro`) | 主画廊库，存放已有归档，**下载任务绝不写入此目录** |
| `./downloads` | `/downloads` | 读写 (`rw`) | 下载落盘目录，新下载文件在此生成并触发增量入库 |
| `./cache` | `/gv-cache` | 读写 (`rw`) | 缩略图与封面缓存，避免高频请求重复拉取图片 |
| `./Archive` | `/archive` | 读写 (`rw`) | （可选）分层冷存储归档目标卷，用于存放长期低频画廊 |

### 2. 冷热分层存储与多盘挂载

如果您在 NAS 上拥有多块存储池或希望将既有下载目录作为**仅扫描不写入**的库，可按如下方式在 `docker-compose.yml` 中追加数据卷：

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - ./cache:/gv-cache
      # 额外挂载多块外部硬盘或 NAS 共享路径：
      - /mnt/storage_pool2/ehviewer_export:/mnt/pool2:ro
      - /mnt/cold_archive/disk1:/archive1:rw
```

**生效步骤**：
1. 编辑 `docker-compose.yml` 中的 `backend.volumes` 并重启容器：`docker compose up -d backend`。
2. 打开 Web 界面进入「系统设置 → 库根目录」，在多行文本框中填入容器内路径（如 `/mnt/pool2`，每行一个）并保存。
3. 点击「扫描库」开始索引。系统会将这些目录统一汇聚至统一资产视图中。

---

## 反向代理最佳实践

为确保登录限速、防跨站请求伪造（CSRF）与安全认证正常工作，反向代理必须正确透传客户端来源信息。

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

### 权限排错指南
- **数据目录被 root 锁定**：若此前曾以 root 启动，请在宿主机执行修复属主：
  ```bash
  chown -R 1000:1000 ./downloads ./library ./cache
  ```
- **数据库容器启动报错 `chown: changing ownership of '/var/lib/postgresql/data': Operation not permitted`**：
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

- **`download_concurrency`（并发画廊数）**：默认 `2`。建议配置在 `1-4` 之间，避免多画廊并行抢占配额。
- **`page_concurrency`（单画廊并发页数）**：默认 `4`，上限 `16`。高速稳定链路可适度上调；UDP/代理链路出现抖动时建议下调至 `2-4`。
- **`exhentai_max_concurrency`（全局并发上限）**：默认 `6`。系统内部硬限制，严控发往服务端的突发请求密度，保障账号安全。
- **`GV_CHALLENGE_PROBE_INTERVAL`（302 探针间隔）**：默认 `600` 秒。遭遇防爬限制时的探测周期。

---

## 系统更新与升级

```bash
docker compose pull
docker compose up -d
```

Alembic 数据库结构迁移程序会在 `backend` 启动时自动执行，平滑升级无须手动介入。
