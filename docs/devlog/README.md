# 开发记录

<!-- 出处: docs/PROJECT_INIT-templates-research.md §2（开发记录）与 §13.2（逐字段对照）；结构参考 towncrier news fragments（https://towncrier.readthedocs.io/en/stable/）与 Changesets frontmatter（https://changesets.dev）；字段与流程为本仓设计。 -->

> 一个任务 / 返修 / 热修一个文件，与代码同一提交。只记实际发生的事；未验证的如实写。

## 命名

<!-- 来源: 用户要求（一个任务一个文件）；文件名格式与目录层次为本仓设计，无外部依据（towncrier/Changesets 只提供“一文件+元信息”思路）。 -->

`<YYYY>/<MM-DD>-<任务ID>-<短名>.md`；短名用英文小写与连字符。

## 何时写

<!-- 来源: 本仓设计，无外部依据；用户要求只确认“一个任务一个文件”，未要求每次代码改动都写。 -->

- 有代码改动的任务建议写一条，返修与热修同样。
- 纯格式化、错别字可免。
- 未启用 `records` 的小工具用提交说明代替。

## 字段（YAML front matter，键名固定）

<!-- 来源: 本仓设计，无外部依据；frontmatter 形式参考 towncrier/Changesets，但字段集未由它们规定。 -->

| 字段 | 说明 |
|---|---|
| `task` | 任务 ID |
| `date` | `YYYY-MM-DD` |
| `kind` | `feature` / `fix` / `chore` / `refactor` / `docs` |
| `source` | 来源：用户原话要点、任务单或评审记录 |
| `tickets` | 外部工单/来源（Redmine/Notion/聊天）编号或链接数组，可为 `[]`；只写编号或 URL，不写凭据 |
| `commits` | 短 SHA 数组，可为 `[]` |
| `decisions` | 相关决策文件名数组，可为 `[]` |
| `docs` | 同批更新的文档相对路径数组，可为 `[]` |
| `verified` | 实际跑过的 `命令 :: 结果`，可为 `[]` |
| `unverified` | 未验证项，可为 `[]` |

## 正文结构

<!-- 来源: 改了什么/为什么为本仓设计；验证/缺口与后续借鉴 MADR 4.0.0 的 Confirmation / Consequences（https://adr.github.io/madr/）。 -->

`# <任务ID> <一句话>`，然后依次是 `## 改了什么`、`## 为什么`、`## 验证`、`## 缺口与后续`。外部系统的任务在 `tickets` 写编号或链接，不写凭据。

## 索引

<!-- 来源: 本仓设计，无外部依据（INDEX.md 由主控在主仓重建；缺记录只告警）。 -->

`INDEX.md` 由主控在**主仓**重建；缺记录只告警、不阻塞合入。

## 忽略与 worktree

<!-- 来源: 本仓设计，无外部依据（运行态不进 Git，worktree 只认已跟踪文件）。 -->

运行态 `.opencode/{plans,state,local,tmp}` 不进 Git，worktree 里看不到；执行者只认已跟踪的 `docs/`、`AGENTS.md` 与任务单。记录放已跟踪的 `docs/`，索引只在主仓生成，避免并行分支各改同一文件。
