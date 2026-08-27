# GalleryVault

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 **中文 / English** 双语界面。

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)

**中文** · [English](README.en.md) · [📖 在线文档](https://github.com/ResidualBlood/galleryvault/wiki)

---

## 功能特性

- **本地画廊库**：扫描 Ehviewer 导出目录、CBZ/CBR 文件与普通图片文件夹，建立持久化、可搜索的索引（PostgreSQL）。
- **标签云与搜索**：带命名空间的标签体系、词频加权标签云、即时搜索联想补全；**点击标签（标签云或画廊详情页）即可筛选出所有含该标签的画廊**。
- **标签翻译**：自动获取最新 EhTagTranslation 数据库，中文输入反向匹配翻译表（如输入「巨乳」可提示 `big breasts`）。
- **双语界面**：完整的中文与 English 界面，可随时切换；中文界面下标签显示翻译。
- **ExHentai 集成**：使用自有 cookie（e-hentai.org 或 exhentai.org）获取每个画廊的元数据、分类与标签。
- **下载管理**：类似 Ehviewer 的并发分页下载、实时进度、可续传重试、部分下载（`max_pages`）、取消与批量重试；下载完成**自动增量入库**（含标签/封面，无需全量扫描）。
- **收藏夹监控与管理**：监控十个 ExHentai 收藏文件夹自动下载、独立列表、查重扫描与忽略误报。
- **元数据缓存与自动同步**：收藏夹检查用 gdata 批量接口缓存标签/分类/发布时间/大小，扫描入库直接复用；检查后自动把最新元数据应用到本地画廊。
- **阅读器与历史**：逐页流式加载、键盘/空格/点击翻页、预加载后三页、最后一页自动跳转下一画廊、自动保存阅读位置。
- **日志页面**：统一展示后台任务（扫描/标签同步/缩略图/收藏元数据）进行中与已完成状态，可取消。
- **首次运行向导**：新部署登录后自动进入三步引导（改密码 → 连 ExHentai → 扫描库），可随时在 `#/welcome` 重看。
- **Telegram 通知**：下载成功/失败、扫描完成、收藏同步时发送通知。
- **安全与隐私**：PBKDF2 认证、登录限速、跨域校验与域名白名单、非 root 运行、可选的**静态加密**（`ENCRYPTION_KEY`，AES-256-GCM）；改密码立即撤销所有会话。
- **一键部署**：两个 Docker Hub 镜像 + PostgreSQL，单条 `docker compose up` 即可运行。

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
3. **建议先配置 ExHentai cookie 并跑一次「收藏夹 → 立即检查所有」**，把收藏过的画廊的元数据缓存进数据库，之后扫描入库会直接复用缓存，标签同步快得多。
4. 将画廊放入 `./library` 目录（挂载至 `/library`），点击「扫描库」即可开始使用。

> 首次启动时 Docker 会自动创建 `./library`、`./downloads`、`./cache`、`./db-data` 目录；下载的 `docker-compose.yml` 可按需定制（端口、挂载目录、`ENCRYPTION_KEY` 等）。

> JSON API 位于 **http://\<主机地址\>:8001**。

## 数据与目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **只读库目录**：已有画廊归档，挂载至 `/library`，新下载不会写入 |
| `./downloads` | **下载目录**：从 ExHentai 下载的画廊，挂载至 `/downloads`，自动纳入扫描 |
| `./cache` | **缩略图缓存**（自动生成），挂载至 `/gv-cache` |

库目录（只读，每行一个路径）与下载目录在「设置」中分开配置；把其他 Ehviewer 下载目录挂载为**仅扫描不下载**的库，见 [Wiki → 部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment)。

## 升级

```bash
docker compose pull
docker compose up -d
```

数据库迁移在 backend 启动时自动执行（alembic），无需手动操作；镜像使用 `:latest` 标签，`pull` 即可获得新版本。

> **不要**用 `curl -o docker-compose.yml` 覆盖本地 compose——它可能含有你的定制（端口、挂载目录、`ENCRYPTION_KEY` 等）。如需获取更新的 compose 模板，先备份本地文件，再手动比对合并修改。

## 安全

默认密码 `p1a2s3s4` 只供内网首次使用，公网部署前请在「设置」修改。后端 API 默认仅绑定 `127.0.0.1:8001`；可选启用**静态加密**（`ENCRYPTION_KEY`，保护 cookie / token / 密码哈希）。给 PostgreSQL 设置独立强口令（`.env` 中 `POSTGRES_PASSWORD`）并妥善保管 `ENCRYPTION_KEY`。公网部署检查清单、TLS 与密钥丢失恢复见 [Wiki → 部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) 与 [Wiki → 静态加密](https://github.com/ResidualBlood/galleryvault/wiki/Encryption)。

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

- [部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) — compose、数据目录、只读库挂载、安全加固、TLS、升级
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
