#!/usr/bin/env node
/**
 * Production bundle guard (CSP: script-src 'self').
 *
 *   node scripts/check-dist.mjs
 *
 * Fails when dist/:
 *   - is missing or has no index.html;
 *   - contains an inline <script> (or a script/link pointing at another origin);
 *   - contains `eval(` / `new Function(`;
 *   - contains a connection target (fetch/WebSocket/EventSource/XHR/import)
 *     pointing at an absolute external URL.
 *
 * Exit 0 = clean, 1 = violation.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(HERE, "..");
const DIST = join(PROJECT_ROOT, "dist");

const errors = [];
const notes = [];

if (!existsSync(join(DIST, "index.html"))) {
  console.error(`[dist] missing ${join(DIST, "index.html")} — run npm run build first`);
  process.exit(1);
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

const files = walk(DIST);
const htmlFiles = files.filter((file) => file.endsWith(".html"));
const scriptFiles = files.filter((file) => /\.(?:js|mjs)$/.test(file));

function rel(file) {
  return relative(DIST, file).split("\\").join("/");
}

/* ------------------------------------------------------------------- html */

for (const file of htmlFiles) {
  const html = readFileSync(file, "utf8");
  const where = rel(file);

  const scriptTags = html.match(/<script\b[^>]*>/gi) ?? [];
  for (const tag of scriptTags) {
    if (!/\bsrc\s*=/i.test(tag)) {
      errors.push(`${where}: inline <script> is forbidden by CSP (use a built module)`);
      continue;
    }
    if (/\bsrc\s*=\s*["'](?:https?:)?\/\//i.test(tag)) {
      errors.push(`${where}: external script source is forbidden: ${tag.slice(0, 120)}`);
    }
  }

  if (/\b(?:href|src)\s*=\s*["'](?:https?:)?\/\//i.test(html)) {
    errors.push(`${where}: external href/src reference is forbidden`);
  }
  if (/javascript:/i.test(html)) {
    errors.push(`${where}: javascript: URL is forbidden`);
  }
}

/* -------------------------------------------------------------- js bundles */

const EVAL_RE = /\beval\s*\(/;
const NEW_FUNCTION_RE = /\bnew\s+Function\s*\(/;
const EXTERNAL_CONNECTION_RE =
  /(?:fetch|WebSocket|EventSource|import)\s*\(\s*["'`](?:https?:)?\/\//;
const XHR_EXTERNAL_RE = /\.open\s*\(\s*["'][A-Z]+["']\s*,\s*["'`](?:https?:)?\/\//;

let scanned = 0;
for (const file of [...scriptFiles, ...files.filter((f) => f.endsWith(".mjs"))]) {
  if (!existsSync(file) || !statSync(file).isFile()) continue;
  const source = readFileSync(file, "utf8");
  scanned += 1;
  const where = rel(file);
  if (EVAL_RE.test(source)) errors.push(`${where}: eval() detected`);
  if (NEW_FUNCTION_RE.test(source)) errors.push(`${where}: new Function() detected`);
  if (EXTERNAL_CONNECTION_RE.test(source)) {
    errors.push(`${where}: connection to an external origin detected`);
  }
  if (XHR_EXTERNAL_RE.test(source)) {
    errors.push(`${where}: XMLHttpRequest to an external origin detected`);
  }
}

/* ---------------------------------------------------------------- summary */

notes.push(`html: ${htmlFiles.length} file(s), js: ${scanned} bundle(s), total files: ${files.length}`);
for (const note of notes) console.log(`[dist] ${note}`);

if (errors.length) {
  console.error(`\n[dist] ${errors.length} violation(s):`);
  for (const error of errors) console.error(`  - ${error}`);
  process.exit(1);
}

console.log("[dist] OK (no inline script, no eval/new Function, no external connections)");
