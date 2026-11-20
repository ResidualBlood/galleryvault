<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-dev；本机参考项目 docs/dev/handbook/00-onboarding.md:5（十分钟速览→读什么→第一周；接手顺序） -->
# galleryvault 开发文档

> 写给“刚接手、没读过代码”的人。事实以代码和根 `AGENTS.md` 为准；这里解释设计意图、约定与踩坑。

## 十分钟速览

<!-- 来源: dev/handbook/00 导读与接手（按接手顺序排） -->

- 这个项目做什么：`<一句话>`。
- 现在能跑什么：`<可运行入口与最小验证命令>`。
- 最近一次可用状态：看 `docs/plan/STATUS.md` 的更新日期与“已完成”。

## 读什么

<!-- 来源: dev/handbook/00（读什么、按接手顺序） -->

| 文件 | 内容 | 维护时机 |
|---|---|---|
| [goals.md](goals.md) | 目标、非目标、原则与张力、写码前判定清单 | 目标或约束变化时 |
| [architecture.md](architecture.md) | 上下文、策略、构建块、运行时、部署、横切 | 结构调整时 |
| [conventions.md](conventions.md) | 分支提交、共享文件写范围、目录、代码风格、禁止提交项 | 约定变化时 |
| [pitfalls.md](pitfalls.md) | 现象 → 原因 → 排查顺序 → 规避 | 每次踩坑后 |
| [workflow.md](workflow.md) | 执行纪律，决策、开发记录、计划状态的写法与时机 | 记录流程变化时 |
| `docs/ui/design-system.md` | 前端样式规范：Token、色彩、字体、状态语义、组件规矩（仅启用 frontend 模块时存在） | 有前端界面时 |
| [config.md](config.md) | 配置项规范、默认值与出处、设计原则（可选章节） | 有可配置项时 |
| [testdata.md](testdata.md) | 测试数据规范与执行纪律：模拟器、回放、黄金对照、完整性校验、何时跑全量 | 引入测试数据时 |
| [release.md](release.md) | 版本号规则、分支模型、本地提交与钩子、发布与回滚 | 首次发版前 |

## 第一周

<!-- 来源: dev/handbook/00（第一周安排）；TGDP how-to（先写前置条件再给任务） -->

1. 跑通 `conventions.md` 里的检查命令，确认本机能跑测试。
2. 读 `goals.md` 的目标与非目标，再看 `architecture.md` 的主数据流。
3. 找一个已完成的批次，对照 `docs/devlog/` 看改了什么、验收怎么做的。
4. 按 `workflow.md` 写第一条开发记录，确认流程能走通。
