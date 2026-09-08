# GalleryVault 知识库

> **中文** · [English](Home-EN)

欢迎查阅 **GalleryVault** 官方文档。GalleryVault 是专为个人数字收藏打造的**私有、自托管本地画廊资产库与云端同步中心**，让所有媒体文件、索引数据与收藏关系完全留存在您掌控的本地设备或 NAS 之中。

---

## 核心专精与独特优势

- ⚡ **Ehviewer 原生契合，零搬迁入库**：直接挂载 Ehviewer 导出的多层级目录结构即可识别索引，无损解析 SpiderInfo（V1/V2）与 Sidecar 元数据，告别重复解压与手工改名。
- 🔄 **云端元数据双向深度联动**：自动化同步标签、作者、社团与分类，提供多收藏夹增量监控、后台队列下载与删除安全保护。
- 🎯 **画廊生命周期与智能去重**：独家支持重传版本（新旧 GID 变更）追踪检测与一键替换；内置跨 GID 智能聚类与收藏夹重复排查，轻松治理冗余副本。
- 🛡️ **细粒度并发调度与自愈看门狗**：流式下载与官方整包归档通道（Range 复用不重扣配额）、H@H 慢速节点超时看门狗与 302 防爬挑战探针自动恢复。
- 🔒 **全流程隐私安全与静态加密**：支持 AES-256-GCM 数据库字段级静态加密（`ENCRYPTION_KEY`），10 年免重登持久化签名会话与改密全局即时吊销。
- 📖 **沉浸式全模式阅读体验**：日漫翻页、双页并排、条漫瀑布流与动图原生帧率自适应幻灯片轮播，全面开放 OPDS 协议支持第三方阅读器。

---

## 典型用户旅程指引

根据您的使用场景，选择最适合的快速上手路径：

### 场景 A：从现有的 Ehviewer 导出目录快速建库
1. 在 `docker-compose.yml` 中将宿主机现有的 Ehviewer 导出文件夹挂载进容器（例如 `/data/Ehviewer:/Ehviewer:ro`）。
2. 在「系统设置 → 库根目录」中添加挂载路径，保存配置。
3. 点击「扫描库」按钮，系统将自动读取目录下的 `.ehviewer` 或 sidecar 元数据并建立高性能全文检索索引。
4. 详见 **[兼容性与格式规范](Compatibility)** 与 **[使用指南：画廊库管理](Usage#画廊库library)**。

### 场景 B：云端收藏夹一键私有化与持续增量同步
1. 在「系统设置 → ExHentai」中配置您的账户凭证并点击「测试登录」验证连接状态。
2. 进入「收藏夹监控」页面，为各收藏文件夹启用「增量下载」或「仅监控」模式。
3. 系统将后台定时自动拉取收藏夹变动、预热封面缓存并完成下载入库。
4. 详见 **[使用指南：收藏夹与监控](Usage#收藏夹favorites)** 与 **[下载管理](Downloads)**。

### 场景 C：多版本去重与生命周期维护
1. 打开「收藏夹查重」页面，系统自动扫描出同一画廊的不同语言版本、画质重置版或无修正副本，支持一键取消多余收藏或删除本地文件。
2. 打开「更新画廊」页面，系统自动比对云端被更新/重传分配新 GID 的条目，支持一键下载新版并原地清理旧版本地副本。
3. 详见 **[使用指南：收藏夹查重](Usage#收藏夹查重duplicate-copies)** 与 **[更新画廊](Favorites#更新画廊updates)**。

---

## 模块全景索引

### 📖 用户指南
- **[功能特性 (Features)](Features)** — 全量功能矩阵、底层架构与专精能力全景
- **[使用指南 (Usage Guide)](Usage)** — 浏览筛选、在线阅读器、下载管理、收藏夹监控、查重与回收站操作
- **[界面截图 (Screenshots)](Screenshots)** — 各主要功能模块中英文界面直观一览
- **[常见问题 (FAQ)](FAQ)** — 部署排错、网络调度、Cookie 维护与常见疑问解答

### ⚙️ 运维与部署
- **[兼容性与格式规范 (Compatibility)](Compatibility)** — 目录结构标准、SpiderInfo V1/V2、Sidecar JSON 规范与客户端矩阵
- **[部署指南 (Deployment)](Deployment)** — Docker Compose 快速上手、目录挂载、Nginx/Caddy 反向代理与权限配置
- **[数据备份与恢复 (Backup)](Backup)** — 数据库快照导出、冷备份归档与一键灾备恢复流程
- **[静态数据加密 (Encryption)](Encryption)** — AES-256-GCM 数据库字段级加密原理、密钥管理与紧急灾备方案

### 🛠️ 接口与开发
- **[API 参考 (API)](API)** — REST API 完整接口规范与 OpenAPI 文档
- **[开发指南 (Development)](Development)** — 本地开发环境搭建、Dev Compose 热重载与自动化测试套件

---

## 快速运行命令

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- 默认访问入口：`http://<主机IP>:8000`
- 默认管理员密码：`p1a2s3s4`（首次登录后请立即进入「设置」修改）
- 数据落盘：默认存储在当前目录的 `./library`、`./downloads`、`./db-data` 与 `./cache`。

---

## 许可协议

本项目基于 [MIT License](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE) 开源发布。
