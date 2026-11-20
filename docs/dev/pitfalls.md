<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-dev；TGDP troubleshooting 模板 https://gitlab.com/tgdp/templates/-/blob/main/troubleshooting/template_troubleshooting.md （2026-11-20 实读该文件：`## Symptom` / `### Cause N of symptom N` / `### Solution or workaround to cause N of symptom N` / `### For more information`） -->
# 踩坑记录

> 每次踩坑后追加一行；只写能复用的排查路径，不贴长日志。

## 记录格式

<!-- 来源: dev/handbook/14 坑；TGDP troubleshooting（Symptom→Cause→Solution or workaround→For more information，同文件级 URL） -->

| 现象 | 原因 | 排查顺序 | 规避 |
|---|---|---|---|

填写要求：

- 现象写“能看到什么”（报错原文、截图路径、日志关键行），不写推断。
- 排查顺序写可复现的步骤编号，写清“看到什么就排除什么”。
- 规避写“下次怎么做”，能落到检查命令或模板的优先写命令。

## 排查前置条件

<!-- 来源: TGDP how-to 模板 https://gitlab.com/tgdp/templates/-/blob/main/how-to/template_how-to.md （`## Before you start` 先写前置条件） -->

- 需要的最小环境：`<版本 / 设备 / 数据>`。
- 需要先确认的日志位置：`<路径>`。
- 无法复现时：记录时间、版本、提交号，标“未复现”。

## 常见坑示例（可选）

<!-- 出处: 本机参考项目 docs/dev/handbook/14-pitfalls.md:5-20、24-36、38-100、102-108、117-159、209-227（通用化，见调研 §R-constraints） -->

删除或改写为项目实际遇到的坑；没有对应条件的不要保留。

| 现象 | 常见原因 | 先查什么 | 规避 |
|---|---|---|---|
| 偶发死锁、竞争告警，状态写晚提交 | 两把锁获取顺序不一致，持锁做 IO | 锁顺序是否有单一写法、IO 是否在锁外 | 锁顺序写进规格并加用例；持锁只做快照与决策 |
| 时序测试偶发慢或偶发失败 | 用固定等待兜底同步 | 新增 `sleep`、超长超时 | 用通道、条件轮询、假时钟；白名单只减不增 |
| 契约、生成物、文档三边不一致 | 有人手改了生成物或下游副本 | 生成物是否由源生成 | 生成物一律不手改；`--check` 进钩子与 CI |
| 单测过、运行时报规格不一致 | 生成/嵌入副本没同步 | 每份副本的生成命令 | 改源后重跑生成，生成物与源同批提交 |
| 打包版本静默变成默认值 | 打包未显式传版本 | 包名、包内版本文件、关于页 | 打包命令显式带版本，出包后三处核对 |
| 本机跑测试把机器卡死 | 并发拉满、改公共页面牵出大量用例 | worker 上限、是否同时开多组 E2E | 限并发，只跑目标文件或串行 |
| 调用链靠超时换绿 | 等真实数据落库、反复放大超时 | 用例是否确定性造数 | 预置数据 + 有界条件等待，找根因 |
| 文档或注释里的路径不存在 | 目录已搬迁，断链检查扫不到代码注释 | 路径是否真实存在 | 写前先 `ls`；断链检查覆盖代码注释 |

## 相关链接

<!-- 来源: TGDP troubleshooting（文末 `### For more information` 串联相关文档，同文件级 URL） -->

- 架构与数据流见 [architecture.md](architecture.md)。
- 配置项与默认值见 [config.md](config.md)。
- 测试数据的构造与回放见 [testdata.md](testdata.md)。
