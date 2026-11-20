# galleryvault 数据模型与错误码

<!-- 出处: docs/PROJECT_INIT-templates-research.md §R-api -->

> 端点清单见 [README.md](README.md)；这里只写跨端点共用的数据模型与错误体，字段落地以 yaml 的 `components` 为准。生成于 2026-11-20，之后由项目自己维护。

<!-- 来源: OpenAPI 3.1.1 components（schema 容器，https://spec.openapis.org/oas/v3.1.1.html#components-object）+ 本仓设计，无外部依据（时间/分页/排序的命名约定） -->

## 1 数据模型

| 模型 | 用途 | 关键字段 | 字段口径来源 |
|---|---|---|---|
<!-- 例：<Device> | <端点返回的资源> | id / name / status | docs/reference/data-dictionary.md -->

- 字段类型与必填在 yaml 的 schema 里定义；本表只列“读接口的人最常问的字段”。
- 时间字段统一：<ISO 8601 带时区 / epoch 秒>；单位与精度见数据字典。
- 分页、排序、筛选的参数名全服务统一，写清一次，不在每个端点重复。

<!-- 来源: Zalando RESTful API Guidelines §176（MUST support problem JSON，https://opensource.zalando.com/restful-api-guidelines/#176）+ RFC 9457 Problem Details（2023-07，字段 type/title/status/detail/instance，https://www.rfc-editor.org/rfc/rfc9457.html） -->

## 2 错误体

错误响应统一用 RFC 9457 的 Problem Details（`application/problem+json`）；项目自定义字段只能作为扩展：

```json
{"type": "/problems/<稳定 slug>", "title": "<简短标题>", "status": 400, "detail": "<人能读的一句话>", "instance": "/<请求路径>", "trace_id": "<请求追踪号，可选>"}
```

- `type` 是稳定的问题类型标识，发布后不改；`title` 面向人、可改文案；`detail` 只放补充说明，不塞长日志；`instance` 指向本次请求。
- `trace_id` 是本仓扩展字段（RFC 9457 与 Zalando §176 都没有该字段），默认按项目需要决定是否填、是否必填；不要把它写成协议强制要求。
- 返回 4xx/5xx 时以 Problem Details 为准，客户端不得只解析 `title`。

<!-- 来源: 本仓设计，无外部依据（错误码表）；HTTP 状态码语义见 RFC 9110 §15（https://www.rfc-editor.org/rfc/rfc9110.html#name-status-codes），逐端点错误响应要求见 Zalando §151 -->

## 3 错误码表

| HTTP | code | 含义 | 客户端该做什么 |
|---|---|---|---|
<!-- 例：401 | auth_required | 未登录/会话过期 | 跳登录，保留原路径 -->

- 校验失败必须指出哪个字段；批量接口逐项返回，部分失败也返回 200 以外的明确码。
- 不在表里的码不许临时现造；新增先改本表与 yaml，再改代码。
