"use strict";

// view-runtime.js — 视图渲染运行时 (render token + AbortController + stale guard)
// 纯逻辑，不直接依赖 DOM：app / 序号计数 / api 都可注入，便于 node 测试。
// 全局入口由 core.js 用 createViewRuntime 创建（getSeq/setSeq 复用 viewRenderSeq）。

function isAbortError(err) {
  return !!err && (err.name === "AbortError" || err.code === 20);
}

function createViewRuntime(opts) {
  opts = opts || {};
  const getApp = typeof opts.getApp === "function" ? opts.getApp : () => ({});
  const makeAbort = typeof opts.createAbortController === "function"
    ? opts.createAbortController
    : () => new AbortController();
  const callApi = typeof opts.api === "function"
    ? opts.api
    : (method, path, body, o) => {
      if (typeof api !== "function") throw new Error("view-runtime: api() is not available");
      return api(method, path, body, o);
    };

  // 序号计数默认由本运行时持有；core.js 注入 getSeq/setSeq 后可共用 viewRenderSeq。
  let localSeq = 0;
  const getSeq = typeof opts.getSeq === "function" ? opts.getSeq : () => localSeq;
  const setSeq = typeof opts.setSeq === "function" ? opts.setSeq : (n) => { localSeq = n; };

  let controller = null;

  function currentSeq() {
    return Number(getSeq()) || 0;
  }

  function abortCurrent() {
    const c = controller;
    controller = null;
    if (c) {
      try { c.abort(); } catch (_) {}
    }
  }

  // 每次 router()/视图渲染都递增序号，并取消上一轮仍在飞行的请求。
  function beginViewRender() {
    const seq = currentSeq() + 1;
    setSeq(seq);
    abortCurrent();
    return seq;
  }

  function isStale(token, view, id) {
    if (token !== currentSeq()) return true;
    const app = getApp() || {};
    if (view !== undefined && app.view !== view) return true;
    if (id !== undefined && id !== null && String((app.params && app.params.id) || "") !== String(id)) return true;
    return false;
  }

  // withViewRender(view, id, fn) -> fn({seq, signal, stale(), api, abort})
  // AbortError 属于“被更新的渲染取代”，不得冒泡成未处理拒绝。
  function withViewRender(view, id, fn) {
    if (typeof fn !== "function") throw new TypeError("withViewRender(view, id, fn) requires fn");
    const seq = beginViewRender();
    const ctrl = makeAbort();
    controller = ctrl;
    const ctx = {
      seq,
      signal: ctrl.signal,
      stale: () => isStale(seq, view, id),
      api: (method, path, body, o) => callApi(method, path, body, Object.assign({}, o || {}, { signal: ctrl.signal })),
      abort: () => { try { ctrl.abort(); } catch (_) {} },
    };
    let result;
    try {
      result = fn(ctx);
    } catch (err) {
      if (isAbortError(err)) return undefined;
      throw err;
    }
    if (result && typeof result.then === "function") {
      return Promise.resolve(result).catch(err => {
        if (isAbortError(err)) return undefined;
        throw err;
      });
    }
    return result;
  }

  return { beginViewRender, isStale, withViewRender, abort: abortCurrent, currentSeq };
}

const GVViewRuntime = { createViewRuntime, isAbortError };

if (typeof window !== "undefined" && window) {
  window.GVViewRuntime = GVViewRuntime;
  window.isAbortError = isAbortError;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = GVViewRuntime;
}
