# 兼容性与适用范围

> 中文 · [English](Compatibility-EN)

GalleryVault 专注于管理本地画廊归档，优先支持主流客户端的导出格式并提供高保真度元数据解析。

## 优先支持：Ehviewer 家族客户端

本项目**首要面向 [Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ) 下载的画廊**：
- **目录结构**：`<gid>-<标题>/` 图片文件夹 + `.ehviewer` 元数据文件。
- **元数据格式**：SpiderInfo VERSION1 / VERSION2，包含画廊 gid、token 与每页 pToken。扫描器据此精确还原画廊身份与在线关联。

`.ehviewer` 格式源自 Hippo Seven 的 EhViewer（`com.hippo.ehviewer.spider.SpiderInfo`），**同源客户端写出的格式完全兼容**，可直接入库：

- **EhViewer 原版**（[seven332/EhViewer](https://github.com/seven332/EhViewer)，已停止维护）。
- **主流活跃分支**：
  - [**FooIbar/EhViewer**](https://github.com/FooIbar/EhViewer)（MD3）
  - [**Ehviewer-Overhauled/Ehviewer**](https://github.com/Ehviewer-Overhauled/Ehviewer)
  - [**EhViewer-NekoInverter/EhViewer**](https://github.com/EhViewer-NekoInverter/EhViewer)
  - [**exzhawk/EhViewer**](https://github.com/exzhawk/EhViewer)
  - [**AdNotFound/EhViewer**](https://github.com/AdNotFound/EhViewer)
  - [**WarnError/Ehviewer-NekoWhite**](https://github.com/WarnError/Ehviewer-NekoWhite)
  - [**NotFaceGUI/EhViewer-Auto-Translation-Ver**](https://github.com/NotFaceGUI/EhViewer-Auto-Translation-Ver)
  - [**axlecho/MHViewer**](https://github.com/axlecho/MHViewer) 等分支
- **跨平台移植**：
  - [**EhViewer-Apple**](https://github.com/felixchaos/EhViewer-Apple)（iOS / macOS）
  - [**Ehviewer_OHOS**](https://github.com/suibianqwe/Ehviewer_OHOS)（鸿蒙）
- **周边生态工具**：
  - [**LRReader**](https://github.com/Xslx98/LRReader)（Android · LANraragi 客户端）
  - [**exhentai-manga-manager**](https://github.com/SchneeHertz/exhentai-manga-manager)
  - [**ehviewer_manga_manager**](https://github.com/Schweik7/ehviewer_manga_manager)（Python CLI）
  - [**LANraragi**](https://github.com/Difegue/LANraragi) 的 `Ehviewer.pm` 元数据插件

## 其它格式支持

- **[JHenTai](https://github.com/jiangtian616/JHenTai)**（全平台 Flutter，Android / iOS / Windows / macOS / Linux）：
  - **原生支持**其下载目录：`<gid> - <标题>/` + `metadata` JSON。
  - 扫描直接还原完整身份（gid、token、标签、分类、发布时间）。如遇个别版本的解析异常，欢迎附带样例 `metadata` 提交 issue。
- **降级支持**：
  - **无 `.ehviewer` 的 `<gid>-<标题>` 图片文件夹**：仅可识别 gid。
  - **CBZ / CBR 压缩包**：需在文件名开头包含 gid（如 `123456-标题.cbz`）。
  - **无 gid 的纯画廊**：可作为本地画廊正常浏览与阅读，但**无法参与在线更新、下载比对与收藏夹查重**。
- **Sidecar 元数据**：
  - GalleryVault 下载器在落盘时会生成 `.galleryvault.json`（分类、标题、标签）辅助文件，重新扫描与重建时可直接读取。
