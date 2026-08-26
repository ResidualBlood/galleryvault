# 部署

## Docker Compose

仓库根目录的 `docker-compose.yml` 包含三个服务，容器名固定：

| 服务 | 容器名 | 宿主端口 |
|------|--------|----------|
| 前端 nginx SPA | `galleryvault-frontend` | 8000 |
| FastAPI 后端 | `galleryvault-backend` | 127.0.0.1:8001（仅本机） |
| PostgreSQL | `galleryvault-db` | 内部 |

```bash
docker compose up -d
```

启动后打开 `http://<host>:8000`，用默认密码 `p1a2s3s4` 登录——**登录后请立即在设置中修改密码**（默认密码只供首次使用）。

## 数据目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **只读库目录**：已有画廊归档（Ehviewer 导出、CBZ/CBR），新下载不会写入 |
| `./downloads` | **下载目录**：新下载的画廊存放于此，自动扫描 |
| `./cache` | **缩略图缓存**（自动生成），不会写入画廊目录 |

> 挂载多个宿主目录、将其他 Ehviewer 下载目录作为**仅扫描不下载**的库，见下文。

## 将其他 Ehviewer 下载目录作为「仅扫描不下载」的库

如果有多份 Ehviewer 下载内容想让它们都被扫描、但**新下载只写入 `download_root`**，把它们挂载进 backend 容器（建议 `:ro` 只读），再在「设置 → 库根目录（只读）」加入容器内路径：

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - /mnt/你的/ehviewer下载目录:/Ehviewer2:ro   # 新增
      - ./cache:/gv-cache
```

1. 在 `docker-compose.yml` 的 `backend.volumes` 下追加一行（宿主路径换成你的目录，容器内路径任取）。
2. 重启 backend：`docker compose up -d backend`。
3. 在「设置 → 库根目录（只读）」加入该容器内路径（每行一个）并保存。
4. 点击「扫描库」开始索引（保存设置不会自动触发扫描）。

`library_roots` 是只读库根：画廊会被索引、标签同步正常，但新下载只会落到 `download_root`，绝不会写入这些目录。容器需能读取宿主目录（权限 ≥ `755`）。

## 安全加固

后端默认绑定 `127.0.0.1:8001`，只通过前端 nginx 代理访问；登录接口按真实客户端 IP 限速（每 IP 60 秒 10 次），`/api` 限流 30 次/秒。

### 启用 TLS（可选）

要公网 HTTPS 访问，在 nginx 终止 TLS（或前置 Caddy/反代），并设置 `AUTH_COOKIE_SECURE=true`：

```yaml
    environment:
      AUTH_COOKIE_SECURE: "true"   # backend 服务
```

前端镜像自带 TLS 配置模板（`nginx.conf` 注释部分），把证书挂载进容器并指向 `ssl_certificate` 路径即可，启用后建议加 HSTS 头。

### 静态加密（可选）

设置 `ENCRYPTION_KEY` 环境变量即可让 cookie / token / 密码哈希以 AES-256-GCM 加密存储。详见 [静态加密](encryption.md)。

### 非 root 运行

后端镜像默认以非特权用户运行（容器内 `app`，uid 10001），启动时会自动调整 `/downloads`、`/gv-cache` 属主并降权，`/library` 保持只读。

## 升级

```bash
git pull          # 更新 docker-compose.yml / README
docker compose pull
docker compose up -d
```

数据库迁移会在 backend 启动时自动执行（alembic），无需手动操作。
