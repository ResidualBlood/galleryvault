# Product Roadmap

> Maintained by the maintainer. Priorities shift with real user feedback —
> discuss and vote in [Discussions](https://github.com/ResidualBlood/galleryvault/discussions)
> or file an [issue](https://github.com/ResidualBlood/galleryvault/issues).
> Items marked ⚠️ are **unvalidated assumptions** (we don't know yet whether
> real users want them).

## Shipped · v1.0.0 (2026-08)

The first tagged release. Core value proposition delivered:

- Local gallery library (Ehviewer exports / CBZ/CBR / folders) with a
  PostgreSQL search index
- Namespaced tag cloud, instant autocomplete, EhTagTranslation-based Chinese
  translation (incl. reverse matching)
- ExHentai integration: metadata sync, concurrent resumable downloads,
  favorites monitor + duplicate scan, Telegram notifications
- Reader with history; bilingual EN/中文 UI; activity log page
- Security: rate limiting, non-root runtime, optional AES-256-GCM at-rest
  encryption; docs on the GitHub Wiki; MIT license
- **First-run welcome wizard** (`#/welcome`): guided change-password → ExHentai
  cookies → fill-the-library steps, shown while the default password is in use

## Now · Growth & onboarding (next weeks)

Focus: turn "works for me" into "works for a stranger".

- **Empty states** on Library / Downloads / Favorites that tell the user what
  to do next
- **Community distribution**: submit to TrueNAS / Unraid app catalogs
  (self-hosted growth engine)
- **Public launch**: Show HN / r/selfhosted announcement for v1.0.0
- **Onboarding docs**: a "from zero to first gallery in 5 minutes" page on the wiki

## Next · Core experience

- **Batch tag editing** on local galleries (user-defined tags) — browse/search
  today, no way to organize
- **Advanced search**: multi-tag AND/OR, sort by size/posted, filter by
  favorites status
- **PWA + mobile pass**: installable, offline-read cache, touch gestures in
  the reader
- **Reader improvements**: zoom, double-page, bookmarks

## Later · Scale

- ⚠️ **Multi-user / shared instance** (currently single-password by design)
- ⚠️ **Anonymous usage stats** (opt-in only — privacy-first product)
- **Full-text & fuzzy search**, tagging the index
- **Plugin/webhook ecosystem** for notifications beyond Telegram

## Non-goals

- A GUI config editor for everything — settings stay in the Settings page
- Cloud sync / hosted accounts — GalleryVault stays self-hosted
- Not-a-streaming-server for arbitrary media — this is a gallery library

## How to influence this

1. Open a [Discussion](https://github.com/ResidualBlood/galleryvault/discussions)
   — Ideas for proposals, Q&A for help.
2. Upvote what matters to you; tell us your use case (it changes priorities).
3. The maintainer is the single voice on scope; community adoption reorders
   the board.
