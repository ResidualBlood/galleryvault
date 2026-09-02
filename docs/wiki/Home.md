# GalleryVault

> [English](Home-EN) · 中文

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 **中文 / English** 双语界面。

## 功能特性

**本地画廊库**

- **扫描入库**：扫描 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹，建立持久化、可搜索的索引（PostgreSQL）。
- **格式还原**：`<gid>-<标题>/` + `.ehviewer`（SpiderInfo V1/V2）、JHenTai `metadata` JSON、CBZ/CBR（+ ComicInfo.xml）都能恢复完整画廊身份；无 gid 的画廊可浏览，但无法参与下载/查重。
- **重复副本清理**：同一画廊（gid）出现在多个扫描目录时，按 `duplicate_policy`（保留已入库/页数多/新/大/小或手动）自动保留一份，其余副本在「重复副本」页一键保留/删除。
- **标题显示**：`japanese` / `english` / `directory` 三档控制全站标题显示；下载目录命名由独立的「下载标题」设置决定，互不影响。

**搜索与标签**

- **多标签与混合搜索**：点击标签（搜索建议/详情页/标签云）叠加筛选（AND/OR）；排除 `-tag`；搜索框支持 `动图 中国` 混输与 `ns:name` 显式语法，点击建议才把词当标签，回车只做标题文字搜索（多词逐词 AND）。
- **库筛选**：多维排序（入库/发布/标题/页数/体积/评分）、阅读状态、页数与评分区间；卡片标签 Shift+点击加入排除。
- **标签翻译**：自动获取最新 [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database) 数据库，中文输入反向匹配（如输入「巨乳」提示 `big breasts`）；标签页搜索框同样支持中文补全。
- **双语界面**：中文 / English 随时切换；中文界面下标签显示翻译。
- **标签云**：命名空间分组（标签/作者/角色/原作/社团/女性/男性/语言），字号随使用热度。

**ExHentai 集成**

- **元数据同步**：使用自有 cookie 获取每个画廊的元数据/分类/标签；gdata 批量缓存，扫描与收藏夹直接复用。
- **外站兼容**：使用 e-hentai.org 外站时，里站专属画廊**暂停**标签同步（不会误判为已删除），切回 exhentai.org 自动恢复。
- **收藏夹监控与管理**：监控十个收藏文件夹（增量/仅监控/强制三模式）自动下载、独立列表、跳过启发式省流量、查重扫描与忽略误报；详情页/库页可加收藏或换夹（以云端成功为准）。
- **更新画廊**（`#/updates`）：检测 ExHentai **重传**（新版本 = 新 gid）的本地旧版画廊，一键下载新版并删除旧版本地副本；新 gid 已在库时检测会自动收尾。
- **打开原站**：画廊详情一键跳转 ExHentai 原页（按设置的 base URL 生成）。
- **Cookie 健康**：启动与定时探活；失效或无里站权限时顶栏红条并导向设置。

**下载管理**

- **Ehviewer 风格下载**：并发分页下载、实时进度、断点续传（仅补缺失页）、部分下载（`max_pages`）、取消与批量重试；下载页可粘贴 URL/`gid/token`（逐页或归档），有更新则跟新版。
- **归档下载（ExHentai archive）**：官方整包 zip 通道，用 GP 换大画廊速度；任务级画质覆盖（原图/重采样）、单连接流式 + Range 断点续传、重试不重复扣 GP、GP 预检弹窗（只读）。
- **全局暂停与配额**：暂停持久化（Web 与 Bot 同一开关）；下载页显示 GP 与图片配额（约 30 分钟缓存）。
- **慢速看门狗**：单图总超时 + 预热窗口 + 最低速度三参数，慢速 H@H 节点不再拖住整个画廊。
- **失败自愈**：瞬时错误**指数退避自动重试**（30s→6h，上限 10 次），大画廊遇网络波动自动恢复；周期巡检重激活仍有余量的失败任务。
- **增量入库**：下载完成直接写入索引（含标签/封面），无需全量扫描；下载目录复用不重复建。
- **Telegram**：下载/扫描/收藏通知（汇总/即时/仅失败/关闭，中文/English）；bot 控制命令（`/pause` `/resume` `/status`、粘贴画廊 URL 入队下载）。

**阅读器与界面**

- **阅读器**：逐页流式、LTR / RTL 日漫 / 双页并排、键盘/空格/点击翻页、`G` 跳页、预加载后三页、最后一页自动跳转下一画廊、全屏与适应模式、页面浏览器缓存 1 小时、阅读位置自动保存，搜索上下文全程保留。
- **浏览与历史**：最新画廊浏览（随机画廊、标签命名空间入口）、**继续阅读**卡片、顶栏全局搜索、阅读历史页、后台任务日志页、首次运行三步向导。
- **回收站与缺页**：用户删除/扫描失踪可恢复；缺页体检一键补下缺失页。

**安全与运维**

- **安全**：PBKDF2 认证、登录限速、跨域校验与域名白名单、改密立即撤销所有会话；backend 默认 root，可用 `PUID`/`PGID` 降权；可选**静态加密**（`ENCRYPTION_KEY`，AES-256-GCM）。
- **代理**：HTTP 或 SOCKS5（二选一），用于 ExHentai 访问、下载与翻译更新。
- **一键部署**：两个 Docker Hub 镜像 + PostgreSQL，单条 `docker compose up` 即可运行；升级自动迁移，`scripts/backup.sh` 一键备份。

## 快速开始

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

打开 `http://<host>:8000`，使用默认密码 `p1a2s3s4` 登录（登录后请立即在设置中修改）。详见 [部署](Deployment)。

### 推荐使用流程

1. **登录 ExHentai**：设置 → ExHentai，填 `ipb_member_id` / `ipb_pass_hash` / `igneous` 并「测试登录」（cookie 加密存库，勿写进 compose）。
2. **只读收藏夹（不下载）**：「收藏夹」页先把模式设为「仅监控」，再「同步收藏夹名称」→「立即检查所有」，把收藏元数据（标题/标签/封面/大小）缓存入库并记录收藏集合，**不下任何画廊**。
3. **扫描库**：把已有画廊放进库目录，点「扫描库」入库，直接复用步骤 2 的元数据缓存。
4. **先查重**：同一作品多版本用「收藏夹管理 → 扫描重复画廊」分组处理（云端与本地一起比较，可先取消收藏/忽略重复），避免下载后再去重；多目录同 gid 副本用「重复副本」页清理。
5. **开始下载**：模式切到「强制下载」→「立即检查」，把文件夹里**不在本地库**的画廊一次排入下载（已在本地的自动跳过）。
6. **切回增量 + 定时**：存量下完切回「增量下载」，设置打开 **download favorites**、间隔按需（如 10 分钟）；新加收藏自动下载。

### 适用范围

本项目**首要面向 [Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ) 下载的画廊**：下载目录为 `<gid>-<标题>/` 图片文件夹 + `.ehviewer` 元数据文件（SpiderInfo VERSION1/VERSION2，含 gid/token 与每页 pToken），扫描器据此精确还原画廊身份。

`.ehviewer` 源自 Hippo Seven 的 EhViewer（`com.hippo.ehviewer.spider.SpiderInfo`），**同源客户端写出的格式完全兼容**，可直接入库：

- **EhViewer 原版**（[seven332/EhViewer](https://github.com/seven332/EhViewer)，已弃用）；当前主流分支 [**FooIbar/EhViewer**](https://github.com/FooIbar/EhViewer)（MD3）、[**Ehviewer-Overhauled/Ehviewer**](https://github.com/Ehviewer-Overhauled/Ehviewer)、[**EhViewer-NekoInverter/EhViewer**](https://github.com/EhViewer-NekoInverter/EhViewer)、[**exzhawk/EhViewer**](https://github.com/exzhawk/EhViewer)、[**AdNotFound/EhViewer**](https://github.com/AdNotFound/EhViewer)、[**WarnError/Ehviewer-NekoWhite**](https://github.com/WarnError/Ehviewer-NekoWhite)、[**NotFaceGUI/EhViewer-Auto-Translation-Ver**](https://github.com/NotFaceGUI/EhViewer-Auto-Translation-Ver)、[**axlecho/MHViewer**](https://github.com/axlecho/MHViewer) 等。
- 跨平台移植：[**EhViewer-Apple**](https://github.com/felixchaos/EhViewer-Apple)（iOS/macOS）、[**Ehviewer_OHOS**](https://github.com/suibianqwe/Ehviewer_OHOS)（鸿蒙）。
- 周边工具：[**LRReader**](https://github.com/Xslx98/LRReader)（Android·LANraragi 客户端）、[**exhentai-manga-manager**](https://github.com/SchneeHertz/exhentai-manga-manager)、[**ehviewer_manga_manager**](https://github.com/Schweik7/ehviewer_manga_manager)（Python CLI）、[**LANraragi**](https://github.com/Difegue/LANraragi) 的 `Ehviewer.pm` 元数据插件。

其余格式：

- **[JHenTai](https://github.com/jiangtian616/JHenTai)**（全平台 Flutter，Android/iOS/Windows/macOS/Linux）下载目录**原生支持**：`<gid> - <标题>/` + `metadata` JSON，扫描直接还原完整身份（gid/token/标签/分类/发布时间）。**该格式支持较新，尚未大量实测**，如遇解析异常请附样例 `metadata` 提交 issue。
- 按能力降级支持：无 `.ehviewer` 的 `<gid>-<标题>` 图片文件夹、**CBZ/CBR**（gid 需在文件名开头）。无 gid 的画廊可浏览，但**无法参与下载/查重/重复副本解析**。

## 文档导航

- **[部署](Deployment)** — compose 部署、数据目录、容器名、库挂载、安全加固
- **[使用指南](Usage)** — 浏览、阅读器、标签、下载、收藏夹、回收站、缺页、日志、设置
- **[备份与恢复](Backup)** — pg_dump 备份脚本与恢复
- **[静态加密](Encryption)** — ENCRYPTION_KEY 加密与密钥丢失恢复
- **[API 参考](API)** — 完整 REST API
- **[开发指南](Development)** — 架构、项目布局、开发约定
- **[常见问题](FAQ)** — 排查与技巧
- **[界面截图](Screenshots)** — 画廊库、标签云、收藏夹、下载、阅读器、日志、设置（中英文对照）

## License

[MIT](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)。

