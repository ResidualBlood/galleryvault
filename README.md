# 📚 GalleryVault

> 一个私有的、自托管的本地画廊库管理器 —— 内置 ExHentai 下载、标签同步与翻译。

GalleryVault 将 **Ehviewer 导出目录、CBZ/CBR 压缩包和普通图片文件夹** 索引成一个可搜索的 Web 画廊库，并可选地 **从 ExHentai 同步标签与元数据**、**下载画廊**、**监控你的收藏夹**、**翻译每个标签**——全部在一个简洁的密码保护界面之后，支持 中文/English 双语。

[![Backend CI](https://github.com/ResidualBlood/galleryvault-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-backend/actions)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault-frontend/actions/workflows/ci.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault-frontend/actions)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)

**中文（默认）** · [English](README.en.md)

---

## 界面截图

| 中文界面 | 英文界面 |
|----------|----------|
| **画廊库** | **Library** |
| <img src="docs/screenshots/library_zh.png" alt="画廊库界面" width="420"> | <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> |
| **标签云** | **Tag cloud** |
| <img src="docs/screenshots/tags_zh.png" alt="标签云页面" width="420"> | <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> |

---

## ✨ 功能特性

| | |
|---|---|
| 🗂️ **本地画廊库** | 将 Ehviewer 导出目录、CBZ/CBR 文件和普通图片文件夹扫描进一个持久化、可搜索的索引（PostgreSQL）。 |
| 🏷️ **标签云与搜索** | 带命名空间的标签（画师/角色/原作/社团/语言/分类/杂项…）、按词频加权的标签云、即时标签自动补全。 |
| 🌐 **标签翻译** | 自动拉取最新 EhTagTranslation 数据库——中文输入反向匹配翻译表，输入"巨乳"会提示 `big breasts`。 |
| 🆎 **双语界面** | 完整的中文和 English 界面，随时切换；中文界面下标签显示翻译。 |
| 🌠 **ExHentai 集成** | 用你自己的 cookie（表站或里站）登录，为每个画廊获取元数据、分类和标签。 |
| ⬇️ **下载管理器** | 类似 Ehviewer 的并发分页下载、实时进度条、可续传重试（只补下缺失页）、部分下载（`max_pages`）、取消与批量重试。 |
| ⭐ **收藏夹监控** | 监控你的十个 ExHentai 收藏文件夹，自动下载还没有的画廊——定时或手动触发。 |
| 📖 **阅读器与历史** | 逐页流式加载、自动保存阅读进度、可浏览的阅读历史。 |
| 🔔 **Telegram 通知** | 下载成功/失败、扫描完成、收藏同步时发送通知。 |
| 🗑️ **孤儿清理** | 从 ExHentai 删除的画廊（或无坐标的画廊）自动归入 **已删除** 分类。 |
| 🔒 **私有且简单** | 单密码认证 + 持久会话、安全的设置存储、可选的"免登录"模式。 |
| 🐳 **一键部署** | 两个发布的 Docker Hub 镜像 + PostgreSQL，一条 `docker compose up` 启动。 |

---

## 快速开始

```bash
git clone https://github.com/ResidualBlood/galleryvault
cd galleryvault
docker compose up -d
```

1. 打开 **http://\<主机地址\>:8000** —— Web 界面。
2. 使用默认密码 **`p1a2s3s4`** 登录，并在 *设置* 中修改（在修改前会有横幅提醒）。
3. 把画廊放进 `./library`（挂载到 `/library`），点击 **扫描库**，开始阅读。

> JSON API 位于 **http://\<主机地址\>:8001**。

---

## 数据与目录

| 路径 | 用途 |
|------|------|
| `./db-data` | PostgreSQL 数据（索引、设置、历史）——容器重建后依然保留 |
| `./library` | 你的画廊压缩包/目录（挂载到 `/library`，默认被扫描） |
| `./downloads` | 从 ExHentai 下载的画廊（挂载到 `/downloads`） |

更多库目录请在 *设置 → 库目录* 中添加（每个路径都需要在 `docker-compose.yml` 中挂载进容器）。

---

## 配置

没有需要手工编辑的 **`config.json` 或 `.env`**。所有设置都在 *设置* 页面中，并持久化到 PostgreSQL：

- **库目录** —— 每行一个文件系统路径。
- **账户** —— 修改密码、切换 *需要登录*。
- **ExHentai** —— 基础 URL（表站/里站）、`ipb_member_id` / `ipb_pass_hash` / `igneous` cookie，带 **测试登录** 按钮。cookie 永远不会被回显。
- **代理** —— HTTP 或 SOCKS5。
- **下载** —— 根目录、并发数、画质、H@H 网络、`max_pages`。
- **标签同步** —— 扫描/启动后自动同步、间隔、并发数。
- **收藏夹** —— 自动下载开关与轮询间隔。
- **Telegram** —— bot token、chat ID、允许的 user ID、**发送测试消息**。
- **翻译** —— 自动更新间隔与 **立即更新** 按钮。

敏感信息（cookie、bot token、密码哈希）存储在 PostgreSQL 中，绝不会通过 API 暴露。

---

## 架构

项目拆分为两个源码仓库，发布这里使用的 Docker 镜像：

```
┌────────────┐   :8000   ┌──────────────────────┐   :8001   ┌────────────────┐
│  浏览器     │ ────────▶ │ nginx SPA（原生 JS）  │ ────────▶ │ FastAPI 后端   │ ─▶ PostgreSQL
└────────────┘           │  /api,/login,/logout │           └────────────────┘
                         └──────────────────────┘
```

| 组件 | 仓库 | Docker 镜像 | 宿主端口 |
|------|------|-------------|----------|
| 前端（nginx SPA） | [galleryvault-frontend](https://github.com/ResidualBlood/galleryvault-frontend) | `residualblood/galleryvault-frontend` | **8000** |
| 后端（FastAPI + asyncpg） | [galleryvault-backend](https://github.com/ResidualBlood/galleryvault-backend) | `residualblood/galleryvault-backend` | **8001** |
| 数据库 | — | `postgres:16-alpine` | 内部 |

前端是无依赖的原生 JS 单页应用（无构建步骤、无 CDN）；后端启动时自动运行 Alembic 迁移，升级只需一条 `docker compose pull && docker compose up -d`。

### 从源码构建

```bash
git clone https://github.com/ResidualBlood/galleryvault-backend
cd galleryvault-backend
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

---

## 使用亮点

- **画廊库**（`#/library`）—— 按标题搜索、按分类筛选、页码大小选择（5…500）、批量删除（可选删除磁盘文件）、基于标签的自动补全筛选。
- **标签**（`#/tags`）—— 命名空间标签页、词频加权标签云、使用次数统计、点击标签下钻到画廊库。
- **画廊详情**（`#/gallery/<id>`）—— 元数据、翻译后的标签、页面缩略图、**立即阅读**、**同步标签**。
- **阅读器**（`#/reader/<id>/<page>`)—— 方向键翻页、自动保存阅读位置。
- **下载**（`#/downloads`）—— 实时进度、取消/重试、批量操作。
- **收藏夹**（`#/favorites`）—— 十个收藏文件夹的模式与调度。

---

## 文档

- [API 参考](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/API.md)
- [使用指南](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/USAGE.md)
- [开发说明](https://github.com/ResidualBlood/galleryvault-backend/blob/main/docs/DEVELOPMENT.md)

---

## 免责声明

请合理使用。ExHentai 集成需要 **你自己的** 账户 cookie，并应遵守站点的规则与频率限制。