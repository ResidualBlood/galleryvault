---
task: fe-favpicker-heading
date: 2026-11-27
kind: fix
source: 复审 review-fe-native-dialog 第 2 轮必修（窄屏收藏选择器可见 h2 标题语义丢失）
tickets: []
commits:
  - c288c95
decisions:
  - 标题由 FavPickerPanel 渲染为 <h2 :id="headingId">，FavPicker 用 useId() 生成 id 并以 aria-labelledby 命名 dialog、去掉 aria-label
  - 面板 heading 布尔 prop 改为必填 headingId 字符串，消除 Vue Boolean 缺省 false 导致的“标题存在与否随调用方”歧义
  - 窄屏补 aria-hidden 装饰把手，复用 Sheet.vue 的尺寸/圆角/outline 视觉
docs:
  - docs/devlog/2026/11-27-fe-favpicker-heading.md
verified:
  - npm --prefix frontend run typecheck :: 0
  - npm --prefix frontend run lint :: 0
  - npm --prefix frontend run test:unit :: 0
  - node frontend/scripts/check-design.mjs :: 0
  - node frontend/scripts/check-parity.mjs --strict :: 0
  - npm --prefix frontend run e2e:mock -- e2e/dialog-review-fixes.spec.ts e2e/actions.spec.ts e2e/fav-dl.spec.ts e2e/polish-favorites.spec.ts :: 0
unverified:
  - Firefox/WebKit 与 iOS Safari 未跑（沿用 chromium mock）
---

# fe-favpicker-heading：恢复收藏选择器的可见 h2 标题

## 改了什么

- `components/actions/FavPicker.vue`
  - `useId()` 生成 `titleId`，`<dialog>` 用 `:aria-labelledby="titleId"`，删除 `:aria-label`；不再需要 `useI18n`。
  - 传 `:heading-id="titleId"` 给面板；窄屏（`compact`）渲染 `div.fav-picker__handle[aria-hidden=true]` 装饰把手。
- `components/actions/FavPickerPanel.vue`
  - `heading?: boolean` → 必填 `headingId: string`；标题由 `<p class="fav-panel__title">` 改为 `<h2 :id="headingId" class="fav-panel__title">`，样式 token 不变（`--gv-type-title-small`）。
  - 修复复审指出的 `props.heading ?? true` 失效：Vue 对省略的 Boolean prop 传 `false`，旧代码在唯一调用方（FavPicker 未传 `heading`）下根本不渲染标题。
- 单测 `src/components/actions/__tests__/fav-picker.test.ts`：桌面与窄屏各一条，断言可见 `h2.fav-panel__title`、`aria-labelledby` 指向该 h2、无 `aria-label`、窄屏有 `aria-hidden` 把手。
- `e2e/dialog-review-fixes.spec.ts` 新增窄屏回归：390px 打开 `fav-sheet`，`getByRole('heading', { level: 2 })` 可见且文本为“选择收藏夹”，`aria-labelledby` 指向它，`toHaveAccessibleName("选择收藏夹")`，把手数量 1，Esc 关闭。

## 为什么

原 Sheet 分支把标题交给 `Sheet.vue` 的 `<h2>` 渲染；迁移到单一 dialog 后标题落在面板内，既是 `<p>` 又因 Boolean prop 缺省为 false 而不渲染，导致窄屏出现“无可见标题、无 heading 语义”的回归（第 2 轮复审：`title: undefined, handle: false`）。现在标题总是渲染、且是 dialog 名称来源，两个断点结构一致；把手只是把旧 Sheet 的视觉提示按 `aria-hidden` 补回，不引入拖拽交互。

## 验证

- `npm --prefix frontend run typecheck` → 0
- `npm --prefix frontend run lint` → 0
- `npm --prefix frontend run test:unit` → 0
- `node frontend/scripts/check-design.mjs` → 0
- `node frontend/scripts/check-parity.mjs --strict` → 0
- `npm --prefix frontend run e2e:mock -- e2e/dialog-review-fixes.spec.ts e2e/actions.spec.ts e2e/fav-dl.spec.ts e2e/polish-favorites.spec.ts` → 0

## 缺口与后续

- 仅 Chromium mock；移动端真机与其它内核未验证。
- 把手无拖拽关闭手势，与旧 Sheet 行为一致。
