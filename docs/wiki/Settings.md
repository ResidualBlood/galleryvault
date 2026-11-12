# 系统设置

> 中文 · [English](Settings-EN) | 属于 [使用指南](Usage) 系列

设置分组、保存规则、各分组字段、OPDS、Telegram Bot，以及哪些操作需要访问网络。

## 设置（`#/settings`）

设置按 13 个分组组织，左侧（移动端为抽屉）是分组导航，顶部提供按键名 / 标题 / 说明搜索。

**保存规则**：

- 按组保存，且**只提交本组改动过的键**；未展示或未改动的键保持原值，不会被整表写回默认值。
- 标记「安全敏感」的键（需要登录、可信代理、下载根目录、库根目录）保存时需输入当前管理员密码；未配置密码时需一次显式确认，缺少确认返回 `428`。
- 凭据类字段（EH Cookie、Telegram Bot Token、API token）只写不回显；状态用「已配置 / 未配置」表示。
- 动作按钮（测试登录、生成缩略图、同步标签、生成 token 等）与配置项分区摆放；页面内快捷入口保留在各自功能页。

| 分组 | 主要内容 | 存储 |
| :--- | :--- | :--- |
| 1 外观与语言 | 主题、界面语言、标题显示、列表每页条数 | 浏览器 / 后端 |
| 2 阅读器 | 阅读模式、图片适配、幻灯片间隔、在线取图通道 | 浏览器 |
| 3 E-Hentai 站点与网络 | 站点地址、Cookie、代理、H@H 开关、在线并发与缓存、页面并发上限 | 后端 / 环境变量 |
| 4 在线浏览与快捷操作 | 默认收藏夹、在线列表默认筛选 | 浏览器 |
| 5 资料库 | 库根目录、查重策略、缩略图生成 | 后端 |
| 6 下载 | 下载根目录、并发、画质、标题命名、慢速重试阈值、全局暂停镜像 | 后端 |
| 7 收藏夹同步 | 收藏夹自动下载、归档开关与页数阈值；每个收藏夹的独立配置仍在收藏页 | 后端 |
| 8 归档与冷存储 | 冷存储目录、自动归档、归档后删除源、归档画质与降级页数 | 后端 |
| 9 标签 | 自动同步、翻译更新、分类修复 | 后端 |
| 10 通知 | Telegram Bot 与会话 | 后端 |
| 11 账户与安全 | 访问控制、密码、会话、API token、登出 | 后端 |
| 12 集成 | 伴侣脚本、Comic Looms、OPDS 地址 | — |
| 13 存储与系统 | 存储面板、最大画廊、运行日志入口、PWA | — |

### 1. 外观与语言

| 设置项 | 字段 / 取值 | 说明与默认值 |
| :--- | :--- | :--- |
| 界面主题 | `gv_theme` | 顶栏 ◐ 图标切换深色 / 浅色 / 跟随系统（`system`），持久化于本地存储，默认深色。 |
| 界面语言 | `gv_lang` | 中文 / English，同时更新 `<html lang>`。 |
| 标题显示 | `title_display` | `japanese` / `english` / `directory`；画廊库、浏览、详情、收藏夹、收藏查重与副本去重页的标题策略。默认 `japanese`（日文优先，无日文回退英文）。 |
| 每页条数 | `gv_page_size` | 列表分页大小；各列表页保留快捷下拉入口。 |

### 2. 阅读器

| 设置项 | 字段 / 取值 | 说明与默认值 |
| :--- | :--- | :--- |
| 阅读模式 | `gv_reader_mode` | 单页 LTR / RTL、双页、双页 RTL、条漫；阅读器内保留快捷切换。 |
| 图片适配 | `gv_reader_fit` | 适高 / 适宽 / 原始尺寸；旧版仅存在内存，新版持久化到本设备。 |
| 幻灯片间隔 | `gv_slideshow_interval` | 秒；阅读器与画廊详情共用同一来源。 |
| 在线取图通道 | `gv_online_image_mode` | `direct`（默认，浏览器直连 H@H，不占服务端图片额度）/ `proxy`（服务器代理，仅本机无法直连时按设备开启）。详见 [在线阅读](Online-Reading#阅读器与两种取图模式)。 |

### 3. E-Hentai 站点与网络

| 设置项 | 参数 / 字段 | 说明与默认值 |
| :--- | :--- | :--- |
| ExHentai 基础 URL | `exhentai_base_url` | 仅支持 `exhentai.org` / `e-hentai.org` 或其子域。 |
| Cookie 认证 | `ipb_member_id`<br>`ipb_pass_hash`<br>`igneous` | 配置后通过「测试登录」验证，字段只写不回显；状态由 `exhentai_cookie_configured` 表示。获取流程见 [入门向导与 Cookie 配置](Usage#配置-exhentai-cookie)。 |
| 连通性探活 | 周期探活 | 启动时探活，之后每 30 分钟检查一次；Cookie 失效、无里站权限或 IP 封禁显示红条，网络失败显示橙条，均链接至设置页。 |
| 网络代理 | `http_proxy` / `socks5_proxy` | 二选一，同时填写会被拒绝。 |
| 使用 H@H 节点 | `use_hah` | 向 EH 请求时是否附带 H@H 偏好（`uh` cookie），影响图片由 H@H 节点还是主站提供。 |
| 在线并发 | `online_reader_concurrency` | 在线解析与代理共用上限，默认 3（1–16）。 |
| 在线缓存上限 | `online_cache_max_mb` | 仅服务器代理回退时的图片缓存，默认 512 MB。 |
| EH 页面并发上限 | `exhentai_max_concurrency` | 只读，由环境变量 `EXHENTAI_MAX_CONCURRENCY` 控制（1–32，默认 6）；EH 页面 / gdata / 收藏夹请求共用该预算。 |
| 302 探针间隔 | `GV_CHALLENGE_PROBE_INTERVAL` | 环境变量，默认 600 秒。 |
| 单任务挑战暂停上限 | `GV_MAX_CHALLENGE_PAUSES` | 环境变量，默认 5 次；达到后任务标记失败并保留剩余重试预算。 |
| 安全响应头 | 全部响应 | 后端为 API 与页面响应附加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: same-origin` 与 `Content-Security-Policy`（含 `frame-ancestors 'none'`、`worker-src 'self'`，在线图片仅放开 `img-src`）。 |

### 4. 在线浏览与快捷操作

| 设置项 | 字段 / 取值 | 说明与默认值 |
| :--- | :--- | :--- |
| 默认收藏夹 | `gv_default_favcat` | 在线卡片与详情页快捷收藏的目标收藏夹；首次收藏时弹选择并可记住。 |
| 在线列表默认筛选 | `gv_online_defaults` | 列表类型、Toplist 周期与最低评分；旧版只写在 URL 里，不记忆。 |

### 5. 资料库

| 设置项 | 参数 / 取值 | 说明与约束 |
| :--- | :--- | :--- |
| 库根目录 | `library_roots` | 路径列表，每行一个。默认 `/library` 与 `/downloads`；路径末尾斜杠不影响去重；扫描根目录本身永远不是合法的删除目标。只读警告由 `library_root_warnings` 展示。 |
| 重复画廊策略 | `duplicate_policy` | 同 GID 多副本的默认保留规则（`keep_first` / `prefer_more_pages` / `prefer_newer`，以及手动指定）；查重页提供入口。 |
| 缩略图生成 | `generate_thumbnails` | 自动生成开关与「立即生成」操作，显示实时状态；worker 数由 `THUMBNAIL_WORKERS` 控制（1–16，默认 4）。 |
| 压缩包与文档 | `.7z` / `.pdf` | 识别 `.7z`（只收图，阅读时内存解压，单页上限 128MB）与 `.pdf`（抽取内嵌图片，单图超过 128MB 或抽取失败则跳过）。 |

### 6. 下载

| 设置项 | 参数 / 取值 | 说明与默认值 |
| :--- | :--- | :--- |
| 下载根目录 | `download_root` | 新增任务写入的目标热目录；安全敏感。 |
| 并发画廊数 | `download_concurrency` | 同时进行的画廊任务数，修改后立即生效。 |
| 归档传输并发 | 固定上限 | 官方归档 zip 的流式传输最多 2 路，与画廊并发独立；中断续传复用已申请的链接。 |
| 单画廊并发页数 | `page_concurrency` | 单个画廊同时拉取的图片数，默认 `4`。H@H 节点对单 IP 并发有限，过高易出现连接错误。 |
| 下载画质 | `download_quality` | 普通 / 原图。 |
| 下载标题命名 | `download_title` | 仅控制下载目录新文件夹命名：`japanese`（默认，`gid-日文标题`）或 `english`；与界面「标题显示」独立，已下载画廊不改名。 |
| 慢速 H@H 看门狗 | `image_download_timeout_seconds`<br>`image_slow_warmup_seconds`<br>`image_min_speed_kb_s` | 单图最大耗时、预热窗口与最低速率（默认预热 30 秒、低于 10KB/s 判定限速）；同样适用于归档 zip 传输。 |
| 全局暂停 | `global_paused` | 下载页按钮与 Telegram `/pause`、`/resume` 共用；此处镜像状态并提供入口。 |

### 7. 收藏夹同步

| 设置项 | 字段 / 取值 | 说明与默认值 |
| :--- | :--- | :--- |
| 收藏夹自动下载 | `download_favorites_enabled` | 总开关；关闭时收藏夹只检查、不下载。 |
| 收藏夹归档 | `favorites_archive_enabled` | 定时扫描大画廊时走官方归档通道。 |
| 归档页数阈值 | `favorites_archive_max_pages` | `0` 表示全部。 |
| 每夹独立配置 | `favorites[].enabled` / `.mode` / `.poll_interval_minutes` | 收藏页维护；设置页只给入口，不重复编辑。 |

### 8. 归档与冷存储

| 设置项 | 参数 / 取值 | 说明与约束 |
| :--- | :--- | :--- |
| 冷存储目录 | `archive_roots` | 多行路径（如 `/archive`）；留空不启用，旧配置 `cold_storage_root` 自动转为单项。挂载与容量均衡见 [部署指南 → 冷热分层存储](Deployment#2-冷热分层存储多盘挂载与归档规则)。 |
| 自动归档 | `auto_archive_downloads` | 默认关闭。 |
| 归档后删除源 | `archive_delete_source` | 默认关闭。 |
| 冷归档规格 | 限制规格 | 单卷上限 **500 页且 2GiB**（取 AND），超限生成冷目录而非单卷 CBZ；CBZ 路径 `{cold}/cbz/{hh}/{ii}/{gid}-{DB 英文标题}.cbz`，内含 `.galleryvault.json`。操作入口在 **管理 → 冷库归档**（`#/archive`）。 |
| 归档画质 | `archive_quality` | 官方整包归档的默认画质档位。 |
| 归档降级为逐页 | `archive_fallback_pages` | 默认开启；归档通道不可用时转逐页下载，不扣 GP。 |
| 清理残留 | 存储操作 | 清理已归档源目录残留文件，自动跳过 pending / downloading 任务。 |

### 9. 标签

| 设置项 | 字段 / 操作 | 说明与行为 |
| :--- | :--- | :--- |
| 标签自动同步 | `auto_sync_tags` / `tag_sync_interval_seconds` / `tag_sync_concurrency` | 扫描或启动后自动同步标签元数据；提供「立即同步标签」。 |
| 翻译自动更新 | `tag_translation_update_interval_minutes` | 0 表示关闭（默认 720）；提供「立即更新」与状态。 |
| 本地分类修复 | 离线操作 | 依据本地 `.galleryvault.json` 标签重推大类，不访问外网。 |

### 10. 通知

- **基础配置**：`telegram_bot_token`（只写不回显）、`telegram_chat_ids`、`telegram_allowed_user_ids`，提供「发送测试消息」；配置 token 后启动会自动注册客户端指令菜单。
- **通知选项**：`telegram_notify_level` 支持汇总 / 即时 / 仅失败 / 关闭；`telegram_notify_lang` 支持中文 / English。下载、扫库、收藏夹检查、302 挑战告警与 Bot 回复统一采用该语言。消息使用 Telegram HTML 格式（标题加粗、GID 等宽），画廊标题保持原文。

**控制命令表**（仅限允许的 user ID；聊天框输入 `/` 可见菜单）：

| 分类 | 命令 | 说明 |
| :--- | :--- | :--- |
| 系统与运维 | `/status`<br>`/ping`<br>`/cookie`<br>`/quota`<br>`/storage`<br>`/scan`<br>`/help` | 查看运行状态与队列概况；测试延迟；检查 Cookie 有效性；查看图像配额与 GP；查看磁盘用量；触发扫库；查看命令说明。 |
| 下载与队列 | `/queue`<br>`/pause`<br>`/resume`<br>`/retry <id/all>`<br>`/cancel <id/gid>`<br>`/clear`<br>`/stats` | 查看队列与操作按键；全局暂停与恢复；重试失败任务；取消任务；清除成功记录；查看库本数与队列快照。 |
| 后台任务 | `/tasks`<br>`/kill <name>` | 查看长任务列表；中断指定任务。 |
| 图库 | `/search <关键词>`<br>`/info <gid>`<br>`/random`<br>`/redownload <gid>` | 本地搜索与翻页；查看画廊详情与封面；随机抽取画廊；重新下载指定画廊。 |
| 收藏夹 | `/fav_sync`<br>`/fav_download [0-9]`<br>`/fav_check` | 同步收藏夹分类；下载指定收藏夹未入库项；全量检查收藏夹更新。 |

**全局暂停与 URL 交互**：

- `/pause` 持久化于 `app_config.user_settings`，重启后仍生效；停止认领新画廊，已开始的当前页下载完成，队列不丢失。Web 下载页暂停按钮与 Bot 共用 `GET/POST /api/pause`。
- 在聊天框粘贴画廊 URL 会自动解析 GID 与 token，未暂停时立即入队并回复确认与标题；404 或已删除的画廊不入队并提示。

### 11. 账户与安全

| 设置项 | 字段 / 操作 | 说明与默认值 |
| :--- | :--- | :--- |
| 需要登录 | `auth_required` | 切换是否启用登录认证；安全敏感。 |
| 修改密码 | — | 修改后撤销所有已登录会话。 |
| 会话时长 | `galleryvault_session`<br>`galleryvault_csrf` | 默认 10 年（`315360000` 秒）；修改密码或重置签名密钥后现存会话立即失效。 |
| 安全确认 | 当前密码 / 显式确认 | 修改「需要登录」「可信代理」「下载根目录」「库根目录」需当前管理员密码；未配置密码时需一次显式确认（否则 `428`）。 |
| 登录保护 | `429` / `Retry-After` | 连续失败 5 次后按指数退避（5 秒起，最长 15 分钟）；另有每 IP 每分钟 10 次的独立限速。计数在进程内，多进程各自计数，重启清零。 |
| 伴侣脚本 API token | 生成 / 撤销 | 用于伴侣用户脚本的 Bearer 认证。明文只显示一次（`POST /api/auth/api-token`），`GET` 只返回是否已配置与创建时间，`DELETE` 立即撤销。只能在已登录会话中管理，Bearer 不能生成或撤销 token。安装见 [在线阅读 → 伴侣脚本](Online-Reading#伴侣脚本可选增强零服务端额度)。 |
| 登出 | — | 清除会话 Cookie；顶栏同时提供入口。 |

### 12. 集成

| 功能 | 协议 / 路径 | 认证方式与行为 |
| :--- | :--- | :--- |
| 伴侣脚本 | `/galleryvault-companion.user.js` | 在官方 EH 画廊页注入状态、下载、收藏与跳转按钮；用 API token 认证，只访问白名单接口。 |
| 阅读增强 | Comic Looms | 官方页的阅读器增强由第三方脚本提供，本项目不内置、不复制其代码。 |
| OPDS 目录 | `GET /api/opds` | 返回最近入库最多 50 条画廊（Atom XML），acquisition 指向 `GET /api/galleries/{id}/export.cbz`。 |
| OPDS 认证 | HTTP Basic | 用户名固定 `galleryvault`（非 EH 账号），密码为 Web 登录密码；亦支持 Cookie。未认证返回 `401` 并带 `WWW-Authenticate: Basic realm="GalleryVault OPDS"`。 |
| CBZ 导出 | `GET/HEAD /api/galleries/{id}/export.cbz` | 与 OPDS 相同的 Basic 认证或 Cookie 会话；常规 `/api/*` 请求仍只支持 Cookie 会话。 |

### 13. 存储与系统

| 功能 | 说明 |
| :--- | :--- |
| 磁盘用量表 | 显示 library、cold、downloads、cache 四行路径、条目数、已用空间与磁盘剩余；列出体积最大的 10 本画廊。打开设置页不扫描全盘；统计不跨文件系统挂载点，硬链接只计一次。 |
| 运行日志 | 日志级别与过滤留在日志页（`#/logs`），此处只给入口。 |
| PWA | 支持添加到主屏幕；Service Worker 缓存页面壳与静态资源（network-first），明确不缓存画廊图片与 `/api/` 响应。 |

## 哪些操作要上网

| 网络对象 | 操作 | 条件与行为 |
| :--- | :--- | :--- |
| **ExHentai / E-Hentai 源站** | 在线浏览与搜索 | 访问普通搜索、热门、关注与排行榜；后端短期缓存结果（60s / 120s）。 |
| | 在线阅读（直连） | 后端每页解析一次图片地址（页面预算）；图片由浏览器直接向 H@H 取回，不占服务端图片并发与带宽。 |
| | 在线阅读（服务器代理回退） | 图片经本服务转发，占用服务端图片并发（12）与缓存；默认关闭，按设备开启。 |
| | 普通分页下载 | 并发受限，原图与普通请求分别控制，通过 H@H 节点拉取。 |
| | 官方归档整包下载 | 扣除 GP 或配额，直接拉取源站打包文件。 |
| | 标签与元数据同步 | 批量调用 gdata 接口拉取元数据、在线分类与画质探测信息。 |
| | 收藏夹双向管理 | 定期拉取云端分类、数量与列表；向云端提交添加、移除、移动分类或备注修改。 |
| | Cookie 探活与配额检查 | 启动及每 30 分钟周期探活；只有确认是有效会话页（`/uconfig.php` 成员页特征）才判定正常；反爬阻断（Challenge / 509）后自动探活恢复。 |
| | 画廊新版本下载 | 一键更新创建新下载任务时，拉取新 GID 的画廊数据。 |
| **GitHub API (`api.github.com`)** | EhTag 翻译词库 | 检查并拉取 EhTag 数据库更新。 |
| **Telegram Bot API (`api.telegram.org`)** | 推送通知与交互 | 推送通知与 Bot 长轮询交互（需配置 Bot Token）。 |
| **纯本地离线（不访问外网）** | 画廊详情与本地阅读 | 详情页读取本地数据库，阅读器仅加载本地文件。 |
| | 库维护与冷库归档 | 扫描本地磁盘入库、CBZ 冷库打包、源文件清理、OPDS 目录与 CBZ 导出、回收站操作。 |
| | 收藏夹更新初筛 | 基于本地记录与标题做文本匹配初筛，不发起外网请求。 |
| | 本地分类修复 | 依据本地 `.galleryvault.json` 标签重推大类。 |
| **本地优先缓存例外** | 详情与入队准备 | 详情优先读取本地数据库；入队准备优先复用本地元数据，缺失时才请求 gdata。 |
| | 封面与配额缓存 | 远程封面先查本地缓存目录；GP 与配额在缓存有效期内不重复请求源站。 |
| | PWA 资源缓存 | Service Worker 以 network-first 缓存页面文档与静态资源；不缓存画廊图片与 `/api/` 响应。 |
