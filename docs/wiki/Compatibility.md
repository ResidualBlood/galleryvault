# 兼容性与格式规范

> **中文** · [English](Compatibility-EN)

GalleryVault 专注于管理本地数字画廊资产归档，优先深度支持主流移动客户端的导出格式，并提供高保真度元数据解析。

---

## 客户端支持矩阵

| 客户端 / 生态工具 | 支持级别 | 元数据识别方式 | 说明 |
| :--- | :--- | :--- | :--- |
| **Ehviewer_CN_SXJ** | 原生推荐 | `.ehviewer` (SpiderInfo V1/V2) | 本项目目录结构与元数据标准的基准参考实现 |
| **FooIbar / EhViewer (MD3)** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 原生读取与索引，完美还原画廊与各页元数据 |
| **Ehviewer-Overhauled** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 结构完全同源，直接挂载即可扫库 |
| **EhViewer-NekoInverter / NekoWhite** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 原生识别，支持全量标签与分类入库 |
| **axlecho / MHViewer** 等分支 | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 导出格式完全兼容 |
| **EhViewer-Apple (iOS / macOS)** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 移动端导出目录直接挂载入库 |
| **Ehviewer_OHOS (鸿蒙)** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 导出格式完全兼容 |
| **JHenTai (Flutter 全平台)** | 完整支持 | `metadata` (JSON 格式) | 原生自动识别 JSON 字段，还原分类、标签与时间 |
| **Tachiyomi / Mihon / Panels** | 协议接入 | OPDS 目录协议 (`/api/opds`) | 通过 HTTP Basic 认证直接接入画廊书库浏览阅读 |
| **通用 CBZ / CBR 压缩包** | 标准支持 | `ComicInfo.xml` / 文件名前缀 | 支持 `gid-标题.cbz` 或内部内嵌元数据解析 |

---

## 标准目录组织拓扑

GalleryVault 支持多层级挂载与灵活的资产组织。典型的目录拓扑结构如下：

```
/library (或自定义挂载根目录)
├── 123456-画廊标题A/
│   ├── .ehviewer                  # SpiderInfo 核心元数据文件
│   ├── 0001.jpg
│   ├── 0002.jpg
│   └── 0003.jpg
├── 234567 - 画廊标题B/
│   ├── metadata                   # JHenTai 导出的 JSON 元数据文件
│   ├── 1.png
│   └── 2.png
├── 345678-画廊标题C.cbz           # 标准 CBZ 压缩归档包 (内嵌 ComicInfo.xml)
└── /archive (冷存储分层归档卷)
    └── 456789-画廊标题D/
        ├── .galleryvault.json     # GalleryVault 标准 Sidecar 索引
        ├── 0001.webp
        └── 0002.webp
```

---

## 元数据规范与样例

### 1. `.ehviewer` 规范 (SpiderInfo)

源自 Hippo Seven 的 EhViewer 架构规范（`com.hippo.ehviewer.spider.SpiderInfo`），采用多行结构化文本定义：

```text
SpiderInfo VERSION2
123456
a1b2c3d4e5
Category Name
Gallery Title (English / Romaji)
Gallery Japanese Title
2026-09-08 12:00:00
uploader_username
4.5
48
tag_namespace:tag_name,group:group_name,artist:artist_name
```

- **第一行**：版本标识（`SpiderInfo VERSION1` 或 `SpiderInfo VERSION2`）。
- **第二行**：全局画廊唯一标识（`gid`）。
- **第三行**：云端访问凭据令牌（`token`）。
- **后续各行**：画廊分类、主标题、日文标题、发布时间、上传者、评分、总页数与逗号分隔的标签集。

### 2. JHenTai `metadata` JSON 规范

JHenTai 导出的画廊元数据以标准 JSON 格式持久化存储在画廊根目录下：

```json
{
  "gid": 234567,
  "token": "f6e5d4c3b2",
  "title": "Sample Gallery Title",
  "japaneseTitle": "サンプルギャラリータイトル",
  "category": "Manga",
  "uploader": "SampleUploader",
  "publishTime": "2026-09-08 12:00:00",
  "rating": 4.8,
  "filecount": 32,
  "tags": {
    "artist": ["artist_name"],
    "female": ["long hair", "glasses"],
    "language": ["chinese", "translated"]
  }
}
```

GalleryVault 扫描器能够自动解析上述字段并建立索引，将其与云端信息无缝对齐。

### 3. `.galleryvault.json` Sidecar 规范

在分层冷存储或本地归档重构时，系统会在画廊目录或同名路径旁生成 `.galleryvault.json` 索引文件，确保在无网络或离线环境下依然保留完整的双语元数据：

```json
{
  "version": 1,
  "gid": 345678,
  "token": "b9c8d7e6f5",
  "title": "Archived Gallery Title",
  "title_jpn": "アーカイブ画廊タイトル",
  "category": "Doujinshi",
  "uploader": "archive_manager",
  "posted": "2026-09-08T12:00:00Z",
  "rating": 4.75,
  "pages": 64,
  "tags": [
    "artist:sample_artist",
    "female:long hair",
    "language:chinese"
  ],
  "archived_at": "2026-09-08T18:30:00Z"
}
```

---

## 格式降级与容错处理

1. **无 `.ehviewer` 的纯数字/标题目录**（例如 `123456-标题/`）：
   - 系统自动提取前置数字识别为 `gid`。
   - 若配置了云端凭证，可在后续后台任务中通过 GData API 自动补全封面、标签与分类元数据。
2. **CBZ / CBR 归档包**：
   - 文件名推荐形如 `123456-标题.cbz`。
   - 若压缩包内包含 `ComicInfo.xml`，系统将优先解析内部标题、作者与标签元数据。
3. **无 GID 的本地画廊**：
   - 可完全正常被扫描入库，支持本地浏览、日漫/双页阅读、星级评价与加入本地书单。
   - 因缺少全局唯一标识，此类条目不参与在线更新对比、云端收藏夹同步与跨 GID 查重。
