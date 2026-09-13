# 系统设置

> 中文 · [English](Settings-EN) | 属于 [使用指南](Usage) 系列

本文档介绍 GalleryVault 的系统配置选项、客户端/OPDS 集成、Telegram 机器人控制、以及各功能模块的网络访问行为。

## 设置（`#/settings`）

- **账户**：修改密码（改密码会**撤销所有已登录会话**）、切换「需要登录」。Web 会话 Cookie（`galleryvault_session`）与 CSRF Cookie（`galleryvault_csrf`）默认有效时长为 10 年（`315360000` 秒），支持长期免重复登录；改密码或重置签名密钥后全量现存会话立即失效。
- **界面**：
  - **标题显示**：`japanese`（默认，日文标题优先）/ `english`（英文标题优先）/ `directory`（目录名）。画廊库、浏览、画廊详情、收藏夹（含纯云端项）、收藏夹查重与重复副本去重页的标题都跟随此设置。
- **站点与代理**：
   - **ExHentai**：基础 URL（仅 `exhentai.org` / `e-hentai.org` 或其子域）与 `ipb_member_id` / `ipb_pass_hash` / `igneous` cookie，**测试登录**验证；cookie 不会回显。启动时探活、之后每 30 分钟；Cookie 失效、无里站权限或 IP 封禁出红条，探活网络失败出橙条，均链到设置（登录后也会立刻刷新一次）。具体获取与配置流程请参阅 [入门向导与 Cookie 配置](Usage#配置-exhentai-cookie)。
  - **代理**：HTTP 或 SOCKS5（二选一）。
- **资料库**：
   - **库根目录**：每行一个文件系统路径。默认含 `/library` 与 `/downloads`（新下载仍只写入 `download_root`，但扫库会扫 downloads）。删除画廊时若挂载可写会一并删除这里的对应文件，若为只读挂载则删除失败并在 toast 与日志页提示。
- **归档 / Archive**：和库根在同一「资料库」分区。多行 `archive_roots`（如 `/archive`、`/archive2`），留空 = 不启用。旧字段 `cold_storage_root` 读入时升成单元素列表。写入挑「剩余空间 ≥ 预估 × 1.2 且最空」的根；扫库会扫全部归档根。默认不自动归档、归档后不删源。CBZ 名固定 `gid-英文标题.cbz`，不跟 `download_title`。单卷上限 **500 页且 2GiB**（两者取 AND），超限自动切卷。打包与清理操作在 **管理 → 冷库归档**（`#/archive`）；设置页存储表也有「清理已归档源目录残留文件」，跳过 pending/downloading。
- **磁盘用量**：表里四行 **library / cold / downloads / cache**（路径、条目数、已用、盘剩余）。library/cold 显示画廊数与图片数，cache 显示缩略图约数。打开设置页不扫全盘。下面列出体积最大的 10 本。
- **下载常用**：根目录、并发画廊数、**单画廊并发页数**（默认 4——H@H 节点对同一出口 IP 的并发连接数有限，设太高会顶穿限制、在线路不稳时大量报连接错误；求稳就保持低值，线路干净想榨带宽再调高）、画质（普通/原图）、**归档下载质量**（归档默认档位）、**归档不可用降级为逐页下载**（默认开；归档通道无法服务该画廊时自动转逐页，不扣 GP、走 H@H）；**下载标题**：仅控制**下载热目录** `download_root` 新建文件夹命名——`japanese`（默认，`gid-日文标题`，无日文标题时 fallback 英文）/ `english`（`gid-英文标题`），与显示用「标题显示」相互独立（冷库 CBZ 固定使用英文标题，不受此项影响），已下载的画廊会复用原有目录，切换设置不会改名或重复下载。
- **下载高级选项（折叠）**：H@H 开关、归档默认画质、`favorites_archive_max_pages`（归档页数阈值，0=全部）、定时扫描大画廊走归档、归档不可用降级为逐页。慢速 H@H 看门狗：单图最大耗时、预热窗口、最低 KB/s。302 探针间隔环境变量 `GV_CHALLENGE_PROBE_INTERVAL`（默认 600 秒）。
- **标签**：
  - **标签同步**：扫描/启动后自动同步、间隔、并发，**立即同步标签**。
  - **翻译自动更新**：间隔（分钟，0=关闭）与**立即更新**（按钮在本页，不在日志页）。
  - **本地分类秒级自愈**：不访问外网，用本地元数据 / `.galleryvault.json` 把误标成 Misc/Other 的大类改回来。
- **缩略图**：自动生成开关、**立即生成**；下方显示缩略图**实时状态**。后台包含定时维护机制：**孤儿文件自动清理**（定期扫描缓存目录，清理数据库中已无对应画廊记录的孤立缩略图文件，释放磁盘空间）与**周期播种机制**（后台定期巡检并为新入库或缺失缩略图的画廊补齐首页及全量缩略图播种任务），保障缓存完整性且无无效文件堆积。
- **Telegram（折叠）**：bot token、chat ID、允许的 user ID，**发送测试消息**验证；**通知级别**（汇总 / 即时 / 仅失败 / 关闭）与**通知语言**（中文 / English）——下载、扫库、收藏夹检查、302 临时挑战告警（🚨 触发/✅ 恢复）与 bot 回复统一用该语言发送，消息采用 Telegram HTML 格式（标题加粗、gid 等宽），画廊标题保持原文不翻译。配置 token 后启动会自动向 Telegram 注册客户端指令菜单。
- **PWA**：可「添加到主屏幕」。Service worker 只缓存 html/css/js 壳（js/css **network-first**，成功再写入缓存；离线回退缓存），**不缓存画廊图片与 `/api/`**。
- **浅色主题**：顶栏 ◐ 切换；`localStorage gv_theme=dark|light`，默认 dark。
- **7z / PDF 扫描**：库扫描识别 `.7z`（py7zr，只收图）与 `.pdf`（抽取内嵌图；抽不到则跳过并 warning）。
- **OPDS 与 CBZ 导出**：`GET /api/opds`（atom+xml）列出**最近入库最多 50 条**，acquisition 链到 `GET /api/galleries/{id}/export.cbz`。OPDS 端点支持 HTTP Basic 认证（用户名固定为 `galleryvault`，不是 EH 账号；密码为本站 Web 登录密码），便于第三方阅读器接入；Cookie 鉴权仍完全可用。未提供凭据或认证失败时返回 `401 Unauthorized` 并携带响应头 `WWW-Authenticate: Basic realm="GalleryVault OPDS"`。CBZ 导出及其实际 API 路由需常规登录会话，其余 `/api/*` 均为 Cookie-only。
- **Telegram bot 控制命令**（仅「允许的 user ID」；聊天框输入 `/` 可见菜单）：

  | 分类 | 命令 |
  | :--- | :--- |
   | 系统与运维 | `/status` 运行状态与队列概况；`/ping` 延迟；`/cookie` Cookie 有效性；`/quota` 图像配额与 GP；`/storage` 磁盘用量；`/scan` 触发扫库；`/help` 命令说明 |
  | 下载与队列 | `/queue` 队列 + InlineKeyboard；`/pause` `/resume` 全局暂停；`/retry <id/all>`；`/cancel <id/gid>`（找不到会回复）；`/clear` 清成功记录；`/stats` 库本数与队列快照 |
  | 后台任务 | `/tasks` 长任务列表；`/kill <name>` 中断 |
  | 图库 | `/search <关键词>` 本地检索翻页；`/info <gid>` 详情与封面（5 级降级）；`/random`；`/redownload <gid>` |
  | 收藏夹 | `/fav_sync` 同步分类；`/fav_download [0-9]` 下未入库；`/fav_check` 全量检查更新 |

  `/pause` 为**全局暂停**（持久化到 `app_config.user_settings`，重启后仍生效）：**停止 claim 新画廊 + 暂停后不再领取新页，已开始的当前页会下完（已入队的画廊不丢，恢复后继续）**，同时暂停**自动扫描**与 **Web 端新扫描**（扫描触发返回 `paused`）。Web 下载页暂停按钮与 Bot `/pause` `/resume` 操作**同一开关**（`GET/POST /api/pause`），顶栏黄条与 Cookie 红条可叠加。暂停期间粘贴的画廊 URL 会被忽略、不入队。**直接粘贴画廊 URL**（如 `https://exhentai.org/g/2325283/d3722b6aa8/`，首尾多余 `/` 也可）解析 gid/token 立即入队，回复带**标题**（有新版说明旧→新 gid；404/删除则提示未入队）。未知非 URL 文本回 `/help`。

## 哪些操作要上网

| 分级 | 操作 |
| --- | --- |
| 访问 ExHentai | 发现页（搜索 / Popular / Watched / Toplist）、下载（gdata / 画廊页 / H@H / 原图 / Archive / GP 与配额）、测试登录、收藏夹同步与增删改、缺封面、标签同步、联网分类回填、画质回填 |
| 访问 GitHub | EhTag 词库「立即更新」（不打 EH） |
| 只本地 | 库搜索、阅读器、缩略图、进度/历史、本地星级与列表、导出 CBZ、回收站、扫盘、更新页对比、查重、日志、磁盘用量、OPDS、**本地分类秒级自愈** |
| 先本地 | 入队缺元数据才 gdata；详情读 DB；封面/配额先缓存 |
