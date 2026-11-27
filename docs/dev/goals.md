# GalleryVault 项目目标

> 一句话定位与边界；功能细节见 wiki [功能特性](../wiki/Features.md) 与 [首页](../wiki/Home.md)。

## 定位

GalleryVault 是面向 Ehviewer 导出目录的**自托管画廊库**：文件、索引与收藏关系保存在本机或 NAS，未配置 Cookie 时可作纯本地库，配置 Cookie 后启用在线发现、收藏夹同步、画廊下载与更新检测（`docs/wiki/Home.md:5`）。

## 能力边界

- **本地能力**：直接挂载 Ehviewer `<gid>-标题/` 目录、CBZ/CBR、7z（提取图片）、PDF，读取 SpiderInfo/sidecar 元数据，无需解压或重命名。
- **联网能力**（需 Cookie）：在线浏览/阅读（浏览器直连 H@H，代理按设备回退）、10 个收藏夹同步、逐页与官方 Archive 整包下载、重传更新检测与换 GID 迁移。
- **维护与归档**：同 GID 副本清理、收藏夹查重、跨 GID 查重、缺页/坏图体检、多盘冷库 CBZ 归档。
- **阅读与扩展**：RTL/双页/条漫阅读器 + 动图幻灯片；OPDS、静态加密、Telegram Bot 远程控制。

## 非目标（明确不做）

- 不是通用网盘/相册：只面向 E-Hentai 生态的画廊与收藏。
- 不做多用户：单一管理员账号，密码唯一。
- 不做云端托管：数据留在用户本机/NAS。

## 约束

- 仓库公开：文档、截图、代码不得含私人信息（内网 IP、域名、主机名、本机路径、邮箱、凭据）；示例用 `<NAS-IP>`、`example.com` 占位。
- 最小改动、范围先确认（AGENTS.md）。
- 生产默认不动，人授权才操作生产（AGENTS.md 铁律）。

## 技术选型（现状）

- 后端：FastAPI + SQLAlchemy 2.x + PostgreSQL 18 + Alembic（`backend/pyproject.toml`）。
- 前端：Vue 3 + Vite + TypeScript + Pinia + vue-router + vue-i18n（`frontend/package.json`）。
- 部署：AMD64/ARM64 双架构镜像，`docker compose`（根 `docker-compose.yml`）。
