# galleryvault 页面清单

> 回答“有哪些页面/屏、从哪进、数据从哪来”。路由权威源是 `frontend/src/router/routes.ts`；导航权威源是 `frontend/src/components/shell/navigation.ts`。视觉与 Token 见 [design-system.md](design-system.md)。

## 页面与屏清单

导航共 15 个目的地（`navigation.ts` 的 `navDestinations`），加登录/欢迎/详情/阅读器等子页。路径为 hash 路由（旧锚点别名保留）。

| 页面 | 入口 `#/` | 数据源（API） | 状态 |
|---|---|---|---|
| 登录 | `/login` | `POST /login` | 已实现 |
| 浏览（首页） | `/browse` | `GET /api/galleries` + 阅读进度 | 已实现 |
| 在线（发现） | `/online`（别名 `/discover`） | `GET /api/eh/search`、`/api/eh/status` | 已实现 |
| 本机库 | `/library` | `GET /api/galleries` | 已实现 |
| 画廊详情 | `/gallery/:id` | `GET /api/galleries/{id}` | 已实现 |
| 阅读器 | `/reader/:id/:page` | `GET /api/galleries/{id}/pages/{n}` | 已实现 |
| 在线阅读器 | `/online/g/:gid/:token/read/:page` | `GET /api/eh/galleries/...` | 已实现 |
| 系列 | `/series` | `GET /api/series` | 已实现 |
| 标签 | `/tags` | `GET /api/tags/search` | 已实现 |
| 历史 | `/history` | `GET /api/history` | 已实现 |
| 收藏 | `/favorites` | `GET /api/favorites/categories`、`/check-status` | 已实现 |
| 下载 | `/downloads` | `GET /api/downloads` | 已实现 |
| 更新 | `/updates`（子页 `/updates/ignored`） | `GET /api/updates` | 已实现 |
| 查重 | `/duplicates`（子页 `/duplicates/cross-gid`、`/duplicates/favorites`） | `GET /api/scan/duplicates` 等 | 已实现 |
| 回收站 | `/recycle` | `GET /api/galleries/trash`、`/expunged` | 已实现 |
| 完整性 | `/integrity` | `GET /api/galleries/integrity` | 已实现 |
| 归档 | `/archive` | `GET /api/archive`、`/api/system/storage` | 已实现 |
| 日志 | `/logs` | `GET /api/logs`、`/api/system/logs` | 已实现 |
| 设置 | `/settings/:group?` | `GET /api/settings` | 已实现 |
| 欢迎（首登向导） | `/welcome` | `GET /api/onboarding/status` | 已实现 |
| 样张（设计调试） | `/_kit` | 静态（懒加载，不进导航） | 已实现 |

## 共用组件与导航

| 组件/区域 | 作用 | 出现位置 |
|---|---|---|
| 顶栏 | 菜单、品牌、页标题、通知、全局控制、主题/语言/退出 | 全部（reader 等沉浸页除外） |
| 抽屉/侧轨/底栏 | 三处渲染同一导航表（`navGroups`/`navFixed`/`bottomDestinations`） | 全部非沉浸页 |
| 维护导航 Tab | 回收站/重复副本/收藏夹重复/跨 GID 重复/缺页体检/归档 六页切换（`MaintenanceNav`/`MaintenanceTabs`） | 维护类页 |
| 视图切换 | grid/list/table 三态，按页记忆（`useViewMode`） | 浏览类列表页 |

## 每页要素

- 指标、操作、空态、错误态：各页在 `frontend/src/locales/{zh,en}/<feature>.json` 里定义文案；空态组件 `EmptyState`、错误态 `ErrorState` 统一。
- 测试钩子：稳定 `data-testid`（`gallery-card`、`gv-page-header`、`gv-toolbar` 等），mock/real E2E 共用。

## 设计系统

- Token、色彩/对比度、密度、状态语义统一写在 [design-system.md](design-system.md) 与 `frontend/docs/design/DESIGN.md`。

## 无障碍

- 键盘可达/焦点可见/非文本对比度：以 `frontend/scripts/check-design.mjs` 的 glyph/原生控件扫描 + E2E 审计为准；未逐页核对的写“未核对”。
