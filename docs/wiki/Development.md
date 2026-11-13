# 前端开发与构建

> 中文 · [English](Development-EN)

前端架构、开发 / 构建 / 测试命令、设计规范入口，以及在线阅读与伴侣脚本的实现要点。

## 架构

前端是 **Vue 3 + Vite + TypeScript** 单页应用，构建为 `dist/` 后由 nginx 托管；nginx 同时把 `/api`、`/login`、`/logout` 反向代理到后端（默认 `http://backend:8001`）。后端仍是纯 JSON API，不输出 HTML。

- **路由**：hash 模式，兼容旧书签（如 `#/gallery/12`）。在线浏览新增 `#/online`、`#/online/g/:gid/:token`、`#/online/g/:gid/:token/read/:page`；旧 `#/discover` 作为别名保留。
- **状态**：Pinia（`auth`、`settings`、`ui`、`downloads`、`favorites` 等）。
- **国际化**：vue-i18n，消息在构建期预编译，不使用运行时编译器，也没有 `eval` / `new Function`。
- **样式**：不引入 UI 组件库；`src/styles/tokens.css` 是颜色、字号、圆角、间距的唯一来源，组件位于 `src/components/ui/`。
- **请求**：`src/api/client.ts` 是唯一入口，统一 `credentials: "include"`、CSRF 双提交头、30 秒超时与 401 处理；端点只在 `src/api/<domain>.ts` 声明。
- **Service Worker**：构建期注入（injectManifest），负责页面壳与静态资源的更新提示；不缓存 `/api/` 响应与画廊图片。

## 目录

切换后前端位于仓库根的 `frontend/`：

```
frontend/
  src/
    api/                 # HTTP client 与按域拆分的端点声明
    components/          # AppShell、ui/ 基础组件、actions/ 操作行
    composables/         # useViewRequest、usePolling
    i18n/ locales/       # 预编译消息（zh/ 与 en/ 键集必须一致）
    pwa/                 # Service Worker 注册与更新提示
    reader/              # PageSource：local / online-direct / online-proxy
    router/              # 路由表与导航守卫
    stores/              # Pinia
    styles/tokens.css    # 设计 token
    views/               # 各业务页面
  docs/design/           # DESIGN.md、REFERENCES.md、tokens.required.json、specimen.html
  e2e/                   # Playwright 用例与 mock 后端
  parity/                # 旧路由 / 端点快照与豁免
  scripts/               # check-design / check-dist / check-parity
  userscript/            # 伴侣用户脚本源码、构建与单测
  public/                # 图标、manifest、伴侣脚本产物
  nginx.conf Dockerfile
```

## 开发与构建

```bash
cd frontend
npm ci
npm run dev          # 开发服务器；/api、/login、/logout 代理到 $GV_BACKEND（默认 http://127.0.0.1:8201）
npm run build        # 产出 dist/，base 为 '/'
npm run preview      # 预览构建产物
```

`npm run build` 之后可直接把 `dist/` 交给任意静态服务器验证；正式部署由镜像内的 nginx 托管 `dist/`。

Monorepo 根目录的本地开发编排：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

- 前端以后端热重载方式运行 Vite 开发服务器，改源码即时生效；
- 后端使用 `uvicorn --reload`，并带代理头参数以取得真实客户端 IP；
- 开发数据库隔离在 `./db-data-dev`，宿主 `./library`、`./downloads`、`./cache` 映射到容器。

## 测试

```bash
cd frontend
npm run typecheck     # vue-tsc --noEmit
npm run lint          # ESLint（含「裸 /api/ 字面量」守卫）
npm run test:unit     # Vitest：i18n 键集、API client、路由对齐、阅读器分页等
npm run e2e:mock      # Playwright + mock 后端（不访问真实服务）
npm run e2e:real      # Playwright 打真实测试环境（GV_E2E_BASE）
```

- `e2e:mock` 的端口按 worktree 路径哈希到 4200–4999，可用 `GV_E2E_PORT` 覆盖，避免并行工作树抢端口；截图目录由 `GV_SHOTS` 指定。
- `e2e:real` 只由测试环境负责人执行，登录口令经 `GV_E2E_PASSWORD` 传入，不写进源码、日志、提交或截图。
- CI 目前只跑后端测试与构建，前端 E2E 由发布前的测试环境统一执行。
- 伴侣脚本：

  ```bash
  node userscript/build.mjs            # 生成 public/galleryvault-companion.user.js
  node userscript/build.mjs --check    # 校验产物未漂移
  npm run test:unit -- userscript      # 只跑脚本单测
  npm run e2e:mock -- --grep @userscript
  ```

## 设计规范入口

| 内容 | 位置 |
| :--- | :--- |
| 设计规范正文 | `frontend/docs/design/DESIGN.md` |
| 参考对象与具体方面 | `frontend/docs/design/REFERENCES.md` |
| token 必备清单 | `frontend/docs/design/tokens.required.json` |
| 第三方图标与许可证声明 | `frontend/THIRD_PARTY_NOTICES.md` |
| 静态样张 | `frontend/docs/design/specimen.html` |
| token 定义 | `frontend/src/styles/tokens.css` |
| 自动检查 | `node scripts/check-design.mjs`（`--tokens-only` 只校验 token 与对比度） |

规范基于 Material Design 3 的 token 结构（不引入其组件库），品牌色沿用暖金，分类色与收藏夹 0–9 色固定。后续每个 UI 批次都必须：只用 `--gv-*` token、通过 `check-design.mjs`、提交亮 / 暗 × 桌面 1280 / 手机 390 四张截图（存树外），并在验收中对照规范章节。参考对象只借布局与交互模式，不复制代码、图标、截图。

## 在线取图的实现要点

在线阅读不在服务端转发图片字节（默认路径）：后端按页解析出有时效的 H@H 地址，浏览器直接取图；只有用户按设备切到代理模式时才走服务端代理。

- 解析复用全局 EH 页面并发（6）；在线并发默认 3（`online_reader_concurrency`）同时约束解析与代理；阅读器最多预载 2 页。
- 解析结果服务端缓存 10 分钟（H@H 签名 15 分钟），过期或加载失败重新解析；失败自动换节点重试 2 次，仍失败则提示改用代理或在官方页打开。
- 图片额度耗尽（509 / 429）停止预载并展示配额，不循环重试。
- CSP 的 `img-src` 放开 `ehgt.org`、`*.hath.network:*` 与 EH 站点，`connect-src` 仍为 `'self'`；`scripts/check-dist.mjs` 会拒绝外部脚本、`eval` 与外部请求目标。
- 用户侧说明见 [在线阅读](Online-Reading)。

## API token 与伴侣脚本

- 设置页「账户与安全」提供生成 / 撤销 API token；明文只返回一次，数据库只存哈希。撤销后使用该 token 的脚本立即失效。
- Bearer 只允许访问白名单端点：会话状态、`GET /api/eh/status`、收藏夹分类、添加 / 移除收藏、创建 / 查询下载任务；其余接口返回 `403`。带会话 Cookie 的请求仍走 CSRF 校验，Bearer 与 Cookie 混用不豁免。
- 脚本只在官方画廊页注入面板，不读取 EH Cookie；地址与 token 通过脚本管理器存储。安装与隐私说明见 [在线阅读 → 伴侣脚本](Online-Reading#伴侣脚本可选增强零服务端额度)。

## 图标、基础组件与设计参考

- **图标来源**：全站图标统一写 `<Icon name="语义名" />`，语义名到 Material Symbols Rounded 路径的映射集中在 `frontend/src/components/icons/registry.ts`。图标经 `unplugin-icons` + `@iconify-json/material-symbols` 在**构建期**编译成内联 SVG Vue 组件：不引入图标字体、不在运行时请求、不给 `<svg>` 注入样式；未使用的图标不会进包。页面不得直接 import `~icons/`，也不得再用 Unicode 字符或 emoji 充当图标（`check-design` 强制）。尺寸取 16 / 18 / 20 / 24 四档 token，控件内默认 20（32 档用 18），导航 24。
- **许可证**：Material Symbols 与 Iconify 图标数据为 **Apache-2.0**，`unplugin-icons` 为 **MIT**；两个 npm 包只进 `devDependencies`。完整声明（来源、用途、许可证）见 `frontend/THIRD_PARTY_NOTICES.md`，选型与用法约束见 `frontend/docs/design/DESIGN.md` C16。
- **基础组件与尺寸档位**：Button / IconButton / TextField / Select / Switch / Checkbox / Field / TextArea / Slider / SegmentedControl / Chip / Toolbar / PageHeader / Pager / FilterButton / SelectionBar / EmptyState / ErrorState / TagChip / TagList / TagMenu / GalleryCollection / GalleryCard / GalleryListRow / GalleryTable / ViewModeToggle。控件高度只取 `--gv-size-control-lg/md/sm` 三档（40 / 36 / 32，触屏各 +4），同一工具栏只用一个档位并垂直居中；图标与文字间距 8，组内间距 8、组间 16。组件规范见 `DESIGN.md` C12、C17–C19，浏览器级样张在 `#/_kit`（不进导航）。
- **视图与 tag 约定的代码入口**：
  - `frontend/src/composables/useViewMode.ts`：页内网格 / 列表 / 表格切换，偏好按页面键写入 `localStorage.gv_view_mode`；<600px 不提供表格，已存的表格偏好只临时回退、不覆盖原值。
  - `frontend/src/components/tags/tag-utils.ts`：语言选择（zh 用 `display`、其余用 `name`）、行内排序与 `language` 跳过、`libraryTagQuery`（`tags=ns:name&tag_mode=and`，幂等追加 / 排除）与 `formatEhTagQuery`（`ns:"name$"`，幂等）。
  - `frontend/src/components/tags/useTagNavigation.ts`、`TagChip.vue`、`TagList.vue`、`TagMenu.vue`：点击跳转、Shift / Ctrl 排除、长按 / 右键复制原文。
  - `frontend/src/components/gallery/GalleryCollection.vue`：三种视图共用同一份条目数据与选择状态。
- **设计参考**：参考对象、参考方面、链接与许可证统一登记在 `frontend/docs/design/REFERENCES.md`。打磨阶段新增 **EhViewer_CN_SXJ**（GPL-3.0，本地源码 `d129f20`）作为浏览页视图切换、行内 tag、点击搜索语法、筛选角标与跳页的交互参考；只借鉴行为与交互，不复制其源码、布局 XML、资源或字符串。三视图与按页面记忆是本仓扩展——对方只有全局的列表 / 网格设置，改完需重建列表。

## 部署与安全

- 构建产物由 nginx 托管，CSP `script-src 'self'`；不允许内联脚本、外部 CDN 与 `eval`。
- 前端只消费 `/api` 等相对路径；开发时由 Vite 代理，生产时由 nginx 反向代理。
- 提交前在 `frontend/` 下运行 `npm run lint`、`npm run test:unit` 与 `node scripts/check-parity.mjs --strict`（旧路由 / 端点覆盖）。
