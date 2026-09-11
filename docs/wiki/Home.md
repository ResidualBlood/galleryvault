# GalleryVault 知识库

> **中文** · [English](Home-EN)

欢迎查阅 **GalleryVault** 官方文档。GalleryVault 是专为个人数字收藏打造的**私有、自托管本地画廊资产库与云端同步中心**，让所有媒体文件、索引数据与收藏关系完全留存在您掌控的本地设备或 NAS 之中。

---

## 能做什么

- 直接挂载 Ehviewer `<gid>-标题/` 与 CBZ，读 SpiderInfo / sidecar，不必先解压改名。
- 配 Cookie 后：发现页、十个收藏夹监控、逐页或官方 Archive 下载、重传换 GID。
- 管理页：同 GID 副本、收藏夹重复、跨 GID、缺页坏图、冷库 CBZ（可选多盘）。
- 阅读器：RTL / 双页 / 条漫；幻灯片跟 GIF/WebP 帧时长。可选 OPDS、库字段加密、Telegram Bot（粘贴 URL 入队、队列操作、扫库/配额/本地检索与封面）。

下载写 `downloads/`；冷归档写你配置的 `archive_roots`（compose 默认不挂 Archive）。细节见 [功能特性](Features)。

---

## 上手路径

### A. 已有 Ehviewer 目录
1. compose 里把宿主目录挂进 backend（例如 `/data/Ehviewer:/Ehviewer:ro`）。
2. **设置 → 资料库** 把容器路径加到库根，保存。
3. 打开 **画廊库**（`#/library`）点 **扫描库**。
4. [兼容格式](Compatibility) · [浏览与库](Library#画廊库library)

### B. 同步收藏夹
1. **设置 → 站点与代理** 填 Cookie，点 **测试登录**。
2. **收藏夹**（`#/favorites`）启用文件夹，模式选增量下载或仅监控。
3. [收藏与更新](Favorites#收藏夹favorites) · [下载](Downloads)

### C. 去重与换 GID
1. **管理 → 收藏夹重复**（`#/duplicates/favorites`）。
2. **管理 → 跨 GID 重复**（`#/duplicates/cross-gid`）。
3. 收藏夹页进 **更新画廊**（`#/updates`）。
4. [库维护](Manage#重复副本与查重duplicates) · [更新画廊](Favorites#更新画廊updates)

### D. 冷归档
1. compose 挂上归档卷，**设置 → 资料库** 填 `archive_roots`。
2. **管理 → 冷库归档**（`#/archive`）点开始归档；之后可清理已归档源目录（设置存储表同一按钮）。
3. [部署](Deployment) · [冷库归档](Manage#冷库归档archive)

### E. 系列与缺页
1. 顶栏 **系列**（`#/series`）。
2. **管理 → 缺页体检**（`#/integrity`）先扫描再修复。
3. [系列](Library#系列作品series) · [缺页体检](Manage#缺页体检integrity)

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

开发接口写在仓库 `backend/docs/API.md` 与 `backend/docs/DEVELOPMENT.md`（不在 GitHub Wiki）。

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
