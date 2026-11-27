# GalleryVault 构建与发布

> 命令清单；流程约束（默认不 push、完成态拆三截）见项目根 `AGENTS.md` 与 skill `galleryvault-maintenance`。

## 本地构建与验证

后端（`backend/`）：

```bash
cd backend
uv pip install --system -e ".[dev]"      # 或 pip install -e ".[dev]"
ruff check galleryvault/                  # lint
pytest -q -n 2 -p no:cacheprovider --cov=galleryvault --cov-fail-under=45
```

前端（`frontend/`）：

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run test:unit
npm run build                 # -> dist/，nginx 服务
node scripts/check-design.mjs
node scripts/check-parity.mjs
npm run e2e:mock -- --grep @shell   # 批处理门禁
```

真实环境验证必须进测试容器（测试栈 :8200/:8201），不能只在宿主编译树报绿。

## CI 流水线（`.github/workflows/`）

| 工作流 | 触发 | 作用 |
| :--- | :--- | :--- |
| `ci-backend.yml` | push 到 `main`/`dev` 且后端相关文件变更 | Postgres tmpfs + alembic 迁移 + `ruff` + `.importlinter` 契约 + contract 测试 + pytest（覆盖率 ≥45%）；通过后 buildx 多架构（amd64+arm64）构建镜像并 `imagetools create` 合成 manifest，推送 `:dev` |
| `ci-frontend.yml` | push 到 `main`/`dev` 且前端相关文件变更 | npm 构建 + 单测 + mock E2E + 设计/parity 守门；构建并推送前端镜像 |
| `release-images.yml` | 打 `v*` tag | gitleaks 扫描 + 后端测试 + 发布版镜像构建 |
| `sync-wiki.yml` | push 到 `dev` | `rsync --delete` 把 `docs/wiki/` 同步到 wiki 仓 |
| `sync-docs.yml` | push | 同步 `backend/docs/` |
| `pages.yml` | 每小时 / main | 从 `main` 构建 VitePress `docs-site` |
| `sync-dockerhub-desc.yml` | — | 同步 Docker Hub 描述 |

## 发布节奏

1. **日常**：`git push origin HEAD:dev` → 触发 ci-backend/ci-frontend，测试通过后自动推送 `:dev` 镜像（生产 compose 跟 `:dev` + watchtower 会**自动**拉取，见 [pitfalls](pitfalls.md)）。
2. **发版**：`dev → main` 才发版；`git tag v*` 触发 `release-images.yml`。合 main 必须任务正文点名。
3. **生产更新**（仅授权后）：生产 `docker compose pull && up -d`；启动时 alembic 自动迁移。
4. **回滚**：镜像 tag（`rb-*`）+ 生产 DB 备份（`gv-pre-*.dump`），见 HANDOFF 各条记录。

## 文档同步

- 权威源是 `docs/wiki/`（中英成对）。dev 推送后 `sync-wiki.yml` 用 `rsync --delete` 同步到 wiki 仓，**不要直接改 wiki 仓**。
- wiki 图片引用 `raw.githubusercontent.com/.../main/docs/screenshots/...`，新截图要等 `main` 更新后才在 wiki 显示。
- 往 `main` 推 docs/wiki 改动时提交信息必须带 `[skip ci]`，否则会用旧内容覆盖 wiki。
