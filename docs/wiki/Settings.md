# 系统设置

> 中文 · [English](Settings-EN) | 属于 [使用指南](Usage) 系列

本文档介绍 GalleryVault 的系统配置选项、客户端/OPDS 集成、Telegram 机器人控制、以及各功能模块的网络访问行为。

## 设置（`#/settings`）

- **库根目录**：每行一个文件系统路径；新下载不会写入这里。删除画廊时若挂载可写会一并删除这里的对应文件，若为只读挂载则删除失败并在 toast 与日志页提示。
- **下载**：根目录、并发画廊数、**单画廊并发页数**（默认 4——H@H 节点对同一出口 IP 的并发连接数有限，设太高会顶穿限制、在线路不稳时大量报连接错误；求稳就保持低值，线路干净想榨带宽再调高）、画质（普通/原图）、**归档下载质量**（归档默认档位）、**归档不可用降级为逐页下载**（默认开；归档通道无法服务该画廊时自动转逐页，不扣 GP、走 H@H）、H@H 网络、`max_pages`。慢速 H@H 节点看门狗：**单图最大耗时（秒）**、**慢速预热窗口（秒）**、**单图最低速度（KB/s）**——超过总时长预算、或预热窗口后平均速度低于下限的单张图片会被中断并按退避重试，不再长时间拖住整个画廊。
- **标题显示**（下载设置组内）：`japanese`（默认，日文标题优先）/ `english`（英文标题优先）/ `directory`（目录名）。画廊库、浏览、画廊详情、收藏夹（含纯云端项）、收藏夹查重与重复副本去重页的标题都跟随此设置。
- **下载标题**（下载设置组内）：控制下载目录的文件命名——`japanese`（默认，`gid-日文标题`）/ `english`（`gid-英文标题`）。与显示用「标题显示」相互独立；已下载的画廊会复用原有目录，切换设置不会改名或重复下载。
- **账户**：修改密码（改密码会**撤销所有已登录会话**）、切换「需要登录」。
- **ExHentai**：基础 URL 与 `ipb_member_id` / `ipb_pass_hash` / `igneous` cookie，**测试登录**验证；cookie 不会回显。启动时探活、之后每 30 分钟；Cookie 失效或无里站权限时顶栏分别展示对应红条并链到设置（登录后也会立刻刷新一次）。具体获取与配置流程请参阅 [入门向导与 Cookie 配置](Usage#配置-exhentai-cookie)。
- **代理**：HTTP 或 SOCKS5（二选一）。
- **标签同步**：扫描/启动后自动同步、间隔、并发，**立即同步标签**。
- **Thumbnails**：自动生成开关、**立即生成**；下方显示缩略图**实时状态**。
- **Telegram**：bot token、chat ID、允许的 user ID，**发送测试消息**验证；**通知级别**（汇总 / 即时 / 仅失败 / 关闭）与**通知语言**（中文 / English）——下载、扫库、收藏夹检查与 bot 回复统一用该语言发送，消息采用 Telegram HTML 格式（标题加粗、gid 等宽），画廊标题保持原文不翻译。
- **磁盘用量**：设置页展示 library / downloads / cache 用量，以及库内体积最大的 10 本（读 DB `storage_size`，不对万本 `du`）。目录不存在该项为 0。
- **PWA**：可「添加到主屏幕」。Service worker 只缓存 html/css/js 壳（js/css **network-first**，成功再写入缓存；离线回退缓存），**不缓存画廊图片与 `/api/`**。
- **浅色主题**：顶栏 ◐ 切换；`localStorage gv_theme=dark|light`，默认 dark。
- **7z / PDF 扫描**：库扫描识别 `.7z`（py7zr，只收图）与 `.pdf`（抽取内嵌图；抽不到则跳过并 warning）。
- **OPDS 与 CBZ 导出**：`GET /api/opds`（atom+xml）列出最近入库，acquisition 链到 `GET /api/galleries/{id}/export.cbz`。这两个端点支持 HTTP Basic 认证（用户名固定为 `galleryvault`，不是 EH 账号；密码为本站 Web 登录密码），便于第三方阅读器（Tachiyomi / Panels / Chunky 等）接入；Cookie 鉴权仍完全可用。未提供凭据或认证失败时返回 `401 Unauthorized` 并携带响应头 `WWW-Authenticate: Basic realm="GalleryVault OPDS"`。除这两个端点外，其余 `/api/*` 均为 Cookie-only。
- **Telegram bot 控制命令**（在「允许的 user ID」账号发给 bot）：`/help` 列出命令，`/queue` 查看等待/进行中/失败摘要，`/stats` 库本数 + 队列 pending/downloading/failed，`/cancel <id|gid>` 取消任务（找不到会回复，不静默），未知非 URL 文本会回帮助；`/pause` 暂停接收新 URL（暂停期间粘贴的画廊 URL 会被忽略、不入队）、`/resume` 恢复接收、`/status` 查看暂停状态；`/pause` 为**全局暂停**（持久化到 `app_config.user_settings`，重启后仍生效）：**停止 claim 新画廊 + 暂停后不再领取新页，已开始的当前页会下完（已入队的画廊不丢，恢复后继续）**，同时暂停**自动扫描**与 **Web 端新扫描**（扫描触发返回 `paused`），Web 下载页的暂停按钮与 Bot 的 `/pause` / `/resume` 操作**同一开关**（`GET/POST /api/pause`），网页暂停后 Bot 一致，顶栏黄条与 Cookie 红条可叠加显示。**直接粘贴画廊 URL**（如 `https://exhentai.org/g/2325283/d3722b6aa8/`）会解析 gid/token 并立即入队下载，bot 回复带**标题**（有新版会说明旧→新 gid；404/删除则提示未入队）。
- **翻译自动更新**：间隔（分钟，0=关闭）与**立即更新**。

## 哪些操作要上网

| 分级 | 操作 | 说明 |
| --- | --- | --- |
| 会向 ExHentai 拉取数据 | 发现页搜索 | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | Popular | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | Watched | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | Toplist | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 下载执行（gdata / 画廊页 / showpage / H@H） | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 原图 fullimg.php | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | Archive archiver.php | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | Archive 预览+GP | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 配额 home.php / exchange.php | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | Cookie 测试 | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 收藏全量同步 favorites.php+gdata | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 同步分类名 | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 加入/移出/移动收藏与 Note（云端成功后写 DB） | 云端成功后写 DB，会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 未下载封面 | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 标签同步按钮/worker | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 分类 other 回填 | 会向 ExHentai 拉取数据 |
| 会向 ExHentai 拉取数据 | 画质回填 | 会向 ExHentai 拉取数据 |
| 访问 GitHub（非 EH） | EhTag 词库更新 | 访问 GitHub Release API，不访问 ExHentai |
| 只在本地 | 图库列表搜索 | 不访问网站 |
| 只在本地 | 阅读器 | 不访问网站 |
| 只在本地 | 缩略图 | 不访问网站 |
| 只在本地 | 进度/历史 | 不访问网站 |
| 只在本地 | 本地评分私有标签 | 不访问网站 |
| 只在本地 | 导出 CBZ | 不访问网站 |
| 只在本地 | 删除回收站 | 不访问网站 |
| 只在本地 | 扫盘 | 不访问网站 |
| 只在本地 | 版本更新页（本地对比） | 本地对比，不访问网站 |
| 只在本地 | 查重 | 不访问网站 |
| 只在本地 | 书单 | 不访问网站 |
| 只在本地 | 中文标签联想 | 不访问网站 |
| 只在本地 | 日志 | 不访问网站 |
| 只在本地 | 磁盘 | 不访问网站 |
| 只在本地 | OPDS | 不访问网站 |
| 先本地，必要时上网 | 下载入队缺元数据才 gdata | 缺元数据才打远端 gdata |
| 先本地，必要时上网 | 详情页打开只读 DB | 只读本地 DB |
| 先本地，必要时上网 | 封面/分类计数/配额先缓存 | 优先读本地缓存 |
