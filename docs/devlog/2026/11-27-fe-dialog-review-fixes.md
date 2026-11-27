---
task: fe-dialog-review-fixes
date: 2026-11-27
kind: fix
source: 用户“按 modern-web-guidance 审查结果修前端，你自己决定”；审查 VERDICT=rework
tickets: []
commits: []
decisions:
  - FavPicker 合并为单一原生 dialog，只按断点改布局，不再在两个模态分支间搬移
  - 点外判定要求 event.target 就是 dialog 根（遮罩/留白），再叠加面板 rect
docs:
  - docs/devlog/2026/11-27-fe-dialog-review-fixes.md
verified:
  - npm --prefix frontend run typecheck :: 0
  - npm --prefix frontend run lint :: 0
  - npm --prefix frontend run test:unit :: 0（444 passed / 57 files）
  - node frontend/scripts/check-design.mjs :: 0
  - node frontend/scripts/check-parity.mjs --strict :: 0
  - npm --prefix frontend run e2e:mock -- e2e/dialog-review-fixes.spec.ts :: 0（2 passed）
  - npm --prefix frontend run e2e:mock :: 0（264 passed）
  - 基线 25b73d5 副本复跑新 spec :: 1（2 failed；跨断点后 fav-picker 不存在，TagMenu 复制后父 Sheet 已关）
unverified:
  - Firefox/WebKit 未跑（沿用 e2e:mock 的 chromium 配置）
  - iOS Safari 的触摸滚动与原生 dialog 行为未验证
---

# fe-dialog-review-fixes：原生 dialog 审查两项必修

## 改了什么

- **FavPicker 跨断点丢失**（审查必修 1）：`components/actions/FavPicker.vue` 不再在 `compact` 时挂 `Sheet`、桌面时挂另一个 `<dialog>`。现在始终是同一个 `Teleport` + 原生 `<dialog>`，断点只切换 `fav-picker--compact` 布局（底部整宽卡片）与桌面居中卡片；`open` watcher 不再依赖 `compact`，跨 599px 时 dialog 不重建，`data-gv-modal`/top layer/焦点都保持。
  - 保留 `data-testid`：窄屏仍为 `fav-sheet`，桌面为 `fav-picker`，现有 E2E 契约不变。
- **模态内 TagMenu 误关父 Sheet**（审查必修 2）：`Dialog.vue`、`Sheet.vue`、`NavSheet.vue`、`ReaderSettingsSheet.vue`、`FavPicker.vue` 的 `outside()` 统一改为：`event.target === 根 <dialog>` 且坐标在可视面板 rect 外。Teleport 到 host 里的 TagMenu 等子浮层冒泡上来的 pointer 事件 target 是浮层元素，不再被当成遮罩点击。
  - `TagMenu.vue` 根 additionally `@pointerdown.stop` / `@pointerup.stop`，与命中判定双保险。
- **Minor：卸载时仍 open 的 dialog**（审查 minor）：五个模态都在 `onBeforeUnmount` 里若 `dialog.open` 先清 `data-gv-modal` 再 `close()`，避免直接卸载把焦点丢到 BODY，也避免残留的顶层模态标记影响 host 查找。与审查建议的“devlog 记已知限制”二选一，这里直接修。
- 单测补充：`Dialog.test.ts` / `Sheet.test.ts` 各加“嵌套浮层冒泡不触发点外关闭”和“owner 卸载时关闭仍 open 的 dialog”。
- 新增真实浏览器回归 `frontend/e2e/dialog-review-fixes.spec.ts`：
  1. 390×844 打开收藏选择器（`fav-sheet`），扩到 1280×900 后同一模态变成 `fav-picker`，仍匹配 `:modal`，焦点仍在 dialog 内；
  2. 390×844 `card-tag-sheet` 内右键标签打开 TagMenu，点击复制后父 Sheet 仍匹配 `:modal` 且可见，最后 Esc 才关闭。

## 为什么

审查的两条必修都来自“同一个 DOM 生命周期里换分支”：

- FavPicker 旧的 `v-if="compact"` 与 `v-else` 并存时，断点切到桌面会在旧 Sheet 尚未卸载前调用 `refreshHost()`，把即将卸载的 Sheet dialog 选成新 dialog 的 Teleport host；旧分支移除后新 dialog 随之断开，业务 `open` 仍 true，焦点落 BODY。合并成单一 dialog 后没有“新旧两个 host”这个时序。
- Sheet 的旧点外逻辑只看坐标是否在面板 rect 外；TagMenu 被 Teleport 成 dialog 的兄弟节点，菜单项天然落在面板 rect 外，pointerdown/up 冒泡到 dialog 后就被当作遮罩点击。先要求事件 target 是 dialog 根，才能把“面板外的宿主子树”与“真正的遮罩/留白”区分开。

## 验证

- `npm --prefix frontend run typecheck` → 0
- `npm --prefix frontend run lint` → 0
- `npm --prefix frontend run test:unit` → 0（444 passed / 57 files）
- `node frontend/scripts/check-design.mjs` → 0
- `node frontend/scripts/check-parity.mjs --strict` → 0
- `npm --prefix frontend run e2e:mock -- e2e/dialog-review-fixes.spec.ts` → 0（2 passed）
- `npm --prefix frontend run e2e:mock` → 0（264 passed，全量 chromium mock）
- 基线 `25b73d5` 的 `/tmp` 副本（仅替换为本 spec）复跑 `e2e/dialog-review-fixes.spec.ts` → 1（2 failed）：跨断点后 `fav-picker` 元素不存在；TagMenu 复制后父 Sheet 已关闭，符合 RED 预期。

## 缺口与后续

- 只验证 Chromium mock；Firefox/WebKit 与 iOS Safari 的 top layer/触摸滚动未覆盖。
- 程序化直接卸载模态时现在会先 `close()`，但若原触发器已随同一更新被移除，浏览器仍只能把焦点归还给仍存在的元素/BODY，这是原生 dialog 的既有边界。
- FavPicker 窄屏从 Sheet 的标题栏改为面板内标题，视觉上少一个拖拽把手；如需完全对齐 Sheet 外观，可单独补 handle（不影响本次行为修复）。
