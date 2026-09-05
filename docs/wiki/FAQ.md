# 常见问题

## 为什么有些标签没有翻译？

翻译来自 [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)（自动获取最新版）。数据库未收录的标签（多为冷门画师/原作名）会保持原文；多值标签（`A | B`）只显示翻译的部分，未翻译的别名自动隐藏。可在设置页「立即更新翻译」手动刷新。

## 移除某个库目录后，里面的画廊会消失吗？

扫描时只会把「仍在扫描根目录内、但本次扫描没见到」的画廊标记为 `expunged`（软删除）。仅从设置移除目录不影响已有画廊；目录加回后重新扫描会自动恢复显示。建议移除目录前先从「库根目录」中删除该路径，避免误标。

## 下载任务失败，日志报 `image download request failed`？

这是**网络瞬时故障**（ExHentai / H@H 节点或代理链路），不是应用 bug，可在下载页重试。诊断看后端日志（升级到修复版后每行带 `[error='...']`）：

```bash
docker logs galleryvault-backend --since 6h | grep -E "download task failed|page download failed"
```

- `[error='ReadTimeout']` → H@H 节点断流/太慢，换节点或换时段。
- `[error='ConnectTimeout']` / `[error='ConnectError']` / `[error='RemoteProtocolError']` → 代理链路不稳。若走 hy2（QUIC/UDP）等 UDP 代理，国际链路抖动容易断长流，建议换 TCP 系协议（VLESS+TCP / Reality / SS / Trojan），或把 `page_concurrency` 调低。
- `EhClientError: ExHentai request failed` → 页面/API 请求的瞬时网络错误，已自动退避 30s 重试，一般不用管。

## 下载没有并发/速度上不去？

- 设置里的 `download_concurrency` 控制同时下载的画廊数。
- 后端对 ExHentai 有**全局并发上限**（`exhentai_max_concurrency`，默认 6），防止触发反爬；ExHentai 限速（429/509）时会退避重试。

## 修改密码后所有设备都被登出？

是的，这是有意的安全设计：改密码会**撤销所有已登录会话**，每台设备需要重新登录。

## 登录提示密码错误 / 无法登录？

- 首次使用默认密码 `p1a2s3s4`，登录后请修改。
- 若曾在设置里关闭「需要登录」，认证被旁路（直接访问，无需密码）。

## 密钥丢了？

见 [静态加密 → 密钥丢失的恢复](Encryption#密钥丢失的恢复)。

## 如何换端口 / 绑定域名？

端口映射在 `docker-compose.yml` 中修改；反代配置与域名绑定见 [服务部署 → 安全加固](Deployment#安全加固)。

## 跨网段或反代访问时，提交操作报「Cross-origin request rejected」？

这是 CSRF 防护校验了客户端来源与服务端 Host；前置反代需正确透传 Host 头（如 `proxy_set_header Host $http_host;`），或配置 `TRUSTED_PROXIES` 白名单。配置细节见 [服务部署 → 安全加固](Deployment#安全加固)。

## 顶栏出现「Cookie 已失效」或「无里站权限」红条？

启动时探活，之后每 30 分钟；登录后也会立刻刷新一次。顶栏红条分两态：
- **Cookie 已失效**：会话过期，需点横幅进设置重新填 cookie 并「测试登录」；
- **无里站权限**：当前账号无 ExHentai 里站访问权限（里站返回空/空白 200 或 Sad Panda），需检查账号权限或配置正确的 `igneous`，也可切到 `e-hentai.org` 表站。

云端同步在 Cookie 失效或无里站权限期间会暂停。

## 库里删掉的画廊还能找回吗？

**不删盘** → 见 [画廊管理 → 回收站与画廊找回](Manage#回收站与画廊找回)「用户删除」可恢复。扫描时目录里找不到 → 「扫描失踪」。**彻底删除且勾选删盘**后不能从本页找回（扫描也不会重新入库）。

## 点了暂停，扫描和下载还在跑？

暂停后不再领取新页，已开始的当前页会下完；不再 claim；扫描返回 `paused`。Web 下载页按钮与 Telegram `/pause` `/resume` 是同一开关，网页暂停后 Bot 一致，重启后仍保持暂停。详见 [下载管理 → 全局暂停与任务恢复](Downloads#全局暂停与任务恢复)。

## 发现页和画廊库有什么区别？

发现页（`#/discover`）用于在线浏览 / 搜索 ExHentai 资源；画廊库（`#/library`）用于管理本地已入库的画廊。详见 [浏览与画廊库 → 发现](Library#发现discover)。

## 加到主屏幕会把画廊下到手机吗？

**不会**。PWA 只缓存界面壳；js/css 网络优先（离线才用缓存），不缓存画廊图和 `/api/`。

## 怎么用 OPDS？

第三方阅读器支持通过 HTTP Basic 认证接入 OPDS 目录（用户名固定为 `galleryvault`，密码为 Web 登录密码）。注意 Basic 认证仅适用于 `GET /api/opds` 目录接口；画廊 CBZ 导出与其余 `/api/*` 接口需常规会话 Cookie、不再免密且不接受 Basic 凭据。详细说明见 [系统设置 → OPDS 与 CBZ 导出](Settings#设置settings)。

## 扫描 7z 会把整个压缩包解到磁盘吗？

**不会**。只抽取图片后缀，其它文件留在包内。

## 下载页提示「图片配额将达上限」？

来自 ExHentai Image Limit（与 GP 一起约 30 分钟缓存）。用量超过约 80% 时顶栏告警，建议暂停，避免 509。

## 归档下载重试或断点续传会重复扣除 GP 吗？

**不会**。归档任务创建后，ExHentai 生成的专属下载 URL 会持久化在本地缓存（`.archive.json`）中。后续发生网络断流、暂停续传（HTTP Range）或失败重试时，系统均直接复用该 URL 续传，**绝不会重新打包或二次扣除 GP**。当画廊归档通道不可用或 GP 不足时，系统还会自动无缝降级为逐页 H@H 下载（不消耗 GP）。

## 增量已经下完新版，「更新画廊」里还在？

新 gid 已在本地库时，**立即检测**会直接删除旧版本地副本，条目随之消失，不必再点「更新选中」。若该行曾被**忽略**，不会自动删旧。收藏夹入队/下载入库也会挂上更新行并在成功后收尾。详见 [收藏夹与更新 → 更新画廊](Favorites#更新画廊updates)。

## 收藏夹不自动下载？

需同时满足：设置里 **download favorites** 总开关开启 + 收藏夹页对应文件夹已**启用**（新夹默认关，需勾选并保存）+ 模式为「增量下载」或「强制下载」。详见 [收藏夹与更新 → 收藏夹监控](Favorites#收藏夹favorites)。

## 收藏夹检查成功但没有封面 / 列表是空的？

- 后端必须配置 **ExHentai cookie**（设置 → ExHentai → 填 `ipb_member_id` / `ipb_pass_hash` / `igneous` 并「测试登录」）。cookie 会**加密存库**（`ENCRYPTION_KEY`），不要在 `docker-compose.yml` 里设 `EXHENTAI_COOKIES`。没有 cookie 时 `favorites.php` 会 302 到首页，检查形同空跑。
- 封面在**立即检查**时后台预热到磁盘（`/gv-cache/remote-covers/{gid}.img`）；进夹只读缓存（`<img>` 走 `/api/favorites/cover`），不再等外网。大夹封面会陆续出现。若仍缺图，可在总览点**下载缺失项目**补漏。

## 如何同时按多个标签搜索？

支持点击追加多标签（默认 AND 逻辑）、胶囊栏 AND / OR 切换以及 `-tag` 排除语法。详见 [浏览与画廊库 → 搜索与筛选](Library#画廊库library)。

## 阅读器翻页后返回，搜索标签还在吗？

还在。阅读器内翻页全程保留搜索上下文，返回画廊详情与画廊库时搜索关键词与标签筛选均保持。详见 [画廊详情与阅读 → 阅读器](Reading#阅读器readeridpage)。

## 怎么跳到 ExHentai 上的原画廊页？

画廊详情页「开始阅读」旁提供「打开原站」按钮（需画廊有 token 且浏览器已登录 EH）。详见 [画廊详情与阅读 → 打开原站](Reading#画廊详情galleryid)。

## 用外站（e-hentai.org）设置时，里站专属画廊会被误删吗？

不会。外站看不到的里站专属画廊会返回与「已删除」相同的 404，但不会当作删除处理：画廊会**暂停**标签同步、**分类保持不变**，在设置里切回 `exhentai.org` 后**自动恢复**同步（无需手动）。

## 里站 / 外站 Base URL 怎么设置？

设置 → ExHentai → Base URL 可在 `exhentai.org`（里站）、`e-hentai.org`（外站）或自定义代理域之间切换，保存立即生效。详见 [系统设置 → 设置选项](Settings#设置settings)。

## 标题显示设置对哪些页面生效？

控制画廊库、浏览、画廊详情与收藏夹中显示日文、英文或目录名，与下载目录命名规则相互独立。详见 [系统设置 → 设置选项](Settings#设置settings)。
