# Compatibility and Scope

> [中文](Compatibility) · English

GalleryVault focuses on managing local gallery archives, natively supporting download formats from popular clients with high fidelity metadata parsing.

## Primary Support: EhViewer Family Clients

GalleryVault is built **primarily for galleries downloaded by [Ehviewer_CN_SXJ](https://github.com/xiaojieonly/Ehviewer_CN_SXJ)**:
- **Directory structure**: `<gid>-<title>/` image folder plus a `.ehviewer` metadata file.
- **Metadata format**: SpiderInfo VERSION1 / VERSION2 containing gallery gid, token, and per-page pToken. The scanner parses these to accurately restore full gallery identity.

Because `.ehviewer` originates from Hippo Seven's EhViewer (`com.hippo.ehviewer.spider.SpiderInfo`), **any client in this ecosystem writing this format is fully compatible**:

- **Original EhViewer** ([seven332/EhViewer](https://github.com/seven332/EhViewer), deprecated).
- **Active main forks**:
  - [**FooIbar/EhViewer**](https://github.com/FooIbar/EhViewer) (Material Design 3)
  - [**Ehviewer-Overhauled/Ehviewer**](https://github.com/Ehviewer-Overhauled/Ehviewer)
  - [**EhViewer-NekoInverter/EhViewer**](https://github.com/EhViewer-NekoInverter/EhViewer)
  - [**exzhawk/EhViewer**](https://github.com/exzhawk/EhViewer)
  - [**AdNotFound/EhViewer**](https://github.com/AdNotFound/EhViewer)
  - [**WarnError/Ehviewer-NekoWhite**](https://github.com/WarnError/Ehviewer-NekoWhite)
  - [**NotFaceGUI/EhViewer-Auto-Translation-Ver**](https://github.com/NotFaceGUI/EhViewer-Auto-Translation-Ver)
  - [**axlecho/MHViewer**](https://github.com/axlecho/MHViewer) and other forks
- **Cross-platform ports**:
  - [**EhViewer-Apple**](https://github.com/felixchaos/EhViewer-Apple) (iOS / macOS)
  - [**Ehviewer_OHOS**](https://github.com/suibianqwe/Ehviewer_OHOS) (HarmonyOS)
- **Ecosystem companion tools**:
  - [**LRReader**](https://github.com/Xslx98/LRReader) (Android, LANraragi client)
  - [**exhentai-manga-manager**](https://github.com/SchneeHertz/exhentai-manga-manager)
  - [**ehviewer_manga_manager**](https://github.com/Schweik7/ehviewer_manga_manager) (Python CLI)
  - [**LANraragi**](https://github.com/Difegue/LANraragi)'s `Ehviewer.pm` metadata plugin

## Other Formats & Graceful Degradation

- **[JHenTai](https://github.com/jiangtian616/JHenTai)** (cross-platform Flutter: Android / iOS / Windows / macOS / Linux):
  - **Natively supported**: `<gid> - <title>/` plus `metadata` JSON.
  - Ingestion restores full gallery identity (gid, token, tags, category, publish date). Feel free to submit an issue with a sample `metadata` file if you encounter anomalies.
- **Graceful degradation**:
  - **Plain `<gid>-<title>` folders without `.ehviewer`**: Identifies gid only.
  - **CBZ / CBR archives**: gid must prefix the archive filename (e.g. `123456-title.cbz`).
  - **Galleries without gid**: Fully browsable and readable locally, but **cannot take part in online downloads, update checking, or favorites deduplication**.
- **Sidecar metadata**:
  - GalleryVault's downloader writes `.galleryvault.json` (category, title, tags) sidecars upon download, which are read on rescan or index rebuilds.
