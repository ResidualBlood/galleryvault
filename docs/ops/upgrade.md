# GalleryVault 升级与回滚

> 摘要 + 入口；完整升级步骤见 wiki [部署指南](../wiki/Deployment.md)，CI/发版见 [dev/release](../dev/release.md)。

## 升级路径

1. **代码**：`git push origin HEAD:dev` → CI（ci-backend/ci-frontend）测试通过后自动构建并推送 `:dev` 镜像。
2. **测试栈验证**：先 `docker cp` 同步代码 + `pip install -e ".[dev]"` 再 `start`，跑 pytest/ruff/冒烟（见 skill `galleryvault-maintenance`）。
3. **生产**（仅授权后）：`docker compose pull && up -d`；启动时 alembic 自动迁移（迁移版本见 `backend/alembic/versions/`）。
4. **发版**：`dev → main` + `git tag v*` 触发 `release-images.yml`；合 main 必须任务正文点名。

## 回滚

- 镜像回滚 tag：`residualblood/galleryvault-{frontend,backend}:rb-<YYYYMMDD-HHMM>`。
- DB 备份：生产 `gv-pre-*.dump`；有迁移的回滚需先 `alembic downgrade <target>`（见 HANDOFF 各条记录的具体 downgrade 目标）。
- 回滚顺序与注意见 [dev/pitfalls](../dev/pitfalls.md) 与 wiki [部署指南](../wiki/Deployment.md)。

## 注意

- 生产 compose 跟 `:dev` + watchtower 会**自动**拉取并迁移；发布前先做生产 DB 备份（[dev/pitfalls](../dev/pitfalls.md)）。
- 数据库迁移是向前兼容的增量脚本；跨大版本升级前先看 alembic 迁移链与 HANDOFF。
