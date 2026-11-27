# GalleryVault 运维文档

> 部署、备份、升级、排障的入口。用户向完整说明在 wiki（中英成对），本目录只做摘要 + 链接，不复制内容。

| 文档 | 回答什么 | 对应 wiki |
| :--- | :--- | :--- |
| [install.md](install.md) | 首次部署与 Compose 配置 | [部署指南](../wiki/Deployment.md) |
| [upgrade.md](upgrade.md) | 升级、发版与回滚 | [部署指南](../wiki/Deployment.md) + [dev/release](../dev/release.md) |
| [backup.md](backup.md) | 数据库备份与恢复、密钥保管 | [备份与恢复](../wiki/Backup.md) |
| [troubleshoot.md](troubleshoot.md) | 常见问题定位 | [常见问题](../wiki/FAQ.md) |

## 快速入口

- 环境与端口（测试/生产）：项目根 `AGENTS.md`「环境与端口」。
- 最短命令与测试栈生命周期：skill `galleryvault-maintenance`。
- 生产操作授权：默认不动生产，人授权才 SSH/改 compose/pull/restart（AGENTS.md 铁律）。
- 生产远程：SSH 入口与口令见 AGENTS.md「环境与端口」+ HANDOFF.md §1（本地、gitignore）。

## 相关

- 静态加密与密钥职责：[wiki 静态加密](../wiki/Encryption.md)。
- 后端 API/开发：`backend/docs/API.md`、`backend/docs/DEVELOPMENT.md`。
- 计划与状态：[plan/STATUS](../plan/STATUS.md)。
