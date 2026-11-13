/* eslint-disable no-restricted-syntax -- the audit route allowlist names the read-only endpoint directly */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "@playwright/test";
import { ensureSession } from "./support";

/**
 * Read-only visual audit capture (`@audit`). Writers do not run this; the
 * tester runs it against the shared test stack after integration:
 *
 *   GV_E2E_BASE=http://127.0.0.1:8200 GV_E2E_PASSWORD=... \
 *     GV_SHOTS=/tmp/opencode/gv-frontend-rewrite/shots/audit npm run e2e:real -- --grep @audit
 *
 * It mirrors `audit/capture.mjs`: one login per run (global setup), every
 * non-GET /api request blocked in the browser (only the read-only
 * `POST /api/tags/search` is allowed through), per-page screenshots and a
 * metrics JSON. No password, cookie or token is printed or persisted outside
 * Playwright's ignored `test-results/` state file.
 */

const BASE = (process.env.GV_E2E_BASE || "http://127.0.0.1:8200").replace(/\/+$/, "");
const SHOT_DIR =
  process.env.GV_SHOTS || "/tmp/opencode/gv-frontend-rewrite/shots/audit";
const METRIC_DIR = join(SHOT_DIR, "metrics");

const VARIANTS = [
  { theme: "dark", width: 1280, height: 900 },
  { theme: "light", width: 1280, height: 900 },
  { theme: "dark", width: 390, height: 844 },
  { theme: "light", width: 390, height: 844 },
] as const;

interface Ids {
  gallery: string | null;
  online: string | null;
  fav: string | null;
}

/** DOM metrics kept intentionally small: enough to reproduce the audit counts. */
function collectMetrics() {
  const visible = (el: Element): boolean => {
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return false;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) {
      return false;
    }
    return rect.bottom > 0 && rect.top < Math.max(window.innerHeight, 4000);
  };
  const controls = [
    ...document.querySelectorAll(
      'button, [role="button"], [role="tab"], [role="switch"], a[class*="btn"], input:not([type="hidden"]), select, textarea',
    ),
  ]
    .filter(visible)
    .map((el) => {
      const rect = el.getBoundingClientRect();
      return {
        tag: el.tagName.toLowerCase(),
        height: Math.round(rect.height * 10) / 10,
        width: Math.round(rect.width),
        label: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 24),
        hasSvg: Boolean(el.querySelector("svg")),
      };
    });

  const heights: Record<string, number> = {};
  for (const control of controls) {
    if (control.tag === "input" || control.tag === "textarea") continue;
    const key = String(control.height);
    heights[key] = (heights[key] ?? 0) + 1;
  }

  const glyphPattern =
    /[\u00D7\u2039\u203A\u2190-\u21FF\u2300-\u23FF\u25A0-\u27BF\u2900-\u2BFF\u2261\u2263\u29C9\u{1F300}-\u{1FAFF}]/u;
  const glyphs: string[] = [];
  for (const el of document.querySelectorAll("body *")) {
    if (!visible(el) || el.children.length > 0) continue;
    const text = (el.textContent ?? "").replace(/[·•–—…]/g, "").trim();
    if (text && glyphPattern.test(text)) glyphs.push(`${el.tagName.toLowerCase()}: ${text.slice(0, 24)}`);
    if (glyphs.length >= 20) break;
  }

  const rows: Array<Record<string, unknown>> = [];
  for (const row of document.querySelectorAll("[data-gv-toolbar], .toolbar, header, form")) {
    const items = [...row.querySelectorAll("button, input, select")].filter(visible);
    if (items.length < 2) continue;
    const rects = items.map((el) => el.getBoundingClientRect());
    const centers = rects.map((rect) => rect.top + rect.height / 2);
    const spread = Math.max(...centers) - Math.min(...centers);
    const heightSpread = Math.max(...rects.map((rect) => rect.height)) - Math.min(...rects.map((rect) => rect.height));
    if (spread > 1 || heightSpread > 1) {
      rows.push({ centerSpread: Math.round(spread * 10) / 10, heightSpread: Math.round(heightSpread * 10) / 10 });
    }
    if (rows.length >= 12) break;
  }

  const documentWidth = document.documentElement.scrollWidth;
  const overflowing = [...document.querySelectorAll("body *")]
    .filter((el) => {
      if (!visible(el)) return false;
      const rect = el.getBoundingClientRect();
      return rect.right > window.innerWidth + 1 && rect.width < window.innerWidth * 3;
    })
    .slice(0, 8)
    .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].slice(0, 2).join(".")}`);

  return {
    url: location.hash,
    document: {
      width: documentWidth,
      height: document.documentElement.scrollHeight,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    },
    counts: {
      controls: controls.length,
      svg: document.querySelectorAll("svg").length,
      glyphs: glyphs.length,
      rows: rows.length,
      smallControls: controls.filter((control) => control.height < 44 || control.width < 44).length,
      brokenImages: [...document.images].filter((image) => image.complete && image.naturalWidth === 0).length,
    },
    heights,
    glyphs,
    rows,
    overflowing,
    controls: controls.slice(0, 120),
  };
}

async function settle(page: import("@playwright/test").Page, ms = 1200): Promise<void> {
  await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(ms);
}

async function firstHref(
  page: import("@playwright/test").Page,
  prefix: string,
  pattern: RegExp,
): Promise<string | null> {
  return page.evaluate(
    ({ prefix, source }) => {
      const re = new RegExp(source);
      const hrefs = [...document.querySelectorAll(`a[href*="${prefix}"]`)]
        .map((anchor) => anchor.getAttribute("href"))
        .filter((href): href is string => Boolean(href));
      return hrefs.find((href) => re.test(href)) ?? null;
    },
    { prefix, source: pattern.source },
  );
}

test.describe("@audit read-only visual audit", () => {
  test.beforeAll(() => {
    mkdirSync(METRIC_DIR, { recursive: true });
  });

  for (const variant of VARIANTS) {
    test(`capture ${variant.theme} ${variant.width}x${variant.height}`, async ({ context, page }) => {
      test.setTimeout(900_000);
      await ensureSession(context);
      await page.setViewportSize({ width: variant.width, height: variant.height });
      await page.emulateMedia({ colorScheme: variant.theme });
      await page.addInitScript(
        (theme) => {
          localStorage.setItem("gv_theme", theme);
          localStorage.setItem("gv_lang", "zh");
        },
        variant.theme,
      );

      // Read-only guard: GET passes, POST /api/tags/search (read-only) passes,
      // every other method is fulfilled locally and recorded.
      const blocked: string[] = [];
      await page.route("**/api/**", async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (request.method() === "GET" || (request.method() === "POST" && path === "/api/tags/search")) {
          await route.continue();
          return;
        }
        blocked.push(`${request.method()} ${path}`);
        await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      });

      const tag = `${variant.theme}-${variant.width}`;
      const ids: Ids = { gallery: null, online: null, fav: null };

      const go = async (hash: string, ms = 1200): Promise<void> => {
        await page.goto(`${BASE}/#${hash}`);
        await settle(page, ms);
      };

      const capture = async (name: string, options: { full?: boolean } = {}): Promise<void> => {
        const file = join(SHOT_DIR, `${name}-${tag}.png`);
        await page.screenshot({ path: file, animations: "disabled" });
        if (options.full && variant.theme === "dark") {
          const height = await page.evaluate(() => document.documentElement.scrollHeight);
          if (height > variant.height + 40) {
            await page
              .screenshot({ path: join(SHOT_DIR, `${name}-${tag}-full.png`), fullPage: true, animations: "disabled" })
              .catch(() => {});
          }
        }
        const metrics = await page.evaluate(collectMetrics).catch((error) => ({ error: String(error) }));
        writeFileSync(
          join(METRIC_DIR, `${name}-${tag}.json`),
          JSON.stringify({ name, variant: tag, ...metrics }, null, 1),
        );
      };

      await page.goto(`${BASE}/`);
      await settle(page);

      await go("/browse");
      await capture("browse", { full: true });

      await go("/library");
      await capture("library", { full: true });
      ids.gallery = await firstHref(page, "#/gallery/", /^#\/gallery\/\d+$/);

      await go("/online", 3500);
      await capture("online-list", { full: true });
      ids.online = await firstHref(page, "#/online/g/", /^#\/online\/g\/\d+\/[0-9a-f]+$/);

      if (ids.gallery) {
        await go(ids.gallery.replace(/^#/, ""));
        await capture("gallery-detail", { full: true });
        const gid = ids.gallery.match(/\d+/)?.[0];
        if (gid) {
          await go(`/reader/${gid}/1`);
          await capture("reader");
          await page.mouse.click(variant.width / 2, variant.height / 2).catch(() => {});
          await page.waitForTimeout(400);
          await capture("reader-bars");
        }
      }

      if (ids.online) {
        const online = ids.online.replace(/^#/, "");
        await go(online, 3500);
        await capture("online-detail", { full: true });
        await go(`${online}/read/1`, 4000);
        await capture("online-reader");
        await page.mouse.click(variant.width / 2, variant.height / 2).catch(() => {});
        await page.waitForTimeout(400);
        await capture("online-reader-bars");
      }

      for (const [name, hash, ms] of [
        ["series", "/series", 1200],
        ["tags", "/tags", 1200],
        ["history", "/history", 1200],
        ["favorites", "/favorites", 1200],
        ["favorites-manage", "/favorites/manage", 2000],
        ["favorites-ignored", "/favorites/ignored", 1200],
        ["downloads", "/downloads", 1200],
        ["updates", "/updates", 1200],
        ["updates-ignored", "/updates/ignored", 1200],
        ["duplicates", "/duplicates", 1200],
        ["duplicates-cross-gid", "/duplicates/cross-gid", 1200],
        ["recycle", "/recycle", 1200],
        ["integrity", "/integrity", 1200],
        ["archive", "/archive", 1200],
        ["logs", "/logs", 1200],
        ["welcome", "/welcome", 1200],
      ] as const) {
        await go(hash, ms);
        if (name === "favorites") ids.fav = await firstHref(page, "#/favorites/", /^#\/favorites\/\d+$/);
        await capture(name, { full: true });
      }

      if (ids.fav) {
        await go(ids.fav.replace(/^#/, ""), 2000);
        await capture("favorites-list", { full: true });
      }

      // Settings index + one capture per group (group list is discovered).
      await go("/settings", 1500);
      await capture("settings-00-index", { full: true });
      const groups = await page.evaluate(() =>
        [...document.querySelectorAll("[data-settings-nav]")].map((el) =>
          el.getAttribute("data-settings-nav"),
        ),
      );
      const uniqueGroups = [...new Set(groups.filter((group): group is string => Boolean(group)))];
      for (const [index, group] of uniqueGroups.entries()) {
        await go("/settings", 800);
        const nav = page.locator(`[data-settings-nav="${group}"]`).first();
        if (await nav.count()) {
          await nav.click({ timeout: 3000 }).catch(() => {});
          await page.waitForTimeout(600);
        }
        await capture(`settings-${String(index + 1).padStart(2, "0")}-${group}`, { full: true });
      }

      writeFileSync(
        join(METRIC_DIR, `_readonly-${tag}.json`),
        JSON.stringify({ variant: tag, blockedWrites: [...new Set(blocked)] }, null, 1),
      );
    });
  }
});
