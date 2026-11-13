/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import { galleryPageEp, galleryPageMetaEp } from "../../src/api/galleries";
import { annotateUnverified, expect, firstGallery, test } from "./support";

/**
 * Local gallery detail + reader parity (V-03, V-04).
 *
 * Local notes/progress are mutated only briefly and restored from the values
 * captured before the test, so the shared test library ends in its original
 * state even when a later assertion fails.
 */
test("V-03 画廊详情：元数据 / 标签 / 缩略图 / 收藏 / 本地字段 @parity", async ({ app }) => {
  const { page } = app;
  const gallery = await firstGallery(app.api);
  test.skip(!gallery, "test library is empty");
  if (!gallery) return;

  const detail = await app.api.get<{
    id: number;
    local_rating?: number | null;
    local_note?: string | null;
    tags?: Array<{ namespace: string | null; name: string }>;
    page_count?: number;
    favorite?: boolean;
  }>(`/api/galleries/${gallery.id}`);
  const originalLocal = {
    local_rating: detail.local_rating ?? null,
    local_note: detail.local_note ?? null,
    local_tags: (detail.tags ?? [])
      .filter((tag) => tag.namespace === "local")
      .map((tag) => tag.name),
  };

  try {
    await page.goto(`/#/gallery/${gallery.id}`);
    await expect(page.getByTestId("gallery-title")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("gallery-manage")).toBeVisible();
    await expect(page.getByTestId("local-fields")).toBeVisible();
    await expect(page.getByTestId("gallery-lists")).toBeVisible();

    if ((detail.page_count ?? 0) > 0) {
      await expect(page.getByTestId("thumb-grid")).toBeVisible({ timeout: 20_000 });
    } else {
      annotateUnverified("gallery has no pages; thumbnail grid was not rendered");
    }

    if (gallery.gid && gallery.token) {
      await expect(page.getByTestId("fav-button")).toBeVisible();
      await expect(page.getByTestId("download-button")).toBeVisible();
      await expect(page.getByTestId("download-original")).toBeVisible();
      await expect(page.getByTestId("sync-tags")).toBeVisible();
    } else {
      annotateUnverified("gallery has no EH gid/token; cloud quick actions were not rendered");
    }

    // Local field editing: write a unique note, verify persistence, then restore
    // the captured tri-state in `finally`.
    const note = `parity-note-${Date.now().toString(36)}`;
    // `local-note` is the shared TextArea wrapper (GalleryManageSection); the
    // editable control is the textarea inside it.
    const noteField = page.getByTestId("local-note");
    await expect(noteField.locator("textarea")).toHaveCount(1);
    await noteField.locator("textarea").fill(note);
    const patched = page.waitForResponse(
      (response) =>
        response.request().method() === "PATCH" &&
        response.url().includes(`/api/galleries/${gallery.id}/local`),
    );
    await page.getByTestId("save-local").click();
    expect((await patched).ok()).toBeTruthy();
    await expect
      .poll(async () => {
        const current = await app.api.get<{ local_note?: string | null }>(
          `/api/galleries/${gallery.id}`,
        );
        return current.local_note ?? "";
      })
      .toBe(note);

    await page.getByTestId("delete-gallery").click();
    await expect(page.getByTestId("delete-gallery-confirm")).toBeVisible();
    await page.keyboard.press("Escape");
    annotateUnverified("gallery delete / delete-files / download-original / sync-tags were not executed");
  } finally {
    await app.api
      .patch(`/api/galleries/${gallery.id}/local`, originalLocal)
      .catch(() => undefined);
  }
  await app.shot("V-03");
});

test("V-04 阅读器：五种模式 / 键盘 / 预载 / 进度写回 / 轮播 @parity", async ({ app }) => {
  const { page } = app;
  const gallery = await firstGallery(app.api);
  test.skip(!gallery, "test library is empty");
  if (!gallery) return;
  test.skip((gallery.page_count ?? 0) === 0, "gallery has no pages");
  if (!gallery.page_count) return;

  const progressResponse = await page.request.get(`/api/galleries/${gallery.id}/progress`);
  const originalProgress = progressResponse.ok()
    ? ((await progressResponse.json()) as { current_page?: number; total_pages?: number })
    : null;
  let imageRequests = 0;
  page.on("request", (request) => {
    if (/\/api\/galleries\/\d+\/pages\/\d+$/.test(new URL(request.url()).pathname)) {
      imageRequests += 1;
    }
  });

  try {
    await page.goto(`/#/reader/${gallery.id}/0`);
    await expect(page.getByTestId("reader-shell")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("reader-page-label")).toContainText("1");
    await expect.poll(() => imageRequests).toBeGreaterThan(0);

    // Five modes through the real settings sheet. Bars start hidden.
    if ((await page.getByTestId("reader-shell").getAttribute("data-bars")) !== "visible") {
      await page.getByTestId("reader-zone-center").click();
    }
    await expect(page.getByTestId("reader-settings")).toBeVisible();
    await page.getByTestId("reader-settings").click();
    await expect(page.getByTestId("reader-settings-panel")).toBeVisible();
    for (const mode of ["rtl", "double", "double-rtl", "ltr"]) {
      await page
        .locator(`[data-testid="reader-mode-control"] [data-segmented-value="${mode}"]`)
        .click();
      await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-mode", mode);
    }
    await page
      .locator('[data-testid="reader-mode-control"] [data-segmented-value="webtoon"]')
      .click();
    await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-mode", "webtoon");
    await expect(page.getByTestId("webtoon-strip")).toBeVisible({ timeout: 20_000 });
    await page
      .locator('[data-testid="reader-mode-control"] [data-segmented-value="ltr"]')
      .click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("reader-settings-panel")).toHaveCount(0);

    // Keyboard page turn + durable progress write-back.
    if (gallery.page_count > 1) {
      const before = await page.getByTestId("reader-shell").getAttribute("data-page");
      const saved = page.waitForResponse(
        (response) =>
          response.request().method() === "PUT" &&
          response.url().includes(`/api/galleries/${gallery.id}/progress`),
      );
      await page.keyboard.press("ArrowRight");
      await expect(page.getByTestId("reader-shell")).not.toHaveAttribute(
        "data-page",
        before ?? "0",
      );
      expect((await saved).ok()).toBeTruthy();
    } else {
      annotateUnverified("single-page gallery: keyboard page turn and progress PUT not exercised");
    }

    // Slideshow controls (duration-aware animated timing is a known gap; see receipt).
    if ((await page.getByTestId("reader-shell").getAttribute("data-bars")) !== "visible") {
      await page.getByTestId("reader-zone-center").click();
    }
    await expect(page.getByTestId("reader-slideshow")).toBeVisible();
    await page.getByTestId("reader-slideshow").click();
    await expect(page.getByTestId("reader-slideshow")).toHaveClass(/active/);
    await page.getByTestId("reader-slideshow").click();
    await expect(page.getByTestId("reader-slideshow")).not.toHaveClass(/active/);
    annotateUnverified(
      "animated-image duration and bad-page placeholder were not forced; next-gallery depends on library order",
    );

    // Legacy page image + metadata contracts are exercised directly so the C3
    // endpoint coverage check is not limited to the URL string built by
    // LocalPageSource.
    const pagePath = galleryPageEp.path
      .replace("{id}", String(gallery.id))
      .replace("{id}", "0");
    const image = await page.request.get(pagePath);
    expect(image.ok()).toBeTruthy();
    expect(Number(image.headers()["content-length"] ?? 1)).toBeGreaterThan(0);

    const metaPath = galleryPageMetaEp.path
      .replace("{id}", String(gallery.id))
      .replace("{id}", "0");
    const meta = await page.request.get(metaPath);
    expect(meta.ok()).toBeTruthy();
    expect(await meta.json()).toBeTruthy();
  } finally {
    if (originalProgress) {
      await app.api
        .put(`/api/galleries/${gallery.id}/progress`, {
          current_page: originalProgress.current_page ?? 0,
          total_pages: originalProgress.total_pages ?? gallery.page_count,
        })
        .catch(() => undefined);
    } else {
      await app.api.del(`/api/galleries/${gallery.id}/progress`).catch(() => undefined);
    }
  }
  await app.shot("V-04", { fullPage: false });
});
