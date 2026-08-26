# GalleryVault

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 中文 / English 双语界面。

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)

**中文** · [English](README.en.md) · [📖 在线文档](https://github.com/ResidualBlood/galleryvault/wiki)

---

## 功能特性

- **本地画廊库**：扫描 Ehviewer 导出目录、CBZ/CBR 文件与普通图片文件夹，建立持久化、可搜索的索引（PostgreSQL）。
- **标签云与搜索**：带命名空间的标签体系（画师、角色、原作、社团、语言、分类、杂项等）、词频加权标签云与即时标签自动补全。
- **标签翻译**：自动获取最新 EhTagTranslation 数据库，中文输入反向匹配翻译表（如输入「巨乳」可提示 `big breasts`）。
- **双语界面**：完整的中文与 English 界面，可随时切换；中文界面下标签显示翻译。
- **ExHentai 集成**：使用自有 cookie（e-hentai.org 或 exhentai.org）获取每个画廊的元数据、分类与标签。
- **下载管理**：类似 Ehviewer 的并发分页下载、实时进度、可续传重试（仅补下缺失页）、部分下载（`max_pages`）、取消与批量重试；**下载页**专注展示下载任务状态。
- **日志页面**：统一展示后台任务（库扫描、标签同步、缩略图生成、收藏元数据同步）——上半区为**进行中**任务（开始时间、实时进度条、可取消，多任务并排多行），下半区为**已完成**任务（状态徽标、耗时、完成时间与成败原因），两区按内容自然浮动；页面每 2 秒自动刷新。
- **分页增强**：所有列表分页（浏览/画廊库/标签/历史/下载/收藏夹列表）统一支持每页 **5/20/50/100/200/500** 与**页码输入框直接跳转**（显示 当前页/总页数）。
- **收藏夹监控**：监控十个 ExHentai 收藏文件夹，自动下载本地缺失的画廊（定时或手动触发）；「立即检查所有」一次检查全部收藏夹。
- **收藏夹管理**：每个收藏文件夹独立画廊列表（复选框、批量下载/移除收藏、云端封面内联显示）；详情页可一键取消收藏并显示所属收藏夹；内置**查重扫描**，自动识别同一作品的不同版本（如 DL 版、无修正、语言搬运）并批量取消收藏或删除本地副本，支持**忽略误报**（已忽略项目独立页面可恢复）与分页展示。
- **元数据缓存与自动同步**：收藏夹检查用 gdata 批量接口把画廊的标签/大分类/发布时间/大小缓存进数据库，扫描入库的画廊直接复用缓存免网络；检查后自动把最新元数据应用到本地已下载画廊（tags、分类等），标签始终与 ExHentai 保持同步。
- **阅读器与历史**：逐页流式加载、键盘/空格/点击翻页、预加载后三页、最后一页自动跳转下一画廊、自动保存阅读位置、可浏览的阅读历史。
- **Telegram 通知**：下载成功/失败、扫描完成、收藏同步时发送通知。
- **孤儿清理**：已在 ExHentai 删除的画廊（或无可关联坐标的画廊）自动归入「已删除」分类。
- **安全与隐私**：单密码认证（PBKDF2 高强度哈希）与持久会话、登录限速防暴力破解（按真实客户端 IP）、`/api` 跨域校验与 ExHentai 域名白名单、设置安全存储，可选的「免登录」模式；改密码会**立即撤销所有已登录会话**；后台以非 root 用户运行；可选的**静态加密**（`ENCRYPTION_KEY`，AES-256-GCM）保护 cookie / token / 密码哈希。
- **一键部署**：两个发布的 Docker Hub 镜像与 PostgreSQL，单条 `docker compose up` 即可运行。

## 界面截图

| 中文界面 | English 界面 |
|----------|--------------|
| **画廊库** | **Library** |
| <img src="docs/screenshots/library_zh.png" alt="画廊库界面" width="420"> | <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> |
| **标签云** | **Tag cloud** |
| <img src="docs/screenshots/tags_zh.png" alt="标签云页面" width="420"> | <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> |

## 快速开始

```bash
git clone https://github.com/ResidualBlood/galleryvault
cd galleryvault
docker compose up -d
```

1. 打开 **http://\<主机地址\>:8000** 访问 Web 界面。
2. 使用默认密码 **`p1a2s3s4`** 登录，并在「设置」中修改密码（修改前界面会显示提示横幅）。
3. **建议先配置 ExHentai cookie 并跑一次「收藏夹监控 → 立即检查所有」**，再扫描库目录入库。原因：收藏夹检查会用 gdata 批量接口把收藏过的画廊的**标签、大分类、发布时间、大小**等元数据缓存到数据库；之后扫描入库时，凡收藏夹里见过的画廊会**直接复用这份缓存**，无需再逐画廊请求 ExHentai 同步标签，扫描和标签同步会快得多。
4. 将画廊放入 `./library` 目录（挂载至 `/library`），点击「扫描库」即可开始使用。

> JSON API 位于 **http://\<主机地址\>:8001**。

## 数据与目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **只读库目录**：存放已有画廊归档（Ehviewer 导出、CBZ/CBR），挂载至 `/library`。新下载的画廊不会写入此目录 |
| `./downloads` | **下载目录**：从 ExHentai 下载的画廊存放于此，挂载至 `/downloads`，自动纳入扫描 |
| `./cache` | **缩略图缓存**（自动生成），挂载至 `/gv-cache`，不会写入画廊目录 |

库目录与下载目录在「设置」中分开配置：`library_roots`（只读，每行一个路径）与 `download_root`（下载目标）；下载目录始终会被扫描。

### 将其他 Ehviewer 下载目录作为「仅扫描不下载」的库

如果你有多个存放 Ehviewer 下载内容的目录，想让它们都被扫描、但**新下载只写入** `download_root`，把它们挂载进 backend 容器（建议 `:ro` 只读，防止误写），再在「设置 → 库根目录（只读）」中把容器内路径加进去即可：

```yaml
    volumes:
      - ./library:/library
      - ./downloads:/downloads
      - /mnt/你的/ehviewer下载目录:/Ehviewer2:ro   # 新增
      - ./cache:/gv-cache
```

1. 在 `docker-compose.yml` 的 `backend.volumes` 下追加一行（宿主路径换成你的目录，容器内路径任取，如 `/Ehviewer2`）。
2. 重启 backend（`docker compose up -d backend`）让挂载生效。
3. 在「设置 → 库根目录（只读）」加入该容器内路径（每行一个）并保存。
4. 点击「扫描库」开始索引（保存设置不会自动触发扫描）。

`library_roots` 是只读库根：画廊会被索引、标签同步正常进行，但新下载只会落到 `download_root`，绝不会写入这些目录。容器需能读取宿主目录（权限 ≥ `755`）。

## 配置

所有设置均在「设置」页面完成并持久化到 PostgreSQL，无需手工编辑 `config.json` 或 `.env`：

- **库目录**：每行一个文件系统路径。
- **账户**：修改密码、切换「需要登录」。
- **ExHentai**：基础 URL（e-hentai.org / exhentai.org）、`ipb_member_id` / `ipb_pass_hash` / `igneous` cookie，提供「测试登录」功能。cookie 不会回显。
- **代理**：HTTP 或 SOCKS5。
- **下载**：根目录、并发数、画质、H@H 网络、`max_pages`。
- **标签同步**：扫描/启动后自动同步、间隔与并发数。
- **收藏夹**：自动下载开关与轮询间隔。
- **Telegram**：bot token、chat ID、允许的 user ID，提供「发送测试消息」。
- **翻译**：自动更新间隔与「立即更新」按钮。

敏感信息（cookie、bot token、密码哈希）存储于 PostgreSQL，绝不通过 API 暴露。

### 静态加密（可选）

默认情况下敏感信息在数据库中是**明文**存储的——任何拿到数据库（或备份）的人都能读到。要启用静态加密，为 backend 设置 `ENCRYPTION_KEY` 环境变量（一个足够长的随机串）：

```yaml
    environment:
      ENCRYPTION_KEY: 请改成足够长的随机字符串
```

启用后（下次启动即生效）：

- ExHentai cookies、Telegram bot token、`auth_secret`、密码哈希以 **AES-256-GCM** 加密存储（`enc:v1:...`）；
- 已有明文值在启动时**自动迁移**为密文，无需停机；
- 未设置 `ENCRYPTION_KEY` 时一切照旧（明文存储，行为不变）。

**重要**：密钥必须独立于数据库妥善保管（例如密码管理器）。它与数据库备份分开放置——**密钥丢失后，已加密的 cookie / token / 密码哈希将无法解密**（需用仍含明文的历史备份或原密钥恢复）。

#### 密钥丢失的恢复

`ENCRYPTION_KEY` 丢失后，已加密的值（旧 `enc:v1:` 密文）用新密钥无法解密。cookies / bot token 可以在设置页重新填写覆盖，但 `auth_secret` 与密码哈希没有 API 可重置，必须清掉旧密文让系统重新生成：

```bash
# 1) 停止 backend
docker stop galleryvault-backend
# 2) 重置认证凭据：auth_secret 重新生成、密码回到默认 p1a2s3s4
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "DELETE FROM app_config WHERE key='runtime_auth';"
# 3) 清掉旧密文的 cookies / bot token（之后在设置页重新填写）
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "UPDATE app_config SET value = value - 'exhentai_cookies' - 'telegram_bot_token' WHERE key='user_settings';"
# 4) 换上新的 ENCRYPTION_KEY 并启动
docker start galleryvault-backend
```

启动后使用默认密码 `p1a2s3s4` 登录，然后立即在设置中改密码并重新填写 ExHentai cookies / Telegram token。

> 只要还持有**加密前**的数据库备份，就能直接恢复（还原备份后按上面的流程重新设置密钥），无需上面的清库步骤。

## 备份

数据库是唯一必须备份的状态（画廊索引、设置、历史；缩略图与画廊文件本身可重建）。项目提供 `scripts/backup.sh`，在 `docker-compose.yml` 所在目录运行：

```bash
./scripts/backup.sh        # 生成 backups/galleryvault_<时间戳>.dump，保留最近 14 份
```

推荐通过 cron 每日执行，例如 `0 3 * * * cd /path/to/galleryvault && ./scripts/backup.sh`。恢复：

```bash
docker compose exec -T db pg_restore -U galleryvault -d galleryvault -c --if-exists < backups/galleryvault_<时间戳>.dump
```

## 架构

项目分为两个源码仓库，分别发布本仓库使用的 Docker 镜像：

```
┌────────────┐   :8000   ┌──────────────────────┐   :8001   ┌────────────────┐
│  浏览器     │ ────────▶ │ nginx SPA（原生 JS）  │ ────────▶ │ FastAPI 后端   │ ─▶ PostgreSQL
└────────────┘           │  /api,/login,/logout │           └────────────────┘
                         └──────────────────────┘
```

| 组件 | 源码仓库 | Docker 镜像 | 宿主端口 |
|------|----------|-------------|----------|
| 前端（nginx SPA） | [galleryvault-frontend](https://github.com/ResidualBlood/galleryvault-frontend) | `residualblood/galleryvault-frontend` | **8000** |
| 后端（FastAPI + asyncpg） | [galleryvault-backend](https://github.com/ResidualBlood/galleryvault-backend) | `residualblood/galleryvault-backend` | **8001** |
| 数据库 | — | `postgres:16-alpine` | 内部 |

前端为无第三方依赖的原生 JavaScript 单页应用（无构建步骤、无 CDN）；后端启动时自动执行 Alembic 迁移，升级仅需 `docker compose pull && docker compose up -d`。

### 从源码构建

```bash
git clone https://github.com/ResidualBlood/galleryvault-backend
cd galleryvault-backend
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## 致谢

本项目的画廊格式兼容与翻译功能基于以下开源项目：

- **Ehviewer_CN_SXJ**：Ehviewer 的汉化版（[github.com/xiaojieonly/Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)）。本项目的画廊导出目录结构与命名约定（`<gid>-<标题>`、`.ehviewer` 元数据文件、`.thumb` 缩略图）、并发分页下载与断点续传，以及中文标签翻译的反向检索，均参考其实现。
- **EhTagTranslation**：标签翻译数据库与更新机制（[github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)）。
- **ehsyringe（e 站注射器）**：翻译数据的整理与导出格式。

后端基于以下开源组件构建：

- **FastAPI**、**Starlette**、**Uvicorn** —— Web 框架与 ASGI 服务器
- **SQLAlchemy**、**asyncpg**、**Alembic** —— 数据库 ORM、驱动与迁移
- **httpx** —— 异步 HTTP 客户端
- **Pydantic** —— 数据校验与配置

基础设施：**PostgreSQL**、**nginx**、**Docker**。

## 公网部署安全建议

若将实例暴露到公网，请务必：

1. **配置强密码并开启登录限速**：默认密码 `p1a2s3s4` 只供内网首次使用，公网部署前请在「设置」修改密码。登录接口已内置**限速**（每 IP 每 60 秒 10 次），nginx 也按客户端 IP 对 `/login`（10 次/分）与 `/api`（30 次/秒）限流。
2. **启用 TLS**：建议在 nginx 前置 Caddy/反代做 HTTPS 终结，并设置环境变量 `AUTH_COOKIE_SECURE=true`，否则登录密码与会话 cookie 会明文传输。启用 TLS 后建议加 HSTS 头。
3. **只暴露 8000 端口**：`docker-compose.yml` 已把后端 8001 绑定到 `127.0.0.1`（仅本机可达），不要改回 `8001:8001` 直暴露；API 一律经前端 nginx 反代访问。
4. **内置安全防线**（无需配置）：登录限速、`/api` 写请求跨域 Origin 校验、`exhentai_base_url` 域名白名单（仅 `exhentai.org` / `e-hentai.org`）、会话 cookie `HttpOnly + SameSite=Lax`、PBKDF2-SHA256(31 万次迭代) 密码哈希。
5. **建议**：容器以非 root 运行、为 PostgreSQL 设置独立强口令、`downloads/library` 目录避免挂载到系统关键路径。

## 文档

- [API 参考](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/API.md)
- [使用指南](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/USAGE.md)
- [开发说明](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/DEVELOPMENT.md)

## 免责声明

ExHentai 集成需要您自己的账户 cookie，请合理使用并遵守站点规则与访问频率限制。