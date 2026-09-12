# GalleryVault

<p align="center">
  <img src="frontend/assets/icon.svg" alt="GalleryVault Logo" width="96" height="96">
</p>

<p align="center">
  <strong>自托管画廊库</strong><br>
  扫描 Ehviewer 导出目录与 CBZ · 可选同步 E-Hentai / ExHentai 收藏 · 本机阅读
</p>

<p align="center">
  <a href="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml"><img src="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg" alt="Backend CI"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml"><img src="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg" alt="Frontend CI"></a>
  <a href="https://hub.docker.com/u/residualblood"><img src="https://img.shields.io/badge/docker-images-blue?logo=docker" alt="Docker"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/wiki"><img src="https://img.shields.io/badge/docs-wiki-9cf?logo=github" alt="Wiki"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

<p align="center">
  <strong>中文</strong> · <a href="README.en.md">English</a> · <a href="https://github.com/ResidualBlood/galleryvault/wiki">Wiki</a>
</p>

---

文件、索引和收藏关系都在你自己的机器或 NAS 上。不配 Cookie 也能当本地库用；配了 Cookie 才能逛发现页、同步收藏夹、下载。

| 页面 | 路由 | 做什么 |
| :--- | :--- | :--- |
| 浏览 / 画廊库 / 标签 | `#/browse` `#/library` `#/tags` | 扫库、筛选、搜索、无限滚动 |
| 系列 | `#/series` | 按标题聚类同人/漫画，可手工改组成员 |
| 发现 | `#/discover` | 在线逛 Popular / Watched / Toplist（要 Cookie） |
| 收藏 / 更新 | `#/favorites` `#/updates` | 十个收藏夹监控、增量下载、重传换 GID |
| 下载 | `#/downloads` | 逐页或官方 Archive zip；失败指数退避 |
| 管理 | `#/recycle` | 回收站、同 GID 副本、收藏夹重复、跨 GID（查重系列 `#/duplicates`）、缺页体检（`#/integrity`）、冷归档（`#/archive`） |
| 阅读器 | `#/reader/...` | RTL / 双页 / 条漫；GIF/WebP 幻灯片跟帧时长 |
| 设置 / 日志 | `#/settings` `#/logs` | 路径、并发、加密会话、后台任务 |

也支持：本地列表与星级、OPDS（Tachiyomi / Mihon 等）、可选 AES-256-GCM 把 Cookie 等字段加密落库、可选 Telegram Bot（粘贴 URL 入队、队列 InlineKeyboard、扫库/配额/本地检索）。

截图见 [Wiki · 界面截图](https://github.com/ResidualBlood/galleryvault/wiki/Screenshots)。

---

## 快速开始

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. 打开 `http://<主机IP>:8000`（API 只绑 `127.0.0.1:8001`，经前端反代）。
2. 默认密码 **`p1a2s3s4`**。首次登录会进 `#/welcome`，必须改密。
3. 把已有画廊放到 `./library`，在画廊库点 **扫描库**。下载会写入 `./downloads`，不会写进 library。

### 目录

| 本地路径 | 容器内 | 说明 |
| :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql` | PostgreSQL 18（容器 UID 999，不要 chown 成自己。**切勿配置旧路径 `/var/lib/postgresql/data`，切勿设置 PGDATA 环境变量**） |
| `./library` | `/library` | 已有库；下载不写这里。只读挂载时删文件会失败并记日志 |
| `./downloads` | `/downloads` | 新下载落盘并即时入库 |
| `./cache` | `/gv-cache` | 缩略图 / 封面缓存 |
| `./archive` | `/archive` | **可选**，compose 里默认注释。启用后在设置填 `archive_roots` |

冷归档要自己加卷，例如 `- ./archive:/archive`，保存设置后再在 **管理 → 冷库归档**（`#/archive`）打包 CBZ。在设置中配置 `archive_roots` 时需注意，它是一个多行输入框，每行填写一个独立目录（消除反斜杠 `\n`），后台会自动进行跨卷负载均衡。文件名固定 `gid-英文标题.cbz`，不跟界面标题语言走。

### 环境变量

写在 `docker-compose.yml` 的 backend `environment`：

- `ENCRYPTION_KEY`：任意足够长的随机串（不是 32 字节 Hex）。设置后 Cookie / bot token / 密码哈希以 AES-256-GCM 落库。丢失则密文无法解密，见 [加密](https://github.com/ResidualBlood/galleryvault/wiki/Encryption)。
- `AUTH_SECRET`：会话签名。不填则首次启动生成并写入数据库。
- `PUID` / `PGID`：NAS 上避免下载文件属主变成 root。
- `TRUSTED_PROXIES`：反代网段，例如 `127.0.0.1,192.168.1.0/24`。
- `POSTGRES_PASSWORD`：数据库密码，默认 `galleryvault`。
- `database_pool_size`：数据库常驻连接池大小，默认 `30`。
- `database_pool_timeout`：数据库连接超时时间，默认 `30` 秒。如有大量并发查重等导致报错，可适当调优。

路径类配置（库根、下载根、归档根）只在 Web 设置里改，不要用环境变量覆盖。

---

## 文档

- [入门](https://github.com/ResidualBlood/galleryvault/wiki/Usage) — 向导、Cookie、顶栏入口
- [部署](https://github.com/ResidualBlood/galleryvault/wiki/Deployment) — 挂载、Nginx/Caddy、冷热存储
- [库维护](https://github.com/ResidualBlood/galleryvault/wiki/Manage) — 查重、缺页、冷归档、日志
- [设置](https://github.com/ResidualBlood/galleryvault/wiki/Settings) — 并发、归档、OPDS
- [FAQ](https://github.com/ResidualBlood/galleryvault/wiki/FAQ)

兼容客户端（Ehviewer 家族、JHenTai、OPDS 阅读器）见 [Compatibility](https://github.com/ResidualBlood/galleryvault/wiki/Compatibility)。

---

## 致谢

- Ehviewer_CN_SXJ — 目录与 SpiderInfo 约定
- EhTagTranslation — 标签词库
- ehsyringe — 翻译数据整理

---

## 免责声明

### 1. NSFW / 18+

本软件供个人在私有设备上整理媒体。可能被用来存放成人内容。**仅供达到法定成年年龄者使用**。未满法定年龄或当地法律禁止的，请停止使用。

### 2. 第三方内容

GalleryVault **不托管、不分发**任何媒体文件。连 E-Hentai / ExHentai 需要你自己的 Cookie。检索、下载、存储的法律责任由使用者自行承担。
