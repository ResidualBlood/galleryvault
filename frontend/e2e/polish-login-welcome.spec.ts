import { expect, type Page } from "@playwright/test";
import { sessionEp } from "@/api/auth";
import { test as mockTest } from "./fixtures/mock";
import {
  expectControlHeights,
  expectHitTargets,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * po-login-welcome polish gate (batch 21).
 *
 * Closes the eleven audit findings for the login page and the onboarding
 * wizard:
 *
 *   LG-01 / LG-02  topbar uses the same 56px + divider + SVG icon chrome as the
 *                  app shell, and the brand is printed once;
 *   LG-03 / LG-04  the single-column form is one xl (48px) step with 24px card
 *                  padding and aligned left/right edges;
 *   WL-01 … WL-07  the wizard uses PageHeader (headline-small), one xl control
 *                  step per action row, readable cookie labels with the
 *                  technical key demoted to helper text, a step indicator and
 *                  status chip, and GalleryCard for the recent list.
 */


function watchConsole(page: Page): string[] {
  const issues: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (
      message.type() === "error" &&
      /content security policy|refused to (?:load|execute|connect)/i.test(text)
    ) {
      issues.push(text);
    }
  });
  page.on("pageerror", (error) => {
    if (/content security policy/i.test(error.message)) issues.push(error.message);
  });
  return issues;
}

/**
 * The shared mock fixture keeps the session authenticated so every shell route
 * renders. The login page needs the opposite answer; a later route wins over
 * the fixture's catch-all.
 */
async function anonymousSession(page: Page): Promise<void> {
  await page.route(`**${sessionEp.path}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: false, auth_required: true }),
    });
  });
}

async function clearPasswordFields(page: Page): Promise<void> {
  for (const input of await page.locator('input[type="password"]').all()) {
    if (await input.isVisible()) await input.fill("");
  }
}

mockTest.describe("@polish-login-welcome", () => {
  mockTest("login page is one xl step with aligned edges @polish-login-welcome", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    await anonymousSession(page);
    await page.goto("/#/login");

    const card = page.getByTestId("login-card");
    await expect(card).toBeVisible();
    await expectNoGlyphIcons(page);

    // LG-02: the login chrome mirrors the shell topbar: 56px, one divider,
    // brand printed exactly once.
    const bar = page.getByTestId("login-bar");
    const barBox = await bar.boundingBox();
    expect(barBox).toBeTruthy();
    expect(Math.round(barBox!.height)).toBe(56);
    expect(await bar.evaluate((el) => getComputedStyle(el).borderBottomWidth)).toBe("1px");
    const brandCount = ((await page.locator("body").innerText()).match(/GalleryVault/g) ?? [])
      .length;
    expect(brandCount, "the brand must appear once, not in bar + mark + heading").toBe(1);
    await expect(card).not.toContainText("GalleryVault");

    // LG-01: theme / language are registry SVG icons on the lg (40px) step.
    expect(await bar.locator("svg.gv-icon").count()).toBe(2);
    await expectControlHeights(bar.locator("button"), 40);
    await expectHitTargets(bar.locator("button"), 44);

    // LG-03: input and CTA share the xl ladder step and both edges.
    const input = page.getByTestId("login-form").locator("input");
    const submit = page.getByTestId("login-submit");
    const inputBox = await input.boundingBox();
    const submitBox = await submit.boundingBox();
    expect(inputBox && submitBox).toBeTruthy();
    expect(Math.abs(inputBox!.height - 48)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(submitBox!.height - 48)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(inputBox!.x - submitBox!.x)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(inputBox!.width - submitBox!.width)).toBeLessThanOrEqual(0.5);

    // The password can be revealed through an icon button, never a glyph.
    const reveal = page.getByTestId("login-reveal");
    await expect(reveal).toHaveAttribute("aria-label", /显示明文|Show plain text/);
    await reveal.click();
    await expect(input).toHaveAttribute("type", "text");
    await expect(reveal).toHaveAttribute("aria-label", /隐藏明文|Hide plain text/);
    await reveal.click();
    await expect(input).toHaveAttribute("type", "password");

    // Errors carry aria-invalid + role=alert and the error copy. The mock
    // login endpoint answers 401 so the real auth store path runs.
    await page.route("**/login", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "unauthorized" }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html>" });
    });
    await input.fill("wrong-password");
    await submit.click();
    const alert = page.getByTestId("login-form").getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(input).toHaveAttribute("aria-invalid", "true");
    await expect(input).toHaveValue("");

    // 390: same form, no horizontal overflow.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#/login");
    await expect(card).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await clearPasswordFields(page);
    await shotMatrix(page, "login");
    expect(csp).toEqual([]);
  });

  mockTest("welcome keeps the shared header and readable field labels @polish-login-welcome", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    // WL-07: seed the recent strip so the GalleryCard contract is measurable.
    await page.route(/\/api\/galleries\?page_size=4$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: 1,
              gid: 101,
              token: "aa",
              title: "A recent local gallery with a title long enough to clamp at two lines",
              category: "doujinshi",
              page_count: 42,
              cover_url: null,
              tags: [],
            },
            {
              id: 2,
              gid: 102,
              token: "bb",
              title: "Second recent gallery",
              category: "manga",
              page_count: 18,
              cover_url: null,
              tags: [],
            },
            {
              id: 3,
              gid: 103,
              token: "cc",
              title: "Third recent gallery",
              category: "artistcg",
              page_count: 7,
              cover_url: null,
              tags: [],
            },
            {
              id: 4,
              gid: 104,
              token: "dd",
              title: "Fourth recent gallery",
              category: "cosplay",
              page_count: 12,
              cover_url: null,
              tags: [],
            },
          ],
        }),
      });
    });
    await page.goto("/#/welcome");

    await expect(page.getByTestId("welcome-page")).toBeVisible();
    await expect(page.getByTestId("welcome-password")).toBeVisible();
    await expect(page.getByTestId("welcome-site")).toBeVisible();
    await expect(page.getByTestId("welcome-finish")).toBeVisible();

    // WL-02: the shared PageHeader renders h1 on the headline-small step.
    const h1 = page.getByTestId("welcome-header").locator("h1");
    await expect(h1).toBeVisible();
    expect(await h1.evaluate((el) => getComputedStyle(el).fontSize)).toBe("24px");

    // WL-03: labels are human copy; the internal key only lives in the helper.
    const labels = await page
      .locator('[data-testid="welcome-site"] .gv-field__label')
      .allInnerTexts();
    const labelText = labels.join(" ");
    expect(labels.length).toBeGreaterThanOrEqual(4);
    for (const key of ["ipb_member_id", "ipb_pass_hash", "igneous"]) {
      expect(labelText).not.toContain(key);
    }
    const helpers = await page
      .locator('[data-testid="welcome-site"] .gv-field__help')
      .allInnerTexts();
    expect(helpers.join(" ")).toContain("ipb_member_id");
    expect(helpers.join(" ")).toContain("ipb_pass_hash");
    expect(helpers.join(" ")).toContain("igneous");

    // Saving connection settings clears the write-only cookie fields.
    const member = page.locator("#welcome-ipb-member-id");
    await member.fill("cookie-secret");
    await page.getByTestId("welcome-save-site").click();
    await expect(member).toHaveValue("");

    // WL-05 / WL-06: a visible step indicator and numbered card headings.
    await expect(page.locator(".welcome__steps .welcome__step")).toHaveCount(3);
    await expect(page.locator(".welcome__step-badge")).toHaveCount(3);

    // One control step (xl = 48px) for every field and button on the page.
    const controls = page.locator(
      '[data-testid="welcome-page"] input, [data-testid="welcome-page"] select, [data-testid="welcome-page"] button',
    );
    await expectControlHeights(controls, 48);

    // WL-04: action rows are single-row toolbars, equal height and centred.
    await expectRowsAligned(page, {
      rowSelector: '[data-testid="welcome-page"] [data-gv-toolbar]',
      requireRows: true,
    });

    // WL-04: connection state is a coloured chip, not bare 12px text.
    const status = page.getByTestId("welcome-site-status");
    const statusBox = await status.boundingBox();
    expect(statusBox).toBeTruthy();
    expect(Math.round(statusBox!.height)).toBe(32);
    expect(await status.locator(".welcome__status-dot").count()).toBe(1);

    // WL-07: the recent strip follows the GalleryCard contract (title-small,
    // 2-line clamp, category + page-count badges) instead of 12px markup.
    const recentCards = page.locator('[data-testid="welcome-recent"] .welcome__recent-link');
    await expect(recentCards).toHaveCount(4);
    const cardTitle = recentCards.first().locator(".welcome__recent-title-text");
    expect(await cardTitle.evaluate((el) => getComputedStyle(el).fontSize)).toBe("14px");
    expect(await cardTitle.evaluate((el) => getComputedStyle(el).webkitLineClamp)).toBe("2");
    await expect(recentCards.first().getByText("42P")).toBeVisible();
    await expect(recentCards.first().getByText("同人志", { exact: true })).toBeVisible();

    // No character icons anywhere in the wizard.
    await expectNoGlyphIcons(page);

    // 390: single column, no horizontal overflow.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#/welcome");
    await expect(page.getByTestId("welcome-page")).toBeVisible();
    await expectNoHorizontalOverflow(page);

    // Credentials must be blank before the screenshot matrix.
    await clearPasswordFields(page);
    for (const input of await page.locator('input[type="password"]').all()) {
      expect(await input.inputValue()).toBe("");
    }
    await shotMatrix(page, "welcome", { fullPage: true });
    expect(csp).toEqual([]);
  });
});

