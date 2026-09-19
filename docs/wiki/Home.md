# GalleryVault 文档

> **中文** · [English](Home-EN)

GalleryVault 是面向 Ehviewer 导出目录的自托管画廊库。文件、索引与收藏关系保存在本机或 NAS。扫描 `<gid>-标题/` 与 SpiderInfo。**建议配置 Cookie** 以同步 E-Hentai / ExHentai；未配置时仍可作为本地库使用。功能列表见 [功能特性](Features)。

---

## 功能概要

- 挂载 Ehviewer `<gid>-标题/`、CBZ、7z（仅提取图片）与 PDF，读取 SpiderInfo / sidecar，无需先解压或改名。
- 配置 Cookie 后：发现页、十个收藏夹、逐页或官方 Archive 下载、重传换 GID。
- 管理页：同 GID 副本、收藏夹重复、跨 GID、缺页坏图、冷库 CBZ（可选多盘）。
- 阅读器：RTL / 双页 / 条漫；幻灯片跟随 GIF/WebP 帧时长。可选 OPDS、字段加密、Telegram Bot（粘贴 URL 入队、队列操作、扫库 / 配额 / 本地检索与封面）。

下载写入 `downloads/`。冷归档写入配置的 `archive_roots`（compose 默认不挂载 `./archive`）。详见 [功能特性](Features)。

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

## 文档索引

### 使用

- **[功能特性](Features)** — 按模块列出行为
- **[使用指南](Usage)** — 界面路由与操作
- **[界面截图](Screenshots)** — 主要页面
- **[常见问题](FAQ)** — 排错

### 运维

- **[兼容格式](Compatibility)** — 目录、SpiderInfo、sidecar、客户端
- **[部署](Deployment)** — Compose、挂载、反向代理、权限
- **[备份与恢复](Backup)** — `pg_dump` / `pg_restore`
- **[静态加密](Encryption)** — AES-256-GCM、密钥、丢失后的处理

开发接口在仓库 `backend/docs/API.md` 与 `backend/docs/DEVELOPMENT.md`（不在 GitHub Wiki）。

---

## 快速运行

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- 访问：`http://<主机IP>:8000`
- 默认密码：`p1a2s3s4`（登录后进入 `#/welcome`，必须改密）
- 数据目录：`./library`、`./downloads`、`./db-data`、`./cache`

---

## 许可

[MIT License](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)
