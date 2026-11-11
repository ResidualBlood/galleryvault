import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const GVViewRuntime = require(path.join(here, "..", "assets", "view-runtime.js"));

// utils.js is a classic browser script (globals, no exports): evaluate it in
// the test realm so its top-level functions become reachable as globals.
vm.runInThisContext(fs.readFileSync(path.join(here, "..", "assets", "utils.js"), "utf8"), {
  filename: "utils.js",
});
const utils = globalThis;

function abortError() {
  const err = new Error("The operation was aborted.");
  err.name = "AbortError";
  return err;
}

function makeRuntime(extra = {}) {
  const app = { view: "library", params: {}, query: {} };
  let seq = 0;
  const rt = GVViewRuntime.createViewRuntime({
    getApp: () => app,
    getSeq: () => seq,
    setSeq: (n) => { seq = n; },
    api: async () => ({}),
    ...extra,
  });
  return { app, rt };
}

test("withViewRender: 旧 token 在新渲染后 stale 为 true，并中止旧 signal", () => {
  const { rt } = makeRuntime();
  let first = null;
  rt.withViewRender("library", undefined, ctx => { first = ctx; });
  let second = null;
  rt.withViewRender("library", undefined, ctx => { second = ctx; });

  assert.equal(first.stale(), true);
  assert.equal(second.stale(), false);
  assert.equal(first.signal.aborted, true);
  assert.equal(second.signal.aborted, false);
});

test("withViewRender: 视图已切走时 stale 为 true，切回后新 token 不 stale", () => {
  const { app, rt } = makeRuntime();
  let ctx;
  rt.withViewRender("library", undefined, c => { ctx = c; });
  assert.equal(ctx.stale(), false);

  app.view = "discover";
  assert.equal(ctx.stale(), true);

  let fresh;
  rt.withViewRender("discover", undefined, c => { fresh = c; });
  assert.equal(fresh.stale(), false);
  assert.equal(fresh.seq, ctx.seq + 1);
});

test("withViewRender: AbortError 不抛到调用方（返回 undefined）", async () => {
  const { rt } = makeRuntime({ api: () => Promise.reject(abortError()) });
  const result = await rt.withViewRender("discover", undefined, async ctx => {
    await ctx.api("GET", "/api/eh/search");
  });
  assert.equal(result, undefined);
});

test("withViewRender: 非 AbortError 仍然抛出", async () => {
  const { rt } = makeRuntime({ api: () => Promise.reject(new Error("boom")) });
  await assert.rejects(
    rt.withViewRender("discover", undefined, async ctx => { await ctx.api("GET", "/x"); }),
    /boom/,
  );
});

test("withViewRender: ctx.api 注入本轮的 signal", async () => {
  let seen = null;
  const { rt } = makeRuntime({
    api: async (method, p, body, opts) => { seen = { method, p, body, opts }; return { ok: true }; },
  });
  let ctx;
  const data = await rt.withViewRender("history", undefined, c => {
    ctx = c;
    return c.api("GET", "/api/history", undefined, { signal: "caller" });
  });
  assert.deepEqual(data, { ok: true });
  assert.equal(seen.method, "GET");
  assert.equal(seen.p, "/api/history");
  assert.equal(seen.opts.signal, ctx.signal);
});

test("stopInfinite: 非 owner 调用被忽略", () => {
  globalThis.infiniteState = { ownerSeq: 7, observer: null, controller: null, sentinel: null };
  utils.stopInfinite({ ownerSeq: 99 });
  assert.notEqual(globalThis.infiniteState, null);
  assert.equal(globalThis.infiniteState.ownerSeq, 7);
  globalThis.infiniteState = null;
});

test("stopInfinite: owner 可停止，无参（router）也可停止", () => {
  globalThis.infiniteState = { ownerSeq: 7, observer: null, controller: null, sentinel: null };
  utils.stopInfinite({ ownerSeq: 7 });
  assert.equal(globalThis.infiniteState, null);

  globalThis.infiniteState = { ownerSeq: 8, observer: null, controller: null, sentinel: null };
  utils.stopInfinite();
  assert.equal(globalThis.infiniteState, null);
});
