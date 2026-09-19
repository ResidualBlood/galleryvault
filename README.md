<div align="center">

<img src="frontend/assets/icon.svg" alt="GalleryVault Logo" width="96" height="96">

# GalleryVault

**面向 Ehviewer 导出目录的自托管画廊库**

[![Backend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml)
[![Frontend CI](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml)
[![Docker](https://img.shields.io/badge/docker-images-blue?logo=docker)](https://hub.docker.com/u/residualblood)
[![Wiki](https://img.shields.io/badge/docs-wiki-9cf?logo=github)](https://github.com/ResidualBlood/galleryvault/wiki)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

[快速开始](#快速开始) · [功能特性](#功能特性) · [Wiki](https://github.com/ResidualBlood/galleryvault/wiki) · [English](README.en.md)

</div>

---

挂载 Ehviewer 导出的目录即可在浏览器中浏览，无需改名或重新打包。配置 Cookie 后可使用发现页、同步十个收藏夹并下载；未配置时仍可作为本地库使用。文件始终保存在本机。

## 功能特性

📁 **目录扫描** — 支持 `<gid>-标题/`、`.ehviewer`（SpiderInfo V1/V2）、JHenTai `metadata`，以及 CBZ/CBR、7z（仅提取图片）、PDF。新下载写入 `downloads/`，不修改 library。

⭐ **收藏夹与发现页** — 十个收藏夹可增量下载或仅监控。发现页提供 Popular、Watched、Toplist。画廊重传导致 GID 变化时，可一键替换本地旧版本。

🧹 **查重、缺页与冷归档** — 同一 GID 的多份副本、收藏夹内重复项、跨 GID 聚类（不同汉化或画质），以及系列分组、缺页与坏图检查。额外磁盘可写入冷归档 CBZ。

📖 **阅读器** — 支持从右向左、双页、条漫。幻灯片跟随 GIF/WebP 帧时长。可通过 OPDS 在 Tachiyomi / Mihon 中阅读。可选 Telegram Bot：发送画廊 URL 即可入队。

🔐 **加密** — 设置 `ENCRYPTION_KEY` 后，Cookie、bot token 与密码哈希以 AES-256-GCM 存储。修改密码会撤销全部会话。

<p align="center">
  <img src="docs/screenshots/library_zh.png" alt="画廊库" width="270">
  <img src="docs/screenshots/reader_zh.png" alt="阅读器" width="270">
  <img src="docs/screenshots/fav_dedupe_zh.png" alt="收藏夹查重" width="270">
</p>

更多截图：[Wiki · 界面截图](https://github.com/ResidualBlood/galleryvault/wiki/Screenshots)

## 快速开始

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. 打开 `http://<主机IP>:8000`（API 绑定 `127.0.0.1:8001`，由前端反向代理）。
2. 默认密码 **`p1a2s3s4`**。首次登录进入 `#/welcome`，必须修改密码。
3. 将已有画廊放入 `./library`，在画廊库中点击 **扫描库**。之后的下载写入 `./downloads`，不会写入 library。

### 目录

| 本地路径 | 容器内 | 说明 |
| :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql` | PostgreSQL 18 数据目录（进程 UID 999，请勿 chown。**不要使用旧路径 `/var/lib/postgresql/data`，不要设置 `PGDATA`**） |
| `./library` | `/library` | 已有画廊。下载不会写入此目录。只读挂载时删除会失败并记录日志 |
| `./downloads` | `/downloads` | 新下载目录，完成后立即入库 |
| `./cache` | `/gv-cache` | 缩略图与封面缓存 |
| `./archive` | `/archive` | 可选；compose 中默认注释。启用后在设置中填写 `archive_roots`（每行一个容器路径） |

冷归档：取消注释 `- ./archive:/archive`，在设置中保存 `archive_roots`，然后到 **管理 → 冷库归档**（`#/archive`）执行打包。CBZ 文件名格式为 `gid-英文标题.cbz`。多盘分配与源目录清理见 [部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment)。

### 环境变量

在 `docker-compose.yml` 的 backend `environment` 中设置：

- `ENCRYPTION_KEY`：任意足够长的随机字符串（不是 32 字节 Hex）。启用后 Cookie、bot token、密码哈希以 AES-256-GCM 存储。密钥丢失后密文无法解密，见 [加密](https://github.com/ResidualBlood/galleryvault/wiki/Encryption)。
- `AUTH_SECRET`：会话签名密钥。未设置时，首次启动会生成并写入数据库。
- `PUID` / `PGID`：用于 NAS 环境，避免下载文件属主为 root。
- `TRUSTED_PROXIES`：反向代理网段，例如 `127.0.0.1,192.168.1.0/24`。
- `POSTGRES_PASSWORD`：数据库密码，默认 `galleryvault`。

库根、下载根、归档根与并发仅在 Web 设置中修改。连接池等见 [部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment)。

## 文档

| 文档 | 说明 |
| ---- | ---- |
| [入门](https://github.com/ResidualBlood/galleryvault/wiki/Usage) | 向导、Cookie、界面导航 |
| [功能](https://github.com/ResidualBlood/galleryvault/wiki/Features) | 功能说明 |
| [部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) | 挂载、Nginx/Caddy、归档存储 |
| [库维护](https://github.com/ResidualBlood/galleryvault/wiki/Manage) | 查重、缺页、冷归档 |
| [兼容](https://github.com/ResidualBlood/galleryvault/wiki/Compatibility) | Ehviewer 家族、JHenTai、OPDS |
| [FAQ](https://github.com/ResidualBlood/galleryvault/wiki/FAQ) | 常见问题 |

反馈：[Discussions](https://github.com/ResidualBlood/galleryvault/discussions) · [Issues](https://github.com/ResidualBlood/galleryvault/issues)

## 鸣谢

- [Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ) — 目录结构与 SpiderInfo 约定
- [EhTagTranslation](https://github.com/EhTagTranslation/Database) — 标签翻译词库
- [EhSyringe](https://github.com/EhTagTranslation/EhSyringe) — 翻译数据整理

## 免责声明

本软件用于在私有设备上整理媒体，可能涉及成人内容。**仅供达到法定成年年龄且当地法律允许的使用者。** GalleryVault 不托管、不分发任何媒体文件。访问 E-Hentai / ExHentai 需要使用者自有 Cookie。检索、下载与存储的法律责任由使用者承担。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ResidualBlood/galleryvault&type=Date)](https://star-history.com/#ResidualBlood/galleryvault&Date)

---

<div align="center">

如果 GalleryVault 对你有帮助，欢迎点一个 ⭐ Star

Made with ❤️ by [ResidualBlood](https://github.com/ResidualBlood/)

</div>
