#!/usr/bin/env node
/**
 * GalleryVault design guard.
 *
 *   node scripts/check-design.mjs --tokens-only   # required tokens + contrast
 *   node scripts/check-design.mjs                 # tokens + src scan, strict
 *   node scripts/check-design.mjs --strict        # explicit alias (compatibility)
 *
 * Dependency-free. Exit 0 = clean, 1 = violations.
 *
 * Token mode:
 *   - every global token is defined in :root;
 *   - every themed token is defined in both dark and light role blocks;
 *   - the duplicated light blocks (data-theme and prefers-color-scheme) agree;
 *   - every contrast pair listed in tokens.required.json meets its ratio.
 *
 * Scan mode (src/**\/*.{vue,css,ts}, tokens.css excluded):
 *   - no raw color literals (#hex / rgb() / hsl());
 *   - no literal font-size values;
 *   - no non-token border-radius values.
 *
 * Polish rules (files on the polish surface, i.e. src/views/** and
 * src/components/{actions,system,gallery}/**, plus AppShell / ThemeToggle /
 * LangToggle):
 *   - no Unicode symbol-range characters used as icons (U+00D7, arrows,
 *     misc technical, geometric shapes, dingbats, misc symbols and arrows);
 *     "·" is whitelisted as a text separator;
 *   - no native <button> / <input> / <select> / <textarea> in templates;
 *   - `~icons/` imports only from src/components/icons/.
 * A file whose first lines contain `<!-- gv-polish:pending -->` is still exempt
 * from the glyph / native-control rules, kept for future page-by-page work, but
 * the guard now fails whenever any marker remains. `--strict` is a no-op alias
 * kept so existing CI invocations keep working.
 */

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(HERE, "..");
const TOKENS_PATH = join(PROJECT_ROOT, "src/styles/tokens.css");
const REQUIRED_PATH = join(PROJECT_ROOT, "docs/design/tokens.required.json");
const SRC_ROOT = join(PROJECT_ROOT, "src");

const argv = process.argv.slice(2);
if (argv.includes("--help") || argv.includes("-h")) {
  console.log(`Usage:
  node scripts/check-design.mjs --tokens-only
  node scripts/check-design.mjs
  node scripts/check-design.mjs --strict

--tokens-only  validate tokens.required.json against tokens.css
default        also scan src/**/*.{vue,css,ts} for raw design literals,
               glyph icons and native form controls; fails if any
               gv-polish:pending marker remains
--strict       compatibility alias (default is already strict)`);
  process.exit(0);
}
const tokensOnly = argv.includes("--tokens-only");
// Marker removals are complete; the guard is strict by default. `--strict` is
// accepted as a compatibility alias so existing gate commands keep working.
const strict = true;
const errors = [];
const notes = [];
let pendingFiles = 0;

/* ------------------------------------------------------------------ CSS parse */

function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
}

function parseBlocks(css, stack = []) {
  const blocks = [];
  let buf = "";
  let i = 0;
  while (i < css.length) {
    const ch = css[i];
    if (ch === "{") {
      const selector = buf.trim();
      let depth = 1;
      let j = i + 1;
      while (j < css.length && depth > 0) {
        if (css[j] === "{") depth += 1;
        else if (css[j] === "}") depth -= 1;
        j += 1;
      }
      const body = css.slice(i + 1, j - 1);
      const nextStack = [...stack, selector];
      blocks.push({ selector, stack: nextStack, body });
      if (selector.startsWith("@media") || selector.startsWith("@supports")) {
        blocks.push(...parseBlocks(body, nextStack));
      }
      i = j;
      buf = "";
      continue;
    }
    if (ch === "}") {
      i += 1;
      buf = "";
      continue;
    }
    buf += ch;
    i += 1;
  }
  return blocks;
}

function classifyTheme(stack) {
  const s = stack.join(" ").toLowerCase();
  if (/prefers-color-scheme\s*:\s*light/.test(s)) return "light";
  if (/prefers-color-scheme\s*:\s*dark/.test(s)) return "dark";
  if (/data-theme\s*=\s*["']?light/.test(s)) return "light";
  if (/data-theme\s*=\s*["']?dark/.test(s)) return "dark";
  return "global";
}

function parseDeclarations(body) {
  const out = new Map();
  for (const part of body.split(";")) {
    const idx = part.indexOf(":");
    if (idx < 0) continue;
    const name = part.slice(0, idx).trim();
    if (!name.startsWith("--gv-")) continue;
    out.set(name, part.slice(idx + 1).trim());
  }
  return out;
}

/* -------------------------------------------------------------- color / wcag */

function parseFile(file, label) {
  let css;
  try {
    css = readFileSync(file, "utf8");
  } catch (err) {
    errors.push(`${label}: cannot read ${file} (${err.message})`);
    return;
  }
  const maps = { global: new Map(), dark: new Map(), light: new Map() };
  for (const block of parseBlocks(stripComments(css))) {
    if (block.selector.startsWith("@")) continue;
    if (block.body.includes("{")) continue;
    const theme = classifyTheme(block.stack);
    // An @media override may legally change a global value (e.g. the coarse
    // pointer control ladder). Themed duplicates must still agree in both the
    // data-theme and prefers-color-scheme copies.
    const isOverride = block.stack.some((entry) => /^@(media|supports)/.test(entry));
    for (const [name, value] of parseDeclarations(block.body)) {
      const prev = maps[theme].get(name);
      if ((!isOverride || theme !== "global") && prev !== undefined && prev !== value) {
        errors.push(
          `${label}: ${name} defined twice in ${theme} theme with different values: "${prev}" vs "${value}"`,
        );
      }
      maps[theme].set(name, value);
    }
  }
  return maps;
}

function resolveToken(name, maps, theme, seen = new Set()) {
  if (seen.has(name)) return null;
  seen.add(name);
  const raw = maps[theme]?.get(name) ?? maps.global.get(name);
  if (raw === undefined) return null;
  const value = raw.trim();
  const varMatch = value.match(/^var\(\s*(--[\w-]+)\s*(?:,\s*([\s\S]+))?\)$/);
  if (varMatch) {
    const inner = resolveToken(varMatch[1], maps, theme, seen);
    if (inner !== null) return inner;
    return varMatch[2] ? varMatch[2].trim() : null;
  }
  return value;
}

function parseColor(value) {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  if (v === "transparent") return { r: 0, g: 0, b: 0, a: 0 };
  if (v === "black") return { r: 0, g: 0, b: 0, a: 1 };
  if (v === "white") return { r: 255, g: 255, b: 255, a: 1 };
  if (v.startsWith("#")) {
    let hex = v.slice(1);
    if (![3, 4, 6, 8].includes(hex.length) || !/^[0-9a-f]+$/.test(hex)) return null;
    if (hex.length === 3 || hex.length === 4) {
      hex = hex
        .split("")
        .map((c) => c + c)
        .join("");
    }
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    const a = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1;
    return { r, g, b, a };
  }
  const m = v.match(
    /^rgba?\(\s*([0-9.]+%?)\s*[, ]\s*([0-9.]+%?)\s*[, ]\s*([0-9.]+%?)\s*(?:[,/]\s*([0-9.]+%?)\s*)?\)$/,
  );
  if (!m) return null;
  const channel = (s) =>
    s.endsWith("%") ? (parseFloat(s) / 100) * 255 : parseFloat(s);
  let a = 1;
  if (m[4] !== undefined) a = m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
  return { r: channel(m[1]), g: channel(m[2]), b: channel(m[3]), a };
}

function composite(fg, bg) {
  if (fg.a >= 1) return fg;
  return {
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  };
}

function luminance({ r, g, b }) {
  const lin = (c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrastRatio(fg, bg) {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const hi = Math.max(l1, l2);
  const lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}

/* ------------------------------------------------------------------ token mode */

function checkTokens() {
  let required;
  try {
    required = JSON.parse(readFileSync(REQUIRED_PATH, "utf8"));
  } catch (err) {
    console.error(`check-design: cannot read ${REQUIRED_PATH}: ${err.message}`);
    process.exit(1);
  }

  const maps = parseFile(TOKENS_PATH, relative(PROJECT_ROOT, TOKENS_PATH) || "tokens.css");
  if (!maps) process.exit(1);

  const global = required.required?.global ?? [];
  const themed = required.required?.themed ?? [];
  const themeNames = required.themes ?? ["dark", "light"];

  for (const name of global) {
    if (!maps.global.has(name)) errors.push(`missing global token ${name} (expected in :root)`);
  }
  for (const theme of themeNames) {
    const map = maps[theme];
    if (!map) {
      errors.push(`missing theme block for "${theme}"`);
      continue;
    }
    for (const name of themed) {
      if (!map.has(name)) errors.push(`missing themed token ${name} in ${theme} theme`);
    }
  }

  if (!errors.length) {
    let checked = 0;
    for (const pair of required.contrast ?? []) {
      for (const theme of themeNames) {
        const fgRaw = resolveToken(pair.fg, maps, theme);
        const bgRaw = resolveToken(pair.bg, maps, theme);
        if (fgRaw === null || bgRaw === null) {
          errors.push(
            `contrast pair ${pair.fg} / ${pair.bg}: token not resolvable in ${theme} theme`,
          );
          continue;
        }
        const fg0 = parseColor(fgRaw);
        const bg0 = parseColor(bgRaw);
        if (!fg0 || !bg0) {
          errors.push(
            `contrast pair ${pair.fg} / ${pair.bg}: unsupported color value "${fgRaw}" / "${bgRaw}"`,
          );
          continue;
        }
        const bg = composite(bg0, { r: 255, g: 255, b: 255, a: 1 });
        const fg = composite(fg0, bg);
        const ratio = contrastRatio(fg, bg);
        const min = pair.min ?? 4.5;
        checked += 1;
        if (ratio < min) {
          errors.push(
            `contrast ${pair.fg} on ${pair.bg} (${theme}) = ${ratio.toFixed(2)}:1 < ${min}:1`,
          );
        }
      }
    }
    notes.push(
      `tokens: ${global.length} global + ${themed.length} themed x ${themeNames.length} themes, ${checked} contrast pairs`,
    );
  }
}

/* ------------------------------------------------------------------- src scan */

const COLOR_RE = /(?:^|[^\w-])(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()/;
const CSS_WIDE = /^(inherit|initial|unset|revert|revert-layer)$/i;

/* ----------------------------------------------------------- polish surface */

const PENDING_MARKER = "gv-polish:pending";
const PENDING_FILES = [
  "src/components/AppShell.vue",
  "src/components/ThemeToggle.vue",
  "src/components/LangToggle.vue",
];
const POLISH_DIRS = [
  "src/views/",
  "src/components/actions/",
  "src/components/system/",
  "src/components/gallery/",
];

/** Where the polish rules apply (the surface being converted page by page). */
function isPolishSurface(rel) {
  return PENDING_FILES.includes(rel) || POLISH_DIRS.some((dir) => rel.startsWith(dir));
}

/** The marker lives in one of the first five lines of the file. */
function hasPendingMarker(source) {
  return source
    .split(/\r?\n/, 5)
    .some((line) => line.includes(PENDING_MARKER));
}

/**
 * Character-icon detector. Ranges follow the audit's Unicode scan:
 * multiplication sign, arrows, misc technical, geometric shapes, dingbats,
 * misc symbols and arrows, plus the three technical/math glyphs that the old
 * templates used (≡ ≣ ⧉). `·` stays legal as a text separator.
 */
const GLYPH_RE =
  /[\u00D7\u2039\u203A\u2190-\u21FF\u2300-\u23FF\u25A0-\u27BF\u2900-\u2BFF\u2261\u2263\u29C9\u{1F300}-\u{1FAFF}]/u;
const GLYPH_SEPARATORS = /[·•–—…]/g;

function hasGlyphIcon(text) {
  return GLYPH_RE.test(text.replace(GLYPH_SEPARATORS, ""));
}

/** Remove comments before reading .ts string literals (doc arrows are fine). */
function stripTsComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
    .split(/\r?\n/)
    .map((line) => (line.trimStart().startsWith("//") ? " ".repeat(line.length) : line))
    .join("\n");
}

function scanGlyphs(rel, source, isTypeScript) {
  if (!isTypeScript) {
    source.split(/\r?\n/).forEach((line, index) => {
      const trimmed = line.trimStart();
      if (trimmed.startsWith("//") || trimmed.startsWith("/*") || trimmed.startsWith("*")) return;
      if (trimmed.startsWith("<!--")) return;
      if (hasGlyphIcon(line)) {
        errors.push(
          `${rel}:${index + 1}: character icon "${line.trim().slice(0, 40)}" — use <Icon name="…"> from src/components/icons/`,
        );
      }
    });
    return;
  }

  const stripped = stripTsComments(source);
  const literal = /(['"`])((?:\\.|(?!\1)[^\\])*)\1/g;
  let match;
  while ((match = literal.exec(stripped))) {
    const value = match[2];
    if (value.length > 400 || value.includes("\n")) continue;
    if (!hasGlyphIcon(value)) continue;
    const line = stripped.slice(0, match.index).split("\n").length;
    errors.push(
      `${rel}:${line}: character icon in string "${value.slice(0, 40)}" — use an Icon name, not a Unicode glyph`,
    );
  }
}

function scanNativeControls(rel, source) {
  const start = source.indexOf("<template");
  const end = source.lastIndexOf("</template>");
  if (start < 0 || end <= start) return;
  const body = source
    .slice(start, end)
    .replace(/<!--[\s\S]*?-->/g, (match) => match.replace(/[^\n]/g, " "));
  body.split(/\r?\n/).forEach((line, index) => {
    const trimmed = line.trimStart();
    if (trimmed.startsWith("//") || trimmed.startsWith("/*") || trimmed.startsWith("*")) return;
    const control = line.match(/<(button|input|select|textarea)(?=[\s/>])/);
    if (!control) return;
    const lineNumber = source.slice(0, start).split("\n").length + index;
    errors.push(
      `${rel}:${lineNumber}: native <${control[1]}> in template — use the shared control from src/components/ui/`,
    );
  });
}

function walk(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, out);
    } else if (entry.isFile() && /\.(vue|css|ts)$/.test(entry.name)) {
      out.push(full);
    }
  }
}

function scanFile(file) {
  const rel = relative(PROJECT_ROOT, file).split(sep).join("/");
  if (rel.endsWith("src/styles/tokens.css")) return;
  const source = readFileSync(file, "utf8");
  const lines = source.split(/\r?\n/);
  lines.forEach((line, index) => {
    const where = `${rel}:${index + 1}`;
    const trimmed = line.trim();
    const inComment =
      trimmed.startsWith("//") ||
      trimmed.startsWith("/*") ||
      trimmed.startsWith("*") ||
      trimmed.startsWith("<!--");
    if (inComment) return;

    const color = line.match(COLOR_RE);
    if (color) {
      const idx = color.index + color[0].length - color[1].length;
      const before = line.slice(0, idx);
      const isUrlFragment = /url\(\s*$/i.test(before);
      if (!isUrlFragment) {
        errors.push(`${where}: raw color literal "${color[1]}" — use a --gv-color-* or --gv-cat-* token`);
      }
    }

    const fontSize = line.match(/font-size\s*:\s*([^;]+)/i);
    if (fontSize) {
      const value = fontSize[1].trim();
      const ok = CSS_WIDE.test(value) || /^var\(\s*--gv-type-[\w-]+\s*\)$/.test(value);
      if (!ok) {
        errors.push(`${where}: literal font-size "${value}" — use a --gv-type-*-size token`);
      }
    }

    const radius = line.match(/border-radius\s*:\s*([^;]+)/i);
    if (radius) {
      const parts = radius[1].split(/[\s/]+/).filter(Boolean);
      for (const part of parts) {
        if (part === "0" || CSS_WIDE.test(part)) continue;
        if (/^var\(\s*--gv-radius-[\w-]+\s*\)$/.test(part)) continue;
        errors.push(
          `${where}: non-token border-radius "${radius[1].trim()}" — use --gv-radius-* tokens`,
        );
        break;
      }
    }
  });

  /* ------------------------------------------------- polish rules (opt-out) */

  if (/from\s+["']~icons\/|import\(\s*["']~icons\//.test(source) && !rel.startsWith("src/components/icons/")) {
    errors.push(
      `${rel}: imports from "~icons/" outside src/components/icons/ — register the icon in the registry instead`,
    );
  }

  if (!isPolishSurface(rel)) return;
  if (hasPendingMarker(source)) {
    pendingFiles += 1;
    return;
  }
  scanGlyphs(rel, source, rel.endsWith(".ts"));
  if (rel.endsWith(".vue")) scanNativeControls(rel, source);
}

function scanSrc() {
  if (!existsSync(SRC_ROOT)) {
    notes.push("scan: src/ does not exist yet (fe-scaffold); nothing to scan");
    return;
  }
  const files = [];
  walk(SRC_ROOT, files);
  let scanned = 0;
  for (const file of files) {
    const rel = relative(PROJECT_ROOT, file).split(sep).join("/");
    const abs = file.split(sep).join("/");
    if (abs.endsWith("/src/styles/tokens.css")) continue;
    scanned += 1;
    scanFile(file);
  }
  notes.push(`scan: ${scanned} file(s) under src/ (tokens.css excluded)`);
}

/* ---------------------------------------------------------------------- main */

checkTokens();
if (!tokensOnly) scanSrc();

if (!tokensOnly) {
  notes.push(`polish: ${pendingFiles} file(s) still marked <!-- ${PENDING_MARKER} -->`);
  if (strict && pendingFiles > 0) {
    errors.push(
      `${pendingFiles} file(s) still carry <!-- ${PENDING_MARKER} --> — the design guard requires 0`,
    );
  }
}

for (const note of notes) console.log(`[design] ${note}`);
if (errors.length) {
  console.error(`\n[design] ${errors.length} violation(s):`);
  for (const err of errors) console.error(`  - ${err}`);
  process.exit(1);
}
console.log(`[design] OK${tokensOnly ? " (tokens only)" : ""}`);
