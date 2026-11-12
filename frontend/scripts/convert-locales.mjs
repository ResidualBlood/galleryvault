#!/usr/bin/env node
/**
 * Convert the legacy locale bundles (frontend/assets/locales/{zh,en}.js) into
 * JSON resources consumed by the new frontend.
 *
 * Why conversion is not a plain JSON.stringify:
 *   - vue-i18n treats "." inside a message key as a path separator, so every
 *     flat legacy key containing a dot is mapped to an underscore key.
 *   - a mapped key must not silently overwrite an existing key; collisions abort
 *     the conversion and must be resolved by hand (README lists the mapping).
 *
 * Usage:
 *   node scripts/convert-locales.mjs            # write src/locales/{zh,en}/legacy.json
 *   node scripts/convert-locales.mjs --check    # verify the files are up to date
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(HERE, "..");
const LEGACY_LOCALES = resolve(PROJECT_ROOT, "../assets/locales");
const OUT_ROOT = join(PROJECT_ROOT, "src/locales");
const LANGS = ["zh", "en"];
const ERROR_EXIT = 1;
const checkOnly = process.argv.includes("--check");

const errors = [];

function loadLegacy(lang) {
  const file = join(LEGACY_LOCALES, `${lang}.js`);
  const sandbox = { window: {} };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(file, "utf8"), sandbox, { filename: file });
  const locale = sandbox.window?.GV_LOCALES?.[lang];
  if (!locale || typeof locale !== "object") {
    throw new Error(`${file}: window.GV_LOCALES.${lang} was not assigned an object`);
  }
  return locale;
}

function vueMessage(value) {
  if (typeof value !== "string") return value;
  // vue-i18n treats `@` as a linked-message prefix and `|` as a plural
  // separator. Legacy copy uses them literally (e.g. "H@H"), so emit the
  // library's literal syntax instead of letting the compiler fail.
  return value.replaceAll("@", "{'@'}").replaceAll("|", "{'|'}");
}

function convert(lang) {
  const source = loadLegacy(lang);
  const out = {};
  const flatKeys = Object.keys(source).filter((key) => key !== "ns" && key !== "groups");
  const flatSet = new Set(flatKeys);
  const mapping = [];

  for (const key of Object.keys(source)) {
    if (key === "ns" || key === "groups") {
      out[key] = Object.fromEntries(
        Object.entries(source[key]).map(([name, text]) => [name, vueMessage(text)]),
      );
      continue;
    }
    if (!key.includes(".")) {
      out[key] = vueMessage(source[key]);
      continue;
    }
    const mapped = key.replaceAll(".", "_");
    if (flatSet.has(mapped) || Object.prototype.hasOwnProperty.call(out, mapped)) {
      errors.push(
        `${lang}: dotted key "${key}" maps to "${mapped}" which already exists; resolve manually`,
      );
      continue;
    }
    out[mapped] = vueMessage(source[key]);
    mapping.push([key, mapped]);
  }

  const sorted = Object.fromEntries(
    Object.keys(out)
      .sort((a, b) => (a === "ns" ? 1 : b === "ns" ? -1 : a.localeCompare(b)))
      .map((key) => [key, out[key]]),
  );
  return { locale: sorted, mapping, leafCount: countLeaves(sorted) };
}

function countLeaves(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.values(value).reduce((sum, item) => sum + countLeaves(item), 0);
  }
  return 1;
}

function render(result) {
  return `${JSON.stringify(result.locale, null, 2)}\n`;
}

const results = {};
for (const lang of LANGS) {
  results[lang] = convert(lang);
}

if (errors.length) {
  for (const error of errors) console.error(`[locales] ${error}`);
  process.exit(ERROR_EXIT);
}

const zhKeys = new Set(Object.keys(results.zh.locale));
const enKeys = new Set(Object.keys(results.en.locale));
for (const key of zhKeys) if (!enKeys.has(key)) errors.push(`en is missing top-level key "${key}"`);
for (const key of enKeys) if (!zhKeys.has(key)) errors.push(`zh is missing top-level key "${key}"`);
if (errors.length) {
  for (const error of errors) console.error(`[locales] ${error}`);
  process.exit(ERROR_EXIT);
}

for (const lang of LANGS) {
  const dir = join(OUT_ROOT, lang);
  const file = join(dir, "legacy.json");
  const text = render(results[lang]);
  if (checkOnly) {
    if (!existsSync(file) || readFileSync(file, "utf8") !== text) {
      console.error(`[locales] ${file} is out of date; run node scripts/convert-locales.mjs`);
      process.exit(ERROR_EXIT);
    }
  } else {
    mkdirSync(dir, { recursive: true });
    writeFileSync(file, text);
  }
  console.log(
    `[locales] ${lang}: ${results[lang].leafCount} leaf keys ` +
      `(${results[lang].mapping.length} dotted keys mapped to underscores)`,
  );
}

const zhMapping = results.zh.mapping;
const enMapping = results.en.mapping;
if (zhMapping.length !== enMapping.length) {
  console.error("[locales] zh/en dotted-key mapping counts differ");
  process.exit(ERROR_EXIT);
}
for (let index = 0; index < zhMapping.length; index += 1) {
  if (zhMapping[index][0] !== enMapping[index][0]) {
    console.error("[locales] zh/en dotted-key mapping sets differ");
    process.exit(ERROR_EXIT);
  }
}

console.log(
  `[locales] mapping: ${zhMapping.map(([from, to]) => `${from} -> ${to}`).join(", ")}`,
);
console.log(`[locales] OK${checkOnly ? " (check only)" : ""}`);
