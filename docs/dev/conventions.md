# GalleryVault 开发约定

> 团队共享约定已写进项目根 `AGENTS.md`；本文件只登记“写代码时要遵守、能脚本校验”的约定与出处。

## 后端（`backend/`）

- **lint/格式化**：`ruff`（见 `backend/pyproject.toml` 的 `[tool.ruff]`）；测试容器内 `ruff check galleryvault/`。
- **类型与结构**：`.importlinter` 16 条契约，`test_p2_architecture` 钉死导入边界（领域包之间不得互相 import；见 HANDOFF 2026-11-15「导入契约收紧」）。
- **生产代码禁止引用 `app.main` 除装配外的符号**（AGENTS.md），避免 import 时连带 DB/worker 副作用。
- **错误**：抛 `app/exceptions.py` 里的领域异常，不裸抛 `HTTPException`；错误体 `{detail, code}` 见 [models.md](../api/models.md)。
- **写文件用原子写**：`services/fsutil` 共享一个原子 cache 写入器（commit 63f89af）。
- **DB 会话**：只读路径用 `Depends(get_session)`；EH 网络前先释放 session（见 HANDOFF 2026-11-14「四个读写路径释放 session」）。

## 前端（`frontend/`）

- **端点声明只放 `src/api/<domain>.ts`**，用 `ep("GET","/api/...")` 声明；ESLint 拒绝在 `src/api/` 之外出现裸 `/api/` 字面量（`frontend/README.md`「API client contract」）。
- **组件/样式**：只用 `--gv-*` token，禁裸色值/字面量 `font-size`/非 token 圆角；用 `<Icon name="...">` 不用 Unicode glyph；控件走 `src/components/ui/` 的尺寸阶梯。守门脚本 `frontend/scripts/check-design.mjs`（退出码 0）。
- **i18n**：文案按 feature 分 `src/locales/{zh,en}/<feature>.json`，键集必须一致（单测校验）；vue-i18n 构建期预编译。
- **测试钩子**：稳定 `data-testid`（`gallery-card`、`gv-page-header`、`gv-toolbar` 等），mock/real E2E 共用选择器。
- **提交前**：`npm run typecheck`、`npm run lint`、`npm run test:unit`、`npm run build`、`node scripts/check-design.mjs`、`node scripts/check-parity.mjs`。

## 通用

- **验证必须进测试容器**（测试栈 compose，:8200/:8201），不能只在宿主编译树报绿（AGENTS.md 铁律）；测试栈命令见 skill `galleryvault-maintenance`。
- **完成态拆三截**：验证 → commit（只 commit，默认 `dev`）→ 发布（人授权才 push）。
- **文档**：权威源 `docs/wiki/`（中英成对）；dev 推送后由 `.github/workflows/sync-wiki.yml` rsync 到 wiki 仓，不直接改 wiki 仓。
- **凭据**：密码/cookie/token 不写进仓库、wiki、commit、PLAN、HANDOFF；值用 `op-run`/env 注入，只写“值放哪”。
