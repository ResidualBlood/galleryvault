import type { Page } from "@playwright/test";
import {
  DEFAULT_PROGRESS,
  GALLERIES,
  thumbnailSvg,
} from "./data";

export interface GalleryMockOptions {
  /** Override the saved page per gallery id. */
  progress?: Record<number, number>;
}

/**
 * Detail/progress/thumbnail responses for the gallery fixtures.
 *
 * Registered after the shared `** /api/**` mock, so Playwright resolves this
 * handler first; unrelated paths fall back to the shared mock (session,
 * notifications, ...). Never touches the test containers.
 */
export async function mockGalleryBackend(
  page: Page,
  options: GalleryMockOptions = {},
): Promise<void> {
  const progress = { ...DEFAULT_PROGRESS, ...options.progress };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(
      /^\/api\/galleries\/(\d+)(?:\/progress|\/thumb\/(\d+))?$/,
    );
    if (!match) {
      await route.fallback();
      return;
    }

    const id = Number(match[1]);
    const gallery = GALLERIES[id];
    if (!gallery) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "not found" }),
      });
      return;
    }

    if (url.pathname.endsWith("/progress")) {
      const current = progress[id] ?? 0;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          gallery_id: id,
          current_page: current,
          total_pages: gallery.page_count,
          updated_at: current > 0 ? "2026-11-12T10:00:00Z" : null,
        }),
      });
      return;
    }

    if (url.pathname.includes("/thumb/")) {
      const index = Number(match[2] ?? 0);
      await route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: thumbnailSvg(index),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(gallery),
    });
  });
}
