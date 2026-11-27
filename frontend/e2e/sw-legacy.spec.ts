import { copyFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, installMockBackend, test } from "./fixtures/mock";

/**
 * C3 white-screen regression (@upgrade-b).
 *
 * A browser that was on the legacy shell (`frontend/sw.js`, cache
 * `gv-shell-v14`) keeps reading the cached document after the new build is
 * deployed. Its assets are gone, so the page stays blank while the new worker
 * sits in `waiting`; only the *second* start renders the new shell.
 *
 * The harness reproduces the legacy side with `/legacy-sw.js`
 * (e2e/fixtures/legacy-sw.js) and a `gv-shell-v14` cache that holds the old
 * index plus an asset the new deploy no longer has. Registering `/sw.js` then
 * stands for the browser's update check after the deploy.
 */

const DIST = join(process.cwd(), "dist");

const LEGACY_INDEX = `<!doctype html>
<html lang="en" data-shell="legacy">
  <head><meta charset="utf-8" /><title>GalleryVault</title></head>
  <body>
    <div id="legacy-shell">legacy shell</div>
    <script type="module" src="/assets/legacy-v8.js"></script>
  </body>
</html>`;

test.beforeAll(() => {
  // Vite preview serves `dist/`: the harness-only worker must live there too.
  copyFileSync(join(process.cwd(), "e2e/fixtures/legacy-sw.js"), join(DIST, "legacy-sw.js"));
});

/** Same-origin document that does not require the app bundle. */
async function openProbe(page: Page): Promise<void> {
  await page.route("**/__legacy-probe", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<!doctype html><html><body>probe</body></html>",
    }),
  );
  await page.goto("/__legacy-probe");
}

test("the first start after the swap replaces the stale legacy shell @sw-legacy", async ({
  page,
  context,
}) => {
  await openProbe(page);
  await page.evaluate(async (html) => {
    const cache = await caches.open("gv-shell-v14");
    await cache.put(
      "/index.html",
      new Response(html, { headers: { "content-type": "text/html" } }),
    );
    // Legacy asset entry: it exists in the old cache but not in the new build.
    await cache.put(
      "/assets/legacy-v8.css",
      new Response("body{}", { headers: { "content-type": "text/css" } }),
    );
    await navigator.serviceWorker.register("/legacy-sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
  }, LEGACY_INDEX);

  // The pre-swap cold start: the legacy worker answers with the cached shell,
  // whose entry script is not served as JavaScript by the new deploy (nginx
  // returns 404; the preview server falls back to index.html, also unusable),
  // so the app never mounts - the reported white screen.
  const staleAsset = await page.request.get("/assets/legacy-v8.js");
  expect(staleAsset.headers()["content-type"] ?? "").not.toContain("javascript");

  await page.goto("/");
  await expect(page.locator("#legacy-shell")).toBeVisible();
  expect(await page.getByTestId("content").count()).toBe(0);
  expect(await page.getByTestId("nav-drawer").count()).toBe(0);

  // Count real document loads only: hash-route changes also fire
  // `framenavigated`. One document request == one forced reload.
  let documents = 0;
  page.on("request", (request) => {
    if (!request.isNavigationRequest()) return;
    if (request.frame() !== page.mainFrame()) return;
    documents += 1;
  });

  // Deploy: the browser's update check picks up the new worker for /sw.js.
  await page.evaluate(() => navigator.serviceWorker.register("/sw.js", { scope: "/" }));

  // No prompt and no waiting worker: the new build must replace the stale
  // document during this start.
  await expect(page.getByTestId("nav-drawer")).toBeVisible({ timeout: 30_000 });

  const state = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    return {
      waiting: Boolean(registration?.waiting),
      active: registration?.active?.scriptURL ?? "",
      controlled: Boolean(navigator.serviceWorker.controller),
      cacheKeys: await caches.keys(),
    };
  });
  expect(state.waiting).toBe(false);
  expect(state.active).toMatch(/\/sw\.js$/);
  expect(state.controlled).toBe(true);
  expect(state.cacheKeys.some((key) => key.startsWith("gv-shell-"))).toBe(false);
  expect(state.cacheKeys.some((key) => key.startsWith("gv-precache-"))).toBe(true);

  // Exactly one forced navigation: the migration marker must not loop.
  await page.waitForTimeout(1_500);
  expect(documents).toBe(1);

  // The next cold start (new page in the same profile) must already be the new
  // shell, not another stale document.
  const cold = await context.newPage();
  try {
    await installMockBackend(cold, { expired: false, authenticated: true });
    await cold.goto("/");
    await expect(cold.getByTestId("nav-drawer")).toBeVisible({ timeout: 20_000 });
    expect(await cold.locator("#legacy-shell").count()).toBe(0);
    expect(await cold.locator("script[src='/assets/legacy-v8.js']").count()).toBe(0);
  } finally {
    await cold.close();
  }
});

test("an update over a live gv-precache-* build still waits for the prompt @sw-legacy", async ({
  page,
}) => {
  await openProbe(page);
  await page.evaluate(async () => {
    // An earlier new-version build is live: its precache cache is the signal
    // that this is a normal new→new update, not the legacy swap.
    const previous = await caches.open("gv-precache-previous");
    await previous.put("/previous-build-probe", new Response("previous build"));
    await navigator.serviceWorker.register("/legacy-sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
  });
  await expect
    .poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller)), {
      timeout: 20_000,
    })
    .toBe(true);

  await page.evaluate(() => navigator.serviceWorker.register("/sw.js", { scope: "/" }));

  await expect
    .poll(
      () =>
        page.evaluate(async () => {
          const registration = await navigator.serviceWorker.getRegistration();
          return Boolean(registration?.waiting);
        }),
      { timeout: 20_000 },
    )
    .toBe(true);

  // A waiting worker means the prompt flow: the open page is not reloaded.
  expect(new URL(page.url()).pathname).toBe("/__legacy-probe");
  await expect(page.locator("body")).toHaveText("probe");
});
