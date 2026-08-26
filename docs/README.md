# GalleryVault

GalleryVault 是一个私有、自托管的本地画廊库管理器。它将 Ehviewer 导出目录、CBZ/CBR 压缩包与普通图片文件夹索引为可搜索的 Web 画廊库，并可选地从 ExHentai 同步标签与元数据、下载画廊、监控收藏文件夹以及翻译标签。支持 **中文 / English** 双语界面。

## 功能特性

- **本地画廊库**：扫描 Ehviewer 导出目录、CBZ/CBR 文件与普通图片文件夹，建立持久化、可搜索的索引（PostgreSQL）。
- **标签云与搜索**：带命名空间的标签体系、词频加权标签云与即时标签自动补全。
- **标签翻译**：自动获取最新 [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database) 数据库，中文输入反向匹配翻译表。
- **双语界面**：完整的中文与 English 界面；中文界面下标签显示翻译（多值标签只显示翻译部分）。
- **ExHentai 集成**：使用自有 cookie 获取每个画廊的元数据、分类与标签。
- **下载管理**：类似 Ehviewer 的并发分页下载、实时进度、可续传重试、部分下载（`max_pages`）、取消与批量重试。
- **日志页面**：统一展示后台任务（扫描/标签同步/缩略图/收藏元数据）进行中与已完成状态，可取消。
- **收藏夹监控与管理**：监控十个 ExHentai 收藏文件夹自动下载、独立列表、查重扫描与忽略误报。
- **阅读器与历史**：逐页流式加载、键盘/空格/点击翻页、自动跳转下一画廊、自动保存阅读位置。
- **Telegram 通知**：下载、扫描、收藏同步时发送通知。
- **安全与隐私**：PBKDF2 认证、按真实 IP 的登录限速、跨域校验与域名白名单、可选的静态加密（AES-256-GCM）、非 root 运行。

## 快速开始

```bash
git clone https://github.com/ResidualBlood/galleryvault.git
cd galleryvault
docker compose up -d
```

打开 `http://<host>:8000`，使用默认密码 `p1a2s3s4` 登录（登录后请立即在设置中修改）。详见 [部署](deployment.md)。

## 文档导航

- **[部署](deployment.md)** — compose 部署、数据目录、容器名、只读库挂载、安全加固
- **[使用指南](usage.md)** — 浏览、阅读器、标签、下载、收藏夹、日志、设置
- **[备份与恢复](backup.md)** — pg_dump 备份脚本与恢复
- **[静态加密](encryption.md)** — ENCRYPTION_KEY 加密与密钥丢失恢复
- **[API 参考](api.md)** — 完整 REST API
- **[开发指南](development.md)** — 架构、项目布局、开发约定
- **[常见问题](faq.md)** — 排查与技巧
