import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { addFavoritesEp } from "@/api/favorites";
import { createDownloadEp } from "@/api/downloads";
import { mockActionsBackend } from "./fixtures/actions/mock";
import { freePort, watchCsp } from "./support/polish";

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

let vite: ViteDevServer;
let HARNESS = "";



type Theme = "dark" | "light";

function harnessUrl(options: {
  density?: "card" | "detail" | "toolbar";
  theme?: Theme;
  favorited?: boolean;
  favcat?: number;
  inLibrary?: boolean;
}): string {
  const params = new URLSearchParams();
  params.set("density", options.density ?? "card");
  params.set("theme", options.theme ?? "dark");
  if (options.favorited) params.set("favorited", "1");
  if (options.favcat !== undefined) params.set("favcat", String(options.favcat));
  if (options.inLibrary) params.set("inLibrary", "1");
  return `${HARNESS}?${params.toString()}`;
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true });
}

async function longPress(page: Page): Promise<void> {
  const actions = page.getByTestId("gallery-actions");
  await actions.dispatchEvent("pointerdown", {
    button: 0,
    pointerType: "touch",
    pointerId: 1,
    isPrimary: true,
  });
  await page.waitForTimeout(700);
  await actions.dispatchEvent("pointerup", {
    button: 0,
    pointerType: "touch",
    pointerId: 1,
    isPrimary: true,
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
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/actions/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

test.beforeEach(async ({ page }) => {
  await page.context().addCookies([
    { name: "galleryvault_csrf", value: "test-csrf", url: HARNESS },
  ]);
  await page.addInitScript(() => {
    try {
      localStorage.setItem("gv_default_favcat", "3");
    } catch {
      /* about:blank has no storage */
    }
  });
});

test.describe("quick actions @actions", () => {
  test("card one-click favorite lands in favcat 3 with the slot colour", async ({ page }) => {
    const csp = watchCsp(page);
    const mock = await mockActionsBackend(page);

    await page.goto(harnessUrl({ density: "card", theme: "dark" }));
    const actions = page.getByTestId("gallery-actions");
    await expect(actions).toBeVisible();
    await expect(actions).toHaveCSS("opacity", "0");

    await page.getByTestId("card-shell").hover();
    await expect(actions).toHaveCSS("opacity", "1");

    await page.getByTestId("fav-button").click();
    const heart = page.getByTestId("fav-heart");
    await expect(heart).toHaveAttribute("data-favcat", "3");
    const color = await heart.evaluate((element) => getComputedStyle(element).color);
    expect(color).toBe("rgb(221, 229, 0)");

    expect(mock.addRequests).toBe(1);
    const add = mock.writes.find((write) => write.path === addFavoritesEp.path);
    expect(add).toBeTruthy();
    expect(add?.csrf).toBe("test-csrf");
    expect(add?.body).toMatchObject({ target_favcat: 3, gid: 4242 });
    expect(csp).toEqual([]);
  });

  test("favorite API 500 shows a toast and leaves the badge unchanged", async ({ page }) => {
    await mockActionsBackend(page, { addStatus: 500 });
    await page.goto(harnessUrl({ density: "card", theme: "dark" }));

    await page.getByTestId("fav-button").click();

    await expect(page.locator(".toast--error")).toContainText("收藏失败");
    const heart = page.getByTestId("fav-heart");
    expect(await heart.getAttribute("data-favcat")).toBeNull();
    await expect(page.getByTestId("fav-button")).toHaveAttribute("aria-pressed", "false");
  });

  test("one-click download badge goes queued → downloading x/y → in library", async ({
    page,
  }) => {
    const mock = await mockActionsBackend(page);
    await page.goto(harnessUrl({ density: "card", theme: "dark" }));

    await page.getByTestId("download-button").click();
    const badge = page.getByTestId("download-badge");
    await expect(badge).toHaveAttribute("data-status", "queued");
    await expect(badge).toHaveText("排队");

    // The store polls `/api/eh/status`; drive its own visibility tick and wait
    // for the observed state instead of racing a long fixed timeout.
    await expect
      .poll(
        async () => {
          await page.evaluate(() =>
            document.dispatchEvent(new Event("visibilitychange")),
          );
          return badge.getAttribute("data-status");
        },
        { timeout: 15_000 },
      )
      .toBe("downloading");
    await expect(badge).toHaveText("下载中 3/10");

    await expect
      .poll(
        async () => {
          await page.evaluate(() =>
            document.dispatchEvent(new Event("visibilitychange")),
          );
          return badge.getAttribute("data-status");
        },
        { timeout: 15_000 },
      )
      .toBe("success");
    await expect(badge).toHaveText("已在库");

    const post = mock.writes.find(
      (write) => write.path === createDownloadEp.path && write.method === "POST",
    );
    expect(post?.csrf).toBe("test-csrf");
    expect(post?.body).toMatchObject({ gid: 4242, quality: "resample" });
    expect(mock.writes.every((write) => write.csrf === "test-csrf")).toBe(true);
  });

  test("screenshots: hover overlay, favcat picker, mobile long-press sheet", async ({ page }) => {
    const csp = watchCsp(page);
    await mockActionsBackend(page, { statusSequence: ["none"] });

    for (const theme of ["dark", "light"] as const) {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(harnessUrl({ density: "card", theme }));
      await page.getByTestId("card-shell").hover();
      await expect(page.getByTestId("gallery-actions")).toHaveCSS("opacity", "1");
      await shot(page, `actions-desktop-1280-${theme}-hover`);

      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(harnessUrl({ density: "detail", theme }));
      await page.getByTestId("fav-select").click();
      await expect(page.getByTestId("fav-picker")).toBeVisible();
      await expect(page.getByTestId("fav-cat-3")).toBeVisible();
      await shot(page, `actions-desktop-1280-${theme}-favcat-picker`);

      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(harnessUrl({ density: "card", theme }));
      await longPress(page);
      await expect(page.getByTestId("action-sheet")).toBeVisible();
      await page.waitForTimeout(400);
      await shot(page, `actions-mobile-390-${theme}-sheet`);

      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(harnessUrl({ density: "detail", theme }));
      await page.getByTestId("fav-select").click();
      await expect(page.getByTestId("fav-sheet")).toBeVisible();
      await expect(page.getByTestId("fav-cat-3")).toBeVisible();
      await page.waitForTimeout(400);
      await shot(page, `actions-mobile-390-${theme}-favcat-picker`);
    }

    expect(csp).toEqual([]);
  });
});
