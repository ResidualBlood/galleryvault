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

// --- 回归护栏：本轮修复的视图/核心缺陷不得复发 -----------------------------

const assetsDir = path.join(here, "..", "assets");
const assetSource = rel => fs.readFileSync(path.join(assetsDir, rel), "utf8");

function topLevelFunctionSource(src, name) {
  const re = new RegExp(`^(?:async\\s+)?function\\s+${name}\\b`, "m");
  const m = re.exec(src);
  assert.ok(m, `未找到顶层函数 ${name}`);
  return functionSource(src, m.index);
}

test("views: favorites 收藏卡 change 不重复绑定（components.js 已绑定）", () => {
  const fav = scanned.find(f => f.name === "favorites.js");
  assert.ok(fav, "favorites.js 缺失");
  assert.equal(
    fav.source.includes('addEventListener("change"'),
    false,
    "favorites.js 仍为收藏卡单独绑定 change（与 components.js 重复）",
  );
});

test("views: series 本地选择用独立集合，不复用画廊库选择", () => {
  const series = scanned.find(f => f.name === "series.js");
  assert.ok(series, "series.js 缺失");
  assert.equal(series.source.includes("selGalleries"), false, "series.js 仍引用画廊库选择集合");
  assert.equal(series.source.includes("selSeriesLocal"), true, "series.js 缺少 selSeriesLocal");
});

test("state: EH_BASE_URLS 标签走 i18n，不再中文硬编码", () => {
  const src = assetSource("state.js");
  assert.equal(src.includes("ExHentai（里站）"), false, "state.js 仍硬编码中文站点标签");
  assert.equal(src.includes('t("ehBaseExhentai")'), true, "state.js 未通过 t() 取站点标签");
});

test("core: api() 遇到 401 停止轮询并回登录页", () => {
  const src = assetSource("core.js");
  assert.equal(src.includes("res.status === 401"), true, "api() 缺少 401 分支");
  assert.equal(src.includes('path !== "/api/auth/session"'), true, "401 分支未排除会话探针");
});

test("core: doLogout 跑当前视图 cleanup 并置空", () => {
  const body = topLevelFunctionSource(assetSource("core.js"), "doLogout");
  assert.equal(body.includes("currentViewCleanup()"), true, "doLogout 未调用 currentViewCleanup");
  assert.equal(body.includes("currentViewCleanup = null"), true, "doLogout 未置空 currentViewCleanup");
});

test("core: parseHash 对非法详情 id 回退到浏览页", () => {
  const body = topLevelFunctionSource(assetSource("core.js"), "parseHash");
  assert.equal(body.includes('"#/browse"'), true, "parseHash 未回退到 #/browse");
  assert.equal(body.includes("invalidLink"), true, "parseHash 未提示非法链接");
});
