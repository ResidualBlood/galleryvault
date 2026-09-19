# 功能特性

> **中文** · [English](Features-EN)

按模块列出 GalleryVault 的行为。架构如下。

```
┌─────────────────────────────────────────────────────────────┐
│  前端 SPA  :8000                                             │
│  Browse · Discover · Library · Series · Tags · Downloads     │
│  Favorites · Manage(recycle/dup/integrity/archive) · Reader  │
└──────────────┬───────────────────────────────▲──────────────┘
               │ /api 反代                     │
┌──────────────▼───────────────────────────────┴──────────────┐
│  FastAPI  127.0.0.1:8001                                     │
│  扫描 Ehviewer/CBZ  ·  下载/Archive  ·  收藏同步  ·  查重    │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
          PostgreSQL（可选字段加密）
```

---

## 1. 扫描与格式

- **Ehviewer 目录**：扫描 `<gid>-<标题>/`，解析 `.ehviewer`（SpiderInfo V2；无标记的 V1 也可读）得到 gid、token 与各页 pToken。标题、分类、标签不在 SpiderInfo 中，由目录名 / `.galleryvault.json` / gdata 补全。无需解压或改名。
- **其它格式**：CBZ、CBR（内嵌 `ComicInfo.xml`）、JHenTai 逐页目录的 `metadata` JSON（不扫描归档 `ametadata`），以及冷库 CBZ/目录内的 `.galleryvault.json`。
- **7z / PDF / 无 gid**：`.7z` 只索引图片成员（非图片不解到库目录），阅读时按页在内存解压，单页上限 128MB；`.pdf` 抽取内嵌图（单图超 128MB 跳过）。没有 gid 的纯图目录也可以浏览、打星。
- **冷热存储**：新下载写入热目录；归档根可单独挂载。归档不会自动运行。
- **本地整理**：自定义列表、星级、笔记，不依赖外部站点。

## 2. 版本与查重

- **Updates**：检测云端重传后分配的新 GID，可一键下载新版并删除本地旧副本。
- **跨 GID 查重**：按作品特征聚类不同汉化、画质或重复收藏，可批量移除。
- **同 GID 多副本**：多盘或路径重复入库时，按策略保留一份（已有 / 页数多 / 体积大 / 最新 / 手动）。
- **标题显示**：日文 / 英文 / 目录名三档，与下载目录命名无关。

## 3. 站点与收藏

- **gdata**：用本机 Cookie 拉取分类、标签、评分，结果缓存。
- **十个收藏夹**：每夹可选「增量下载」、「仅监控」或「强制下载」，并有独立轮询间隔。定时检查时按模式入队新项。
- **站点 URL**：仅允许 `exhentai.org`、`e-hentai.org` 或其子域（其它主机名返回 422）。表站模式下暂停里站条目的标签同步。
- **Cookie 探活**：启动时及之后周期性检查；顶栏提示失效。
- **发现页**：Popular、Watched、Toplist；可下载或加入收藏。

## 4. 下载

- **逐页**：并发可配，进度可见，只补缺失页。
- **官方 Archive**：zip 通道，消耗 GP；单连接流式传输，Range 续传；**重试不重复扣 GP**。
- **慢节点**：单图总超时、预热窗口、最低传输速率；踢掉慢 H@H 节点。
- **退避**：瞬时错误按 30 秒至 6 小时递增重试，最多 10 次。
- **302**：检测到挑战后暂停队列；后台探针默认每 10 分钟一次，限制解除后继续。
- **入库**：下载完成后写入索引与封面，不必全量扫盘。

## 5. 阅读与检索

- **排版**：从右向左（RTL）、从左向右（LTR）、条漫、双页。
- **导航**：键盘、点击热区、`G` 跳页、预加载；末页进入下一本。条漫用滚轮/触控垂直滚动（方向键与左右热区不翻页）。
- **幻灯片**：GIF/WebP 的 `duration_ms`（各帧 delay 之和，二进制扫描，**上限 120 秒**），间隔为 `max(用户设定, 时长 + 150ms)`。开始后进入全屏，退出全屏即停止。
- **标签搜索**：EhTagTranslation 词库；标签建议、AND/OR、`-tag` 排除、中文反向联想（例如输入「长发」可匹配 `long hair`）。
- **OPDS**：`GET /api/opds`，HTTP Basic，可用于 Tachiyomi、Mihon、Panels。
- **回收站**：手动删除或扫描失踪的画廊可恢复。

## 6. 安全与部署

- **AES-256-GCM**：设置 `ENCRYPTION_KEY` 后，Cookie、token、密码哈希以密文存储。
- **会话**：签名密钥写入数据库，容器重启后仍保持登录；修改密码会撤销全部会话。Cookie 默认有效期 10 年。
- **PUID / PGID**：NAS 上以降权用户运行。CSRF 防护（含 `Origin: null` / 无 Origin 带 Cookie）。`TRUSTED_PROXIES` 白名单。压缩包单页解压上限 128MB。
- **Docker**：AMD64 / ARM64 镜像，PostgreSQL 18，Alembic 自动迁移。

## 7. Telegram Bot

- 配置 bot token 后，启动时向 Telegram 注册 `/` 菜单；文案跟随通知语言。
- 聊天中粘贴画廊 URL（首尾多余斜杠也可）即入队；`/queue` 带 InlineKeyboard（暂停、重试、取消）；`/pause` `/resume` 与 Web 下载页同一开关。
- `/status` 队列概况、`/storage` 磁盘用量、`/quota` 图像配额与 GP、`/cookie` Cookie 有效性，与 Web 展示一致。
- `/search` 检索翻页、`/info` `/random` 发送详情与封面（与 Web 相同的 5 级封面降级）、`/scan` 触发扫库、`/fav_sync` `/fav_download` `/fav_check` 操作收藏夹。
