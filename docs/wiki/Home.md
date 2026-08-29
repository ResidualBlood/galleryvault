# GalleryVault

> [English](Home-EN) · 中文

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 **中文 / English** 双语界面。

## 功能特性

- **本地画廊库**：扫描 Ehviewer 导出目录、CBZ/CBR 文件与普通图片文件夹，建立持久化、可搜索的索引（PostgreSQL）。
- **重复副本清理**：同一画廊（gid）出现在多个扫描目录时自动按策略保留一份（`duplicate_policy`：优先保留已入库/页数多/新/大/小或手动），其余副本列在「重复副本」页（缩略图/标签/页数/大小/发布时间），可一键保留或删除磁盘上的其他副本。
- **标签翻译**：自动获取最新 [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database) 数据库，中文输入反向匹配翻译表（如输入「巨乳」可提示 `big breasts`）。
- **多标签与混合搜索**：点击标签提示/详情页/标签云的标签可**叠加筛选**（AND）；搜索框支持「标签+文字」混输自动识别（如 `动图 中国` → 标签 `animated` + 关键词）；详情页可一键跳转 **ExHentai 原页**（按设置的 base URL 生成）。
- **双语界面**：完整的中文与 English 界面，可随时切换；中文界面下标签显示翻译。
- **ExHentai 集成**：使用自有 cookie（e-hentai.org 或 exhentai.org）获取每个画廊的元数据、分类与标签；外站设置下里站专属画廊会**暂停**标签同步（不会误判为已删除），切回 exhentai.org 后自动恢复。
- **下载管理**：类似 Ehviewer 的并发分页下载、实时进度、可续传重试、部分下载（`max_pages`）、取消与批量重试；失败任务**指数退避自动重试**（30s→6h，上限 10 次），大画廊跑中段遇网络波动自愈；下载完成**自动增量入库**（含标签/封面，无需全量扫描）。
- **收藏夹监控与管理**：监控十个 ExHentai 收藏文件夹自动下载、独立列表、查重扫描与忽略误报。
- **元数据缓存与自动同步**：收藏夹检查用 gdata 批量接口缓存标签/分类/发布时间/大小，扫描入库直接复用；检查后自动把最新元数据应用到本地画廊。
- **阅读器与历史**：逐页流式加载、键盘/空格/点击翻页、预加载后三页、最后一页自动跳转下一画廊、自动保存阅读位置。
- **日志页面**：统一展示后台任务（扫描/标签同步/缩略图/收藏元数据）进行中与已完成状态，可取消。
- **首次运行向导**：新部署登录后自动进入三步引导（改密码 → 连 ExHentai → 扫描库），可随时在 `#/welcome` 重看。
- **Telegram 通知**：下载成功/失败、扫描完成、收藏同步时发送通知；默认**汇总**模式（批量下载合并为一条摘要），可切"即时/仅失败/关闭"；**通知语言**（中文/English）统一控制全部消息文案。
- **安全与隐私**：PBKDF2 认证、登录限速、跨域校验与域名白名单、非 root 运行、可选的**静态加密**（`ENCRYPTION_KEY`，AES-256-GCM）；改密码立即撤销所有会话。
- **一键部署**：两个 Docker Hub 镜像 + PostgreSQL，单条 `docker compose up` 即可运行。

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
- **[使用指南](Usage)** — 浏览、阅读器、标签、下载、收藏夹、日志、设置
- **[备份与恢复](Backup)** — pg_dump 备份脚本与恢复
- **[静态加密](Encryption)** — ENCRYPTION_KEY 加密与密钥丢失恢复
- **[API 参考](API)** — 完整 REST API
- **[开发指南](Development)** — 架构、项目布局、开发约定
- **[常见问题](FAQ)** — 排查与技巧
- **[界面截图](Screenshots)** — 画廊库、标签云、收藏夹、下载、阅读器、日志、设置（中英文对照）

## License

[MIT](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)。

