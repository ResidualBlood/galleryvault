import { expect, test } from "./fixtures/mock";
import {
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * `#/_kit` is the shared specimen page for the polish phase. It must stay out
 * of the navigation, collect `views/kit/sections/*.vue` automatically, and
 * expose the tokens baseline (control ladder + tag namespace palette) so every
 * later component task has a browser-level fixture to assert against.
 */
test("component kit renders the tokens baseline and captures four variants @kit", async ({
  page,
}) => {
  await page.goto("/#/_kit");

  const kit = page.getByTestId("kit-view");
  await expect(kit).toBeVisible();
  await expect(kit.getByRole("heading", { level: 1, name: "Component specimen" })).toBeVisible();
  await expect(kit.getByTestId("kit-tokens")).toBeVisible();

  // Both ladders are present and rendered from tokens.
  await expect(kit.getByTestId("kit-tokens-controls").locator("[data-token]")).toHaveCount(4);
  await expect(kit.getByTestId("kit-tokens-icons").locator("[data-token]")).toHaveCount(4);
  await expect(kit.getByTestId("kit-tokens-controls").locator("[data-token]").first()).toHaveAttribute(
    "data-token",
    "--gv-size-control-xl",
  );

  // The ladder really renders four distinct heights (xl/lg/md/sm).
  const barHeights = await kit
    .getByTestId("kit-tokens-controls")
    .locator(".tokens__bar")
    .evaluateAll((bars) => bars.map((bar) => Math.round(bar.getBoundingClientRect().height)));
  expect(barHeights).toEqual([48, 40, 36, 32]);
  const iconWidths = await kit
    .getByTestId("kit-tokens-icons")
    .locator(".tokens__icon")
    .evaluateAll((icons) => icons.map((icon) => Math.round(icon.getBoundingClientRect().width)));
  expect(iconWidths).toEqual([16, 18, 20, 24]);

  // All 15 EH namespaces used by the tag UI have a colour swatch.
  await expect(kit.getByTestId("kit-tagns-swatch")).toHaveCount(15);
  await expect(
    kit.locator('[data-testid="kit-tagns-swatch"][data-namespace="uploader"]'),
  ).toBeVisible();

  // No character "icons", no horizontal overflow, no mixed-height toolbar row.
  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-view"]' });
  await expectNoHorizontalOverflow(page);
  await expectRowsAligned(page, { requireRows: false });

  const shots = await shotMatrix(page, "kit", { fullPage: true });
  expect(shots.files).toHaveLength(4);
});

test("component kit stays inside a 390 viewport @kit", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/_kit");
  await expect(page.getByTestId("kit-tokens")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-view"]' });
});
