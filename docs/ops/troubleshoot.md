<!-- 出处: GitLab runbooks https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md（Recommended structure：Symptoms → Pre-checks → Resolution → Post-checks）；PagerDuty Incident Response https://response.pagerduty.com/（After an Incident / Postmortem）；Google SRE ch.11 https://sre.google/sre-book/being-on-call/（无责复盘）。 -->

# galleryvault 排障 runbook

> 每个现象一篇，固定五段：现象 → 前置检查 → 处置 → 处置后核对 → 回滚。生成于 2026-11-20，之后由项目自己维护。

## 1 用法

<!-- 出处: GitLab runbooks https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md（给链接、写清期望、别让人临场推理） -->

- 先按 §2 索引定位现象，再跳到对应小节；索引里没有的，新增一节并回填索引。
- 每段只写能执行的动作与可核对的期望值；不写“检查一下”这种无法判定的指令。
- 处置前记录：现象、开始时间、版本、影响面、已做操作。改配置前先备份。
- 影响面扩大、或 30 分钟无进展：按 `README.md` 的升级路径叫人，不并行试错。

## 2 现象索引

<!-- 出处: 本仓设计，无外部依据（现象索引表字段）；“先按现象定位”参考 GitLab runbooks https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md（Symptoms） -->

| 现象 | 先看 | 常见根因 | 危险度 |
|---|---|---|---|
| <服务起不来> | §3.1 | <端口/配置/依赖> | 高 |
| <页面打不开> | §3.2 | <网络/反代/证书> | 中 |
| <数据不入库> | §3.3 | <链路/权限/队列> | 高 |
| <时间不同步> | §3.4 | <时源/防火墙> | 中 |
| <空间不足> | §3.5 | <日志/归档> | 中 |

## 3 单篇模板

<!-- 出处: GitLab runbooks https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md（五段式：Symptoms / Pre-checks / Resolution / Post-checks / Rollback 可选） -->

每篇都按下面五段写，段名不改，便于搜索与交接。

### 3.x <现象一句话>

#### 现象

- 用户看到什么、日志里出现什么、从何时开始。
- 影响范围：<单机 / 全部 / 仅某形态>。

#### 前置检查

| 检查 | 期望值 | 怎么查 |
|---|---|---|
| <服务状态> | 运行中 | <命令或页面> |
| <端口/连通性> | 可连接 | <命令> |
| <版本与最近变更> | 与记录一致 | <版本查询 + 变更记录> |

#### 处置

1. <动作一>；期望：<看到什么>。
2. <动作二>；期望：<看到什么>。
3. 仍不恢复：<升级路径或下一步>。

#### 处置后核对

- <关键流程跑通一次>。
- <无新增持续错误日志>。
- <相关监控/告警恢复正常>。

#### 回滚

- 本处置改过配置或版本时：按 `upgrade.md` §5 还原，并记录回滚点。
- 只读排查未改动时：写“无需回滚”，并说明依据。

## 4 升级失败兜底

<!-- 出处: 本仓设计，无外部依据（升级失败兜底：按现象判断停点，再决定重试或回滚） -->

| 现象 | 先判断 | 处置 |
|---|---|---|
| 升级后服务不起 | 版本号、日志首行错误 | 修配置重试一次；仍失败回滚 |
| 升级后数据缺失 | 迁移日志、备份条数 | 停止写入，按 `backup.md` 恢复 |
| 升级卡在固定进度 | 是否有写入、磁盘余量 | 等 5 分钟；无写入则按续做表 |
| 回滚后仍异常 | 旧配置是否还原、数据是否回灌 | 用备份整体恢复到升级前 |

## 5 记录与复盘

<!-- 出处: PagerDuty Incident Response https://response.pagerduty.com/（After an Incident / Postmortem Template）；Google SRE ch.11 https://sre.google/sre-book/being-on-call/（无责复盘） -->

- 事件结束后 24 小时内记录：时间线、根因、处置、影响面、后续动作。
- 复盘只对流程与系统，不追责个人；每条后续动作要有责任人与期限。
- 同一现象第二次出现：把处置步骤补进对应小节，不留在个人笔记里。

## 6 修订记录

<!-- 出处: NUCATS《Writing Standard Operating Procedures》https://nucats.northwestern.edu/docs/cecd/writing-sops-and-templates.pdf 第 8 页 Revision History 表（Revision / Date / Description of changes / Requested By） -->

| Rev | 日期 | 变更摘要 | 提出人 |
|---|---|---|---|
| 1 | 2026-11-20 | 初版骨架 | <角色> |
