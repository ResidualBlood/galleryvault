# GalleryVault

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 中文 / English 双语界面。

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

**中文** · [English](README.en.md)

---

## 功能特性

- **本地画廊库**：扫描 Ehviewer 导出目录、CBZ/CBR 文件与普通图片文件夹，建立持久化、可搜索的索引（PostgreSQL）。
- **标签云与搜索**：带命名空间的标签体系（画师、角色、原作、社团、语言、分类、杂项等）、词频加权标签云与即时标签自动补全。
- **标签翻译**：自动获取最新 EhTagTranslation 数据库，中文输入反向匹配翻译表（如输入「巨乳」可提示 `big breasts`）。
- **双语界面**：完整的中文与 English 界面，可随时切换；中文界面下标签显示翻译。
- **ExHentai 集成**：使用自有 cookie（e-hentai.org 或 exhentai.org）获取每个画廊的元数据、分类与标签。
- **下载管理**：类似 Ehviewer 的并发分页下载、实时进度、可续传重试（仅补下缺失页）、部分下载（`max_pages`）、取消与批量重试。
- **收藏夹监控**：监控十个 ExHentai 收藏文件夹，自动下载本地缺失的画廊（定时或手动触发）。
- **阅读器与历史**：逐页流式加载、键盘/空格/点击翻页、预加载后三页、最后一页自动跳转下一画廊、自动保存阅读位置、可浏览的阅读历史。
- **Telegram 通知**：下载成功/失败、扫描完成、收藏同步时发送通知。
- **孤儿清理**：已在 ExHentai 删除的画廊（或无可关联坐标的画廊）自动归入「已删除」分类。
- **安全与隐私**：单密码认证与持久会话，设置安全存储，可选的「免登录」模式。
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
3. 将画廊放入 `./library` 目录（挂载至 `/library`），点击「扫描库」即可开始使用。

> JSON API 位于 **http://\<主机地址\>:8001**。

## 数据与目录

| 路径 | 说明 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史），容器重建后保留 |
| `./library` | **只读库目录**：存放已有画廊归档（Ehviewer 导出、CBZ/CBR），挂载至 `/library`。新下载的画廊不会写入此目录 |
| `./downloads` | **下载目录**：从 ExHentai 下载的画廊存放于此，挂载至 `/downloads`，自动纳入扫描 |
| `./cache` | **缩略图缓存**（自动生成），挂载至 `/gv-cache`，不会写入画廊目录 |

库目录与下载目录在「设置」中分开配置：`library_roots`（只读，每行一个路径）与 `download_root`（下载目标）；下载目录始终会被扫描。更多库目录需在 `docker-compose.yml` 中挂载进容器。

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

## 文档

- [API 参考](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/API.md)
- [使用指南](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/USAGE.md)
- [开发说明](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/DEVELOPMENT.md)

## 免责声明

ExHentai 集成需要您自己的账户 cookie，请合理使用并遵守站点规则与访问频率限制。