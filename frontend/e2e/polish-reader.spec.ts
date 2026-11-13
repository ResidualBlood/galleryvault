import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { expect, test } from "./fixtures/mock";
import { mockPages } from "./fixtures/reader/pages";
import { READER_GID, READER_TOKEN } from "./fixtures/online-reader/data";
import { mockOnlineReaderBackend } from "./fixtures/online-reader/mock";
import {
  expectControlHeights,
  expectHitTargets,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
  freePort,
  watchCsp,
} from "./support/polish";

/**
 * po-reader polish gate.
 *
 * Closes the sixteen audit defects owned by this task (OR-01…OR-09, RD-01…RD-07)
 * with DOM-measured assertions instead of screenshots:
 *
 *   - both reader bars render registry SVG icons (never Unicode glyphs) and the
 *     bars disappear together with the online action strip;
 *   - every bar control sits on one control-ladder step with a shared centre
 *     line (>= 44px hit areas);
 *   - the page is printed once: the jump field stays empty until typed;
 *   - at 390 the right-hand bar controls keep their inset and nothing scrolls
 *     sideways; the page indicator stands in while the bars are hidden;
 *   - the settings sheet uses SegmentedControl / TextField / Button only.
 */

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");
const THEMES = ["dark", "light"] as const;
const VIEWPORTS = [
  { width: 1280, height: 900, label: "desktop" },
  { width: 390, height: 844, label: "mobile" },
] as const;

let vite: ViteDevServer;
let READER_HARNESS = "";
let ONLINE_HARNESS = "";


test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  READER_HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/reader/harness.html`;
  ONLINE_HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/online-reader/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

interface ReaderOptions {
  total?: number;
  page?: number;
  mode?: string;
  theme?: string;
  /** Load the gallery meta first so the loading state is observable. */
  meta?: boolean;
}

function readerUrl(options: ReaderOptions = {}): string {
  const params = new URLSearchParams();
  params.set("total", String(options.total ?? 12));
  params.set("page", String(options.page ?? 0));
  params.set("mode", options.mode ?? "ltr");
  params.set("fit", "height");
  if (options.theme) params.set("theme", options.theme);
  if (options.meta) params.set("meta", "1");
  params.set("id", "7");
  return `${READER_HARNESS}?${params.toString()}`;
}

function onlineUrl(theme: string): string {
  const params = new URLSearchParams();
  params.set("gid", String(READER_GID));
  params.set("token", READER_TOKEN);
  params.set("theme", theme);
  return `${ONLINE_HARNESS}?${params.toString()}`;
}

async function allowViteModules(page: Page): Promise<void> {
  // The shared mock fixture routes `**/api/**`; Vite serves the app from
  // `/src/**` and `/e2e/**`, which must reach the dev server untouched.
  await page.route("**/src/**", (route) => route.continue());
  await page.route("**/e2e/**", (route) => route.continue());
}

async function openLocal(page: Page, options: ReaderOptions = {}): Promise<void> {
  await allowViteModules(page);
  await page.goto(readerUrl(options));
  const shell = page.getByTestId("reader-shell");
  await expect(shell).toBeVisible();
  await expect(shell).toHaveAttribute("data-total", String(options.total ?? 12));
  await expect(page.getByTestId("reader-loading")).toHaveCount(0);
}

async function openOnline(page: Page, theme = "dark"): Promise<void> {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await allowViteModules(page);
  await mockOnlineReaderBackend(page);
  await page.goto(onlineUrl(theme));
  await expect(page.getByTestId("online-reader")).toBeVisible();
  try {
    await expect(page.getByTestId("reader-shell")).toBeVisible({ timeout: 20_000 });
  } catch (error) {
    throw new Error(`${(error as Error).message}\nconsole=${errors.join(" | ") || "none"}`);
  }
}

/**
 * The bars start hidden; a centre tap is how a reader calls them up. Webtoon
 * mode has no tap zones (the strip owns the gestures), so it falls back to the
 * stage's centre tap.
 */
async function showBars(page: Page): Promise<void> {
  const shell = page.getByTestId("reader-shell");
  if ((await shell.getAttribute("data-bars")) === "visible") return;
  if ((await shell.getAttribute("data-mode")) === "webtoon") {
    const box = await shell.boundingBox();
    if (!box) throw new Error("reader shell has no box");
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  } else {
    await page.getByTestId("reader-zone-center").click();
  }
  await expect(shell).toHaveAttribute("data-bars", "visible");
}

/** Read one control-ladder step as the browser resolved it. */
async function ladderStep(page: Page, token = "--gv-size-control-lg"): Promise<number> {
  const raw = await page.evaluate(
    (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim(),
    token,
  );
  return Number.parseFloat(raw);
}


/**
 * Four-variant screenshots for states that need an interaction (`shotMatrix`
 * only replays a URL). Same directory and naming convention as `shotMatrix`.
 */
async function stateMatrix(
  page: Page,
  name: string,
  urlFor: (variant: { theme: string; width: number }) => string,
  prepare: (variant: { theme: string; width: number }) => Promise<void>,
  options: { idle?: boolean } = {},
): Promise<string[]> {
  await allowViteModules(page);
  const files: string[] = [];
  for (const theme of THEMES) {
    for (const viewport of VIEWPORTS) {
      const errors: string[] = [];
      const onError = (error: Error): void => {
        errors.push(error.message);
      };
      const onConsole = (message: { type: () => string; text: () => string }): void => {
        if (message.type() === "error" || message.type() === "warning") {
          errors.push(`${message.type()}: ${message.text()}`);
        }
      };
      page.on("pageerror", onError);
      page.on("console", onConsole);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(urlFor({ theme, width: viewport.width }));
      if (options.idle !== false) {
        await page.waitForLoadState("networkidle").catch(() => {});
      }
      try {
        await prepare({ theme, width: viewport.width });
      } catch (error) {
        throw new Error(
          `${(error as Error).message}\nurl=${page.url()}\nconsole=${errors.join(" | ") || "none"}`,
        );
      } finally {
        page.off("pageerror", onError);
        page.off("console", onConsole);
      }
      await page.waitForTimeout(200);
      const file = join(SHOTS, `${name}-${theme}-${viewport.width}.png`);
      await page.screenshot({ path: file });
      files.push(file);
    }
  }
  await page.emulateMedia({ colorScheme: null });
  return files;
}

function boxCenters(page: Page, selector: string): Promise<number[]> {
  return page.$$eval(selector, (nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return Math.round((rect.top + rect.height / 2) * 10) / 10;
    }),
  );
}

test("@polish-reader bars use registry icons only (no character glyphs)", async ({ page }) => {
  const csp = watchCsp(page);
  await mockPages(page, { total: 12 });
  await openLocal(page);
  await showBars(page);

  for (const bar of ["reader-topbar", "reader-bottombar"]) {
    await expectNoGlyphIcons(page, { selector: `[data-testid="${bar}"]` });
  }

  const topIcons = page.locator('[data-testid="reader-topbar"] svg.gv-icon');
  const bottomIcons = page.locator('[data-testid="reader-bottombar"] svg.gv-icon');
  expect(await topIcons.count()).toBeGreaterThanOrEqual(2);
  expect(await bottomIcons.count()).toBeGreaterThanOrEqual(6);
  expect((await topIcons.count()) + (await bottomIcons.count())).toBeGreaterThanOrEqual(8);

  // Every icon is a real 20px SVG, not a font-sized glyph.
  const widths = await page
    .locator('[data-testid="reader-topbar"] svg.gv-icon, [data-testid="reader-bottombar"] svg.gv-icon')
    .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().width)));
  expect(new Set(widths)).toEqual(new Set([20]));

  expect(csp).toEqual([]);
});

test("@polish-reader bars share one control step and one centre line", async ({ page }) => {
  await mockPages(page, { total: 12 });
  await openLocal(page);
  await showBars(page);

  const step = await ladderStep(page);
  expect(step).toBeGreaterThan(0);

  for (const bar of ["reader-topbar", "reader-bottombar"]) {
    await expectControlHeights(
      page.locator(`[data-testid="${bar}"] [data-gv-control]`),
      step,
    );
  }
  await expectRowsAligned(page, { rowSelector: "[data-gv-toolbar]", requireRows: true });

  // The slider track sits on the same centre line as the icon buttons.
  const buttonCenters = await boxCenters(
    page,
    '[data-testid="reader-bottombar"] button[data-gv-control]',
  );
  const sliderCenters = await boxCenters(page, '[data-testid="reader-bottombar"] .slider__input');
  expect(sliderCenters).toHaveLength(1);
  for (const center of buttonCenters) {
    expect(Math.abs(center - sliderCenters[0])).toBeLessThanOrEqual(1);
  }

  // 44px hit areas: the 40px visual box is expanded, neighbours never cover it.
  for (const id of ["reader-first", "reader-prev", "reader-next", "reader-last", "reader-settings"]) {
    await expect(page.getByTestId(id)).toBeVisible();
  }
  await expectHitTargets(page.locator('[data-testid="reader-bottombar"] button'), 44);
  await expectHitTargets(page.locator('[data-testid="reader-topbar"] button'), 44);
});

test("@polish-reader prints the page once and keeps the jump field labelled", async ({ page }) => {
  await mockPages(page, { total: 12 });
  await openLocal(page, { total: 12, page: 3 });
  await showBars(page);

  const topbar = page.getByTestId("reader-topbar");
  const label = topbar.getByTestId("reader-page-label");
  const input = topbar.locator("input").first();

  await expect(label).toHaveText("第 4 / 12 页");
  // The field carries the aria-label and a placeholder, not a second copy of
  // the current page number (OR-03 / RD-03).
  await expect(input).toHaveAttribute("aria-label", "跳转到页");
  await expect(input).toHaveValue("");

  const text = await topbar.innerText();
  expect(text.split("第 4 / 12 页").length - 1).toBe(1);

  // Input and page text share the centre line.
  const centers = await boxCenters(page, '[data-testid="reader-topbar"] input, [data-testid="reader-page-label"]');
  expect(centers).toHaveLength(2);
  expect(Math.abs(centers[0] - centers[1])).toBeLessThanOrEqual(1);

  // Typing a page jumps once and clears the field again.
  await input.fill("9");
  await input.press("Enter");
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-page", "8");
  await expect(label).toHaveText("第 9 / 12 页");
  await expect(input).toHaveValue("");
});

test("@polish-reader 390 keeps bar controls inside the padding", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockPages(page, { total: 12 });
  await openLocal(page);
  await showBars(page);

  await expectNoHorizontalOverflow(page);

  const shell = page.getByTestId("reader-shell");
  const viewport = await shell.evaluate(() => window.innerWidth);
  const right = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll<HTMLElement>(
      '[data-testid="reader-topbar"] button[data-gv-control], [data-testid="reader-topbar"] input',
    )];
    return Math.max(...nodes.map((node) => node.getBoundingClientRect().right));
  });
  expect(right).toBeLessThanOrEqual(viewport - 4);
  expect(right).toBeGreaterThanOrEqual(viewport - 16);

  // The title steps aside, the spacer keeps the right-hand group flush.
  const titleVisible = await page
    .locator('[data-testid="reader-topbar"] .reader-topbar__title')
    .isVisible();
  expect(titleVisible).toBe(false);
});

test("@polish-reader page indicator stands in while the bars are hidden", async ({ page }) => {
  await mockPages(page, { total: 12 });
  await openLocal(page, { total: 12, page: 2 });

  const shell = page.getByTestId("reader-shell");
  await expect(shell).toHaveAttribute("data-bars", "hidden");
  const indicator = page.getByTestId("reader-page-indicator");
  await expect(indicator).toBeVisible();
  await expect(indicator).toHaveText("第 3 / 12 页");
  await expect(indicator).toHaveCSS("opacity", "1");

  await showBars(page);
  // The top bar owns the page while the bars are open (RD-05).
  await expect.poll(() => indicator.evaluate((node) => getComputedStyle(node).opacity)).toBe("0");
});

test("@polish-reader settings sheet uses shared controls", async ({ page }) => {
  const csp = watchCsp(page);
  await mockPages(page, { total: 12 });
  await openLocal(page);
  await showBars(page);
  await page.getByTestId("reader-settings").click();

  const panel = page.getByTestId("reader-settings-panel");
  await expect(panel).toBeVisible();
  await expectNoGlyphIcons(page, { selector: '[data-testid="reader-settings-panel"]' });

  const modeControl = page.getByTestId("reader-mode-control");
  const fitControl = page.getByTestId("reader-fit-control");
  await expect(modeControl.locator('[data-segmented-value]')).toHaveCount(5);
  await expect(fitControl.locator('[data-segmented-value]')).toHaveCount(3);

  // Mode uses icons + text; the current mode is the checked segment.
  await expect(modeControl.locator('[data-segmented-value="ltr"] svg.gv-icon')).toHaveCount(1);
  await expect(modeControl.locator('[data-segmented-value="ltr"]')).toHaveAttribute(
    "aria-checked",
    "true",
  );

  // Interval is a TextField with a unit suffix, the slideshow action a Button.
  const interval = page.getByTestId("reader-settings-interval").locator("input");
  await expect(interval).toHaveAttribute("aria-label", "轮播间隔");
  await expect(page.getByTestId("reader-settings-interval")).toContainText("秒");

  const step = await ladderStep(page);
  await expectControlHeights(
    panel.locator('[data-testid="reader-settings-interval"] input, [data-testid="reader-settings-slideshow"]'),
    step,
  );

  // Switching still persists (behaviour preserved, only the chrome changed).
  await modeControl.locator('[data-segmented-value="webtoon"]').click();
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-mode", "webtoon");
  await modeControl.locator('[data-segmented-value="ltr"]').click();
  expect(csp).toEqual([]);
});

test("@polish-reader online action strip rides with the bars", async ({ page }) => {
  const csp = watchCsp(page);
  await openOnline(page);

  const shell = page.getByTestId("reader-shell");
  const strip = page.getByTestId("online-reader-actions");

  // Hidden together with the bars: no third floating control group (OR-05).
  // The bar layer keeps its box (it slides out with a transform), so the
  // assertion is on the resolved opacity / hit-testing, not a bounding box.
  const layerOpacity = (): Promise<string> =>
    page.evaluate(() =>
      getComputedStyle(document.querySelector('[data-testid="online-reader-actions"]')!.closest(".reader__bar-layer")!).opacity,
    );
  await expect(shell).toHaveAttribute("data-bars", "hidden");
  await expect.poll(layerOpacity).toBe("0");
  await expect(strip).toHaveCSS("pointer-events", "none");

  await showBars(page);
  await expect(strip).toBeVisible();
  await expect.poll(layerOpacity).toBe("1");
  await expect(shell).toHaveAttribute("data-bars", "visible");

  // Image source is a segmented control; the wrapper keeps the mode hook.
  await expect(page.getByTestId("online-reader-mode")).toHaveAttribute("data-mode", "direct");
  await expect(
    page.getByTestId("online-reader-mode").locator('[data-segmented-value="proxy"]'),
  ).toBeVisible();

  // The strip sits directly above the bottom bar, inside the same right inset.
  const geometry = await page.evaluate(() => {
    const actions = document.querySelector('[data-testid="online-reader-actions"]')!.getBoundingClientRect();
    const bar = document.querySelector('[data-testid="reader-bottombar"]')!;
    const barBox = bar.getBoundingClientRect();
    const pad = Number.parseFloat(getComputedStyle(bar).paddingRight);
    return {
      actionsBottom: actions.bottom,
      actionsRight: actions.right,
      barTop: barBox.top,
      barContentRight: barBox.right - pad,
    };
  });
  expect(geometry.actionsBottom).toBeLessThanOrEqual(geometry.barTop + 1);
  expect(Math.abs(geometry.actionsRight - geometry.barContentRight)).toBeLessThanOrEqual(2);

  // Bar chrome itself carries no glyphs and stays centre-aligned.
  await expectNoGlyphIcons(page, { selector: '[data-testid="reader-topbar"]' });
  await expectNoGlyphIcons(page, { selector: '[data-testid="reader-bottombar"]' });
  await expectRowsAligned(page, { rowSelector: "[data-gv-toolbar]", requireRows: true });

  // Tapping the centre again hides the strip with the bars.
  await page.getByTestId("reader-zone-center").click();
  await expect(shell).toHaveAttribute("data-bars", "hidden");
  await expect.poll(layerOpacity).toBe("0");

  await expectNoHorizontalOverflow(page);
  expect(csp).toEqual([]);
});

test("@polish-reader online bars have dark/light x desktop/mobile screenshots", async ({ page }) => {
  await allowViteModules(page);
  await mockOnlineReaderBackend(page);

  const files = await stateMatrix(
    page,
    "online-reader-bars",
    ({ theme }) => onlineUrl(theme),
    async () => {
      await expect(page.getByTestId("online-reader")).toBeVisible();
      await expect(page.getByTestId("reader-shell")).toBeVisible({ timeout: 20_000 });
      await showBars(page);
    },
  );
  expect(files).toHaveLength(4);
});

test("@polish-reader bar states have dark/light x desktop/mobile screenshots", async ({ page }) => {
  await mockPages(page, { total: 12 });

  // Default state through the shared shotMatrix helper (bars hidden, indicator
  // visible) — the harness resolves the theme from the persisted `gv_theme`.
  await allowViteModules(page);
  // shotMatrix reads localStorage before the first capture, so land on the
  // harness origin first (about:blank denies storage access).
  await page.goto(readerUrl());
  await expect(page.getByTestId("reader-shell")).toBeVisible();
  const matrix = await shotMatrix(page, "reader-default", { url: readerUrl() });
  expect(matrix.files).toHaveLength(4);

  const bars = await stateMatrix(
    page,
    "reader-bars",
    ({ theme }) => readerUrl({ theme }),
    async () => {
      await expect(page.getByTestId("reader-shell")).toBeVisible();
      await expect(page.getByTestId("reader-loading")).toHaveCount(0);
      await showBars(page);
    },
  );
  expect(bars).toHaveLength(4);

  const settings = await stateMatrix(
    page,
    "reader-settings",
    ({ theme }) => readerUrl({ theme }),
    async () => {
      await expect(page.getByTestId("reader-shell")).toBeVisible();
      await showBars(page);
      await page.getByTestId("reader-settings").click();
      await expect(page.getByTestId("reader-settings-panel")).toBeVisible();
    },
  );
  expect(settings).toHaveLength(4);
});

test("@polish-reader loading and failure states use Icon + Button", async ({ page }) => {
  await allowViteModules(page);
  const galleryMeta = /\/api\/galleries\/7(?:\?.*)?$/;

  // Loading: the gallery meta is held back so the spinner state is on screen.
  await page.route(galleryMeta, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ page_count: 12, title: "Harness Gallery" }),
    });
  });
  const loading = await stateMatrix(
    page,
    "reader-loading",
    ({ theme }) => readerUrl({ theme, meta: true }),
    async () => {
      await expect(page.getByTestId("reader-loading")).toBeVisible();
      await expect(page.locator(".reader__spinner")).toBeVisible();
    },
    { idle: false },
  );
  expect(loading).toHaveLength(4);

  // Failure: ErrorState (icon + title + retry Button) instead of a bare line.
  await page.unroute(galleryMeta);
  await page.route(galleryMeta, (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );
  const failure = await stateMatrix(
    page,
    "reader-error",
    ({ theme }) => readerUrl({ theme, meta: true }),
    async () => {
      await expect(page.getByTestId("reader-error")).toBeVisible();
      await expect(page.getByTestId("reader-error-state")).toBeVisible();
      await expect(page.getByTestId("reader-error-state-retry")).toBeVisible();
    },
  );
  expect(failure).toHaveLength(4);
});

test("@polish-reader webtoon and double modes have screenshots", async ({ page }) => {
  await mockPages(page, { total: 12 });

  const webtoon = await stateMatrix(
    page,
    "reader-mode-webtoon",
    ({ theme }) => readerUrl({ theme, mode: "webtoon", page: 1 }),
    async () => {
      await expect(page.getByTestId("reader-shell")).toBeVisible();
      await expect(page.getByTestId("reader-loading")).toHaveCount(0);
      await expect(page.getByTestId("webtoon-strip")).toBeVisible();
      await showBars(page);
    },
  );
  expect(webtoon).toHaveLength(4);

  const double = await stateMatrix(
    page,
    "reader-mode-double",
    ({ theme }) => readerUrl({ theme, mode: "double", page: 2 }),
    async () => {
      await expect(page.getByTestId("reader-shell")).toBeVisible();
      await expect(page.getByTestId("reader-loading")).toHaveCount(0);
      await expect(page.locator('[data-testid="reader-page"]').first()).toBeVisible();
      await showBars(page);
    },
  );
  expect(double).toHaveLength(4);

  // Both modes surface the same two bars, so the chrome is identical.
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-mode", "double");
  await expect(page.getByTestId("reader-topbar")).toBeVisible();
  await expect(page.getByTestId("reader-bottombar")).toBeVisible();
});
