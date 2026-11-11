import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// views/reader.js is a classic browser script: it declares globals and only
// touches `window` at load time (window.startSlideshow = ...). Evaluating it in
// this realm with window aliased to globalThis exposes the pure helpers without
// needing a DOM; `t`/`esc` are called at render time only, so they are stubbed.
const here = path.dirname(fileURLToPath(import.meta.url));
const readerPath = path.join(here, "..", "assets", "views", "reader.js");
const webtoonPath = path.join(here, "..", "assets", "views", "reader-webtoon.js");
const readerSrc = fs.readFileSync(readerPath, "utf8");
const webtoonSrc = fs.readFileSync(webtoonPath, "utf8");

globalThis.window = globalThis;
globalThis.t = (key, params) => {
  if (key === "readerPageUnavailable") return `第 ${params.n} 页不可用`;
  return key;
};
globalThis.esc = (s) => String(s)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

vm.runInThisContext(readerSrc, { filename: "reader.js" });

const shouldHandleReaderKey = globalThis.shouldHandleReaderKey;
const clampReaderScale = globalThis.clampReaderScale;
const readerPageKey = globalThis.readerPageKey;
const markPageFailed = globalThis.markPageFailed;
const isPageFailed = globalThis.isPageFailed;
const pagePlaceholderHtml = globalThis.pagePlaceholderHtml;

test("reader.js 顶层纯函数可直接加载并导出", () => {
  for (const fn of [shouldHandleReaderKey, clampReaderScale, readerPageKey, markPageFailed, isPageFailed, pagePlaceholderHtml]) {
    assert.equal(typeof fn, "function");
  }
});

test("shouldHandleReaderKey: 丢弃系统重复键", () => {
  assert.equal(shouldHandleReaderKey(1000, 0, true, 80), false);
  assert.equal(shouldHandleReaderKey(5000, 1000, true, 80), false);
});

test("shouldHandleReaderKey: 首次按键总是处理", () => {
  assert.equal(shouldHandleReaderKey(1000, 0, false, 80), true);
});

test("shouldHandleReaderKey: 80ms 阈值不再吞掉 100ms 间隔的连按", () => {
  // 旧实现用 150ms 全局冷却，这里 100ms 内的两次按键必须都生效。
  assert.equal(shouldHandleReaderKey(1100, 1000, false, 80), true);
  assert.equal(shouldHandleReaderKey(1000, 960, false, 80), false);
  assert.equal(shouldHandleReaderKey(1000, 920, false, 80), true);
  // 省略阈值时默认 80ms。
  assert.equal(shouldHandleReaderKey(1000, 950, false), false);
  assert.equal(shouldHandleReaderKey(1000, 920, false), true);
});

test("clampReaderScale: 捏合缩放夹取在 1x–3.5x", () => {
  assert.equal(clampReaderScale(1, 1.5), 1.5);
  assert.equal(clampReaderScale(2, 2), 3.5);
  assert.equal(clampReaderScale(2, 0.1), 1);
  assert.equal(clampReaderScale(3.5, 1.2), 3.5);
});

test("失败缓存：TTL 内命中，过期后可重试", () => {
  const map = new Map();
  markPageFailed(map, readerPageKey(12, 3), 1000);
  assert.equal(isPageFailed(map, "12:3", 1000, 60000), true);
  assert.equal(isPageFailed(map, "12:3", 60999, 60000), true);
  assert.equal(isPageFailed(map, "12:3", 61000, 60000), false);
  // 时钟回拨时不能把未发生过的失败当成命中。
  assert.equal(isPageFailed(map, "12:3", 500, 60000), false);
  // 未记录的键永远不命中。
  assert.equal(isPageFailed(map, "12:4", 1001, 60000), false);
});

test("失败缓存：不同 gallery 的同页号互不干扰", () => {
  const map = new Map();
  markPageFailed(map, readerPageKey(12, 3), 1000);
  assert.equal(isPageFailed(map, "12:3", 1001), true);
  assert.equal(isPageFailed(map, "13:3", 1001), false);
  assert.equal(readerPageKey(12, 3), readerPageKey("12", "3"));
});

test("pagePlaceholderHtml: 1-based 文案、占位类名与 data-page", () => {
  const html = pagePlaceholderHtml(4);
  assert.ok(html.includes('class="reader-page-missing"'));
  assert.ok(html.includes('data-page="4"'));
  assert.ok(html.includes("第 5 页不可用"));
});

test("pagePlaceholderHtml: 文案经过 HTML 转义", () => {
  const original = globalThis.t;
  globalThis.t = () => '<img src=x onerror="alert(1)">';
  try {
    const html = pagePlaceholderHtml(0);
    assert.equal(html.includes("<img"), false);
    assert.ok(html.includes("&lt;img"));
  } finally {
    globalThis.t = original;
  }
});

test("reader.js 接线：e.repeat 忽略、渲染回顶部、换页复位缩放", () => {
  assert.ok(readerSrc.includes("e.repeat"));
  assert.ok(readerSrc.includes("window.scrollTo({ top: 0"));

  const swapStart = readerSrc.indexOf("function readerSwapPage(");
  const swapEnd = readerSrc.indexOf("function toggleReaderFit(");
  assert.ok(swapStart > 0 && swapEnd > swapStart);
  assert.ok(readerSrc.slice(swapStart, swapEnd).includes("resetReaderZoom();"),
    "readerSwapPage 未复位缩放");

  // 预热必须先查失败缓存，否则坏页会被每个相邻页反复请求。
  const preloadStart = readerSrc.indexOf("function preloadReaderPages(");
  const preloadEnd = readerSrc.indexOf("async function renderReader(");
  const preload = readerSrc.slice(preloadStart, preloadEnd);
  assert.ok(preload.includes("isPageFailed("), "preloadReaderPages 未跳过失败页");

  // 换页时的相邻页预热同样要查缓存。
  const swap = readerSrc.slice(swapStart, swapEnd);
  assert.ok(swap.includes("isPageFailed("), "readerSwapPage 预热未跳过失败页");
});

test("webtoon：复用手势并给坏页挂占位", () => {
  const gestures = readerSrc.slice(
    readerSrc.indexOf("function initReaderGestures("),
    readerSrc.indexOf("function toggleReaderFullscreen("),
  );
  assert.ok(gestures.includes("webtoon-strip"), "手势容器未包含 .webtoon-strip");
  assert.ok(webtoonSrc.includes("initReaderGestures()"), "webtoon 渲染后未初始化手势");
  assert.ok(webtoonSrc.includes("onWebtoonPageError"), "webtoon 缺少坏页处理");
  assert.ok(webtoonSrc.includes("pagePlaceholderHtml("), "webtoon 未显示占位");
});

test("locales：zh/en 均有 readerPageUnavailable", () => {
  function locale(file) {
    const ctx = { window: {} };
    vm.runInNewContext(fs.readFileSync(path.join(here, "..", "assets", "locales", file), "utf8"), ctx);
    return ctx.window.GV_LOCALES;
  }
  const zh = locale("zh.js").zh;
  const en = locale("en.js").en;
  assert.equal(typeof zh.readerPageUnavailable, "string");
  assert.equal(typeof en.readerPageUnavailable, "string");
  assert.ok(zh.readerPageUnavailable.includes("{n}"));
  assert.ok(en.readerPageUnavailable.includes("{n}"));
});
