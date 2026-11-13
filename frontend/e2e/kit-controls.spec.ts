import { expect, installMockBackend, test } from "./fixtures/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  shotMatrix,
} from "./support/polish";
import type { Page } from "@playwright/test";

/**
 * `#/_kit` control specimen: the shared ladder is 40 / 36 / 32 (mouse) and
 * 44 / 40 / 36 (coarse pointer). Every row must be equal-height with centres
 * inside 1px, the icon sits on the text centre line, the Select chevron is
 * vertically centred, disabled filled keeps >=3:1, and every control shows a
 * keyboard focus ring.
 */
const STEPS = [
  { size: "lg", height: 40, touchHeight: 44 },
  { size: "md", height: 36, touchHeight: 40 },
  { size: "sm", height: 32, touchHeight: 36 },
] as const;

const FOCUS_TARGETS = [
  "kit-focus-button",
  "kit-focus-icon",
  "kit-focus-input",
  "kit-focus-select",
  "kit-focus-switch",
  "kit-focus-checkbox",
  "kit-focus-textarea",
  "kit-focus-slider",
];

interface Box {
  height: number;
  center: number;
}

async function rowBoxes(page: Page, size: string): Promise<Box[]> {
  return page.getByTestId(`kit-row-${size}`).evaluate((row) =>
    [...row.querySelectorAll("[data-gv-control]")].map((element) => {
      const rect = element.getBoundingClientRect();
      return { height: rect.height, center: rect.top + rect.height / 2 };
    }),
  );
}

async function disabledFilledContrast(page: Page): Promise<number> {
  return page.evaluate(() => {
    interface Rgba {
      r: number;
      g: number;
      b: number;
      a: number;
    }

    const parse = (value: string): Rgba | null => {
      const rgb = value.match(/rgba?\(([^)]+)\)/);
      if (rgb) {
        const parts = rgb[1].split(/[,/\s]+/).filter(Boolean).map(Number);
        return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
      }
      const srgb = value.match(/color\(srgb\s+([^)]+)\)/);
      if (srgb) {
        const parts = srgb[1].split(/[\s/]+/).filter(Boolean).map(Number);
        return {
          r: parts[0] * 255,
          g: parts[1] * 255,
          b: parts[2] * 255,
          a: parts[3] ?? 1,
        };
      }
      return null;
    };
    const over = (fg: Rgba, bg: Rgba): Rgba => ({
      r: fg.r * fg.a + bg.r * (1 - fg.a),
      g: fg.g * fg.a + bg.g * (1 - fg.a),
      b: fg.b * fg.a + bg.b * (1 - fg.a),
      a: 1,
    });
    const luminance = ({ r, g, b }: Rgba): number => {
      const channel = (value: number): number => {
        const s = value / 255;
        return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };

    const button = document.querySelector('[data-testid="kit-disabled-filled"]');
    if (!button) return 0;
    const layers: Rgba[] = [];
    for (let node: Element | null = button; node; node = node.parentElement) {
      const parsed = parse(getComputedStyle(node).backgroundColor);
      if (parsed && parsed.a > 0) layers.push(parsed);
    }
    let background: Rgba = { r: 255, g: 255, b: 255, a: 1 };
    for (const layer of layers.reverse()) background = over(layer, background);

    const foreground = parse(getComputedStyle(button).color) ?? { r: 0, g: 0, b: 0, a: 1 };
    const text = over(foreground, background);
    const light = Math.max(luminance(text), luminance(background));
    const dark = Math.min(luminance(text), luminance(background));
    return (light + 0.05) / (dark + 0.05);
  });
}

test("control ladder, icon alignment and chevron centring @kit-controls", async ({ page }) => {
  await page.goto("/#/_kit");
  const section = page.getByTestId("kit-controls");
  await expect(section).toBeVisible();

  for (const step of STEPS) {
    const row = page.getByTestId(`kit-row-${step.size}`);
    await expect(row).toHaveAttribute("data-height", String(step.height));

    const controls = row.locator("[data-gv-control]");
    await expect(controls).toHaveCount(4);
    await expectControlHeights(controls, step.height);

    const boxes = await rowBoxes(page, step.size);
    const heights = boxes.map((box) => box.height);
    const centers = boxes.map((box) => box.center);
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(0.5);
    expect(Math.max(...centers) - Math.min(...centers)).toBeLessThanOrEqual(1);
  }

  // Icon and label share a centre line inside the icon button.
  const buttonLine = await page.getByTestId("kit-button-with-icon").evaluate((button) => {
    const icon = button.querySelector("svg");
    const text = [...button.childNodes].find(
      (node) => node.nodeType === Node.TEXT_NODE && (node.textContent ?? "").trim().length > 0,
    );
    if (!icon || !text) return null;
    const range = document.createRange();
    range.selectNodeContents(text);
    const iconRect = icon.getBoundingClientRect();
    const textRect = range.getBoundingClientRect();
    return {
      icon: iconRect.top + iconRect.height / 2,
      text: textRect.top + textRect.height / 2,
    };
  });
  expect(buttonLine, "icon + label must both be in the button").not.toBeNull();
  expect(Math.abs(buttonLine!.icon - buttonLine!.text)).toBeLessThanOrEqual(1);

  // The Select chevron is a centred Icon, not a text glyph.
  const chevron = await page.getByTestId("kit-row-lg").evaluate((row) => {
    const select = row.querySelector("select");
    const icon = row.querySelector(".select-field__chevron");
    if (!select || !icon) return null;
    const selectRect = select.getBoundingClientRect();
    const iconRect = icon.getBoundingClientRect();
    return {
      tag: icon.tagName.toLowerCase(),
      diff:
        (iconRect.top + iconRect.height / 2) - (selectRect.top + selectRect.height / 2),
    };
  });
  expect(chevron, "Select must render the Icon chevron").not.toBeNull();
  expect(chevron!.tag).toBe("svg");
  expect(Math.abs(chevron!.diff)).toBeLessThanOrEqual(1);

  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-controls"]' });
  await expectNoHorizontalOverflow(page);
});

test("every control exposes a visible keyboard focus ring @kit-controls", async ({ page }) => {
  await page.goto("/#/_kit");
  await expect(page.getByTestId("kit-controls")).toBeVisible();
  await page.getByTestId("kit-focus-start").focus();

  const seen: Record<string, boolean> = {};
  for (let press = 0; press < 80 && Object.keys(seen).length < FOCUS_TARGETS.length; press += 1) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      if (!active) return null;
      const host = active.closest("[data-testid]");
      const testid = host?.getAttribute("data-testid") ?? "";
      const ring = active.matches(".checkbox__input")
        ? active.nextElementSibling
        : active;
      if (!ring) return { testid, visible: false };
      const style = getComputedStyle(ring);
      const outline =
        style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth || "0") > 0;
      const shadow = style.boxShadow !== "none" && style.boxShadow !== "";
      return { testid, visible: outline || shadow };
    });
    if (info && FOCUS_TARGETS.includes(info.testid)) seen[info.testid] = info.visible;
  }

  expect(seen).toEqual(Object.fromEntries(FOCUS_TARGETS.map((target) => [target, true])));
});

test("disabled filled keeps at least 3:1 in both themes @kit-controls", async ({ page }) => {
  await page.goto("/#/_kit");
  for (const theme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
    await page.reload();
    await page.waitForLoadState("networkidle").catch(() => {});
    await expect(page.getByTestId("kit-controls")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

    const ratio = await disabledFilledContrast(page);
    expect(ratio, `disabled filled contrast in ${theme}`).toBeGreaterThanOrEqual(3);
  }
  await page.emulateMedia({ colorScheme: null });
});

test("coarse pointer raises the three ladder steps to 44 / 40 / 36 @kit-controls", async ({
  browser,
}) => {
  const context = await browser.newContext({
    hasTouch: true,
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();
  await installMockBackend(page, { expired: false, authenticated: true });

  try {
    await page.goto("/#/_kit");
    await expect(page.getByTestId("kit-controls")).toBeVisible();
    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);

    for (const step of STEPS) {
      await expectControlHeights(
        page.getByTestId(`kit-row-${step.size}`).locator("[data-gv-control]"),
        step.touchHeight,
      );
      const boxes = await rowBoxes(page, step.size);
      const centers = boxes.map((box) => box.center);
      expect(Math.max(...centers) - Math.min(...centers)).toBeLessThanOrEqual(1);
    }
  } finally {
    await context.close();
  }
});

test("controls stay inside a 390 viewport @kit-controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/_kit");
  await expect(page.getByTestId("kit-controls")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-controls"]' });
});

test("kit controls load with zero CSP violations @kit-controls", async ({ page }) => {
  const csp: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (
      message.type() === "error" &&
      /content security policy|refused to (?:load|execute|connect)/i.test(text)
    ) {
      csp.push(text);
    }
  });
  page.on("pageerror", (error) => {
    if (/content security policy/i.test(error.message)) csp.push(error.message);
    else pageErrors.push(error.message);
  });

  await page.goto("/#/_kit");
  await expect(page.getByTestId("kit-controls")).toBeVisible();
  await page.getByTestId("kit-focus-input").click();
  await page.keyboard.type("csp");
  await page.getByTestId("kit-focus-select").selectOption("id_asc");

  expect(csp).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("screenshot matrix for each control state @kit-controls", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/#/_kit");
  const base = page.url().replace(/#.*$/, "");

  for (const state of ["default", "disabled", "error", "loading"]) {
    const shots = await shotMatrix(page, `kit-controls-${state}`, {
      url: `${base}#/_kit?state=${state}`,
      fullPage: true,
    });
    expect(shots.files, `${state} must produce four screenshots`).toHaveLength(4);
  }
});
