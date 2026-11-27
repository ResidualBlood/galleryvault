import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { readerPagePath } from "../src/api/reader";
import { mockGalleryBackend } from "./fixtures/gallery/mock";
import { SMALL_GALLERY_ID } from "./fixtures/gallery/data";
import { expect, test } from "./fixtures/mock";
import { freePort, watchCsp } from "./support/polish";

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");
const MODES = ["ltr", "rtl", "double", "double-rtl", "webtoon"] as const;

let vite: ViteDevServer;
let HARNESS = "";


test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/reader/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

interface ReaderOptions {
  total?: number;
  page?: number;
  mode?: string;
  fit?: string;
  theme?: string;
  lang?: string;
  slideshow?: number;
  title?: string;
  id?: number;
}

function harnessUrl(options: ReaderOptions = {}): string {
  const params = new URLSearchParams();
  params.set("total", String(options.total ?? 12));
  params.set("page", String(options.page ?? 0));
  params.set("mode", options.mode ?? "ltr");
  params.set("fit", options.fit ?? "height");
  params.set("theme", options.theme ?? "dark");
  if (options.lang) params.set("lang", options.lang);
  if (options.slideshow) params.set("slideshow", String(options.slideshow));
  if (options.title) params.set("title", options.title);
  params.set("id", String(options.id ?? 7));
  return `${HARNESS}?${params.toString()}`;
}

function svgPage(page: number, width = 800, height = 1200): string {
  const label = `Page ${page + 1}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f4f1ea"/>
  <rect x="24" y="24" width="${width - 48}" height="${height - 48}" rx="12" fill="none" stroke="#8a8177" stroke-width="2"/>
  <text x="50%" y="48%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 10)}" fill="#1c1a17">${label}</text>
  <text x="50%" y="58%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 22)}" fill="#55504a">GalleryVault reader fixture</text>
</svg>`;
}

interface ImageMock {
  counts: Map<number, number>;
  bad: Set<number>;
  width?: number;
  height?: number;
}

async function mockPages(
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

async function openReader(page: Page, options: ReaderOptions = {}): Promise<void> {
  /*
   * The shared mock fixture routes `**\/api/**` to JSON. The Vite dev server
   * serves TypeScript modules from `/src/api/...`, which would also match that
   * glob, so let all `/src/**` requests reach Vite untouched.
   */
  await page.route("**/src/**", (route) => route.continue());
  await page.goto(harnessUrl(options));
  await expect(page.getByTestId("reader-shell")).toBeVisible();
  await expect(page.getByTestId("reader-shell")).toHaveAttribute(
    "data-total",
    String(options.total ?? 12),
  );
  await expect(page.getByTestId("reader-loading")).toHaveCount(0);
}


test("keyboard turns ten pages without dropping one @reader", async ({ page }) => {
  await mockPages(page, { total: 40 });
  await openReader(page, { total: 40, mode: "ltr" });

  for (let index = 0; index < 10; index += 1) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(100);
  }

  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-page", "10");
  await expect(page.getByTestId("reader-page-label")).toContainText("11");
});

test("touch swipe left turns the page @reader", async ({ page }) => {
  await mockPages(page, { total: 20 });
  await openReader(page, { total: 20, mode: "ltr" });

  await page.evaluate(() => {
    const root = document.querySelector<HTMLElement>('[data-testid="reader-shell"]');
    if (!root) throw new Error("reader shell missing");
    const rect = root.getBoundingClientRect();
    const y = rect.top + rect.height / 2;
    const fire = (type: string, x: number) => {
      root.dispatchEvent(
        new PointerEvent(type, {
          bubbles: true,
          pointerId: 1,
          pointerType: "touch",
          isPrimary: true,
          clientX: x,
          clientY: y,
          button: 0,
          buttons: type === "pointerup" ? 0 : 1,
        }),
      );
    };
    fire("pointerdown", rect.left + rect.width * 0.75);
    fire("pointermove", rect.left + rect.width * 0.55);
    fire("pointermove", rect.left + rect.width * 0.35);
    fire("pointerup", rect.left + rect.width * 0.35);
  });

  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-page", "1");
});

test("centre tap toggles both toolbars @reader", async ({ page }) => {
  await mockPages(page, { total: 12 });
  await openReader(page, { total: 12, mode: "ltr" });
  const shell = page.getByTestId("reader-shell");
  await expect(shell).toHaveAttribute("data-bars", "hidden");

  await page.mouse.click(640, 450);
  await expect(shell).toHaveAttribute("data-bars", "visible");
  await expect(page.getByTestId("reader-topbar")).toBeVisible();
  await expect(page.getByTestId("reader-bottombar")).toBeVisible();

  await page.mouse.click(640, 450);
  await expect(shell).toHaveAttribute("data-bars", "hidden");
});

test("double click zooms and the zoomed page can be dragged @reader", async ({ page }) => {
  await mockPages(page, { total: 10 });
  await openReader(page, { total: 10, page: 1, mode: "ltr" });
  const stage = page.locator(".reader__stage");

  await page.mouse.dblclick(640, 450);
  await expect.poll(() => stage.getAttribute("style")).toContain("scale(2.2)");

  await page.mouse.move(640, 450);
  await page.mouse.down();
  await page.mouse.move(720, 510, { steps: 6 });
  await page.mouse.up();
  await expect.poll(() => stage.getAttribute("style")).not.toContain("translate(0px, 0px)");

  await page.mouse.dblclick(640, 450);
  await expect.poll(() => stage.getAttribute("style")).toContain("scale(1)");
});

test("500-page webtoon keeps fewer than 30 images in the DOM @reader", async ({ page }) => {
  await mockPages(page, { total: 500 });
  await openReader(page, { total: 500, mode: "webtoon" });
  await expect(page.getByTestId("webtoon-strip")).toBeVisible();
  await expect(page.locator('[data-testid="reader-page"] img').first()).toBeVisible();

  expect(await page.locator('[data-testid="reader-shell"] img').count()).toBeLessThan(30);

  await page.evaluate(() => {
    const strip = document.querySelector<HTMLElement>('[data-testid="webtoon-strip"]');
    if (!strip) return;
    strip.scrollTop = 180_000;
    strip.dispatchEvent(new Event("scroll"));
  });
  await page.waitForTimeout(200);
  expect(await page.locator('[data-testid="reader-shell"] img').count()).toBeLessThan(30);
});

test("a broken page shows a placeholder and is not requested twice @reader", async ({ page }) => {
  const images = await mockPages(page, { total: 6, bad: [2] });
  await openReader(page, { total: 6, mode: "ltr" });

  await expect.poll(() => images.counts.get(2) ?? 0).toBeGreaterThanOrEqual(1);
  await page.waitForTimeout(300);

  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(120);
  await page.keyboard.press("ArrowRight");

  const placeholder = page.getByTestId("reader-page-missing");
  await expect(placeholder).toBeVisible();
  expect(images.counts.get(2) ?? 0).toBe(1);

  await page.getByTestId("reader-retry").click();
  await expect.poll(() => images.counts.get(2) ?? 0).toBe(2);
});

test("a progress PUT that fails once is retried successfully @reader", async ({ page }) => {
  await mockPages(page, { total: 10 });
  const bodies: string[] = [];
  const statuses: number[] = [];
  await page.route(/\/api\/galleries\/7\/progress$/, async (route) => {
    if (route.request().method() !== "PUT") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      return;
    }
    bodies.push(route.request().postData() ?? "");
    const attempt = statuses.length + 1;
    const status = attempt === 1 ? 500 : 200;
    statuses.push(status);
    await route.fulfill({
      status,
      contentType: "application/json",
      body: status === 200 ? "{}" : JSON.stringify({ detail: "boom" }),
    });
  });

  await openReader(page, { total: 10, mode: "ltr" });
  await expect.poll(() => statuses.length).toBeGreaterThanOrEqual(2);
  expect(statuses[0]).toBe(500);
  expect(statuses[1]).toBe(200);
  expect(JSON.parse(bodies[1])).toEqual({ current_page: 0, total_pages: 10 });

  await page.keyboard.press("ArrowRight");
  await expect.poll(() => statuses.length).toBeGreaterThanOrEqual(3);
  expect(JSON.parse(bodies.at(-1) ?? "{}")).toEqual({
    current_page: 1,
    total_pages: 10,
  });
});

test("mode and fit choices persist to localStorage @reader", async ({ page }) => {
  await mockPages(page, { total: 12 });
  await openReader(page, { total: 12, mode: "ltr", fit: "height" });
  await page.mouse.click(640, 450);
  await page.getByTestId("reader-settings").click();
  const shell = page.getByTestId("reader-shell");

  await page
    .getByTestId("reader-fit-control")
    .locator('[data-segmented-value="original"]')
    .click();
  await expect(shell).toHaveAttribute("data-fit", "original");
  expect(await page.evaluate(() => localStorage.getItem("gv_reader_fit"))).toBe("original");

  await page
    .getByTestId("reader-mode-control")
    .locator('[data-segmented-value="double-rtl"]')
    .click();
  await expect(shell).toHaveAttribute("data-mode", "double-rtl");
  expect(await page.evaluate(() => localStorage.getItem("gv_reader_mode"))).toBe("double-rtl");
});

test("slideshow advances without a page turn @reader", async ({ page }) => {
  await mockPages(page, { total: 20 });
  await openReader(page, { total: 20, page: 0, mode: "ltr", slideshow: 1 });
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-page", "1", {
    timeout: 5_000,
  });
});

test("last page offers the next gallery @reader", async ({ page }) => {
  await mockPages(page, { total: 5 });
  await page.route(/\/api\/galleries\/7\/next$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 88 }),
    });
  });
  await openReader(page, { total: 5, page: 4, mode: "ltr" });
  await page.mouse.click(640, 450);
  const next = page.getByTestId("reader-next-gallery");
  await expect(next).toBeVisible();
  await next.click();
  await expect.poll(() => page.evaluate(() => window.__readerHarness?.next)).toBe(88);
});

test("detail thumbnail opens the routed reader at that page @reader", async ({ page }) => {
  await mockGalleryBackend(page);
  const pageBase = readerPagePath(SMALL_GALLERY_ID, 0).replace(/\/0$/, "");
  await page.route(new RegExp(`${pageBase}/\\d+(?:\\?.*)?$`), async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/pages\/(\d+)/);
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: svgPage(Number(match?.[1] ?? 0), 600, 900),
    });
  });

  await page.goto(`/#/gallery/${SMALL_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
  await page.locator('[data-testid="thumb"]').nth(5).click();

  await expect(page).toHaveURL(new RegExp(`#/reader/${SMALL_GALLERY_ID}/5$`));
  const shell = page.getByTestId("reader-shell");
  await expect(shell).toBeVisible();
  await expect(shell).toHaveAttribute("data-total", "12");
  await expect(shell).toHaveAttribute("data-page", "5");
  await expect(page.getByTestId("reader-page-label")).toContainText("6");
  await expect(page.locator('[data-testid="reader-page"] img').first()).toBeVisible();

  await page.mouse.click(640, 450);
  await page.getByTestId("reader-close").click();
  await expect(page).toHaveURL(new RegExp(`#/gallery/${SMALL_GALLERY_ID}$`));
});

test("reader page turns mirror the URL and reload resumes in place @reader", async ({ page }) => {
  await mockGalleryBackend(page);
  const pageBase = readerPagePath(SMALL_GALLERY_ID, 0).replace(/\/0$/, "");
  await page.route(new RegExp(`${pageBase}/\\d+(?:\\?.*)?$`), async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/pages\/(\d+)/);
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: svgPage(Number(match?.[1] ?? 0), 600, 900),
    });
  });

  await page.goto(`/#/gallery/${SMALL_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
  await page.locator('[data-testid="thumb"]').nth(0).click();
  await expect(page).toHaveURL(new RegExp(`#/reader/${SMALL_GALLERY_ID}/0$`));
  const shell = page.getByTestId("reader-shell");
  await expect(shell).toHaveAttribute("data-page", "0");
  // Router.replace must update the URL without remounting the reader shell.
  await shell.evaluate((el) => el.setAttribute("data-e2e-marker", "keep"));

  const historyBefore = await page.evaluate(() => history.length);
  for (let index = 0; index < 3; index += 1) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(100);
  }

  await expect(shell).toHaveAttribute("data-page", "3");
  await expect(page).toHaveURL(new RegExp(`#/reader/${SMALL_GALLERY_ID}/3$`));
  await expect(shell).toHaveAttribute("data-e2e-marker", "keep");
  // History-replacing sync: page turns must not stack history entries.
  expect(await page.evaluate(() => history.length)).toBe(historyBefore);

  await page.reload();
  await expect(page.getByTestId("reader-loading")).toHaveCount(0);
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-page", "3");
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-total", "12");
  await expect(page.getByTestId("reader-page-label")).toContainText("4");

  // Back goes straight to the detail view instead of walking pages backwards.
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`#/gallery/${SMALL_GALLERY_ID}$`));
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
});

test("five modes have dark/light desktop/mobile screenshots @reader", async ({ page }) => {
  const viewports = [
    { width: 1280, height: 900, label: "desktop" },
    { width: 390, height: 844, label: "mobile" },
  ] as const;

  for (const mode of MODES) {
    for (const theme of ["dark", "light"] as const) {
      for (const viewport of viewports) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await mockPages(page, {
          total: 8,
          width: viewport.width,
          height: viewport.width * (mode === "webtoon" ? 0.75 : 1.5),
        });
        await openReader(page, {
          total: 8,
          page: mode === "double" || mode === "double-rtl" ? 2 : 1,
          mode,
          theme,
        });

        if (mode === "webtoon") {
          await expect(page.getByTestId("webtoon-strip")).toBeVisible();
        } else {
          await expect(page.getByTestId("reader-page").first()).toBeVisible();
        }
        await page.mouse.click(viewport.width / 2, viewport.height / 2);
        await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-bars", "visible");
        await page.waitForTimeout(150);

        await page.screenshot({
          path: join(SHOTS, `reader-${mode}-${theme}-${viewport.label}.png`),
        });
      }
    }
  }
});

test("reader has zero CSP violations across modes @reader", async ({ page }) => {
  const csp = watchCsp(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockPages(page, { total: 12 });

  for (const mode of MODES) {
    await openReader(page, { total: 12, page: 1, mode });
    await page.waitForTimeout(100);
  }

  expect(csp).toEqual([]);
  expect(pageErrors).toEqual([]);
});
