# 决策记录

<!-- 出处: docs/PROJECT_INIT-templates-research.md §1（ADR/决策记录）与 §13.1（逐字段对照）；外部结构参考 MADR 4.0.0 Full template（https://adr.github.io/madr/）与 Nygard 2011（https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions）。索引只在主仓重建、小决定并入开发记录为本仓设计，无外部依据。 -->

> 一条决定一个文件，只新增、不就地改写结论。命名 `<YYYY-MM-DD>-<短名>.md`，短名用英文小写与连字符。索引 `INDEX.md` 由主控在**主仓**重建，不手工合并。

## 何时单独记录

<!-- 来源: 用户要求（一条决定一个文件）；单独成文的边界与小决定并入开发记录为本仓设计，无外部依据。MADR/Nygard 只提供背景与状态字段。 -->

- 用户拍板、改变默认值 / 接口 / 行为口径、难以回退的决定。
- 小决定在开发记录里一句话带过。

## 字段（YAML front matter，键名固定）

<!-- 来源: MADR 4.0.0 Full template 的 YAML status / date / decision-makers / superseded by；tickets 来自用户要求（外部系统的决定写工单号/来源编号）；source 与键名收敛为本仓设计。 -->

| 字段 | 取值 |
|---|---|
| `status` | `proposed` / `accepted` / `superseded` |
| `date` | `YYYY-MM-DD` |
| `decider` | `user` / `maintainer` / `team` / 姓名 |
| `source` | 用户原话要点、工单号、评审记录 |
| `tickets` | 外部工单/来源（Redmine/Notion/聊天）编号或链接数组，可为 `[]`；只写编号或 URL，不写凭据 |
| `supersedes` | 旧决策文件名数组，可为 `[]` |
| `superseded_by` | 新决策文件名，生效中为 `null` |

## 正文结构

<!-- 来源: MADR 4.0.0 Full template 的 Context and Problem Statement / Decision Outcome / Decision Drivers / Considered Options / Consequences / Confirmation / More Information（https://adr.github.io/madr/）；中文章节名与顺序为本仓设计。 -->

`# 一句话标题`，然后依次是 `## 背景`、`## 决定`、`## 理由与备选`、`## 影响`、`## 确认方式`、`## 更多信息`。外部系统的决定在 `tickets` 写编号或链接，不写凭据。

## 取代关系

<!-- 来源: MADR 4.0.0 的 status / superseded by 与 Nygard 2011 的 Status；旧文件保留、只改状态为本仓设计。 -->

被推翻时不删旧文件：旧文件 `status` 改 `superseded`、`superseded_by` 指向新文件；新文件在 `supersedes` 列出旧文件。只允许改状态与取代关系。

## 并行

<!-- 来源: 本仓设计，无外部依据（日期+短名避免并行分支撞号；MADR 默认 NNNN 顺序编号）。 -->

文件名带日期与短名，不用顺序编号；并行分支各写一个文件，合并不会冲突。
