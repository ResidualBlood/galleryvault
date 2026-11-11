import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// Static i18n guard. It never touches the DOM: locales are classic browser
// scripts assigning `window.GV_LOCALES.{zh,en}`, so they are evaluated in an
// isolated vm context, and every `t("key")` / `t('key')` / `data-i18n*="key"`
// reference under frontend/assets + frontend/index.html is collected with a
// regex (the same scan that produced the recorded baseline in
// /tmp/opencode/gv-r2/i18n_check.mjs).
//
// Baseline (this worktree, 760 flat keys/lang, 641 static keys):
//   missing zh = 0, missing en = 0, zh/en key-set diff = 0, orphans = 94/lang.
//
// Dynamic key construction cannot be resolved statically. Known prefixes:
//   - favMode  -> favorites.js: `t("favMode" + mode)` resolves favModeIncremental,
//                 favModeMonitorOnly, favModeForce.
// A literal inside the scan that is not a locale key but *is* a prefix of real
// locale keys is treated as such a dynamic prefix. Any prefix not listed above
// fails the "dynamic prefix allowlist" test, so it must be added here (after
// checking it is really a runtime-computed key, not a typo).
//
// Nested objects `ns.*` / `groups.*` are read through nsLabel()/groupLabel()
// (i18n.js), never through t(), so they are excluded from orphan detection.
// Orphans are allowed to stay at the baseline (deleting them is a separate
// task) but must not grow.

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.join(here, "..");

const LOCALES = ["zh", "en"];
const ORPHAN_BASELINE = 94;
const KNOWN_DYNAMIC_PREFIXES = ["favMode"];
const NESTED_PREFIXES = ["ns.", "groups."];

function loadLocale(name) {
  const sandbox = { window: {} };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  const file = path.join(frontend, "assets", "locales", `${name}.js`);
  vm.runInContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
  const loc = (sandbox.window.GV_LOCALES || {})[name];
  assert.ok(loc && typeof loc === "object", `locales/${name}.js 必须赋值 window.GV_LOCALES.${name}`);
  return loc;
}

function flatKeys(obj, prefix = "", out = new Set()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    out.add(key);
    if (v && typeof v === "object" && !Array.isArray(v)) flatKeys(v, key, out);
  }
  return out;
}

function walk(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name === "locales") continue;
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, acc);
    else if (/\.(js|html)$/.test(ent.name)) acc.push(p);
  }
  return acc;
}

const locales = Object.fromEntries(LOCALES.map(name => [name, loadLocale(name)]));
const flat = Object.fromEntries(LOCALES.map(name => [name, flatKeys(locales[name])]));

// key -> ["relative/path:line", ...]
const used = new Map();
const RE_T = /\bt\(\s*(["'])((?:\\.|(?!\1).)*)\1/g;
const RE_I18N = /data-i18n(?:-text|-placeholder|-title|-aria-label)?\s*=\s*(["'])([A-Za-z0-9_.]+)\1/g;

const scanFiles = walk(path.join(frontend, "assets")).concat([path.join(frontend, "index.html")]);
assert.ok(scanFiles.length > 0, "i18n 扫描未找到任何源文件");

for (const file of scanFiles) {
  const src = fs.readFileSync(file, "utf8");
  const rel = path.relative(path.join(frontend, ".."), file);
  const add = (key, index) => {
    const line = src.slice(0, index).split("\n").length;
    if (!used.has(key)) used.set(key, []);
    used.get(key).push(`${rel}:${line}`);
  };
  for (const m of src.matchAll(RE_T)) add(m[2], m.index);
  for (const m of src.matchAll(RE_I18N)) add(m[2], m.index);
}

const usedKeys = [...used.keys()].sort();
const isPrefixOf = (key, keys) => keys.some(k => k !== key && k.startsWith(key));
const dynamicPrefixes = usedKeys.filter(key => !flat.zh.has(key) && isPrefixOf(key, [...flat.zh]));

function formatMissing(keys) {
  return keys.map(key => `${key} <- ${used.get(key).join(", ")}`).join("\n");
}

function missingIn(lang) {
  assert.ok(usedKeys.length > 0, "静态扫描未找到任何 i18n 引用（扫描断链）");
  const keys = [...flat[lang]];
  return usedKeys.filter(key => !flat[lang].has(key) && !isPrefixOf(key, keys));
}

function orphanKeys(lang) {
  return [...flat[lang]]
    .filter(key => !used.has(key))
    .filter(key => !NESTED_PREFIXES.some(p => key.startsWith(p)))
    .filter(key => !dynamicPrefixes.some(p => key.startsWith(p)))
    .sort();
}

test("i18n: locales 定义 zh/en 且两语言扁平键集相等", () => {
  const zh = [...flat.zh].sort();
  const en = [...flat.en].sort();
  const zhOnly = zh.filter(key => !flat.en.has(key));
  const enOnly = en.filter(key => !flat.zh.has(key));
  assert.deepEqual(
    { zhOnly, enOnly },
    { zhOnly: [], enOnly: [] },
    `zh/en 键集不一致：\nzh-only: ${zhOnly.join(", ") || "-"}\nen-only: ${enOnly.join(", ") || "-"}`,
  );
  assert.equal(zh.length, en.length);
});

test("i18n: 静态引用的键在 zh 全部存在", () => {
  const missing = missingIn("zh");
  assert.deepEqual(missing, [], `zh 缺键：\n${formatMissing(missing)}`);
});

test("i18n: 静态引用的键在 en 全部存在", () => {
  const missing = missingIn("en");
  assert.deepEqual(missing, [], `en 缺键：\n${formatMissing(missing)}`);
});

test("i18n: 孤儿键数量不增长（基线 94/lang）", () => {
  const orphansZh = orphanKeys("zh");
  const orphansEn = orphanKeys("en");
  assert.ok(
    orphansZh.length <= ORPHAN_BASELINE,
    `zh 孤儿键 ${orphansZh.length} > 基线 ${ORPHAN_BASELINE}：\n${orphansZh.join(", ")}`,
  );
  assert.ok(
    orphansEn.length <= ORPHAN_BASELINE,
    `en 孤儿键 ${orphansEn.length} > 基线 ${ORPHAN_BASELINE}：\n${orphansEn.join(", ")}`,
  );
  // Same keys on both sides: a key orphaned in one language only means the
  // other locale lost a reference (or a language file drifted).
  assert.deepEqual(orphansZh, orphansEn, "zh/en 孤儿键集合不一致");
});

test("i18n: 动态前缀键在白名单内（无法静态解析的 t() 键）", () => {
  const unexpected = dynamicPrefixes.filter(prefix => !KNOWN_DYNAMIC_PREFIXES.includes(prefix));
  assert.deepEqual(
    unexpected,
    [],
    `出现未登记的动态键前缀（可能掩盖缺键）：${unexpected.join(", ")}\n` +
      `请确认是 t("prefix" + x) 拼接后加入 KNOWN_DYNAMIC_PREFIXES。`,
  );
});
