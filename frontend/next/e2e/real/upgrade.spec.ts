import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { chromium, expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * C3 upgrade / rollback drill.
 *
 * The tester switches the shared test environment between builds; all three
 * stages must reuse the SAME Chromium profile so the service worker state
 * survives the swap:
 *
 *   1. deploy the legacy frontend   -> run @upgrade-a
 *   2. deploy the new frontend      -> run @upgrade-b
 *   3. deploy the legacy frontend   -> run @upgrade-c
 *
 *   GV_E2E_BASE=http://127.0.0.1:8200 \
 *   GV_E2E_PROFILE=/tmp/opencode/gv-upgrade-profile \
 *   GV_E2E_PASSWORD=... npm run e2e:real -- --grep @upgrade
 *
 * Writers only list these cases; real execution belongs to the tester.
 */

const PROFILE = process.env.GV_E2E_PROFILE;
const BASE = process.env.GV_E2E_BASE || "http://127.0.0.1:8200";
const PASSWORD = process.env.GV_E2E_PASSWORD;
const LEGACY_CACHE = /^gv-shell-/;
const PRECACHE = /^gv-precache-/;

test.describe("service worker upgrade @upgrade", () => {
  test.skip(!PROFILE, "GV_E2E_PROFILE not set");
  test.skip(!PASSWORD, "GV_E2E_PASSWORD not set");

  let context: BrowserContext;

  test.afterEach(async () => {
    await context?.close().catch(() => undefined);
  });

  async function openProfile(): Promise<Page> {
    mkdirSync(dirname(PROFILE as string), { recursive: true });
    context = await chromium.launchPersistentContext(PROFILE as string, {
      headless: true,
      baseURL: BASE,
      viewport: { width: 1280, height: 900 },
    });
    const page = context.pages()[0] ?? (await context.newPage());
    await page.goto("/");

    // The legacy shell (frontend/assets) has no data-testid at all, so the
    // login/shell readiness probes cover both shells: testids for the new
    // build, the plain login form plus #topbar for the legacy build.
    const loginCard = page.getByTestId("login-card");
    const legacyLogin = page.locator('form[data-action="login"]');
    const newShell = page.getByTestId("content");
    const legacyShell = page.locator("#topbar");
    await expect(loginCard.or(legacyLogin).or(newShell).or(legacyShell)).toBeVisible({
      timeout: 30_000,
    });

    if (await loginCard.isVisible().catch(() => false)) {
      await page.getByLabel(/密码|Password/).fill(PASSWORD as string);
      await page.getByTestId("login-submit").click();
    } else if (await legacyLogin.isVisible().catch(() => false)) {
      await legacyLogin.locator('input[name="password"]').fill(PASSWORD as string);
      await legacyLogin.locator('button[type="submit"]').click();
    }
    await expect(newShell.or(legacyShell)).toBeVisible({ timeout: 30_000 });
    return page;
  }

  async function cacheKeys(page: Page): Promise<string[]> {
    return page.evaluate(() => caches.keys()).catch(() => []);
  }

  async function waitForCaches(
    page: Page,
    predicate: (keys: string[]) => boolean,
    timeout = 45_000,
  ): Promise<string[]> {
    const deadline = Date.now() + timeout;
    let keys: string[] = [];
    while (Date.now() < deadline) {
      keys = await cacheKeys(page);
      if (predicate(keys)) return keys;
      await page.waitForTimeout(500);
    }
    throw new Error(`cache condition not met; caches: ${keys.join(", ") || "(none)"}`);
  }

  test("@upgrade-a legacy worker is active on the legacy build", async () => {
    const page = await openProfile();
    await page.waitForFunction(
      () => navigator.serviceWorker.getRegistration().then((reg) => Boolean(reg?.active)),
      null,
      { timeout: 30_000 },
    );

    const keys = await waitForCaches(page, (list) => list.some((key) => LEGACY_CACHE.test(key)));
    expect(keys.some((key) => LEGACY_CACHE.test(key))).toBe(true);

    const state = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      return { active: reg?.active?.scriptURL ?? "", controlled: Boolean(navigator.serviceWorker.controller) };
    });
    expect(state.active).toContain("/sw.js");
    expect(state.controlled).toBe(true);
  });

  test("@upgrade-b new worker replaces the legacy one in the same profile", async () => {
    const page = await openProfile();
    await page.waitForFunction(
      () => navigator.serviceWorker.getRegistration().then((reg) => Boolean(reg?.active)),
      null,
      { timeout: 30_000 },
    );

    // A new build installed behind the legacy worker waits for the prompt.
    const prompt = page.getByTestId("pwa-update");
    await expect(prompt).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("pwa-update-apply").click();

    const keys = await waitForCaches(
      page,
      (list) => list.some((key) => PRECACHE.test(key)) && !list.some((key) => LEGACY_CACHE.test(key)),
    );
    expect(keys.some((key) => PRECACHE.test(key))).toBe(true);
    expect(keys.some((key) => LEGACY_CACHE.test(key))).toBe(false);

    const state = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      return { active: reg?.active?.scriptURL ?? "", controlled: Boolean(navigator.serviceWorker.controller) };
    });
    expect(state.active).toContain("/sw.js");
    expect(state.controlled).toBe(true);
  });

  test("@upgrade-c legacy worker wins again when the old build is restored", async () => {
    const page = await openProfile();
    await page.waitForFunction(
      () => navigator.serviceWorker.getRegistration().then((reg) => Boolean(reg?.active)),
      null,
      { timeout: 30_000 },
    );

    // The legacy worker calls skipWaiting on install and its activate step
    // removes every cache except gv-shell-v14.
    const keys = await waitForCaches(
      page,
      (list) => list.some((key) => LEGACY_CACHE.test(key)) && !list.some((key) => PRECACHE.test(key)),
    );
    expect(keys.some((key) => LEGACY_CACHE.test(key))).toBe(true);
    expect(keys.some((key) => PRECACHE.test(key))).toBe(false);

    const state = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      return { active: reg?.active?.scriptURL ?? "", controlled: Boolean(navigator.serviceWorker.controller) };
    });
    expect(state.active).toContain("/sw.js");
    expect(state.controlled).toBe(true);
  });
});
