import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures/mock";
import type { Page } from "@playwright/test";
import { watchCsp } from "./support/polish";

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");
const UPDATE_EVENT = "gv-pwa-update-available";
const API_PREFIX = ["", "api", ""].join("/");

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});


async function waitForServiceWorker(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller), null, {
    timeout: 20_000,
  });
}

async function cacheKeys(page: Page): Promise<string[]> {
  return page.evaluate(() => caches.keys());
}

async function cachedUrls(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const urls: string[] = [];
    for (const key of await caches.keys()) {
      const cache = await caches.open(key);
      for (const request of await cache.keys()) urls.push(request.url);
    }
    return urls;
  });
}

function announceUpdate(page: Page): Promise<void> {
  return page.evaluate((event: string) => {
    window.dispatchEvent(new Event(event));
  }, UPDATE_EVENT);
}

test("SW activates at /sw.js and deletes legacy gv-shell-* caches @pwa", async ({ page }) => {
  // Seed the old worker's cache from a non-app document so it exists before
  // the new worker registers and activates.
  await page.goto("/sw.js");
  await page.evaluate(async () => {
    const cache = await caches.open("gv-shell-v14");
    await cache.put("/legacy-shell-probe", new Response("legacy shell"));
  });

  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await waitForServiceWorker(page);

  const registration = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.getRegistration();
    return { scope: reg?.scope ?? "", active: reg?.active?.scriptURL ?? "" };
  });
  expect(registration.scope).toContain("/");
  expect(registration.active).toContain("/sw.js");

  await expect.poll(() => cacheKeys(page)).toEqual(
    expect.not.arrayContaining([expect.stringMatching(/^gv-shell-/)]),
  );
  const keys = await cacheKeys(page);
  expect(keys.some((key) => key.startsWith("gv-precache-"))).toBe(true);
});

test("SW never caches /api/ or image requests, including cross-origin @pwa", async ({ page }) => {
  const csp = watchCsp(page);
  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await waitForServiceWorker(page);

  await page.evaluate(async (apiPrefix: string) => {
    await fetch(`${apiPrefix}pwa-probe`, { cache: "no-store" }).catch(() => undefined);

    const waitFor = (src: string) =>
      new Promise<void>((resolve) => {
        const image = new Image();
        image.onload = () => resolve();
        image.onerror = () => resolve();
        image.src = src;
        document.body.append(image);
        window.setTimeout(resolve, 3_000);
      });

    await waitFor(`${apiPrefix}galleries/1/thumb/0`);
    await waitFor("https://ehgt.org/pwa-probe.png");
  }, API_PREFIX);

  await expect
    .poll(async () => {
      const urls = await cachedUrls(page);
      return urls.filter((url) => url.includes(API_PREFIX) || /ehgt\.org/.test(url));
    })
    .toEqual([]);

  expect(csp).toEqual([]);
});

test("update prompt is visible and dismissible @pwa", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await waitForServiceWorker(page);

  await announceUpdate(page);
  const toast = page.getByTestId("pwa-update");
  await expect(toast).toBeVisible();
  await expect(page.getByTestId("pwa-update-apply")).toBeVisible();

  await page.getByTestId("pwa-update-dismiss").click();
  await expect(toast).toBeHidden();
});

test("screenshots cover dark/light x desktop/mobile @pwa", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("content")).toBeVisible();
  await waitForServiceWorker(page);

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
      await expect(page.getByTestId("content")).toBeVisible();
      await announceUpdate(page);
      await expect(page.getByTestId("pwa-update")).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `pwa-${theme}-${viewport.label}.png`),
        fullPage: true,
      });
    }
  }
});

test("console has zero CSP violations @pwa", async ({ page }) => {
  const csp = watchCsp(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await waitForServiceWorker(page);
  await announceUpdate(page);
  // Below 840px the theme control lives in the navigation sheet (audit SH-06);
  // the CSP check only needs one theme cycle after the shell has booted.
  await page.getByTestId("theme-toggle").click();
  await page.setViewportSize({ width: 390, height: 844 });

  expect(csp).toEqual([]);
  expect(pageErrors).toEqual([]);
});
