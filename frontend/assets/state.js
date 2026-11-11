"use strict";

/**
 * state.js — 全局状态与向后兼容适配层
 * 统一登记初始状态与视图级 timer 注册表，
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
  { key: "language", ns: "language" }, { key: "location", ns: "location" },
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

// 状态初始定义清单
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

// 视图级轮询 timer 注册表：视图写入（如 timers.archive），core.js 的 clearViewTimers 统一清理
const timers = Object.create(null);

const globalScope = typeof window !== "undefined" ? window : globalThis;

// 代理暴露 window.state
globalScope.state = initialManagedState;

// 在全局作用域建立双向属性绑定，兼容历史脚本直接读写全局变量
for (const key of Object.keys(initialManagedState)) {
  if (!(key in globalScope)) {
    Object.defineProperty(globalScope, key, {
      get() {
        return initialManagedState[key];
      },
      set(val) {
        initialManagedState[key] = val;
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
