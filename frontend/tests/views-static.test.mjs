import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Static guard for the view render contract: every async `render*` entry point
// must go through the shared view runtime (withViewRender) or at least keep a
// render token (isStaleViewRender), so a slow response can never overwrite a
// newer view.
const here = path.dirname(fileURLToPath(import.meta.url));
const viewsDir = path.join(here, "..", "assets", "views");

const DECL_RE = /^(?:async\s+)?function\s+([A-Za-z0-9_$]+)/gm;
const RENDER_RE = /^async\s+function\s+(render[A-Za-z0-9_$]*)\s*\(/gm;

function listViewFiles() {
  return fs.readdirSync(viewsDir)
    .filter(name => name.endsWith(".js"))
    .sort();
}

// Source of one top-level function: from its declaration line up to the next
// top-level declaration. Views declare every function at column 0, so this is
// stable even when the body contains template literals with unbalanced braces.
function functionSource(src, startIndex) {
  DECL_RE.lastIndex = startIndex + 1;
  const next = DECL_RE.exec(src);
  return src.slice(startIndex, next ? next.index : src.length);
}

function renderEntries(src) {
  const out = [];
  RENDER_RE.lastIndex = 0;
  let m;
  while ((m = RENDER_RE.exec(src))) {
    out.push({ name: m[1], source: functionSource(src, m.index) });
  }
  return out;
}

const files = listViewFiles();
const scanned = files.map(name => ({
  name,
  source: fs.readFileSync(path.join(viewsDir, name), "utf8"),
}));

test("views: 所有 async render* 都接入 view runtime token", () => {
  const bare = [];
  let total = 0;
  for (const { name, source } of scanned) {
    for (const entry of renderEntries(source)) {
      total++;
      const key = `${name}:${entry.name}`;
      const guarded = entry.source.includes("withViewRender") || entry.source.includes("isStaleViewRender");
      if (!guarded) bare.push(key);
    }
  }
  assert.ok(total >= 20, `扫描到的 render* 数量异常: ${total}`);
  assert.deepEqual(bare, [], `未接入 view runtime 的 render*: ${bare.join(", ")}`);
});

test("views: reader 用 new Image() 预加载，不再往 body 注入 link rel=preload", () => {
  const reader = scanned.find(f => f.name === "reader.js");
  assert.ok(reader, "reader.js 缺失");
  assert.equal(reader.source.includes('rel="preload"'), false, "reader.js 仍含 <link rel=preload>");
  assert.equal(reader.source.includes("new Image()"), true, "reader.js 缺少 new Image() 预加载");
});
