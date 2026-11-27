import type { Page } from "@playwright/test";
import { readerPagePath } from "../../../src/api/reader";

/**
 * Reader page image mock shared by the reader E2E suites.
 *
 * Serves an SVG per page index so the reader never touches the network, and
 * counts requests per page so "requested twice" regressions are measurable.
 */
export function svgPage(page: number, width = 800, height = 1200): string {
  const label = `Page ${page + 1}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f4f1ea"/>
  <rect x="24" y="24" width="${width - 48}" height="${height - 48}" rx="12" fill="none" stroke="#8a8177" stroke-width="2"/>
  <text x="50%" y="48%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 10)}" fill="#1c1a17">${label}</text>
  <text x="50%" y="58%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 22)}" fill="#55504a">GalleryVault reader fixture</text>
</svg>`;
}

export interface ImageMock {
  counts: Map<number, number>;
  bad: Set<number>;
  width?: number;
  height?: number;
}

export async function mockPages(
  page: Page,
  options: { total: number; bad?: number[]; width?: number; height?: number; galleryId?: number },
): Promise<ImageMock> {
  const counts = new Map<number, number>();
  const bad = new Set(options.bad ?? []);
  const galleryId = options.galleryId ?? 7;
  const pageBase = readerPagePath(galleryId, 0).replace(/\/0$/, "");
  await page.route(new RegExp(`${pageBase}/\\d+(?:\\?.*)?$`), async (route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/pages\/(\d+)/);
    const index = match ? Number.parseInt(match[1], 10) : 0;
    counts.set(index, (counts.get(index) ?? 0) + 1);
    if (bad.has(index)) {
      await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: svgPage(index, options.width, options.height),
    });
  });
  return { counts, bad, width: options.width, height: options.height };
}
