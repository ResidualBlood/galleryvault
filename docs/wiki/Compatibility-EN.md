# Compatibility and Scope

> [中文](Compatibility) · **English**

GalleryVault focuses on managing local digital gallery archives, natively supporting download formats from major mobile clients with high-fidelity metadata parsing.

---

## Client Support Matrix

| Client / Ecosystem Tool | Support Level | Metadata Detection | Details |
| :--- | :--- | :--- | :--- |
| **Ehviewer_CN_SXJ** | Primary Reference | `.ehviewer` (SpiderInfo V1/V2) | The project's reference architecture for directory and metadata structures |
| **FooIbar / EhViewer (MD3)** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Natively indexes gallery and page-level metadata |
| **Ehviewer-Overhauled** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Completely upstream-compatible; mount and scan directly |
| **EhViewer-NekoInverter / NekoWhite** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Natively supported with full category and tag parsing |
| **axlecho / MHViewer** & forks | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Full export format compatibility |
| **EhViewer-Apple (iOS / macOS)** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Direct ingestion of mobile exports |
| **Ehviewer_OHOS (HarmonyOS)** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Full export format compatibility |
| **JHenTai (Flutter Multi-platform)** | Full Support | `metadata` (JSON format) | Automatically parses JSON tags, categories, and timestamps |
| **Tachiyomi / Mihon / Panels** | Protocol Integration | OPDS Catalog (`/api/opds`) | Connects via HTTP Basic authentication for remote browsing and reading |
| **Generic CBZ / CBR Archives** | Standard Support | `ComicInfo.xml` / filename prefix | Recognizes `gid-title.cbz` formats and embedded metadata schemas |

---

## Directory Organization Topology

GalleryVault supports flexible multi-tier mounts. A standard directory topology looks like:

```
/library (or custom scan roots)
├── 123456-GalleryTitleA/
│   ├── .ehviewer                  # SpiderInfo metadata file
│   ├── 0001.jpg
│   ├── 0002.jpg
│   └── 0003.jpg
├── 234567 - GalleryTitleB/
│   ├── metadata                   # JHenTai JSON metadata file
│   ├── 1.png
│   └── 2.png
├── 345678-GalleryTitleC.cbz       # Standard CBZ package (with ComicInfo.xml)
└── /archive (Tiered cold storage volume)
    └── 456789-GalleryTitleD/
        ├── .galleryvault.json     # GalleryVault standard sidecar index
        ├── 0001.webp
        └── 0002.webp
```

---

## Metadata Specifications & Samples

### 1. `.ehviewer` Specification (SpiderInfo)

Originating from Hippo Seven's EhViewer specification (`com.hippo.ehviewer.spider.SpiderInfo`), this file uses structured multi-line text:

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

- **Line 1**: Format identifier (`SpiderInfo VERSION1` or `SpiderInfo VERSION2`).
- **Line 2**: Global gallery identifier (`gid`).
- **Line 3**: Remote access token (`token`).
- **Subsequent lines**: Category, primary title, Japanese title, posted timestamp, uploader, rating, page count, and comma-separated tags.

### 2. JHenTai `metadata` JSON Specification

JHenTai saves gallery metadata in a standard JSON format located in the gallery root:

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

GalleryVault's scanner automatically maps these properties to its internal database schema without requiring external network lookups.

### 3. `.galleryvault.json` Sidecar Specification

For cold archive storage or portable exports, GalleryVault writes a `.galleryvault.json` sidecar alongside the archive to preserve complete metadata offline:

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

## Graceful Degradation & Fallback

1. **Bare numeric/title directories without `.ehviewer`** (e.g. `123456-Title/`):
   - The scanner extracts the prefix digits as the `gid`.
   - If cloud credentials are configured, background jobs will backfill covers, categories, and tags via GData APIs.
2. **CBZ / CBR archives**:
   - Filenames prefixed with GID (e.g. `123456-title.cbz`) are indexed immediately.
   - Embedded `ComicInfo.xml` metadata is parsed to extract titles, authors, and tag namespaces.
3. **Galleries without a GID**:
   - Fully browsable and readable locally, with support for star ratings and custom reading lists.
   - Without a persistent GID, these entries cannot participate in cloud sync, re-upload update tracking, or cross-GID duplicate resolution.
