# GalleryVault frontend

Vue 3 + Vite + TypeScript SPA, served by nginx from the `galleryvault-frontend`
image. It replaces the legacy vanilla-JS bundle in place (PLAN §5): the old
`frontend/assets` tree is gone and there is no `/next/` or `/legacy/` prefix.

- Router: hash mode, so legacy bookmarks such as `#/gallery/12` keep working.
- Runtime: Vue 3 `<script setup>`, Pinia, vue-router.
- i18n: vue-i18n with **build-time precompiled** messages (no runtime compiler,
  no `eval` / `new Function`).
- No UI component library: thin components under `src/components/ui/` follow
  `docs/design/DESIGN.md`.
- Service Worker: `vite-plugin-pwa`; the legacy `gv-shell-*` caches are dropped on activation.

## Commands

```bash
npm ci
npm run dev            # proxy /api, /login, /logout to $GV_BACKEND (default http://127.0.0.1:8201)
npm run build          # -> dist/ (base '/')
npm run preview
npm run typecheck      # vue-tsc --noEmit
npm run lint           # ESLint (flat config) incl. the bare-/api/ guard
npm run test:unit      # Vitest
npm run e2e:mock       # Playwright, mocked backend, local vite preview
npm run e2e:real       # Playwright against GV_E2E_BASE (tester only)
node scripts/check-design.mjs
node scripts/check-dist.mjs
node scripts/check-parity.mjs --report | --views | --strict
```

`npm run e2e:mock -- --grep @shell` is the batch gate. Ports are derived from
the worktree path (4200–4999) so parallel worktrees do not collide; override
with `GV_E2E_PORT`. Screenshots go to `$GV_SHOTS` when set.

## Polish phase (2026-11-13)

- **Control ladder**: `--gv-size-control-xl/lg/md/sm` = 48 / 40 / 36 / 32 (touch
  pointers 48 / 44 / 40 / 36). One toolbar row uses one step and
  `align-items: center`; 48 is reserved for the login / welcome forms. See
  `docs/design/DESIGN.md` C12 and C16–C19.
- **Tag namespace colours**: themed `--gv-tagns-<namespace>` for the 15 EH
  namespaces, each checked at ≥4.5:1 against `--gv-color-surface-container`.
- **Specimen page**: `#/_kit` (lazy route, not in the navigation) auto-collects
  `src/views/kit/sections/*.vue`; `00-tokens.vue` renders the control ladder,
  icon sizes and the namespace palette.
- **Pending markers**: files on the polish surface start with
  `<!-- gv-polish:pending -->`. `check-design` skips the glyph / native-control
  rules for marked files and prints the remaining count; `--strict` requires 0.
  The marker is the only allowed edit to existing `.vue` files in this batch.
- **E2E helpers**: `e2e/support/polish.ts` (`expectNoGlyphIcons`,
  `expectControlHeights`, `expectRowsAligned`, `expectNoHorizontalOverflow`,
  `expectTouchTargets`, `shotMatrix`); `e2e/kit.spec.ts` is the `@kit` gate.
- **Audit capture**: `e2e/real/audit.spec.ts` (`@audit`) mirrors
  `audit/capture.mjs` against `$GV_E2E_BASE`, blocks every non-GET `/api`
  request except `POST /api/tags/search`, and writes screenshots + metrics to
  `$GV_SHOTS`. Writers do not run it; the tester does after integration.

```bash
node scripts/check-design.mjs --tokens-only   # tokens + contrast
node scripts/check-design.mjs                 # + glyph/native-control scan
node scripts/check-design.mjs --strict        # fails while markers remain
```

## Directory ownership

| Path | Contents / owner |
| --- | --- |
| `src/api/` | HTTP client plus **all** endpoint declarations, grouped by domain. |
| `src/components/AppShell.vue` | Responsive shell (bottom bar / rail / drawer) and top bar. |
| `src/components/ui/` | Design-system primitives: Button, IconButton, Input, Select, Switch, Dialog, Sheet, Popover, Toast, EmptyState, ErrorState, Skeleton. |
| `src/components/actions/` | Card / detail / reader action rows (placeholder until fe-quick-actions). |
| `src/composables/` | `useViewRequest` (token + AbortController + stale check), `usePolling`. |
| `src/locales/{zh,en}/` | Feature JSON (`app`, `login`, `common`) plus generated `legacy.json`. |
| `src/reader/source.ts` | `PageSource` interface for local / online-direct / online-proxy. |
| `src/router/` | Hash route table (`routes.ts`) and navigation guard. |
| `src/stores/` | `auth`, `settings` (theme/lang/page size), `ui` (toasts). |
| `src/views/` | `LoginView` and the shared not-migrated placeholder. |
| `parity/` | Legacy endpoint/route snapshots and waivers. |
| `scripts/` | Locale conversion, parity, dist and design guards. |
| `e2e/` | Mocked shell tests + `e2e/real` smoke tests. |
| `docs/design/` | Design spec, references, specimen, required-token list (fe-design). |

Business views belong to later batches; this scaffold only ships the
placeholder view, so every route is reachable without pretending a feature is
implemented.

## API client contract

`src/api/client.ts` is the single request entry point:

- `credentials: "include"` on every request;
- `POST/PUT/PATCH/DELETE` copy the `galleryvault_csrf` cookie into
  `X-CSRF-Token` (double-submit, cookie is not httpOnly);
- default 30 s timeout plus caller `AbortSignal` support (`code: "timeout"`);
- any 401 calls the handler registered in `main.ts` (clears the auth store and
  routes to `#/login`); the session probe and login opt out;
- non-2xx throws `ApiError` with `status` and structured `detail`.

Endpoints are declared only in `src/api/<domain>.ts`:

```ts
export const settingsEp = ep("GET", "/api/settings");
```

ESLint rejects a bare `/api/` literal or template outside `src/api/`. When a
new endpoint is needed, add it to the matching domain file first, then call it.
`parity/legacy-endpoints.json` and `scripts/check-parity.mjs` use these
declarations to measure coverage; `--report` also re-greps the old
`frontend/assets` source when it still exists and prints
`grep 命中但未收录 = 0` (the cutover deleted that tree).

## i18n

- Feature copy is split per feature: `src/locales/zh/<feature>.json` and
  `src/locales/en/<feature>.json`. Key sets must stay equal (unit test).
- `legacy.json` is the flattened snapshot of the pre-cutover
  `frontend/assets/locales/{zh,en}.js` bundles (763 leaf keys per language).
  The one-off converter is gone (its legacy sources were deleted); `src/locales/**`
  is now edited directly.
- vue-i18n treats `.` as a path separator. All **48** legacy keys containing a
  dot are therefore mapped to underscores; the mapping is deterministic and is
  checked for collisions. If a mapped name collided with an existing key the
  converter would abort instead of silently overwriting.
- Literal `@` and `|` in old copy are emitted using vue-i18n literal syntax
  (`{'@'}`, `{'|'}`) so messages such as “H@H” compile.
- `ns` and `groups` stay nested objects (they were never read through `t()` in
  the old frontend).

Dotted-key → underscore mapping:

<details>
<summary>48 mapped keys</summary>

| Legacy key | New key |
| --- | --- |
| `library.filters.advanced` | `library_filters_advanced` |
| `library.filters.activeCount` | `library_filters_activeCount` |
| `tasks.duplicates` | `tasks_duplicates` |
| `tasks.duplicatesDesc` | `tasks_duplicatesDesc` |
| `tasks.galleryUpdates` | `tasks_galleryUpdates` |
| `tasks.galleryUpdatesDesc` | `tasks_galleryUpdatesDesc` |
| `tasks.galleryUpdate` | `tasks_galleryUpdate` |
| `tasks.galleryUpdateDesc` | `tasks_galleryUpdateDesc` |
| `tasks.orphanThumbnailCleanup` | `tasks_orphanThumbnailCleanup` |
| `tasks.orphanThumbnailCleanupDesc` | `tasks_orphanThumbnailCleanupDesc` |
| `tasks.thumbnailPeriodicSeed` | `tasks_thumbnailPeriodicSeed` |
| `tasks.thumbnailPeriodicSeedDesc` | `tasks_thumbnailPeriodicSeedDesc` |
| `tasks.downloadRetrySweep` | `tasks_downloadRetrySweep` |
| `tasks.downloadRetrySweepDesc` | `tasks_downloadRetrySweepDesc` |
| `tasks.cookieHealth` | `tasks_cookieHealth` |
| `tasks.cookieHealthDesc` | `tasks_cookieHealthDesc` |
| `tasks.calibrateStorage` | `tasks_calibrateStorage` |
| `tasks.calibrateStorageDesc` | `tasks_calibrateStorageDesc` |
| `tasks.purgeArchivedSources` | `tasks_purgeArchivedSources` |
| `tasks.purgeArchivedSourcesDesc` | `tasks_purgeArchivedSourcesDesc` |
| `tasks.integrity` | `tasks_integrity` |
| `tasks.integrityDesc` | `tasks_integrityDesc` |
| `tasks.galleryLocal` | `tasks_galleryLocal` |
| `tasks.galleryLocalDesc` | `tasks_galleryLocalDesc` |
| `tasks.downloadEnqueue` | `tasks_downloadEnqueue` |
| `tasks.downloadEnqueueDesc` | `tasks_downloadEnqueueDesc` |
| `tasks.downloadIngest` | `tasks_downloadIngest` |
| `tasks.downloadIngestDesc` | `tasks_downloadIngestDesc` |
| `tasks.downloadUpdated` | `tasks_downloadUpdated` |
| `tasks.downloadUpdatedDesc` | `tasks_downloadUpdatedDesc` |
| `tasks.exportCbz` | `tasks_exportCbz` |
| `tasks.exportCbzDesc` | `tasks_exportCbzDesc` |
| `tasks.favoritesNote` | `tasks_favoritesNote` |
| `tasks.favoritesNoteDesc` | `tasks_favoritesNoteDesc` |
| `tasks.localListCreate` | `tasks_localListCreate` |
| `tasks.localListCreateDesc` | `tasks_localListCreateDesc` |
| `tasks.localListAdd` | `tasks_localListAdd` |
| `tasks.localListAddDesc` | `tasks_localListAddDesc` |
| `tasks.localListRemove` | `tasks_localListRemove` |
| `tasks.localListRemoveDesc` | `tasks_localListRemoveDesc` |
| `tasks.localListDelete` | `tasks_localListDelete` |
| `tasks.localListDeleteDesc` | `tasks_localListDeleteDesc` |
| `tasks.moveFavorites` | `tasks_moveFavorites` |
| `tasks.moveFavoritesDesc` | `tasks_moveFavoritesDesc` |
| `tasks.removeFavorites` | `tasks_removeFavorites` |
| `tasks.removeFavoritesDesc` | `tasks_removeFavoritesDesc` |
| `tasks.restoreGalleries` | `tasks_restoreGalleries` |
| `tasks.restoreGalleriesDesc` | `tasks_restoreGalleriesDesc` |

</details>

## Themes and local settings

Keys intentionally match the legacy frontend so upgrades and rollbacks keep
user choices:

| Key | Values | Notes |
| --- | --- | --- |
| `gv_theme` | `dark` / `light` / `system` | `system` removes `data-theme` and follows `prefers-color-scheme`. |
| `gv_lang` | `zh` / `en` | Also sets `<html lang>`. |
| `gv_page_size` | number | List page size (used by later list batches). |

`tokens.css` is the only place with colour / type / radius values. UI code
must use `--gv-*` tokens; `scripts/check-design.mjs` fails on raw colour,
`font-size` or non-token `border-radius` literals.

## Routes

Hash mode. Legacy paths and aliases (PLAN §4.1, inv-frontend.md §2.1):

- `/browse`, `/library`, `/series`, `/gallery/:id`, `/reader/:id/:page`,
  `/tags`, `/history`, `/downloads`, `/logs`, `/settings`, `/favorites`,
  `/favorites/:id`, `/favorites/manage`, `/favorites/ignored`, `/duplicates`,
  `/duplicates/cross-gid`, `/updates`, `/updates/ignored`, `/recycle`,
  `/integrity`, `/archive`, `/welcome`.
- Aliases: `/discover` → `/online`, `/duplicates/favorites` →
  `/favorites/manage`.
- New: `/online`, `/online/g/:gid/:token`, `/online/g/:gid/:token/read/:page`.
- Design kit: `/_kit` (lazy, not in the navigation) renders
  `src/views/kit/sections/*.vue` for shared alignment / screenshot fixtures.
- Waiver: `#/series/{id}` is a dead legacy route and redirects to `/series`
  (`parity/waivers.json`). Every other entry in `parity/legacy-routes.json` is
  resolved by the new router in a unit test.

## Tests and E2E fixtures

- Unit: `npm run test:unit` covers locale key equality, API client
  CSRF/401/timeout/abort, and route parity.
- Mock E2E: `e2e/fixtures/mock.ts` intercepts `/api/**`, `/login`, `/logout`.
  It never talks to a real backend. Tests cover login, theme, language, 401 →
  login, the three navigation breakpoints, four screenshots and CSP console
  cleanliness.
- Real E2E: `e2e/real/smoke.spec.ts` (`@smoke`) reads `GV_E2E_BASE` and
  `GV_E2E_PASSWORD`. **Writers do not run it**; the tester runs it against the
  shared environment after integration (PLAN §5.2). Password/cookies never go
  into source, PLAN, commits, screenshots or logs.
- `playwright install --dry-run` must report the browser revision already on
  the host; `@playwright/test` is pinned to the matching version.

## Design and CSP guards

- `docs/design/DESIGN.md` + `tokens.css` are the design contract. Every UI
  batch must pass `check-design.mjs` and attach light/dark × 1280/390
  screenshots (tree-external) for review.
- `scripts/check-dist.mjs` fails on inline `<script>`, `eval(` /
  `new Function(`, external script/link URLs, and external
  fetch/WebSocket/EventSource/XHR/import targets. The production nginx CSP is
  `script-src 'self'`.

## Image and CI

`Dockerfile` builds `dist/` with node 22 and copies it into `nginx:1.27-alpine`
with `nginx.conf`. CI (`ci-frontend.yml`) runs `npm ci`, typecheck, lint, unit
tests, build, `check-dist`, `check-design`, `check-parity --strict` and
`nginx -t`.
