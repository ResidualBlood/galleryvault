import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// Guards for the three sinks where server text reaches markup:
//   - href  -> safeHref() scheme/shape allowlist, then esc()
//   - cover src -> coverSrc() allowlist, then esc()
//   - innerHTML locale text -> tHtml() only for keys authored as trusted HTML
const here = path.dirname(fileURLToPath(import.meta.url));
const assetsDir = path.join(here, "..", "assets");
const viewsDir = path.join(assetsDir, "views");

// utils.js / i18n.js / locales are classic browser scripts (globals, no
// exports): evaluate them in the test realm so their top-level functions
// become reachable as globals (same approach as view-runtime.test.mjs).
globalThis.window = globalThis;
vm.runInThisContext(fs.readFileSync(path.join(assetsDir, "utils.js"), "utf8"), { filename: "utils.js" });
vm.runInThisContext(fs.readFileSync(path.join(assetsDir, "i18n.js"), "utf8"), { filename: "i18n.js" });
for (const lang of ["zh", "en"]) {
  vm.runInThisContext(
    fs.readFileSync(path.join(assetsDir, "locales", `${lang}.js`), "utf8"),
    { filename: `locales/${lang}.js` },
  );
}

function viewFiles() {
  return fs.readdirSync(viewsDir).filter(name => name.endsWith(".js")).sort();
}

function flatten(obj, prefix = "", out = {}) {
  for (const [key, value] of Object.entries(obj || {})) {
    const full = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object") flatten(value, full, out);
    else out[full] = value;
  }
  return out;
}

test("safeHref: 只放行 http(s)、#、单斜杠相对路径", () => {
  const { safeHref } = globalThis;
  assert.equal(typeof safeHref, "function");
  // allowed
  assert.equal(safeHref("https://e-hentai.org/g/123/abcdef/"), "https://e-hentai.org/g/123/abcdef/");
  assert.equal(safeHref("http://example.com/a?b=1&c=2"), "http://example.com/a?b=1&c=2");
  assert.equal(safeHref("HTTPS://EXAMPLE.COM/X"), "HTTPS://EXAMPLE.COM/X");
  assert.equal(safeHref("#/favorites"), "#/favorites");
  assert.equal(safeHref("/api/galleries/1"), "/api/galleries/1");
  assert.equal(safeHref("  https://example.com/  "), "https://example.com/");
  // rejected -> "#", so the anchor stays inert
  assert.equal(safeHref("javascript:alert(1)"), "#");
  assert.equal(safeHref("JaVaScRiPt:alert(1)"), "#");
  assert.equal(safeHref("data:text/html;base64,PHNjcmlwdD4="), "#");
  assert.equal(safeHref("//evil.example.com/x"), "#");
  assert.equal(safeHref("/\\evil.example.com"), "#");
  assert.equal(safeHref("vbscript:msgbox(1)"), "#");
  assert.equal(safeHref(""), "#");
  assert.equal(safeHref(null), "#");
  assert.equal(safeHref(undefined), "#");
});

test("coverSrc: 只放行图片 data URI、http(s)、单斜杠相对路径", () => {
  const { coverSrc } = globalThis;
  assert.equal(typeof coverSrc, "function");
  // allowed
  assert.equal(coverSrc("data:image/png;base64,AAAA"), "data:image/png;base64,AAAA");
  assert.equal(coverSrc("data:image/jpeg;base64,AAAA"), "data:image/jpeg;base64,AAAA");
  assert.equal(coverSrc("data:image/gif;base64,AAAA"), "data:image/gif;base64,AAAA");
  assert.equal(coverSrc("data:image/webp;base64,AAAA"), "data:image/webp;base64,AAAA");
  assert.equal(coverSrc("https://ehgt.org/t/1.jpg"), "https://ehgt.org/t/1.jpg");
  assert.equal(coverSrc("/api/galleries/7/thumb/0"), "/api/galleries/7/thumb/0");
  // rejected -> "" (callers must skip the <img>)
  assert.equal(coverSrc("data:image/svg+xml;base64,AAAA"), "");
  assert.equal(coverSrc("data:text/html;base64,AAAA"), "");
  assert.equal(coverSrc("data:image/png,notbase64"), "");
  assert.equal(coverSrc("javascript:alert(1)"), "");
  assert.equal(coverSrc("//evil.example.com/x.png"), "");
  assert.equal(coverSrc(""), "");
  assert.equal(coverSrc(null), "");
  assert.equal(coverSrc(undefined), "");
});

test("views: 服务端 URL 进 href 必须先 safeHref 再 esc", () => {
  const bad = [];
  for (const name of viewFiles()) {
    const src = fs.readFileSync(path.join(viewsDir, name), "utf8");
    assert.ok(!src.includes("safeHref(esc("), `${name}: 顺序必须是 esc(safeHref(x))`);
    src.split("\n").forEach((line, i) => {
      if (line.includes('href="${esc(') && !line.includes("safeHref")) {
        bad.push(`${name}:${i + 1}`);
      }
    });
  }
  assert.deepEqual(bad, [], `href 直插未过 safeHref: ${bad.join(", ")}`);
});

test("tHtml: 只出现在可信 HTML locale 的两个使用点", () => {
  const hits = [];
  for (const name of viewFiles()) {
    const src = fs.readFileSync(path.join(viewsDir, name), "utf8");
    src.split("\n").forEach((line, i) => {
      if (line.includes("tHtml(")) hits.push(`${name}:${i + 1}`);
    });
  }
  const files = [...new Set(hits.map(hit => hit.split(":")[0]))].sort();
  assert.deepEqual(files, ["duplicates.js", "integrity.js"]);
  assert.equal(hits.length, 2, `tHtml( 使用点: ${hits.join(", ")}`);
});

test("locales: 含 HTML 标签的键集 == tHtml 白名单", () => {
  const htmlKeys = obj => Object.entries(flatten(obj))
    .filter(([, value]) => typeof value === "string" && /[<>]/.test(value))
    .map(([key]) => key)
    .sort();
  const expected = ["dupXgidInfoDetail", "integrityInfoDetail"];
  for (const lang of ["zh", "en"]) {
    const locale = globalThis.window.GV_LOCALES[lang];
    assert.ok(locale, `缺少 locale: ${lang}`);
    assert.deepEqual(htmlKeys(locale), expected, `${lang} 含 < > 的键`);
  }
});

test("t() 返回原文、tHtml() 显式标记同一份可信 HTML", () => {
  globalThis.app = { lang: "zh" };
  assert.equal(typeof globalThis.tHtml, "function");
  for (const key of ["integrityInfoDetail", "dupXgidInfoDetail"]) {
    assert.match(globalThis.t(key), /<ul/);
    assert.equal(globalThis.tHtml(key), globalThis.t(key));
  }
});
