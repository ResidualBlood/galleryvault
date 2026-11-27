---
task: fe-img-priority
date: 2026-11-27
kind: fix
source: 用户「按 modern-web-guidance 审查结果修前端，你自己决定」；审查结论 /tmp/opencode/mwg/audit.md P3
tickets: []
commits: []
decisions: []
docs: []
verified:
  - npm --prefix frontend run typecheck :: exit 0
  - npm --prefix frontend run lint :: exit 0
  - npm --prefix frontend run test:unit :: exit 0（51 文件 / 406 用例）
  - node frontend/scripts/check-design.mjs :: exit 0
  - node frontend/scripts/check-parity.mjs --strict :: exit 0
  - npm --prefix frontend run e2e:mock :: exit 0（258 passed，24.8m）
unverified:
  - 网格/列表首屏卡片 eager：需给 VirtualGrid → GalleryCard/GalleryListRow 新增 eager prop 链，按任务单“否则只做封面”的兜底未做
  - 阅读器当前页 fetchpriority：ReaderPage 自身没有当前页信号，currentPage 在 ReaderShell（scope 外），未接线
---

# fe-img-priority 详情页封面按 LCP 提升加载优先级

## 改了什么

- `GalleryDetailLayout.vue` 详情页封面 `<img>` 增加 `fetchpriority="high"`，保持 `decoding="async"`，不加 `loading="lazy"`。
- 新增 `__tests__/detail/GalleryDetailLayout.test.ts`，断言封面带 `fetchpriority="high"`、无 `loading` 属性、仍为异步解码。

## 为什么

modern-web-guidance `optimize-image-priority`：LCP 候选图必须 `fetchpriority="high"`，且 high 禁止与 `loading="lazy"` 组合；详情页封面是首屏最大图，按审查结论 P3 处理。网格卡片需要先把“首屏”位置从 VirtualGrid 传给卡片，构成新的 prop 链，按任务单兜底只做封面；未给任何屏外 lazy 图加 `fetchpriority="low"`。

## 验证

见 front matter `verified`。E2E mock 全量结果补记于此。

## 缺口与后续

- 网格/列表首屏卡片仍为 `loading="lazy"`；若后续接受新增 `eager` prop，可在 VirtualGrid 首行启用。
- 阅读器当前页没有现成信号可读（`ReaderPage` 只有 `page/src`，`currentPage` 在 `ReaderShell`），本次未改。
- `ThumbGrid`、`GalleryTableRow` 等仍保持 lazy；它们位于首屏下方，符合指南。
