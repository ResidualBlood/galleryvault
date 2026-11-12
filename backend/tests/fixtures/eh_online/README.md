# `eh_online` test fixtures

## `gallery-detail.html`

Trimmed, sanitized excerpt of a real ExHentai gallery detail page captured by
the p0-eh-spike (gid `4323821`, gallery page `?p=0`) on 2026-11-12.

- Kept: the info table rows (`Posted` / `Parent` / `File Size` / `Length`),
  title, tags, rating box, cover, the 20 sprite thumbnail cells
  (`<a href="/s/<ptoken>/<gid>-<n>"><div title="Page n: …" style="…">`), and
  the preview-page pager.
- Removed: every `<script>` block (the original page embedded `apiuid` /
  `apikey` / login URLs), ads and unrelated chrome.
- Sanitized: the uploader name and forum user id replaced with
  `sample-uploader` / `0`; the H@H node host replaced with
  `node1.example.hath.network`; the per-gallery genkey replaced with
  `samplegenkey01`. No cookie, apikey, token or username values remain.

The file intentionally contains the *unmodified* sprite layout; do not edit it
to make a parser test pass — if the layout drifts, re-capture a page instead.

No page-1 (`?p=1`) capture was available; tests that need a second preview page
build it inline from the same cell markup.
