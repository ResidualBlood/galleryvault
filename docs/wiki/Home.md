# GalleryVault

> 中文 · [English](Home-EN)

GalleryVault 是私有、自托管的本地画廊库：文件和收藏留在你的机器上，不把库交给别人。

把 Ehviewer 导出目录、CBZ/CBR 与图片文件夹编成可搜索的 Web 库；可选从 ExHentai 同步标签与元数据、下载画廊并监控收藏。阅读、搜索、标签云与标签翻译同在中英界面，Docker Compose 即可部署。

## 快速开始

```bash
mkdir galleryvault && cd galleryvault
curl -fsSL https://raw.githubusercontent.com/ResidualBlood/galleryvault/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

1. 执行 `docker compose up -d` 启动容器服务。
2. 打开 `http://<host>:8000` 访问 Web 界面。
3. 使用默认密码 `p1a2s3s4` 登录并在「设置」中修改密码。
4. 将画廊放入 `./library` 挂载目录，点击「扫描库」即可开始使用。

> **使用流程**：推荐按「先缓存收藏元数据 → 扫描库 → 查重 → 批量/增量下载」顺序使用，详见 **[使用指南：推荐使用流程](Usage#推荐使用流程)**。  
> **兼容格式**：支持 Ehviewer 全系客户端目录、JHenTai、CBZ/CBR 等格式，详见 **[兼容性与适用范围](Compatibility)**。

## 文档导航

- **用户指南**：
  - **[使用指南](Usage)** — 浏览与多标签搜索、在线阅读器、下载管理、收藏夹监控与查重、回收站、PWA 与系统设置
  - **[功能特性](Features)** — 核心功能详解与设计特点
  - **[界面截图](Screenshots)** — 各主要页面中英文界面一览
  - **[常见问题](FAQ)** — 常见问题解答与排错建议
- **运维与部署**：
  - **[部署指南](Deployment)** — Docker Compose 部署、目录挂载与权限配置、反向代理 TLS、安全加固与升级
  - **[备份与恢复](Backup)** — 数据库与配置的一键备份与恢复方案
  - **[静态加密](Encryption)** — 敏感凭据 AES-256-GCM 静态加密与密钥丢失恢复
- **API 与开发**：
  - **[API 参考](API)** — REST API 完整接口规范与 OpenAPI 定义
  - **[开发指南](Development)** — 项目架构、前后端源码布局与测试规范

## License

[MIT](https://github.com/ResidualBlood/galleryvault/blob/main/LICENSE)。
