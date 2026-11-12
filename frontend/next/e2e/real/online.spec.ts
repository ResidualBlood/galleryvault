/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import type { OnlineSearchItem, OnlineSearchResponse } from "../../src/api/eh";
import {
  annotateUnverified,
  expect,
  newApiContext,
  test,
} from "./support";

/**
 * Online browse / detail / reader parity (V-05, N-01 … N-04).
 *
 * EH budget for this file: 1 sample search in `beforeAll`, 2 UI searches in
 * V-05, at most 2 detail fetches (N-01 + N-03), at most 2 direct resolves
 * (N-02) and at most 2 proxy images (N-04). A banned/challenge answer skips the
 * EH-dependent cases rather than retrying and burning the shared quota.
 */
let sample: OnlineSearchItem | null = null;
let sampleState = "error";
let sampleError = "";

test.beforeAll(async ({ playwright }) => {
  const api = await newApiContext(playwright);
  try {
    const response = await api.get("/api/eh/search?list=popular");
    const data = (await response.json()) as OnlineSearchResponse;
    sampleState = data.state;
    sample = Array.isArray(data.items) && data.items.length ? data.items[0] : null;
    if (!sample) sampleError = "online search returned no items";
  } catch (error) {
    sampleError = error instanceof Error ? error.message : String(error);
  } finally {
    await api.dispose();
  }
});

test.beforeEach(() => {
  test.skip(
    Boolean(sampleError) || sampleState !== "ok" || !sample,
    sampleError || `online state is ${sampleState}`,
  );
});

test("V-05 在线浏览：搜索 / 分类 / 评分 / 列表类型 / 徽标 / 快捷操作 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/online");
  await expect(page.getByTestId("online-view")).toBeVisible();
  await expect(
    page.getByTestId("online-grid").or(page.getByTestId("online-empty")),
  ).toBeVisible({ timeout: 30_000 });

  await expect(page.getByTestId("online-search")).toBeVisible();
  await expect(page.getByTestId("online-cat-all")).toBeVisible();
  await expect(page.getByTestId("online-min-rating")).toBeVisible();
  for (const list of ["search", "popular", "watched", "toplist"]) {
    await expect(page.getByTestId(`online-list-${list}`)).toBeVisible();
  }

  const cards = page.getByTestId("gallery-card");
  if ((await cards.count()) > 0) {
    await expect(cards.first().getByTestId("fav-button")).toBeVisible();
    await expect(cards.first().getByTestId("download-button")).toBeVisible();
  } else {
    annotateUnverified("online search rendered no cards; badges/quick actions were not visible");
  }

  // Search form and list-type transition (two real EH searches).
  await page.locator('[data-testid="online-search"] input').fill("a");
  await page.getByTestId("online-submit").click();
  await expect(page).toHaveURL(/[?&]q=a/);
  await expect(page.getByTestId("online-view")).toBeVisible();
  await page.getByTestId("online-list-toplist").click();
  await expect(page).toHaveURL(/list=toplist/);
  await expect(page.getByTestId("online-toplists")).toBeVisible();

  annotateUnverified(
    "online list has no batch selection; batch download / batch favourite are only available from library/favourites",
  );
  await app.shot("V-05");
});

test("N-01 在线详情：字段 / 标签回搜 / 缩略图 / 新版本 / 已在库 @parity", async ({ app }) => {
  const { page } = app;
  const item = sample;
  if (!item) return;
  await page.goto(`/#/online/g/${item.gid}/${item.token}`);
  await expect(page.getByTestId("online-detail-view")).toBeVisible({ timeout: 20_000 });

  const state = page.getByTestId(/^online-state-/);
  if (await state.isVisible().catch(() => false)) {
    test.skip(true, `online detail state is ${(await state.textContent()) ?? "not ok"}`);
    return;
  }

  await expect(page.getByTestId("online-title")).toBeVisible();
  await expect(page.getByTestId("online-actions")).toBeVisible();
  await expect(page.getByTestId("online-read")).toBeVisible();
  await expect(page.getByTestId("online-official")).toHaveAttribute("href", /exhentai\.org\/g\//);

  const cover = page.getByTestId("online-cover");
  const coverFallback = page.getByTestId("online-cover-fallback");
  await expect(cover.or(coverFallback)).toBeVisible();
  const thumbs = page.getByTestId("online-thumbs");
  if (await thumbs.isVisible().catch(() => false)) {
    await expect(thumbs.getByTestId(/online-thumb/).first()).toBeVisible();
  } else {
    annotateUnverified("detail thumbnail grid was not rendered (page preview unavailable)");
  }

  if (item.in_library) {
    await expect(page.getByTestId("online-in-library")).toBeVisible();
    await expect(page.getByTestId("online-open-local")).toBeVisible();
  }
  if (await page.getByTestId("online-newer").isVisible().catch(() => false)) {
    await expect(page.getByTestId("online-newer")).toBeVisible();
  } else {
    annotateUnverified("sample gallery has no newer version link");
  }
  await app.shot("N-01");
});

test("N-02 在线阅读直连：后端图片请求 0 / 五模式 / 进度与继续阅读 @parity", async ({ app }) => {
  const { page } = app;
  const item = sample;
  if (!item) return;

  const progressPath = `/api/eh/galleries/${item.gid}/${encodeURIComponent(item.token)}/progress`;
  const progressResponse = await page.request.get(progressPath);
  const originalProgress = progressResponse.ok()
    ? ((await progressResponse.json()) as { page?: number; total_pages?: number })
    : null;

  let imageRequests = 0;
  let resolveRequests = 0;
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (/\/api\/eh\/galleries\/\d+\/[^/]+\/pages\/\d+\/image$/.test(path)) imageRequests += 1;
    if (/\/api\/eh\/galleries\/\d+\/[^/]+\/pages\/\d+\/resolve$/.test(path)) resolveRequests += 1;
  });

  try {
    await page.addInitScript(() =>
      localStorage.setItem("gv_online_image_mode", "direct"),
    );
    await page.goto(`/#/online/g/${item.gid}/${item.token}/read/1`);
    await expect(page.getByTestId("online-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("reader-shell")).toBeVisible({ timeout: 30_000 });

    const blocked = page.getByTestId("online-reader-blocked");
    if (await blocked.isVisible().catch(() => false)) {
      test.skip(true, "ExHentai/H@H blocked the direct image path");
      return;
    }

    await expect.poll(() => resolveRequests, { timeout: 30_000 }).toBeGreaterThan(0);
    expect(imageRequests).toBe(0);
    expect(resolveRequests).toBeLessThanOrEqual(6);

    // Modes are shared with the local reader; exercise them through the same sheet.
    if ((await page.getByTestId("reader-shell").getAttribute("data-bars")) !== "visible") {
      await page.getByTestId("reader-zone-center").click();
    }
    await page.getByTestId("reader-settings").click();
    for (const mode of ["rtl", "double", "double-rtl", "webtoon", "ltr"]) {
      await page.locator(`[data-testid="reader-settings-panel"] [data-mode="${mode}"]`).click();
      await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-mode", mode);
    }
    await page.keyboard.press("Escape");

    // Page turn persists online progress (local DB only; no server image fetch).
    if ((await page.getByTestId("reader-shell").getAttribute("data-bars")) !== "visible") {
      await page.getByTestId("reader-zone-center").click();
    }
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(
        async () => {
          const response = await page.request.get(progressPath);
          if (!response.ok()) return 0;
          const body = (await response.json()) as { page?: number };
          return Number(body.page) || 0;
        },
        { timeout: 20_000 },
      )
      .toBeGreaterThan(1);

    await page.goto("/#/browse");
    await expect(page.getByTestId("browse-view")).toBeVisible();
    await expect(page.getByTestId("online-continue")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("online-continue-item").first()).toBeVisible();

    if (await page.getByTestId("online-reader-quota").isVisible().catch(() => false)) {
      annotateUnverified("image quota notice was visible; proxy switch / official link covered by N-04");
    } else {
      annotateUnverified(
        "node re-resolve and expired-URL re-resolve need induced failures and were not forced",
      );
    }
  } finally {
    const restore = originalProgress
      ? { page: Math.max(1, originalProgress.page ?? 1), total_pages: originalProgress.total_pages }
      : { page: 1 };
    await app.api.put(progressPath, restore).catch(() => undefined);
  }
  await app.shot("N-02", { fullPage: false });
});

test("N-03 快捷操作：指定 favcat 收藏 / 取消 / 一键下载入口 @parity", async ({ app }) => {
  const { page } = app;
  const item = sample;
  if (!item) return;

  await page.goto(`/#/online/g/${item.gid}/${item.token}`);
  await expect(page.getByTestId("online-detail-view")).toBeVisible({ timeout: 20_000 });
  const state = page.getByTestId(/^online-state-/);
  if (await state.isVisible().catch(() => false)) {
    test.skip(true, `online detail state is ${(await state.textContent()) ?? "not ok"}`);
    return;
  }
  await expect(page.getByTestId("fav-button")).toBeVisible();

  const status = await app.api.get<{
    items?: Array<{ favorited?: boolean; favcat?: number | null }>;
  }>(`/api/eh/status?gids=${item.gid}`);
  const already = Boolean(status.items?.[0]?.favorited);
  let mutated = false;
  try {
    if (!already) {
      await page.getByTestId("fav-select").click();
      await expect(page.getByTestId("fav-picker")).toBeVisible();
      await page.getByTestId("fav-cat-3").click();
      const added = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          response.url().includes("/api/favorites/add"),
      );
      await page.getByTestId("fav-confirm").click();
      expect((await added).ok()).toBeTruthy();
      mutated = true;
      await expect(page.getByTestId("fav-button")).toHaveAttribute("data-favcat", "3");

      await page.getByTestId("fav-button").click();
      await expect(page.getByTestId("fav-menu")).toBeVisible();
      const removed = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          response.url().includes("/api/favorites/remove"),
      );
      await page.getByTestId("fav-remove").click();
      expect((await removed).ok()).toBeTruthy();
      await expect(page.getByTestId("fav-button")).not.toHaveAttribute("data-favcat", "3");
    } else {
      annotateUnverified(
        "sample gallery was already favourited by the test account; add/remove was not run",
      );
      await page.getByTestId("fav-button").click();
      await expect(page.getByTestId("fav-menu")).toBeVisible();
      await page.keyboard.press("Escape");
    }

    await page.getByTestId("download-quality").click();
    await expect(page.getByTestId("download-quality-menu")).toBeVisible();
    await expect(page.getByTestId("download-quality-original")).toBeVisible();
    await expect(page.getByTestId("download-quality-resample")).toBeVisible();
    await page.keyboard.press("Escape");
    annotateUnverified(
      "actual one-click download was not queued (would spend EH download budget); only the quality menu was exercised",
    );
  } finally {
    if (mutated) {
      await app.api.post("/api/favorites/remove", { gids: [item.gid] }).catch(() => undefined);
    }
  }
  await app.shot("N-03");
});

test("N-04 在线阅读回退：按设备切服务器代理 / 官方页入口 @parity", async ({ app }) => {
  const { page } = app;
  const item = sample;
  if (!item) return;

  let proxyImages = 0;
  page.on("request", (request) => {
    if (
      /\/api\/eh\/galleries\/\d+\/[^/]+\/pages\/\d+\/image$/.test(
        new URL(request.url()).pathname,
      )
    ) {
      proxyImages += 1;
    }
  });

  try {
    await page.addInitScript(() => localStorage.setItem("gv_online_image_mode", "proxy"));
    await page.goto(`/#/online/g/${item.gid}/${item.token}/read/1`);
    await expect(page.getByTestId("online-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("online-reader-mode")).toHaveAttribute("data-mode", "proxy");
    await expect.poll(() => proxyImages, { timeout: 30_000 }).toBeGreaterThan(0);

    if (await page.getByTestId("online-reader-blocked").isVisible().catch(() => false)) {
      await expect(page.getByTestId("online-reader-official")).toHaveAttribute(
        "href",
        /exhentai\.org\/g\//,
      );
    } else {
      annotateUnverified(
        "proxy path stayed healthy; blocked-panel official link was not rendered (detail link covered by N-01)",
      );
    }
  } finally {
    await page.evaluate(() => localStorage.setItem("gv_online_image_mode", "direct"));
  }
  await app.shot("N-04", { fullPage: false });
});
