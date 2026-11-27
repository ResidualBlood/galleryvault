import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import { mockActionsBackend, type ActionsMockOptions } from "./fixtures/actions/mock";
import { mockOnlineBackend } from "./fixtures/online/mock";
import { LIST_GID, LIST_TOKEN } from "./fixtures/online/data";
import { mockGalleryBackend } from "./fixtures/gallery/mock";
import { SMALL_GALLERY_ID } from "./fixtures/gallery/data";
import { mockOnlineReaderBackend } from "./fixtures/online-reader/mock";
import { READER_GID, READER_TOKEN } from "./fixtures/online-reader/data";
import { addFavoritesEp } from "@/api/favorites";
import { createDownloadEp } from "@/api/downloads";
import { watchCsp } from "./support/polish";

/**
 * Routed-app coverage for the quick actions batch: the same GalleryActions /
 * favourites / downloads stores are mounted on the online list card, online
 * detail, local detail and the online reader toolbar + end panel.
 *
 * Every backend is mocked; nothing leaves the preview server. The shared
 * `fixtures/mock` session handler is the base layer, and the more specific
 * fixtures registered inside each test take precedence (Playwright matches
 * routes in reverse registration order).
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");


async function onlineWithActions(
  page: Page,
  options: ActionsMockOptions = {},
) {
  // Registered in this order so the action fixture (added last) is matched
  // first for its endpoints/status, then falls back to the online fixture and
  // finally to the shared session mock.
  await mockOnlineBackend(page);
  const mock = await mockActionsBackend(page, { ...options, fallbackUnknown: true });
  return mock;
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

test.beforeEach(async ({ page, baseURL }) => {
  await page.context().addCookies([
    { name: "galleryvault_csrf", value: "test-csrf", url: baseURL ?? "http://127.0.0.1" },
  ]);
  await page.addInitScript(() => {
    try {
      localStorage.setItem("gv_default_favcat", "3");
    } catch {
      /* about:blank has no storage */
    }
  });
});

test.describe("quick actions wired into the real routes @actions-wired", () => {
  test("online list card favourite flips the card badge to favourited", async ({ page }) => {
    const csp = watchCsp(page);
    const mock = await onlineWithActions(page);

    await page.goto("/#/online");
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "12");

    const card = page.getByTestId("gallery-card").first();
    await expect(card.getByTestId("fav-button")).toHaveAttribute("aria-pressed", "false");
    await card.getByTestId("fav-button").click();

    await expect(card.getByTestId("fav-button")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".toast--success")).toContainText("已收藏");
    await expect(card.getByTestId("fav-heart")).toHaveAttribute("data-favcat", "3");
    await expect(card.getByTestId("fav-button")).toHaveAttribute("data-state", "favorited");

    expect(mock.writes.some((write) => write.path === addFavoritesEp.path)).toBe(true);
    const add = mock.writes.find((write) => write.path === addFavoritesEp.path);
    expect(add?.csrf).toBe("test-csrf");
    expect(add?.body).toMatchObject({ gid: 910001, target_favcat: 3 });
    expect(csp).toEqual([]);
  });

  test("online detail download enqueues and shows the downloading badge", async ({ page }) => {
    const csp = watchCsp(page);
    const mock = await onlineWithActions(page, { statusSequence: ["none", "downloading"] });

    await page.goto(`/#/online/g/${LIST_GID}/${LIST_TOKEN}`);
    await expect(page.getByTestId("online-title")).toHaveText("Online Detail Fixture");

    const actions = page.getByTestId("online-actions").getByTestId("gallery-actions");
    const badge = actions.getByTestId("download-badge");
    await actions.getByTestId("download-button").click();
    await expect(badge).toHaveAttribute("data-status", "queued");
    await expect(badge).toContainText("排队");

    // Force one visibility tick so the poller reads the second (downloading)
    // status phase instead of waiting for the idle interval.
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await expect(badge).toHaveAttribute("data-status", "downloading");
    await expect(badge).toContainText("下载中");

    const post = mock.writes.find((write) => write.path === createDownloadEp.path);
    expect(post?.method).toBe("POST");
    expect(post?.body).toMatchObject({ gid: LIST_GID, token: LIST_TOKEN });
    await page.screenshot({ path: join(SHOTS, "actions-wired-online-detail.png"), fullPage: true });
    expect(csp).toEqual([]);
  });

  test("online reader toolbar favourite and end panel use the wired actions", async ({ page }) => {
    const csp = watchCsp(page);
    const mock = await mockActionsBackend(page, { fallbackUnknown: true });
    await mockOnlineReaderBackend(page);

    await page.goto(`/#/online/g/${READER_GID}/${READER_TOKEN}/read/0`);
    // The action strip rides with the bottom bar (OR-05), so call the bars up
    // before touching favourite / download.
    await expect(page.getByTestId("reader-shell")).toBeVisible();
    await expect(page.getByTestId("reader-loading")).toHaveCount(0);
    if ((await page.getByTestId("reader-shell").getAttribute("data-bars")) !== "visible") {
      await page.getByTestId("reader-zone-center").click();
    }
    const actions = page.getByTestId("online-reader-actions");
    await expect(actions).toBeVisible();

    await actions.getByTestId("fav-button").click();
    await expect(actions.getByTestId("fav-button")).toHaveAttribute("aria-pressed", "true");
    expect(
      mock.writes.some(
        (write) => write.path === addFavoritesEp.path && write.body.gid === READER_GID,
      ),
    ).toBe(true);

    // Jump to the last page (keyboard, so the auto-hidden bottom bar is not in
    // the way); the end panel hosts the same wired actions (no event stub /
    // legacy download button).
    await page.keyboard.press("End");
    const end = page.getByTestId("online-reader-end");
    await expect(end).toBeVisible();
    await expect(end.getByTestId("gallery-actions")).toBeVisible();
    await expect(end.getByTestId("download-button")).toBeVisible();
    await expect(page.getByTestId("online-reader-download")).toHaveCount(0);
    await page.screenshot({ path: join(SHOTS, "actions-wired-reader-toolbar.png") });
    expect(csp).toEqual([]);
  });

  test("local detail favourite writes through the cloud-confirmed store", async ({ page }) => {
    const csp = watchCsp(page);
    const mock = await mockActionsBackend(page, { fallbackUnknown: true });
    await mockGalleryBackend(page);

    await page.goto(`/#/gallery/${SMALL_GALLERY_ID}`);
    await expect(page.getByTestId("gallery-title")).toHaveText("Small Detail Fixture");

    const fav = page.getByTestId("gallery-actions").getByTestId("fav-button");
    await expect(fav).toHaveAttribute("aria-pressed", "false");
    await fav.click();
    await expect(fav).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("gallery-actions").getByTestId("download-badge")).toHaveText(
      "已在库",
    );
    expect(mock.writes.some((write) => write.path === addFavoritesEp.path)).toBe(true);
    expect(csp).toEqual([]);
  });

  test("cloud-rejected favourite keeps the card unchanged and surfaces an error", async ({
    page,
  }) => {
    const csp = watchCsp(page);
    await onlineWithActions(page, { addCloudFail: true });

    await page.goto("/#/online");
    await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "12");

    const card = page.getByTestId("gallery-card").first();
    const fav = card.getByTestId("fav-button");
    await fav.click();

    await expect(page.locator(".toast--error")).toContainText("收藏失败");
    await expect(fav).toHaveAttribute("aria-pressed", "false");
    await expect(card.getByTestId("fav-heart")).not.toHaveAttribute("data-favcat", /.+/);
    expect(csp).toEqual([]);
  });
});
