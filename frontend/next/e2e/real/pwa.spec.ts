import { BASE_URL, expect, test } from "./support";

/**
 * G-09: installable shell, generated service worker, and no stale legacy cache.
 *
 * The upgrade / rollback browser-profile drill is the separate `@upgrade-*`
 * spec owned by fe-pwa; this gate only proves the shipped shell is a PWA.
 */
test("G-09 PWA 可安装与旧壳升级 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/");

  const manifestLink = page.locator('link[rel="manifest"]');
  await expect(manifestLink).toHaveAttribute("href", /manifest/);
  const href = await manifestLink.getAttribute("href");
  expect(href).toBeTruthy();
  const manifestResponse = await page.request.get(new URL(href as string, BASE_URL).toString());
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = (await manifestResponse.json()) as {
    name?: string;
    icons?: Array<{ sizes?: string; src?: string }>;
  };
  expect(manifest.icons?.length ?? 0).toBeGreaterThan(0);

  await expect
    .poll(
      () =>
        page.evaluate(async () =>
          (await navigator.serviceWorker.getRegistrations()).map(
            (registration) => registration.active?.scriptURL ?? "",
          ),
        ),
      { timeout: 25_000 },
    )
    .toContainEqual(expect.stringContaining("/sw.js"));

  const legacyCaches = await page.evaluate(async () =>
    (await caches.keys()).filter((key) => key.startsWith("gv-shell-")),
  );
  expect(legacyCaches).toEqual([]);

  await app.shot("G-09");
});
