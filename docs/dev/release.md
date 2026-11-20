<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-release -->
# 版本号规则与分支发布流程

> 先定“版本号怎么涨、分支怎么走、发布按什么顺序”，再谈工具。发布=产物 + 顺序 + 校验 + 门禁 + 撤回，五段缺一不可。

## 版本号规则

<!-- 来源: SemVer 2.0.0（https://semver.org/）；CalVer calver.org（交付物按日期发版，声明非 semver） -->

- 对外接口 / 库 / 可升级软件用 SemVer：`MAJOR.MINOR.PATCH`。
  - MAJOR：不兼容的接口或行为变更。
  - MINOR：向后兼容的新功能。
  - PATCH：向后兼容的修复。
  - 预发布：`1.2.0-rc.1`；`0.y.z` 视为不稳定，MINOR 可含破坏性变更。
- 按日期交付的整包 / 镜像用 CalVer：`YYYY.MM.<patch>`，并在发布说明里声明“非 SemVer”。
- 一个项目只选一种主规则，写在这里；两种并存时说明各自适用范围。

## 分支模型

<!-- 来源: Trunk Based Development（Short-Lived Feature Branches / Branch for release / Release from trunk）；ops/branching.md -->

- 主干：`<主干名>` 是唯一集成线；功能分支短命，从主干切、回合主干后删除。
- 发布分支：从主干切 `release/<x.y>`，只接受修复；修复先回主干，再 cherry-pick 到发布分支。
- 不允许长期分叉的双主干；大改动用功能开关，不靠长分支。

## 提交与合入

<!-- 来源: Conventional Commits 1.0.0（`type[scope]: desc`，fix↔PATCH、feat↔MINOR、BREAKING CHANGE footer） -->

| 提交类型 | 版本档位 | 说明 |
|---|---|---|
| `fix` | PATCH | 修复 |
| `feat` | MINOR | 新功能 |
| 正文含 `BREAKING CHANGE:` | MAJOR | 破坏性变更，必须显式写 |
| `docs` / `chore` / `refactor` / `test` | 不涨版本 | 不改变对外行为 |

- 合入前必须通过 `conventions.md` 里的检查命令与测试。
- 破坏性变更在决策记录里写明迁移方式。

## 本地提交与钩子

<!-- 出处: 本机参考项目 docs/dev/handbook/13-conventions.md:16-36,122-133（本地提交、提交信息与正文、原子提交、禁止提交项）；docs/ops/branching.md:20-38,43（分支、提交内容、提交信息、推 tag 授权）；AGENTS.md:80,85（push 前测试/钩子职责/单独授权、禁止提交项）；docs/dev/shared-files.md:35-37（运行态与凭据不进仓库）（通用化，见调研 §R-constraints） -->

- 执行会话只做本地提交，不合入、不 push；合入与推送由主控执行。
- 提交信息：任务制用 `<任务ID> <动词>：<一句话>`；正文写实际跑过的验收命令与结果、已知缺口、后续事项，不贴长日志、不贴完整 diff。若同时采用上节的语义化类型，类型只用于版本档位。
- 一个任务一到几次原子提交，不夹带无关改动；格式化只处理本次改动的文件。
- push 前测试必须通过；推 tag、发布、生产部署需单独授权。
- 钩子职责：
  - `pre-commit`：只对暂存文件跑格式化与 lint，单文件级、秒级返回。
  - `pre-push`：跑结构约束与契约检查，再按本次推送的改动并行跑定向测试；目标 ≤2 分钟，超过上限只跑基础项（提供快速开关）。
- 钩子不自动安装，由新检出显式启用；模板只给脚本与安装说明。
- 禁止提交：运行态计划（`PLAN`）与本地运行/临时目录、`.env` 与密钥口令、构建产物与依赖目录、测试报告与覆盖率、本机绝对路径、与本任务无关的格式化。

## 发布流程

<!-- 来源: ops/release.md §1 产物 / §2 顺序 / §3 校验 / §4 门禁 / §5 回滚撤回 / §6 本地与 CI 同口径 -->

1. 产物：列出本次交付的文件、镜像、包与校验和。
2. 顺序：写清先发什么、后发什么，以及每步的前置条件。
3. 校验：发布后核对版本号、校验和、启动与关键功能。
4. 门禁：测试通过、文档已更新、决策与记录已写；任一不满足不发布。
5. 撤回：写明触发条件与回退步骤（见下节）。

- 本地与 CI 用同一套命令与参数；不一致时以 CI 为准并修本地脚本。

## 回滚与撤回

<!-- 来源: ops/release.md §5；Keep a Changelog 1.1.0（YANKED） -->

| 触发条件 | 回滚到 | 步骤 | 验证 | 记录 |
|---|---|---|---|---|

- 已发布的坏版本在 changelog 标 `YANKED` 并说明原因，不删记录。
- 回滚后必须验证关键功能与数据完整性，再恢复发布。

## 变更日志

<!-- 来源: Keep a Changelog 1.1.0（Guiding Principles、Types of changes、Unreleased、日期格式） -->

- 位置：`CHANGELOG.md`；版本倒序，日期用 `YYYY-MM-DD`。
- 六类分节：Added / Changed / Deprecated / Removed / Fixed / Security。
- 未发布变更放 `## [Unreleased]`；链接与版本号对应。
- 只写对使用者有意义的变更，不贴提交列表。

## 升级注意事项

<!-- 来源: SemVer 2.0.0 的升级注意事项（https://semver.org/）；ops/upgrade.md（升级前核对与回滚预案） -->

- 升级前：备份配置与数据、确认回滚路径、确认空间与版本兼容。
- MAJOR 升级必须给迁移步骤与不可逆项说明。
- 升级后核对：版本号、配置项是否按默认值补齐、关键流程可用。

## 发布资产

<!-- 来源: 本仓设计，无外部依据（发布资产取舍）；ops/release.md §1 -->

| 资产 | 是否必发 | 命名规则 | 校验方式 |
|---|---|---|---|
| 安装包 / 镜像 | 是 | — | SHA256 |
| 校验和清单 | 是 | — | `sha256sum -c` |
| 发布说明 | 是 | — | 与 changelog 对应 |
| 符号表 / 调试文件 | 按需 | — | 单独归档，不进安装包 |
