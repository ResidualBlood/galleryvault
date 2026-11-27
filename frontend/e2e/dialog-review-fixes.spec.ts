import { fileURLToPath } from "node:url";
import { createServer, type ViteDevServer } from "vite";
import { expect, test } from "@playwright/test";
import { mockActionsBackend } from "./fixtures/actions/mock";
import { installMockBackend } from "./fixtures/mock";
import { installLibraryMock } from "./fixtures/library/seed";
import { freePort } from "./support/polish";

/**
 * Regressions for the native-dialog migration review.
 *
 *  1. The favorite picker is one native dialog whose layout adapts; crossing
 *     599px while it is open must keep the dialog modal and focus inside it.
 *  2. A TagMenu teleported into an open Sheet is part of that modal: using it
 *     must not count as a backdrop press and close the parent sheet.
 */

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));

let vite: ViteDevServer;
let harness = "";

test.beforeAll(async () => {
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  harness = `http://127.0.0.1:${port}/e2e/fixtures/actions/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

test("fav picker survives crossing 390 → 1280 while open", async ({ page }) => {
  await mockActionsBackend(page, { statusSequence: ["none"] });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${harness}?density=detail&theme=dark`);

  await page.getByTestId("fav-select").click();
  const sheet = page.getByTestId("fav-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByTestId("fav-cat-3")).toBeVisible();

  await page.setViewportSize({ width: 1280, height: 900 });
  const picker = page.getByTestId("fav-picker");
  await expect(picker).toBeVisible();
  expect(await picker.evaluate((el) => (el as HTMLDialogElement).open)).toBe(true);
  expect(await picker.evaluate((el) => (el as HTMLDialogElement).matches(":modal"))).toBe(true);

  const focus = await page.evaluate(() => {
    const active = document.activeElement;
    return {
      tag: active?.tagName ?? "",
      inside: Boolean(active && active.closest("[data-testid='fav-picker']")),
    };
  });
  expect(focus.tag).not.toBe("BODY");
  expect(focus.inside).toBe(true);

  await page.keyboard.press("Escape");
  await expect(picker).toHaveCount(0);
});

test("tag menu action inside the card tag sheet keeps the parent modal open", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  // Explicit mocks: the shared fixture's `**/api/**` route would also swallow
  // Vite module URLs (/src/api/*.ts) in the action harness above.
  await installMockBackend(page, { expired: false, authenticated: true });
  await installLibraryMock(page, { total: 24 });
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-grid")).toBeVisible({ timeout: 20_000 });

  const card = page.getByTestId("gallery-card").first();
  await card.dispatchEvent("pointerdown", {
    pointerType: "touch",
    clientX: 40,
    clientY: 260,
    bubbles: true,
  });

  const sheet = page.getByTestId("card-tag-sheet");
  await expect(sheet).toBeVisible({ timeout: 3_000 });
  const dialog = page.locator("dialog[open]").filter({ has: sheet });
  expect(await dialog.evaluate((el) => (el as HTMLDialogElement).matches(":modal"))).toBe(true);

  await sheet.locator(".tag-chip").first().click({ button: "right" });
  const menu = page.getByTestId("tag-menu");
  await expect(menu).toBeVisible();
  await menu.getByTestId("tag-menu-copy").click();
  await expect(menu).toHaveCount(0);

  // The copy button sits outside the sheet panel rect; its press must not be
  // mistaken for a backdrop press, and the parent dialog must still be modal.
  expect(await dialog.evaluate((el) => (el as HTMLDialogElement).matches(":modal"))).toBe(true);
  await expect(sheet).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});
