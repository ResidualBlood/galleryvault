import { createHash } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";

import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  shotMatrix,
  freePort,
  watchCsp,
} from "./support/polish";

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");
const GROUPS = [
  "appearance",
  "reader",
  "network",
  "online",
  "library",
  "download",
  "favorites",
  "archive",
  "tags",
  "notifications",
  "account",
  "integrations",
  "system",
] as const;

let vite: ViteDevServer;
let HARNESS = "";



function harnessUrl(options: { group?: string; theme?: "dark" | "light" } = {}): string {
  const params = new URLSearchParams({ view: "settings" });
  if (options.theme) params.set("theme", options.theme);
  if (options.group) params.set("group", options.group);
  return `${HARNESS}?${params.toString()}`;
}

function groupUrl(id: string): string {
  return `${harnessUrl()}#/settings/${id}`;
}

async function openGroup(page: Page, id: string): Promise<void> {
  await page.goto(groupUrl(id));
  await expect(page.locator(`[data-settings-group="${id}"]`)).toBeVisible();
}

interface LayoutMetrics {
  rows: number;
  xSpread: number;
  widthSpread: number;
  rightSpread: number;
  centreViolations: string[];
  multilineViolations: string[];
  actionHeights: number[];
  titleSize: number;
  navIcons: number;
  navTopDelta: number;
  navBaselineDelta: number;
}

async function measureLayout(page: Page): Promise<LayoutMetrics> {
  return page.evaluate(() => {
    const visible = (el: Element | null): boolean => {
      if (!el) return false;
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return (
        rect.width > 1 &&
        rect.height > 1 &&
        style.visibility !== "hidden" &&
        style.display !== "none"
      );
    };
    const round = (value: number): number => Math.round(value * 10) / 10;
    const spread = (values: number[]): number =>
      values.length ? round(Math.max(...values) - Math.min(...values)) : 0;

    const rows = [...document.querySelectorAll("[data-settings-group] [data-setting-key]")];
    const centreViolations: string[] = [];
    const multilineViolations: string[] = [];
    const controls: Element[] = [];
    const rights: number[] = [];

    for (const row of rows) {
      const control = row.querySelector(".row__control");
      if (!visible(control)) continue;
      const first = control?.querySelector("[data-gv-control], .row__value") ?? null;
      if (!visible(first) || !first) continue;
      controls.push(first);
      rights.push(first.getBoundingClientRect().right);
      const kind = row.getAttribute("data-setting-control") ?? "";
      const title = row.querySelector(".row__title");
      if (!visible(title) || !title) continue;
      const titleRect = title.getBoundingClientRect();
      const controlRect = first.getBoundingClientRect();
      const key = row.getAttribute("data-setting-key") ?? "";
      if (kind === "textarea") {
        // Multi-line controls align on the top edge, not the centre line.
        const delta = Math.abs(titleRect.top - controlRect.top);
        if (delta > 2) multilineViolations.push(`${key}: top delta ${round(delta)}px`);
        continue;
      }
      if (kind === "online-defaults") continue;
      const titleCentre = titleRect.top + titleRect.height / 2;
      const controlCentre = controlRect.top + controlRect.height / 2;
      const delta = Math.abs(titleCentre - controlCentre);
      if (delta > 2) centreViolations.push(`${key}: centre delta ${round(delta)}px`);
    }

    // Switch and read-only slots share the same right edge as inputs/selects.
    for (const el of document.querySelectorAll(
      "[data-settings-group] .switch, [data-settings-group] .row__value",
    )) {
      if (visible(el)) rights.push(el.getBoundingClientRect().right);
    }

    const textControls = [
      ...document.querySelectorAll(
        "[data-settings-group] input.field__control, [data-settings-group] select.select-field__control",
      ),
    ].filter(visible);
    const xs = textControls.map((el) => el.getBoundingClientRect().left);
    const widths = textControls.map((el) => el.getBoundingClientRect().width);

    const actionHeights = [
      ...document.querySelectorAll("[data-settings-actions] button, [data-settings-actions] a"),
    ]
      .filter(visible)
      .map((el) => round(el.getBoundingClientRect().height));

    const navTitle = document.querySelector(".settings__nav-title");
    const groupTitle = document.querySelector(".group__title");
    const navItem = document.querySelector("[data-settings-nav]");
    const fields = document.querySelector(".group__fields");
    const navBaselineDelta =
      navTitle && groupTitle
        ? round(Math.abs(navTitle.getBoundingClientRect().top - groupTitle.getBoundingClientRect().top))
        : 0;
    const navTopDelta =
      navItem && fields
        ? round(Math.abs(navItem.getBoundingClientRect().top - fields.getBoundingClientRect().top))
        : 0;

    const h1 = document.querySelector("[data-testid='settings-header'] h1");
    const titleSize = h1 ? Number.parseFloat(getComputedStyle(h1).fontSize) : 0;
    const navIcons = document.querySelectorAll("[data-settings-nav] svg").length;

    return {
      rows: rows.length,
      xSpread: spread(xs),
      widthSpread: spread(widths),
      rightSpread: spread(rights),
      centreViolations,
      multilineViolations,
      actionHeights: [...new Set(actionHeights)],
      titleSize,
      navIcons,
      navTopDelta,
      navBaselineDelta,
    };
  });
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/settings-sys/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

test.beforeEach(async ({ page, baseURL }) => {
  await page.context().addCookies([
    { name: "galleryvault_csrf", value: "test-csrf", url: HARNESS },
    { name: "galleryvault_csrf", value: "test-csrf", url: baseURL ?? "http://127.0.0.1" },
  ]);
});

test.describe("settings polish @polish-settings", () => {
  test("13 groups share one control column, one height step and one title baseline @polish-settings", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    const csp = watchCsp(page);
    await page.setViewportSize({ width: 1280, height: 900 });

    for (const group of GROUPS) {
      await openGroup(page, group);
      await expectNoGlyphIcons(page, { selector: "[data-testid='settings-content']" });

      const metrics = await measureLayout(page);
      expect(metrics.rows, `${group}: rows`).toBeGreaterThan(0);
      expect(metrics.xSpread, `${group}: Select/TextField left edges`).toBeLessThanOrEqual(1);
      expect(metrics.widthSpread, `${group}: Select/TextField widths`).toBeLessThanOrEqual(1);
      expect(metrics.rightSpread, `${group}: right edges (controls, switch, value slot)`).toBeLessThanOrEqual(1);
      expect(metrics.centreViolations, `${group}: title first line vs control centre`).toEqual([]);
      expect(metrics.multilineViolations, `${group}: multiline top edges`).toEqual([]);
      expect(metrics.actionHeights.length, `${group}: action heights`).toBeLessThanOrEqual(1);
      expect(metrics.titleSize, `${group}: h1 uses headline-small`).toBe(24);
      expect(metrics.navIcons, `${group}: nav items carry an icon`).toBe(GROUPS.length);
      expect(metrics.navBaselineDelta, `${group}: nav title baseline`).toBeLessThanOrEqual(1);
      expect(metrics.navTopDelta, `${group}: first nav item aligns with the panel top`).toBeLessThanOrEqual(1);

      await expectControlHeights(
        page.locator("[data-testid='settings-content'] input.field__control, [data-testid='settings-content'] select.select-field__control"),
        40,
        { allowEmpty: true },
      );
    }

    expect(csp).toEqual([]);
  });

  test("narrow viewport stacks rows without horizontal overflow @polish-settings", async ({ page }) => {
    test.setTimeout(180_000);
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    const csp = watchCsp(page);
    await page.setViewportSize({ width: 390, height: 844 });

    for (const group of GROUPS) {
      await openGroup(page, group);
      await expect(page.getByTestId("settings-nav")).toBeHidden();
      await expectNoHorizontalOverflow(page);
      const stacked = await page.evaluate(() => {
        const rows = [...document.querySelectorAll("[data-setting-key]")];
        const problems: string[] = [];
        for (const row of rows) {
          const control = row.querySelector(".row__control");
          if (!control) continue;
          const rowRect = row.getBoundingClientRect();
          const controlRect = control.getBoundingClientRect();
          if (controlRect.width + 1 < rowRect.width - 32) {
            problems.push(`${row.getAttribute("data-setting-key")}: control ${Math.round(controlRect.width)} / row ${Math.round(rowRect.width)}`);
          }
        }
        return problems;
      });
      expect(stacked, `${group}: controls fill the stacked row`).toEqual([]);
    }

    expect(csp).toEqual([]);
  });

  test("group sub-pages live in the route and the back button returns to the index @polish-settings", async ({
    page,
  }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto(harnessUrl());
    await expect(page.getByTestId("settings-nav")).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/settings");

    await page.locator('[data-settings-nav="download"]').click();
    await expect(page.locator('[data-settings-group="download"]')).toBeVisible();
    await expect(page.getByTestId("settings-nav")).toBeHidden();
    expect(new URL(page.url()).hash).toBe("#/settings/download");

    await page.goBack();
    await expect(page.getByTestId("settings-nav")).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/settings");

    // Direct deep link (no click) opens the same sub-page.
    await page.goto(`${harnessUrl()}#/settings/archive`);
    await expect(page.locator('[data-settings-group="archive"]')).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/settings/archive");

    // Unknown groups fall back to the index instead of rendering nothing.
    await page.goto(`${harnessUrl()}#/settings/not-a-group`);
    await expect(page.getByTestId("settings-nav")).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/settings");
  });

  test("search hits deep-link to the owning group and locate the row @polish-settings", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    await page.setViewportSize({ width: 1280, height: 900 });

    await page.goto(harnessUrl());
    await page.getByTestId("settings-search").locator("input").fill("socks5_proxy");
    await page.locator('[data-result-key="socks5_proxy"]').click();

    await expect(page.locator('[data-settings-group="network"]')).toBeVisible();
    await expect(page.locator('[data-setting-key="socks5_proxy"]')).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/settings/network");
    await expect(page.getByTestId("settings-search").locator("input")).toHaveValue("");
  });

  test("dirty state shows a save bar above the mobile nav bar @polish-settings", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    await page.setViewportSize({ width: 390, height: 844 });

    await openGroup(page, "download");
    await expect(page.getByTestId("settings-savebar")).toHaveCount(0);

    await page.locator('[data-setting-key="download_concurrency"] input').fill("8");
    const bar = page.getByTestId("settings-savebar");
    await expect(bar).toBeVisible();
    await expect(bar).toContainText("1");

    const box = await bar.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.y + box.height, "save bar must sit above the 80px nav bar").toBeLessThanOrEqual(844 - 80);
      expect(box.y).toBeGreaterThan(0);
    }
    const navHeight = await page.evaluate(() =>
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--gv-size-navbar") || "80",
      ),
    );
    expect(navHeight).toBe(80);
  });

  test("every group renders in both themes at 1280 and 390 @polish-settings", async ({ page }) => {
    test.setTimeout(300_000);
    mkdirSync(SHOTS, { recursive: true });
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);

    await page.goto(harnessUrl());
    await shotMatrix(page, "settings-00-index", {
      url: harnessUrl(),
      fullPage: true,
      dir: SHOTS,
    });
    for (const group of GROUPS) {
      await shotMatrix(page, `settings-${group}`, {
        url: groupUrl(group),
        fullPage: true,
        dir: SHOTS,
      });
    }

    const dir = SHOTS;
    const hashes = GROUPS.map((group) =>
      createHash("sha1").update(readFileSync(join(dir, `settings-${group}-dark-390.png`))).digest("hex"),
    );
    expect(new Set(hashes).size, "390px group screenshots must differ").toBe(GROUPS.length);
  });
});
