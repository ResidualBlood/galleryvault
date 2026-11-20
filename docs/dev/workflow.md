<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-dev -->
# 记录与文档写法

> 过程记录与代码同一提交；决定当轮写下，不留在聊天、工单或本机记忆里。本文件只规定“写在哪、何时写”，不重复具体内容。

## 智能体执行纪律

<!-- 出处: 本机参考项目 docs/dev/handbook/13-conventions.md:66-87（角色与模型、智能体纪律 6 条、测试并行、子智能体超时）；AGENTS.md:71-72,84（模型约定、30 分钟代跑）（通用化，见调研 §R-constraints） -->

- 只改任务单写明的范围；需要越界先回报，不自行扩大。
- 开工先核对工作树目录与基线；返修先看文件与 diff，不重做。
- 一次只做一个验收目标，改了就跑对应检查；停下时回报“完成/部分/阻塞”，不写“应该可以”。
- 状态不明不重放命令；回执丢失不等于未执行。
- 协作走主控：不自行唤醒其他会话、不触发广播。
- 叶子角色按任务难度选模型与思考等级：搬运/文档低，常规中，协议/状态机/事务/算法高，逐位对齐类最高。
- 子任务超过 30 分钟无回复：先核查是否在串行跑测试；是则在快照副本并行代跑验收，通过即结束该子任务并合入，不死等。
- 里程碑收尾用更强的模型复审，并在干净 worktree 重跑该里程碑全部验收。

## 写作前置条件

<!-- 来源: TGDP how-to 模板 https://gitlab.com/tgdp/templates/-/blob/main/how-to/template_how-to.md （Overview→Before you start→Task→See also，2026-11-20 实读）；R-dev 章节清单（流程先写前置条件） -->

- 先确认这条记录属于哪类：决策、开发记录、计划状态、资料、协议；不同类不混写。
- 先确认是否已有同类文件：一个决定一个文件、一个任务一个文件，不追加到别人的文件里。
- 先确认影响面：改默认值 / 接口 / 行为口径的，必须先写决策记录，再改代码。

## 决策

<!-- 来源: MADR 4.0.0（https://adr.github.io/madr/）+ Nygard 2011（https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions）。 -->

- 位置：`docs/decisions/`，一条一个文件 `<YYYY-MM-DD>-<短名>.md`。
- 生成：`project_docs.py new decision --root . --slug <短名> --title <一句话>`。
- 边界：用户拍板、改变默认值 / 接口 / 行为口径、难以回退的决定才单独成文；小决定写进开发记录。
- 被推翻时保留旧文件，改 `status` 与 `superseded_by`，新文件在 `supersedes` 指向旧文件。

## 开发记录

<!-- 来源: towncrier news fragments（https://towncrier.readthedocs.io/en/stable/）+ Changesets frontmatter（https://changesets.dev）；只借鉴“一文件+元信息”，字段为本仓设计。 -->

- 位置：`docs/devlog/<YYYY>/<MM-DD>-<任务ID>-<短名>.md`。
- 生成：`project_docs.py new devlog --root . --task <任务ID> --slug <短名> --kind <类型>`。
- 一个任务一个文件，与代码同一提交；缺记录只告警、不阻塞合入。

## 计划与状态

<!-- 来源: KEP 模板（Graduation Criteria / Implementation History）；ROADMAP/STATUS 分工与“出口含文档已更新”为本仓设计，无外部依据。 -->

- `docs/plan/ROADMAP.md` 写里程碑、完成标准与依赖，出口必须含“文档已更新”。
- `docs/plan/STATUS.md` 写当前状态、在飞、阻塞、下一步与协同安排；长期规则不进这里。
- `docs/plan/OPEN-QUESTIONS.md` 写需要拍板的事；`docs/plan/SESSION-PROMPT.md` 是交接开场提示。
- 编排用的运行态计划不进 Git；批次验收时把结论提升到上述文档与决策记录。

## 索引

<!-- 来源: 本仓设计，无外部依据（索引由工具生成，只在主仓重建）。 -->

- `docs/decisions/INDEX.md` 与 `docs/devlog/INDEX.md` 是生成物，只由主控在**主仓**运行 `project_docs.py index --root .` 重建。
- 合并冲突时重跑生成，不逐行手工合并。

## 其它资料

<!-- 来源: TGDP reference/how-to 分类；文档启用时机为本仓设计，无外部依据。 -->

- 资料与手册先在 `docs/README.md` 的应有文档表登记，到起写时机再建文件。
- 本机事实（路径、设备入口、凭据位置）放 `.opencode/local/MEMORY.md`，不进 Git。

## 通讯协议

<!-- 来源: 本仓设计，无外部依据（链路一节一文件 + registers.yaml）；协议内容出处见 docs/protocol/ 模板。 -->

- 位置：`docs/protocol/README.md` 管链路总表，一条链路一个 `<短名>.md`；新链路用 `project_docs.py new protocol-link --root . --slug <短名>`。
- 从旧源码反推的协议先放 `docs/research/`，文首标“从源码推出，非规格”；核对后提炼进 `docs/protocol/`。
- spec-first 的 `.opencode/specs/SPEC-*.md` 定稿后迁入 `docs/protocol/`，原文件只留指针。
- 链路、地址、帧格式或默认值变更要写决策记录与开发记录；改完更新 `registers.yaml` 并重生成、跑 `--check`。
- 每条链路按模板九节写全：物理层、帧格式、校验、命令/寄存器、时序与状态机、错误码、版本兼容、真实抓包、验证方式；缺节 `--check` 只 `warn`。

## 质量与风险

<!-- 来源: arc42 §10 Quality Requirements、§11 Risks and Technical Debt -->

- 质量要求写成可验收的句子（场景 + 期望值 + 验证命令），不写“尽量快”“足够稳”。
- 已知技术债与风险登记在 `docs/plan/ROADMAP.md` 的“风险与缓解”，本文件只写写法要求。
- 验收结论必须附命令输出或产物路径；未验证的项标“未验证”，不写成通过。

## 忽略与 worktree

<!-- 来源: 本仓设计，无外部依据（运行态不进 Git，worktree 只认已跟踪文件）。 -->

- 运行态 `.opencode/{plans,state,local,tmp}` 不进 Git，因此不会出现在 worktree；执行者只认已跟踪的 `docs/`、`AGENTS.md` 与任务单。
- 决策与开发记录放已跟踪的 `docs/`，worktree 与并行分支都能看到；索引只在主仓生成，避免两边各改同一文件。
