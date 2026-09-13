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

Originating from Hippo Seven's EhViewer specification (`com.hippo.ehviewer.spider.SpiderInfo`). The scanner expects line 1 to be `VERSION1` or `VERSION2` (**not** `SpiderInfo VERSION2`):

```text
VERSION2
0
123456
a1b2c3d4e5
0
0
0
3
0 abcdef01
1 abcdef02
2 abcdef03
```

- **Line 1**: `VERSION1` or `VERSION2`.
- **Next 7 fields** (one per line): start page (hex), `gid`, `token`, `mode`, preview page count, previews per page (ignored on VERSION1), total pages.
- **Then**: one `index pToken` line per page. Titles, category, and tags are **not** in `.ehviewer`; they come from the folder name, sidecar, or gdata.

### 2. JHenTai `metadata` JSON Specification

JHenTai writes a `metadata` file in the gallery root. Fields live under a `gallery` object; `tags` is a comma-separated string, not a dict:

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

The scanner reads `gallery.gid` / `token` / `title` / `category` / `uploader` / `publishTime` / `pageCount` / `tags`.

### 3. `.galleryvault.json` Sidecar Specification

For cold archive storage or portable exports, GalleryVault writes a `.galleryvault.json` sidecar. Written fields are `gid` / `token` / `title` / `title_jpn` / `tags` / `p_tokens`, plus optional `category` (no `version`, `posted`, `rating`, or `archived_at`):

```json
{
  "gid": 345678,
  "token": "b9c8d7e6f5",
  "title": "Archived Gallery Title",
  "title_jpn": "アーカイブ画廊タイトル",
  "category": "Doujinshi",
  "tags": [
    "artist:sample_artist",
    "female:long hair",
    "language:chinese"
  ],
  "p_tokens": ["abcdef01", "abcdef02"]
}
```

---

## Graceful Degradation & Fallback

1. **Bare numeric/title directories without `.ehviewer`** (e.g. `123456-Title/`):
   - The scanner extracts the prefix digits as the `gid`.
   - If cloud credentials are configured, background jobs will backfill covers, categories, and tags via GData APIs.
  2. **CBZ / CBR Archives & Specifications**:
    - Filenames prefixed with GID (e.g. `123456-title.cbz`) are indexed immediately. `.cbr` / `.rar` need Python `rarfile` **and** host `unrar` or libarchive; without a native extractor the scan fails.
   - **ComicInfo.xml Compatibility & Writer Truncation**: Embedded `ComicInfo.xml` metadata is parsed to extract titles, authors, and tag namespaces. During ingestion, overlong `Writer` tags are automatically truncated to 128 characters to prevent database column overflow errors from halting ingestion.
   - **243-Byte Filename Truncation Standard**: When generating or managing CBZ archives, GalleryVault replaces legacy character-based truncation with Linux ext4 byte-level rules. CBZ base filenames are clamped to 243 bytes, leaving sufficient headroom for the temporary `.cbz.partial` suffix (12 bytes) to strictly stay within the ext4 255-byte limit. Directory names are capped at 247 bytes. This completely resolves `[Errno 36] File name too long` exceptions caused by CJK multi-byte characters and overlong titles.
3. **Galleries without a GID**:
   - Fully browsable and readable locally, with support for star ratings and custom reading lists.
   - Without a persistent GID, these entries cannot participate in cloud sync, re-upload update tracking, or cross-GID duplicate resolution.
