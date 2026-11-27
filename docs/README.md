# galleryvault 文档总目录

> 先按读者找入口，再按模块查应有文档。文档与代码同一提交，解释“为什么”和“怎么做”；事实以代码和本仓根 `AGENTS.md` 为准。生成于 2026-11-20，之后由项目自己维护。

<!-- 版式参考：GitLab runbooks README 的 Recommended structure（https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md）与 Diátaxis 文档形态（https://diataxis.fr/map/）。本文件只做总目录：按读者找入口 + 应有文档表，不写单篇内容；该结构为本仓设计，无外部依据。 -->

## 1 按读者找入口

拿不准从哪篇看起时，按自己的角色看下表；路径都相对本文件（`docs/`）。

| 读者 | 先读 | 什么时候看 |
|---|---|---|
| 主控、全体 | `docs/plan/ROADMAP.md` 路线与里程碑 | 立项时 |
| 接手开发 | `docs/dev/` 开发文档 | 需要第二人接手时 |
| 前端、设计 | `docs/ui/` 页面清单与样式入口 | 开始做界面前 |
| 集成方、开发 | `docs/api/` 接口契约 | 定义对外接口时 |
| 运维 | `docs/ops/` 安装、升级与排障 | 首次部署前 |

## 2 应有文档

未到起写时机的文档只在这里登记，不预建空文件；状态与实际不符时以实际为准。

| 文档 | 读者 | 路径 | 起写时机 | 状态 |
|---|---|---|---|---|
| 路线与里程碑 | 主控、全体 | `docs/plan/ROADMAP.md` | 立项时 | 已建 |
| 当前状态 | 主控、全体 | `docs/plan/STATUS.md` | 每批合入后 | 已建 |
| 待决问题 | 主控、全体 | `docs/plan/OPEN-QUESTIONS.md` | 出现悬而未决的问题时 | 已建 |
| 会话提示词 | 主控、接手者 | `docs/plan/SESSION-PROMPT.md` | 换会话或交接时 | 已建 |
| 决策记录 | 全体 | `docs/decisions/` | 出现需要回看的决定时 | 已建 |
| 开发记录 | 执行者、主控 | `docs/devlog/` | 每次代码改动、返修或热修 | 已建 |
| 开发文档 | 接手开发 | `docs/dev/` | 需要第二人接手时 | 已建 |
| 配置项规范 | 开发、运维 | `docs/dev/config.md` | 出现可配置项时 | 已建 |
| 测试数据规范 | 开发、测试 | `docs/dev/testdata.md` | 引入测试数据时 | 已建 |
| 发布与回滚 | 开发、运维 | `docs/dev/release.md` | 首次发版前 | 已建 |
| 页面清单与样式入口 | 前端、设计 | `docs/ui/` | 开始做界面前 | 已建 |
| 前端样式规范 | 前端、设计 | `docs/ui/design-system.md` | 开始做界面前 | 已建 |
| 接口契约 | 集成方、开发 | `docs/api/` | 定义对外接口时 | 已建 |
| 安装、升级与排障 | 运维 | `docs/ops/` | 首次部署前 | 已建 |

## 记录与索引

- 决策、开发记录与计划状态的写法见 `docs/dev/workflow.md`。
- 索引只由主控在主仓运行 `project_docs.py index --root .` 重建。
