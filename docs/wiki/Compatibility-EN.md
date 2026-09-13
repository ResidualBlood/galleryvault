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
| **EhViewer-NekoInverter / NekoWhite** | Legacy text only | Legacy text `.ehviewer` | Current Neko writes `.ehviewer` as CBOR; this scanner only parses Hippo/SXJ plaintext, so CBOR exports are skipped |
| **axlecho / MHViewer** & forks | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Full export format compatibility |
| **EhViewer-Apple (iOS / macOS)** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Direct ingestion of mobile exports |
| **Ehviewer_OHOS (HarmonyOS)** | Full Support | `.ehviewer` (SpiderInfo V1/V2) | Full export format compatibility |
| **JHenTai (Flutter Multi-platform)** | Page downloads | Gallery-root `metadata` JSON | Reads `{gid} - {title}/metadata` from page-by-page downloads; archive unpack dirs with `ametadata` are **not** scanned |
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
│   ├── metadata                   # JHenTai page-download JSON (no extension)
│   ├── 0.png
│   └── 1.png
├── 345678-GalleryTitleC.cbz       # Cold CBZ: ComicInfo.xml + .galleryvault.json inside the zip
└── /archive/dir/.../456789/       # Oversize galleries stay as a cold directory
    ├── .galleryvault.json         # Inside the directory, not beside the .cbz file
    ├── ComicInfo.xml
    ├── 0001.webp
    └── 0002.webp
```

---

## Metadata Specifications & Samples

### 1. `.ehviewer` Specification (SpiderInfo)

From Hippo Seven / SXJ (`com.hippo.ehviewer.spider.SpiderInfo`): plaintext lines, never CBOR. SXJ and this project's downloader **write VERSION2 only** (**not** `SpiderInfo VERSION2`):

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

- **VERSION2 (current)**: line 1 is `VERSION2`; next 7 fields: start page (8-digit hex, SXJ uses `%08x`; readers also accept `0`), `gid`, `token`, `mode` (written as `"1"`), preview page count, previews per page (this project writes `20`), total pages.
- **VERSION1 (read-only legacy)**: no `VERSION1` marker; line 1 is the hex start page. The same 7 fields follow; the previews-per-page line is present but ignored. The scanner also accepts a mistaken `VERSION1` first line; SXJ neither writes nor correctly reads that form.
- **Then**: one `index pToken` line per page. Titles, category, and tags are **not** in `.ehviewer`; they come from the folder name, `.galleryvault.json`, or gdata.

### 2. JHenTai `metadata` JSON Specification

JHenTai **page-by-page downloads** write `{gid} - {title}/metadata` (no extension). Fields live under a `gallery` object; `tags` is a comma-separated `namespace:key` string; `images` is a JSON-encoded **string**, not an array. Image files are `{serial}.{ext}` **starting at 0**:

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

The scanner reads `gallery.gid` / `token` / `title` / `category` / `uploader` / `publishTime` / `pageCount` / `tags`; pages are the directory's images in natural order (`images` is not parsed). Archive unpack dirs are `Archive - {gid} - {title}/` plus a top-level `ametadata` file (no `gallery` wrapper) and are **not** recognized.

### 3. `.galleryvault.json` Sidecar Specification

`.galleryvault.json` serves as GalleryVault's **offline Single Source of Truth (SSOT)**. Whether during download persistence, cold archive packaging, or automatic metadata backfilling during library scans, the system uniformly writes a consistent JSON document containing 15 fixed keys (`version: 1`). Even in an offline environment without database access, active network connections, or `.ehviewer` files, scanners can completely reconstruct the gallery identity (`gid` / `token`), titles, category, image quality, tags, and page-level `p_tokens` solely from the sidecar.

Storage Locations:
- **Directory Galleries** (page-by-page download hot folders, unpackaged cold archive directories): Located at the gallery root folder (alongside image files or `.ehviewer`).
- **CBZ Archives**: Located **inside the root** of the archive package (alongside `ComicInfo.xml`). **Never** placed outside next to the `.cbz` file.

Unified Schema Full Example (15 keys):

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

Conventions & Rules:

- `version`: Schema version, fixed integer `1`.
- `gid` / `token`: Unique gallery identifier and access token. Integer `gid` (`null` if unknown), lowercase hex string `token` (`""` if unknown).
- `title` / `title_jpn`: Primary title and Japanese title. Pure numeric `title_jpn` values are automatically normalized to `""`.
- `category`: Strictly lowercase (e.g. `"doujinshi"`, `"manga"`, not capitalized).
- `quality`: Strict enumeration `"original"` | `"resample"` | `null`. Unknown values must be explicitly written as `null` and never omitted (preventing rescans from clearing existing `image_quality` records in the database).
- `tags`: Formatted as an array of `{"namespace": "artist", "name": "sample"}` objects. The reader remains backward-compatible with legacy `"namespace:name"` strings.
- `p_tokens`: Index-aligned dense array of page tokens, with gaps filled by `""` (not a sparse array).
- `uploader` / `posted` / `rating` / `file_count` / `file_size` / `site`: Supplementary metadata. Written if available, filled with `null` if unknown (downloads do not issue extra GData network requests just to populate these; cold archive and scanner inherit from the database or existing sidecar metadata).
- **Key Completeness**: Always writes all 15 keys, filling missing items with `null` / `[]` / `""`, **never omitting keys**.
- **No Local Ephemeral State**: Does not persist `local_rating`, `local_note`, local file paths, file signatures, or `archived_at`.
- **Encoding**: UTF-8 encoding, `indent=2`, `ensure_ascii=False`, trailing newline.

Reader Compatibility & Scanner Backfill:

- **Backward Compatibility**: Readers seamlessly parse both legacy formats (early download version without `gid`/`token`/`p_tokens` but with `quality`; cold archive version with `gid` but without `quality` and optional `category`; tags as string lists).
- **Precedence**: Field precedence follows `sidecar > ComicInfo.xml > .ehviewer / directory inference` (sidecar title and tags override ComicInfo). However, a `gid` extracted from the filename prefix (e.g., `123456-xxx`) retains highest priority for gallery identification.
- **Directory Backfill**: After successful ingestion, only directory storages (hot and cold directories) are checked. If the sidecar is missing or lacks any critical key, a full v1 sidecar is automatically generated from current metadata; complete v1 sidecars are skipped to avoid altering filesystem `mtime`.
- **Read-Only Archives**: Compressed archive packages (CBZ, CBR, PDF) are strictly treated as read-only and are never modified or repacked during library scans.

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
