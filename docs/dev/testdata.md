# GalleryVault 测试数据规范

> 测试数据只放仓库 `backend/tests/` 下或测试栈 DB；生产数据、真实 Cookie、口令一律不进仓库。真实环境验证进测试容器（:8200/:8201）。

## 仓库内测试数据

| 位置 | 内容 | 用途 |
| :--- | :--- | :--- |
| `backend/tests/fixtures/eh_online/` | `gallery-detail.html`、`search-list-compact.html`（E-Hentai 页面 HTML 快照） | EH 解析器单测（不联网） |
| `backend/tests/contract/golden/` | `galleries_list.json`、`downloads_list.json`、`settings.json` 等 10 个响应快照 | 契约测试（`tests/contract/`）比对响应结构 |

## 测试栈数据（不进仓库）

- 测试 compose 挂载 `test-data/db-data`（PostgreSQL，uid 999，勿 chown）、`library`、`TEMP`、`test-data/downloads`、`test-data/cache` 等目录（见 skill `galleryvault-maintenance`）。
- 测试库含少量真实画廊（用于真实 E2E/截图），登录口令按名加载 `local-credentials/galleryvault-test.env`（禁止抄进仓库）。
- E-Hentai 表站测试账号：无里站权限（`igneous` 空），Cookie 只放本地 `TEMP/cookies.txt`；测发现页须 `exhentai_base_url=https://e-hentai.org`。禁止配进生产。

## 约定

- **不复制被测算法**：测试真实实现，按需 mock，不用复制被测算法来“证明”自己（AGENTS.md）。
- **凭据零落盘**：Playwright/测试里读口令只走 env 或 local-credentials 注入，不写进测试文件、报告、截图。
- **污染隔离**：测试栈与生产隔离；测完 `docker compose stop` 保留（不 down/rmi），下次有更新先 `docker cp` + `pip install -e ".[dev]"` 再 `start`。
- **新增 fixture**：EH HTML 快照要脱敏（去掉个人 Cookie/账号痕迹）再入库。
