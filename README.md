# GalleryVault

<p align="center">
  <img src="frontend/favicon.svg" alt="GalleryVault Logo" width="96" height="96">
</p>

<p align="center">
  <strong>现代化私有画廊资产管理系统与云端同步中心</strong><br>
  本地数字资产归档 · 深度元数据同步 · 智能生命周期追踪 · 原生静态加密 · 沉浸式阅读
</p>

<p align="center">
  <a href="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml"><img src="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-backend.yml/badge.svg" alt="Backend CI"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml"><img src="https://github.com/ResidualBlood/galleryvault/actions/workflows/ci-frontend.yml/badge.svg" alt="Frontend CI"></a>
  <a href="https://hub.docker.com/u/residualblood"><img src="https://img.shields.io/badge/docker-images-blue?logo=docker" alt="Docker"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/wiki"><img src="https://img.shields.io/badge/docs-wiki-9cf?logo=github" alt="Wiki"></a>
  <a href="https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

<p align="center">
  <strong>中文</strong> · <a href="README.en.md">English</a> · <a href="https://github.com/ResidualBlood/galleryvault/wiki">📖 在线完整文档</a>
</p>

---

GalleryVault 是专为个人数字收藏打造的**私有、自托管本地画廊资产库**。所有媒体文件、索引数据与收藏关系完全保存在您自己的机器或私有 NAS 上，无需依赖第三方云服务。

系统原生支持直接扫描解析 Ehviewer 导出目录、CBZ/CBR 压缩包及普通图片文件夹，建立高保真全文检索索引；支持与云端元数据双向同步、收藏监控下载、版本重传追踪与智能跨 GID 去重；内置日漫、双页、条漫与动图自适应幻灯片阅读器，支持 OPDS 协议对接移动端；全栈提供 AES-256-GCM 数据库静态加密与多架构 Docker 一键部署。

## 为什么选择 GalleryVault？

不同于传统泛用型漫画服务或纯归档解压工具，GalleryVault 专注于画廊生态的完整生命周期治理与深度元数据联动：

- ⚡ **Ehviewer 原生契合与零搬迁入库**：直接挂载 Ehviewer 导出的多层级目录结构即可识别索引，无缝读取 SpiderInfo（V1/V2）与 Sidecar 元数据，免除二次解压、重命名或重整归档的繁重开销。
- 🔄 **云端元数据深度联动与双向同步**：自动拉取分类、多语言标签与发布信息，支持本地与云端收藏夹双向映射、增量监控下载及云端删除安全保护机制。
- 🎯 **画廊生命周期追踪与智能去重**：独家支持新旧版本重传识别（新旧 GID 变更追踪）一键原地替换，内置跨 GID 聚类与收藏夹重复排查，彻底解决同名多版本与搬运冗余。
- 🛡️ **细粒度并发调度与自愈看门狗**：具备任务级指数退避重试、分页并发流控、官方归档包断点续传（Range 复用不重扣配额）、H@H 慢速节点看门狗及 302 防爬挑战探针自动恢复。
- 🔒 **全流程隐私安全与静态加密**：可选启用数据库字段级 AES-256-GCM 静态加密（`ENCRYPTION_KEY`），敏感凭证落库加密；支持 10 年免重登持久化签名会话与改密全局吊销。
- 📖 **沉浸式全模式阅读与生态互联**：支持日漫（RTL）、韩漫瀑布流、双页并排阅读与动图（GIF/WebP）帧率自适应幻灯片轮播，原生开放 OPDS 协议兼容各大第三方阅读客户端。

---

## 核心特性全景

### 1. 本地资产归档与高保真解析
- **无缝目录解析**：扫描 `<gid>-<标题>/` 文件夹，自动读取 `.ehviewer`、JHenTai `metadata` JSON、CBZ/CBR 压缩包（ComicInfo.xml），完美恢复画廊元数据。
- **冷热分层归档**：支持热存储工作区（新下载）与冷存储归档卷（CBZ/只读目录）分离挂载，生成标准 `.galleryvault.json` sidecar 索引。
- **格式弹性容错**：支持扫描 7z/PDF 压缩资源，仅解压图片流，不向宿主释放垃圾临时文件。

### 2. 云端同步与收藏夹监控
- **元数据批量回填**：利用自有凭据高效批量拉取分类、评分、详细标签，支持批量预热缩略图缓存。
- **多收藏夹智能巡检**：支持 10 个收藏夹独立配置同步策略（增量下载、仅监控、定时同步），变动自动入队。
- **版本更新自动追踪**：全天候比对云端重传与版本替换事件，智能识别更新版 GID，一键替换旧版画廊。
- **跨 GID 查重与副本治理**：智能算法比对作品聚类，直观标记重复收藏与本地冗余版本，支持一键清理。

### 3. 稳健的后台下载流水线
- **分层下载引擎**：支持逐页并发流式下载与官方整包归档（Archive Zip）下载通道，断点续传绝不重复扣减 GP 配额。
- **智能自愈与看门狗**：网络抖动自动触发指数退避重试（30s 至 6h，多达 10 次）；单图超时与低速看门狗自动踢除卡死节点。
- **反爬保护与全局流控**：遭遇 302 临时挑战时自动挂起所有调度并启动后台静默探针，限制全局并发，守护凭据安全。
- **增量即时入库**：下载完成直接注入持久化索引，无需触发全量扫描。

### 4. 极致阅读与跨端生态
- **多阅读模式**：支持从右至左（RTL 日漫）、从左至右（LTR）、垂直瀑布流（条漫）、双页并排显示。
- **动态图自适应幻灯片**：智能解析 GIF/WebP 原生动画时长与帧延迟，自动匹配轮播间隔，提供顺滑观赏体验。
- **标签多维联想检索**：集成 EhTagTranslation 标签数据库，支持多标签 AND/OR 混合检索、反向中文联想与排除语法。
- **开放客户端对接**：内置标准 OPDS 协议目录（`GET /api/opds`），可无缝对接 Tachiyomi、Mihon、Panels 等阅读客户端。

---

## 快速开始

仅需 1 分钟即可通过 Docker Compose 启动全套服务：

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

### 1. 访问与初始化
- 打开浏览器访问 **`http://<主机IP>:8000`**（API 后端位于 `:8001`）。
- 使用初始默认口令 **`p1a2s3s4`** 登录。
- **安全建议**：登录后请第一时间进入「设置」修改管理员密码。

### 2. 数据目录映射说明

| 本地路径 | 容器内挂载点 | 说明 |
| :--- | :--- | :--- |
| `./db-data` | `/var/lib/postgresql/data` | PostgreSQL 核心数据库（索引、设置、历史），持久化保存 |
| `./library` | `/library` | 本地画廊库（已有 Ehviewer 目录、CBZ/CBR 等），下载不会写入此目录 |
| `./downloads` | `/downloads` | 下载存储目录，新下载文件落盘于此并自动即时入库 |
| `./cache` | `/gv-cache` | 缩略图与封面本地缓存目录，避免反复消耗外部流量 |
| `./Archive` | `/archive` | （可选）冷数据归档目录，支持挂载多块外部硬盘或 NAS 共享卷 |

### 3. 核心环境变量速查

在 `docker-compose.yml` 中可按需启用高级安全与环境配置：

- `ENCRYPTION_KEY`：用于数据库字段级静态加密的 32 字节 Hex 密钥。配置后自动加密存储会话凭据、Cookie 与签名密钥。
- `AUTH_SECRET`：Web 会话 Cookie 签名密钥。默认自适应随机生成并入库持久化；显式配置可用于多节点统一管理。
- `PUID` / `PGID`：设置后端运行的用户与用户组 ID（如 `1000:1000`），避免在非 root NAS 环境中产生文件属主冲突。
- `TRUSTED_PROXIES`：反向代理受信网段或 IP（如 `127.0.0.1,192.168.1.0/24`），确保真实客户端 IP 限速与防伪造校验生效。

---

## 界面一览

> 提示：文档与截图均已做安全合规化处理。

| 模块 | 中文界面 | English UI |
| :--- | :--- | :--- |
| **画廊资产库** | <img src="docs/screenshots/library_zh.png" alt="画廊库界面" width="400"> | <img src="docs/screenshots/library_en.png" alt="Library UI" width="400"> |
| **多维标签云** | <img src="docs/screenshots/tags_zh.png" alt="标签云页面" width="400"> | <img src="docs/screenshots/tags_en.png" alt="Tag Cloud UI" width="400"> |
| **收藏夹智能查重** | <img src="docs/screenshots/fav_dedupe_zh.png" alt="收藏夹查重" width="400"> | <img src="docs/screenshots/fav_dedupe_en.png" alt="Favorites Dedupe UI" width="400"> |
| **双向监控与同步** | <img src="docs/screenshots/fav_monitor_zh.png" alt="双向监控" width="400"> | <img src="docs/screenshots/fav_monitor_en.png" alt="Favorites Monitor UI" width="400"> |
| **下载任务调度** | <img src="docs/screenshots/downloads_zh.png" alt="下载管理" width="400"> | <img src="docs/screenshots/downloads_en.png" alt="Downloads Manager UI" width="400"> |
| **版本更新追踪** | <img src="docs/screenshots/updates_zh.png" alt="更新追踪" width="400"> | <img src="docs/screenshots/updates_en.png" alt="Updates Tracker UI" width="400"> |

---

## 客户端与生态支持

| 生态分类 | 客户端 / 工具 | 兼容性与集成机制 |
| :--- | :--- | :--- |
| **Ehviewer 原生家族** | Ehviewer_CN_SXJ, FooIbar, Overhauled, NekoWhite, MHViewer, Apple, OHOS | 原生零改动读取 `<gid>-<标题>/` 目录与 SpiderInfo V1/V2 元数据 |
| **跨平台客户端** | JHenTai (Flutter 全平台) | 原生自动识别 `metadata` JSON 文件并无损还原分类、标签与状态 |
| **移动阅读客户端** | Tachiyomi, Mihon, Panels, Komikku | 通过内置 OPDS 协议规范（`GET /api/opds`）直接添加目录源 |
| **标准归档文件** | CBZ, CBR, 7z, PDF | 支持包含 ComicInfo.xml 的压缩包与纯图片目录索引 |

---

## 文档指引

完整进阶指南与规范请参阅 **[GitHub Wiki 知识库](https://github.com/ResidualBlood/galleryvault/wiki)**：

- **[使用指南 (Usage Guide)](https://github.com/ResidualBlood/galleryvault/wiki/Usage)** — 资产检索、阅读器手势、下载策略、收藏夹监控与查重深度教程
- **[功能特性 (Features)](https://github.com/ResidualBlood/galleryvault/wiki/Features)** — 全量特性矩阵与底层系统架构说明
- **[部署指南 (Deployment)](https://github.com/ResidualBlood/galleryvault/wiki/Deployment)** — Nginx / Caddy 反向代理、TLS 证书加固、非 root 权限与冷热分层存储
- **[数据加密 (Encryption)](https://github.com/ResidualBlood/galleryvault/wiki/Encryption)** — 静态加密原理、密钥迁移与容灾应急恢复
- **[常见问题 (FAQ)](https://github.com/ResidualBlood/galleryvault/wiki/FAQ)** — 安装排错、网络调度诊断、标签翻译与会话机制答疑

---

## 运维诊断工具

仓库在 `scripts/` 目录内置了开箱即用的自动化运维与性能分析工具：

- **`scripts/monitor_prod_logs.sh`**：远程实时监听生产环境多容器日志流，自动归档本地临时镜像。
- **`scripts/analyze_prod_logs.py`**：智能分析服务日志归档，统计异常调用、状态码分布、高频请求及慢耗时热点。

---

## 致谢

- **Ehviewer_CN_SXJ**：目录组织与多层元数据规范设计参考。
- **EhTagTranslation**：提供高质量多语言标签元数据库与更新机制。
- **ehsyringe**：标签翻译格式化与数据规范整理支持。

---

## 免责声明

GalleryVault 是一款开源的本地画廊资产管理与元数据组织工具。涉及第三方云端服务同步的功能均需用户自行配置私有凭据。请使用者务必遵守当地法律法规及所访问网络平台的服务条款，合理配置并发限制，严禁用于任何非法或违规用途。
