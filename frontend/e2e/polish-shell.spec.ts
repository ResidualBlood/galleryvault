import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Locator } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * po-shell polish gate.
 *
 * Covers the ten audit defects owned by this task (SH-01 … SH-08, RD-08,
 * LG2-02) with DOM-measured assertions so they cannot silently regress:
 *
 *   - icons are inline SVG from the registry (24px nav / 20px topbar), never
 *     Unicode characters;
 *   - every topbar / toolbar control sits on one control-ladder step;
 *   - all 15 destinations are reachable below 840px through the sheet;
 *   - the drawer / rail are sticky and keep settings + logs in view on a
 *     12 000px page;
 *   - reader routes are immersive and the document does not scroll;
 *   - no horizontal overflow at 390, and the cookie banner does not cover it.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

/** All 15 navigation destinations, in render order. */
const DESTINATIONS: Array<{ path: string; nav: string }> = [
  { path: "/browse", nav: "app.nav.browse" },
  { path: "/online", nav: "app.nav.online" },
  { path: "/library", nav: "app.nav.library" },
  { path: "/favorites", nav: "app.nav.favorites" },
  { path: "/downloads", nav: "app.nav.downloads" },
  { path: "/series", nav: "app.nav.series" },
  { path: "/tags", nav: "app.nav.tags" },
  { path: "/history", nav: "app.nav.history" },
  { path: "/updates", nav: "app.nav.updates" },
  { path: "/duplicates", nav: "app.nav.duplicates" },
  { path: "/recycle", nav: "app.nav.recycle" },
  { path: "/integrity", nav: "app.nav.integrity" },
  { path: "/archive", nav: "app.nav.archive" },
  { path: "/settings", nav: "app.nav.settings" },
  { path: "/logs", nav: "app.nav.logs" },
];

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

async function iconSize(scope: Locator): Promise<number[]> {
  return scope.evaluateAll((nodes) =>
    nodes.map((node) => Math.round(node.getBoundingClientRect().width)),
  );
}

test("@polish-shell topbar and navigation use registry SVG icons", async ({ page }) => {
  await page.goto("/");
  const topbar = page.getByTestId("topbar");
  const drawer = page.getByTestId("nav-drawer");
  await expect(topbar).toBeVisible();
  await expect(drawer).toBeVisible();

  // SH-01 / SH-02: zero character icons anywhere in the chrome.
  await expectNoGlyphIcons(page, { selector: "[data-testid='topbar']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='nav-drawer']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='nav-rail']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='nav-bottom']" });

  // 15 fixed destinations + topbar actions + rail + bottom bar.
  const drawerIcons = drawer.locator("svg.gv-icon");
  await expect(drawerIcons).toHaveCount(15);
  expect(await iconSize(drawerIcons)).toEqual(Array(15).fill(24));

  const topbarIcons = topbar.locator("svg.gv-icon");
  expect(await topbarIcons.count()).toBeGreaterThanOrEqual(5);
  expect(await iconSize(topbarIcons)).toEqual(Array(await topbarIcons.count()).fill(20));

  const shellIcons = page.locator(
    "[data-testid='topbar'] svg.gv-icon, [data-testid='nav-drawer'] svg.gv-icon, [data-testid='nav-rail'] svg.gv-icon, [data-testid='nav-bottom'] svg.gv-icon",
  );
  expect(await shellIcons.count()).toBeGreaterThanOrEqual(20);

  // Every topbar action is the same 44px hit target on the touch ladder.
  await expectControlHeights(topbar.locator("button"), 44);
});

test("@polish-shell topbar brand and title are separated once", async ({ page }) => {
  await page.goto("/#/browse");
  const topbar = page.getByTestId("topbar");
  await expect(topbar).toBeVisible();

  const brand = topbar.locator(".shell__brand");
  const title = topbar.locator(".shell__page-title");
  const brandBox = await brand.boundingBox();
  const titleBox = await title.boundingBox();
  expect(brandBox && titleBox).toBeTruthy();
  // SH-03: brand / 1px divider / title, >= 16px apart (not a 4px run-on).
  expect(titleBox!.x - (brandBox!.x + brandBox!.width)).toBeGreaterThanOrEqual(16);

  // The welcome route uses the app title as its page title; print it once.
  await page.goto("/#/welcome");
  await expect(topbar).toBeVisible();
  const text = (await topbar.innerText()).replace(/\s+/g, " ").trim();
  expect(text.match(/GalleryVault/g)?.length ?? 0).toBe(1);
  await expect(topbar).not.toContainText("GalleryVault GalleryVault");
});

test("@polish-shell all destinations are reachable at 390 via more", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("nav-bottom")).toBeVisible();

  const sheet = page.getByTestId("nav-sheet");
  await page.getByTestId("bottom-more").click();
  await expect(sheet).toBeVisible();
  await expect(sheet.locator("[data-nav]")).toHaveCount(15);

  // Current page is highlighted in the sheet.
  const current = sheet.locator('[data-nav="app.nav.browse"]');
  await expect(current).toHaveClass(/router-link-active/);
  await expect(current).toHaveAttribute("aria-current", "page");

  for (const destination of DESTINATIONS) {
    if (!(await sheet.isVisible())) await page.getByTestId("bottom-more").click();
    await expect(sheet).toBeVisible();
    await page.waitForTimeout(240);
    await sheet.locator(`[data-nav="${destination.nav}"]`).click();
    await expect(page).toHaveURL(new RegExp(`#${destination.path}$`));
    await expect(sheet).toBeHidden();
  }
});

test("@polish-shell all destinations are reachable at 700 via menu", async ({ page }) => {
  await page.setViewportSize({ width: 700, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("nav-rail")).toBeVisible();

  const sheet = page.getByTestId("nav-sheet");
  for (const destination of DESTINATIONS) {
    if (!(await sheet.isVisible())) await page.getByTestId("drawer-toggle").click();
    await expect(sheet).toBeVisible();
    await page.waitForTimeout(240);
    await sheet.locator(`[data-nav="${destination.nav}"]`).click();
    await expect(page).toHaveURL(new RegExp(`#${destination.path}$`));
    await expect(sheet).toBeHidden();
  }
});

test("@polish-shell drawer stays in view on a 12000px page", async ({ page }) => {
  await page.goto("/#/browse");
  const drawer = page.getByTestId("nav-drawer");
  await expect(drawer).toBeVisible();

  await page.getByTestId("content").evaluate((content) => {
    const filler = document.createElement("div");
    filler.setAttribute("data-testid", "tall-filler");
    filler.style.height = "12000px";
    content.appendChild(filler);
  });

  const scrollHeight = await page.evaluate(() => document.scrollingElement?.scrollHeight ?? 0);
  expect(scrollHeight).toBeGreaterThan(10000);

  await page.evaluate(() => window.scrollTo(0, document.scrollingElement?.scrollHeight ?? 0));
  const viewportHeight = await page.evaluate(() => window.innerHeight);
  const box = await drawer.boundingBox();
  expect(box).not.toBeNull();
  // LG2-02: sticky under the 56px topbar instead of growing with the document.
  expect(box!.y).toBeLessThanOrEqual(57);
  expect(Math.round(box!.height)).toBe(viewportHeight - 56);

  await expect(drawer.locator('[data-nav="app.nav.settings"]')).toBeInViewport();
  await expect(drawer.locator('[data-nav="app.nav.logs"]')).toBeInViewport();

  // Rail is sticky at the compact breakpoint too.
  await page.setViewportSize({ width: 700, height: 900 });
  await page.evaluate(() => window.scrollTo(0, document.scrollingElement?.scrollHeight ?? 0));
  const rail = page.getByTestId("nav-rail");
  await expect(rail).toBeVisible();
  const railBox = await rail.boundingBox();
  expect(railBox!.y).toBeLessThanOrEqual(57);

  // Evidence: a 12 000px page scrolled to the end still shows settings / logs.
  await page.setViewportSize({ width: 1280, height: 900 });
  for (const theme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
    await page.reload();
    await page.getByTestId("content").evaluate((content) => {
      const filler = document.createElement("div");
      filler.style.height = "12000px";
      content.appendChild(filler);
    });
    await page.evaluate(() => window.scrollTo(0, document.scrollingElement?.scrollHeight ?? 0));
    await page.waitForTimeout(150);
    await page.screenshot({
      path: join(SHOTS, `shell-tall-page-${theme}-1280.png`),
    });
  }
});

test("@polish-shell reader routes are immersive and do not scroll", async ({ page }) => {
  const svgPage = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200"><rect width="100%" height="100%" fill="#f4f1ea"/><text x="50%" y="50%" text-anchor="middle" font-family="sans-serif" font-size="64" fill="#1c1a17">Reader page</text></svg>`;
  await page.route(/\/api\/galleries\/7\/pages\/\d+$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/svg+xml", body: svgPage }),
  );
  await page.route("**/api/galleries/7/progress", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ current_page: 0, total_pages: 3 }),
    }),
  );
  await page.route("**/api/galleries/7", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 7,
        gid: 7,
        token: "abcdef",
        title: "Shell reader fixture",
        page_count: 3,
        pages: [
          { index: 0, media_type: "image" },
          { index: 1, media_type: "image" },
          { index: 2, media_type: "image" },
        ],
      }),
    }),
  );

  for (const path of ["#/reader/7/0", "#/online/g/1/abcdef/read/0"]) {
    await page.goto(`/${path}`);
    await expect(page.getByTestId("content")).toBeVisible();
    // RD-08: no shell bars on immersive routes.
    await expect(page.getByTestId("topbar")).toHaveCount(0);
    await expect(page.getByTestId("nav-drawer")).toHaveCount(0);
    await expect(page.getByTestId("nav-bottom")).toHaveCount(0);

    const dims = await page.evaluate(() => ({
      scrollHeight: document.scrollingElement?.scrollHeight ?? 0,
      innerHeight: window.innerHeight,
    }));
    expect(dims.scrollHeight).toBe(dims.innerHeight);
  }

  // Evidence: RD-08 after state at 1280 / 390, both themes.
  for (const variant of [
    { theme: "dark", width: 1280, height: 900 },
    { theme: "light", width: 1280, height: 900 },
    { theme: "dark", width: 390, height: 844 },
    { theme: "light", width: 390, height: 844 },
  ] as const) {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.emulateMedia({ colorScheme: variant.theme });
    await page.evaluate((value) => localStorage.setItem("gv_theme", value), variant.theme);
    await page.goto("/#/reader/7/0");
    await page.reload();
    await expect(page.getByTestId("content")).toBeVisible();
    await page.waitForTimeout(300);
    expect(
      await page.evaluate(
        () => document.scrollingElement?.scrollHeight === window.innerHeight,
      ),
    ).toBe(true);
    await page.screenshot({
      path: join(SHOTS, `shell-reader-${variant.theme}-${variant.width}.png`),
    });
  }
});

test("@polish-shell cookie banner uses one control step and never covers content", async ({
  page,
}) => {
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        auth_required: true,
        must_change_password: false,
        cookie_health: { state: "not_configured" },
      }),
    }),
  );
  await page.route("**/api/settings/cookie-health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ state: "not_configured" }),
    }),
  );

  await page.goto("/#/browse");
  const banner = page.getByTestId("cookie-health-banner");
  await expect(banner).toBeVisible();

  // SH-05: both actions are Buttons on the same 40px ladder step.
  await expectControlHeights(banner.locator("button"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='cookie-health-banner'] [data-gv-toolbar]",
    requireRows: true,
  });

  // SH-07: single row on 390 and in normal flow (no overlap with content).
  await page.setViewportSize({ width: 390, height: 844 });
  const bannerBox = await banner.boundingBox();
  const contentBox = await page.getByTestId("content").boundingBox();
  expect(bannerBox!.height).toBeLessThanOrEqual(56);
  expect(bannerBox!.y + bannerBox!.height).toBeLessThanOrEqual(contentBox!.y + 1);
  await expectNoHorizontalOverflow(page);

  await banner.getByTestId("cookie-banner-settings").click();
  await expect(page).toHaveURL(/#\/settings$/);
});

test("@polish-shell notification and global panels use icons on one step", async ({ page }) => {
  await page.goto("/#/browse");
  await expect(page.getByTestId("topbar")).toBeVisible();

  await page.getByTestId("notifications").click();
  const panel = page.getByTestId("notification-panel");
  await expect(panel).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='notification-panel']" });
  await expectControlHeights(panel.locator("button"), 32);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='notification-panel'] [data-gv-toolbar]",
    requireRows: true,
  });

  await page.getByTestId("global-controls-toggle").click();
  const global = page.getByTestId("global-controls");
  await expect(global).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='global-controls']" });
  await expectControlHeights(global.locator("[data-gv-toolbar] > button"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='global-controls'] [data-gv-toolbar]",
    requireRows: true,
  });
});

test("@polish-shell 390 shell has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/browse");
  await expect(page.getByTestId("nav-bottom")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByTestId("bottom-more").click();
  await expect(page.getByTestId("nav-sheet")).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("@polish-shell screenshot matrix", async ({ page }) => {
  await page.goto("/#/browse");
  await shotMatrix(page, "shell-browse");

  await page.goto("/#/logs");
  await shotMatrix(page, "shell-logs");

  // Sheet state: open it after each variant reload (shotMatrix has no hook).
  const variants = [
    { theme: "dark", width: 1280, height: 900 },
    { theme: "light", width: 1280, height: 900 },
    { theme: "dark", width: 390, height: 844 },
    { theme: "light", width: 390, height: 844 },
  ] as const;
  const files: string[] = [];
  for (const variant of variants) {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.emulateMedia({ colorScheme: variant.theme });
    await page.evaluate((theme) => localStorage.setItem("gv_theme", theme), variant.theme);
    await page.goto("/#/browse");
    await page.reload();
    await expect(page.getByTestId("topbar")).toBeVisible();
    if (variant.width >= 840) {
      await expect(page.getByTestId("nav-drawer")).toBeVisible();
    } else {
      await page.getByTestId("bottom-more").click();
      await expect(page.getByTestId("nav-sheet")).toBeVisible();
    }
    await page.waitForTimeout(250);
    files.push(join(SHOTS, `shell-nav-${variant.theme}-${variant.width}.png`));
    await page.screenshot({ path: files[files.length - 1] });
  }
  expect(files).toHaveLength(4);

  // Cookie-banner state (SH-05 / SH-07) in the same four variants.
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        auth_required: true,
        must_change_password: false,
        cookie_health: { state: "not_configured" },
      }),
    }),
  );
  await page.route("**/api/settings/cookie-health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ state: "not_configured" }),
    }),
  );
  for (const variant of variants) {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.emulateMedia({ colorScheme: variant.theme });
    await page.evaluate((theme) => localStorage.setItem("gv_theme", theme), variant.theme);
    await page.goto("/#/browse");
    await page.reload();
    await expect(page.getByTestId("cookie-health-banner")).toBeVisible();
    await page.waitForTimeout(200);
    await page.screenshot({
      path: join(SHOTS, `shell-cookie-banner-${variant.theme}-${variant.width}.png`),
    });
  }
});
