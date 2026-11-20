<!-- 出处: GitLab runbooks https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md（Adding runbooks rules → Recommended structure / Checklists）；PagerDuty Incident Response https://response.pagerduty.com/（Before / During / After an Incident）；Google SRE ch.11 https://sre.google/sre-book/being-on-call/（清晰升级路径、事件流程、无责复盘）。 -->

# galleryvault 运维手册

> 首次部署前先读本文件，再按需进入分册：安装、升级与回滚、备份、排障。生成于 2026-11-20，之后由项目自己维护。

## 1 怎么用

<!-- 出处: GitLab runbooks https://gitlab.com/gitlab-com/runbooks/-/raw/master/README.md（Recommended structure：五段式、写清期望、给链接）；Google SRE ch.11 https://sre.google/sre-book/being-on-call/（清晰升级路径、事件处理流程、无责复盘） -->

| 你要做的事 | 先读 | 再读 |
|---|---|---|
| 首次部署 | 本文件 §2 装机前准备 + §3 网络与时序 | `install.md` |
| 升级或回退 | 本文件 §2 回滚预案 | `upgrade.md` |
| 备份或恢复 | 本文件 §2 备份对象 | `backup.md` |
| 出故障 | 本文件 §5 排障入口 | `troubleshoot.md` |

- 每篇排障按五段写：**现象 → 前置检查 → 处置 → 处置后核对 → 回滚**；写清期望值，不让人临场推理。
- 值班前置：确认升级路径（找谁）、事件流程（先做什么）、复盘要求（事后写什么）三样都在。

## 2 装机前准备

<!-- 出处: 本仓设计，无外部依据（装机前准备表）；回滚预案字段参考 KEP https://raw.githubusercontent.com/kubernetes/enhancements/master/keps/NNNN-kep-template/README.md（Rollout, Upgrade and Rollback Planning） -->

| 项 | 要求 | 怎么核对 |
|---|---|---|
| 版本与资产 | 与 `product/changelog.md` 的发布资产一致 | 文件名 + 校验值 |
| 环境 | <供电、空间、温度、网络出口> | 现场核对表 |
| 依赖 | <数据库、消息、对时源、证书> | 逐项连通性测试 |
| 账号与权限 | 安装账号、服务账号、备份账号分离 | 实际登录验证 |
| 回滚预案 | 旧版本与旧配置可恢复；备份已验证可读 | 演练一次恢复 |
| 窗口 | 停机时长、通知对象、谁在岗 | 与用户方确认 |

没有可用的回滚预案就不开始升级；只能前进不能后退的变更先写决策记录。

## 3 网络、对时与传输

<!-- 出处: 本仓设计，无外部依据（网络、对时、传输的通用检查表） -->

| 项 | 取值/要求 | 核对命令或位置 |
|---|---|---|
| 地址与端口 | <网段、端口清单> | <连通性测试> |
| 对时 | <NTP 源、允许偏差> | <时间比对> |
| 文件传输 | <协议、账号、目录、权限> | 上传下载各一次 |
| 对外访问 | <HTTPS/证书有效期> | 浏览器与证书检查 |

变更网络或对时前先备份配置；对时偏差超阈值时先排时源，不改业务参数。

## 4 备份与恢复

<!-- 出处: 本仓设计，无外部依据（备份与恢复只在此做入口，细节见 backup.md） -->

- 备什么、存哪、保留多久、怎么验证：见 [`backup.md`](backup.md)。
- 恢复演练至少一次；未演练过的备份视为不可用。

## 5 升级与回滚

<!-- 出处: KEP https://raw.githubusercontent.com/kubernetes/enhancements/master/keps/NNNN-kep-template/README.md（Upgrade / Downgrade Strategy）；“业务流程运行中不升级”为本仓设计（经验约束，未核实为外部标准） -->

- 升级事务步骤、中断续做、回滚与升级后核对：见 [`upgrade.md`](upgrade.md)。
- 业务流程运行中不升级；升级前必备份与版本记录。

## 6 卸载与空间

<!-- 出处: 本仓设计，无外部依据（卸载与空间回收的顺序） -->

| 项 | 动作 | 注意 |
|---|---|---|
| 卸载服务 | 停服务、移出开机自启 | 先导出数据与配置 |
| 保留数据 | <保留目录与期限> | 删除前二次确认 |
| 空间不足 | 清理顺序：日志 → 临时文件 → 历史归档 | 不删正在写入的文件 |

## 7 排障入口

<!-- 出处: PagerDuty Incident Response https://response.pagerduty.com/（During an Incident：先记录现象与已做操作、按升级路径找人）；Google SRE ch.11 https://sre.google/sre-book/being-on-call/ -->

- 先看 [`troubleshoot.md`](troubleshoot.md) 的现象索引；索引里没有的再新建一篇。
- 排障时先记录：现象、时间、版本、已做操作；改任何配置前先备份。
- 影响面扩大或 30 分钟无结论：按升级路径找人，不并行试错。

## 8 运维日历

<!-- 出处: 本仓设计，无外部依据（运维日历的周期与记录项为建议，由项目按实际来源填写） -->

| 周期 | 做什么 | 记录 |
|---|---|---|
| 每日 | 看告警、看容量与备份结果 | <记录位置> |
| 每周 | 核对备份可读、检查证书与时间同步 | <记录位置> |
| 每月 | 演练一次恢复或回滚 | <记录位置> |
| 每版 | 更新本目录与 `product/changelog.md` | 修订记录 |

## 9 修订记录

<!-- 出处: NUCATS《Writing Standard Operating Procedures》https://nucats.northwestern.edu/docs/cecd/writing-sops-and-templates.pdf 第 8 页 Revision History 表（Revision / Date / Description of changes / Requested By） -->

| Rev | 日期 | 变更摘要 | 提出人 |
|---|---|---|---|
| 1 | 2026-11-20 | 初版骨架 | <角色> |
