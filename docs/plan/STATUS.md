# 当前状态

> 每批合入后由主控更新；只写当前事实，长期规则写进根 `AGENTS.md`。时间只写日期，不写“刚刚”“最近”。

- 更新日期：2026-11-27
- 当前分支 / HEAD：`dev`（前端 a11y 批次 + Dependabot #44-#48 合并后）
- 最近完成批次（来源 git log / HANDOFF）：
  - 前端 modern-web-guidance 审查修复：模态迁原生 `<dialog>`、菜单键盘契约、Toast region/暂停/top layer、详情封面 fetchpriority（2026-11-27，决策 `docs/decisions/2026-11-27-native-dialog-overlays.md`）
  - Dependabot #44-#48 依赖下限合并（2026-11-27）
  - 修复保存设置后运行时 Cookie/Bot Token 被清空（2026-11-22，`c84d8af`）
- 进行中：发布本批到 dev/main 与生产（用户授权）
- 阻塞：—
- 下一步：网格首屏卡片 eager、阅读器当前页 fetchpriority、AppShell Popover 显式声明非菜单 role（后续可选）

## 在飞与阻塞

| 项 | 谁在做 | 开始日期 | 当前进展 | 解除条件 |
|---|---|---|---|---|

## 协同

- 本轮总协调：主控（ogma-chaos 会话）
- 并发上限：本仓同一时刻只允许一方改 docs/（见任务书）
- 冻结文件：—
- 互斥区：`docs/wiki/`、`docs/screenshots/`（本轮由本会话独占）

## 缺口

| 缺口 | 影响 | 何时补 | 记录位置 |
|---|---|---|---|
| `Deployment-EN.md` 未随 Deployment.md 同步 | 英文部署文档落后 | 待定 | HANDOFF 2026-11-15 |
| 真实 GID 换版 finalize E2E 未执行 | 换版迁移缺端到端证据 | 待定 | HANDOFF 2026-11-15 |
| Q9 超时默认值未对生产验证 | 生产超时行为未实证 | 待定 | HANDOFF 2026-11-15 |
| 容器内 test_cold_* + test_storage_usage 组合偶发 1 例 503 | 既有测试隔离问题 | 待定 | HANDOFF 2026-11-15 |
