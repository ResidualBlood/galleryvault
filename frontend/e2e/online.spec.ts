import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { ehSearchEp } from "../src/api/eh";
import { mockOnlineBackend } from "./fixtures/online/mock";
import {
  LIST_GID,
  LIST_TOKEN,
  NEWER_GID,
  NEWER_TOKEN,
  PAGE_CURSOR,
} from "./fixtures/online/data";

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

function watchConsole(page: Page): string[] {
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

function detailUrl(gid = LIST_GID, token = LIST_TOKEN): string {
  return `/#/online/g/${gid}/${token}`;
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

test.describe("online browse @online", () => {
  test("search updates the URL and renders matching cards", async ({ page }) => {
    const csp = watchConsole(page);
    await mockOnlineBackend(page);

    await page.goto("/#/discover");
    await expect(page.getByTestId("online-view")).toBeVisible();
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "12");

    await page.getByTestId("online-search").locator("input").fill("match");
    await page.getByTestId("online-submit").click();

    await expect(page).toHaveURL(/q=match/);
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "1");
    await expect(page.getByTestId("gallery-card").first()).toContainText(
      "Search Match: match",
    );
    expect(csp).toEqual([]);
  });

  test("cursor infinite scroll loads page two and back restores the list", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    await mockOnlineBackend(page);
    const searches: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === ehSearchEp.path) searches.push(url.search);
    });

    await page.goto("/#/online");
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "12");

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "18");
    expect(searches.some((query) => query.includes(`next=${PAGE_CURSOR}`))).toBe(true);

    await page.evaluate(() => window.scrollTo(0, 700));
    await expect.poll(() => page.evaluate(() => Math.round(window.scrollY))).toBe(700);
    // The row's tag line sits on the vertical centre; click the title area so
    // the card link opens the detail page (tags intentionally search instead).
    await page.getByTestId("gallery-card").nth(4).click({ position: { x: 200, y: 20 } });

    await expect(page).toHaveURL(new RegExp(`#/online/g/\\d+/tok\\d+$`));
    await expect(page.getByTestId("online-title")).toHaveText("Online Detail Fixture");

    await page.goBack();
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "18");
    await expect
      .poll(() => page.evaluate(() => Math.round(window.scrollY)))
      .toBeGreaterThan(400);
    const restored = await page.evaluate(() => Math.round(window.scrollY));
    expect(Math.abs(restored - 700)).toBeLessThan(300);
    expect(csp).toEqual([]);
  });

  test("detail renders contract fields, official link, no iframe and page placeholders", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    await mockOnlineBackend(page);

    await page.goto(detailUrl());
    await expect(page.getByTestId("online-detail-view")).toBeVisible();
    await expect(page.getByTestId("online-title")).toHaveText("Online Detail Fixture");
    await expect(page.locator('[data-testid="tag-group"]')).toHaveCount(5);
    await expect(page.getByTestId("online-newer")).toBeVisible();

    const official = page.getByTestId("online-official");
    await expect(official).toHaveAttribute(
      "href",
      `https://exhentai.org/g/${LIST_GID}/${LIST_TOKEN}/`,
    );
    await expect(official).toHaveAttribute("target", "_blank");
    await expect(official).toHaveAttribute("rel", "noopener noreferrer");
    expect(await page.locator("iframe").count()).toBe(0);

    await expect
      .poll(async () => Number(await page.getByTestId("online-thumbs").getAttribute("data-loaded")))
      .toBeGreaterThanOrEqual(20);
    const placeholders = page.getByTestId("online-thumb-placeholder");
    expect(await placeholders.count()).toBeGreaterThan(0);
    await expect(placeholders.first()).toContainText("2");

    await page.getByTestId("online-read").click();
    await expect(page).toHaveURL(
      new RegExp(`#/online/g/${LIST_GID}/${LIST_TOKEN}/read/0$`),
    );
    expect(csp).toEqual([]);
  });

  test("in-library fixture offers the local copy and newer-version navigation", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    await mockOnlineBackend(page);

    await page.goto(detailUrl(NEWER_GID, NEWER_TOKEN));
    await expect(page.getByTestId("online-title")).toHaveText(
      "Online Detail Fixture (newer)",
    );
    const local = page.getByTestId("online-open-local");
    await expect(local).toBeVisible();
    await expect(local).toHaveAttribute("href", /#\/gallery\/42$/);
    expect(csp).toEqual([]);
  });

  test("preview thumbnails load one page at a time on mobile", async ({ page }) => {
    const csp = watchConsole(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await mockOnlineBackend(page);
    const requested: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.endsWith("/pages")) requested.push(url.search);
    });

    await page.goto(detailUrl());
    await expect(page.getByTestId("online-thumbs")).toHaveAttribute("data-loaded", "20");
    expect(requested.some((query) => query.includes("p=1"))).toBe(false);

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect
      .poll(() => requested.some((query) => query.includes("p=1")))
      .toBe(true);
    await expect(page.getByTestId("online-thumbs")).toHaveAttribute("data-loaded", "32");
    expect(csp).toEqual([]);
  });

  test("auth state points at settings, banned state shows a ban notice", async ({ page }) => {
    const csp = watchConsole(page);
    await mockOnlineBackend(page);

    await page.goto("/#/online?q=__auth__");
    const auth = page.getByTestId("online-state-auth");
    await expect(auth).toBeVisible();
    const settings = auth.getByTestId("online-state-settings");
    await expect(settings).toBeVisible();
    await expect(settings).toHaveAttribute("href", /#\/settings$/);

    await page.goto("/#/online?q=__banned__");
    const banned = page.getByTestId("online-state-banned");
    await expect(banned).toBeVisible();
    await expect(banned).toContainText("封禁");
    expect(await page.locator("iframe").count()).toBe(0);
    expect(csp).toEqual([]);
  });

  test("screenshots cover dark/light x desktop/mobile", async ({ page }) => {
    const csp = watchConsole(page);
    await mockOnlineBackend(page);
    const themes = ["dark", "light"] as const;
    const viewports = [
      { width: 1280, height: 900, label: "1280" },
      { width: 390, height: 844, label: "390" },
    ];

    for (const theme of themes) {
      for (const viewport of viewports) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto("/#/online");
        await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
        await page.reload();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "12");
        await page.screenshot({
          path: join(SHOTS, `online-list-${theme}-${viewport.label}.png`),
          fullPage: true,
        });

        await page.goto(detailUrl());
        await expect(page.getByTestId("online-title")).toBeVisible();
        await page.screenshot({
          path: join(SHOTS, `online-detail-${theme}-${viewport.label}.png`),
          fullPage: true,
        });
      }
    }
    expect(csp).toEqual([]);
  });
});
