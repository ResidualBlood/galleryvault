---
task: fe-native-dialog
date: 2026-11-27
kind: refactor
source: 用户“按 modern-web-guidance 审查结果修前端，你自己决定”
tickets: []
commits: []
decisions: []
docs:
  - docs/devlog/2026/11-27-fe-native-dialog.md
verified:
  - npm --prefix frontend run typecheck :: 0
  - npm --prefix frontend run lint :: 0
  - npm --prefix frontend run test:unit :: 0（414 passed / 52 files）
  - node frontend/scripts/check-design.mjs :: 0
  - node frontend/scripts/check-parity.mjs --strict :: 0
  - npm --prefix frontend run e2e:mock :: 0（258 passed）
unverified:
  - e2e:real 未跑（需要测试栈/生产数据，按任务单交给主控）
  - Firefox/WebKit 未跑；E2E 只覆盖 chromium mock
---

# fe-native-dialog 自绘模态迁到原生 `<dialog>`

## 改了什么

- `components/ui/Dialog.vue`、`components/ui/Sheet.vue`、`components/shell/NavSheet.vue`、`views/reader/ReaderSettingsSheet.vue` 与 `components/actions/FavPicker.vue` 的桌面分支由 Teleport + `div role="dialog"` 改为原生 `<dialog>`：`open` 变 true 后 `showModal()`，关闭时 `close()`。
- 删除手写 `role="dialog"`、`aria-modal`、document 级 Esc 监听、`previousFocus` 手动归还与 scrim 点击层；焦点约束、背景 inert、单层 Esc 与焦点归还交给浏览器。
- `cancel` 事件统一 `preventDefault()` 后 `emit('close')`（父组件持有 `open`）；`dismissible=false` 时只阻止默认关闭。
- 点外关闭改成指针坐标判断：`pointerdown` 与 `pointerup` 都落在面板外才关闭，避免框选拖拽误关。
- 标题用 `useId()` 生成 id：Dialog/Sheet/ReaderSettingsSheet 用 `aria-labelledby` 指向可见标题，NavSheet/FavPicker 保留 `aria-label`。
- 滚动按指南处理：`dialog:modal { overscroll-behavior: contain }`、`::backdrop { overflow: hidden; overscroll-behavior: contain }`；删除 NavSheet 的 `html/body { overflow: hidden }` 锁滚动。
- 开合过渡改为 `display`/`overlay` + `transition-behavior: allow-discrete`，面板位移动效与 token 不变，`prefers-reduced-motion` 降到 1ms。
- 离场过渡期间旧 `<dialog>` 仍在 DOM：关闭时给它 `aria-hidden="true"` 并在 `.dialog-leave-active`/`.sheet-leave-active` 上禁用指针，避免无障碍树里同时存在两个 dialog（E2E `getByRole("dialog")` strict 会命中两个）。
- 新增 `src/test-setup.ts` 的 jsdom 最小 polyfill（`showModal`/`show`/`close`/`requestClose`），组件内不写测试分支；`vitest.config.ts` 挂 `setupFiles`。
- 新增 `components/ui/__tests__/Dialog.test.ts`、`Sheet.test.ts`：showModal 调用、取消→close、`dismissible=false`、点外关闭、`aria-labelledby`。
- E2E 适配：`c3fix` 的 `toHaveAttribute("role", "dialog")` 改为 `toHaveRole("dialog")`（原生隐式角色）；`real/shell` 的 `.fav-picker__scrim` 点击改为 Esc。

## 为什么

审查 P1 的核心是自绘模态没有焦点约束、背景不 inert、每实例一个 Esc 监听导致叠层一次全关、背景仍可滚动。原生 `dialog.showModal()` 直接提供这些能力，且无需焦点 trap/`inert` 依赖库。

### Teleport 到 body 的浮层在模态内会被 inert：排查结论

- 模态打开后 body 子树 inert，且普通定位元素永远在 top layer 之下。`TagMenu`、`Toast` 都 `Teleport to="body"`。
- 组件内嵌套：`GalleryActions` 的 `action-sheet` 里会再开 `FavPicker` 的 `fav-sheet`。Dialog/Sheet 现在打开时先查 `[data-gv-modal]`，把 `<Teleport>` 目标切到最上层已开模态，因此嵌套 Sheet/Dialog 落在模态子树内，不再被 inert，Esc 也由原生 top-layer 栈只关最上层。
- `Popover`/`Menu` 不 Teleport，位于模态子树内，不受影响。
- `TagMenu` 会被 `GalleryCard` 的 `card-tag-sheet`（TagList 的 `@menu`）在 Sheet 内触发，仍 Teleport 到 body：迁移后它在模态内会被 inert 且压在 backdrop 下。该组件属于 `fe-menu-a11y` 范围，本任务不动；后续应让它把 Teleport 目标指向最近的 `[data-gv-modal]`（与 Dialog/Sheet 相同的查找）。
- `Toast` 同理，由 `fe-toast-a11y` 处理。

## 验证

- `npm --prefix frontend run typecheck` → 0
- `npm --prefix frontend run lint` → 0
- `npm --prefix frontend run test:unit` → 0（新增 9 个用例通过）
- `node frontend/scripts/check-design.mjs` → 0
- `node frontend/scripts/check-parity.mjs --strict` → 0
- `npm --prefix frontend run e2e:mock` → 0（258 passed，chromium mock 全量）
- `grep -nE 'role="dialog"|aria-modal'` 五个组件 → 无匹配

## 缺口与后续

- `TagMenu` 在 Sheet 内仍会 inert/被遮挡，见上；需 `fe-menu-a11y` 或后续批次处理。
- `Toast` 在模态打开时的可见性由 `fe-toast-a11y` 处理。
- jsdom 的 dialog polyfill 只覆盖测试所需的 open/close 语义，不模拟真实焦点移动、inert 与 top layer；这些由 E2E 覆盖。
- FavPicker 桌面分支从锚定下拉变为居中模态，尺寸/圆角/阴影 token 不变；如产品要求仍贴按钮，需要另做 anchor 定位。
