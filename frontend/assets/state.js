"use strict";

/**
 * state.js — 全局状态托管与向后兼容适配层
 * 将原有散落无序的全局状态注册接入 Store 统一托管，
 * 同时维持原有全局变量名与 window.state 访问能力，保证历史视图无缝过渡。
 */

const $view = () => document.getElementById("view");
const $topbar = () => document.getElementById("topbar");

// 常量定义
const PAGE_SIZES = [5, 30, 50, 100, 200, 500];

const CATEGORY_LABELS = {
  doujinshi: "catDoujinshi", manga: "catManga", artistcg: "catArtistcg", gamecg: "catGamecg",
  western: "catWestern", "non-h": "catNonH", image_set: "catImageSet", cosplay: "catCosplay",
  asianporn: "catAsianporn", misc: "catMisc", other: "catMisc", deleted: "catDeleted",
};

const TAG_NAMESPACES = [
  { key: "all", ns: "" }, { key: "tag", ns: "other" }, { key: "artist", ns: "artist" },
  { key: "character", ns: "character" }, { key: "parody", ns: "parody" }, { key: "group", ns: "group" },
  { key: "female", ns: "female" }, { key: "male", ns: "male" },
  { key: "language", ns: "language" },
];

const DL_STATUSES = ["all", "pending", "downloading", "success", "failed", "cancelled"];

const EH_BASE_URLS = [
  { v: "https://exhentai.org", label: "ExHentai（里站）" },
  { v: "https://e-hentai.org", label: "E-Hentai（外站）" },
];
const EH_CUSTOM = "__custom__";

const FAV_MODES = ["incremental", "monitor_only", "force"];

const UPD_STATUS_KEYS = {
  pending: "updPending", downloading: "updDownloading", failed: "updFailed", ignored: "updIgnored",
};

const DUPGAL_STATUSES = { open: "dupGalOpen", dismissed: "dupGalDismissed" };

// 状态初始定义清单（统一注册接入 Store）
const initialManagedState = {
  selGalleries: new Set(),
  selDiscover: new Set(),
  suggestTimer: null,
  infiniteState: null,
  readerKeyHandler: null,
  readerFsActive: false,
  readerFitBeforeFs: "",
  tagFacetCounts: null,
  dlTimer: null,
  favTimer: null,
  selFav: new Set(),
  selDup: new Set(),
  dupFilter: "all",
  dupPage: 1,
  dupLocallyIgnored: new Set(),
  favCatNames: {},
  logTimer: null,
  lastDupStatus: null,
  updatesTimer: null,
  selUpdate: new Set(),
  dupGalFilter: "all",
  dupGalCache: null,
  dupXgidCache: null,
  dupXgidReady: false,
  dupXgidPage: 1,
  dupXgidFilter: "all",
  selXgid: new Set(),
  dupXgidLocallyIgnored: new Set(),
  selRecycle: new Set(),
  selIntegrity: new Set(),
  slideshowTimer: null,
};

// 获取或初始化 Store 实例
const globalScope = typeof window !== "undefined" ? window : globalThis;
const storeInstance = globalScope.store || (typeof Store !== "undefined" ? new Store() : null);

if (storeInstance) {
  for (const [key, val] of Object.entries(initialManagedState)) {
    if (storeInstance.getState(key) === undefined) {
      storeInstance.setState(key, val, { silent: true });
    }
  }
}

// 代理暴露 window.state
globalScope.state = storeInstance ? storeInstance.state : initialManagedState;

// 在全局作用域建立双向属性绑定，兼容历史脚本直接读写全局变量
for (const key of Object.keys(initialManagedState)) {
  if (!(key in globalScope)) {
    Object.defineProperty(globalScope, key, {
      get() {
        return storeInstance ? storeInstance.getState(key) : initialManagedState[key];
      },
      set(val) {
        if (storeInstance) {
          storeInstance.setState(key, val);
        } else {
          initialManagedState[key] = val;
        }
      },
      configurable: true,
      enumerable: true,
    });
  }
}

// 显式挂载特定别名
globalScope.selRecycle = globalScope.selRecycle || initialManagedState.selRecycle;
globalScope.selIntegrity = globalScope.selIntegrity || initialManagedState.selIntegrity;
globalScope.selXgid = globalScope.selXgid || initialManagedState.selXgid;
