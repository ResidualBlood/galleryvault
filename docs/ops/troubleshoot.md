# GalleryVault 排障

> 摘要 + 入口；常见问题的定位与排错见 wiki [常见问题](../wiki/FAQ.md)（中英：`FAQ-EN.md`）。

## 先看这些

- **健康**：`GET /healthz` 返回 `{status:"ok"}`，DB 不可达时 `503`（`backend/galleryvault/app/routers/core.py:18`）。
- **指标**：`GET /metrics` 返回 Prometheus 文本（请求/错误计数）。
- **日志**：容器内 `docker compose logs -f`；应用内 日志页 可在线调级（DEBUG/INFO/WARNING/ERROR）与导出 `galleryvault.log`（见 wiki [库维护](../wiki/Manage.md#日志页logs)）。
- **Cookie 状态**：顶栏 Cookie 健康横幅；`GET /api/settings/cookie-health`。

## 常见现象速查

| 现象 | 先看 | 参考 |
| :--- | :--- | :--- |
| 登录失败/429 | 登录退避（管理员 5 次起、每 IP 10 次/分） | wiki [FAQ](../wiki/FAQ.md) |
| 下载暂停不恢复 | 配额挑战 302 / 429 / 509，探针每 10 分钟 | wiki [功能特性 §4](../wiki/Features.md#4-下载) |
| 在线页无结果/被墙 | Cookie 失效 / 配额耗尽 / IP 封禁，分别提示 | wiki [画廊库](../wiki/Library.md#在线浏览online) |
| 扫描把整库移进回收站 | 扫描根离线被误判，跳过「扫描失踪」标记 | [dev/pitfalls](../dev/pitfalls.md) |
| DB 认证失败 | asyncpg SCRAM 与 conftest 提速冲突 | [dev/pitfalls](../dev/pitfalls.md) |

## 完整排查

见 wiki [常见问题](../wiki/FAQ.md) 与 [部署指南](../wiki/Deployment.md)（网络与反代拓扑、权限）。
