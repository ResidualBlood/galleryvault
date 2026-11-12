/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import { annotateUnverified, expect, firstGallery, test } from "./support";

/**
 * History / downloads / favourites parity (V-08, V-09, V-12, V-13).
 *
 * The only mutation performed here is history progress that the suite creates
 * itself and then removes; cloud sync, download queueing and favourite
 * removal stay behind confirmation dialogs because they operate on shared
 * ExHentai data.
 */
test("V-08 历史：列表 / 清空 / 清空进度 / 删除单本进度 @parity", async ({ app }) => {
  const { page } = app;
  const gallery = await firstGallery(app.api);
  test.skip(!gallery, "test library is empty");
  if (!gallery) return;

  const progressPath = `/api/galleries/${gallery.id}/progress`;
  const before = await page.request.get(progressPath);
  const original = before.ok()
    ? ((await before.json()) as { current_page?: number; total_pages?: number })
    : null;

  try {
    await app.api.put(progressPath, {
      current_page: 1,
      total_pages: Math.max(1, gallery.page_count),
    });

    await page.goto("/#/history");
    await expect(page.getByTestId("history-view")).toBeVisible();
    const row = page.locator(`li[data-gallery-id="${gallery.id}"]`);
    await expect(row).toBeVisible({ timeout: 20_000 });
    await row.getByTestId("history-reset-row").click();
    await expect(row).toHaveCount(0);

    await page.getByTestId("history-clear").click();
    await expect(page.getByTestId("history-clear-confirm")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("history-clear-dialog")).toHaveCount(0);

    await page.getByTestId("history-clear-progress").click();
    await expect(page.getByTestId("history-clear-progress-confirm")).toBeVisible();
    await page.keyboard.press("Escape");
    annotateUnverified("clear-all history / clear-all progress were opened but never confirmed");
  } finally {
    if (original) {
      await app.api.put(progressPath, {
        current_page: original.current_page ?? 0,
        total_pages: original.total_pages ?? gallery.page_count,
      }).catch(() => undefined);
    }
  }
  await app.shot("V-08");
});

test("V-09 下载：列表 / 过滤 / 新建 / 配额 / 暂停 / 批量对话框 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/downloads");
  await expect(page.getByTestId("downloads-view")).toBeVisible();
  await expect(page.getByTestId("downloads-page-size")).toBeVisible();
  await expect(page.getByTestId("downloads-urls")).toBeVisible();
  await expect(page.getByTestId("downloads-quality")).toBeVisible();
  await expect(page.getByTestId("downloads-gp")).toBeVisible();

  for (const filter of ["all", "pending", "downloading", "success", "failed", "cancelled"]) {
    await expect(page.getByTestId(`downloads-filter-${filter}`)).toBeVisible();
  }

  // Pause toggle is global but reversible; restore the initial value.
  const initial = await app.api.get<{ paused: boolean }>("/api/pause");
  await page.getByTestId("downloads-pause").click();
  await expect
    .poll(async () => (await app.api.get<{ paused: boolean }>("/api/pause")).paused)
    .toBe(!initial.paused);
  await page.getByTestId("downloads-pause").click();
  await expect
    .poll(async () => (await app.api.get<{ paused: boolean }>("/api/pause")).paused)
    .toBe(initial.paused);

  await page.getByTestId("downloads-retry-all").click();
  await expect(page.getByTestId("downloads-retry-all-confirm")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByTestId("downloads-clear-success").click();
  await expect(page.getByTestId("downloads-clear-confirm")).toBeVisible();
  await page.keyboard.press("Escape");

  // Empty input is rejected in place; only a parsed link opens the archive
  // dialog. The dialog is confirmed only after the test types a valid link, and
  // even then it is dismissed without queueing anything.
  await page.getByTestId("downloads-add-archive").click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: /没有识别到画廊链接|No gallery links recognised/ }),
  ).toBeVisible();
  await expect(page.getByTestId("downloads-archive-dialog")).toHaveCount(0);

  await page.getByTestId("downloads-urls").fill("123456/abcdef");
  await page.getByTestId("downloads-add-archive").click();
  await expect(page.getByTestId("downloads-archive-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("downloads-archive-dialog")).toHaveCount(0);

  // The cancel button only exists for live tasks; terminal tasks show retry
  // instead. Assert the per-row contract rather than requiring a cancellable
  // task to already exist in the shared queue.
  const list = page.getByTestId("downloads-list");
  if (await list.isVisible().catch(() => false)) {
    const rows = list.locator("li[data-task-id]");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    let cancellable = 0;
    for (let index = 0; index < count; index += 1) {
      const row = rows.nth(index);
      const status = await row.getAttribute("data-status");
      await expect(row.getByTestId("downloads-delete")).toBeVisible();
      if (status === "pending" || status === "downloading") {
        cancellable += 1;
        await expect(row.getByTestId("downloads-cancel")).toBeVisible();
      } else {
        await expect(row.getByTestId("downloads-cancel")).toHaveCount(0);
        await expect(row.getByTestId("downloads-retry")).toBeVisible();
      }
    }
    if (cancellable > 0) {
      annotateUnverified("cancel / retry / delete / clear / retry-all were not confirmed on shared tasks");
    } else {
      annotateUnverified(
        "all visible tasks are terminal; cancel is correctly absent and retry is shown instead",
      );
    }
  } else {
    annotateUnverified("download list is empty; task-level cancel/retry/delete controls were not rendered");
  }
  annotateUnverified("new download / batch URL submission was not queued (would spend EH budget)");
  await app.shot("V-09");
});

test("V-12 收藏夹表与每夹配置保存 @parity", async ({ app }) => {
  const { page } = app;
  const original = await app.api.get<
    Array<{
      favcat: number;
      enabled?: boolean | null;
      mode?: string | null;
      poll_interval_minutes?: number | null;
    }>
  >("/api/favorites/categories");
  const restore = original.map((item) => ({
    favcat: item.favcat,
    enabled: Boolean(item.enabled),
    mode: item.mode ?? "incremental",
    poll_interval_minutes: Math.max(1, item.poll_interval_minutes ?? 720),
  }));

  try {
    await page.goto("/#/favorites");
    await expect(page.getByTestId("favorites-view")).toBeVisible();
    const table = page.getByTestId("favorites-table");
    const empty = page.getByTestId("favorites-empty");
    await expect(table.or(empty)).toBeVisible({ timeout: 20_000 });
    if (!(await table.isVisible().catch(() => false))) {
      test.skip(true, "favourite categories are unavailable");
      return;
    }

    await expect(page.getByTestId("favcat-row").first()).toBeVisible();
    await expect(page.getByTestId("favorites-save")).toBeDisabled();

    const firstToggle = page.getByTestId("favcat-enabled").first();
    const current = await firstToggle.getAttribute("aria-checked");
    await firstToggle.click();
    await expect(firstToggle).toHaveAttribute("aria-checked", current === "true" ? "false" : "true");
    await expect(page.getByTestId("favorites-save")).toBeEnabled();

    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/api/settings"),
    );
    await page.getByTestId("favorites-save").click();
    expect((await saved).ok()).toBeTruthy();

    for (const action of ["favorites-sync", "favorites-check-all", "favorites-download-missing"]) {
      await expect(page.getByTestId(action)).toBeVisible();
    }
    annotateUnverified(
      "sync names / check all / download missing were not clicked (cloud and download budget)",
    );
  } finally {
    await app.api.post("/api/settings", { favorites: restore }).catch(() => undefined);
  }
  await app.shot("V-12");
});

test("V-13 单收藏夹：15 个筛选 / 下载 / 移动 / 移除 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/favorites/0");
  await expect(page.getByTestId("favlist-view")).toBeVisible();
  await expect(page.getByTestId("favlist-grid").or(page.getByTestId("favlist-empty"))).toBeVisible({
    timeout: 20_000,
  });

  await page.getByTestId("favlist-advanced-toggle").click();
  const filters = [
    "favlist-q",
    "favlist-category",
    "favlist-language",
    "favlist-order",
    "favlist-read-status",
    "favlist-min-rating",
    "favlist-page-min",
    "favlist-page-max",
    "favlist-size-min",
    "favlist-size-max",
    "favlist-posted-from",
    "favlist-posted-to",
    "favlist-uploader",
    "favlist-image-quality",
    "favlist-local-rating",
  ];
  for (const id of filters) {
    await expect(page.getByTestId(id)).toBeVisible();
  }

  const grid = page.getByTestId("favlist-grid");
  if (await grid.isVisible().catch(() => false)) {
    await grid.locator('input[type="checkbox"]').first().check({ force: true });
    await page.getByTestId("favlist-move").click();
    await expect(page.getByTestId("favlist-move-target")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("favlist-move-dialog")).toHaveCount(0);

    await page.getByTestId("favlist-remove").click();
    await expect(page.getByTestId("favlist-remove-confirm")).toBeVisible();
    await page.keyboard.press("Escape");
  } else {
    annotateUnverified("favourite category 0 is empty; selection-driven move/remove dialogs not rendered");
  }

  annotateUnverified(
    "single-category check, download-selected and actual remove/move were not executed (EH / shared favourites)",
  );
  await app.shot("V-13");
});
