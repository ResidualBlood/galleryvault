import { expect, test } from "./fixtures/mock";
import {
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  shotMatrix,
} from "./support/polish";

/**
 * Tag UI specimen. The `#/_kit` section is static, so every assertion here
 * proves the components work without touching the backend:
 *
 * - chip text is the tag body and follows the interface language live;
 * - the namespace lives in the colour dot and the tooltip;
 * - a chip inside a card link never opens that link;
 * - long press / right click opens the same menu and copies `ns:name`;
 * - `+N` reports the real hidden count (including truncated list payloads).
 */
test("tag kit stays language-reactive, clickable and truncates with +N @kit-tags", async ({
  page,
}) => {
  const cspViolations: string[] = [];
  const apiRequests: string[] = [];
  page.on("console", (message) => {
    if (/content security policy/i.test(message.text())) {
      cspViolations.push(message.text());
    }
  });
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api")) apiRequests.push(path);
  });
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);

  await page.goto("/#/_kit");

  const section = page.getByTestId("kit-tags");
  await expect(section).toBeVisible();

  // Two chip sizes measured in the browser.
  const small = await page
    .getByTestId("tag-size-24")
    .locator(".tag-chip")
    .first()
    .boundingBox();
  const large = await page
    .getByTestId("tag-size-28")
    .locator(".tag-chip")
    .first()
    .boundingBox();
  expect(Math.round(small?.height ?? 0)).toBe(24);
  expect(Math.round(large?.height ?? 0)).toBe(28);

  // +N counts the hidden tags, and tag_count wins over the truncated array.
  await expect(page.getByTestId("tag-list-truncated").getByTestId("tag-more")).toHaveText(
    "+8",
  );
  await expect(page.getByTestId("tag-list-full").getByTestId("tag-more")).toHaveText("+4");

  // Chinese shows the backend display value; the tooltip carries namespace and raw.
  const chip = page.getByTestId("tag-showcase-chip");
  await expect(chip).toHaveText("巨乳");
  await expect(chip).toHaveAttribute("title", "女性：female:big breasts");
  await expect(chip).toHaveAttribute("aria-label", "女性：female:big breasts");

  // Switching the interface language re-renders the chip without any /api call.
  const requestsBefore = apiRequests.length;
  await page.getByTestId("lang-toggle").click();
  await expect(chip).toHaveText("big breasts");
  await expect(chip).not.toContainText("female:");
  expect(apiRequests.length).toBe(requestsBefore);

  // A chip inside a link must not trigger the link.
  const beforeClick = page.url();
  await page.getByTestId("tag-in-link").click();
  await page.waitForTimeout(150);
  expect(page.url()).toBe(beforeClick);

  // Right click -> menu -> copy raw `ns:name`.
  await page.getByTestId("tag-menu-trigger").click({ button: "right" });
  const menu = page.getByTestId("tag-menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByTestId("tag-menu-copy")).toHaveText("Copy raw tag");
  await menu.getByTestId("tag-menu-copy").click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toBe("female:big breasts");
  await expect(menu).toBeHidden();

  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-view"]' });
  await expectNoHorizontalOverflow(page);
  expect(cspViolations).toEqual([]);

  const shots = await shotMatrix(page, "kit-tags", { fullPage: true });
  expect(shots.files).toHaveLength(4);
});

test("tag menu opens from a touch long press at 390 @kit-tags", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/_kit");

  const chip = page.getByTestId("tag-menu-trigger");
  await chip.scrollIntoViewIfNeeded();
  await chip.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    element.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        pointerType: "touch",
        clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2,
      }),
    );
  });

  const menu = page.getByTestId("tag-menu");
  await expect(menu).toBeVisible({ timeout: 2_000 });
  await expect(menu).toContainText("female:big breasts");

  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-view"]' });
});
