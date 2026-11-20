# galleryvault API 对照

<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-api -->

> 本文件是“接口规格 ↔ 实现”的对照入口；`*.yaml` 里的 OpenAPI 是机读唯一来源，这里只写人读摘要与一致性核对。生成于 2026-11-20，之后由项目自己维护。

<!-- 来源: OpenAPI 3.1.1 Info Object（https://spec.openapis.org/oas/v3.1.1.html#info-object）+ 本仓设计，无外部依据（维护者/最后核对两列） -->

## 1 文档头

| 项 | 值 |
|---|---|
| 规范版本 | OpenAPI 3.1.1 |
| 服务版本 | <语义化版本，如 1.4.0> |
| 维护者 | <角色或人> |
| 最后核对 | 2026-11-20 |
| 机读文件 | <`docs/api/<service>-api.yaml`> |
| 权限文档 | `docs/reference/security-permissions.md` |

维护者必须能回答“谁改接口谁改这份文件”；不一致时以 yaml 与代码为准，并回头修本文。

<!-- 来源: OpenAPI 3.1.1 Server Object（https://spec.openapis.org/oas/v3.1.1.html#server-object） -->

## 2 环境地址

| 环境 | Base URL | 用途 | 备注 |
|---|---|---|---|
| 本机 | <http://127.0.0.1:PORT> | 开发自测 | 只监听回环 |
| 现场 | <http(s)://host:port> | 部署后访问 | <是否 HTTPS/证书来源> |

地址变更属于配置，按 `docs/dev/conventions.md` 的配置约定登记，不散落在接口说明里。

<!-- 来源: Zalando §225 的 scope 命名（`<application-id>.<resource-name>.<access-mode>`，https://opensource.zalando.com/restful-api-guidelines/#225）；本模板改用 `<资源>:<动作>` 属本仓设计，无外部依据 -->

## 3 鉴权与 scope 命名

- 认证方式：<会话 Cookie / Bearer Token / mTLS；写清有效期与刷新方式>。
- scope 命名：`<资源>:<动作>`（如 `<device>:read`、`<config>:write`），全小写，不含版本号；这是本模板的约定，不声称与 Zalando 点分格式一致。
- 每个端点必须声明的权限点写在第 4 节 `权限` 列，与 `docs/reference/security-permissions.md` 的矩阵同名。
- 未授权返回码与错误体见 [models.md](models.md)；不得用 200 + 业务错误码代替。

<!-- 来源: OpenAPI 3.1.1 Paths Object（https://spec.openapis.org/oas/v3.1.1.html#paths-object）；端点表列（风险级/幂等/权限点）为本仓设计，无外部依据 -->

## 4 端点表

一条端点一行；风险级与幂等决定能否重试与是否需要确认弹窗。

| 方法 | 路径 | 说明 | 风险级 | 幂等 | 权限点 |
|---|---|---|---|---|---|
<!-- 例：GET | /api/<资源> | <一句话> | 只读 | 是 | <资源>:read -->

- 风险级只用四档：`只读`、`写`、`高危`、`内部`。`高危` 必须同时出现在确认白名单里。
- 查询参数与请求体字段不在本表展开，写在 yaml 的 operation 与 schema 中。

<!-- 来源: Zalando 弃用与版本章节（https://opensource.zalando.com/restful-api-guidelines/，deprecation/compatibility 两章）；语义化版本见 https://semver.org/ -->

## 5 版本与废弃

- 服务版本用语义化版本；破坏性变更升主版本，新增可选字段升次版本，修 bug 升补丁。
- 废弃：先标 `deprecated: true` 并在响应头/变更说明里给出替代端点与下线日期，观察期结束后才删。
- 旧版本仍在线时在本节保留一行“版本 / 下线日期 / 替代端点”。

<!-- 来源: 本仓设计，无外部依据（覆盖表与 CI diff 的做法） -->

## 6 一致性核对

机读 yaml、实现代码与本表必须同源；核对做成可重复执行的动作，不靠记忆。

| 检查 | 做什么 | 何时跑 | 失败怎么办 |
|---|---|---|---|
| 覆盖 | yaml 的每条 path+method 在代码里有且仅有一个实现 | 每次改接口 | 补实现或删 yaml 条目 |
| 反向覆盖 | 代码里的路由都能在 yaml 找到 | 每次改接口 | 补文档，不允许“先上后补” |
| 差异 | 生成物与提交内容比对，不一致即失败 | CI | 重新生成并提交 |
| 权限 | 端点权限点与权限矩阵一致 | 改权限时 | 先改矩阵再改端点 |

未接入 CI 的项目写“手工跑什么命令”；没跑过的检查不写进“已通过”。

<!-- 来源: OpenAPI 3.1.1 External Documentation Object（https://spec.openapis.org/oas/v3.1.1.html#external-documentation-object） -->

## 7 外部资料

- 对外说明页：<URL 或“无”>
- 现场对接文档：<URL 或“无”>
- 只放链接与一句话用途；凭据、Token、内网口令不写在这里。

<!-- 来源: 用户要求 2026-11-20（凡是有通讯的项目都要有通讯协议文档）；链路分类与两处同步做法为本仓设计，无外部依据 -->

## 8 接口总览：全部链路

项目所有对外/对下接口按传输类型分两处登记；本目录只收 HTTP/REST（OpenAPI）。

| 链路类型 | 文档位置 | 机读来源 |
|---|---|---|
| HTTP / REST | 本目录 `docs/api/README.md` 与各 `docs/api/<service>-api.yaml` | OpenAPI 3.1.1 |
| UART / RS485 / CAN / Modbus（RTU/TCP） | `docs/protocol/README.md` 链路总表 + 每条 `<短名>.md` | `docs/protocol/registers.yaml`（寄存器/命令） |
| TCP / UDP 自定义帧 | `docs/protocol/README.md` 链路总表 + 每条 `<短名>.md` | 无固定机读格式，以链路文件字段表为准 |
| WebSocket 自定义消息 / MQTT | `docs/protocol/README.md` 链路总表 + 每条 `<短名>.md` 的“消息类型表” | 消息表或 schema 文件路径 |
| IEC 61850 / gRPC / IPC / 私有口 | `docs/protocol/README.md` 链路总表 + 每条 `<短名>.md` | ICD/CID、proto、报文定义路径 |

- 纯 HTTP/REST 不建 protocol 链路文件；有自定义帧的非 HTTP 通讯不写在本目录，避免两套契约打架。
- `docs/protocol/` 与 `docs/reference/` 可能未启用：路径用纯文本，不写 Markdown 链接；确认启用后再改成本地链接。
- 新增链路时两处同步：本表加一行，`docs/protocol/README.md` 链路总表加一行。
