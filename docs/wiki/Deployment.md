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

## 数据目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **库目录**：已有画廊归档（Ehviewer 导出、CBZ/CBR），新下载不会写入；删除画廊时若挂载可写会一并删除这里对应文件 |
| `./downloads` | **下载目录**：新下载的画廊存放于此，自动扫描 |
| `./cache` | **缩略图缓存**（自动生成），不会写入画廊目录 |

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

> **权限**：backend 以容器内 `app`（uid 10001）运行，需能读取挂载的宿主目录（≥ 可读即可）。挂载前建议直接 `chown -R 10001:10001 <宿主目录>` 一劳永逸；删除画廊需该目录对 10001 可写（只读挂载时删除会如实失败）。`./db-data` 属 postgres（999），**勿 chown**。

## 安全加固

后端默认绑定 `127.0.0.1:8001`，只通过前端 nginx 代理访问；登录接口按真实客户端 IP 限速（每 IP 60 秒 10 次），`/api` 限流 30 次/秒（由前端 nginx 的 `limit_req` 实现）。

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

收藏夹检查、封面抓取、下载都依赖 ExHentai 登录态。cookie 在**首次运行向导**或**设置 → ExHentai** 中配置（`ipb_member_id` / `ipb_pass_hash` / `igneous`，可「测试登录」验证），保存后**加密存库**（依赖上面的 `ENCRYPTION_KEY`），不会回显。

**如何获取这三个 cookie？**

1. 浏览器登录 **e-hentai.org**（需要 e-hentai 账户）→ 按 `F12` → **Application/应用程序 → Storage → Cookies → https://e-hentai.org**，复制 **`ipb_member_id`** 与 **`ipb_pass_hash`** 的值。
2. 需要访问 **exhentai.org 里站**（未和谐画廊/部分专区）时，再从 `https://exhentai.org` 的 Cookies 复制 **`igneous`**（仅对已获得里站权限的账户存在；只用外站则无需填写）。
3. 填入设置页并「测试登录」验证。

> 注意：**不要**在 `docker-compose.yml` 里写 `EXHENTAI_COOKIES` 环境变量——设置的单数据源是数据库；环境变量缺失时收藏夹检查会 302 回首页、静默空跑（收藏夹无封面、列表为空），误以为是网络/风控问题。

### 非 root 运行

后端镜像默认以非特权用户运行（容器内 `app`，uid 10001），启动时会自动调整 `/downloads`、`/gv-cache` 属主并降权。若想让 `./library` 等库根目录支持删除画廊，需确保该目录对容器内 `app` 用户（uid 10001）可写（宿主 `chown -R 10001:10001` 或组写权限），否则删除会失败并如实报告。

## 升级

```bash
docker compose pull
docker compose up -d
```

数据库迁移会在 backend 启动时自动执行（alembic），无需手动操作。镜像使用 `:latest` 标签，`pull` 即可获得新版本。

> **不要**用 `curl -o docker-compose.yml` 覆盖本地 compose——它可能含有你的定制（端口、挂载目录、`ENCRYPTION_KEY` 等）。如需获取更新的 compose 模板，先备份本地文件，再手动比对合并修改。
