# GalleryVault 文档

> **中文** · [English](Home-EN)

GalleryVault 是面向 Ehviewer 导出目录的自托管画廊库。文件、索引与收藏关系保存在本机或 NAS。系统支持扫描 `<gid>-标题/` 目录与 SpiderInfo 元数据。未配置 Cookie 时可作为本地画廊库使用；配置 Cookie 后可使用在线发现、收藏夹同步、画廊下载与更新检测。功能说明见 [功能特性](Features)。

---

## 快速运行

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- 访问：`http://<主机IP>:8000`
- 默认密码：`p1a2s3s4`（登录后进入 `#/welcome`，首次登录必须修改密码）
- 数据目录：`./library`、`./downloads`、`./db-data`、`./cache`

---

## 功能概要

- 本地能力：直接挂载 Ehviewer `<gid>-标题/` 目录、CBZ、7z（提取图片）与 PDF 文件；读取 SpiderInfo 与 sidecar 元数据，无需提前解压或批量重命名。
- 联网能力（需要配置 Cookie）：提供在线发现页、十个收藏夹同步、逐页与官方 Archive 整包下载、重传更新检测与换 GID 迁移。
- 维护与归档：提供同 GID 重复副本清理、收藏夹查重、跨 GID 重复清理、缺页与坏图体检、多盘冷库 CBZ 归档。
- 阅读与扩展：内置 RTL、双页、条漫阅读器与跟随动态图帧时长的幻灯片播放；支持 OPDS 协议、数据库敏感字段静态加密与 Telegram Bot 远程控制。

下载文件保存至 `downloads/` 目录；冷归档保存至配置的 `archive_roots` 目录。详细说明见 [功能特性](Features)。

---

## 上手路径

### A. 已有 Ehviewer 目录
1. 在 compose 文件中把宿主机目录挂载至 backend 容器（例如 `/data/Ehviewer:/Ehviewer:ro`）。
2. 打开 **设置 → 资料库**，将容器内挂载路径添加到库根目录并保存（会要求输入当前管理员密码确认）。
3. 进入 **画廊库**（`#/library`）点击 **扫描库**。
4. 详情见 [兼容格式](Compatibility) 与 [画廊库](Library#画廊库library)。

### B. 同步收藏夹
1. 打开 **设置 → 站点与代理**，填写 Cookie 并点击 **测试登录** 验证状态。
2. 进入 **收藏夹**（`#/favorites`），启用目标文件夹并选择增量下载或仅监控模式。
3. 详情见 [收藏夹](Favorites#收藏夹favorites) 与 [下载](Downloads)。

### C. 去重与换 GID
1. 进入 **管理 → 收藏夹重复**（`#/duplicates/favorites`）或 **跨 GID 重复**（`#/duplicates/cross-gid`）清理重复项目。
2. 在收藏夹页面点击 **更新画廊**（`#/updates`）检测重传画廊并迁移状态。
3. 详情见 [库维护](Manage#重复副本与查重duplicates) 与 [更新画廊](Favorites#更新画廊updates)。

### D. 冷归档
1. 在 compose 中挂载归档存储卷，并在 **设置 → 资料库** 中配置 `archive_roots`。
2. 进入 **管理 → 冷库归档**（`#/archive`）执行归档；归档完成后可通过设置页面存储表格清理已归档源目录。
3. 详情见 [部署指南](Deployment) 与 [冷库归档](Manage#冷库归档archive)。

### E. 系列与缺页
1. 访问顶栏 **系列**（`#/series`）查看同系列作品聚合。
2. 进入 **管理 → 缺页体检**（`#/integrity`）执行画廊完整性扫描与下载补页。
3. 详情见 [系列作品](Library#系列作品series) 与 [缺页体检](Manage#缺页体检integrity)。

---

## 文档索引

### 入门

- **[使用指南](Usage)** — 界面路由、首次配置向导、推荐流程与旧锚点迁徙对照
- **[功能特性](Features)** — 按模块列出系统能力、运行前提与拓扑结构
- **[界面截图](Screenshots)** — 核心功能与主要页面截图索引

### 使用

- **[浏览与库](Library)** — 画廊库浏览、发现页、本地列表、高级筛选与阅读历史
- **[阅读器](Reading)** — 画廊详情页、标签同步、阅读器模式、快捷键与幻灯片
- **[任务与下载](Downloads)** — 下载队列、状态徽标、重试机制与官方归档整包下载
- **[收藏夹](Favorites)** — 收藏夹管理、同步模式、查重与重传更新检测
- **[库维护](Manage)** — 重复副本清理、跨 GID 查重、回收站、冷库归档与体检日志
- **[系统设置](Settings)** — 系统设置项、存储面板、Telegram Bot 命令与联网清单

### 运维

- **[部署指南](Deployment)** — Compose 配置、存储拓扑、权限控制、性能调优与修复脚本
- **[兼容格式](Compatibility)** — 客户端支持矩阵、目录拓扑、元数据规范与命名限制
- **[备份与恢复](Backup)** — 数据库备份与恢复、密钥保管、归档备份与运维说明
- **[静态加密](Encryption)** — AES-256-GCM 字段加密原理、密钥职责与丢失恢复
- **[常见问题](FAQ)** — 部署与使用过程中的常见问题定位与排错

开发接口文档位于仓库 `backend/docs/API.md` 与 `backend/docs/DEVELOPMENT.md`。

---

## 许可

[MIT License](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)
