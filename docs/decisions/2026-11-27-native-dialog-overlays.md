---
status: accepted
date: 2026-11-27
decider: user
source: 用户「用 modern-web-guidance 审查下项目前端」→「你去做吧, 你自己决定」；主控按审查结论定方案
tickets: []
supersedes: []
superseded_by: null
---

# 前端模态改用原生 `<dialog>.showModal()`，浮层按“新近可用特性需特性检测”口径实现

## 背景

modern-web-guidance 审查发现 Dialog/Sheet/NavSheet/FavPicker/ReaderSettingsSheet 均为 Teleport 到 body 的自绘 `div role="dialog"`：焦点可逃逸、背景不 inert 且可滚动、每实例 document 级 Esc 导致叠层一次全关。Popover/TagMenu 标了 `role="menu"` 却无键盘契约；Toast 重复 live 语义且固定 TTL。

## 决定

1. 所有模态使用原生 `<dialog>` + `showModal()`：不再写 `role="dialog"`/`aria-modal`/手写焦点陷阱/document Esc；`cancel` 事件 `preventDefault` 后交给父组件控制 `open`；滚动用 `overscroll-behavior: contain`，禁止 `body { overflow: hidden }`。
2. 点外关闭只认“`event.target` 为 dialog 元素本身且指针在面板矩形外”，press 与 release 都在外才关。
3. 模态打开时，需要在其内弹出的浮层（嵌套 Dialog/Sheet、TagMenu）通过 `useModalHost` Teleport 到最上层 `[data-gv-modal]`，否则会被 inert。
4. 浏览器口径：Baseline 广泛可用直接用；新近可用特性（`popover`、`closedby` 等）必须特性检测并保留旧行为兜底，兜底不引入依赖。Toast 宿主在支持时用 `popover="manual"` 置于 top layer。
5. 菜单键盘契约统一走 `composables/useMenuKeyboard.ts`（Menu.vue 暂保留自有实现）。

## 理由与备选

- 备选：保留 div 方案，手写 focus trap + `inert` + Esc 栈——重复浏览器已有能力、维护成本高，否决。
- 备选：引入第三方 dialog/focus-trap 库——不必要的依赖，否决。

## 影响

- 新增模态组件必须复用 `components/ui/Dialog.vue`/`Sheet.vue` 或遵循同一模式；新增 Teleport 浮层若可能在模态内打开必须用 `useModalHost`。
- 已知限制：模态打开后才出现的 toast 视觉在上但不可交互（Chromium 命中仍归 dialog）；先于模态出现的 toast 会被压在模态下，直到下一条 toast。
- 单测依赖 `frontend/src/test-setup.ts` 的 jsdom `showModal/close` 最小 polyfill；行为以真实浏览器 E2E 为准。

## 确认方式

- `frontend/e2e/dialog-review-fixes.spec.ts`（跨断点、模态内 TagMenu、标题可访问名）与各点外关闭 E2E。
- 测试栈实测报告 `/tmp/opencode/reports/gv-smoke-a11y.md`（本机，2026-11-27，36+8 PASS）。

## 更多信息

开发记录：`docs/devlog/2026/11-27-fe-native-dialog.md`、`11-27-fe-dialog-review-fixes.md`、`11-27-fe-favpicker-heading.md`、`11-27-fe-menu-a11y.md`、`11-27-fe-toast-a11y.md`、`11-27-fe-img-priority.md`。
