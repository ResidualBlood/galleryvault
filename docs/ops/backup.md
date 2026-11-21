# GalleryVault 备份与恢复

> 摘要 + 入口；完整备份对象、恢复步骤、密钥保管见 wiki [备份与恢复](../wiki/Backup.md)（中英：`Backup-EN.md`）。

## 要备份什么

| 对象 | 位置（容器/卷） | 说明 |
| :--- | :--- | :--- |
| PostgreSQL 数据 | `./db-data` | 索引、收藏关系、进度、任务、配置（含持久化会话密钥） |
| 画廊文件 | `./library`、`./downloads`、归档根（`archive_roots`） | 本机/NAS 上的实际文件 |
| 缩略图缓存 | `./cache` / `thumbnail_cache_dir` | 可重建，可选 |
| 密钥 | `ENCRYPTION_KEY`（静态加密）、会话签名密钥（DB 内） | 密钥丢失 = 加密字段不可解，见 wiki [静态加密](../wiki/Encryption.md) |

## 备份/恢复

- 数据库：`pg_dump`/`pg_restore`（或 compose 里对应卷）；备份文件路径生产见 HANDOFF（`gv-pre-*.dump`）。
- 生产变更前先做 DB 备份再迁移（见 [dev/pitfalls](../dev/pitfalls.md)「生产 compose 跟 :dev」）。
- 完整命令与密钥保管规则见 wiki [备份与恢复](../wiki/Backup.md)。

## 相关

- 发布/回滚顺序：[dev/release](../dev/release.md)。
- 归档备份（冷库）与恢复语义：[库维护](../wiki/Manage.md#冷库归档archive)。
