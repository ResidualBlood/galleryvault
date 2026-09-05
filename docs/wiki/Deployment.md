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

Docker Hub 上的镜像是 `linux/amd64` 与 `linux/arm64` 双架构 manifest，`docker compose pull` 会自动拉取与宿主机匹配的架构。

> 三个服务均设置了 `restart: always`（容器异常退出自动重启）与日志轮转（json-file，单文件 ≤10MB、保留 3 份，共占用 ≤30MB）。

启动后打开 `http://<host>:8000`，用默认密码 `p1a2s3s4` 登录——**登录后请立即在设置中修改密码**（默认密码只供首次使用）。

> 本地开发与热重载环境（Dev Compose）请参见 [开发指南](Development#dev-compose)。

## 数据目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **库目录**：已有画廊归档（Ehviewer 导出、CBZ/CBR），新下载不会写入；删除画廊时若挂载可写会一并删除这里对应文件 |
| `./downloads` | **下载目录**：新下载的画廊存放于此，自动扫描（热目录新建文件夹名遵循 `download_title`，无日文时回退英文） |
| `./cache` | **缩略图缓存**（自动生成），不会写入画廊目录 |
| `./Archive` | **归档目录**（可选，compose 默认注释）：分层归档目标（冷库 CBZ 统一以 `gid-英文标题.cbz` 命名，不跟随 `download_title`），启用时取消注释并在设置填 `/archive` |

> 挂载多个宿主目录、将其他 Ehviewer 下载目录作为**仅扫描不下载**的库，见下文。

## 将其他 Ehviewer 下载目录作为「仅扫描不下载」的库

如果有多份 Ehviewer 下载内容想让它们都被扫描、但**新下载只写入 `download_root`**，把它们挂载进 backend 容器（建议 `:ro` 只读，仅当不需要在该目录里删除画廊时），再在「设置 → 库根目录」加入容器内路径：

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - /mnt/你的/ehviewer下载目录:/Ehviewer2:ro   # 新增
      - ./cache:/gv-cache
```

1. 在 `docker-compose.yml` 的 `backend.volumes` 下追加一行（宿主路径换成你的目录，容器内路径任取）。
2. 重启 backend：`docker compose up -d backend`。
3. 在「设置 → 库根目录」加入该容器内路径（每行一个）并保存。
4. 点击「扫描库」开始索引（保存设置不会自动触发扫描）。

`library_roots` 是库根：画廊会被索引、标签同步正常，但新下载只会落到 `download_root`，绝不会写入这些目录。删除画廊时**若挂载可写**会一并删除库根下的对应文件；若挂载为只读，删除会失败并在 toast 与日志页提示（DB 行保留，不会被下次扫描当作新画廊重新入库）。

> **多个已有画廊目录**：有几个就挂几条 volume（容器内路径各取一个唯一名字，如 `/gallery1`、`/gallery2`），然后在「库根目录」每行填一个容器内路径。`download_root` 会被自动并入库根，无需重复填写。

> **环境变量可省略**：compose 里的 `LIBRARY_ROOTS` / `DOWNLOAD_ROOT` 只是**启动初值**，实际以「设置 → 库根目录 / 下载目录」保存的值为准（存 DB，启动时覆盖环境变量）。backend 默认即 `download_root=/downloads`、`library_roots=["/library","/downloads"]`，所以全新部署可以直接不写这两个变量，去设置页配置即可。

## 安全加固

后端默认绑定 `127.0.0.1:8001`，只通过前端 nginx 代理访问；登录接口按真实客户端 IP 限速（每 IP 60 秒 10 次），`/api` 限流 30 次/秒（由前端 nginx 的 `limit_req` 实现）。

> **受信代理白名单 `TRUSTED_PROXIES`**：`X-Forwarded-For` / `X-Real-IP` 仅当直连 IP 为 `127.0.0.1` / `::1` / `testclient` 或在 `TRUSTED_PROXIES` 白名单时才被信任（支持单 IP 或 CIDR，如 `10.0.0.0/8,192.168.1.10`），其余私网 IP 不再隐式可信，避免内网任意客户端伪造 XFF 绕过登录限速。未配置时仅本机环回可信；在反代后部署时请按实际反代 IP 段配置。

### 启用 TLS（可选）

要公网 HTTPS 访问，在 nginx 终止 TLS（或前置 Caddy/反代），并设置 `AUTH_COOKIE_SECURE=true`：

```yaml
    environment:
      AUTH_COOKIE_SECURE: "true"   # backend 服务
```

前端镜像自带 TLS 配置模板（`nginx.conf` 注释部分），把证书挂载进容器并指向 `ssl_certificate` 路径即可，启用后建议加 HSTS 头。

### 静态加密（可选）

设置 `ENCRYPTION_KEY` 环境变量即可让 cookie / token / 密码哈希以 AES-256-GCM 加密存储。详见 [静态加密](Encryption)。

### ExHentai cookie（收藏夹/云同步必需）

收藏夹检查、封面抓取、下载都依赖 ExHentai 登录态。cookie 在**首次运行向导**或**设置 → ExHentai** 中配置（`ipb_member_id` / `ipb_pass_hash` / `igneous`，可「测试登录」验证），保存后**加密存库**（依赖上面的 `ENCRYPTION_KEY`），不会回显。获取方法参见 [入门指南：配置 ExHentai Cookie](Usage#配置-exhentai-cookie)。

> 注意：**不要**在 `docker-compose.yml` 里写 `EXHENTAI_COOKIES` 环境变量——设置的单数据源是数据库；环境变量缺失时收藏夹检查会 302 回首页、静默空跑（收藏夹无封面、列表为空），误以为是网络/风控问题。

### 自定义权限 / 非 root 运行 (PUID / PGID)

后端镜像支持通过环境变量指定运行身份：
- **默认（未配置 `PUID`/`PGID`）**：直接以 `root (0:0)` 权限运行，无需手动 `chown` 挂载目录，启动即用。注意：以 root 模式运行时，新下载的画廊文件和系统日志在宿主机上的属主为 `root`。
- **自定义指定（如 NAS / 非特权 Linux 用户，推荐）**：在 `docker-compose.yml` 中指定 `PUID` 与 `PGID`（如 `PUID=1000` / `PGID=1000`），容器启动时会自动校验参数、动态映射并降权运行，同时在初次启动时自动修复 `/downloads`、`/gv-cache` 等可写目录属主。若想让 `./library` 库根支持删除画廊，请确保宿主目录对该 UID 可写（如 `chown -R 1000:1000 <宿主目录>`）。

> **注意**：`./db-data` 属 postgres（UID 999），**切勿 chown**，否则会导致数据库容器启动失败。

### 可选：集成 Dozzle 实时查看容器日志

如果需要更直观地在浏览器中分屏查看 Nginx、FastAPI 后端及 PostgreSQL 容器的实时日志输出流，可在 `docker-compose.yml` 中按需追加轻量级的 [Dozzle](https://github.com/amir20/dozzle) 容器（占用 ~10MB 内存）：

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
      # 建议绑定本地回环端口或指定内网端口；公网访问建议置于反向代理或身份认证后
      - "127.0.0.1:8888:8080"
```

> **安全提示**：挂载 `/var/run/docker.sock` 时请务必保留 `:ro`（只读），并建议仅绑定 `127.0.0.1` 本地回环接口或通过 SSH 隧道/反向代理访问，避免直接将 Docker 控制接口暴露到公网。

## 升级

```bash
docker compose pull
docker compose up -d
```

数据库迁移会在 backend 启动时自动执行（alembic），无需手动操作。镜像使用 `:latest` 标签，`pull` 即可获得新版本。

> **不要**用 `curl -o docker-compose.yml` 覆盖本地 compose——它可能含有你的定制（端口、挂载目录、`ENCRYPTION_KEY` 等）。如需获取更新的 compose 模板，先备份本地文件，再手动比对合并修改。
