---
task: fe-menu-a11y
date: 2026-11-27
kind: fix
source: 用户「按 modern-web-guidance 审查结果修前端，你自己决定」；审查 P2（Popover/TagMenu 有 role=menu 无键盘契约）
tickets: []
commits: []
decisions: []
docs: []
verified: []
unverified: []
---

# fe-menu-a11y Popover / TagMenu 补齐菜单键盘契约

## 改了什么

- `components/ui/Popover.vue`
  - 打开时把焦点移到面板内第一个 `role="menuitem"`（没有 menuitem 时退到第一个可聚焦控件），
    ArrowUp/ArrowDown/Home/End 在 menuitem 间循环，Esc 关闭并把焦点还给触发器，Tab 关闭。
  - 触发器上的 `aria-expanded` 跟随开合；`aria-haspopup="menu"` 只保留给真正含 menuitem 的面板。
  - 面板角色由插槽内容决定：含 menuitem 才算 `role="menu"`（Menu.vue 不变），AppShell 的两个按钮组
    popover 打开后不再错标 `role="menu"`；未打开前默认 `menu` 以免改变 Menu.vue。
  - 保留原有 `document` pointerdown（点外关闭）与 Esc 监听；Esc 处理识别 `defaultPrevented`，
    避免和 Menu.vue 自带的面板键盘处理重复执行。
- `components/tags/TagMenu.vue`
  - 打开（onMounted 后 nextTick）把焦点移到第一个菜单项；ArrowUp/ArrowDown/Home/End 循环；
    Esc 关闭并回焦打开菜单的元素，Tab 关闭。
  - 回焦目标在 onBeforeMount 捕获：优先 `document.activeElement`，右击/触摸长按后焦点在 body 时用
    `elementFromPoint(x, y)` 向上找可聚焦祖先（即标签 chip）。调用方签名不变。
  - 四个菜单动作（复制/筛选/在线搜索/排除）关闭后同样回焦触发标签。
- `composables/useMenuKeyboard.ts`：新增共享的 menuitem 查询/首项聚焦/循环导航纯函数，
  被 Popover 与 TagMenu 复用；Menu.vue 按 scope 不改编，仍保留自己的实现。
- 单测：新增 `ui/__tests__/layout/Popover.test.ts`（5 例）；`tags/__tests__/TagMenu.test.ts`
  增加首项聚焦、方向键循环、Esc 回焦、Tab 关闭 4 例。
- E2E：`e2e/kit-tags.spec.ts` 右键与长按用例断言首项聚焦、ArrowDown 移动、Esc 后 chip 回焦。

## 为什么

审查 P2：两个组件都声明了 `role="menu"` 却没有 WAI-ARIA 菜单键盘行为，键盘用户打开后焦点
仍停在触发器、无法用方向键选择、Esc 后焦点丢失。按现代菜单模式（打开移焦首项、方向键循环、
Esc 回焦、Tab 关闭）补齐；Popover 面板内容由插槽决定，因此不再无条件标 `role="menu"`。
浏览器支持口径：未使用 popover/top layer 等新近特性，沿用现有 `position: absolute` + document
监听实现，不需要特性检测或兜底分支。

## 验证

- `npm --prefix frontend run typecheck` → 退出码 0
- `npm --prefix frontend run lint` → 退出码 0
- `npm --prefix frontend run test:unit` → 51 文件 / 414 用例通过（含新增 Popover 5 例、TagMenu 9 例）
- `node frontend/scripts/check-design.mjs` → 退出码 0
- `node frontend/scripts/check-parity.mjs --strict` → 退出码 0
- `npm --prefix frontend run e2e:mock` → 258 passed，退出码 0（含 kit-tags 右键/长按键盘断言）

## 缺口与后续

- 未采用原生 `popover` 属性（controller 允许可选）；后续若要 top layer，需特性检测并保留现有监听兜底。
- TagMenu 的定位仍按写死的 248×232 夹逼（审查同条提到），不在本任务 scope，未改。
- AppShell 的 popover 面板角色在首次打开后才被纠正为无 role；触发器 `aria-haspopup` 也在此时移除，
  调用方未改（AppShell 不在 scope）。
