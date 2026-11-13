/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import legacyRoutes from "../../parity/legacy-routes.json" with { type: "json" };
import {
  annotateUnverified,
  expect,
  firstGallery,
  galleryTotal,
  test,
} from "./support";

/**
 * Global shell parity (G-02 … G-08, G-10).
 *
 * Everything here is read-only against existing data. The two destructive
 * global actions (purge archived sources / start a library scan) are only
 * checked for their confirmation surface; actually running them belongs to a
 * human-approved maintenance window, not to a gate run.
 */

test("G-02 顶栏搜索与标签建议 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-view")).toBeVisible();

  const input = page.locator('[data-testid="tag-suggest"] input').first();
  await input.fill("a");
  const suggestion = page.getByTestId("tag-suggestion").first();
  const hasSuggestion = await suggestion
    .isVisible({ timeout: 3_000 })
    .catch(() => false);
  if (hasSuggestion) {
    await suggestion.click();
  } else {
    annotateUnverified("tag database returned no suggestion for 'a'; fallback submit used");
    await page.locator('form[role="search"] button[type="submit"]').first().click();
  }

  await expect(page).toHaveURL(/#\/library/);
  await expect(page.getByTestId("library-view")).toBeVisible();
  await app.shot("G-02");
});

test("G-03 随机打开一本 @parity", async ({ app }) => {
  const { page } = app;
  const total = await galleryTotal(app.api);
  test.skip(total === 0, "test library is empty; random needs at least one gallery");
  if (!total) return;

  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-view")).toBeVisible();
  await page.getByTestId("random-button").click();
  await expect(page).toHaveURL(/#\/gallery\/\d+/);
  await expect(page.getByTestId("gallery-title")).toBeVisible({ timeout: 20_000 });
  await app.shot("G-03");
});

test("G-04 通知面板 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/browse");
  await page.getByTestId("notifications").click();
  const panel = page.getByTestId("notification-panel");
  await expect(panel).toBeVisible();

  const badge = page.getByTestId("notification-badge");
  const hasUnread = await badge.isVisible().catch(() => false);
  if (hasUnread) {
    await panel.getByRole("button", { name: /全部已读|mark.*read|标记.*已读/i }).first().click();
    await expect(badge).toHaveCount(0);
  } else {
    annotateUnverified("no unread notifications existed; mark-read transition not exercised");
  }

  await expect(
    panel.getByRole("button", { name: /清空|clear/i }).first(),
  ).toBeVisible();
  annotateUnverified("notification clear is destructive to shared state and was not executed");
  await app.shot("G-04");
});

test("G-05 全局控制（暂停 / 恢复 / 扫描 / 清理入口） @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/browse");
  await page.getByTestId("global-controls-toggle").click();
  await expect(page.getByTestId("global-controls")).toBeVisible();

  const initial = await app.api.get<{ paused: boolean }>("/api/pause");
  const first = page.getByTestId(initial.paused ? "global-resume" : "global-pause");
  await first.click();
  const flipped = initial.paused ? "global-pause" : "global-resume";
  await expect(page.getByTestId(flipped)).toBeVisible();
  await page.getByTestId(flipped).click();
  await expect(page.getByTestId(initial.paused ? "global-resume" : "global-pause")).toBeVisible();

  await expect(page.getByTestId("global-scan")).toBeVisible();
  await page.getByTestId("global-purge").click();
  await expect(page.getByTestId("global-purge-confirm")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("global-purge-confirm")).toHaveCount(0);

  annotateUnverified("scan trigger and archived-source purge were not executed (shared maintenance data)");
  await app.shot("G-05");
});

test("G-06 外观与语言沿用旧 localStorage 键 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/browse");
  const original = await page.evaluate(() => ({
    theme: localStorage.getItem("gv_theme"),
    lang: localStorage.getItem("gv_lang"),
  }));
  try {
    await page.evaluate(() => {
      localStorage.setItem("gv_theme", "light");
      localStorage.setItem("gv_lang", "en");
    });
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.getByTestId("lang-toggle")).toContainText("EN");

    await page.getByTestId("theme-toggle").click();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-theme")))
      .toBeNull();
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("gv_theme")))
      .toBe("system");

    await page.getByTestId("lang-toggle").click();
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("gv_lang")))
      .toBe("zh");
  } finally {
    await page.evaluate((values) => {
      for (const [key, value] of Object.entries(values)) {
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, value);
      }
    }, original);
    await page.reload();
    await expect(page.getByTestId("content")).toBeVisible();
  }
  await app.shot("G-06");
});

test("G-07 Cookie 健康横幅 @parity", async ({ app }) => {
  const { page } = app;
  // The banner probes once on mount. Reload so that probe is observable and the
  // banner state we assert below belongs to this test.
  const probe = page.waitForResponse(
    (response) =>
      response.url().includes("/api/settings/cookie-health") &&
      response.request().method() === "GET",
    { timeout: 20_000 },
  );
  await page.goto("/#/browse");
  await page.reload();
  const wanted = await probe;
  await wanted.finished();
  await expect(page.getByTestId("content")).toBeVisible({ timeout: 20_000 });

  const health = await app.api.get<{ state?: string }>("/api/settings/cookie-health");
  const state = String(health.state ?? "").toLowerCase();
  const banner = page.getByTestId("cookie-health-banner");
  // Mirrors PROBLEM_STATES in CookieHealthBanner.vue (same contract as the old
  // v1.13.5 core.js): only actionable problems raise the banner. "ok" and the
  // advisory "failed" (probe error / anti-bot challenge page) stay silent.
  const problemStates = [
    "not_configured",
    "not_logged_in",
    "no_exhentai_access",
    "ip_banned",
  ];
  if (problemStates.includes(state)) {
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toHaveAttribute("data-cookie-state", state);
    await expect(page.getByTestId("cookie-banner-settings")).toBeVisible();
    await page.getByTestId("cookie-banner-dismiss").click();
    await expect(banner).toHaveCount(0);
    annotateUnverified(
      `cookie banner rendered for state=${state}; the settings jump was not followed`,
    );
  } else {
    await expect(banner).toHaveCount(0);
    annotateUnverified(
      `cookie health state=${state || "unknown"} is silent by design; the problem banner branch cannot be opened`,
    );
  }
  await app.shot("G-07");
});

test("G-08 归档对话框与收藏夹选择框 @parity", async ({ app }) => {
  const { page } = app;
  const gallery = await firstGallery(app.api);
  test.skip(!gallery, "test library is empty; favourite picker needs a local gallery");
  if (!gallery) return;
  test.skip(!gallery.gid || !gallery.token, "local gallery has no EH gid/token for the picker");
  if (!gallery.gid || !gallery.token) return;

  await page.goto(`/#/gallery/${gallery.id}`);
  await expect(page.getByTestId("gallery-title")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("fav-select").click();
  await expect(page.getByTestId("fav-picker")).toBeVisible();
  await page.locator(".fav-picker__scrim").click();
  await expect(page.getByTestId("fav-picker")).toHaveCount(0);

  await page.goto("/#/downloads");
  await expect(page.getByTestId("downloads-view")).toBeVisible();
  const archiveDialog = page.getByTestId("downloads-archive-dialog");
  const archiveLinks = page.getByTestId("downloads-urls");

  // By design `openArchive()` validates the pasted links first, so an empty
  // form reports an error instead of opening the dialog.
  await archiveLinks.fill("");
  await page.getByTestId("downloads-add-archive").click();
  await expect(archiveDialog).toHaveCount(0);

  // A valid gallery link is only parsed client-side; nothing is queued.
  await archiveLinks.fill(`https://e-hentai.org/g/${gallery.gid}/${gallery.token}/`);
  await page.getByTestId("downloads-add-archive").click();
  await expect(archiveDialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(archiveDialog).toHaveCount(0);
  await archiveLinks.fill("");
  await app.shot("G-08");
});

test("G-10 旧书签 hash 路由全部可达 @parity", async ({ app }) => {
  const { page } = app;
  const gallery = await firstGallery(app.api);
  const galleryId = gallery?.id ?? 1;

  // /discover is an online list: stub it so route reachability does not spend
  // the shared ExHentai budget.
  await page.route("**/api/eh/search**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ state: "empty", items: [], next: null }),
    }),
  );

  const failures: string[] = [];
  for (const route of legacyRoutes.routes) {
    const path = route.path
      .replace("{id}", String(galleryId))
      .replace("{page}", "0");
    await page.goto(`/#${path}`);
    const content = page.getByTestId("content");
    const ok = await content
      .isVisible({ timeout: 15_000 })
      .catch(() => false);
    if (!ok) failures.push(path);
  }
  await page.unroute("**/api/eh/search**");
  expect(failures, `unreachable legacy routes: ${failures.join(", ")}`).toEqual([]);
  await page.goto("/#/browse");
  await expect(page.getByTestId("content")).toBeVisible();
  await app.shot("G-10");
});
