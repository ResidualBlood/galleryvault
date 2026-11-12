import type { Page } from "@playwright/test";
import { sessionEp } from "../../../src/api/auth";
import { ehSearchEp } from "../../../src/api/eh";
import {
  detailResponse,
  pagesResponse,
  searchResponse,
  spriteSvg,
  thumbSvg,
} from "./data";

/**
 * Mock `/api/eh/*` responses for the online views.
 *
 * Thumbnails are intercepted under `https://ehgt.org/**` and replaced with a
 * local SVG so the mock suite never touches ExHentai / the public CDN.
 */
export async function mockOnlineBackend(page: Page): Promise<void> {
  await page.route(`**${sessionEp.path}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        auth_required: true,
        must_change_password: false,
        cookie_health: { state: "ok" },
      }),
    });
  });

  await page.route("**/api/eh/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === ehSearchEp.path) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(searchResponse(url.searchParams)),
      });
      return;
    }
    const detail = url.pathname.match(/^\/api\/eh\/galleries\/(\d+)\/([^/]+)$/);
    if (detail) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(detailResponse(Number(detail[1]), detail[2])),
      });
      return;
    }
    const pages = url.pathname.match(/^\/api\/eh\/galleries\/(\d+)\/([^/]+)\/pages$/);
    if (pages) {
      const p = Number(url.searchParams.get("p") ?? "0") || 0;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(pagesResponse(Number(pages[1]), pages[2], p)),
      });
      return;
    }
    await route.fallback();
  });

  await page.route("https://ehgt.org/**", async (route) => {
    const url = route.request().url();
    const body = url.endsWith("sprite.svg") ? spriteSvg() : thumbSvg();
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body,
    });
  });
}
