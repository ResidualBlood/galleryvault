"use strict";

// state.js — 按 FRONTEND_OPTIMIZATION_PLAN Phase 0 收敛
// 所有 sel* / *Timer / dup* / reader* / infinite 等可变状态 + 常用配置
// 加载顺序：core.js → state.js → ... → app.js

const $view = () => document.getElementById("view");
const $topbar = () => document.getElementById("topbar");

const selGalleries = new Set();
let suggestTimer = null;

let infiniteState = null;

let readerKeyHandler = null;
let readerFsActive = false;
let readerFitBeforeFs = "";

const PAGE_SIZES = [5, 30, 50, 100, 200, 500];

let tagFacetCounts = null;

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
let dlTimer = null;

const EH_BASE_URLS = [
  { v: "https://exhentai.org", label: "ExHentai（里站）" },
  { v: "https://e-hentai.org", label: "E-Hentai（外站）" },
];
const EH_CUSTOM = "__custom__";

const FAV_MODES = ["incremental", "monitor_only", "force"];

let favTimer = null;
const selFav = new Set();

const selDup = new Set();
let dupFilter = "all";
let dupPage = 1;
const dupLocallyIgnored = new Set();
const favCatNames = {};

let logTimer = null;

let lastDupStatus = null;

let updatesTimer = null;
const selUpdate = new Set();

const UPD_STATUS_KEYS = {
  pending: "updPending", downloading: "updDownloading", failed: "updFailed", ignored: "updIgnored",
};

let dupGalFilter = "all";
let dupGalCache = null;
const DUPGAL_STATUSES = { open: "dupGalOpen", dismissed: "dupGalDismissed" };

const selRecycle = new Set();
const selIntegrity = new Set();
window.selRecycle = selRecycle;
window.selIntegrity = selIntegrity;

// 未来扩展 viewState
// app.viewState = app.viewState || {};
