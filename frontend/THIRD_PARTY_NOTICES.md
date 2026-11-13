# Third-party notices

The frontend bundles the following third-party assets. Each entry lists what is
included, where it is used, and the upstream license.

## Material Symbols

- Upstream: Google Fonts — Material Symbols
  (<https://fonts.google.com/icons>, <https://github.com/google/material-design-icons>)
- License: Apache License 2.0 (Apache-2.0)
- Usage: icon glyph paths compiled at build time into inline SVG Vue
  components by `unplugin-icons`. No icon font is shipped and no runtime request
  is made to Google.
- Only the icons referenced by `src/components/icons/registry.ts` end up in the
  production bundle.

## Iconify icon data (`@iconify-json/material-symbols`)

- Upstream: Iconify (<https://iconify.design>, <https://github.com/iconify/icon-sets>)
- License: Apache License 2.0 (Apache-2.0) — the icon data is a conversion of
  Material Symbols.
- Usage: build-time data source for `unplugin-icons`; development dependency
  only, never imported at runtime.

## `unplugin-icons`

- Upstream: <https://github.com/unplugin/unplugin-icons>
- License: MIT
- Usage: Vite/Vitest plugin that compiles `~icons/<set>/<name>` imports into
  inline SVG Vue components at build time.
