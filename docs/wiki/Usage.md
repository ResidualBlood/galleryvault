# 使用指南

> 中文 · [English](Usage-EN)
>
> **分册直达**：[浏览与库](Library) · [画廊详情与阅读](Reading) · [下载管理](Downloads) · [收藏与更新](Favorites) · [库维护](Manage) · [系统设置](Settings)

GalleryVault 是基于 hash 路由的单页应用（例如 `#/library`、`#/gallery/7`）。页面切换与交互由前端驱动，页面刷新与历史前进/后退操作无需重新请求 HTML。页面切换期间到达的过期响应会被丢弃，不会覆盖新视图内容。

**主要导航入口**：
- **桌面端顶栏**：包含 Browse（浏览）、Discover（发现）、Library（画廊库）、Series（系列）、Tags（标签）、Downloads（下载）、Favorites（收藏夹）以及「管理」。
- **更多菜单**：收纳 History（历史）、Settings（设置）与 Logs（日志）。
- **管理模块**：点击「管理」默认进入回收站（`#/recycle`），支持在页内切换至重复副本（`#/duplicates`）、收藏夹重复（`#/duplicates/favorites`）、跨 GID 重复（`#/duplicates/cross-gid`）、缺页体检（`#/integrity`）与冷库归档（`#/archive`）。旧路由 `#/favorites/manage` 会重定向至收藏夹重复以保持兼容。
- **移动端**：通过汉堡菜单平铺展示全部导航项。

**顶栏状态提示**：

| 提示类型 | 触发原因 | 用户操作 |
| :--- | :--- | :--- |
| 黄色提示条 | 开启了全局下载暂停 | 前往下载管理页或系统设置恢复任务执行 |
| 橙色提示条 | 站点探活请求失败（网络波动或目标站点临时异常） | 检查网络连接与站点可用性，排查是否能正常访问目标站点 |
| 红色提示条 | Cookie 失效、账号缺少里站权限或 IP 被封禁 | 点击提示条跳转至系统设置，更新有效 Cookie 并重新测试登录 |
| 图片配额告警 | ExHentai 图片下载配额耗尽 | 暂停消耗配额的下载任务，或等待云端配额按周期恢复 |

**应用内通知中心**：
顶栏随机画廊按钮旁的铃铛图标为应用内通知中心。记录下载完成、下载失败、版本更新改下、扫库完成或失败、归档进度与状态、以及凭据失效与 IP 封禁等后台事件。即使未配置 Telegram 机器人，也可在界面中获知后台事件；通知面板提供一键清空功能，时间戳显示为容器本地时区。

---

## 首次运行向导（`#/welcome`）

首次部署后（系统处于初始默认密码状态时），登录会自动跳转至 `#/welcome` 三步向导：

1. **修改默认密码**：将内置默认密码 `p1a2s3s4` 替换为自定义强密码。此步骤为强制项不可跳过，后续也可在系统设置中随时修改。
2. **连接 ExHentai**：选择站点基础 URL（`https://exhentai.org`、`https://e-hentai.org` 或官方域名的自定义子域），填入 `ipb_member_id`、`ipb_pass_hash` 与 `igneous`，可通过「测试登录」验证凭据有效性。若暂无账号可点击跳过，后续在设置中补充（操作参见 [配置 ExHentai Cookie](#配置-exhentai-cookie)）。
3. **填充画廊库**：点击「扫描库」检测本地媒体文件，或点击「立即检查所有收藏夹」同步云端记录。此步骤可跳过。

每一步完成后会显示对勾标识；点击「完成设置」即可进入系统主界面。已配置的实例登录后不会强制弹定向导，必要时可在浏览器地址栏手动输入 `#/welcome` 重新查看。

## 推荐使用流程

初次部署建议按以下顺序开展配置与管理：

1. **配置 Cookie（可选）**：在向导或系统设置中录入 ExHentai Cookie，并通过「测试登录」确认连通正常。
2. **检查收藏夹同步元数据**：前往 [收藏与更新](Favorites)（`#/favorites`），执行「立即检查所有」，将云端画廊元数据与封面缓存至本地数据库。
3. **扫描本地库**：将已有本子与归档置于 `./library` 挂载目录，在 [浏览与库](Library) 点击「扫描库」。系统会结合已缓存的云端元数据识别画廊建立索引。
4. **清理重复副本**：前往 [库维护](Manage) 的「重复副本」（`#/duplicates`）处理相同 GID 的多路径归档；使用「收藏夹重复」（`#/duplicates/favorites`，旧路由 `#/favorites/manage` 仍可用）排查同作品多版本。
5. **日常使用与阅读**：在收藏夹中启用目标文件夹并设置为「增量下载」；阅读操作参见 [画廊详情与阅读](Reading)。从搜索结果进入阅读器时，筛选上下文会自动保持。

## 配置 ExHentai Cookie

如需与 ExHentai 联通、同步收藏夹、在线拉取标签或下载画廊，需提供你在浏览器的有效登录凭据：

1. **获取 Cookie**：
   - 使用桌面浏览器登录 [E-Hentai](https://e-hentai.org) 或 [ExHentai](https://exhentai.org)；
   - 按 `F12` 打开开发者工具，切换到 **Application**（Chrome/Edge）或 **Storage**（Firefox）标签页；
   - 在左侧展开 **Cookies** 并选中目标站点域名；
   - 提取以下三个字段的值（Value）：
     - `ipb_member_id`：用户 ID（纯数字）；
     - `ipb_pass_hash`：密码哈希（32 位字符串）；
     - `igneous`：里站专属访问凭据（访问 `exhentai.org` 必填；仅拥有里站权限的账号会生成该字段）。
2. **录入系统**：
   - 在 `#/welcome` 向导第二步，或进入 [系统设置](Settings)（`#/settings`）的 **ExHentai** 配置区；
   - 基础 URL 保持默认 `https://exhentai.org`（若账号无里站权限可改为 `https://e-hentai.org`；系统限制仅允许输入官方域名及其子域）；
   - 依次填入对应的三个字段；Cookie 在前端提交保存后不会回显凭据明文。
3. **连通性验证与探活**：
   - 点击 **测试登录** 按钮，系统向站点发送验证请求并反馈连接结果与权限状态；
   - 服务启动时会自动执行探活检测，运行中每 30 分钟轮询检测一次；
   - Cookie 失效、缺少里站权限或 IP 封禁时顶栏展示红色提示条；探活因网络或目标站点异常失败时展示橙色提示条。可点击红色提示条直接前往设置页更新凭据。

> **安全提示**：Cookie 属于敏感凭据，请切勿将其写入仓库正文、公开文档或分享给他人。系统支持配置环境变量 `ENCRYPTION_KEY` 进行数据库静态加密保护（详见 [静态加密](Encryption)）。

## 文档分册目录

各功能模块使用说明详见对应分册：

- **[浏览与库 (Library)](Library)**：
  - [浏览（#/browse）](Library#浏览browse) — 默认网格浏览、继续阅读面板、键盘导航与全局检索；宽幅封面采用原图模糊衬底，保持完整构图。优先使用云端封面缓存，缺失时降级为本地首图并异步拉取。
  - [发现（#/discover）](Library#发现discover) — 在线浏览 ExHentai、Popular、Watched 与 Toplist 热门榜单，支持游标翻页。
  - [系列作品（#/series）](Library#系列作品series) — 同人与漫画分类过滤、前缀剥离与标题聚类；支持归集云端未入库收藏并展示角标与一键入队，支持手动管理系列成员，扫库后自动重建聚类。
  - [画廊库（#/library）](Library#画廊库library) — 多维度字段排序、阅读状态互斥筛选、AND/OR 多标签过滤与 `-tag` 排除语法，提供批量加入收藏与删除熔断保护。
  - [本地列表（#/library）](Library#本地列表library) — 独立于 EH 的本地自定义书单生命周期管理与分类归类。
  - [标签（#/tags）](Library#标签tags) — 标签命名空间分组展示、词频热度排序与 EhTag 中文语义联想补全。
  - [历史（#/history）](Library#历史history) — 阅读时间线记录查看、历史记录清除与画廊进度重置。

- **[画廊详情与阅读 (Reading)](Reading)**：
  - [画廊详情（#/gallery/<id>）](Reading#画廊详情galleryid) — 缩略图网格进度定位、源站直达、标签元数据同步、画质状态识别与原图升级、CBZ 单本导出。
  - [阅读器（#/reader/<id>/<page>）](Reading#阅读器readeridpage) — 逐页流式加载，支持单页从左至右 (LTR)、日漫从右至左 (RTL)、双页跨页并排与条漫 Webtoon 连续滚动；支持触控缩放、`G` 键跳页、`F` 键全屏与列表筛选上下文记忆。

- **[下载管理 (Downloads)](Downloads)**：
  - [下载页（#/downloads）](Downloads#下载页downloads) — 粘贴 URL 或 GID 快速入队、新版本自动追踪、队列状态监控、全局暂停控制、GP 与配额显示、断点续传与指数退避。
  - [归档下载（ExHentai archive）](Downloads#归档下载exhentai-archive) — 官方整包 zip 下载通道、GP 费用预检、Range 断点续传与逐页降级回退机制。

- **[收藏与更新 (Favorites)](Favorites)**：
  - [收藏夹（#/favorites）](Favorites#收藏夹favorites) — 10 个云端收藏夹单夹与全量同步、元数据更新、跳过策略、夹内排序与批量迁移。
  - [收藏夹查重（#/duplicates/favorites）](Manage#重复副本与查重duplicates) — 跨收藏夹同作品多版本排查，旧路由 `#/favorites/manage` 兼容跳转。
  - [更新画廊（#/updates）](Favorites#更新画廊updates) — 重传换 GID 监测、新版下载入队、下载成功后清理旧版副本。
  - [「download favorites」与「启用」的区别](Favorites#download-favorites与启用的区别) — 定时后台巡检总开关与单文件夹独立启用的生效规则。
  - [三种模式的区别](Favorites#三种模式的区别) — 增量下载、仅监控与强制下载三种运行机制与数据影响。

- **[库维护 (Manage)](Manage)**：
  - [重复副本（#/duplicates）](Manage#重复副本与查重duplicates) — 同 GID 多路径副本排查、收藏夹重复与跨 GID 查重处理。
  - [回收站（#/recycle）](Manage#回收站recycle) — 手动删除与扫描丢失画廊管理，支持安全还原与彻底清除。
  - [缺页体检（#/integrity）](Manage#缺页体检integrity) — 损坏图片与缺失页面扫描，支持差量定向补页。
  - [冷库归档（#/archive）](Manage#冷库归档archive) — 本地目录打包为 CBZ 归档、任务取消与源目录反向清理。
  - [日志页（#/logs）](Manage#日志页logs) — 实时后台任务追踪与系统运行日志审计。

- **[系统设置 (Settings)](Settings)**：
  - [设置（#/settings）](Settings#设置settings) — 存储根目录配置、下载并发与看门狗调优、磁盘空间用量分布、多语言标题显示策略、Telegram Bot 接入、PWA 缓存与 OPDS 协议客户端鉴权。
  - [哪些操作要上网](Settings#哪些操作要上网) — 系统全功能网络访问分级清单（EH 云端交互、GitHub 检查、纯本地离线与本地优先缓存）。

---

## 旧锚点迁徙表

若你此前收藏或引用了旧版 `Usage.md` 的长文锚点，请参考下表对应到拆分后的新文档与章节：

| 旧锚点 (Old Anchor) | 对应新页面 | 对应新章节锚点 |
| :--- | :--- | :--- |
| `#浏览browse` | [浏览与库 (Library)](Library) | [浏览（#/browse）](Library#浏览browse) |
| `#发现discover` | [浏览与库 (Library)](Library) | [发现（#/discover）](Library#发现discover) |
| `#系列作品series` | [浏览与库 (Library)](Library) | [系列作品（#/series）](Library#系列作品series) |
| `#历史history` | [浏览与库 (Library)](Library) | [历史（#/history）](Library#历史history) |
| `#首次运行向导welcome` | [使用指南 (Usage)](Usage) | [首次运行向导（#/welcome）](Usage#首次运行向导welcome) |
| `#画廊库library` | [浏览与库 (Library)](Library) | [画廊库（#/library）](Library#画廊库library) |
| `#本地列表library` | [浏览与库 (Library)](Library) | [本地列表（#/library）](Library#本地列表library) |
| `#重复副本duplicates` | [库维护 (Manage)](Manage) | [重复副本（#/duplicates）](Manage#重复副本与查重duplicates) |
| `#回收站recycle` | [库维护 (Manage)](Manage) | [回收站（#/recycle）](Manage#回收站recycle) |
| `#缺页体检integrity` | [库维护 (Manage)](Manage) | [缺页体检（#/integrity）](Manage#缺页体检integrity) |
| `#画廊详情galleryid` | [画廊详情与阅读 (Reading)](Reading) | [画廊详情（#/gallery/<id>）](Reading#画廊详情galleryid) |
| `#阅读器readeridpage` | [画廊详情与阅读 (Reading)](Reading) | [阅读器（#/reader/<id>/<page>）](Reading#阅读器readeridpage) |
| `#标签tags` | [浏览与库 (Library)](Library) | [标签（#/tags）](Library#标签tags) |
| `#下载页downloads` | [下载管理 (Downloads)](Downloads) | [下载页（#/downloads）](Downloads#下载页downloads) |
| `#日志页logs` | [库维护 (Manage)](Manage) | [日志页（#/logs）](Manage#日志页logs) |
| `#收藏夹favorites` | [收藏与更新 (Favorites)](Favorites) | [收藏夹（#/favorites）](Favorites#收藏夹favorites) |
| `#收藏夹管理` | [库维护 (Manage)](Manage) | [收藏夹重复（#/duplicates/favorites）](Manage#重复副本与查重duplicates) |
| `#更新画廊` | [收藏与更新 (Favorites)](Favorites) | [更新画廊（#/updates）](Favorites#更新画廊updates) |
| `#归档下载exhentai-archive整包-zip` | [下载管理 (Downloads)](Downloads) | [归档下载（ExHentai archive）](Downloads#归档下载exhentai-archive) |
| `#download-favorites与启用的区别` | [收藏与更新 (Favorites)](Favorites) | [「download favorites」与「启用」的区别](Favorites#download-favorites与启用的区别) |
| `#三种模式的区别` | [收藏与更新 (Favorites)](Favorites) | [三种模式的区别](Favorites#三种模式的区别) |
| `#设置settings` | [系统设置 (Settings)](Settings) | [设置（#/settings）](Settings#设置settings) |
| `#哪些操作要上网` | [系统设置 (Settings)](Settings) | [哪些操作要上网](Settings#哪些操作要上网) |
