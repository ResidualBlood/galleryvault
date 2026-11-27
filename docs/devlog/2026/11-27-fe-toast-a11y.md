---
task: fe-toast-a11y
date: 2026-11-27
kind: fix
source: modern-web-guidance 审查（/tmp/opencode/mwg/audit.md，基线 c84d8af）P2 Toast；用户要求“按 modern-web-guidance 审查结果修前端，你自己决定”
tickets: []
commits: []
decisions: []
docs: []
verified:
  - npm --prefix frontend run typecheck :: 退出码 0
  - npm --prefix frontend run lint :: 退出码 0
  - npm --prefix frontend run test:unit :: 退出码 0（52 文件 / 416 用例，含新增 11 条）
  - node frontend/scripts/check-design.mjs :: 退出码 0
  - node frontend/scripts/check-parity.mjs --strict :: 退出码 0
  - npm --prefix frontend run e2e:mock :: 退出码 0
unverified:
  - 真实浏览器（非 Chromium）下的 popover 顶层排序与屏幕阅读器播报未做人工验证
---

# fe-toast-a11y Toast 可访问性与原生模态共存

## 改了什么

- `components/ui/Toast.vue`
  - 外层宿主改为 `role="region"` + `aria-label`（locale `common.toastRegion`）+ 单一 `aria-live="polite"`；去掉每条 toast 的 `role="status"`，消除重复播报。
  - 支持 Popover 时宿主加 `popover="manual"` 并 `showPopover()` 进入 top layer；每次新增 toast 时重新 hide/show，使其排在原生模态之上；不支持时保留 fixed 定位兜底。特性检测用 `Object.hasOwn(HTMLElement.prototype, "popover")`，不引入 polyfill/依赖。
  - 指针悬停、toast 内键盘焦点分别触发 `pauseToast` / `resumeToast`；手动关闭聚焦中的 toast 后焦点移到下一条，最后一条关闭后回到 push 时记录的焦点。
  - 增加 `prefers-reduced-motion` 下关闭动画；宿主样式重置 popover 的 UA border/background/margin，避免顶层出现默认边框。
- `stores/ui.ts`
  - 每条的定时器记录 deadline/remaining 与暂停原因集合；暂停时保存剩余时长，全部原因解除后按剩余时长续跑，TTL 默认值不变。
  - 记录 push 时的 `document.activeElement` 供关闭后回焦。
  - `push/info/success/error` 签名与调用方不变，新增 `pauseToast` / `resumeToast` / `returnFocusFor`。
- 新增单测：`stores/__tests__/ui.test.ts`（5 条）、`components/ui/__tests__/Toast.test.ts`（6 条）。
- E2E 定位器：`c3fix.spec.ts`、`real/favorites-downloads.spec.ts` 中 toast 从 `getByRole("status")` 改为 `.toast`（role 已按单 live region 调整）。

## 为什么

审查指出 `aria-live` 容器内每条又 `role="status"` 会重复播报，且容器缺少 region 名称；固定 TTL 会在用户悬停/聚焦关闭按钮时把 toast 抽走；并行任务把模态切换为原生 `<dialog>.showModal()` 后，body 下的 fixed toast 宿主会落在 top layer 之下并被 backdrop 压暗。按指南用 `popover="manual"` 提升到 top layer，新 toast 重新 show 以排在后来打开的模态之上。

## 验证

见 front matter `verified`。单测覆盖：默认 TTL、悬停暂停/剩余时长恢复、焦点与悬停双重暂停、手动关闭清定时器、回焦元素记录；组件覆盖单一 region/live 语义、popover 兜底、悬停/焦点暂停、关闭后焦点转移、支持 popover 时 show 与重新 show。

## 缺口与后续

- 非 Chromium 浏览器与屏幕阅读器的实际播报顺序未人工验证；`ariaNotify` 未采用（新近可用，按任务要求保留单一 aria-live 宿主）。
- 模态打开时只保证“新增 toast”重新提升到 top layer；已在 backdrop 下的旧 toast 不会主动提升，需等下一次 toast 或模态关闭。
- 已处于模态下时宿主可能仍受 inert 影响（指南不建议在模态中提示），本任务只解决可见性。
