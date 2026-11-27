# GalleryVault 踩坑记录

> 从维护记录（本地 `HANDOFF.md`，gitignore）与 git 历史整理的真实坑；每条带现象→根因→处置。写作时间只到 2026-11-21，之后按“追加当天一条”维护。

## 数据库 / 认证

- **测试容器 DB 认证失败（asyncpg 0.32）**：`tests/conftest.py` 全局把 `hashlib.pbkdf2_hmac` 改成 1 次迭代提速，而 asyncpg 0.32 用同函数做 SCRAM 导致 DB 认证失败。处置：只对 `galleryvault/auth.py` 的调用提速（HANDOFF 2026-10-27）。
- **postgres 数据目录 uid**：测试 compose 的 `test-data/db-data` 属 postgres（uid 999），不可 chown（AGENTS.md）。
- **会话密钥持久化**：`auth_secret` 持久化到 DB 才能重启保持登录；改密码撤销全部会话（`config.py` + wiki [静态加密](../wiki/Encryption.md)）。

## 下载 / 入库

- **下载完成≠入库成功**：落盘到入库之间任务显示「入库中」，只有入库成功才标记成功（`docs/wiki/Features.md` §4）。入库失败重试只重新入库、不重下、不扣 GP。
- **`[DL版] 4869` 类标题去噪后 core 为空**：跨 GID 查重对带数字后缀的标题可能抽不出核心标题（HANDOFF 2026-11-11）。
- **换 GID 漏检**：定时收藏检查用「云端数量==本地已知数量」整体跳过，云端把旧 gid 换成新 gid（总数不变）时漏检。处置：跳过需同时满足数量相等 + 第一页 gid 全部已知 + 距上次完整检查 <15 天（`FAVORITES_FULL_CHECK_MAX_AGE_DAYS`，HANDOFF 2026-10-29）。

## 前端

- **网格 tag 浮层 chip 被挤成圆点**：`TagList` 单行 nowrap + chip 可收缩，浮层 `max=6` 时文字被压到 ~1px。处置：`TagList` 加 `layout="wrap"`（HANDOFF 2026-11-14）。
- **语言/主题用 localStorage 键**：`gv_lang`/`gv_theme`/`gv_page_size`，与旧前端同键，便于升级/回滚保留偏好（`stores/settings.ts:32-35`）。
- **i18n 带点键名**：vue-i18n 把 `.` 当路径分隔符，48 个带点 legacy 键映射为下划线（`frontend/README.md`「i18n」）。

## 发布 / CI

- **往 main 推 docs 改动必须带 `[skip ci]`**：否则 `pages.yml`/`sync-wiki` 会用旧内容覆盖 wiki（任务书关键约束）。
- **测试栈用 `docker compose`（v2）**：宿主 2026-11-12 起装 v2 插件，旧 v1 `docker-compose` 与系统 requests 2.34 不兼容，禁用（AGENTS.md）。
- **生产 compose 跟 `:dev` + watchtower**：推 `dev` 可能被自动拉取并在启动时迁移；发布前先做生产 DB 备份（HANDOFF 2026-11-15）。
- **登录限流**：管理员账号指数退避（5 次起最长 15 分钟）+ 每 IP 10 次/分；真实 E2E 每测重登录会触发 nginx 503，用 global-setup 一次登录 + storageState 复用（`frontend/playwright.real.config.ts:13-15`）。

## 扫描 / 归档

- **扫描根离线不得整库 expunge**：扫描根离线/不可读/本次未扫到候选时跳过「扫描失踪」标记，否则会把整库误移回收站（`docs/wiki/Library.md`「扫描库」）。
- **删除/清理的路径边界**：删除文件与清理副本时绝对路径必须落在扫描根或归档根（`archive_roots`/`archive_root`/`cold_storage_root`）内，用 `Path.resolve()` 校验，防路径遍历；目标就是扫描根本身时拒绝（`docs/wiki/Manage.md`）。
- **冷归档删源需冷包覆盖源**：冷端生成完好 CBZ 且冷包页数覆盖源后才删热目录，否则拒删记日志（HANDOFF 2026-11-15）。
