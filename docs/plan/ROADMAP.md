<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-plan；KEP 模板 https://raw.githubusercontent.com/kubernetes/enhancements/master/keps/NNNN-kep-template/README.md （Graduation Criteria / Implementation History / Risks and Mitigations）；里程碑表列为本仓设计，无外部依据 -->
# galleryvault 路线与里程碑

> 参考做法（Shape Up 章名“Fixed time, variable scope”，LIKELY，仅借鉴）：期限固定、范围可砍；出口标准是否调整由项目决定。里程碑按顺序推进；建议每个出口包含“文档已更新”。修订时保留历史行，不删旧记录（本仓设计）。

## 里程碑

<!-- 来源: KEP 模板 Graduation Criteria / Implementation History；实现规划 §3 总览与依赖、§4 批次详单 -->

| ID | 目标 | 完成标准 | 依赖 | 应交文档 | 状态 |
|---|---|---|---|---|---|
| M0 | 建仓与文档骨架 | 根 `AGENTS.md` 有项目事实；`docs/README.md` 的应有文档表已登记；基础检查命令可跑 | — | 本表、`STATUS.md`、`docs/README.md` | 进行中 |

填写规则：完成标准写成“可执行、可核对”的句子（命令跑通、验收通过、文档已更新）；“依赖”写前置里程碑 ID 或外部交付；状态只用 `未开始 / 进行中 / 已完成 / 已放弃`。

## 本阶段预算与可砍范围

<!-- 来源: Shape Up “Fixed time, variable scope”（LIKELY，仅借鉴“期固定、范围可砍”；出口标准与流程是否采用由项目决定）。 -->

- 本阶段截止：2026-11-20 起算的第 N 周（写具体日期）。
- 必保范围：—
- 可砍范围：—（砍掉后说明对出口的影响；出口标准是否调整由项目决定。）
- 砍掉后的替代做法：—

## 风险与缓解

<!-- 来源: KEP 模板 Risks and Mitigations；实现规划 §6 风险与缺口 -->

| 风险 | 影响 | 触发信号 | 缓解 | 责任人 |
|---|---|---|---|---|

## 文档映射

<!-- 来源: 实现规划 §5 方案→编码仓映射 -->

| 来源（方案 / 旧系统 / 外部资料） | 目标文档 | 抽取方式 | 状态 |
|---|---|---|---|
| — | `docs/` 下具体文件 | 只摘要点并写出处，不整份照抄 | 未开始 |

## 实现历史

<!-- 来源: KEP 模板 Implementation History -->

| 日期 | 里程碑 / 批次 | 变更 | 关联提交或工单 |
|---|---|---|---|

## 签核清单

<!-- 来源: KEP 模板 Release Signoff Checklist；“文档已更新、决策与记录已写”为本仓设计。 -->

- [ ] 里程碑完成标准逐条有证据（命令输出、验收记录或截图路径）。
- [ ] 应交文档已建且不再是空模板。
- [ ] 未完成项写进 `STATUS.md` 的“阻塞”或 `OPEN-QUESTIONS.md`。
- [ ] 相关决策已写进 `docs/decisions/`，开发记录已写进 `docs/devlog/`。
