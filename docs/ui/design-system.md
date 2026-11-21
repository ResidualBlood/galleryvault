# galleryvault 前端设计规范

> 权威规范在 `frontend/docs/design/DESIGN.md`（v1.0，2026-11-12）；本文件只写入口与关键约束，不复制 Token。Token 单一来源 `frontend/src/styles/tokens.css`。

## 入口

| 项 | 位置 |
| :--- | :--- |
| 设计规范正文 | `frontend/docs/design/DESIGN.md` |
| Token 来源 | `frontend/src/styles/tokens.css` |
| 必备 Token 清单 | `frontend/docs/design/tokens.required.json` |
| 静态样张 | `frontend/docs/design/specimen.html`（`#/_kit` 也渲染控件阶梯） |
| 参考清单 | `frontend/docs/design/REFERENCES.md` |
| 守门脚本 | `frontend/scripts/check-design.mjs` |

## 关键约束（每批 UI 必须满足）

1. 只用 `--gv-*` token；`src/**/*.{vue,css,ts}` 内不得出现裸色值、`font-size` 字面量、非 token 圆角。
2. `node frontend/scripts/check-design.mjs` 退出码 0（`--tokens-only` 只查 token + 对比度）。
3. 亮/暗 × 桌面 1280 / 手机 390 四张截图，存树外；验收回执列出对照的 `DESIGN.md` 章节。
4. 组件结构、尺寸、状态按 `DESIGN.md` 第 4 节执行；偏离须在回执说明理由。

## 组件体系

- 无第三方组件库；原语在 `frontend/src/components/ui/`（Button/IconButton/Input/Select/Switch/Dialog/Sheet/Toast/EmptyState/ErrorState/Skeleton 等）。
- 控件尺寸阶梯：`--gv-size-control-xl/lg/md/sm` = 48/40/36/32（触屏 48/44/40/36）；登录/欢迎表单保留 48。
- 图标只从注册表取：`<Icon name="..." />`（`frontend/src/components/icons/`）；Unicode glyph 与每页 `~icons/` 导入会被设计守门拒绝。
- 标签命名空间配色：`--gv-tagns-<namespace>` 15 个 EH 命名空间，各 ≥4.5:1 对比度。
- 页面骨架：`PageHeader`（h1/count/crumbs/actions）+ `Toolbar`（一档尺寸）+ `GalleryCollection`（grid/list/table）+ `EmptyState`。

## 交互与可访问性

- 视图切换按页记忆（`localStorage.gv_view_mode`），<600px 无表格（回退 list，不覆盖原值）。
- tag 点击行为、chip 展示（色点 + 命名空间）、`+N` 真实计数见 `frontend/README.md`「视图切换与 tag 规则」。
- WCAG 对比度门槛与实测方法见 `DESIGN.md`「色彩与对比度」。
