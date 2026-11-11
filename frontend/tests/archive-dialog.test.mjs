import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// Archive dialog (components.js showArchiveDialog).
//
// The two decisions that must hold regardless of the DOM are extracted as pure
// helpers in utils.js: which tier is preselected and whether the confirm button
// is clickable. utils.js is a classic browser script (global function
// declarations, lazy DOM/`app` access), so evaluating it in this realm exposes
// them without a DOM. The remaining dialog wiring (checked at innerHTML time,
// AbortController on close, radio lock + retry on failure) is guarded by
// source assertions, following frontend/tests/views-static.test.mjs.
const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.join(here, "..");
const assetsDir = path.join(frontend, "assets");

function loadUtils() {
  const src = fs.readFileSync(path.join(assetsDir, "utils.js"), "utf8");
  vm.runInThisContext(src, { filename: "utils.js" });
  return {
    archiveDefaultTier: globalThis.archiveDefaultTier,
    archiveConfirmEnabled: globalThis.archiveConfirmEnabled,
  };
}

const { archiveDefaultTier, archiveConfirmEnabled } = loadUtils();

const componentsSrc = fs.readFileSync(path.join(assetsDir, "components.js"), "utf8");

// Body of the top-level function, from its declaration to the next top-level
// declaration (components.js declares every function at column 0).
function functionSource(src, name) {
  const start = src.search(new RegExp(`^(?:async\\s+)?function\\s+${name}\\b`, "m"));
  assert.ok(start >= 0, `未找到顶层函数 ${name}`);
  const rest = src.slice(start + 1);
  const next = rest.search(/^(?:async\s+)?function\s+[A-Za-z0-9_$]+\s*\(/m);
  return next >= 0 ? src.slice(start, start + 1 + next) : src.slice(start);
}

const dialogSrc = functionSource(componentsSrc, "showArchiveDialog");

test("archive: 默认 tier 由 app.settings.archive_quality 决定", () => {
  assert.equal(typeof archiveDefaultTier, "function");
  assert.equal(archiveDefaultTier({ archive_quality: "original" }), "original");
  assert.equal(archiveDefaultTier({ archive_quality: "resample" }), "resample");
  // 设置缺失/未预取时回落 resample（与后端默认一致）
  assert.equal(archiveDefaultTier(null), "resample");
  assert.equal(archiveDefaultTier(undefined), "resample");
  assert.equal(archiveDefaultTier({}), "resample");
});

test("archive: 确认按钮 4 种组合（成功有 items / 空 / 全 error / 请求失败）", () => {
  const ok = { gid: 1, title: "t", original_cost: 100, resample_cost: 50 };
  // 成功且有可用条目 -> 可确认
  assert.equal(archiveConfirmEnabled({ items: [ok], lockTier: null, failed: false }), true);
  // 成功但 items 为空 -> 不可确认
  assert.equal(archiveConfirmEnabled({ items: [], lockTier: null, failed: false }), false);
  // 全部条目 error -> 不可确认
  assert.equal(
    archiveConfirmEnabled({ items: [{ gid: 1, error: "422" }, { gid: 2, error: "422" }], lockTier: null, failed: false }),
    false,
  );
  // 预览请求失败 -> 不可确认
  assert.equal(archiveConfirmEnabled({ items: [ok], lockTier: null, failed: true }), false);
  // 缺省参数（无 items）同样是不可确认
  assert.equal(archiveConfirmEnabled({}), false);
});

test("archive: 部分 error 仍有可归档条目时可确认（与全 error 区分）", () => {
  const items = [{ gid: 1, error: "422" }, { gid: 2, title: "t", original_cost: 100, resample_cost: 50 }];
  assert.equal(archiveConfirmEnabled({ items, lockTier: null, failed: false }), true);
});

test("archive: lockTier=original 仍按原图可用性决定确认", () => {
  assert.equal(archiveConfirmEnabled({
    items: [{ gid: 1, original_cost: 100, original_available: true }],
    lockTier: "original",
    failed: false,
  }), true);
  assert.equal(archiveConfirmEnabled({
    items: [{ gid: 1, original_cost: 100, original_available: false }],
    lockTier: "original",
    failed: false,
  }), false);
  assert.equal(archiveConfirmEnabled({
    items: [{ gid: 1, error: "422" }],
    lockTier: "original",
    failed: false,
  }), false);
});

test("archive: 对话框在 innerHTML 阶段就写入默认 checked，不等预览", () => {
  assert.equal(dialogSrc.includes("archiveDefaultTier(app.settings)"), true, "未在渲染阶段计算默认 tier");
  assert.ok(
    /value="original"\$\{defaultTier === "original" \? " checked" : ""\}/.test(dialogSrc),
    "默认 original 未在 radio 上写 checked",
  );
  assert.ok(
    /value="resample"\$\{defaultTier === "resample" \? " checked" : ""\}/.test(dialogSrc),
    "默认 resample 未在 radio 上写 checked",
  );
});

test("archive: 关闭对话框 abort 预览请求，AbortError 静默", () => {
  assert.equal(dialogSrc.includes("new AbortController()"), true, "缺少 AbortController");
  assert.equal(dialogSrc.includes("{signal: ctrl.signal}"), true, "preview 请求未带 signal");
  // close() 是箭头函数：从声明到 settle 分支末尾必须 abort 当前 controller。
  const closeMatch = /const close = \(value\) => \{([\s\S]*?)\n    \};/.exec(dialogSrc);
  assert.ok(closeMatch, "未找到 close()");
  assert.equal(closeMatch[1].includes("ctrl.abort()"), true, "close() 未取消 preview 请求");
  assert.equal(dialogSrc.includes('err.name === "AbortError"'), true, "AbortError 未被静默");
});

test("archive: 预览失败禁用 radio、显示重试按钮并保持确认禁用", () => {
  assert.equal(dialogSrc.includes("data-archive-retry"), true, "缺少重试按钮");
  assert.equal(dialogSrc.includes("archiveRetry"), true, "重试按钮未走 i18n");
  assert.equal(dialogSrc.includes("retryEl.hidden = false"), true, "失败时未显示重试");
  assert.equal(dialogSrc.includes("setRadiosDisabled(true)"), true, "失败时未禁用 radio");
  assert.equal(dialogSrc.includes("retryEl.addEventListener(\"click\", loadPreview)"), true, "重试按钮未重新 POST");
  // 确认按钮状态统一由纯函数决定，避免各分支各写一套
  assert.equal(dialogSrc.includes("archiveConfirmEnabled({items: previewItems, lockTier, failed: previewFailed})"), true);
});

test("archive: items 全部 error 时把首个错误提到 body 并禁用 radio", () => {
  assert.ok(
    /items\.every\(it => it\.error\)/.test(dialogSrc),
    "未检测全部 error",
  );
  assert.ok(
    /const first = items\.find\(it => it\.error\);\s*\n\s*html = `<p class="error">\$\{esc\(first\.error\)\}<\/p>` \+ html;/.test(dialogSrc),
    "全 error 时未把首个错误提到 body",
  );
});

test("archive: 新 i18n 键在 zh/en 同时存在", () => {
  for (const lang of ["zh", "en"]) {
    const sandbox = { window: {} };
    sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    const file = path.join(assetsDir, "locales", `${lang}.js`);
    vm.runInContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
    const loc = sandbox.window.GV_LOCALES[lang];
    assert.equal(typeof loc.archiveRetry, "string", `${lang} 缺少 archiveRetry`);
    assert.ok(loc.archiveRetry.length > 0, `${lang} archiveRetry 为空`);
  }
});

// --- series 视图勾选不得写入画廊库选择集合（r2-fe-misc-p3 回归） ---------------

test("selection: components.js 的 data-gallery-id 绑定排除 #series-list", () => {
  const checkboxesSrc = functionSource(componentsSrc, "renderCardCheckboxes");
  assert.equal(
    checkboxesSrc.includes("isLibrarySelectionBox"),
    true,
    "renderCardCheckboxes 未区分 series 视图的勾选框",
  );
  assert.equal(
    checkboxesSrc.includes('cb.closest("#series-list")'),
    true,
    "未按 #series-list 容器排除 series 卡片",
  );
  const guardAt = checkboxesSrc.indexOf("if (!isLibrarySelectionBox(cb)) return;");
  const addAt = checkboxesSrc.indexOf("selGalleries.add(id)");
  assert.ok(guardAt >= 0 && addAt > guardAt, "series 排除守卫必须早于 selGalleries.add");
  // 裁剪可见集合时同样只看库视图的勾选框，避免 series 的 id 混入
  assert.equal(
    /filter\(isLibrarySelectionBox\)/.test(checkboxesSrc),
    true,
    "pruneSelection 的 visibleGalleryIds 未排除 series 勾选框",
  );
});

test("selection: series.js 只写 selSeriesLocal，不碰 selGalleries", () => {
  const seriesSrc = fs.readFileSync(path.join(assetsDir, "views", "series.js"), "utf8");
  const changeSrc = functionSource(seriesSrc, "onSeriesChange");
  assert.equal(changeSrc.includes("selSeriesLocal.add"), true, "series 勾选未写入 selSeriesLocal");
  assert.equal(changeSrc.includes("selGalleries"), false, "series 勾选仍写入 selGalleries");
  assert.equal(seriesSrc.includes("selGalleries"), false, "series.js 全文件不应引用 selGalleries");
  assert.equal(seriesSrc.includes('id="series-list"'), true, "series 容器 id 变了，components.js 的排除会失效");
});
