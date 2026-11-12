import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures/mock";
import { installLibraryMock } from "./fixtures/library/seed";

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

async function libraryGrid(page: import("@playwright/test").Page) {
  const grid = page.getByTestId("library-grid");
  await expect(grid).toBeVisible();
  return grid;
}

test("home shows continue reading, latest and random entry @library", async ({ page }) => {
  const csp = watchConsole(page);
  await installLibraryMock(page);

  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-view")).toBeVisible();
  await expect(page.getByTestId("continue-reading")).toBeVisible();
  await expect(page.getByTestId("continue-42")).toContainText("Continue 42");
  await expect(page.getByTestId("browse-grid")).toBeVisible();
  await expect(page.getByTestId("gallery-card").first()).toBeVisible();

  const input = page.getByTestId("tag-suggest").locator("input");
  await input.fill("dragon");
  await expect(page.getByTestId("tag-suggestion").first()).toBeVisible();
  await expect(page.getByTestId("tag-suggestion").first()).toContainText("中文");
  await page.getByTestId("tag-suggestion").first().click();
  await expect(page).toHaveURL(/\/library\?.*tags=language:chinese/);

  await page.goto("/#/browse");
  await page.getByTestId("random-button").click();
  await expect(page).toHaveURL(/#\/gallery\/7/);

  expect(csp).toEqual([]);
});

test("library search, tag suggestions, sort and page size @library", async ({ page }) => {
  const state = await installLibraryMock(page);

  await page.goto("/#/library");
  const grid = await libraryGrid(page);
  await expect(grid).toHaveAttribute("data-loaded", "50");

  const input = page.getByTestId("tag-suggest").locator("input");
  await input.fill("dragon");
  await expect(page.getByTestId("tag-suggestion").first()).toBeVisible();
  await page.getByTestId("tag-suggestion").first().click();
  await expect(page).toHaveURL(/tags=language:chinese/);
  await expect(page.locator(".library__tag")).toContainText("language:chinese");

  await page.getByTestId("order-select").locator("select").selectOption("title_asc");
  await expect(page).toHaveURL(/order_by=title_asc/);
  await expect
    .poll(() => state.requests.at(-1)?.get("order_by"), { timeout: 10_000 })
    .toBe("title_asc");

  await page.getByTestId("page-size-select").locator("select").selectOption("100");
  await expect(page).toHaveURL(/page_size=100/);
  expect(await page.evaluate(() => localStorage.getItem("gv_page_size"))).toBe("100");
  await expect
    .poll(() => state.requests.at(-1)?.get("page_size"), { timeout: 10_000 })
    .toBe("100");
});

test("virtual grid keeps the DOM small and restores scroll after detail @library", async ({ page }) => {
  const csp = watchConsole(page);
  await page.addInitScript(() => {
    localStorage.setItem("gv_page_size", "500");
  });
  await installLibraryMock(page, { total: 5000 });

  await page.goto("/#/library");
  const grid = await libraryGrid(page);
  await expect(grid).toHaveAttribute("data-loaded", "500");

  await expect
    .poll(
      async () => {
        const loaded = Number(await grid.getAttribute("data-loaded"));
        if (loaded < 5000) {
          await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        }
        return loaded;
      },
      { timeout: 90_000, intervals: [400, 600, 800, 1200] },
    )
    .toBe(5000);

  const rendered = await page.locator('[data-testid="gallery-card"]').count();
  expect(rendered).toBeLessThan(200);

  const rowHeight = Number(await grid.getAttribute("data-row-height"));
  expect(rowHeight).toBeGreaterThan(0);

  await page.evaluate(() => window.scrollTo(0, 120_000));
  await page.waitForTimeout(250);
  const before = await page.evaluate(() => window.scrollY);
  expect(before).toBeGreaterThan(100_000);

  await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[data-testid="gallery-card"]'));
    const visible = cards.find((card) => {
      const rect = card.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= window.innerHeight;
    });
    (visible ?? cards[0]).querySelector("a")?.click();
  });
  await expect(page).toHaveURL(/#\/gallery\/\d+/);

  await page.goBack();
  await libraryGrid(page);
  await expect
    .poll(async () => Number(await page.getByTestId("library-grid").getAttribute("data-loaded")), {
      timeout: 20_000,
    })
    .toBe(5000);
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.scrollY);
  expect(Math.abs(after - before)).toBeLessThan(rowHeight);

  expect(csp).toEqual([]);
});

test("light and dark screenshots at desktop and mobile widths @library", async ({ page }) => {
  await installLibraryMock(page);
  const viewports = [
    { width: 1280, height: 900, label: "desktop" },
    { width: 390, height: 844, label: "mobile" },
  ];

  for (const theme of ["dark", "light"] as const) {
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto("/#/library");
      await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
      await page.reload();
      await libraryGrid(page);
      await page.screenshot({
        path: join(SHOTS, `library-${theme}-${viewport.label}.png`),
      });

      await page.goto("/#/browse");
      await expect(page.getByTestId("browse-grid")).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `browse-${theme}-${viewport.label}.png`),
      });
    }
  }
});
