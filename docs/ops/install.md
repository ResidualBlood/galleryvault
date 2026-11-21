# GalleryVault 安装与部署

> 摘要 + 入口；完整步骤、存储拓扑、权限与性能调优见 wiki [部署指南](../wiki/Deployment.md)（中英：`Deployment-EN.md`）。

## 快速开始（docker compose）

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

- 访问 `http://<主机IP>:8000`；默认密码 `p1a2s3s4`（登录后进入 `#/welcome`，首次必须改密）。
- 数据目录：`./library`、`./downloads`、`./db-data`、`./cache`。

## 部署要点

- **挂载**：把宿主机 Ehviewer 目录挂到 backend 容器（例 `/data/Ehviewer:/Ehviewer:ro`），再到 设置 → 资料库 添加库根。
- **权限**：可设 `PUID`/`PGID` 降权运行；PostgreSQL 数据目录 uid 999，勿 chown。
- **冷归档**：挂载归档卷 + 在设置里配 `archive_roots`（容器内路径，每行一个）。
- **代理/信任**：`TRUSTED_PROXIES` 配反代信任网段；`http_proxy`/`socks5_proxy` 二选一。
- **多架构**：AMD64 + ARM64 双架构镜像。

## 详细参考

- 完整 Compose 配置、存储拓扑、性能调优、修复脚本：[部署指南](../wiki/Deployment.md)。
- 配置项默认值与出处：[dev/config](../dev/config.md)。
- 兼容格式与目录拓扑：[兼容格式](../wiki/Compatibility.md)。
