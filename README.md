# GalleryVault

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 **中文 / English** 双语界面。

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)

**中文** · [English](README.en.md) · [📖 在线文档](https://github.com/ResidualBlood/galleryvault/wiki)

---

## 功能特性

- **本地画廊库**：扫描 Ehviewer 导出目录 / CBZ/CBR / 图片文件夹，建立可搜索的本地索引（PostgreSQL）；多目录同 gid 自动去重。
- **搜索与标签**：多标签 AND 叠加筛选、`标签+文字`混输、中文标签翻译与反向检索、双语界面。
- **ExHentai 集成**：自有 cookie 同步元数据与标签；收藏夹监控自动下载与查重；画廊重传自动更新；一键打开原站。
- **下载管理**：Ehviewer 风格并发下载、断点续传、失败自动重试；ExHentai 归档（zip，GP 换速度，断点续传不重复扣 GP）；下载完即入库；Telegram 通知与 bot 命令。
- **阅读器与界面**：流式阅读器（全屏/自动跳下一本）、阅读历史、任务日志、首次运行向导。
- **安全与运维**：PBKDF2 认证、可选静态加密（AES-256-GCM）、非 root 运行；单命令部署与一键备份。

## 界面截图

| 中文界面 | English 界面 |
|----------|--------------|
| **画廊库** | **Library** |
| <img src="docs/screenshots/library_zh.png" alt="画廊库界面" width="420"> | <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> |
| **标签云** | **Tag cloud** |
| <img src="docs/screenshots/tags_zh.png" alt="标签云页面" width="420"> | <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> |
| **收藏夹查重** | **Favorites dedupe** |
| <img src="docs/screenshots/fav_dedupe_zh.png" alt="收藏夹查重页面" width="420"> | <img src="docs/screenshots/fav_dedupe_en.png" alt="Favorites dedupe page" width="420"> |

## 快速开始

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. 打开 **http://\<主机地址\>:8000** 访问 Web 界面。
2. 使用默认密码 **`p1a2s3s4`** 登录，并在「设置」中修改密码。
3. （可选）先配置 ExHentai cookie 并「收藏夹 → 立即检查所有」，把收藏元数据缓存进库，之后扫描快得多。
4. 将画廊放入 `./library`（挂载至 `/library`），点击「扫描库」即可开始使用。

> 首次启动时 Docker 会自动创建 `./library`、`./downloads`、`./cache`、`./db-data` 目录；下载的 `docker-compose.yml` 可按需定制（端口、挂载目录、`ENCRYPTION_KEY` 等）。

> JSON API 位于 **http://\<主机地址\>:8001**。

### 获取 ExHentai cookie（ipb_member_id / ipb_pass_hash / igneous）

1. 浏览器登录 **e-hentai.org**（需 e-hentai 账户），按 `F12` → **Application → Storage → Cookies**，从 `https://e-hentai.org` 复制 **`ipb_member_id`** 与 **`ipb_pass_hash`**。
2. 需要访问 **exhentai.org 里站**（未和谐画廊/部分专区）时，再从 `https://exhentai.org` 的 Cookies 复制 **`igneous`**（仅已获里站权限的账户存在；只用外站可跳过）。
3. 填入「设置 → ExHentai」（或首次运行向导）并「测试登录」验证；cookie 加密存库、不会回显。

### 推荐使用流程

先缓存收藏元数据（「仅监控」+「立即检查所有」）→ 扫描库 → 收藏夹查重 → 强制下载补齐 → 切回增量自动跟进。完整步骤见 [Wiki → 使用指南](https://github.com/ResidualBlood/galleryvault/wiki/Usage)。

### 适用范围

- **原生支持** Ehviewer 家族客户端（`.ehviewer` 格式，含各主流 Fork，完全兼容）与 [JHenTai](https://github.com/jiangtian616/JHenTai)（`metadata`）的下载目录，扫描即精确还原画廊身份；CBZ/CBR 与无 `.ehviewer` 的图片文件夹降级支持（无 gid 的画廊可浏览，但无法参与下载/查重）。完整兼容列表见 [Wiki → 首页](https://github.com/ResidualBlood/galleryvault/wiki/Home)。
- 下载器写目录时还会额外生成 `.galleryvault.json`（category/title/tags）sidecar，扫描与重建可读取。

## 数据与目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **库目录**：已有画廊归档，挂载至 `/library`，新下载不会写入；删除画廊时若挂载可写会一并删除这里对应文件 |
| `./downloads` | **下载目录**：从 ExHentai 下载的画廊，挂载至 `/downloads`，自动纳入扫描 |
| `./cache` | **缩略图缓存**（自动生成），挂载至 `/gv-cache` |

库目录（每行一个路径）与下载目录在「设置」中分开配置；把其他 Ehviewer 下载目录挂载为**仅扫描不下载**的库，见 [Wiki → 部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment)。

> **权限**：backend 容器内以 `app` 用户（uid **10001**）运行。挂载已有目录或放入归档前，确保宿主目录对 10001 **可读**（删除画廊需**可写**）：首次启动前 `chown -R 10001:10001 ./library ./downloads`。`./cache` 自动处理；**`./db-data` 属 postgres（uid 999），切勿 chown**。

## 升级

```bash
docker compose pull
docker compose up -d
```

数据库迁移在 backend 启动时自动执行（alembic），无需手动操作；镜像使用 `:latest` 标签，`pull` 即可获得新版本。

> **不要**用 `curl -o docker-compose.yml` 覆盖本地 compose——它可能含有你的定制（端口、挂载目录、`ENCRYPTION_KEY` 等）。如需获取更新的 compose 模板，先备份本地文件，再手动比对合并修改。

## 安全

默认密码 `p1a2s3s4` 仅供内网首次使用，公网部署前请在「设置」修改。后端 API 默认仅绑定 `127.0.0.1:8001`；可选**静态加密**（`ENCRYPTION_KEY`，AES-256-GCM）保护 cookie / token / 密码哈希，密钥请与数据库备份分开保管。公网部署检查清单、TLS 与密钥丢失恢复见 [Wiki → 部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) 与 [Wiki → 静态加密](https://github.com/ResidualBlood/galleryvault/wiki/Encryption)。

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

前端为无第三方依赖的原生 JavaScript SPA（无构建、无 CDN）；后端启动时自动执行 Alembic 迁移，升级仅需 `docker compose pull && docker compose up -d`。

## 文档

完整文档见 **[📖 Wiki](https://github.com/ResidualBlood/galleryvault/wiki)**：

- [部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) — compose、数据目录、库挂载、安全加固、TLS、升级
- [使用指南](https://github.com/ResidualBlood/galleryvault/wiki/Usage) — 浏览、阅读器、标签、下载、收藏夹、日志、设置
- [备份与恢复](https://github.com/ResidualBlood/galleryvault/wiki/Backup)
- [静态加密](https://github.com/ResidualBlood/galleryvault/wiki/Encryption) — ENCRYPTION_KEY 与密钥丢失恢复
- [API 参考](https://github.com/ResidualBlood/galleryvault/wiki/API)
- [开发指南](https://github.com/ResidualBlood/galleryvault/wiki/Development)
- [常见问题](https://github.com/ResidualBlood/galleryvault/wiki/FAQ)
- [界面截图](https://github.com/ResidualBlood/galleryvault/wiki/Screenshots) — 各主要页面中英文界面一览

产品讨论与反馈：[Discussions](https://github.com/ResidualBlood/galleryvault/discussions)

## 致谢

- **Ehviewer_CN_SXJ**（[github.com/xiaojieonly/Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)）：画廊导出目录结构与命名约定、并发分页下载与断点续传、中文标签翻译反向检索的实现参考。
- **EhTagTranslation**（[github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)）：标签翻译数据库与更新机制。
- **ehsyringe**：翻译数据的整理与导出格式。

后端基于 **FastAPI / Starlette / Uvicorn**、**SQLAlchemy / asyncpg / Alembic**、**httpx**、**Pydantic** 构建；基础设施为 **PostgreSQL、nginx、Docker**。

## 免责声明

ExHentai 集成需要您自己的账户 cookie，请合理使用并遵守站点规则与访问频率限制。
