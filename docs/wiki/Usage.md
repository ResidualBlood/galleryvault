# 使用指南

> 中文 · [English](Usage-EN)
>
> **分册直达**：[浏览与库](Library) · [画廊详情与阅读](Reading) · [下载管理](Downloads) · [收藏与更新](Favorites) · [库维护](Manage) · [系统设置](Settings)

GalleryVault 采用单页应用（SPA）与 hash 路由体系（如 `#/library`、`#/gallery/7`），浏览器刷新与前进/后退均无需服务器往返。

桌面端顶栏主入口包含 Browse（浏览）、Discover（发现）、Library（画廊库）、Tags（标签）、Downloads（下载）、Favorites（收藏夹）与「管理」；History（历史）、Settings（设置）、Logs（日志）收纳于「更多」下拉菜单中。点击「管理」直达回收站，并可通过页内标签自由切换回收站（`#/recycle`）、重复副本（`#/duplicates`）与缺页体检（`#/integrity`），旧 hash 路由完全向下兼容；移动端汉堡菜单保持扁平展示。

顶栏可叠加黄条（全局暂停）、红条（Cookie 失效 / 无里站权限）与图片配额告警。🎲 旁的铃铛为**应用内通知中心**（下载完成/失败、扫库完成/失败、Cookie 失效/无权限；约 15 秒轮询，无需配置 Telegram 也可获知后台事件；Cookie 红条仍保留）。

---

## 首次运行向导（`#/welcome`）

首次部署后（仍在使用默认密码时），登录会自动进入 `#/welcome` 三步向导：

1. **修改默认密码**：把内置默认密码 `p1a2s3s4` 改成你自己的强密码（不可跳过，可随时在设置中修改）。
2. **连接 ExHentai**：选择 base URL（ExHentai 里站 / E-Hentai 外站 / 自定义代理子域）并填入 `ipb_member_id` / `ipb_pass_hash` / `igneous` cookie，可用「测试登录」验证（可跳过，详见后文 [配置 ExHentai Cookie](#配置-exhentai-cookie)）。
3. **填充画廊库**：点击「扫描库」或「立即检查所有收藏夹」（可跳过）。

每步完成会显示 ✓；点击「完成设置」即可进入主界面。已配置的实例登录不会强制进入向导，可在地址栏手动访问 `#/welcome` 重新查看。

## 推荐使用流程

为保证最佳的使用体验与元数据匹配准确率，推荐按以下步骤使用：

1. **配置账户 Cookie（可选但推荐）**：在向导或设置页中配置 ExHentai Cookie 并通过连通性测试。
2. **先缓存收藏夹元数据**：前往 [收藏与更新](Favorites)（`#/favorites`）点击「立即检查所有」，优先将云端收藏夹元数据与封面预热至本地缓存。
3. **扫描本地画廊入库**：将本地归档存入 `./library` 挂载目录，在 [浏览与库](Library) 点击「扫描库」。本地文件将自动比对云端已缓存元数据，实现高精度入库识别。
4. **查重与维护**：进入 [库维护](Manage) 的「重复副本（`#/duplicates`）」按策略清理多目录冗余文件；进入 [收藏与更新](Favorites) 的「收藏夹管理（`#/favorites/manage`）」标记并清理云端不同版本重复画廊。
5. **增量监控与日常阅读**：在收藏夹中启用目标文件夹并设为「增量下载」以追踪最新画廊；日常可在 [画廊详情与阅读](Reading) 中享受多模式阅读与搜索上下文保护。

## 配置 ExHentai Cookie

如需与 ExHentai 联通、同步收藏夹、在线拉取标签或下载画廊，需提供你在浏览器的登录 Cookie：

1. **获取 Cookie**：
   - 使用电脑浏览器登录 [E-Hentai](https://e-hentai.org) 或 [ExHentai](https://exhentai.org)；
   - 按 `F12` 打开开发者工具，切换到 **Application**（Chrome/Edge）或 **Storage**（Firefox）标签页；
   - 在左侧展开 **Cookies** 并选中目标站点域名；
   - 找到并复制以下三个字段的 Value：
     - `ipb_member_id`：用户 ID（纯数字）；
     - `ipb_pass_hash`：密码哈希（32 位字符串）；
     - `igneous`：里站专属访问凭据（访问 exhentai.org 必填；部分账号需里站权限才会有此字段）。
2. **填入系统**：
   - 在 `#/welcome` 向导第二步，或进入 [系统设置](Settings)（`#/settings`）的 **ExHentai** 配置区；
   - 基础 URL 保持默认 `https://exhentai.org`（若无里站权限可改为 `https://e-hentai.org`）；
   - 依次填入对应的三个字段；Cookie 在前端提交后不会回显。
3. **连通性验证与探活**：
   - 点击 **测试登录** 按钮，系统会即时验证 Cookie 的有效性并反馈连接结果；
   - 服务启动时会自动探活，且之后每 30 分钟轮询检测一次；
   - 当 Cookie 失效或账号缺少里站访问权限时，Web 界面顶栏会弹出明显的红色警告条，引导前往设置更新凭据。

> **安全提示**：Cookie 属于敏感凭据，请切勿将其写入仓库正文、公开文档或分享给他人。系统支持启用环境变量 `ENCRYPTION_KEY` 进行数据库静态加密保护（详见 [静态加密](Encryption)）。

## 文档分册目录

使用指南已拆分为以下各功能分册，点击即可深入查阅对应特性说明：

- **[浏览与库 (Library)](Library)**：
  - [浏览（#/browse）](Library#浏览browse) — 落地网格、继续阅读卡片区、键盘导航与全局快捷搜索
  - [发现（#/discover）](Library#发现discover) — 在线浏览 ExHentai、Popular / Watched / Toplist 热门与游标翻页
  - [画廊库（#/library）](Library#画廊库library) — 多维索引排序、阅读状态互斥过滤、AND/OR 多标签与 `-tag` 排除筛选、批量加收藏与批量删除熔断
  - [本地列表（#/library）](Library#本地列表library) — 完全解耦于 EH 的本地独立列表生命周期与归类
  - [标签（#/tags）](Library#标签tags) — 标签命名空间分组、词频检索与 EhTag 中文联想补全
  - [历史（#/history）](Library#历史history) — 阅读历史时间线管理与进度清除

- **[画廊详情与阅读 (Reading)](Reading)**：
  - [画廊详情（#/gallery/<id>）](Reading#画廊详情galleryid) — 缩略图按进度定位、原站直达、标签同步、画质推断与一键升级原图、CBZ 导出
  - [阅读器（#/reader/<id>/<page>）](Reading#阅读器readeridpage) — 逐页流式加载、LTR/日漫 RTL/双页并排/条漫 Webtoon 模式、移动端捏合缩放、`G` 精准跳页、`F` 图片全屏、搜索上下文粘性保留

- **[下载管理 (Downloads)](Downloads)**：
  - [下载页（#/downloads）](Downloads#下载页downloads) — 粘贴 URL/GID 批量入队、自动跟随新版、任务状态队列、全局暂停、GP 与配额看板、断点续传与指数退避自愈
  - [归档下载（ExHentai archive）](Downloads#归档下载exhentai-archive) — 官方整包 zip 通道、GP 余额/清晰度只读预检、Range 断点续传与逐页自动降级

- **[收藏与更新 (Favorites)](Favorites)**：
  - [收藏夹（#/favorites）](Favorites#收藏夹favorites) — 10 个收藏夹全量/单夹检查、元数据自动应用、跳过启发式、文件夹内排序与批量移动
  - [收藏夹管理与查重（#/favorites/manage）](Favorites#收藏夹管理与查重favoritesmanage) — 同作品多版本查重、批量取消收藏与物理删除
  - [更新画廊（#/updates）](Favorites#更新画廊updates) — 重传换 GID 智能检测、新版下载与旧版本地副本安全级联删除
  - [「download favorites」与「启用」的区别](Favorites#download-favorites与启用的区别) — 全局定时检查总开关与单文件夹启用逻辑矩阵
  - [三种模式的区别](Favorites#三种模式的区别) — 增量下载、仅监控、强制下载的行为机制

- **[库维护 (Manage)](Manage)**：
  - [重复副本（#/duplicates）](Manage#重复副本duplicates) — 跨扫描目录重复画廊（相同 GID）策略去重（保留已入库/新/大/多页或手动）
  - [回收站（#/recycle）](Manage#回收站recycle) — 用户删除与扫描失踪双分页、安全恢复与彻底删除
  - [缺页体检（#/integrity）](Manage#缺页体检integrity) — 记录页数与磁盘页数不一致扫描与一键补页
  - [日志页（#/logs）](Manage#日志页logs) — 后台任务实时进度与取消、系统运行时内存环形日志、动态调级、脱敏与导出

- **[系统设置 (Settings)](Settings)**：
  - [设置（#/settings）](Settings#设置settings) — 库根目录、下载看门狗与并发调优、标题显示（日文/英文/目录名）、账户安全、Telegram Bot 控制命令、PWA、主题、OPDS 与第三方客户端接入（Basic 鉴权）
  - [哪些操作要上网](Settings#哪些操作要上网) — 全功能网络访问分级清单（向 ExHentai 拉取、访问 GitHub、纯本地运行、本地优先）

---

## 旧锚点迁徙表

若你此前收藏或引用了旧版 `Usage.md` 的长文锚点，请参考下表对应到拆分后的新文档与章节：

| 旧锚点 (Old Anchor) | 对应新页面 | 对应新章节锚点 |
| :--- | :--- | :--- |
| `#浏览browse` | [浏览与库 (Library)](Library) | [浏览（#/browse）](Library#浏览browse) |
| `#发现discover` | [浏览与库 (Library)](Library) | [发现（#/discover）](Library#发现discover) |
| `#历史history` | [浏览与库 (Library)](Library) | [历史（#/history）](Library#历史history) |
| `#首次运行向导welcome` | [使用指南 (Usage)](Usage) | [首次运行向导（#/welcome）](Usage#首次运行向导welcome) |
| `#画廊库library` | [浏览与库 (Library)](Library) | [画廊库（#/library）](Library#画廊库library) |
| `#本地列表library` | [浏览与库 (Library)](Library) | [本地列表（#/library）](Library#本地列表library) |
| `#重复副本duplicates` | [库维护 (Manage)](Manage) | [重复副本（#/duplicates）](Manage#重复副本duplicates) |
| `#回收站recycle` | [库维护 (Manage)](Manage) | [回收站（#/recycle）](Manage#回收站recycle) |
| `#缺页体检integrity` | [库维护 (Manage)](Manage) | [缺页体检（#/integrity）](Manage#缺页体检integrity) |
| `#画廊详情galleryid` | [画廊详情与阅读 (Reading)](Reading) | [画廊详情（#/gallery/<id>）](Reading#画廊详情galleryid) |
| `#阅读器readeridpage` | [画廊详情与阅读 (Reading)](Reading) | [阅读器（#/reader/<id>/<page>）](Reading#阅读器readeridpage) |
| `#标签tags` | [浏览与库 (Library)](Library) | [标签（#/tags）](Library#标签tags) |
| `#下载页downloads` | [下载管理 (Downloads)](Downloads) | [下载页（#/downloads）](Downloads#下载页downloads) |
| `#日志页logs` | [库维护 (Manage)](Manage) | [日志页（#/logs）](Manage#日志页logs) |
| `#收藏夹favorites` | [收藏与更新 (Favorites)](Favorites) | [收藏夹（#/favorites）](Favorites#收藏夹favorites) |
| `#收藏夹管理` | [收藏与更新 (Favorites)](Favorites) | [收藏夹管理与查重（#/favorites/manage）](Favorites#收藏夹管理与查重favoritesmanage) |
| `#更新画廊` | [收藏与更新 (Favorites)](Favorites) | [更新画廊（#/updates）](Favorites#更新画廊updates) |
| `#归档下载exhentai-archive整包-zip` | [下载管理 (Downloads)](Downloads) | [归档下载（ExHentai archive）](Downloads#归档下载exhentai-archive) |
| `#download-favorites与启用的区别` | [收藏与更新 (Favorites)](Favorites) | [「download favorites」与「启用」的区别](Favorites#download-favorites与启用的区别) |
| `#三种模式的区别` | [收藏与更新 (Favorites)](Favorites) | [三种模式的区别](Favorites#三种模式的区别) |
| `#设置settings` | [系统设置 (Settings)](Settings) | [设置（#/settings）](Settings#设置settings) |
| `#哪些操作要上网` | [系统设置 (Settings)](Settings) | [哪些操作要上网](Settings#哪些操作要上网) |
