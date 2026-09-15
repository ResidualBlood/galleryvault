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
| **EhViewer-NekoInverter / NekoWhite** | 旧文本可读 | 旧版文本 `.ehviewer` | 现代版本把 `.ehviewer` 写成 CBOR，本扫描器只解析 Hippo/SXJ 纯文本，CBOR 导出会当损坏跳过 |
| **axlecho / MHViewer** 等分支 | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 导出格式完全兼容 |
| **EhViewer-Apple (iOS / macOS)** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 移动端导出目录直接挂载入库 |
| **Ehviewer_OHOS (鸿蒙)** | 完整支持 | `.ehviewer` (SpiderInfo V1/V2) | 导出格式完全兼容 |
| **JHenTai (Flutter 全平台)** | 逐页目录支持 | 画廊根目录 `metadata` JSON | 识别逐页下载的 `{gid} - {title}/metadata`；归档解压目录的 `ametadata` **不扫** |
| **Tachiyomi / Mihon / Panels** | 协议接入 | OPDS 目录协议 (`/api/opds`) | 通过 HTTP Basic 认证直接接入画廊书库浏览阅读 |
| **通用 CBZ / CBR 压缩包** | 标准支持 | `ComicInfo.xml` / 文件名前缀 | 支持 `gid-标题.cbz` 或内部内嵌元数据解析 |
| **通用 7z** | 标准支持 | 仅图片成员 | py7zr；按页内存解压，单页上限 128MB；非图片留在包内 |
| **PDF** | 标准支持 | 内嵌图 | 抽取内嵌图；单图超 128MB 跳过 |

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
│   ├── metadata                   # JHenTai 逐页下载 JSON（无扩展名）
│   ├── 0.png
│   └── 1.png
├── 345678-画廊标题C.cbz           # 冷归档 CBZ：包内嵌 ComicInfo.xml + .galleryvault.json
└── /archive/dir/.../456789/       # 超限时打成冷目录，不打 CBZ
    ├── .galleryvault.json         # 写在目录内，不是放在 CBZ 旁边
    ├── ComicInfo.xml
    ├── 0001.webp
    └── 0002.webp
```

---

## 元数据规范与样例

### 1. `.ehviewer` 规范 (SpiderInfo)

源自 Hippo Seven / SXJ（`com.hippo.ehviewer.spider.SpiderInfo`），纯文本换行，无 CBOR。SXJ 与本项目下载**只写 VERSION2**（**不要**写成 `SpiderInfo VERSION2`）：

```text
VERSION2
00000000
123456
a1b2c3d4e5
1
1
20
3
0 abcdef01
1 abcdef02
2 abcdef03
```

- **VERSION2（现网）**：首行 `VERSION2`；随后 7 个字段：起始页（8 位十六进制，SXJ 用 `%08x`，读端也接受 `0`）、`gid`、`token`、`mode`（写出固定 `"1"`）、预览页数、每页预览数（本项目写 `20`）、总页数。
- **VERSION1（只读旧文件）**：没有 `VERSION1` 标记行，首行就是十六进制起始页；后面仍是上述 7 个字段，其中「每页预览数」那行物理存在但忽略。扫描器额外容忍误写的 `VERSION1` 首行；SXJ 自己不写、也读不好这种文件。
- **再往后**：每行 `页索引 pToken`（空格分隔）。标题、分类、标签不在 `.ehviewer` 里，由目录名 / `.galleryvault.json` / gdata 补全。

### 2. JHenTai `metadata` JSON 规范

JHenTai **逐页下载**把元数据写在 `{gid} - {title}/metadata`（无扩展名）。外层包 `gallery` 对象，`tags` 是逗号分隔的 `namespace:key` 字符串，`images` 是 JSON 再编码后的**字符串**（不是数组）。图片名为 `{serial}.{ext}`，**从 0 起**：

```json
{
  "gallery": {
    "gid": 234567,
    "token": "f6e5d4c3b2",
    "title": "Sample Gallery Title",
    "category": "Manga",
    "uploader": "SampleUploader",
    "publishTime": "2026-09-08 12:00:00",
    "pageCount": 32,
    "tags": "artist:artist_name,female:long hair,language:chinese"
  },
  "images": "[]"
}
```

扫描器读 `gallery.gid` / `token` / `title` / `category` / `uploader` / `publishTime` / `pageCount` / `tags`；页列表按目录图片自然序，不解析 `images`。归档下载解压目录是 `Archive - {gid} - {title}/` + 顶层 `ametadata`（无 `gallery` 包裹），**当前不识别**。

### 3. `.galleryvault.json` Sidecar 规范

`.galleryvault.json` 是 GalleryVault 的**离线单一真实数据源（SSOT）**。无论是下载落盘、冷归档打包，还是扫描对目录元数据的自动补齐，系统均统一写出相同结构且包含 15 个固定键的完整 JSON 文件（`version: 1`）。即使脱离数据库、在无网络连接或缺少 `.ehviewer` 时，扫描器仅凭 sidecar 即可完整还原画廊核心身份（gid / token）、标题、分类、画质、标签与逐页 pToken。

存储位置：
- **目录画廊**（逐页下载热目录、未打包的冷归档目录）：置于画廊根目录下（与图片或 `.ehviewer` 并列）。
- **CBZ 归档包**：置于压缩包**内部根目录**（与 `ComicInfo.xml` 并列），**严禁**放在外部 `.cbz` 文件同级。

统一 Schema 完整示例（15 键）：

```json
{
  "version": 1,
  "gid": 345678,
  "token": "b9c8d7e6f5",
  "title": "English Title",
  "title_jpn": "日本語タイトル",
  "category": "doujinshi",
  "quality": "resample",
  "tags": [
    {"namespace": "artist", "name": "sample_artist"},
    {"namespace": "female", "name": "long hair"}
  ],
  "p_tokens": ["abcdef01", "abcdef02"],
  "uploader": null,
  "posted": null,
  "rating": null,
  "file_count": 2,
  "file_size": null,
  "site": null
}
```

约定规则：

- `version`：版本号，固定为整型 `1`。
- `gid` / `token`：画廊唯一标识与访问令牌。整型 `gid`（未知时 `null`），小写十六进制字符串 `token`（未知时 `""`）。
- `title` / `title_jpn`：主标题与日文标题。若 `title_jpn` 为纯数字，系统规整为 `""`。
- `category`：统一小写（如 `"doujinshi"`, `"manga"`，非首字母大写）。
- `quality`：严格受限枚举 `"original"` | `"resample"` | `null`。未知必须写 `null`，禁止省略键（防止重扫冲掉库内已有画质标记）。
- `tags`：规范写出形如 `{"namespace": "artist", "name": "sample"}` 的对象数组。读端保持兼容，亦可解析 `"namespace:name"` 纯字符串。
- `p_tokens`：按页码下标对齐的稠密字符串数组，缺页填充 `""`（非稀疏数组）。
- `uploader` / `posted` / `rating` / `file_count` / `file_size` / `site`：元数据补充项。已知时写入，未知时填 `null`（下载流程不为此额外打网络 GData 请求；冷归档与入库从 DB 或已有元数据继承）。
- **键完整性**：始终写出全部 15 个键，未知项填充 `null` / `[]` / `""`，**禁止省略键**。
- **排除私有状态**：不持久化 `local_rating`、`local_note`、本地路径、文件签名或 `archived_at` 等易变或私有运行状态。
- **编码**：UTF-8 编码、`indent=2`、`ensure_ascii=False`、末尾换行。

读端兼容与扫描回写：

- **后向兼容**：读端无缝兼容历史两套旧格式（早期下载款无 gid/token/p_tokens 但有 quality；冷归档款有 gid 但无 quality 且 category 可缺；tags 为纯字符串列表等）。
- **优先级**：字段合并遵循 `sidecar > ComicInfo.xml > .ehviewer / 目录推断`（包内 sidecar 的标题与标签优先于 ComicInfo）。但文件名提取的 `gid`（形如 `123456-xxx`）依然具有最高优先级。
- **目录回写**：扫描入库成功后，仅针对目录型存储（热目录、冷目录）检查 sidecar。若缺失 sidecar 或缺少任意核心键，将结合本次元数据自动补写完整 v1 sidecar；若已是完整 v1 则跳过以避免刷新 mtime。
- **压缩包只读**：对 CBZ / CBR / 7z / PDF 等压缩归档包严格保持只读，扫描入库绝不修改或重打包压缩文件。

---

## 格式降级与容错处理

1. **无 `.ehviewer` 的纯数字/标题目录**（例如 `123456-标题/`）：
   - 系统自动提取前置数字识别为 `gid`。
   - 若配置了云端凭证，可在后续后台任务中通过 GData API 自动补全封面、标签与分类元数据。
  2. **CBZ / CBR 归档包与规范**：
    - 文件名推荐形如 `123456-标题.cbz`。`.cbr` / `.rar` 需要 Python `rarfile` **以及**宿主机的 `unrar` 或 libarchive；缺原生解压工具时扫描会失败，不是开箱即用。
   - **ComicInfo.xml 兼容与截断防护**：若压缩包内包含 `ComicInfo.xml`，系统将优先解析内部标题、作者与标签元数据。入库解析时，若发现超长 `Writer`（作者）标签，系统将自动按 128 字符截断入库，防止数据库底层字段溢出阻断入库流程。
   - **243 字节文件名截断规范**：生成或重命名 CBZ 归档包时，系统废除了旧版不考虑多字节编码的硬编码截断限制，全面采用 Linux ext4 等现代文件系统的 UTF-8 字节级截断规则。CBZ 基础文件名上限为 243 字节，为打包时追加的临时后缀 `.cbz.partial`（12 字节）预留充足空间，确保最终总文件名始终 ≤ 255 字节上限；中间目录名上限为 247 字节。此机制彻底杜绝了中日韩多字节字符及超长标题在底层文件系统中触发 `[Errno 36] File name too long` 的致命异常。
3. **无 GID 的本地画廊**：
    - 可完全正常被扫描入库，支持本地浏览、日漫/双页阅读、星级评价与加入本地书单。
    - 因缺少全局唯一标识，此类条目不参与在线更新对比、云端收藏夹同步与跨 GID 查重。
4. **7z / PDF**：
    - `.7z` 只索引图片成员，阅读按页在内存解压（固实包也按页，前面成员不计入限额）。单页未压缩上限 **128MB**，超限拒读。
    - `.pdf` 抽取内嵌图；单图超 128MB 跳过该图，不中断整本扫描。抽不到图则跳过并 warning。
    - 两者扫描时只读，不把内容解到库目录。
