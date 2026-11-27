# Frontend Development & Build

> [中文](Development) · English

Frontend architecture, development / build / test commands, the design-spec entry points, and how online reading and the companion script are implemented.

## Architecture

The frontend is a **Vue 3 + Vite + TypeScript** single-page app. It builds to `dist/` and is served by nginx, which also reverse-proxies `/api`, `/login`, and `/logout` to the backend (default `http://backend:8001`). The backend stays a pure JSON API with no HTML output.

- **Routing**: hash mode, so old bookmarks such as `#/gallery/12` keep working. Online browsing adds `#/online`, `#/online/g/:gid/:token`, and `#/online/g/:gid/:token/read/:page`; the old `#/discover` remains an alias.
- **State**: Pinia (`auth`, `settings`, `ui`, `downloads`, `favorites`, …).
- **i18n**: vue-i18n with build-time precompiled messages — no runtime compiler, no `eval` / `new Function`.
- **Styling**: no UI component library; `src/styles/tokens.css` is the only source of colour, type, radius, and spacing values, and primitives live in `src/components/ui/`.
- **Requests**: `src/api/client.ts` is the single entry point (credentials, CSRF double-submit header, 30 s timeout, 401 handling); endpoints are declared only in `src/api/<domain>.ts`.
- **Service Worker**: built with injectManifest and handles shell/static caching plus update prompts; it never caches `/api/` responses or gallery images.

## Layout

After the switch the frontend lives in `frontend/` at the repository root:

```
frontend/
  src/
    api/                 # HTTP client and per-domain endpoint declarations
    components/          # AppShell, ui/ primitives, actions/ rows
    composables/         # useViewRequest, usePolling
    i18n/ locales/       # precompiled messages (zh/ and en/ key sets must match)
    pwa/                 # Service Worker registration and update toast
    reader/              # PageSource: local / online-direct / online-proxy
    router/              # route table and navigation guard
    stores/              # Pinia
    styles/tokens.css    # design tokens
    views/               # feature views
  docs/design/           # DESIGN.md, REFERENCES.md, tokens.required.json, specimen.html
  e2e/                   # Playwright specs and mocked backend
  parity/                # legacy route/endpoint snapshots and waivers
  scripts/               # check-design / check-dist / check-parity
  userscript/            # companion userscript source, build, and unit tests
  public/                # icons, manifest, companion script artifact
  nginx.conf Dockerfile
```

## Develop and build

```bash
cd frontend
npm ci
npm run dev          # dev server; proxies /api, /login, /logout to $GV_BACKEND (default http://127.0.0.1:8201)
npm run build        # emits dist/ with base '/'
npm run preview      # preview the build
```

After `npm run build`, `dist/` can be served by any static server for verification; production uses the nginx in the image.

Local orchestration from the monorepo root:

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

- The frontend runs the Vite dev server with hot reload;
- the backend runs `uvicorn --reload` with proxy headers so rate limiting and logs see the real client IP;
- the development database is isolated in `./db-data-dev`; host `./library`, `./downloads`, and `./cache` are mounted into the container.

## Tests

```bash
cd frontend
npm run typecheck     # vue-tsc --noEmit
npm run lint          # ESLint, including the bare-/api/ guard
npm run test:unit     # Vitest: locale key parity, API client, route parity, reader paging
npm run e2e:mock      # Playwright with a mocked backend (no real service)
npm run e2e:real      # Playwright against a real test environment (GV_E2E_BASE)
```

- `e2e:mock` derives its port from the worktree path (4200–4999, override with `GV_E2E_PORT`) so parallel worktrees do not collide; `GV_SHOTS` selects the screenshot directory.
- `e2e:real` is run only by the test-environment owner; the password comes in via `GV_E2E_PASSWORD` and never appears in source, logs, commits, or screenshots.
- CI currently runs backend tests and builds only; frontend E2E runs in the shared test environment before release.
- Companion script:

  ```bash
  node userscript/build.mjs            # regenerate public/galleryvault-companion.user.js
  node userscript/build.mjs --check    # verify the artifact did not drift
  npm run test:unit -- userscript      # userscript unit tests only
  npm run e2e:mock -- --grep @userscript
  ```

## Design specification

| Item | Location |
| :--- | :--- |
| Design spec | `frontend/docs/design/DESIGN.md` |
| Reference list and the aspect taken from each | `frontend/docs/design/REFERENCES.md` |
| Required token list | `frontend/docs/design/tokens.required.json` |
| Third-party icon and license notice | `frontend/THIRD_PARTY_NOTICES.md` |
| Static specimen | `frontend/docs/design/specimen.html` |
| Token definitions | `frontend/src/styles/tokens.css` |
| Automated check | `node scripts/check-design.mjs` (`--tokens-only` checks tokens and contrast only) |

The spec uses Material Design 3 token structure without its component library, keeps the warm-gold brand colour, and fixes the EH category / favorite-slot colours. Every UI batch must use `--gv-*` tokens only, pass `check-design.mjs`, attach light / dark × desktop 1280 / mobile 390 screenshots (stored outside the tree), and cite the spec sections in its acceptance. Reference projects contribute layout and interaction patterns only — never code, icons, or screenshots.

## How online image loading works

By default the server does not relay image bytes: the backend resolves a time-limited H@H URL per page and the browser fetches the image directly. Only when a user switches that device to proxy mode do bytes pass through the server.

- Resolution uses the global EH page concurrency (6); online concurrency (default 3, `online_reader_concurrency`) caps resolve and proxy together; the reader preloads at most 2 pages.
- Resolved URLs are cached server-side for 10 minutes (H@H signatures live 15 minutes); expiry or a load failure triggers a re-resolve, and a failure is retried on another node twice before the UI offers proxy / official page.
- Exhausted image quota (509 / 429) stops preloading and shows usage instead of retrying in a loop.
- CSP `img-src` allows `ehgt.org`, `*.hath.network:*`, and the EH sites; `connect-src` stays `'self'`. `scripts/check-dist.mjs` rejects external scripts, `eval`, and external request targets.
- User-facing behaviour: [Online Reading](Online-Reading-EN).

## API token and companion script

- Settings → Account & security can generate / revoke the API token; plaintext is returned once and only a hash is stored. Revoking invalidates scripts using that token immediately.
- The Bearer token is restricted to a whitelist: session state, `GET /api/eh/status`, favorite categories, add / remove favorite, create / query download tasks; everything else returns `403`. Requests with a session cookie still go through CSRF checks, and mixing Bearer with a cookie does not grant an exemption.
- The script only injects a panel on official gallery pages and reads no EH cookies; address and token live in the script manager. Install and privacy notes: [Online Reading → Companion script](Online-Reading-EN#companion-script-optional-zero-server-quota).

## Icons, base components, and design references

- **Icon source**: every page writes `<Icon name="semantic-name" />`; the semantic name → Material Symbols Rounded path map lives in `frontend/src/components/icons/registry.ts`. Icons are compiled at **build time** into inline SVG Vue components by `unplugin-icons` + `@iconify-json/material-symbols`: no icon font, no runtime request, no style injection into `<svg>`, and unused icons never reach the bundle. Pages must not import `~icons/` directly and must not use Unicode characters or emoji as icons (`check-design` enforces both). Sizes come from the 16 / 18 / 20 / 24 tokens; 20 inside controls (18 for the 32px tier), 24 in navigation.
- **Licenses**: Material Symbols and the Iconify icon data are **Apache-2.0**; `unplugin-icons` is **MIT**. Both npm packages are `devDependencies` only. The full notice (upstream, usage, license) is in `frontend/THIRD_PARTY_NOTICES.md`; selection and usage rules are in `frontend/docs/design/DESIGN.md` C16.
- **Base components and size tiers**: Button / IconButton / TextField / Select / Switch / Checkbox / Field / TextArea / Slider / SegmentedControl / Chip / Toolbar / PageHeader / Pager / FilterButton / SelectionBar / EmptyState / ErrorState / TagChip / TagList / TagMenu / GalleryCollection / GalleryCard / GalleryListRow / GalleryTable / ViewModeToggle. Control heights only use `--gv-size-control-lg/md/sm` (40 / 36 / 32, +4 on touch); one toolbar uses a single tier and is vertically centred, icon-to-text gap 8, in-group gap 8 / between-group gap 16. Component rules are in `DESIGN.md` C12 and C17–C19; the browser-level specimen lives at `#/_kit` (not in navigation).
- **Code entry points for view and tag rules**:
  - `frontend/src/composables/useViewMode.ts`: in-page grid / list / table switching, preference stored per page key under `localStorage.gv_view_mode`; below 600px the table is not offered and a stored table preference falls back temporarily without being overwritten.
  - `frontend/src/components/tags/tag-utils.ts`: language choice (`display` for zh, `name` otherwise), inline ordering with `language` skipped, `libraryTagQuery` (`tags=ns:name&tag_mode=and`, idempotent append / exclude), and `formatEhTagQuery` (`ns:"name$"`, idempotent).
  - `frontend/src/components/tags/useTagNavigation.ts`, `TagChip.vue`, `TagList.vue`, `TagMenu.vue`: click navigation, Shift / Ctrl exclusion, long-press / right-click copy of the raw tag.
  - `frontend/src/components/gallery/GalleryCollection.vue`: all three views share one item set and selection state.
- **Design references**: reference projects, the aspect taken from each, links, and licenses are registered in `frontend/docs/design/REFERENCES.md`. The polish phase added **EhViewer_CN_SXJ** (GPL-3.0, local source `d129f20`) as the interaction reference for browse-page view switching, inline tags, click-to-search syntax, filter badges, and page jumping. Only behaviour and interaction patterns are borrowed — never its source, layout XML, assets, or strings. The three views and per-page memory are local extensions: that project only has a global list / grid setting and rebuilds the list when it changes.

## Deployment and security

- nginx serves the build with CSP `script-src 'self'`: no inline scripts, external CDNs, or `eval`.
- The frontend uses only relative paths such as `/api`; Vite proxies them in development and nginx reverse-proxies them in production.
- Before committing, run `npm run lint`, `npm run test:unit`, and `node scripts/check-parity.mjs --strict` inside `frontend/` (legacy route and endpoint coverage).
