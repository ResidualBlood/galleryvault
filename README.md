# GalleryVault

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 **中文 / English** 双语界面。

[![Backend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)

**中文** · [English](README.en.md) · [📖 在线文档](https://github.com/ResidualBlood/galleryvault/wiki)

---

## 快速开始

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. 执行 `docker compose up -d` 启动服务。
2. 打开 **http://<主机地址>:8000** 访问 Web 界面（JSON API 位于 `:8001`）。
3. 使用默认密码 **`p1a2s3s4`** 登录，并在「设置」中修改密码。
4. 将画廊放入 `./library`（挂载至 `/library`），点击「扫描库」即可开始使用。

> 如需与 ExHentai 同步元数据或下载画廊，请在「设置 → ExHentai」配置账户 Cookie；获取与配置说明见 [Wiki 使用指南](https://github.com/ResidualBlood/galleryvault/wiki/Usage)。

## 界面截图

| 中文界面 | English 界面 |
|----------|--------------|
| **画廊库** | **Library** |
| <img src="docs/screenshots/library_zh.png" alt="画廊库界面" width="420"> | <img src="docs/screenshots/library_en.png" alt="Library UI" width="420"> |
| **标签云** | **Tag cloud** |
| <img src="docs/screenshots/tags_zh.png" alt="标签云页面" width="420"> | <img src="docs/screenshots/tags_en.png" alt="Tag cloud page" width="420"> |
| **收藏夹查重** | **Favorites dedupe** |
| <img src="docs/screenshots/fav_dedupe_zh.png" alt="收藏夹查重页面" width="420"> | <img src="docs/screenshots/fav_dedupe_en.png" alt="Favorites dedupe page" width="420"> |

## 文档

完整文档见 **[GitHub Wiki](https://github.com/ResidualBlood/galleryvault/wiki)**：

- **[使用指南](https://github.com/ResidualBlood/galleryvault/wiki/Usage)** — 浏览搜索、阅读器、下载管理、收藏夹与查重、PWA 与设置
- **[部署指南](https://github.com/ResidualBlood/galleryvault/wiki/Deployment)** — Docker Compose 部署、目录挂载、权限配置、静态加密、安全加固与备份
- **[API 与开发](https://github.com/ResidualBlood/galleryvault/wiki/API)** — REST API 规范参考与 [开发指南](https://github.com/ResidualBlood/galleryvault/wiki/Development)

## 致谢

- **Ehviewer_CN_SXJ**（[github.com/xiaojieonly/Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)）：目录结构与下载规范参考。
- **EhTagTranslation**（[github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)）：标签翻译数据库与更新机制。
- **ehsyringe**（[github.com/EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)）：翻译数据整理与格式导出。

## 免责声明

ExHentai 集成需要您自己的账户 Cookie，请合理使用并遵守站点规则与访问频率限制。
