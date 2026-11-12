#!/usr/bin/env node
/**
 * Legacy parity guard for the frontend rewrite (fe-scaffold).
 *
 *   node scripts/check-parity.mjs --report   # totals, coverage, self-check (exit 0)
 *   node scripts/check-parity.mjs --views    # per-view coverage table
 *   node scripts/check-parity.mjs --strict   # exit 1 when any endpoint is uncovered
 *
 * The snapshot (`parity/legacy-endpoints.json`) is the source of truth for what
 * the old frontend called. To stop the snapshot from silently missing calls,
 * this script re-greps `frontend/assets` on every run and fails when a literal
 * endpoint found in source is absent from the snapshot
 * ("grep 命中但未收录 = 0").
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(HERE, "..");
const LEGACY_ROOT = resolve(PROJECT_ROOT, "../assets");
const SNAPSHOT = join(PROJECT_ROOT, "parity/legacy-endpoints.json");
const CHECKLIST = join(PROJECT_ROOT, "parity/checklist.json");
const WAIVERS = join(PROJECT_ROOT, "parity/waivers.json");
const NEW_API_ROOT = join(PROJECT_ROOT, "src/api");
const E2E_REAL_ROOT = join(PROJECT_ROOT, "e2e/real");

/** The only route waiver approved by PLAN §旧版功能对齐清单. */
const PLAN_WAIVER_PATHS = new Set(["/series/{id}"]);

const argv = process.argv.slice(2);
const mode = argv.includes("--strict")
  ? "strict"
  : argv.includes("--views")
    ? "views"
    : "report";

const METHOD_RE = /\b(?:view)?api\(\s*["'](GET|POST|PUT|PATCH|DELETE)["']\s*,\s*(["'`])([\s\S]*?)\2/gi;
const PATH_RE = /(["'`])(\/api\/[^"'`\s]*)\1/g;

const errors = [];

function canonical(path) {
  return path
    .split("?")[0]
    .replace(/\$\{[^}]*\}/g, "{id}")
    .replace(/\{[A-Za-z0-9_]+\}/g, "{id}")
    .replace(/\/\d+(?=\/|$)/g, "/{id}")
    .replace(/\/+$/g, "");
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

function walkTs(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walkTs(full, out);
    else if (entry.name.endsWith(".ts")) out.push(full);
  }
  return out;
}

function loadChecklist() {
  const doc = JSON.parse(readFileSync(CHECKLIST, "utf8"));
  const items = Array.isArray(doc) ? doc : doc.items;
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error(`${CHECKLIST}: items[] missing or empty`);
  }
  for (const item of items) {
    if (!item || typeof item.id !== "string" || !/^[A-Z]-\d{2}$/.test(item.id)) {
      throw new Error(`${CHECKLIST}: malformed item ${JSON.stringify(item)}`);
    }
  }
  return items;
}

function loadWaivers() {
  const doc = JSON.parse(readFileSync(WAIVERS, "utf8"));
  return Array.isArray(doc.routes) ? doc.routes : [];
}

/** `test("ID … @parity", …)` titles are the executable checklist. */
function extractParityTitles() {
  const titles = [];
  for (const file of walkTs(E2E_REAL_ROOT)) {
    const source = readFileSync(file, "utf8");
    const TEST_RE = /\btest(?:\.\w+)?\(\s*(["'`])([^"'`]*)\1/g;
    let match;
    while ((match = TEST_RE.exec(source))) titles.push(match[2].trim());
  }
  return titles;
}

function startsWithId(title, id) {
  return new RegExp(`^${id}(?:\\s|:|：|$)`).test(title);
}

function extractLegacy() {
  const known = new Map(); // "METHOD path" -> Set(files)
  const paths = new Map(); // path -> Set(methods)
  const addPath = (path, method) => {
    if (!paths.has(path)) paths.set(path, new Set());
    if (method) paths.get(path).add(method);
  };
  // The legacy frontend (frontend/assets) is deleted by the cutover batch, so
  // there is nothing left to re-grep; the snapshot stays authoritative.
  if (!existsSync(LEGACY_ROOT)) return { known, paths };
  for (const file of walk(LEGACY_ROOT)) {
    const source = readFileSync(file, "utf8");
    const rel = relative(LEGACY_ROOT, file).split(sep).join("/");
    let match;
    while ((match = METHOD_RE.exec(source))) {
      if (!match[3].startsWith("/api/")) continue;
      const closesAt = METHOD_RE.lastIndex;
      const tail = source.slice(closesAt, closesAt + 8);
      const concatenated = match[3].endsWith("/") && /^\s*\+/.test(tail);
      const path = canonical(concatenated ? `${match[3]}{id}` : match[3]);
      const method = match[1].toUpperCase();
      const key = `${method} ${path}`;
      if (!known.has(key)) known.set(key, new Set());
      known.get(key).add(rel);
      addPath(path, method);
    }
    while ((match = PATH_RE.exec(source))) {
      const path = canonical(match[2]);
      addPath(path, null);
    }
  }
  return { known, paths };
}

function loadSnapshot() {
  const doc = JSON.parse(readFileSync(SNAPSHOT, "utf8"));
  if (!Array.isArray(doc.endpoints)) throw new Error(`${SNAPSHOT}: endpoints[] missing`);
  return doc.endpoints;
}

function extractNew() {
  const signatures = new Set();
  const constants = new Map(); // exported constant name -> signature
  const wrappers = new Map(); // exported function name -> Set(signature)
  let files = [];
  try {
    files = readdirSync(NEW_API_ROOT)
      .filter((name) => name.endsWith(".ts") && !name.endsWith(".test.ts"))
      .map((name) => join(NEW_API_ROOT, name));
  } catch {
    return { signatures, constants, wrappers };
  }
  const EP_RE =
    /export\s+const\s+(\w+)\s*=\s*ep\(\s*["'](GET|POST|PUT|PATCH|DELETE)["']\s*,\s*["']([^"']+)["']/g;
  const FN_RE = /export\s+(?:async\s+)?function\s+(\w+)\s*\(/g;
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    let match;
    while ((match = EP_RE.exec(source))) {
      if (!match[3].startsWith("/api/")) continue;
      const signature = `${match[2].toUpperCase()} ${canonical(match[3])}`;
      signatures.add(signature);
      constants.set(match[1], signature);
    }
    while ((match = FN_RE.exec(source))) {
      const start = match.index;
      const next = source.indexOf("\nexport ", start + 1);
      const body = source.slice(start, next === -1 ? source.length : next);
      const used = new Set();
      for (const [name, signature] of constants) {
        if (new RegExp(`\\b${name}\\b`).test(body)) used.add(signature);
      }
      if (used.size) wrappers.set(match[1], used);
    }
  }
  return { signatures, constants, wrappers };
}

/** Endpoints count as covered only when a non-API source file imports the
 * endpoint constant or an API wrapper that uses it. Merely declaring the
 * catalogue ahead of implementation must not make `--strict` vacuous. */
function extractConsumed(constants, wrappers) {
  const consumed = new Set();
  const root = join(PROJECT_ROOT, "src");
  const files = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (full === NEW_API_ROOT) continue;
        walk(full);
      } else if (/\.(?:ts|vue)$/.test(entry.name) && !entry.name.endsWith(".test.ts")) {
        files.push(full);
      }
    }
  };
  try {
    walk(root);
  } catch {
    return consumed;
  }
  const IMPORT_RE = /import\s*\{([^}]*)\}\s*from\s*["'][^"']+["']/g;
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    let match;
    while ((match = IMPORT_RE.exec(source))) {
      for (const part of match[1].split(",")) {
        const name = part.trim().split(/\s+as\s+/)[0]?.trim();
        if (!name) continue;
        const signature = constants.get(name);
        if (signature) consumed.add(signature);
        for (const wrapped of wrappers.get(name) ?? []) consumed.add(wrapped);
      }
    }
  }
  return consumed;
}

/* --------------------------------------------------------------- run checks */

const snapshot = loadSnapshot();
const snapshotSignatures = new Set();
const snapshotPaths = new Map(); // path -> Set(views)

for (const entry of snapshot) {
  if (!entry || typeof entry.method !== "string" || typeof entry.path !== "string") {
    errors.push(`snapshot entry is malformed: ${JSON.stringify(entry)}`);
    continue;
  }
  const method = entry.method.toUpperCase();
  const path = canonical(entry.path);
  snapshotSignatures.add(`${method} ${path}`);
  if (!snapshotPaths.has(path)) snapshotPaths.set(path, new Set());
  for (const view of entry.views ?? ["unknown"]) snapshotPaths.get(path).add(view);
}

const legacy = extractLegacy();
let grepMissing = 0;
for (const [path, methods] of legacy.paths) {
  if (!snapshotPaths.has(path)) {
    errors.push(`grep hit but not recorded: ${path}`);
    grepMissing += 1;
    continue;
  }
  for (const method of methods) {
    if (!snapshotSignatures.has(`${method} ${path}`)) {
      errors.push(`grep hit but not recorded: ${method} ${path}`);
      grepMissing += 1;
    }
  }
}

const { signatures: newSignatures, constants, wrappers } = extractNew();
const consumed = extractConsumed(constants, wrappers);

/**
 * Legacy endpoints that the product UI no longer calls (for example the old
 * slideshow `/meta` probe) may still be covered by an explicit real parity
 * test. Only `@parity` files count, and the endpoint must be imported from the
 * API catalogue, so this cannot be satisfied by a comment or a bare string.
 */
function extractE2EConsumed() {
  const covered = new Set();
  let files = [];
  try {
    files = walkTs(E2E_REAL_ROOT);
  } catch {
    return covered;
  }
  const IMPORT_RE = /import\s*\{([^}]*)\}\s*from\s*["'][^"']+["']/g;
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    if (!source.includes("@parity")) continue;
    let match;
    while ((match = IMPORT_RE.exec(source))) {
      for (const part of match[1].split(",")) {
        const name = part.trim().split(/\s+as\s+/)[0]?.trim();
        if (!name) continue;
        const signature = constants.get(name);
        if (signature) covered.add(signature);
        for (const wrapped of wrappers.get(name) ?? []) covered.add(wrapped);
      }
    }
  }
  return covered;
}

const e2eConsumed = extractE2EConsumed();
const coveredSignatures = new Set([...consumed, ...e2eConsumed]);
const uncovered = [...snapshotSignatures].filter((sig) => !coveredSignatures.has(sig));

const viewNames = new Set();
for (const views of snapshotPaths.values()) for (const view of views) viewNames.add(view);

let checklist = [];
let parityTitles = [];
try {
  checklist = loadChecklist();
  parityTitles = extractParityTitles();
} catch (error) {
  errors.push(error instanceof Error ? error.message : String(error));
}

const duplicateIds = checklist
  .map((item) => item.id)
  .filter((id, index, all) => all.indexOf(id) !== index);
if (duplicateIds.length) {
  errors.push(`checklist has duplicate IDs: ${[...new Set(duplicateIds)].join(", ")}`);
}

const missingParity = checklist
  .filter(
    (item) =>
      !parityTitles.some(
        (title) => startsWithId(title, item.id) && title.includes("@parity"),
      ),
  )
  .map((item) => `${item.id} (${String(item.title ?? "")})`);
if (missingParity.length) {
  errors.push(
    `checklist IDs without a real @parity E2E case: ${missingParity.join(", ")}`,
  );
}

const unplannedWaivers = loadWaivers()
  .filter((waiver) => !PLAN_WAIVER_PATHS.has(String(waiver?.path ?? "")))
  .map((waiver) => String(waiver?.path ?? "?"));
if (unplannedWaivers.length) {
  errors.push(
    `waivers.json contains route(s) not pre-approved by PLAN: ${unplannedWaivers.join(", ")}`,
  );
}

console.log(`[parity] snapshot: ${snapshot.length} entries / ${snapshotPaths.size} unique paths`);
console.log(`[parity] legacy grep: ${legacy.known.size} method+path signatures`);
console.log(`[parity] new endpoint declarations: ${newSignatures.size}`);
console.log(`[parity] consumed by non-API source: ${consumed.size}`);
console.log(`[parity] consumed via @parity E2E: ${e2eConsumed.size}`);
console.log(`[parity] uncovered old endpoints: ${uncovered.length}`);
console.log(
  `[parity] 自检: grep 命中但未收录 = ${grepMissing} (${legacy.paths.size} paths checked)`,
);
console.log(
  `[parity] checklist: ${checklist.length} IDs / ${parityTitles.filter((title) => title.includes("@parity")).length} @parity cases`,
);

if (mode === "views") {
  const rows = [];
  for (const view of [...viewNames].sort()) {
    const paths = [...snapshotPaths].filter(([, views]) => views.has(view));
    const covered = paths.filter(([path]) =>
      [...snapshotSignatures]
        .filter((sig) => sig.endsWith(` ${path}`))
        .some((sig) => coveredSignatures.has(sig)),
    ).length;
    rows.push({ view, total: paths.length, covered, missing: paths.length - covered });
  }
  console.log("[parity] view                 total  covered  missing");
  for (const row of rows) {
    console.log(
      `[parity] ${row.view.padEnd(20)} ${String(row.total).padStart(5)} ` +
        `${String(row.covered).padStart(8)} ${String(row.missing).padStart(8)}`,
    );
  }
}

if (mode === "report" || mode === "views") {
  if (uncovered.length) {
    const preview = uncovered.slice(0, 20);
    console.log("[parity] expected during Batch 1 (pages not migrated yet):");
    for (const item of preview) console.log(`  - ${item}`);
    if (uncovered.length > preview.length) {
      console.log(`  ... ${uncovered.length - preview.length} more`);
    }
  }
}

if (errors.length) {
  console.error(`[parity] ${errors.length} snapshot error(s):`);
  for (const error of errors.slice(0, 40)) console.error(`  - ${error}`);
  process.exit(1);
}

if (mode === "strict" && uncovered.length) {
  console.error(`[parity] strict: ${uncovered.length} old endpoint(s) still uncovered`);
  process.exit(1);
}

console.log("[parity] OK");
