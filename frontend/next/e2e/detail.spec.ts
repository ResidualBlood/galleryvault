import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures/mock";
import { mockGalleryBackend } from "./fixtures/gallery/mock";
import {
  LARGE_GALLERY_ID,
  SMALL_GALLERY_ID,
} from "./fixtures/gallery/data";

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

function watchConsole(page: import("@playwright/test").Page): string[] {
  const issues: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (
      message.type() === "error" &&
      /content security policy|refused to (?:load|execute|connect)/i.test(text)
    ) {
      issues.push(text);
    }
  });
  page.on("pageerror", (error) => {
    if (/content security policy/i.test(error.message)) issues.push(error.message);
  });
  return issues;
}

test("renders metadata and a bounded thumbnail window for 1000 pages @detail", async ({
  page,
}) => {
  const csp = watchConsole(page);
  await mockGalleryBackend(page);

  await page.goto(`/#/gallery/${LARGE_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
  await expect(page.getByTestId("gallery-title")).toHaveText("Large Virtual Gallery");
  await expect(page.getByTestId("gallery-subtitle")).toContainText("日本語");

  const groups = page.locator('[data-testid="tag-group"]');
  await expect(groups).toHaveCount(5);
  await expect(groups.first()).toHaveAttribute("data-ns", "parody");
  await expect(groups.last()).toHaveAttribute("data-ns", "uploader");

  const thumbs = page.locator('[data-testid="thumb"]');
  const count = await thumbs.count();
  expect(count).toBeGreaterThan(0);
  expect(count).toBeLessThan(150);

  expect(csp).toEqual([]);
});

test("continue reading opens the fixture progress page @detail", async ({ page }) => {
  await mockGalleryBackend(page);
  await page.goto(`/#/gallery/${LARGE_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();

  const next = page.getByTestId("continue-reading");
  await expect(next).toHaveText("继续阅读");
  await next.click();
  await expect(page).toHaveURL(new RegExp(`#/reader/${LARGE_GALLERY_ID}/640$`));
});

test("clicking a thumbnail opens the reader at that page @detail", async ({ page }) => {
  await mockGalleryBackend(page);
  await page.goto(`/#/gallery/${SMALL_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();

  const current = page.locator('.thumb[aria-current="page"]');
  await expect(current).toHaveCount(1);
  await expect(current).toContainText("4");
  await expect(current).toHaveAttribute("href", `#/reader/${SMALL_GALLERY_ID}/3`);

  await page.locator('[data-testid="thumb"]').nth(5).click();
  await expect(page).toHaveURL(new RegExp(`#/reader/${SMALL_GALLERY_ID}/5$`));
});

test("an invalid gallery id returns to browse with a toast @detail", async ({ page }) => {
  await mockGalleryBackend(page);
  await page.goto("/#/gallery/abc");

  await expect(page).toHaveURL(/#\/browse$/);
  await expect(page.locator(".toast")).toContainText("画廊地址无效");
});

test("screenshots cover dark/light x desktop/mobile @detail", async ({ page }) => {
  await mockGalleryBackend(page);
  await page.goto(`/#/gallery/${SMALL_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();

  const themes = ["dark", "light"] as const;
  const viewports = [
    { width: 1280, height: 900, label: "1280" },
    { width: 390, height: 844, label: "390" },
  ];

  for (const theme of themes) {
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.getByTestId("gallery-detail")).toBeVisible();
      await expect(page.getByTestId("gallery-title")).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `detail-${theme}-${viewport.label}.png`),
        fullPage: true,
      });
    }
  }
});

test("console has zero CSP violations on the detail route @detail", async ({ page }) => {
  const csp = watchConsole(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockGalleryBackend(page);

  await page.goto(`/#/gallery/${LARGE_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
  await expect(page.getByTestId("thumb").first()).toBeVisible();
  await page.locator('[data-testid="thumb"]').first().click();
  await expect(page).toHaveURL(new RegExp(`#/reader/${LARGE_GALLERY_ID}/\\d+$`));

  expect(csp).toEqual([]);
  expect(pageErrors).toEqual([]);
});
