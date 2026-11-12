# GalleryVault 前端设计规范

- 版本：1.0（Batch 1，2026-11-12）
- 适用：`frontend/` 全部 UI（在线浏览、本机库、详情、阅读器、收藏/下载、设置、管理页）
- Token 单一来源：`frontend/src/styles/tokens.css`
- 必备清单：`frontend/docs/design/tokens.required.json`
- 静态样张：`frontend/docs/design/specimen.html`
- 检查脚本：`frontend/scripts/check-design.mjs`
- 参考清单：`frontend/docs/design/REFERENCES.md`
- 取证报告：`/tmp/opencode/gv-frontend-rewrite/inv-design-refs.md`（链接均经实际打开核实）

本规范只借参考对象的布局与交互模式，**不复制第三方代码、图标、截图**；Kavita 为 GPL-3.0，只取设计模式。EhViewer 因仓库 HTTP 451 无法核实，不作为参考对象。

---

## 0. 后续 UI 任务如何遵守

每个 UI 批次必须同时满足：

1. 只使用 `--gv-*` token；`src/**/*.{vue,css,ts}` 内不得出现裸色值、`font-size` 字面量、非 token 圆角。
2. 运行 `node frontend/scripts/check-design.mjs`，退出码 0。
3. 亮 / 暗 × 桌面 1280 / 手机 390 四张截图，截图放在树外；验收回执列出对照的 `DESIGN.md` 章节。
4. 组件结构、尺寸、状态按第 4 节执行；偏离须在回执中说明理由与替代方案。
5. 设计走查报告由 reviewer 依据截图与本文件产出，存树外。

常用命令：

```bash
cd frontend
node scripts/check-design.mjs --tokens-only   # token 完整性 + 对比度
node scripts/check-design.mjs                 # 额外扫描 src/
```

截图基线（宿主 Playwright）：

```bash
mkdir -p /tmp/opencode/gv-frontend-rewrite/shots/<batch>
for s in dark light; do
  for v in 1280,900 390,844; do
    playwright screenshot -b chromium --full-page --viewport-size "$v" \
      --color-scheme "$s" "file://$PWD/frontend/docs/design/specimen.html" \
      "/tmp/opencode/gv-frontend-rewrite/shots/<batch>/specimen-$s-${v%%,*}.png"
  done
done
```

---

## 1. 设计原则

1. **内容优先，界面退后。** 封面、标题、页码是主角；工具栏、角标、容器只用必要的层级与描边，不做装饰性渐变（品牌光晕只允许出现在页面背景与详情封面后方）。
2. **一套 token，两种主题。** 所有颜色、字号、间距、圆角、海拔、动效必须来自 `tokens.css`；禁止页面局部自定义色板。亮暗主题只改颜色角色，不改结构。
3. **语义色即信息。** EH 分类色、收藏槽位色是用户迁移认知的一部分，保持固定语义色；状态（成功 / 警告 / 错误）用 M3 对应角色，不用分类色代替。
4. **4px 网格与固定标题高度。** 间距只用 4 的倍数；卡片标题固定两行高度，避免网格参差（Kavita 的 `min-height` 做法）。
5. **桌面密度、移动可达。** 桌面用常驻抽屉 + 内容网格；移动底部导航 + 单列。点击目标不小于 44×44（`--gv-size-touch`）。
6. **可访问性是硬门槛。** 正文对比度 ≥ 4.5:1；焦点环始终可见；状态不只靠颜色表达（图标 / 文案 / 形状至少再加一种）。
7. **阅读器克制。** 阅读区纯黑底，控件半透明容器色；默认隐藏上下栏，点按中区呼出，3 秒无操作自动隐藏（拖动滑条时暂停）。

---

## 2. Token 体系

命名：

```
--gv-color-<role>          颜色角色（M3 color roles，亮/暗各一套）
--gv-type-<role>-size     字号
--gv-type-<role>-line     行高
--gv-type-<role>-weight   字重
--gv-type-<role>-tracking 字距
--gv-type-<role>          font 简写
--gv-space-<n|语义>       间距（4px 网格）
--gv-radius-<scale>       圆角
--gv-elev-<level>         海拔阴影
--gv-state-<state>        状态层不透明度 / 焦点环
--gv-motion-<name>        时长与缓动
--gv-bp-<class>           断点
--gv-size-<name>          固定尺寸
--gv-cat-<category>       EH 分类色（固定，不随主题）
--gv-favcat-<0..9>        EH 收藏槽位色（固定，不随主题）
```

主题解析顺序：无 `data-theme` 时默认暗色，`prefers-color-scheme: light` 自动切亮色；`data-theme="dark|light"` 始终覆盖系统偏好。亮色角色块在 `[data-theme="light"]` 与 `prefers-color-scheme: light` 各有一份，必须保持同步，检查脚本会校验两份一致。

### 2.1 颜色角色

| Role | 暗色 | 亮色 | 用途 |
| --- | --- | --- | --- |
| primary | `#d8a55b` | `#b0792c` | 品牌主色：主按钮填充、滑条、进度、选中态 |
| primary-text | `#e8c07c` | `#96601a` | surface 上的主色文字/图标/链接（浅色底 ≥4.5:1） |
| on-primary | `#241703` | `#1a1204` | primary 上的文字/图标 |
| primary-container | `#4a3418` | `#f3ddb9` | 选中项容器、品牌光晕、轻量强调底 |
| on-primary-container | `#f6ddb8` | `#3a2508` | 上述容器上的文字 |
| secondary | `#c9c2b3` | `#6b6355` | 次级操作、中性强调 |
| on-secondary | `#2c2a22` | `#ffffff` | secondary 上的文字 |
| secondary-container | `#3a3a30` | `#e7dfd1` | 导航选中态、tonal 按钮、下载分组底 |
| on-secondary-container | `#e9e2d4` | `#2c2a22` | 上述容器上的文字 |
| tertiary | `#9fc9c2` | `#3f6f68` | 下载/语言等第三语义角标 |
| on-tertiary | `#0f2a26` | `#ffffff` | tertiary 上的文字 |
| tertiary-container | `#23413c` | `#bfe9e2` | 第三语义容器 |
| on-tertiary-container | `#c2e8e1` | `#0f2a26` | 上述容器上的文字 |
| error | `#ffb4ab` | `#ba1a1a` | 错误图标/文字、失败状态 |
| on-error | `#690005` | `#ffffff` | error 上的文字 |
| error-container | `#93000a` | `#ffdad6` | 错误提示块底色（不大面积使用） |
| on-error-container | `#ffdad6` | `#410002` | 上述容器上的文字 |
| success | `#8fd6b7` | `#2f6f52` | 成功、已完成 |
| on-success | `#023824` | `#ffffff` | success 上的文字 |
| success-container | `#1e4b3a` | `#b9f0d8` | 成功提示块 |
| on-success-container | `#b9f0d8` | `#003824` | 上述容器上的文字 |
| warning | `#ffb95e` | `#7a5200` | 警告、评分星 |
| on-warning | `#3d2600` | `#ffffff` | warning 上的文字 |
| warning-container | `#5b3d00` | `#ffddb0` | 警告提示块 |
| on-warning-container | `#ffddb0` | `#3d2600` | 上述容器上的文字 |
| surface | `#0c0e0f` | `#f4f1ea` | 页面底 |
| on-surface | `#f1eee7` | `#1c1a17` | 页面正文 |
| surface-variant | `#2f3537` | `#e3ddd2` | 次级填充、标签底 |
| on-surface-variant | `#aeb6b2` | `#55504a` | 次级文字、图标 |
| surface-dim | `#08090a` | `#e3ded4` | 下沉区域 |
| surface-bright | `#2a2e30` | `#fffdf8` | 提亮区域 |
| surface-container-lowest | `#070809` | `#fffdf8` | 输入框、最下沉卡片 |
| surface-container-low | `#121517` | `#faf7f1` | 低层容器 |
| surface-container | `#171a1c` | `#fffdf8` | 默认卡片/面板 |
| surface-container-high | `#202426` | `#efeae2` | 菜单、悬浮面板、阅读器工具栏 |
| surface-container-highest | `#2a2f31` | `#e7e1d7` | 对话框、最前景 |
| outline | `#6b7478` | `#8a8177` | 输入框/控件描边、可交互边界 |
| outline-variant | `#303638` | `#d9d2c8` | 分隔线、弱边界 |
| inverse-surface | `#f1eee7` | `#302e2a` | Toast / Snackbar 底 |
| inverse-on-surface | `#1c1a17` | `#f4f1ea` | 上述反色底上的文字 |
| inverse-primary | `#7c5a1f` | `#e5c07b` | 反色底上的主色 |
| scrim | `#000000` | `#000000` | 遮罩（配合透明度） |
| shadow | `#000000` | `#000000` | 阴影基色 |
| focus-ring | `#d8a55b` | `#b0792c` | 焦点环（等于 primary） |
| background | `#0c0e0f` | `#f4f1ea` | 兼容别名，等于 surface |
| on-background | `#f1eee7` | `#1c1a17` | 兼容别名，等于 on-surface |
| reader-surface | `#000000` | `#000000` | 阅读区底 |
| reader-on-surface | `#f5f2ea` | `#f5f2ea` | 阅读区前景/页码 |

规则：

- `surface`（页面）→ `surface-container`（卡片）→ `surface-container-high`（菜单/工具栏）→ `surface-container-highest`（对话框）。不要跳级使用。
- 正文用 `on-surface`；说明/元信息用 `on-surface-variant`；分隔线用 `outline-variant`；控件边界用 `outline`。
- 错误只用 `error` / `on-error` / `error-container`，不用分类红或品牌色代替。
- 亮色 `primary` 上的文字必须是 `on-primary`（深色），不要用白字（对比度不足）。
- `primary` 只用于填充与非文字元素；surface 上的文字、图标、链接一律用 `primary-text`（亮色 `#b0792c` 对浅底仅 3.3:1，不可直接当正文色）。

### 2.2 字阶

字体族：`--gv-type-family-brand`（display / headline / title-large）与 `--gv-type-family-plain`（其余）。不打包 Web 字体，使用系统字体栈。

| Token | 字号 | 行高 | 字重 | 字距 |
| --- | --- | --- | --- | --- |
| display-large | 57px | 64px | 400 | -0.25px |
| display-medium | 45px | 52px | 400 | 0 |
| display-small | 36px | 44px | 400 | 0 |
| headline-large | 32px | 40px | 400 | 0 |
| headline-medium | 28px | 36px | 400 | 0 |
| headline-small | 24px | 32px | 400 | 0 |
| title-large | 22px | 28px | 400 | 0 |
| title-medium | 16px | 24px | 500 | 0.15px |
| title-small | 14px | 20px | 500 | 0.1px |
| body-large | 16px | 24px | 400 | 0.5px |
| body-medium | 14px | 20px | 400 | 0.25px |
| body-small | 12px | 16px | 400 | 0.4px |
| label-large | 14px | 20px | 500 | 0.1px |
| label-medium | 12px | 16px | 500 | 0.5px |
| label-small | 11px | 16px | 500 | 0.5px |

用法：页面标题 `headline-small`/`headline-medium`；卡片标题 `title-small`（网格）/ `title-medium`（在线列表）；正文 `body-large`；元信息 `body-small`；按钮/导航 `label-large`；角标/chip `label-small`。`title-*` 与 `label-*` 的字重来自 token，不要在组件里另写 `font-weight`。

### 2.3 间距

4px 网格：`--gv-space-0..8` = 0 / 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64。
语义别名：`xs=4`、`sm=8`、`md=12`、`lg=16`、`xl=24`、`2xl=32`、`3xl=48`。

- 组件内：4 / 8 / 12；卡片内边距 8–12；区块间距 24–32；页面外边距 16（手机）/ 24（桌面）。
- 行高与间距分离：不要用 padding 模拟行高。

### 2.4 圆角

`none 0` / `xs 4` / `sm 8` / `md 12` / `lg 16` / `xl 28` / `full 9999`。

- 卡片 `md`；大面板/详情头 `lg`；对话框/底部 Sheet `xl`；chip/输入框 `xs`；按钮/开关/头像 `full`。
- 旧 `6px` 圆角没有 M3 对应值，统一并入 `sm 8`；chip 用 `xs 4`。

### 2.5 海拔

| Token | 近似 dp | 用途 |
| --- | --- | --- |
| elev-0 | 0 | 页面背景、平铺内容 |
| elev-1 | 1 | 卡片、搜索栏 |
| elev-2 | 3 | 卡片悬停、FAB |
| elev-3 | 6 | 菜单 / Popover / 阅读器工具栏 |
| elev-4 | 8 | 抽屉、模态侧板 |
| elev-5 | 12 | 对话框、最前景浮层 |

阴影只用于表达层级；卡片默认 `elev-1`，hover 升到 `elev-2`，不要同时加粗描边。

### 2.6 状态层

统一采用 material-web token 数值（与 Compose 常见 0.10 的差异已在取证报告 §7.5 记录；本仓固定这一套）：

| 状态 | Token | 值 | 做法 |
| --- | --- | --- | --- |
| hover | `--gv-state-hover` | 0.08 | `on-surface`/`on-*` 以 8% 叠在组件底色上 |
| focus | `--gv-state-focus` | 0.12 | 叠加 + 2px focus ring（offset 2px） |
| pressed | `--gv-state-pressed` | 0.12 | 叠加，不改变组件底色 |
| dragged | `--gv-state-dragged` | 0.16 | 拖拽/滑动中的元素 |
| disabled | `--gv-state-disabled` | 0.38 | 文字/图标 |
| disabled-container | `--gv-state-disabled-container` | 0.12 | 禁用容器底 |

实现可用 `::before` 绝对定位叠加 `currentColor`（或对应 `on-*`）并设置 `opacity`；不要用 `filter: brightness()`，以免改变品牌色。

### 2.7 动效

| Token | 值 | 用途 |
| --- | --- | --- |
| duration-short | 120ms | hover、按下、颜色过渡 |
| duration-medium | 200ms | 抽屉、菜单、阅读器上下栏 |
| duration-long | 300ms | 页面级转场、Sheet |
| ease-standard | `cubic-bezier(0.2, 0, 0, 1)` | 默认 |
| ease-emphasized | `cubic-bezier(0.05, 0.7, 0.1, 1)` | 进入/强调 |
| ease-decelerate | `cubic-bezier(0, 0, 0, 1)` | 元素进入 |
| ease-accelerate | `cubic-bezier(0.3, 0, 1, 1)` | 元素退出 |

尊重 `prefers-reduced-motion: reduce`：去掉位移/缩放，仅保留 ≤120ms 的透明度变化。

### 2.8 断点与导航

| 宽度 | Token | 导航 |
| --- | --- | --- |
| < 600px | `--gv-bp-compact` | 底部 Navigation bar（80px） |
| 600–839px | `--gv-bp-medium` | Navigation rail（80px 宽） |
| 840–1199px | `--gv-bp-expanded` | 可折叠 drawer（264px） |
| 1200–1599px | `--gv-bp-large` | 常驻 drawer + 内容区 |
| ≥ 1600px | — | 常驻 drawer + 更宽内容（`--gv-size-content-max` 1440） |

CSS 媒体查询不能引用自定义属性，组件内可写 `@media (min-width: 840px)` 等字面断点；数值必须与上表一致，并在同一组件的注释中写明对应 token。

抽屉内容（Komga 结构）：品牌 → 主区（本机库 / 在线 / 收藏 / 下载）→ 固定项（设置 / 管理）→ “更多”折叠。选中态用 `secondary-container` 底 + `on-secondary-container` 文字，不加左侧竖条（本仓 Web 形态统一）。

### 2.9 EH 分类色与收藏槽位色

分类色固定，不随主题变化；底色 + 对应 `*-ink` 文字（已校验 ≥4.5:1）。注意：JHenTai 统一用白字，但黄/绿/青分类白字不达标，本仓改为深色 ink。

| 分类 | Token | 色值 | ink |
| --- | --- | --- | --- |
| Doujinshi | `--gv-cat-doujinshi` | `#FC4E4E` | 黑 |
| Manga | `--gv-cat-manga` | `#FCB417` | 黑 |
| Artist CG | `--gv-cat-artistcg` | `#DDE500` | 黑 |
| Game CG | `--gv-cat-gamecg` | `#05BF0B` | 黑 |
| Western | `--gv-cat-western` | `#14E723` | 黑 |
| Non-H | `--gv-cat-nonh` | `#68C9DE` | 黑 |
| Image Set | `--gv-cat-imageset` | `#5050D7` | 白 |
| Cosplay | `--gv-cat-cosplay` | `#9755F5` | 黑 |
| Asian Porn | `--gv-cat-asianporn` | `#FE93FF` | 黑 |
| Misc | `--gv-cat-misc` | `#9E9E9E` | 黑 |
| Private | `--gv-cat-private` | `#000000` | 白 |
| other | `--gv-cat-other` | `#FFFFFF` | 黑 |

收藏槽位 0–9（`--gv-favcat-0` … `--gv-favcat-9`）：

| 槽位 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 色值 | `#9E9E9E` | `#FC4E4E` | `#FCB417` | `#DDE500` | `#17B91B` | `#36B940` | `#68C9DE` | `#5050D7` | `#9755F5` | `#FE93FF` |

收藏心形颜色 = 画廊所在槽位色，不统一用红色，也不要用 `primary`（避免与交互色混淆）。部分槽位色在亮色底上对比度低（如黄、青），**FavHeart 必须带 `outline` 描边或 `surface` 光晕**，保证形状可辨。

### 2.10 固定尺寸

| Token | 值 | 用途 |
| --- | --- | --- |
| `--gv-size-topbar` | 56px | 顶栏 |
| `--gv-size-navbar` | 80px | 底部导航 |
| `--gv-size-rail-width` | 80px | Navigation rail |
| `--gv-size-drawer-width` | 264px | 抽屉 |
| `--gv-size-content-max` | 1440px | 内容最大宽度 |
| `--gv-size-icon-sm/md/lg` | 16 / 20 / 24px | 图标 |
| `--gv-size-touch` | 44px | 最小点击目标 |
| `--gv-size-reader-bar` | 56px | 阅读器上下栏 |
| `--gv-size-card-cover-aspect` | `3 / 4` | 封面比例 |

---

## 3. 旧变量 → 新 token 对照

旧文件 `frontend/assets/styles.css:1-59` 的变量只用于迁移参考，新工程不得继续使用旧名。

| 旧变量 | 旧值（暗/亮） | 新 token | 说明 |
| --- | --- | --- | --- |
| `--bg` | `#0c0e0f` / `#f4f1ea` | `--gv-color-surface`（兼容 `--gv-color-background`） | 页面底 |
| `--bg-glow` | `#29271f` / `#e8dcc8` | `--gv-color-primary-container` | 仅用于 `radial-gradient` 背景光晕，不新增独立 token |
| `--topbar-bg` | `#0d0f10ef` / `#f4f1eaef` | `color-mix(in srgb, var(--gv-color-surface-container) 94%, transparent)` | 顶栏 + `backdrop-filter: blur(8px)` |
| `--panel` | `#171a1c` / `#fffdf8` | `--gv-color-surface-container` | 卡片/面板 |
| `--panel-2` | `#202426` / `#efeae2` | `--gv-color-surface-container-high` | 悬浮面板 |
| `--ink` | `#f1eee7` / `#1c1a17` | `--gv-color-on-surface` | 正文 |
| `--muted` | `#929a97` / `#6b6560` | `--gv-color-on-surface-variant` | 次级文字 |
| `--line` | `#303638` / `#d9d2c8` | `--gv-color-outline-variant` | 分隔线 |
| `--accent` | `#d8a55b` / `#b0792c` | `--gv-color-primary`（填充）/ `--gv-color-primary-text`（文字） | 品牌主色 |
| `--danger` | `#ed8b83` / `#c4564e` | `--gv-color-error` | 错误 |
| `--ok` | `#7fc8a9` / `#3d8f6e` | `--gv-color-success` | 成功 |
| `--warning` | `#ff9800` / `#c07812` | `--gv-color-warning` | 警告/评分 |
| `--color-bg` | 别名 | `--gv-color-background` | 兼容别名保留 |
| `--color-panel` | 别名 | `--gv-color-surface-container` | — |
| `--color-ink` | 别名 | `--gv-color-on-surface` | — |
| `--color-muted` | 别名 | `--gv-color-on-surface-variant` | — |
| `--color-line` | 别名 | `--gv-color-outline-variant` | — |
| `--color-accent` | 别名 | `--gv-color-primary` | — |
| `--color-danger` | 别名 | `--gv-color-error` | — |
| `--color-ok` | 别名 | `--gv-color-success` | — |
| `--space-xs` | 4px | `--gv-space-xs` | 数值不变 |
| `--space-sm` | 8px | `--gv-space-sm` | 数值不变 |
| `--space-md` | 12px | `--gv-space-md` | 数值不变 |
| `--space-lg` | 16px | `--gv-space-lg` | 数值不变 |
| `--space-xl` | 24px | `--gv-space-xl` | 数值不变 |
| `--radius-sm` | 4px | `--gv-radius-xs` | 改名对齐 M3 梯度 |
| `--radius-md` | 6px | `--gv-radius-sm` | 6px 无 M3 对应，并入 8px |
| `--radius-lg` | 8px | `--gv-radius-sm` | 与旧 md 合并 |
| `--font-size-xs` | 0.72rem | `--gv-type-label-small-size` | 11px；接近旧 11.5px |
| `--font-size-sm` | 0.82rem | `--gv-type-body-medium-size` / `--gv-type-label-large-size` | 14px |
| `--font-size-md` | 1rem | `--gv-type-body-large-size` / `--gv-type-title-medium-size` | 16px |
| `--font-size-lg` | 1.1rem | `--gv-type-title-medium-size` | 17.6px 无对应，收敛到 16px |
| `--font-size-xl` | 1.5rem | `--gv-type-headline-small-size` | 24px |
| `--font-size-2xl` | 2rem | `--gv-type-headline-large-size` | 32px |
| `--transition-fast` | 120ms | `--gv-motion-duration-short` | 数值不变 |
| `--transition-base` | 180ms | `--gv-motion-duration-medium` | 统一为 200ms |
| `--focus-ring` | `0 0 0 2px var(--accent)` | `outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring); outline-offset: var(--gv-state-focus-ring-offset)` | 用 outline 不占布局 |

旧 `body` 的 `font-size: 15px; line-height: 1.5` 统一改为 `body-large`（16/24），字族改为 `--gv-type-family-plain`；页面背景光晕改为：

```css
background:
  radial-gradient(circle at 15% 0, var(--gv-color-primary-container) 0, transparent 34%),
  var(--gv-color-background);
```

---

## 4. 核心组件规范

每个组件给出结构、尺寸、token、状态与参考来源。未列出的组合视为新组件，须先补本节再实现。

### C01 AppShell / 导航

**结构**：顶栏（左侧菜单按钮 + 页面标题 + 右侧操作）→ 按断点切换的导航（底部 bar / rail / 可折叠 drawer / 常驻 drawer）→ 内容区。抽屉分组：品牌 → 主区（本机库、在线、收藏、下载）→ 固定项（设置、管理）→ “更多”折叠。

**尺寸**：顶栏 56px；底部 bar 80px；rail 80px；drawer 264px；内容最大 1440px；页面边距 16px（<600）/ 24px（≥600）。

**Token**：`--gv-color-surface`、`--gv-color-surface-container`、`--gv-color-secondary-container`、`--gv-color-on-secondary-container`、`--gv-color-on-surface-variant`、`--gv-color-outline-variant`、`--gv-size-*`、`--gv-elev-0`/`--gv-elev-4`、`--gv-motion-duration-medium`。

**状态**：选中 = `secondary-container` 底 + `on-secondary-container` 文字/图标；hover 叠 8%；focus 叠 12% + 焦点环；drawer 展开/收起 200ms `ease-standard`；移动端 bar 始终可见，不随滚动隐藏。

参考：Mihon（断点与导航结构）+ Komga（抽屉分组）https://developer.android.com/develop/ui/compose/layouts/adaptive/window-size-classes ；https://github.com/gotson/komga/blob/master/komga-webui/src/views/HomeView.vue#L21-L140

### C02 GalleryCard（网格变体，本机库）

**结构**：封面（3:4）叠层 → 标题（固定两行）→ 元信息（作者 · 大小）→ 可选 4px 进度条。角标约定：左上状态（未读圆点/已读）、右上格式（CBZ/PDF/文件夹/数量）、左下评分或语言、右下操作菜单。悬停时封面中央出现“阅读”按钮。

**尺寸**：网格最小列宽 152px；封面 `aspect-ratio: var(--gv-size-card-cover-aspect)`；卡片圆角 `--gv-radius-md`；标题 `title-small` + 2 行 clamp，`min-height: calc(var(--gv-type-title-small-line) * 2)`；进度条仅“未读完”显示，高度 4px，圆角 full。

**Token**：`--gv-color-surface-container`、`--gv-color-surface-container-high`、`--gv-color-on-surface`、`--gv-color-on-surface-variant`、`--gv-color-primary`（进度）、`--gv-color-outline-variant`、`--gv-elev-1`、`--gv-radius-md`、`--gv-type-title-small`、`--gv-type-body-small`。

**状态**：默认 `elev-1` + 1px `outline-variant`；hover `elev-2` + 8% 状态层；选中（批量）2px `primary` 外框；缺失封面用 `surface-container-highest` 占位 + `on-surface-variant` 图标；禁用/被屏蔽整卡 38% 透明并覆盖说明。

参考：Kavita（未读点/进度条/固定标题高度）+ Komga（四角浮层位）https://github.com/Kareadita/Kavita/blob/develop/UI/Web/src/app/cards/entity-card/entity-card.component.html ；https://github.com/gotson/komga/blob/master/komga-webui/src/components/ItemCard.vue#L4-L111

### C03 GalleryCard（在线列表变体）

**结构**：左封面（3:4，104px 宽）→ 右信息列：标题（2 行）+ 上传者 → 可选标签（3 列瀑布/横向滚动）→ 底行：分类 chip、收藏心形、语言、页数、半星评分、上传时间。阅读进度百分比在未读完时放底行左侧。

**尺寸**：行内边距 12px、列间距 12px、封面 104px（宽屏可 112px）；标题 `title-medium` + 2 行 clamp；上传者 `body-small`；底行 `label-large`；分类 chip 高 20px；行圆角 `md`。

**Token**：`--gv-color-surface-container`、`--gv-color-on-surface`、`--gv-color-on-surface-variant`、`--gv-color-outline-variant`、`--gv-cat-*` / `*-ink`、`--gv-favcat-*`、`--gv-color-warning`（评分）、`--gv-elev-1`、`--gv-type-title-medium`、`--gv-type-body-small`、`--gv-type-label-large`、`--gv-type-label-small`。

**状态**：hover 底色 `surface-container-high` + 8%；已读标题降为 `on-surface-variant`；下载中显示 `primary` 细进度；被本地规则屏蔽整卡模糊并覆盖“已屏蔽”；收藏按下时心形缩放 0.92（120ms）。

参考：JHenTai（列表卡信息层级与分类/收藏色语义）https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_list_card_.dart#L130-L223

### C04 BadgeStrip

**结构**：横向 flex 角标组，分 `start`（左侧，语言/下载）与 `end`（右侧，未读/数量）。每个 badge 是单行文本或数字，圆角 `xs`，高 20px，内边距 0 8px。

**尺寸**：高 20px；间距 4px；`label-small`；数字 badge 最小宽 20px 居中。

**Token**：中性 `--gv-color-secondary-container` / `--gv-color-on-secondary-container`；主状态 `--gv-color-primary` / `--gv-color-on-primary`；下载 `--gv-color-tertiary` / `--gv-color-on-tertiary`；错误 `--gv-color-error` / `--gv-color-on-error`；遮罩底可用 `color-mix(in srgb, var(--gv-color-surface) 78%, transparent)`。

**状态**：不交互，无 hover；同组最多 3 个，超出合并为“+N”；文字超长省略，不换行。

参考：Mihon（color role 区分角标语义）+ Kavita（数量/来源角标）https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/library/components/LibraryBadges.kt#L14-L42

### C05 CategoryChip

**结构**：单行 chip，`分类名` 文本；底色 = 对应 `--gv-cat-*`，文字 = `--gv-cat-*-ink`。列表内高 20px，详情/筛选可高 24px。

**尺寸**：高 20 / 24px；内边距 0 8px；圆角 `xs`；`label-small`；不可点击时保持纯展示。

**Token**：`--gv-cat-doujinshi` … `--gv-cat-other` 及对应 `-ink`；禁用态 `--gv-color-outline` 20% 底 + `--gv-color-on-surface-variant` 20% 文字。

**状态**：可筛选时 hover 叠 8% `on-*`；selected 外圈 2px `--gv-color-primary` + 内缩 1px；未知分类回退 `--gv-cat-misc`。

参考：JHenTai（分类常量与纯色底 chip）https://github.com/jiangtian616/JHenTai/blob/master/lib/src/config/ui_config.dart#L47-L59 ；https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_category_tag.dart#L38-L42

### C06 FavHeart

**结构**：心形图标按钮。未收藏 = 描边心形（`on-surface-variant`）；已收藏 = 实心心形，颜色 = 当前收藏槽位 `--gv-favcat-N`；外层 1px `outline` 描边或 2px `surface` 光晕，避免浅色槽位在亮色底上消失。点击循环槽位或打开槽位菜单（按产品行为），长按/右键打开槽位选择。

**尺寸**：视觉图标 20–24px；点击区 44×44（列表内可 40×40，但不得小于 40）；圆角 full。

**Token**：`--gv-favcat-0..9`、`--gv-color-on-surface-variant`、`--gv-color-outline`、`--gv-color-surface`、`--gv-state-hover`/`focus`/`pressed`。

**状态**：未收藏 hover 显示 `on-surface-variant`；已收藏 hover 叠 8% `on-surface`；按下缩放 0.92 + 12%；请求中显示 16px 环形进度，不改变心形颜色；失败回滚并用 `error` 短提示。

参考：JHenTai（收藏心形颜色 = 槽位色）https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_list_card_.dart#L280 ；https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_favorite_tag.dart#L20-L26

### C07 TagChip / TagGroups

**结构**：按 namespace 分组：组标题 `namespace`（`label-large`，`primary`）→ `Wrap` 标签 chip。chip 内容 `namespace:tag`，namespace 加粗，tag 常规；整 chip 可点击进入搜索。

**尺寸**：chip 高 24px，内边距 0 8px，圆角 `xs`，间距 4px；组间距 12px；组标题下间距 4px。

**Token**：`--gv-color-surface-variant` 底、`--gv-color-on-surface-variant` 文字、`--gv-color-on-surface` 加粗 namespace、`--gv-color-primary-text` 组标题；hover 底 `--gv-color-surface-container-highest`；selected `--gv-color-secondary-container` / `--gv-color-on-secondary-container`。

**状态**：暗色主题不复用 JHenTai 浅色 pastel 底（会刺眼且对比不足），统一用 `surface-variant`；若需 namespace 色相，用 `color-mix(in srgb, var(--gv-cat-<x>) 12%, var(--gv-color-surface-variant))` 且文字仍用 `on-surface-variant`。

参考：LANraragi（namespace:tag 搜索与分组）+ JHenTai（namespace 分组 chip）https://sugoi.gitbook.io/lanraragi/v/dev/basic-operations/searching ；https://github.com/jiangtian616/JHenTai/blob/master/lib/src/config/ui_config.dart#L66-L82

### C08 GalleryDetailLayout

**结构**（自上而下）：副标题（可选）→ 封面 + 信息（标题、上传者、数据行）→ 操作行 → namespace 标签 → 缩略图 → 评论（推迟）。宽屏（≥840）封面 176px + 信息双列；窄屏单列，封面最大 180px。

**尺寸**：封面 176px（宽屏）/ 120–180px（窄屏），3:4；详情头内边距 16px，圆角 `lg`；信息行 `body-medium`，值用 `on-surface`，键用 `on-surface-variant`；操作按钮高 40px；缩略图网格最小 96px。

**Token**：`--gv-color-surface-container`、`--gv-color-on-surface`、`--gv-color-on-surface-variant`、`--gv-color-outline-variant`、`--gv-color-primary`（主操作）、`--gv-elev-1`、`--gv-radius-lg`、`--gv-type-headline-small`、`--gv-type-body-medium`、`--gv-type-label-large`。

**状态**：加载时封面 + 信息行用 Skeleton；主操作禁用时 38%/12%；错误用 `ErrorState`；收藏/下载状态与列表卡一致；封面加载失败用 `surface-container-highest` 占位。

参考：JHenTai（详情页顺序与信息排布）+ Mihon（操作按钮语义）https://github.com/jiangtian616/JHenTai/blob/master/lib/src/pages/details/details_page.dart#L210-L233 ；https://github.com/jiangtian616/JHenTai/blob/master/lib/src/pages/details/details_page.dart#L483-L560

### C09 阅读器（上下栏 / 点按分区 / 滑条）

**结构**：全屏 `Stack`：页面内容 → 右下页码浮层 → 顶部栏 → 底部栏。顶部栏 = 返回 + 标题/章节 + 书签 + 在 EH 打开；底部栏 = 首页按钮 + 页码滑条 + 末页按钮 + 设置。中间区域按宽度三等分：左 1/3 上一页、中 1/3 呼出/隐藏上下栏、右 1/3 下一页。连续滚动模式改为上/下 1/4 翻页、中间呼出。

**尺寸**：上下栏各 56px（`--gv-size-reader-bar`）；滑条轨道 6px，thumb 16px；页码浮层 `body-small` 粗体 + 1px 深色描边；底部栏左右内边距 12px；缩略图条（可选）高 88px。

**Token**：`--gv-color-reader-surface`、`--gv-color-reader-on-surface`、`--gv-color-surface-container-high`（工具栏）、`--gv-color-primary`（滑条/当前页）、`--gv-elev-3`、`--gv-motion-duration-medium`、`--gv-type-label-large`、`--gv-type-body-small`。

**状态**：上下栏默认隐藏（移动端），点按中区 200ms 滑入 + 150ms 淡入；无操作 3s 自动隐藏，拖动滑条时暂停计时；键盘 ←/→/PageUp/PageDown/Home/End；滑条可键盘操作（焦点环）；图片加载失败显示重试按钮，切页回来重新加载；页码浮层在菜单打开时淡出。

参考：Mihon（上下栏/点按分区/页码浮层）+ Kavita（首页·滑条·末页与适配档位）https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/reader/appbars/ReaderAppBars.kt ；https://github.com/Kareadita/Kavita/blob/develop/UI/Web/src/app/manga-reader/_models/reader-enums.ts ；https://komga.org/docs/guides/webreader-divina

### C10 设置页布局

**结构**：≥840px 双栏：左侧分组列表（264px），右侧当前分组内容；<840px 单栏：分组列表 → 子页。顶部搜索（可搜索全部设置，Mihon 模式）。分组：外观 / 本机库 / 在线阅读 / 阅读器 / 下载 / 网络 / 安全 / 高级 / 关于。每行：左侧标题 + 说明，右侧控件（开关 / 当前值 + 箭头 / 输入）。服务器级设置底部固定“保存 / 重置”条。

**尺寸**：组标题 `label-large` + `primary`，上间距 16px；行最小高 56px，内边距 16px；行间 1px `outline-variant`；说明 `body-small`；右侧值 `body-medium`；保存条高 64px。

**Token**：`--gv-color-surface`、`--gv-color-surface-container`、`--gv-color-surface-container-low`（双栏左栏）、`--gv-color-primary-text`、`--gv-color-on-surface`、`--gv-color-on-surface-variant`、`--gv-color-outline-variant`、`--gv-space-*`、`--gv-type-label-large`、`--gv-type-body-large`、`--gv-type-body-small`。

**状态**：开关切换 120ms；保存中按钮禁用 + 进度；dirty 时显示未保存提示；保存失败用 `error` 行内提示，不弹大面积红；搜索无结果用 `EmptyState` 紧凑版。

参考：Mihon（分组子页 / 顶部搜索 / twoPane）+ Komga（左说明右控件 / 底部保存条）https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/more/settings/screen/SettingsMainScreen.kt#L76-L160 ；https://komga.org/docs/guides/server-settings

### C11 Dialog / Sheet / Popover / Toast

**结构**：

- Dialog：`scrim` 遮罩 + 居中容器；标题 `headline-small`、正文 `body-medium`、底部按钮右对齐（次要在前、主要在后）。
- Sheet：移动端从底部滑入，顶部圆角 `xl` + 32×4 拖拽条；桌面端可变为右侧面板。
- Popover：锚点定位，`surface-container-high` 容器，8px 内边距，菜单项高 40px。
- Toast：底部居中（桌面右下），`inverse-surface` 底 + `inverse-on-surface` 文字，可带一个文字按钮。

**尺寸**：Dialog 宽 `min(560px, calc(100vw - 32px))`，内边距 24px，圆角 `xl`，`elev-5`；Sheet 最大高 90vh；Popover 圆角 `sm`，`elev-3`；Toast 最小高 48px，圆角 `xs`，边距 16px，显示 4s。

**Token**：`--gv-color-surface-container-highest`（Dialog）、`--gv-color-surface-container-high`（Popover/Sheet）、`--gv-color-inverse-surface` / `--gv-color-inverse-on-surface`（Toast）、`--gv-color-scrim`、`--gv-elev-3/5`、`--gv-radius-xl/sm/xs`、`--gv-motion-duration-medium/long`。

**状态**：打开 200ms 淡入 + 上移 8px（Sheet 从底部滑入）；关闭 150ms 淡出；焦点锁定在容器内，Esc 关闭；遮罩点击关闭（Dialog 可配置）；Toast 不抢焦点，超时或点击关闭。

参考：Material 3（对话框/面板/菜单的层级与状态层）https://m3.material.io/components/navigation-drawer/overview ；https://m3.material.io/styles/elevation/overview

### C12 Button / IconButton / Input / Select / Switch

**结构**：

- Button：`filled`（primary 填充）/ `tonal`（secondary-container）/ `outlined`（outline 描边 + primary-text 文字）/ `text`（primary-text，无底）；可带 18px 前置图标。
- IconButton：44×44 点击区，40×40 视觉圆/方底；图标 20–24px。
- Input：标签（外置或浮动）+ 输入区 + 辅助/错误文字；可选前置图标与清除按钮。
- Select：与 Input 同构，右侧 chevron；展开用 Popover。
- Switch：52×32 轨道 + 24px thumb。

**尺寸**：Button 高 40px（紧凑 32px），左右内边距 16/24px，圆角 full，`label-large`；Input 高 48px（舒适 56px），圆角 `xs`，内边距 12px；Switch 轨道 52×32，thumb 24px，内边距 4px。

**Token**：`--gv-color-primary`、`--gv-color-primary-text`、`--gv-color-on-primary`、`--gv-color-secondary-container`、`--gv-color-on-secondary-container`、`--gv-color-outline`、`--gv-color-outline-variant`、`--gv-color-surface-container-lowest`、`--gv-color-error`、`--gv-radius-full/xs`、`--gv-state-*`、`--gv-size-touch`、`--gv-type-label-large`、`--gv-type-body-large`。

**状态**：hover 8% / focus 12% + ring / pressed 12%；禁用文字 38%、容器 12%；Input focus 边框 2px `primary`，error 边框 `error` + 辅助文字 `error`；Switch 开启轨道 `primary` + thumb `on-primary`，关闭轨道 `surface-variant` + thumb `outline`；所有控件保留键盘可达与 `aria-*`。

参考：Material 3（按钮/输入/开关的角色与状态层）+ Mihon（设置项控件写法）https://m3.material.io/styles/color/roles ；https://m3.material.io/foundations/interaction/states/state-layers

### C13 DownloadItem

**结构**：列表/网格项：缩略图（可选，56×74）→ 标题 + 状态文案 → 进度条 → 操作（暂停/继续/取消/重试）。分组头显示目标库/来源，底色 `secondary-container` 60%。

**尺寸**：行高 ≥72px，内边距 12px；缩略图 56×74；进度条 4px；操作按钮 32–40px；标题 `title-small`；状态 `body-small`。

**Token**：`--gv-color-primary`（进度/进行中）、`--gv-color-surface-container`（默认）、`--gv-color-surface-container-highest`（暂停）、`--gv-color-error`（失败）、`--gv-color-secondary-container`（分组头）、`--gv-color-on-surface-variant`、`--gv-radius-sm`、`--gv-motion-duration-short`。

**状态**：排队 = `on-surface-variant` + 无进度；下载中 = `primary` 进度 + 百分比；暂停 = `surface-container-highest` 底 + “继续”；完成 = `success` 勾 + 打开按钮；失败 = `error` 文案 + 重试；取消需二次确认（Dialog）。

参考：JHenTai（下载页的进度色/暂停态/分组底色）https://github.com/jiangtian616/JHenTai/blob/master/screenshot/download.jpg

### C14 EmptyState / ErrorState

**结构**：居中：图标（48px，线性、单色）→ 标题（`title-medium`）→ 说明（`body-medium`，最多两行）→ 主按钮（可选）+ 次按钮（可选）。ErrorState 复用同结构，图标/标题用 `error`，容器仍用中性 surface；不要大面积铺 `error-container`。

**尺寸**：容器内边距 32px（移动）/ 48px（桌面）；图标 48px；标题与说明间距 4px；按钮上间距 16px；最大文本宽 480px。

**Token**：`--gv-color-on-surface`、`--gv-color-on-surface-variant`、`--gv-color-primary`、`--gv-color-error`、`--gv-color-surface-container-low`、`--gv-radius-lg`、`--gv-type-title-medium`、`--gv-type-body-medium`。

**状态**：加载失败提供“重试”；权限不足显示“去登录/授权”；空库提供“添加库”；离线提示不阻断已有内容；错误信息不得包含 cookie / token / 服务器内部路径。

参考：Komga（EmptyState 结构）+ Mihon（ReaderError 错误呈现）https://github.com/gotson/komga/blob/master/komga-webui/src/components/EmptyState.vue ；https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/reader/ReaderError.kt

### C15 Skeleton

**结构**：按最终布局占位：封面块 + 2 行标题 + 1 行元信息；列表项为左封面 + 右三行。占位块圆角与最终元素一致，不改变布局尺寸。

**尺寸**：与对应组件一致（网格卡封面 3:4、标题两行高度；在线列表封面 104×139）；文本行高 12px，圆角 full；间距使用组件原间距。

**Token**：`--gv-color-surface-variant` ↔ `--gv-color-surface-container-highest` 渐变；`--gv-radius-*`、`--gv-motion-duration-long`。

**状态**：1.2s 循环扫光；`prefers-reduced-motion: reduce` 时改为静态两层底色；加载超过 300ms 才显示（避免闪烁）；加载完成后淡出 120ms，不做位移。

参考：Material 3（骨架屏沿用 surface 层级与 color roles）https://m3.material.io/styles/color/roles ；https://m3.material.io/foundations/design-tokens/overview

---

## 5. 无障碍与质量门槛

- **对比度**：`tokens.required.json` 列出的 on-* / 容器、分类 ink 对比度均 ≥ 4.5:1，由 `--tokens-only` 每次校验；新增颜色角色必须同时加入清单与对比对。
- **焦点**：所有可交互元素使用 `:focus-visible` + `--gv-color-focus-ring`，焦点环不得被 `overflow: hidden` 裁掉。
- **点击目标**：≥ 44×44（`--gv-size-touch`）；列表内图标按钮可视觉 40px，但点击区仍补到 44px。
- **语义**：图标按钮必须有 `aria-label`；状态变化用 `aria-live`；Dialog/Sheet 焦点锁定与 Esc 关闭；Switch 用 `role="switch"` + `aria-checked`。
- **动效**：尊重 `prefers-reduced-motion`；阅读器翻页不做大幅位移。
- **主题**：两套主题都必须通过截图检查；不允许只在暗色下可用。
- **隐私**：截图、日志、错误提示不得包含密码、cookie、token、EH 账号信息。

---

## 6. 截图与评审基线

每个 UI 批次交付四张截图（树外）：

| 主题 | 视口 | 文件 |
| --- | --- | --- |
| dark | 1280×900 | `specimen-dark-1280.png` |
| dark | 390×844 | `specimen-dark-390.png` |
| light | 1280×900 | `specimen-light-1280.png` |
| light | 390×844 | `specimen-light-390.png` |

本规范的样张位于 `/tmp/opencode/gv-frontend-rewrite/shots/b1/`（不提交仓库）。评审对照点：

1. 颜色角色是否只从 `--gv-color-*` 取；分类/收藏色是否只从 `--gv-cat-*` / `--gv-favcat-*` 取。
2. 卡片标题是否固定两行、进度条是否只在未读完时出现。
3. 在线列表卡是否包含分类、收藏、语言、页数、评分、时间六类信息。
4. 阅读器上下栏高度、滑条、点按分区是否符合 C09。
5. 设置页是否左说明右控件、是否有组标题与搜索。
6. 亮/暗对比度与焦点环是否正常。

---

## 7. 变更流程

1. 新 token：先改 `tokens.css` 两套主题 → 更新 `tokens.required.json` → 跑 `--tokens-only` → 更新本文件 token 表。
2. 新组件：先补第 4 节（结构/尺寸/token/状态/参考）→ 再实现 → 跑默认检查与四张截图。
3. 参考对象变更：必须先在 `REFERENCES.md` 增加可核实链接与许可证，再改本文件；不得凭空发明 URL 或替换参考对象。
4. 与取证报告冲突：停下报告，不自行取舍。
