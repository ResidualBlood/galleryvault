/**
 * Companion userscript E2E (mock backend, sanitized EH sample page).
 *
 * The userscript is not part of the SPA; this suite loads the built
 * `public/galleryvault-companion.user.js` into a trimmed E-Hentai gallery page
 * with a GM shim, and drives a local HTTP mock of the GalleryVault API.
 *
 * Covered: status badges, download POST + bearer header, favourite favcat,
 * first-run configuration, 401 reconfiguration, no foreign requests, zero CSP
 * violations, light/dark × desktop/mobile screenshots.
 */

/* eslint-disable no-restricted-syntax -- standalone userscript E2E asserts raw API paths outside the SPA client */

import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { installGmShim } from "./fixtures/userscript/gm-shim";
import {
  MOCK_API_TOKEN,
  MOCK_EH_TOKEN,
  MOCK_GID,
  apiRequests,
  authorizationOf,
  startMockBackend,
  type MockBackend,
} from "./fixtures/userscript/mock";

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

const USERSCRIPT = readFileSync(
  join(PROJECT_ROOT, "public/galleryvault-companion.user.js"),
  "utf8",
);
const SAMPLE_PAGE = readFileSync(
  join(PROJECT_ROOT, "e2e/fixtures/userscript/gallery.html"),
  "utf8",
);

const GALLERY_URL = `https://e-hentai.org/g/${MOCK_GID}/${MOCK_EH_TOKEN}/`;
const PANEL = "#gv-companion-panel";

interface Harness {
  backend: MockBackend;
  consoleLines: string[];
  pageRequests: string[];
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

async function openGallery(
  page: Page,
  backend: MockBackend,
  options: { configured?: boolean } = {},
): Promise<Harness> {
  const consoleLines: string[] = [];
  const pageRequests: string[] = [];

  page.on("console", (message) => consoleLines.push(`${message.type()}: ${message.text()}`));
  page.on("pageerror", (error) => consoleLines.push(`pageerror: ${String(error)}`));
  page.on("request", (request) => pageRequests.push(request.url()));

  // GM requests run outside the page: forward them to Node like the extension.
  await page.exposeFunction(
    "__gvGmRequest",
    async (request: {
      method: string;
      url: string;
      headers: Record<string, string>;
      data?: string;
    }) => {
      const response = await fetch(request.url, {
        method: request.method,
        headers: request.headers,
        body: request.data,
      });
      return { status: response.status, responseText: await response.text() };
    },
  );

  await page.addInitScript(installGmShim, {
    base: backend.baseUrl,
    token: MOCK_API_TOKEN,
    configured: options.configured !== false,
  });

  await page.route(/^https:\/\/(?:e-hentai|exhentai)\.org\/.*/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html; charset=utf-8",
      body: SAMPLE_PAGE,
    }),
  );

  await page.goto(GALLERY_URL);
  await page.addScriptTag({ content: USERSCRIPT });

  return { backend, consoleLines, pageRequests };
}

function cspViolations(consoleLines: string[]): string[] {
  return consoleLines.filter((line) =>
    /content security policy|refused to (?:load|execute|apply)/i.test(line),
  );
}

function expectNoTokenLeak(harness: Harness, html: string): void {
  expect(html).not.toContain(MOCK_API_TOKEN);
  const leaked = [...harness.consoleLines, ...harness.pageRequests].filter((line) =>
    line.includes(MOCK_API_TOKEN),
  );
  expect(leaked).toEqual([]);
}

test.describe("@userscript companion", () => {
  let backend: MockBackend;

  test.beforeEach(async () => {
    backend = await startMockBackend();
  });

  test.afterEach(async () => {
    await backend.close();
  });

  test("@userscript panel shows status, queues a download and favorites @userscript", async ({
    page,
  }) => {
    const harness = await openGallery(page, backend);
    const panel = page.locator(PANEL);

    await expect(panel).toBeVisible();
    await expect(panel).toHaveAttribute("data-state", "ready");
    await expect(panel).toContainText("已在库");
    await expect(panel).toContainText("已收藏（分类 2）");
    await expect(panel).toContainText("下载中");

    // Status came from GET /api/eh/status with the bearer token.
    const statusRequest = apiRequests(backend, "/api/eh/status")[0];
    expect(statusRequest?.path).toContain(`gids=${MOCK_GID}`);
    expect(authorizationOf(statusRequest)).toBe(`Bearer ${MOCK_API_TOKEN}`);

    // Download with an explicit quality.
    await panel.locator('[data-role="quality"]').selectOption("original");
    await panel.getByRole("button", { name: "下载到 GalleryVault" }).click();
    await expect(panel).toContainText("已加入 GalleryVault 下载队列");

    const downloadRequest = apiRequests(backend, "/api/downloads")[0];
    expect(downloadRequest?.method).toBe("POST");
    expect(authorizationOf(downloadRequest)).toBe(`Bearer ${MOCK_API_TOKEN}`);
    expect(JSON.parse(downloadRequest.body)).toEqual({
      gid: MOCK_GID,
      token: MOCK_EH_TOKEN,
      quality: "original",
    });

    // Favorite into an explicitly chosen favcat.
    await panel.locator('[data-role="favcat"]').selectOption("3");
    await panel.getByRole("button", { name: "收藏到 GalleryVault" }).click();
    await expect(panel).toContainText("已收藏到 GalleryVault");
    await expect(panel).toContainText("已收藏（分类 3）");

    const favoriteRequest = apiRequests(backend, "/api/favorites/add")[0];
    expect(favoriteRequest?.method).toBe("POST");
    expect(authorizationOf(favoriteRequest)).toBe(`Bearer ${MOCK_API_TOKEN}`);
    expect(JSON.parse(favoriteRequest.body)).toEqual({
      gid: MOCK_GID,
      token: MOCK_EH_TOKEN,
      target_favcat: 3,
    });

    const openLink = panel.getByRole("link", { name: "在 GalleryVault 打开" });
    await expect(openLink).toHaveAttribute(
      "href",
      `${backend.baseUrl}/#/online/g/${MOCK_GID}/${MOCK_EH_TOKEN}`,
    );

    expect(backend.notFound).toEqual([]);
    expect(cspViolations(harness.consoleLines)).toEqual([]);
    for (const url of harness.pageRequests) {
      expect(url).toMatch(/^https:\/\/(?:e-hentai|exhentai)\.org\//);
    }
    const gmUrls = (await page.evaluate(
      () => ((window as unknown as { __gvGmRequests?: Array<{ url: string }> }).__gvGmRequests || []).map((entry) => entry.url),
    )) as string[];
    expect(gmUrls.length).toBeGreaterThan(0);
    for (const url of gmUrls) expect(url.startsWith(backend.baseUrl)).toBe(true);

    expectNoTokenLeak(harness, await page.content());
  });

  test("@userscript first run asks for a GalleryVault address and token @userscript", async ({
    page,
  }) => {
    const harness = await openGallery(page, backend, { configured: false });
    const panel = page.locator(PANEL);

    await expect(panel).toHaveAttribute("data-state", "unconfigured");
    await expect(panel).toContainText("首次使用请填写 GalleryVault 地址与 API Token");
    await expect(panel.locator('[data-role="base"]')).toBeVisible();
    await expect(panel.locator('[data-role="token"]')).toHaveAttribute("type", "password");

    await panel.locator('[data-role="base"]').fill(backend.baseUrl);
    await panel.locator('[data-role="token"]').fill(MOCK_API_TOKEN);
    await panel.getByRole("button", { name: "保存并连接" }).click();

    await expect(panel).toHaveAttribute("data-state", "ready");
    await expect(panel).toContainText("已在库");

    const stored = (await page.evaluate(() => ({
      base: window.localStorage.getItem("gm:gv_base_url"),
      token: window.localStorage.getItem("gm:gv_api_token"),
    }))) as { base: string | null; token: string | null };
    expect(stored.base).toBe(JSON.stringify(backend.baseUrl));
    expect(stored.token).toBe(JSON.stringify(MOCK_API_TOKEN));

    // The saved token must leave the form behind (no DOM echo).
    await expect(panel.locator('[data-role="token"]')).toHaveCount(0);
    expectNoTokenLeak(harness, await page.content());
    expect(cspViolations(harness.consoleLines)).toEqual([]);
  });

  test("@userscript asks to reconfigure when the token is rejected @userscript", async ({ page }) => {
    await backend.close();
    backend = await startMockBackend({ unauthorized: true });

    const harness = await openGallery(page, backend);
    const panel = page.locator(PANEL);

    await expect(panel).toHaveAttribute("data-state", "unauthorized");
    await expect(panel).toContainText("认证失败");
    await expect(panel).toContainText("重新配置");
    await expect(panel.locator('[data-role="token"]')).toBeVisible();
    await expect(panel.getByRole("button", { name: "下载到 GalleryVault" })).toHaveCount(0);

    expect(apiRequests(backend, "/api/eh/status")).toHaveLength(1);
    expect(authorizationOf(apiRequests(backend, "/api/eh/status")[0])).toBe(
      `Bearer ${MOCK_API_TOKEN}`,
    );
    expectNoTokenLeak(harness, await page.content());
    expect(cspViolations(harness.consoleLines)).toEqual([]);
  });

  test("@userscript screenshots light/dark on desktop and mobile @userscript", async ({ page }) => {
    const harness = await openGallery(page, backend);
    const panel = page.locator(PANEL);
    await expect(panel).toHaveAttribute("data-state", "ready");

    const combos = [
      { theme: "light", device: "desktop", width: 1280, height: 900 },
      { theme: "dark", device: "desktop", width: 1280, height: 900 },
      { theme: "light", device: "mobile", width: 390, height: 844 },
      { theme: "dark", device: "mobile", width: 390, height: 844 },
    ] as const;

    for (const combo of combos) {
      await page.setViewportSize({ width: combo.width, height: combo.height });
      await page.emulateMedia({ colorScheme: combo.theme });
      await expect(panel).toBeVisible();

      const box = await panel.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeLessThanOrEqual(combo.width);
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(combo.width + 1);
      const overflow = (await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      )) as number;
      expect(overflow).toBeLessThanOrEqual(1);

      await page.screenshot({
        path: join(SHOTS, `userscript-${combo.theme}-${combo.device}.png`),
        fullPage: true,
      });
    }

    expect(cspViolations(harness.consoleLines)).toEqual([]);
    expect(backend.notFound).toEqual([]);
  });
});
