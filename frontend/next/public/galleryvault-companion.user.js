// ==UserScript==
// @name         GalleryVault Companion
// @version      0.1.0
// @namespace    https://galleryvault.local/companion
// @description  在 E-Hentai / ExHentai 画廊页显示 GalleryVault 库内状态，并一键下载 / 收藏 / 打开。阅读增强请搭配 Comic Looms。
// @author       GalleryVault
// @match        https://e-hentai.org/g/*
// @match        https://exhentai.org/g/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @connect      *
// @run-at       document-idle
// @noframes
// ==/UserScript==
/*
 * GalleryVault Companion — generated file, do not edit.
 * Source: userscript/companion.mjs · rebuild with `node userscript/build.mjs`.
 */
(function () {
  "use strict";

/**
 * GalleryVault companion userscript — source of truth.
 *
 * `userscript/build.mjs` inlines this module into
 * `public/galleryvault-companion.user.js` (a userscript cannot import modules).
 * Everything here is either a pure helper (unit-tested directly) or DOM code
 * that only runs through `createCompanion()` / `init()`.
 *
 * Design constraints (PLAN-frontend-rewrite §3.0 C, §3.3):
 *  - only the two EH gallery hosts are matched, never `*://*`;
 *  - requests go to the user-configured GalleryVault origin with a Bearer
 *    token, using `GM_xmlhttpRequest` (no CORS, no EH cookies touched);
 *  - reading enhancement is out of scope (recommend Comic Looms instead);
 *  - the API token never reaches the page DOM, `console` or thrown messages.
 */

/* global document, window, URL */

/* ------------------------------------------------------------------ constants */

/** `#gd5` is the "Download" row of the gallery details block on EH pages. */
const SELECTORS = {
  panelId: "gv-companion-panel",
  anchors: ["#gd5", "#gd4", "#gd3", "#gd1"],
  fallback: "#gdd",
  title: "#gn",
};

const STORAGE_KEYS = {
  base: "gv_base_url",
  token: "gv_api_token",
};

const API = {
  status: "/api/eh/status",
  downloads: "/api/downloads",
  favoritesAdd: "/api/favorites/add",
  favoriteCategories: "/api/favorites/categories",
};

const QUAILITIES = ["resample", "original"];
const FAVCAT_VALUES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

const EMPTY_STATUS = Object.freeze({
  inLibrary: false,
  galleryId: null,
  favorited: false,
  favcat: null,
  downloadStatus: null,
});

/* --------------------------------------------------------------- pure helpers */

function safePath(input) {
  if (typeof input === "string") {
    try {
      return new URL(input, "https://e-hentai.org/").pathname;
    } catch {
      return "";
    }
  }
  return "";
}

/**
 * Gallery coordinates from a location-like object or href string.
 * Accepts `/g/<gid>/<token>/` and deeper page paths, rejects list pages.
 */
function parseGalleryLocation(input) {
  const pathname =
    typeof input === "string"
      ? safePath(input)
      : input && typeof input.pathname === "string"
        ? input.pathname
        : "";
  const match = /^\/g\/(\d+)\/([0-9A-Za-z]+)(?:\/|$)/.exec(pathname);
  if (!match) return null;
  const gid = Number(match[1]);
  if (!Number.isSafeInteger(gid) || gid <= 0) return null;
  return { gid, token: match[2] };
}

/** Normalise a user-entered GalleryVault address; "" means "not configured". */
function normalizeBaseUrl(raw) {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  let url;
  try {
    url = new URL(trimmed);
  } catch {
    return "";
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return "";
  if (!url.hostname) return "";
  const path = url.pathname.replace(/\/+$/, "");
  return `${url.origin}${path}`;
}

function statusPath(gids) {
  const list = (Array.isArray(gids) ? gids : [gids])
    .map((gid) => Number(gid))
    .filter((gid) => Number.isSafeInteger(gid) && gid > 0)
    .slice(0, 100);
  return `${API.status}?gids=${list.join(",")}`;
}

/**
 * Request envelope handed to `GM_xmlhttpRequest`. Throws without echoing the
 * token so callers can surface a generic "请重新配置" message.
 */
function buildApiRequest(base, token, spec) {
  const origin = normalizeBaseUrl(base);
  if (!origin) throw new Error("invalid_base_url");
  if (typeof token !== "string" || !token) throw new Error("missing_token");
  const method = String(spec && spec.method ? spec.method : "GET").toUpperCase();
  const path = String((spec && spec.path) || "/");
  const url = `${origin}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };
  const request = { method, url, headers };
  if (spec && spec.body !== undefined) {
    headers["Content-Type"] = "application/json";
    request.data = JSON.stringify(spec.body);
  }
  return request;
}

function galleryVaultUrl(base, gid, token) {
  const origin = normalizeBaseUrl(base);
  if (!origin) return "";
  return `${origin}/#/online/g/${encodeURIComponent(String(gid))}/${encodeURIComponent(token)}`;
}

function normalizeId(value) {
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function normalizeFavcat(value) {
  if (value === null || value === undefined || value === "") return null;
  const favcat = Number(value);
  return Number.isInteger(favcat) && favcat >= 0 && favcat <= 9 ? favcat : null;
}

function normalizeDownloadStatus(value) {
  if (typeof value !== "string") return null;
  const status = value.trim().toLowerCase();
  return status ? status : null;
}

/**
 * Merge a `/api/eh/status` item into a previous view model. Backend payloads
 * use snake_case; the view model is camelCase. Missing fields keep the old
 * value so a partial response never flips a badge off.
 */
function mergeStatus(previous, item) {
  const base = { ...EMPTY_STATUS, ...(previous || {}) };
  if (!item || typeof item !== "object") return base;
  const pick = (snake, camel) =>
    item[snake] !== undefined ? item[snake] : item[camel];
  return {
    inLibrary:
      pick("in_library", "inLibrary") !== undefined
        ? Boolean(pick("in_library", "inLibrary"))
        : base.inLibrary,
    galleryId:
      pick("gallery_id", "galleryId") !== undefined
        ? normalizeId(pick("gallery_id", "galleryId"))
        : base.galleryId,
    favorited:
      pick("favorited", "favorited") !== undefined
        ? Boolean(pick("favorited", "favorited"))
        : base.favorited,
    favcat:
      pick("favcat", "favcat") !== undefined
        ? normalizeFavcat(pick("favcat", "favcat"))
        : base.favcat,
    downloadStatus:
      pick("download_status", "downloadStatus") !== undefined
        ? normalizeDownloadStatus(pick("download_status", "downloadStatus"))
        : base.downloadStatus,
  };
}

const DOWNLOAD_LABELS = {
  pending: "排队中",
  queued: "排队中",
  downloading: "下载中",
  success: "已下载",
  failed: "下载失败",
  cancelled: "已取消",
};

/** Badge list for the panel. Pure so the copy stays testable. */
function statusChips(status) {
  const view = mergeStatus(EMPTY_STATUS, status || {});
  const chips = [];
  if (view.inLibrary) chips.push({ key: "library", label: "已在库", tone: "ok" });
  else chips.push({ key: "library", label: "不在库", tone: "muted" });
  if (view.favorited) {
    const suffix = view.favcat === null ? "" : `（分类 ${view.favcat}）`;
    chips.push({ key: "favorite", label: `已收藏${suffix}`, tone: "ok" });
  } else {
    chips.push({ key: "favorite", label: "未收藏", tone: "muted" });
  }
  if (view.downloadStatus && view.downloadStatus !== "success") {
    const label = DOWNLOAD_LABELS[view.downloadStatus] || view.downloadStatus;
    chips.push({
      key: "download",
      label,
      tone: view.downloadStatus === "failed" ? "bad" : "busy",
    });
  }
  return chips;
}

function isUnauthorized(result) {
  return Boolean(result) && Number(result.status) === 401;
}

function safeJsonParse(text) {
  if (typeof text !== "string" || !text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Cloud-first: only a confirmed `successful_gids` entry flips local state. */
function favoriteSucceeded(result, gid) {
  if (!result || typeof result !== "object") return false;
  const successful = Array.isArray(result.successful_gids)
    ? result.successful_gids.map((value) => Number(value))
    : [];
  return successful.includes(Number(gid));
}

function downloadAccepted(result) {
  if (!result || typeof result !== "object") return false;
  if (result.id === undefined || result.id === null) return false;
  return Number.isFinite(Number(result.id));
}

/* ------------------------------------------------------------------- storage */

/** GM_getValue / GM_setValue with a localStorage fallback (keeps tests simple). */
function createGmStore(scope) {
  const host = scope || (typeof globalThis !== "undefined" ? globalThis : {});
  const getValue = host.GM_getValue;
  const setValue = host.GM_setValue;
  if (typeof getValue === "function" && typeof setValue === "function") {
    return {
      get(key, fallback) {
        try {
          const value = getValue(key, fallback);
          return value === undefined ? fallback : value;
        } catch {
          return fallback;
        }
      },
      set(key, value) {
        try {
          setValue(key, value);
        } catch {
          /* storage failures must not break the panel */
        }
      },
    };
  }
  const ls = host.localStorage;
  return {
    get(key, fallback) {
      try {
        const raw = ls && ls.getItem(`gv-companion:${key}`);
        return raw === null || raw === undefined ? fallback : JSON.parse(raw);
      } catch {
        return fallback;
      }
    },
    set(key, value) {
      try {
        if (ls) ls.setItem(`gv-companion:${key}`, JSON.stringify(value));
      } catch {
        /* ignore */
      }
    },
  };
}

function readSettings(store) {
  return {
    base: normalizeBaseUrl(store.get(STORAGE_KEYS.base, "")),
    token: String(store.get(STORAGE_KEYS.token, "") || ""),
  };
}

/* ---------------------------------------------------------------- GM request */

function createGmRequest(scope) {
  const host = scope || (typeof globalThis !== "undefined" ? globalThis : {});
  const gm =
    typeof host.GM_xmlhttpRequest === "function"
      ? host.GM_xmlhttpRequest
      : host.GM && typeof host.GM.xmlHttpRequest === "function"
        ? host.GM.xmlHttpRequest.bind(host.GM)
        : null;
  if (!gm) {
    return () =>
      Promise.reject(new Error("gm_xmlhttprequest_unavailable"));
  }
  return (request) =>
    new Promise((resolve, reject) => {
      gm({
        method: request.method,
        url: request.url,
        headers: request.headers,
        data: request.data,
        timeout: 20000,
        onload: (response) =>
          resolve({
            status: Number(response && response.status) || 0,
            responseText:
              response && typeof response.responseText === "string"
                ? response.responseText
                : "",
          }),
        onerror: () => reject(new Error("network_error")),
        ontimeout: () => reject(new Error("timeout")),
      });
    });
}

/* ---------------------------------------------------------------------- DOM */

const STYLE_ID = "gv-companion-style";

const STYLE_TEXT = `
#gv-companion-panel {
  box-sizing: border-box;
  margin: 8px 0;
  padding: 10px 12px;
  max-width: 100%;
  font: 13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #1f2933;
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
}
#gv-companion-panel * { box-sizing: border-box; }
#gv-companion-panel .gv-head {
  display: flex; align-items: center; gap: 8px; font-weight: 600;
}
#gv-companion-panel .gv-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
#gv-companion-panel .gv-chip {
  padding: 1px 8px; border-radius: 999px; font-size: 12px;
  border: 1px solid #cbd5e1; background: #fff; white-space: nowrap;
}
#gv-companion-panel .gv-chip[data-tone="ok"] { border-color: #16a34a; color: #14532d; background: #f0fdf4; }
#gv-companion-panel .gv-chip[data-tone="muted"] { color: #64748b; }
#gv-companion-panel .gv-chip[data-tone="busy"] { border-color: #2563eb; color: #1e3a8a; background: #eff6ff; }
#gv-companion-panel .gv-chip[data-tone="bad"] { border-color: #dc2626; color: #7f1d1d; background: #fef2f2; }
#gv-companion-panel .gv-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
#gv-companion-panel .gv-actions select,
#gv-companion-panel .gv-form input {
  font: inherit; padding: 3px 6px; border: 1px solid #94a3b8;
  border-radius: 6px; background: #fff; color: inherit; max-width: 100%;
}
#gv-companion-panel .gv-btn {
  font: inherit; padding: 4px 10px; border-radius: 6px; cursor: pointer;
  border: 1px solid #2563eb; background: #2563eb; color: #fff;
}
#gv-companion-panel .gv-btn.gv-secondary { background: #fff; color: #1e3a8a; }
#gv-companion-panel .gv-link { color: #1d4ed8; }
#gv-companion-panel .gv-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
#gv-companion-panel .gv-form label { display: flex; flex-direction: column; gap: 2px; font-size: 12px; min-width: 180px; flex: 1 1 180px; }
#gv-companion-panel .gv-msg { margin: 8px 0 0; font-size: 12px; color: #475569; }
#gv-companion-panel .gv-msg[data-tone="bad"] { color: #b91c1c; }
@media (prefers-color-scheme: dark) {
  #gv-companion-panel {
    color: #e2e8f0; background: #1e293b; border-color: #334155;
  }
  #gv-companion-panel .gv-chip { background: #0f172a; border-color: #334155; }
  #gv-companion-panel .gv-chip[data-tone="ok"] { border-color: #22c55e; color: #bbf7d0; background: #052e16; }
  #gv-companion-panel .gv-chip[data-tone="muted"] { color: #94a3b8; }
  #gv-companion-panel .gv-chip[data-tone="busy"] { border-color: #3b82f6; color: #bfdbfe; background: #172554; }
  #gv-companion-panel .gv-chip[data-tone="bad"] { border-color: #f87171; color: #fecaca; background: #450a0a; }
  #gv-companion-panel .gv-actions select,
  #gv-companion-panel .gv-form input { background: #0f172a; border-color: #475569; color: #e2e8f0; }
  #gv-companion-panel .gv-btn.gv-secondary { background: #0f172a; color: #bfdbfe; }
  #gv-companion-panel .gv-link { color: #93c5fd; }
  #gv-companion-panel .gv-msg { color: #94a3b8; }
  #gv-companion-panel .gv-msg[data-tone="bad"] { color: #fca5a5; }
}
`;

function createElement(doc, tag, attrs, text) {
  const element = doc.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined) continue;
      if (key === "text") element.textContent = String(value);
      else element.setAttribute(key, String(value));
    }
  }
  if (text !== undefined) element.textContent = text;
  return element;
}

function ensureStyle(doc) {
  if (!doc || !doc.head) return;
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE_TEXT;
  doc.head.appendChild(style);
}

function findAnchor(doc) {
  for (const selector of SELECTORS.anchors) {
    const element = doc.querySelector(selector);
    if (element) return element;
  }
  return doc.querySelector(SELECTORS.fallback);
}

/* ---------------------------------------------------------------- companion */

const ERROR_MESSAGES = {
  invalid_base_url: "GalleryVault 地址无效，请检查后重新配置。",
  missing_token: "请填写 GalleryVault API Token。",
  network_error: "无法连接 GalleryVault，请检查地址与网络。",
  timeout: "连接 GalleryVault 超时。",
  gm_xmlhttprequest_unavailable:
    "当前脚本管理器不支持 GM_xmlhttpRequest，请检查用户脚本权限。",
};

function errorMessage(error) {
  const key = error && error.message ? error.message : "";
  return ERROR_MESSAGES[key] || "请求失败，请稍后重试。";
}

/**
 * Mount the companion panel on the current gallery page.
 *
 * @param {object} [options]
 * @param {Document} [options.doc]
 * @param {Location|{pathname:string}} [options.location]
 * @param {object} [options.store]
 * @param {(request:object)=>Promise<{status:number,responseText:string}>} [options.request]
 * @param {object} [options.logger] never receives the API token
 */
function createCompanion(options = {}) {
  const doc =
    options.doc || (typeof document !== "undefined" ? document : null);
  const loc =
    options.location ||
    (typeof window !== "undefined" && window.location ? window.location : null);
  if (!doc || !loc) return null;
  const target = parseGalleryLocation(loc);
  if (!target) return null;

  const store = options.store || createGmStore();
  const request = options.request || createGmRequest();

  const state = {
    mode: "loading", // loading | ready | unconfigured | unauthorized | error
    status: { ...EMPTY_STATUS },
    categories: [],
    message: "",
    messageTone: "",
    busy: false,
    quality: "resample",
    favcat: 0,
    favcatTouched: false,
  };

  let root = null;

  function render() {
    if (!root) return;
    root.textContent = "";
    root.dataset.state = state.mode;
    const children = [];

    const head = createElement(doc, "div", { class: "gv-head" });
    head.appendChild(createElement(doc, "span", null, "GalleryVault"));
    children.push(head);

    if (state.mode === "ready" || state.mode === "loading") {
      const chips = createElement(doc, "div", { class: "gv-chips" });
      for (const chip of statusChips(state.status)) {
        chips.appendChild(
          createElement(
            doc,
            "span",
            { class: "gv-chip", "data-tone": chip.tone, "data-chip": chip.key },
            chip.label,
          ),
        );
      }
      children.push(chips);
      children.push(buildActions());
    }

    if (state.mode === "unconfigured" || state.mode === "unauthorized") {
      children.push(buildConfigForm());
    }

    if (state.message) {
      children.push(
        createElement(
          doc,
          "p",
          { class: "gv-msg", "data-tone": state.messageTone, role: "status" },
          state.message,
        ),
      );
    }

    for (const child of children) root.appendChild(child);
  }

  function buildActions() {
    const actions = createElement(doc, "div", { class: "gv-actions" });

    const quality = createElement(doc, "select", {
      "data-role": "quality",
      "aria-label": "下载质量",
    });
    for (const value of QUAILITIES) {
      const option = createElement(
        doc,
        "option",
        { value },
        value === "original" ? "原图" : "重采样",
      );
      if (value === state.quality) option.selected = true;
      quality.appendChild(option);
    }
    quality.addEventListener("change", () => {
      state.quality = quality.value;
    });
    actions.appendChild(quality);

    actions.appendChild(
      createElement(
        doc,
        "button",
        {
          type: "button",
          class: "gv-btn",
          "data-action": "download",
          disabled: state.busy ? "disabled" : null,
        },
        "下载到 GalleryVault",
      ),
    );

    const favcat = createElement(doc, "select", {
      "data-role": "favcat",
      "aria-label": "收藏分类",
    });
    for (const value of FAVCAT_VALUES) {
      const category = state.categories.find((item) => item.favcat === value);
      const option = createElement(
        doc,
        "option",
        { value: String(value) },
        category && category.name ? `${value} · ${category.name}` : `分类 ${value}`,
      );
      if (value === state.favcat) option.selected = true;
      favcat.appendChild(option);
    }
    favcat.addEventListener("change", () => {
      state.favcat = Number(favcat.value) || 0;
      state.favcatTouched = true;
    });
    actions.appendChild(favcat);

    actions.appendChild(
      createElement(
        doc,
        "button",
        {
          type: "button",
          class: "gv-btn gv-secondary",
          "data-action": "favorite",
          disabled: state.busy ? "disabled" : null,
        },
        "收藏到 GalleryVault",
      ),
    );

    const settings = readSettings(store);
    const link = createElement(
      doc,
      "a",
      {
        class: "gv-link",
        "data-action": "open",
        href: galleryVaultUrl(settings.base, target.gid, target.token),
        target: "_blank",
        rel: "noopener noreferrer",
      },
      "在 GalleryVault 打开",
    );
    actions.appendChild(link);
    return actions;
  }

  function buildConfigForm() {
    const form = createElement(doc, "div", { class: "gv-form" });
    const settings = readSettings(store);

    const baseLabel = createElement(doc, "label", null, "GalleryVault 地址");
    const baseInput = createElement(doc, "input", {
      "data-role": "base",
      type: "url",
      inputmode: "url",
      placeholder: "http://192.168.1.10:8200",
      autocomplete: "off",
      spellcheck: "false",
    });
    baseInput.value = settings.base;
    baseLabel.appendChild(baseInput);
    form.appendChild(baseLabel);

    const tokenLabel = createElement(doc, "label", null, "API Token");
    const tokenInput = createElement(doc, "input", {
      "data-role": "token",
      type: "password",
      autocomplete: "new-password",
      spellcheck: "false",
    });
    tokenLabel.appendChild(tokenInput);
    form.appendChild(tokenLabel);

    form.appendChild(
      createElement(
        doc,
        "button",
        { type: "button", class: "gv-btn", "data-action": "save" },
        "保存并连接",
      ),
    );
    return form;
  }

  function mount() {
    ensureStyle(doc);
    const existing = doc.getElementById(SELECTORS.panelId);
    if (existing) {
      root = existing;
      render();
      return root;
    }
    root = createElement(doc, "div", {
      id: SELECTORS.panelId,
      "data-gid": String(target.gid),
    });
    root.addEventListener("click", onClick);
    const anchor = findAnchor(doc);
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(root, anchor.nextSibling);
    } else if (doc.body) {
      doc.body.insertBefore(root, doc.body.firstChild);
    } else {
      return null;
    }
    render();
    return root;
  }

  function setMessage(text, tone = "") {
    state.message = text;
    state.messageTone = tone;
  }

  async function callApi(spec) {
    const settings = readSettings(store);
    return request(buildApiRequest(settings.base, settings.token, spec));
  }

  async function loadCategories() {
    try {
      const result = await callApi({ method: "GET", path: API.favoriteCategories });
      if (!isUnauthorized(result) && result.status < 400) {
        const data = safeJsonParse(result.responseText);
        if (Array.isArray(data)) {
          state.categories = data
            .filter(
              (item) =>
                item && Number.isInteger(Number(item.favcat)) && Number(item.favcat) >= 0,
            )
            .map((item) => ({
              favcat: Number(item.favcat),
              name: typeof item.name === "string" ? item.name : "",
            }));
        }
      }
    } catch {
      /* category names are cosmetic */
    }
  }

  async function refresh() {
    const settings = readSettings(store);
    if (!settings.base || !settings.token) {
      state.mode = "unconfigured";
      state.message = "首次使用请填写 GalleryVault 地址与 API Token。";
      render();
      return;
    }
    state.mode = state.mode === "ready" ? "ready" : "loading";
    state.busy = true;
    render();
    try {
      const result = await callApi({
        method: "GET",
        path: statusPath([target.gid]),
      });
      if (isUnauthorized(result)) {
        state.mode = "unauthorized";
        setMessage("认证失败：Token 无效或已被撤销，请重新配置。", "bad");
      } else if (result.status >= 400) {
        state.mode = state.mode === "ready" ? "ready" : "error";
        setMessage(`状态查询失败（HTTP ${result.status}）。`, "bad");
      } else {
        const data = safeJsonParse(result.responseText);
        const item = data && Array.isArray(data.items) ? data.items[0] : null;
        state.status = mergeStatus(state.status, item);
        if (!state.favcatTouched && state.status.favcat !== null) {
          state.favcat = state.status.favcat;
        }
        state.mode = "ready";
        setMessage("");
      }
    } catch (error) {
      state.mode = state.mode === "ready" ? "ready" : "error";
      setMessage(errorMessage(error), "bad");
    } finally {
      state.busy = false;
      render();
    }
    if (state.mode === "ready") {
      await loadCategories();
      render();
    }
  }

  async function download() {
    state.busy = true;
    setMessage("正在提交下载任务…");
    render();
    try {
      const result = await callApi({
        method: "POST",
        path: API.downloads,
        body: {
          gid: target.gid,
          token: target.token,
          quality: state.quality,
        },
      });
      if (isUnauthorized(result)) {
        state.mode = "unauthorized";
        setMessage("认证失败：Token 无效或已被撤销，请重新配置。", "bad");
      } else if (result.status >= 400) {
        setMessage(`下载请求失败（HTTP ${result.status}）。`, "bad");
      } else {
        const data = safeJsonParse(result.responseText);
        if (downloadAccepted(data)) {
          state.status = mergeStatus(state.status, {
            download_status: data.status || "pending",
          });
          setMessage("已加入 GalleryVault 下载队列。");
        } else {
          setMessage("下载请求未被接受，请稍后重试。", "bad");
        }
      }
    } catch (error) {
      setMessage(errorMessage(error), "bad");
    } finally {
      state.busy = false;
      render();
    }
  }

  async function favorite() {
    state.busy = true;
    setMessage("正在收藏…");
    render();
    try {
      const result = await callApi({
        method: "POST",
        path: API.favoritesAdd,
        body: {
          gid: target.gid,
          token: target.token,
          target_favcat: state.favcat,
        },
      });
      if (isUnauthorized(result)) {
        state.mode = "unauthorized";
        setMessage("认证失败：Token 无效或已被撤销，请重新配置。", "bad");
      } else if (result.status >= 400) {
        setMessage(`收藏请求失败（HTTP ${result.status}）。`, "bad");
      } else {
        const data = safeJsonParse(result.responseText);
        if (favoriteSucceeded(data, target.gid)) {
          state.status = mergeStatus(state.status, {
            favorited: true,
            favcat: state.favcat,
          });
          setMessage("已收藏到 GalleryVault。");
        } else {
          setMessage("云端收藏未成功，本地状态未更新。", "bad");
        }
      }
    } catch (error) {
      setMessage(errorMessage(error), "bad");
    } finally {
      state.busy = false;
      render();
    }
  }

  function saveSettings() {
    if (!root) return;
    const baseInput = root.querySelector('[data-role="base"]');
    const tokenInput = root.querySelector('[data-role="token"]');
    const base = normalizeBaseUrl(baseInput ? baseInput.value : "");
    const token = tokenInput ? String(tokenInput.value || "").trim() : "";
    if (!base) {
      setMessage("GalleryVault 地址无效，例如 http://192.168.1.10:8200。", "bad");
      render();
      return;
    }
    if (!token) {
      setMessage("请填写 GalleryVault API Token。", "bad");
      render();
      return;
    }
    store.set(STORAGE_KEYS.base, base);
    store.set(STORAGE_KEYS.token, token);
    state.mode = "loading";
    setMessage("");
    render();
    void refresh();
  }

  function onClick(event) {
    const node =
      event.target && event.target.closest
        ? event.target.closest("[data-action]")
        : null;
    if (!node) return;
    const action = node.dataset.action;
    if (action === "open") return;
    event.preventDefault();
    if (state.busy) return;
    if (action === "download") void download();
    else if (action === "favorite") void favorite();
    else if (action === "save") saveSettings();
  }

  return {
    target,
    state,
    mount,
    refresh,
    render,
    destroy() {
      if (root && root.parentNode) root.parentNode.removeChild(root);
      root = null;
    },
    get panel() {
      return root;
    },
  };
}

/** Entry point appended by `userscript/build.mjs`. */
function init() {
  if (typeof document === "undefined") return null;
  const start = () => {
    try {
      const companion = createCompanion();
      if (!companion) return null;
      companion.mount();
      void companion.refresh();
      return companion;
    } catch {
      return null;
    }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
    return null;
  }
  return start();
}

  init();
})();
