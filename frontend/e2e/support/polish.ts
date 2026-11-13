import { mkdirSync } from "node:fs";
import { createServer as createTcpServer } from "node:net";
import { join } from "node:path";
import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Shared polish-phase assertions. These are deliberately DOM-measured (no
 * screenshots as the source of truth) so every later page task can prove the
 * audit findings are actually closed:
 *
 *   - expectNoGlyphIcons     no Unicode character stands in for an icon
 *   - expectControlHeights   one control ladder step per row
 *   - expectRowsAligned      same toolbar: equal heights, centres within 1px
 *   - expectNoHorizontalOverflow
 *   - expectTouchTargets     >= 44x44 hit areas
 *   - shotMatrix             dark/light x 1280/390 screenshots into $GV_SHOTS
 */

/** Unicode ranges the audit counted as character icons (whitelist: · separators). */
const GLYPH_SOURCE =
  "[\\u00D7\\u2039\\u203A\\u2190-\\u21FF\\u2300-\\u23FF\\u25A0-\\u27BF\\u2900-\\u2BFF\\u2261\\u2263\\u29C9\\u{1F300}-\\u{1FAFF}]";

const SHOT_DIR =
  process.env.GV_SHOTS || "/tmp/opencode/gv-frontend-rewrite/shots/polish";

/** Collect CSP console/page errors raised by a page (one watcher per page). */
export function watchCsp(page: Page): string[] {
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

/** Reserve an ephemeral 127.0.0.1 TCP port for a per-suite Vite harness. */
export function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createTcpServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      const port = typeof address === "object" && address ? address.port : 0;
      probe.close(() => resolve(port));
    });
  });
}

export interface RowsAlignedOptions {
  /** CSS selector for the row container. */
  rowSelector?: string;
  /** Allowed centre-line difference in CSS px. */
  tolerance?: number;
  /** Fail when no row container exists. */
  requireRows?: boolean;
}

export interface TouchTargetOptions {
  /** Minimum width and height in CSS px. */
  min?: number;
  selector?: string;
}

export interface ShotMatrixOptions {
  /** URL to capture; defaults to the current page URL. */
  url?: string;
  /** Output directory; defaults to $GV_SHOTS. */
  dir?: string;
  fullPage?: boolean;
}

export interface ShotMatrixResult {
  dir: string;
  files: string[];
}

let shotSeq = 0;

/** Add/replace a deterministic cache-buster before the hash so every variant boots. */
function withShotBuster(url: string, token: string): string {
  const hashAt = url.indexOf("#");
  const base = hashAt === -1 ? url : url.slice(0, hashAt);
  const hash = hashAt === -1 ? "" : url.slice(hashAt);
  const cleaned = base
    .replace(/([?&])_gvshot=[^&]*&?/g, "$1")
    .replace(/[?&]$/, "")
    .replace(/&{2,}/g, "&")
    .replace(/\?&/, "?");
  const sep = cleaned.includes("?") ? "&" : "?";
  return `${cleaned}${sep}_gvshot=${token}${hash}`;
}

/** Fail when visible text contains a character-icon glyph. */
export async function expectNoGlyphIcons(
  page: Page,
  options: { selector?: string } = {},
): Promise<void> {
  const offenders = await page.evaluate(
    ({ source, selector }) => {
      const icon = new RegExp(source, "u");
      const separators = /[\u00B7\u2022\u2013\u2014\u2026]/g;
      const root = (selector ? document.querySelector(selector) : document.body) ?? document.body;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const found: string[] = [];
      let node = walker.nextNode();
      while (node) {
        const parent = node.parentElement;
        const tag = parent?.tagName ?? "";
        if (parent && tag !== "SCRIPT" && tag !== "STYLE") {
          const text = (node.textContent ?? "").replace(separators, "").trim();
          if (text && icon.test(text)) {
            found.push(`${tag.toLowerCase()}: ${text.slice(0, 40)}`);
          }
        }
        node = walker.nextNode();
      }
      return found;
    },
    { source: GLYPH_SOURCE, selector: options.selector ?? "" },
  );
  expect(offenders, "character icons must be replaced by <Icon name=…>").toEqual([]);
}

/**
 * Every visible tag chip must keep a readable text run: at least 24px of text
 * or a fully shown short label (`scrollWidth <= clientWidth + 1`). This is the
 * regression guard for flex rows squeezing chips down to the namespace dot.
 */
export async function expectTagChipsReadable(chips: Locator): Promise<void> {
  const boxes = await chips.evaluateAll((nodes) =>
    nodes
      .filter((node) => {
        const rect = node.getBoundingClientRect();
        return rect.width > 1 && rect.height > 1;
      })
      .map((node) => {
        const text = node.querySelector<HTMLElement>(".tag-chip__text");
        if (!text) return { label: "", width: 0, clientWidth: 0, scrollWidth: 0 };
        const rect = text.getBoundingClientRect();
        return {
          label: (text.textContent ?? "").trim(),
          width: Math.round(rect.width * 10) / 10,
          clientWidth: text.clientWidth,
          scrollWidth: text.scrollWidth,
        };
      }),
  );
  expect(boxes.length, "expected at least one visible tag chip").toBeGreaterThan(0);
  for (const box of boxes) {
    const readable =
      box.width > 0 && (box.width >= 24 || box.scrollWidth <= box.clientWidth + 1);
    expect(
      readable,
      `tag "${box.label}" text is squeezed to ${box.width}px (scroll ${box.scrollWidth}, client ${box.clientWidth})`,
    ).toBe(true);
  }
}

/** Every visible control in `controls` must use the same ladder step. */
export async function expectControlHeights(
  controls: Locator,
  expected: number,
  options: { tolerance?: number; allowEmpty?: boolean } = {},
): Promise<void> {
  const tolerance = options.tolerance ?? 0.5;
  const count = await controls.count();
  const heights: number[] = [];
  for (let index = 0; index < count; index += 1) {
    const box = await controls.nth(index).boundingBox();
    if (box && box.height > 1) heights.push(box.height);
  }
  if (!options.allowEmpty) {
    expect(heights.length, "expected at least one visible control").toBeGreaterThan(0);
  }
  for (const height of heights) {
    expect(
      Math.abs(height - expected),
      `control height ${height.toFixed(1)}px must equal ${expected}px (one ladder step per row)`,
    ).toBeLessThanOrEqual(tolerance);
  }
}

/** Within one toolbar: equal heights and centre lines within `tolerance` px. */
export async function expectRowsAligned(
  page: Page,
  options: RowsAlignedOptions = {},
): Promise<void> {
  const rowSelector = options.rowSelector ?? "[data-gv-toolbar]";
  const tolerance = options.tolerance ?? 1;
  const result = await page.evaluate(
    ({ rowSelector, tolerance }) => {
      const visible = (el: Element): boolean => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return (
          rect.width > 1 &&
          rect.height > 1 &&
          style.visibility !== "hidden" &&
          style.display !== "none" &&
          Number(style.opacity) !== 0
        );
      };
      const rows = [...document.querySelectorAll(rowSelector)];
      const violations: Array<Record<string, unknown>> = [];
      for (const row of rows) {
        const controls = [
          ...row.querySelectorAll(
            '.segmented, button:not([data-segmented-value]), input:not([type="hidden"]), select, textarea, [role="button"], [role="switch"], [data-gv-control]',
          ),
        ]
          .filter(visible)
          .map((el) => {
            const rect = el.getBoundingClientRect();
            return {
              height: Math.round(rect.height * 10) / 10,
              center: Math.round((rect.top + rect.height / 2) * 10) / 10,
              label: el.getAttribute("aria-label") ?? el.tagName.toLowerCase(),
            };
          });
        if (controls.length < 2) continue;
        const heights = controls.map((control) => control.height);
        const centers = controls.map((control) => control.center);
        const heightSpread = Math.max(...heights) - Math.min(...heights);
        const centerSpread = Math.max(...centers) - Math.min(...centers);
        if (heightSpread > tolerance || centerSpread > tolerance) {
          violations.push({
            heights: [...new Set(heights)],
            heightSpread,
            centerSpread,
            controls: controls.slice(0, 8).map((control) => control.label),
          });
        }
      }
      return { rows: rows.length, violations };
    },
    { rowSelector, tolerance },
  );

  if (options.requireRows) {
    expect(result.rows, `no ${rowSelector} row found`).toBeGreaterThan(0);
  }
  expect(result.violations, `toolbar rows must be equal-height and centre-aligned`).toEqual([]);
}

/** Document must not scroll horizontally at the current viewport. */
export async function expectNoHorizontalOverflow(page: Page, tolerance = 1): Promise<void> {
  const result = await page.evaluate((limit) => {
    const width = document.documentElement.scrollWidth;
    const viewport = window.innerWidth;
    const offenders = [...document.querySelectorAll("body *")]
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.right > viewport + limit && rect.width < viewport * 3;
      })
      .slice(0, 8)
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return `${el.tagName.toLowerCase()}.${[...el.classList].slice(0, 2).join(".")}@${Math.round(rect.right)}`;
      });
    return { width, viewport, offenders };
  }, tolerance);

  expect(
    result.width,
    `horizontal overflow: scrollWidth ${result.width} > viewport ${result.viewport}; ${result.offenders.join(", ")}`,
  ).toBeLessThanOrEqual(result.viewport + tolerance);
}

/**
 * Effective hit area check for controls whose *visual* box is smaller than
 * `min` (e.g. a 40px Material 3 icon button): probe points just inside the
 * required radius around the centre and require the topmost hit at every point
 * to be the control itself. That proves a pseudo-element / padding expansion
 * exists, and that no neighbouring control covers it.
 */
export async function expectHitTargets(
  controls: Locator,
  min = 44,
  options: { tolerance?: number } = {},
): Promise<void> {
  const tolerance = options.tolerance ?? 0.5;
  // Just inside the required edge, so a box of exactly `min` passes.
  const reach = Math.max(min / 2 - tolerance, 0);
  const failures = await controls.evaluateAll(
    (nodes, { reach }) => {
      const out: string[] = [];
      const owns = (el: Element, hit: Element | null): boolean =>
        hit !== null && (hit === el || el.contains(hit));
      for (const el of nodes) {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (rect.width < 1 || rect.height < 1) continue;
        if (style.visibility === "hidden" || style.display === "none") continue;
        if (Number(style.opacity) === 0) continue;
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const probes: Array<[string, number, number]> = [
          ["center", cx, cy],
          ["top", cx, cy - reach],
          ["bottom", cx, cy + reach],
          ["left", cx - reach, cy],
          ["right", cx + reach, cy],
        ];
        const missed = probes
          .filter(([, x, y]) => !owns(el, document.elementFromPoint(x, y)))
          .map(([direction]) => direction);
        if (missed.length) {
          const label = el.getAttribute("aria-label") ?? el.tagName.toLowerCase();
          out.push(
            `${label} (${Math.round(rect.width)}x${Math.round(rect.height)}): hit area misses ${missed.join("/")}`,
          );
        }
      }
      return out.slice(0, 12);
    },
    { reach },
  );
  expect(
    failures,
    `hit areas must reach >= ${min}x${min}px and must not be covered by a neighbour`,
  ).toEqual([]);
}

/** Every visible hit area must be at least `min` x `min` CSS px. */
export async function expectTouchTargets(
  page: Page,
  options: TouchTargetOptions = {},
): Promise<void> {
  const min = options.min ?? 44;
  const selector =
    options.selector ??
    'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="switch"]';
  const small = await page.evaluate(
    ({ selector, min }) => {
      const out: string[] = [];
      for (const el of document.querySelectorAll(selector)) {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (rect.width < 1 || rect.height < 1) continue;
        if (style.visibility === "hidden" || style.display === "none") continue;
        if (Number(style.opacity) === 0) continue;
        if (rect.width + 0.5 < min || rect.height + 0.5 < min) {
          const label =
            el.getAttribute("aria-label") ??
            (el.textContent ?? "").trim().slice(0, 24) ??
            el.tagName.toLowerCase();
          out.push(`${el.tagName.toLowerCase()}(${Math.round(rect.width)}x${Math.round(rect.height)}): ${label}`);
        }
      }
      return out.slice(0, 12);
    },
    { selector, min },
  );
  expect(small, `touch targets must be >= ${min}x${min}px`).toEqual([]);
}

/**
 * Four screenshots per page: dark/light x 1280/390. Theme is applied through
 * both `prefers-color-scheme` and the persisted `gv_theme` key so the capture
 * matches how users actually resolve the theme.
 */
export async function shotMatrix(
  page: Page,
  name: string,
  options: ShotMatrixOptions = {},
): Promise<ShotMatrixResult> {
  const dir = options.dir ?? SHOT_DIR;
  mkdirSync(dir, { recursive: true });
  const target = options.url ?? page.url();
  const initialViewport = page.viewportSize() ?? { width: 1280, height: 900 };
  const initialTheme = await page.evaluate(() => localStorage.getItem("gv_theme")).catch(() => null);

  const variants = [
    { theme: "dark", width: 1280, height: 900 },
    { theme: "light", width: 1280, height: 900 },
    { theme: "dark", width: 390, height: 844 },
    { theme: "light", width: 390, height: 844 },
  ] as const;

  const files: string[] = [];
  for (const variant of variants) {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.emulateMedia({ colorScheme: variant.theme });
    await page.evaluate((theme) => localStorage.setItem("gv_theme", theme), variant.theme);
    // A hash-only goto does not re-run app boot, and `reload()` can abort while
    // a router guard replaces the hash route. A unique query parameter forces
    // a fresh document (the persisted theme applies) without racing the guard.
    shotSeq += 1;
    await page.goto(withShotBuster(target, `${variant.theme}-${variant.width}-${shotSeq}`));
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(150);
    const file = join(dir, `${name}-${variant.theme}-${variant.width}.png`);
    await page.screenshot({ path: file, fullPage: options.fullPage ?? false });
    files.push(file);
  }

  await page.setViewportSize(initialViewport);
  await page.emulateMedia({ colorScheme: null });
  if (initialTheme) {
    await page.evaluate((theme) => localStorage.setItem("gv_theme", theme), initialTheme).catch(() => {});
  }
  return { dir, files };
}

