"use strict";

const I18N = {
  en: {
    loginSub: "Password required to access the local library.",
    searchPlaceholder: "Search library...",
    username: "Username",
    password: "Password", login: "Login", wrong: "Wrong password, please retry.",
    mustChange: "Default password in use — please change it now.",
    changePassword: "Change password", currentPassword: "Current password",
    newPassword: "New password", changePwOk: "Password changed",
    pwDefault: "Using the default password", pwConfigured: "Password configured",
    authLogin: "Account login", authRequired: "Require login",
    translationUpdate: "Translation auto-update",
    translationInterval: "Update interval (minutes, 0 = off)",
    forceUpdate: "Update now", translationStatus: "Translation status",
    transUpdated: "Translations updated",
    testTelegram: "Send test message",
    browse: "Browse", library: "Library", tags: "Tags", downloads: "Tasks",
    downloadsSub: "Download tasks and tag synchronization.",
    favorites: "Favorites", history: "History", settings: "Settings", logout: "Logout",
    scan: "Scan library", random: "Random", readNow: "Read now", syncTags: "Sync tags",
    tagSection: "Tags", pagesSection: "Pages", details: "Details", prev: "Previous",
    next: "Next", allPages: "All pages", clearHistory: "Clear history",
    refreshFolders: "Refresh folder names", checkDownload: "Check & download",
    notConfigured: "Folders not configured or not synced yet.",
    save: "Save", testLogin: "Test login", cookieSet: "set (not shown)", cookieUnset: "not set",
    filterAll: "All", filterPending: "Pending", filterSuccess: "Success", filterFailed: "Failed",
    cancel: "Cancel", noTasks: "No download tasks.", noGalleries: "No matching galleries, click Scan.",
    noHistory: "No reading history.", noTags: "No local tags found.",
    progress: "progress", loading: "Loading…", language: "中文", latest: "Latest",
    enabled: "Enabled", mode: "Mode", intervalMin: "Interval (min)",
    syncFavcats: "Sync folder names", checkNow: "Check now", saveOk: "Saved",
    checkAll: "Check all folders", favLocal: "local", favCloud: "cloud",
    favcatTag: "folder", favDate: "fav:", backToGallery: "back to gallery", postedDate: "posted:",
    unfavorite: "Unfavorite", unfavoriteFail: "Cannot unfavorite", unfavorited: "Removed from favorites",
    unfavoritedLocal: "Cloud removal failed; local record removed", confirmUnfavorite: "Remove this gallery from favorites?",
    favManage: "Manage duplicates", favManageTitle: "Favorites — duplicates",
    favManageSub: "Scan favorite folders for duplicate galleries (same work in different versions, e.g. DL / uncensored / language re-uploads).",
    favListSub: "Galleries in this favorite folder. Select and download or remove from favorites.",
    favDl: "Download selected", favDlQueued: "Download queued", favDlSkip: "already local/skipped",
    favRemove: "Remove from favorites", confirmFavRemove: "Remove selected from favorites?",
    dupScan: "Scan duplicates", dupUnfav: "Unfavorite", dupUnfavDelete: "Unfavorite & delete local",
    dupFilterAll: "All", dupFilterLocal: "Local only", dupFilterCloud: "Cloud only",
    dupHint: "Press “Scan duplicates” to compare all favorite galleries.",
    dupNone: "No duplicate groups found.",
    dupFound: "Found", dupGroups: "groups", dupItems: "items",
    confirmDupUnfav: "Remove selected from favorites?", confirmDupDelete: "Remove from favorites and delete local copies?",
    dupIgnore: "Ignore", dupUnignore: "Restore", dupIgnored: "Ignored", dupIgnoredOk: "Group ignored",
    dupUnignoredOk: "Group restored",
    dupIgnoreSel: "Ignore selected", dupIgnoredPage: "Ignored items", dupIgnoredSub: "Groups you marked as not-duplicates. Select and restore to re-enable them.",
    dupUnignoreSel: "Restore selected",
    favCount: "Galleries (cloud/local)", favSize: "Size (cloud/local)",
    favModeIncremental: "Incremental", favModeMonitorOnly: "Monitor only", favModeForce: "Force",
    libraryRoots: "Library roots (read-only)", baseUrl: "Base URL",
    cookieId: "ipb_member_id", cookieHash: "ipb_pass_hash", cookieIgneous: "igneous",
    libraryRootsHint: "Read-only roots holding your existing archives (Ehviewer exports, CBZ…). New downloads never land here.",
    downloadRootHint: "Download directory: newly downloaded ExHentai galleries are stored here and scanned automatically.",
    cookiesNote: "Cookies are never displayed after saving.",
    proxyHttp: "HTTP proxy", proxySocks5: "SOCKS5 proxy",
    downloadRoot: "Download root", concurrency: "Concurrency", quality: "Quality",
    qualityOriginal: "Original (原图)", qualityResample: "Resample (普通)",
    catDoujinshi: "Doujinshi", catManga: "Manga", catArtistcg: "Artist CG", catGamecg: "Game CG",
    catWestern: "Western", catNonH: "Non-H", catImageSet: "Image Set", catCosplay: "Cosplay",
    catAsianporn: "Asian Porn", catMisc: "Misc", catDeleted: "Deleted",
    useHah: "Use H@H", titleDisplay: "Title display",
    botToken: "Bot token (leave blank to keep)", chatIds: "Chat IDs (comma separated)",
    allowedIds: "Allowed user IDs (comma separated)",
    autoSyncTags: "Auto sync tags", tagSyncInterval: "Tag sync interval (seconds)",
    tagSyncConcurrency: "Tag sync concurrency",
    generateThumbnails: "Generate thumbnails", genThumbs: "Generate now", syncAllTags: "Sync tags now",
    pollDefault: "Default poll interval (minutes)",
    favHint: "Enable folders to monitor; per-folder settings below.",
    testExhentai: "Test ExHentai login", cancelDl: "Cancel", error: "Error",
    retry: "Retry", retrySelected: "Retry selected", selectAll: "Select all",
    deleteDl: "Delete",
    downloading: "downloading", perPage: "per page",
    delete: "Delete", deleteGallery: "Delete gallery", deleteFiltered: "Delete filtered",
    deleteFiles: "Also delete files on disk", confirmDelete: "Delete this gallery?",
    confirmDeleteFiltered: "Delete all matching galleries?", deleted: "Deleted",
    select: "Select", clearSel: "Clear selection", deleteSel: "Delete selected",
    confirmDeleteSel: "Delete selected galleries?",
    tasks: "Background tasks", scanning: "Scanning library",     tagSyncing: "Syncing tags", thumbs: "Generating thumbnails",
    scanDone: "Scan complete", tagSyncDone: "Tag sync complete", thumbsDone: "Thumbnails complete",
    metaDone: "Metadata sync complete", completed: "done", scanned: "scanned", persisted: "persisted",
    favMetaSync: "Syncing favorite metadata", favMetaApply: "Applying favorite metadata", applied: "applied",
    tagSyncFromCache: "Tags updated from cache", tagSyncFromNetwork: "Tags synced from ExHentai",
    noTasks: "No background tasks", dlTasks: "Download tasks",
    favcatTitle: "Favorites folders", favcatSub: "ExHentai favorites monitoring & auto download.",
    settingsSub: "Library, connection and background tasks.",
    groups: { all: "All", tag: "Tags", artist: "Artists", character: "Characters", parody: "Parodies", group: "Groups", female: "Female", male: "Male", language: "Languages" },
    ns: { artist: "Artist", character: "Character", parody: "Parody", group: "Group", language: "Language", category: "Category", misc: "Tag", other: "Tag", female: "Female", male: "Male", mixed: "Mixed" },
  },
  zh: {
    loginSub: "需要密码才能访问本地画廊。",
    searchPlaceholder: "搜索画廊…",
    username: "用户名",
    password: "密码", login: "登录", wrong: "密码错误，请重试。",
    mustChange: "正在使用默认密码，请立即修改。",
    changePassword: "修改密码", currentPassword: "当前密码",
    newPassword: "新密码", changePwOk: "密码已修改",
    pwDefault: "正在使用默认密码", pwConfigured: "已配置密码",
    authLogin: "账户登录", authRequired: "需要登录",
    translationUpdate: "翻译自动更新",
    translationInterval: "更新间隔（分钟，0=关闭）",
    forceUpdate: "立即更新", translationStatus: "翻译状态",
    transUpdated: "翻译已更新",
    testTelegram: "发送测试消息",
    browse: "浏览", library: "画廊库", tags: "标签", downloads: "任务",
    downloadsSub: "下载任务与标签同步。",
    favorites: "收藏夹", history: "历史", settings: "设置", logout: "退出",
    scan: "扫描库", random: "随机", readNow: "开始阅读", syncTags: "同步标签",
    tagSection: "标签", pagesSection: "页面", details: "详情", prev: "上一页",
    next: "下一页", allPages: "所有页面", clearHistory: "清空历史",
    refreshFolders: "刷新文件夹名称", checkDownload: "检查并下载",
    notConfigured: "尚未配置或同步收藏夹。",
    save: "保存", testLogin: "测试登录", cookieSet: "已设置（不回显）", cookieUnset: "未设置",
    filterAll: "全部", filterPending: "进行中", filterSuccess: "成功", filterFailed: "失败",
    cancel: "取消", noTasks: "暂无下载任务。", noGalleries: "没有匹配的画廊，请点击扫描。",
    noHistory: "暂无阅读历史。", noTags: "未找到本地标签。",
    progress: "进度", loading: "加载中…", language: "EN", latest: "最新",
    enabled: "启用", mode: "模式", intervalMin: "间隔（分钟）",
    syncFavcats: "同步收藏夹名称", checkNow: "立即检查", saveOk: "已保存",
    favCount: "画廊数（云端/本地）", favSize: "大小（云端/本地）",
    favModeIncremental: "增量下载", favModeMonitorOnly: "仅监控", favModeForce: "强制下载",
    libraryRoots: "库根目录（只读）", baseUrl: "Base URL",
    cookieId: "ipb_member_id", cookieHash: "ipb_pass_hash", cookieIgneous: "igneous",
    libraryRootsHint: "只读库根目录：存放已有的画廊归档（Ehviewer 导出、CBZ 等）。新下载的画廊不会放到这里。",
    downloadRootHint: "下载目录：新从 ExHentai 下载的画廊存放于此，并自动纳入扫描。",
    cookiesNote: "Cookie 保存后不会回显。",
    proxyHttp: "HTTP 代理", proxySocks5: "SOCKS5 代理",
    downloadRoot: "下载根目录", concurrency: "并发数", quality: "画质",
    qualityOriginal: "原图 (Original)", qualityResample: "重采样 (Resample)",
    catDoujinshi: "同人志", catManga: "漫画", catArtistcg: "画师CG", catGamecg: "游戏CG",
    catWestern: "西方", catNonH: "非H", catImageSet: "图集", catCosplay: "Cosplay",
    catAsianporn: "亚洲色情", catMisc: "杂项", catDeleted: "已删除",
    useHah: "使用 H@H", titleDisplay: "标题显示",
    botToken: "Bot Token（留空保持不变）", chatIds: "Chat ID（逗号分隔）",
    allowedIds: "允许的用户 ID（逗号分隔）",
    autoSyncTags: "自动同步标签", tagSyncInterval: "标签同步间隔（秒）",
    tagSyncConcurrency: "标签同步并发",
    generateThumbnails: "生成缩略图", genThumbs: "立即生成", syncAllTags: "立即同步标签",
    pollDefault: "默认轮询间隔（分钟）",
    favHint: "勾选要监控的收藏夹；各收藏夹设置见下表。",
    testExhentai: "测试 ExHentai 登录", cancelDl: "取消任务", error: "错误",
    retry: "重试", retrySelected: "重试所选", selectAll: "全选",
    deleteDl: "删除",
    downloading: "下载中", perPage: "每页",
    delete: "删除", deleteGallery: "删除画廊", deleteFiltered: "删除筛选结果",
    unfavorite: "取消收藏", unfavoriteFail: "无法取消收藏", unfavorited: "已取消收藏",
    unfavoritedLocal: "云端移除失败，仅移除本地记录", confirmUnfavorite: "确定从收藏夹移除该画廊？",
    favManage: "收藏夹管理", favManageTitle: "收藏夹管理 — 查重",
    favManageSub: "扫描收藏夹中重复的画廊（同一作品的不同版本，如 DL 版 / 无修正 / 不同语言搬运）。",
    checkAll: "立即检查所有", favLocal: "本地", favCloud: "云端",
    favcatTag: "收藏夹", favDate: "收藏", backToGallery: "返回画廊", postedDate: "发布于",
    favListSub: "该收藏夹内的画廊。勾选后可下载或从收藏移除。",
    favDl: "下载所选", favDlQueued: "已加入下载", favDlSkip: "已本地/跳过",
    favRemove: "移除收藏", confirmFavRemove: "将所选从收藏夹移除？",
    dupScan: "开始扫描重复画廊", dupUnfav: "取消收藏", dupUnfavDelete: "取消收藏并删除已下载",
    dupFilterAll: "全部", dupFilterLocal: "只显示本地", dupFilterCloud: "只显示云端",
    dupHint: "点击“开始扫描重复画廊”对比所有收藏的画廊。",
    dupNone: "未发现重复画廊。",
    dupFound: "发现", dupGroups: "组重复", dupItems: "项",
    confirmDupUnfav: "将所选从收藏夹移除？", confirmDupDelete: "将所选从收藏夹移除并删除本地副本？",
    dupIgnore: "忽略", dupUnignore: "恢复", dupIgnored: "已忽略", dupIgnoredOk: "已忽略该组",
    dupUnignoredOk: "已恢复该组",
    dupIgnoreSel: "忽略所选", dupIgnoredPage: "已忽略项目", dupIgnoredSub: "你标记为不重复的组。勾选后点击「恢复所选」重新纳入查重。",
    dupUnignoreSel: "恢复所选",
    deleteFiles: "同时删除磁盘文件", confirmDelete: "确定删除此画廊？",
    confirmDeleteFiltered: "确定删除所有匹配的画廊？", deleted: "已删除",
    select: "选择", clearSel: "清除选择", deleteSel: "删除所选",
    confirmDeleteSel: "确定删除所选画廊？",
    tasks: "后台任务", scanning: "扫描库中", tagSyncing: "同步标签中", thumbs: "生成缩略图中",
    scanDone: "扫描完成", tagSyncDone: "标签同步完成", thumbsDone: "缩略图完成",
    metaDone: "元数据同步完成", completed: "已完成", scanned: "扫描", persisted: "入库",
    favMetaSync: "同步收藏元数据", favMetaApply: "应用收藏元数据", applied: "已应用",
    tagSyncFromCache: "标签已从缓存更新", tagSyncFromNetwork: "标签已从 ExHentai 同步",
    noTasks: "无后台任务", dlTasks: "下载任务",
    favcatTitle: "收藏夹监控", favcatSub: "ExHentai 收藏夹监控与自动下载。",
    settingsSub: "本地库、连接与后台任务。",
    groups: { all: "全部", tag: "标签", artist: "作者", character: "角色", parody: "原作", group: "社团", female: "女性", male: "男性", language: "语言" },
    ns: { artist: "作者", character: "角色", parody: "原作", group: "社团", language: "语言", category: "分类", misc: "标签", other: "标签", female: "女性", male: "男性", mixed: "男女" },
  },
};

const app = {
  authenticated: false, settings: null, session: {}, view: "browse", params: {}, query: {},
  lang: (localStorage.getItem("gv_lang") === "en" ? "en" : "zh"),
};

const $view = () => document.getElementById("view");
const $topbar = () => document.getElementById("topbar");

const selGalleries = new Set();
let suggestTimer = null;

function renderCardCheckboxes() {
  document.querySelectorAll(".gc-check input").forEach(cb => {
    cb.addEventListener("change", () => {
      const id = parseInt(cb.getAttribute("data-gallery-id"), 10);
      if (cb.checked) selGalleries.add(id); else selGalleries.delete(id);
      const btn = document.querySelector('[data-action="sel-delete"]');
      if (btn) btn.textContent = `${t("deleteSel")}${selGalleries.size ? ` (${selGalleries.size})` : ""}`;
    });
  });
  document.querySelectorAll('.gc-check input[data-fav-gid]').forEach(cb => {
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-fav-gid"), 10);
      if (cb.checked) selFav.add(gid); else selFav.delete(gid);
      const update = () => {
        document.querySelectorAll('[data-action="favlist-download"], [data-action="favlist-unfav"]').forEach(b => {
          const base = b.getAttribute("data-action") === "favlist-download" ? t("favDl") : t("favRemove");
          b.textContent = base + (selFav.size ? ` (${selFav.size})` : "");
        });
      };
      update();
    });
  });
  document.querySelectorAll('#dup-groups input[data-dup-gid]').forEach(cb => {
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-dup-gid"), 10);
      if (cb.checked) selDup.add(gid); else selDup.delete(gid);
      updateDupButtons();
    });
  });
}

function t(key) { return (I18N[app.lang] && I18N[app.lang][key]) || I18N.en[key] || key; }
function nsLabel(ns) { return (I18N[app.lang].ns && I18N[app.lang].ns[ns]) || ns; }
function groupLabel(key) { return (I18N[app.lang].groups && I18N[app.lang].groups[key]) || key; }
function tagText(tag) { return app.lang === "zh" ? (tag.display || tag.name) : tag.name; }
function updateLangButton() {
  const b = document.querySelector('[data-action="toggle-lang"]');
  if (b) b.textContent = t("language");
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
}

function updateBanner() {
  const el = document.getElementById("banner");
  if (!el) return;
  if (app.authenticated && app.session.must_change_password) {
    el.hidden = false;
    el.innerHTML = `<span>${esc(t("mustChange"))}</span> <a class="primary" href="#/settings">${esc(t("changePassword"))}</a>`;
  } else {
    el.hidden = true;
    el.innerHTML = "";
  }
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

async function api(method, path, body) {
  const opts = { method, credentials: "include", headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

async function checkAuth() {
  try {
    const session = await api("GET", "/api/auth/session");
    app.authenticated = true;
    app.session = session || {};
    $topbar().hidden = false;
    updateBanner();
    // Normalise the address bar: after logging in the SPA is served at /login
    // (the middleware redirect target) but the app lives at "/"; rewrite the
    // path so the URL reads e.g. /#/browse instead of /login#/browse.
    if (location.pathname.endsWith("/login")) {
      history.replaceState(null, "", "/" + location.hash);
    }
    if (!location.hash || location.hash === "#/" || location.hash === "#/login") {
      location.hash = app.session.must_change_password ? "#/settings" : "#/browse";
    }
    router();
  } catch (_) {
    app.authenticated = false;
    app.session = {};
    $topbar().hidden = true;
    renderLogin();
  }
}

async function doLogin(password) {
  await fetch("/login", {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "password=" + encodeURIComponent(password || ""),
  });
  await checkAuth();
  if (!app.authenticated) toast(t("wrong"));
}

async function doLogout() {
  await fetch("/logout", { method: "POST", credentials: "include" });
  app.authenticated = false;
  $topbar().hidden = true;
  location.hash = "";
  renderLogin();
}

function parseHash() {
  let h = location.hash.replace(/^#/, "");
  if (!h) h = "/browse";
  const [path, qs] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  app.view = parts[0] || "browse";
  app.params = {};
  if (app.view === "gallery" || app.view === "reader") {
    app.params.id = /^\d+$/.test(parts[1] || "") ? parts[1] : "";
  }
  if (app.view === "reader") app.params.page = /^\d+$/.test(parts[2] || "") ? parts[2] : "0";
  if (app.view === "favorites") {
    if (parts[1] === "manage") { app.view = "favmanage"; }
    else if (parts[1] === "ignored") { app.view = "favignored"; }
    else if (/^\d+$/.test(parts[1] || "")) { app.view = "favlist"; app.params.id = parts[1]; }
  }
  app.query = {};
  if (qs) for (const kv of qs.split("&")) {
    const [k, v] = kv.split("=");
    try { app.query[decodeURIComponent(k)] = decodeURIComponent(v || ""); }
    catch (e) { app.query[k.replace(/%/g, "")] = (v || "").replace(/%/g, ""); }
  }
}

function navHash(view, params = {}, query = {}) {
  let p = "/" + view;
  if (view === "favlist") { p = "/favorites/" + (params.id || app.params.id); }
  else if (params.id) p += "/" + params.id;
  if (view === "reader") p += "/" + (params.page || 0);
  const q = Object.entries(query).filter(([, v]) => v !== "" && v != null)
    .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&");
  return "#" + p + (q ? "?" + q : "");
}

function router() {
  parseHash();
  updateLangButton();
  updateBanner();
  if (!app.authenticated) { renderLogin(); return; }
  if (app.view !== "library") selGalleries.clear();
  if (app.view !== "favorites" && app.view !== "favlist" && favTimer) { clearInterval(favTimer); favTimer = null; }
  if (app.view !== "downloads" && dlTimer) { clearInterval(dlTimer); dlTimer = null; }
  if (app.view !== "favlist") selFav.clear();
  if (app.view !== "favmanage" && app.view !== "favignored") { selDup.clear(); }
  switch (app.view) {
    case "browse": renderBrowse(); break;
    case "library": renderLibrary(); break;
    case "gallery": renderGallery(); break;
    case "reader": renderReader(); break;
    case "tags": renderTags(); break;
    case "history": renderHistory(); break;
    case "downloads": renderDownloads(); break;
    case "settings": renderSettings(); break;
    case "favorites": renderFavorites(); break;
    case "favmanage": renderFavManage(); break;
    case "favignored": renderFavIgnored(); break;
    case "favlist": renderFavList(); break;
    default: renderBrowse();
  }
  bindTagSuggest();
  bindReaderKeys();
}

function renderLogin() {
  $view().innerHTML = `
    <div class="login-wrap"><div class="panel">
      <p class="eyebrow">PRIVATE LIBRARY</p>
      <h1>GalleryVault</h1>
      <p class="sub">${esc(t("loginSub"))}</p>
      <form data-action="login">
        <label>${esc(t("password"))}<input name="password" type="password" autocomplete="current-password" autofocus></label>
        <button class="primary" type="submit">${esc(t("login"))}</button>
      </form>
    </div></div>`;
}

function nsClass(ns) {
  return "nst-" + (ns && ["artist","character","parody","group","language","category","female","male","mixed","other","misc"].includes(ns) ? ns : "misc");
}

const CATEGORY_LABELS = {
  doujinshi: "catDoujinshi", manga: "catManga", artistcg: "catArtistcg", gamecg: "catGamecg",
  western: "catWestern", "non-h": "catNonH", image_set: "catImageSet", cosplay: "catCosplay",
  asianporn: "catAsianporn", misc: "catMisc", other: "catMisc", deleted: "catDeleted",
};

function catLabel(c) { return t(CATEGORY_LABELS[c] || "catMisc"); }

function galleryCard(it) {
  const cat = esc(catLabel(it.category));
  return `<div class="gc-wrap">
    <a class="gc" href="${navHash("gallery", { id: it.id })}">
      <div class="gc-cover">
        ${it.cover_url ? `<img loading="lazy" src="${it.cover_url}" alt="">` : `<span class="badge">no cover</span>`}
        <span class="gc-cat">${cat}</span>
        <span class="gc-pages">${it.page_count} P</span>
      </div>
      <div class="gc-title">${esc(it.title)}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-gallery-id="${it.id}"${selGalleries.has(it.id) ? " checked" : ""}></label>
  </div>`;
}

async function galleryGrid(container, page, extraQuery) {
  const pageSize = extraQuery && extraQuery.page_size ? extraQuery.page_size : (app.query.page_size || 20);
  const q = Object.assign({ page, page_size: pageSize }, extraQuery || {});
  delete q.page_size;
  q.page_size = pageSize;
  const qs = Object.entries(q).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
  const data = await api("GET", `/api/galleries?${qs}`);
  if (container == null) return data;
  const el = document.getElementById(container);
  if (!el) return data;
  if (!data.items.length) { el.innerHTML = `<p>${esc(t("noGalleries"))}</p>`; }
  else { el.innerHTML = `<div class="grid gc-grid">` + data.items.map(galleryCard).join("") + `</div>`; }
  return data;
}

const PAGE_SIZES = [5, 20, 50, 100];

function pageSizeSelect(current, view) {
  return `<select class="page-size" data-action="page-size" data-view="${view}" aria-label="page size">
    ${PAGE_SIZES.map(n => `<option value="${n}"${String(n) === String(current) ? " selected" : ""}>${n}</option>`).join("")}
  </select>`;
}

function gridPager(elId, data, buildQuery) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const last = Math.max(1, Math.ceil(data.total / data.page_size));
  const link = (p, label) =>
    `<a class="page-link" href="${navHash(app.view, {}, buildQuery(p))}">${label}</a>`;
  const parts = [];
  if (data.page > 1) parts.push(link(data.page - 1, "<"));
  for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
    parts.push(p === data.page ? `<strong class="cur">${p}</strong>` : link(p, String(p)));
  }
  if (data.page < last) parts.push(link(data.page + 1, ">"));
  el.innerHTML =
    `<span class="muted">${data.page}/${last}</span> ` +
    parts.join(" ") +
    ` · ${pageSizeSelect(data.page_size, app.view)}`;
}

async function renderBrowse() {
  $view().innerHTML = `
    <header><p class="eyebrow">GALLERYVAULT</p><h1>${esc(t("browse"))}</h1></header>
    <form class="toolbar" data-action="browse-search">
      <div class="search-box">
        <input name="q" value="" placeholder="${esc(t("searchPlaceholder"))}" autocomplete="off">
        <div id="tag-suggest" class="tag-suggest" hidden></div>
      </div>
      <button class="primary" type="submit">${esc(t("library"))}</button>
      <button class="secondary big" data-action="random" type="button">🎲 ${esc(t("random"))}</button>
    </form>
    <section>
      <h2>${esc(t("latest"))} <span class="muted" id="browse-total"></span></h2>
      <div id="browse-grid"><p>${esc(t("loading"))}</p></div>
      <div class="pages pager" id="browse-pager"></div>
    </section>
    <section id="task-progress" class="task-progress" hidden>
      <h2>${esc(t("tasks"))}</h2>
      <div id="task-progress-body"></div>
    </section>
    <section>
      <h2>${esc(t("tags"))}</h2>
      <div id="browse-ns" class="ns-strip"></div>
    </section>`;
  try {
    const [data, tagData] = await Promise.all([
      galleryGrid("browse-grid", app.query.page || "1", { page_size: app.query.page_size || 20 }),
      api("GET", "/api/tags/search?page=1&page_size=1").catch(() => null),
    ]);
    const totalEl = document.getElementById("browse-total");
    if (totalEl && data) totalEl.textContent = `· ${data.total}`;
    gridPager("browse-pager", data, p => ({ ...(p > 1 ? { page: p } : {}), page_size: app.query.page_size || 20 }));
    const strip = document.getElementById("browse-ns");
    if (strip && tagData) {
      const counts = {};
      for (const f of tagData.facets || []) counts[f.namespace] = f.total;
      strip.innerHTML = TAG_NAMESPACES
        .filter(g => g.ns && counts[g.ns])
        .map(g => `<a class="pill" href="${navHash("tags", {}, { ns: g.ns })}">${esc(groupLabel(g.key))} <b>${counts[g.ns]}</b></a>`)
        .join("");
    }
    pollTaskProgress();
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function renderLibrary() {
  const page = app.query.page || "1";
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  const filterPill = tags
    ? `<span class="tag">${esc(tags)} <a class="tag-x" data-action="clear-tag" href="#">×</a></span>` : "";
  const selCount = selGalleries.size;
  $view().innerHTML = `
    <header><p class="eyebrow">LOCAL LIBRARY</p><h1>${esc(t("library"))}</h1></header>
    <form class="toolbar" data-action="library-search">
      <div class="search-box">
        <input name="q" value="${esc(q)}" placeholder="${esc(t("searchPlaceholder"))}" autocomplete="off">
        <div id="tag-suggest" class="tag-suggest" hidden></div>
      </div>
      <select name="category">
        <option value="">All categories</option>
        ${["doujinshi","manga","artistcg","gamecg","western","non-h","image_set","cosplay","asianporn","misc","deleted"].map(c => `<option value="${c}" ${c === category ? "selected" : ""}>${esc(catLabel(c))}</option>`).join("")}
      </select>
      <button class="primary" type="submit">${esc(t("library"))}</button>
      <button class="secondary" data-action="scan" type="button">${esc(t("scan"))}</button>
      <button class="secondary" data-action="sel-clear" type="button">${esc(t("clearSel"))}</button>
      <button class="secondary danger" data-action="sel-delete" type="button">${esc(t("deleteSel"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary danger" data-action="delete-filtered" type="button">${esc(t("deleteFiltered"))}</button>
    </form>
    <div class="filters">${filterPill}</div>
    <div id="lib-grid"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="lib-pager"></div>`;
  try {
    const extra = { page_size: app.query.page_size || 20 };
    if (q) extra.q = q;
    if (category) extra.category = category;
    if (tags) extra.tags = tags;
    const data = await galleryGrid("lib-grid", page, extra);
    renderCardCheckboxes();
    gridPager("lib-pager", data, p => ({ ...(q ? { q } : {}), ...(category ? { category } : {}), ...(tags ? { tags } : {}), ...(p > 1 ? { page: p } : {}), page_size: app.query.page_size || 20 }));
    bindTagSuggest();
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function renderGallery() {
  const id = app.params.id;
  $view().innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    const g = await api("GET", `/api/galleries/${id}`);
    let progress = { current_page: 0, total_pages: g.page_count };
    try { progress = await api("GET", `/api/galleries/${id}/progress`); } catch (_) {}
    const order = ["parody", "character", "group", "artist", "language", "category", "misc"];
    const byNs = {};
    for (const tg of (g.tags || [])) (byNs[tg.namespace] = byNs[tg.namespace] || []).push(tg);
    const nsList = Object.keys(byNs).sort((a, b) => order.indexOf(a) - order.indexOf(b));
    const tagHtml = nsList.map(ns => `
      <div class="tag-group"><strong>${esc(nsLabel(ns))}</strong><div class="tag-list">
        ${byNs[ns].map(tg => `<a class="tag ${nsClass(tg.namespace)}" href="${navHash("library", {}, { tags: `${tg.namespace}:${tg.name}` })}">${esc(tagText(tg))}</a>`).join("")}
      </div></div>`).join("");
    const thumbsAll = g.pages || [];
    const perPage = parseInt(app.query.page_size || "20", 10);
    const totalPages = Math.max(1, Math.ceil(thumbsAll.length / perPage));
    const thumbPage = Math.min(Math.max(parseInt(app.query.page || "1", 10), 1), totalPages);
    const pageStart = (thumbPage - 1) * perPage;
    const thumbsVisible = thumbsAll.slice(pageStart, pageStart + perPage);
    const thumbs = thumbsVisible.map(p => `
      <a class="thumb" href="${navHash("reader", { id, page: p.index })}">
        <img loading="lazy" src="/api/galleries/${id}/thumb/${p.index}" alt="Page ${p.index + 1}">
      </a>`).join("");
    const thumbPagerParts = [];
    if (thumbPage > 1) {
      thumbPagerParts.push(`<a class="page-link" href="${navHash("gallery", { id }, { page: thumbPage - 1, page_size: perPage })}">&lt;</a>`);
    }
    for (let p = Math.max(1, thumbPage - 2); p <= Math.min(totalPages, thumbPage + 2); p++) {
      thumbPagerParts.push(p === thumbPage
        ? `<strong class="cur">${p}</strong>`
        : `<a class="page-link" href="${navHash("gallery", { id }, { page: p, page_size: perPage })}">${p}</a>`);
    }
    if (thumbPage < totalPages) {
      thumbPagerParts.push(`<a class="page-link" href="${navHash("gallery", { id }, { page: thumbPage + 1, page_size: perPage })}">&gt;</a>`);
    }
    $view().innerHTML = `
      <a class="link-button" href="${navHash("library")}">← ${esc(t("library"))}</a>
      <header style="margin-top:16px"><p class="eyebrow">${esc(g.storage_type)} · LOCAL GALLERY</p><h1>${esc(g.title)}</h1>
      <p class="sub">gid ${esc(g.gid || "local")} · ${g.page_count} pages · ${esc(t("progress"))} ${progress.current_page}/${progress.total_pages || g.page_count} · ${fmtSize(g.file_size || 0)} <span id="gallery-favcats"></span></p></header>
      <div class="toolbar">
        <a class="primary" href="${navHash("reader", { id, page: progress.current_page })}" style="padding:8px 14px;border-radius:4px">${esc(t("readNow"))}</a>
        <button class="secondary" data-action="sync-tags" data-id="${id}" type="button">${esc(t("syncTags"))}</button>
        <button class="secondary" data-action="unfavorite-gallery" data-id="${id}" type="button" hidden>${esc(t("unfavorite"))}</button>
        <button class="secondary danger" data-action="delete-gallery" data-id="${g.id}" type="button">${esc(t("deleteGallery"))}</button>
      </div>
      <section><h2>${esc(t("tagSection"))}</h2><div class="tag-groups">${tagHtml || `<span class="muted">${esc(t("noTags"))}</span>`}</div></section>
      <section><h2>${esc(t("pagesSection"))}</h2>
        <div class="thumbs">${thumbs}</div>
        <div class="pages pager">${thumbPagerParts.join(" ")} <span class="muted">${thumbPage}/${totalPages}</span> · ${pageSizeSelect(perPage, "gallery")}</div>
      </section>`;
    if (g.gid) {
      try {
        const fav = await api("GET", `/api/galleries/${id}/favorite`);
        const favcatEl = document.getElementById("gallery-favcats");
        if (fav.favorite) {
          const btn = document.querySelector('[data-action="unfavorite-gallery"]');
          if (btn) { btn.hidden = false; btn.dataset.gid = fav.gid; }
          if (favcatEl) {
            favcatEl.innerHTML = (fav.favcat_names || []).map(n =>
              `<a class="badge" href="#/favorites/${n.favcat}?from=${id}" style="color:var(--accent)">${esc(n.name || ("#" + n.favcat))}</a>`
            ).join(" ");
          }
        }
      } catch (_) {}
    }
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function renderReader() {
  const id = app.params.id;
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  try {
    const g = await api("GET", `/api/galleries/${id}`);
    const total = g.page_count;
    app.readerTotal = total;
    let preload = "";
    for (let i = 1; i <= 3 && page + i < total; i++) {
      preload += `<link rel="preload" as="image" href="/api/galleries/${id}/pages/${page + i}">`;
    }
    $view().innerHTML = `
      <div class="reader">
        <div class="reader-bar toolbar">
          <a class="link-button" href="${navHash("gallery", { id })}">← ${esc(t("details"))}</a>
          <span>${page + 1} / ${total} · ${fmtSize(g.file_size || 0)}</span>
        </div>
        ${preload}
        <img id="reader-img" src="/api/galleries/${id}/pages/${page}" alt="Page ${page + 1}" data-next="${page + 1 < total ? page + 1 : ""}">
        <div class="nav">
          ${page > 0 ? `<a class="secondary" href="${navHash("reader", { id, page: page - 1 })}">${esc(t("prev"))}</a>` : `<span>${esc(t("prev"))}</span>`}
          <a class="secondary" href="${navHash("gallery", { id })}">${esc(t("allPages"))}</a>
          ${page + 1 < total ? `<a class="secondary" href="${navHash("reader", { id, page: page + 1 })}">${esc(t("next"))}</a>` : `<span>${esc(t("next"))}</span>`}
        </div>
      </div>`;
    try { await api("PUT", `/api/galleries/${id}/progress`, { current_page: page, total_pages: total }); } catch (_) {}
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

let readerKeyHandler = null;

function bindReaderKeys() {
  if (readerKeyHandler) {
    document.removeEventListener("keydown", readerKeyHandler);
    document.removeEventListener("click", readerKeyHandler);
    readerKeyHandler = null;
  }
  if (app.view !== "reader") return;
  const id = app.params.id;
  const current = () => Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const advance = () => {
    const n = current() + 1;
    if (app.readerTotal && n >= app.readerTotal) { goReaderNext(id); return; }
    location.hash = navHash("reader", { id, page: n });
  };
  readerKeyHandler = (e) => {
    if (e.type === "click") {
      const img = e.target.closest && e.target.closest("#reader-img");
      if (!img) return;
      if (img.dataset.next) {
        location.hash = navHash("reader", { id, page: parseInt(img.dataset.next, 10) });
      } else {
        goReaderNext(id);
      }
      return;
    }
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
    if (e.key === "ArrowRight" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      advance();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      location.hash = navHash("reader", { id, page: Math.max(0, current() - 1) });
    }
  };
  document.addEventListener("keydown", readerKeyHandler);
  document.addEventListener("click", readerKeyHandler);
}

async function goReaderNext(id) {
  try {
    const r = await api("GET", `/api/galleries/${id}/next`);
    location.hash = navHash("reader", { id: r.id, page: 0 });
  } catch (_) { /* no next gallery */ }
}

const TAG_NAMESPACES = [
  { key: "all", ns: "" }, { key: "tag", ns: "other" }, { key: "artist", ns: "artist" },
  { key: "character", ns: "character" }, { key: "parody", ns: "parody" }, { key: "group", ns: "group" },
  { key: "female", ns: "female" }, { key: "male", ns: "male" },
  { key: "language", ns: "language" },
];

function tagNsPillsHtml(activeNs, counts) {
  return TAG_NAMESPACES.map(g => {
    const active = (g.ns || "") === activeNs;
    const count = g.ns ? (counts[g.ns] || 0) : Object.values(counts).reduce((a, b) => a + b, 0);
    return `<a class="pill${active ? " active" : ""}${count ? "" : " empty"}"
      data-action="tag-ns" data-ns="${esc(g.ns || "")}"
      href="${navHash("tags", {}, g.ns ? { ns: g.ns } : {})}">
      ${esc(groupLabel(g.key))} <b>${count || 0}</b></a>`;
  }).join("");
}

function selectTagNamespace(ns) {
  // Update only the namespace pills + tag cloud (no full page re-render).
  app.query.ns = ns || "";
  delete app.query.page;
  const h1 = document.querySelector("main h1");
  if (h1) h1.textContent = app.query.ns ? nsLabel(app.query.ns) : t("tags");
  const pills = document.getElementById("tag-pills");
  if (pills) {
    pills.querySelectorAll(".pill").forEach(p => {
      p.classList.toggle("active", p.getAttribute("data-ns") === (app.query.ns || ""));
    });
  }
  const q = app.query.q || "";
  loadTags(q, app.query.ns, "1");
  history.replaceState(null, "", navHash("tags", {}, Object.assign({}, q ? { q } : {}, app.query.ns ? { ns: app.query.ns } : {})));
}

function cloudSizeClass(count, max) {
  if (!count) return "s1";
  const ratio = max > 0 ? Math.log(count + 1) / Math.log(max + 1) : 0;
  if (ratio > 0.8) return "s5";
  if (ratio > 0.55) return "s4";
  if (ratio > 0.3) return "s3";
  if (ratio > 0.1) return "s2";
  return "s1";
}

async function renderTags() {
  const ns = app.query.ns || "";
  const q = app.query.q || "";
  const page = app.query.page || "1";
  const title = ns ? nsLabel(ns) : t("tags");
  $view().innerHTML = `
    <header><p class="eyebrow">LOCAL TAXONOMY</p><h1>${esc(title)}</h1></header>
    <div class="pills" id="tag-pills"></div>
    <form class="toolbar" data-action="tags-search">
      <input name="q" value="${esc(q)}" placeholder="${esc(t("searchPlaceholder"))}">
      <button class="primary" type="submit">${esc(t("tags"))}</button>
    </form>
    <div id="tag-cloud" class="cloud"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="tag-pages"></div>`;
  await loadTags(q, ns, page);
}

async function loadTags(q, ns, page) {
  try {
    const url = `/api/tags/search?page=${encodeURIComponent(page)}&page_size=100`
      + `${ns ? `&namespace=${encodeURIComponent(ns)}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
    const data = await api("GET", url);
    const pills = document.getElementById("tag-pills");
    if (pills && (data.facets || []).length) {
      const counts = {};
      for (const f of data.facets) { counts[f.namespace] = f.total; }
      pills.innerHTML = tagNsPillsHtml(ns, counts);
    }
    const cloud = document.getElementById("tag-cloud");
    if (!cloud) return;
    const items = data.items;
    if (!items.length) { cloud.innerHTML = `<p>${esc(t("noTags"))}</p>`; }
    else {
      const max = items.reduce((m, it) => Math.max(m, it.usage_count), 0);
      cloud.innerHTML = items
        .map(it => `<a class="cloud-tag ${nsClass(it.namespace)} ${cloudSizeClass(it.usage_count, max)}" href="${navHash("library", {}, { tags: `${it.namespace}:${it.name}` })}">${esc(tagText(it))}<small>${it.usage_count}</small></a>`)
        .join("");
    }
    const pagerEl = document.getElementById("tag-pages");
    if (pagerEl) {
      const last = Math.max(1, Math.ceil(data.total / data.page_size));
      const qp = p => navHash("tags", {}, { ...(ns ? { ns } : {}), ...(q ? { q } : {}), ...(p > 1 ? { page: p } : {}) });
      pagerEl.innerHTML =
        `${data.page > 1 ? `<a class="page-link" href="${qp(data.page - 1)}">&lt;</a>` : ""}
         <strong>${data.page}/${last}</strong>
         ${data.page < last ? `<a class="page-link" href="${qp(data.page + 1)}">&gt;</a>` : ""}
         <span class="muted">· ${data.total}</span>`;
    }
  } catch (e) {
    const cloud = document.getElementById("tag-cloud");
    if (cloud) cloud.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

async function renderHistory() {
  const page = app.query.page || "1";
  $view().innerHTML = `
    <header><p class="eyebrow">READING LOG</p><h1>${esc(t("history"))}</h1>
    <button class="secondary" data-action="clear-history" type="button">${esc(t("clearHistory"))}</button></header>
    <div id="hist-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages" id="hist-pages"></div>`;
  try {
    const data = await api("GET", `/api/history?page=${encodeURIComponent(page)}`);
    const el = document.getElementById("hist-list");
    const items = (data && data.items) || [];
    if (!items.length) { el.innerHTML = `<p>${esc(t("noHistory"))}</p>`; return; }
    el.innerHTML = `<div class="rows">` + items.map(h => `
      <a class="row" href="${navHash("gallery", { id: h.gallery_id })}">
        <span class="row-title">${esc(h.title || ("#" + h.gallery_id))}</span>
        <span class="row-meta">${esc(t("progress"))} ${h.current_page}/${h.total_pages} · ${h.last_read_at ? esc(String(h.last_read_at).slice(0, 10)) : ""}</span>
      </a>`).join("") + `</div>`;
    const last = Math.max(1, Math.ceil(data.total / data.page_size));
    document.getElementById("hist-pages").innerHTML =
      `${data.page > 1 ? `<a href="${navHash("history", {}, { page: data.page - 1 })}">${esc(t("prev"))}</a>` : ""}
       <strong>${data.page}/${last}</strong> · ${data.total}`;
  } catch (e) { document.getElementById("hist-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

const DL_STATUSES = ["all", "pending", "downloading", "success", "failed", "cancelled"];
let dlTimer = null;

async function renderDownloads() {
  const filter = app.query.filter || "all";
  $view().innerHTML = `
    <header><p class="eyebrow">BACKGROUND TASKS</p><h1>${esc(t("downloads"))}</h1>
    <p class="sub">${esc(t("downloadsSub"))}</p></header>
    <section id="task-progress" class="task-progress" hidden>
      <div id="task-progress-body"></div>
    </section>
    <h2 style="margin-top:20px">${esc(t("dlTasks"))}</h2>
    <div class="toolbar">
      <div class="pills" style="margin:0">
        ${DL_STATUSES.map(s => `<a class="pill${s === filter ? " active" : ""}" href="${navHash("downloads", {}, s !== "all" ? { filter: s } : {})}">${esc(s === "all" ? t("filterAll") : s)}</a>`).join("")}
      </div>
      <button class="secondary" data-action="dl-select-all" type="button">${esc(t("selectAll"))}</button>
      <button class="primary" data-action="dl-retry-selected" type="button">${esc(t("retrySelected"))}</button>
      <button class="secondary danger" data-action="dl-delete-selected" type="button">${esc(t("deleteSel"))}</button>
    </div>
    <div id="dl-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages" id="dl-pages"></div>`;
  loadDownloads(filter, app.query.page || "1");
  pollTaskProgress();
  if (dlTimer) clearInterval(dlTimer);
  dlTimer = setInterval(() => {
    if (location.hash.startsWith("#/downloads")) loadDownloads(filter, app.query.page || "1");
  }, 2000);
}

function dlProgressHtml(x) {
  const cur = x.current_page || 0;
  const total = x.total_pages;
  if (x.status === "downloading") {
    if (total) {
      const pct = Math.min(100, Math.round((cur / total) * 100));
      return `<div class="dl-progress"><div class="dl-progress-bar" style="width:${pct}%"></div></div>
        <span class="row-meta">${cur}/${total} · ${pct}%</span>`;
    }
    // Still enumerating the gallery / waiting to start: indeterminate bar.
    return `<div class="dl-progress dl-progress-indet"></div>
      <span class="row-meta">${esc(t("downloading"))}…</span>`;
  }
  return `<span class="row-meta">${esc(x.status)}${total ? ` · ${cur}/${total}` : ""}${x.retry_count ? ` · retry ${x.retry_count}` : ""}${x.error_message ? ` · ${esc(t("error"))}: ${esc(x.error_message)}` : ""}</span>`;
}

async function loadDownloads(filter, page) {
  try {
    const status = filter !== "all" ? `&status=${encodeURIComponent(filter)}` : "";
    const data = await api("GET", `/api/downloads?page=${encodeURIComponent(page)}${status}`);
    const items = (data && data.items) || [];
    const el = document.getElementById("dl-list");
    if (!el) return;
    // Preserve the user's selection across the auto-refresh re-render.
    const checked = new Set(
      [...document.querySelectorAll(".dl-check:checked")].map(b => b.getAttribute("data-id"))
    );
    if (!items.length) { el.innerHTML = `<p>${esc(t("noTasks"))}</p>`; }
    else {
      el.innerHTML = `<div class="rows">` + items.map(x => {
        const title = x.title || ("gid " + (x.gid != null ? x.gid : x.id));
        const actions = [];
        if (x.status === "pending" || x.status === "downloading") {
          actions.push(`<button class="secondary" data-action="cancel-download" data-id="${x.id}" type="button">${esc(t("cancelDl"))}</button>`);
        }
        if (x.status === "failed" || x.status === "cancelled" || x.status === "success") {
          actions.push(`<button class="secondary" data-action="retry-download" data-id="${x.id}" type="button">${esc(t("retry"))}</button>`);
        }
        actions.push(`<button class="secondary danger" data-action="delete-download" data-id="${x.id}" type="button">${esc(t("deleteDl"))}</button>`);
        return `<div class="row" data-task-id="${x.id}">
          <input type="checkbox" class="dl-check" data-id="${x.id}"${checked.has(String(x.id)) ? " checked" : ""} aria-label="${esc(t("selectAll"))}">
          <span class="row-title dl-title" title="${esc(title)}">${esc(title)}</span>
          ${dlProgressHtml(x)}
          ${actions.join("")}
        </div>`;
      }).join("") + `</div>`;
    }
    const last = Math.max(1, Math.ceil(data.total / data.page_size));
    const qp = p => navHash("downloads", {}, filter !== "all" ? { filter, page: p } : { page: p });
    document.getElementById("dl-pages").innerHTML =
      `${data.page > 1 ? `<a href="${qp(data.page - 1)}">${esc(t("prev"))}</a>` : ""}
       <strong>${data.page}/${last}</strong> · ${data.total}`;
  } catch (e) {
    const el = document.getElementById("dl-list");
    if (el) el.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function field(label, inputHtml) {
  return `<label class="field"><span>${esc(label)}</span>${inputHtml}</label>`;
}

async function renderSettings() {
  if (!app.settings) {
    try { app.settings = await api("GET", "/api/settings"); } catch (_) { app.settings = {}; }
  }
  const s = app.settings;
  const warnings = (s.library_root_warnings || [])
    .map(w => `<p class="notice">${esc(w)}</p>`).join("");
  $view().innerHTML = `
    <header><p class="eyebrow">CONFIGURATION</p><h1>${esc(t("settings"))}</h1>
    <p class="sub">${esc(t("settingsSub"))}</p></header>
    <form data-action="settings-save">
      <fieldset><legend>${esc(t("authLogin"))}</legend>
        <label class="checkbox"><input type="checkbox" name="auth_required"${s.auth_required == null ? " checked" : (s.auth_required ? " checked" : "")}> ${esc(t("authRequired"))}</label>
        <p class="notice">${s.auth_hash_configured ? esc(t("pwConfigured")) : esc(t("pwDefault"))}</p>
      </fieldset>
      <fieldset><legend>${esc(t("changePassword"))}</legend>
        ${field(t("currentPassword"), `<input name="current_password" type="password" autocomplete="current-password">`)}
        ${field(t("newPassword"), `<input name="new_password" type="password" autocomplete="new-password">`)}
        <button class="secondary" data-action="change-password" type="button">${esc(t("changePassword"))}</button>
      </fieldset>
      <fieldset><legend>ExHentai</legend>
        ${field(t("baseUrl"), `<input name="exhentai_base_url" value="${esc(s.exhentai_base_url || "")}">`)}
        <p class="notice">Cookie: <strong>${s.exhentai_cookie_configured ? esc(t("cookieSet")) : esc(t("cookieUnset"))}</strong> · ${esc(t("cookiesNote"))}</p>
        <div class="form-grid">
          <input name="ipb_member_id" placeholder="${esc(t("cookieId"))}" autocomplete="off">
          <input name="ipb_pass_hash" placeholder="${esc(t("cookieHash"))}" autocomplete="off">
          <input name="igneous" placeholder="${esc(t("cookieIgneous"))}" autocomplete="off">
        </div>
        <button class="secondary" data-action="test-exhentai" type="button">${esc(t("testExhentai"))}</button>
      </fieldset>
      <fieldset><legend>Proxy</legend>
        <div class="form-grid">
          ${field(t("proxyHttp"), `<input name="http_proxy" value="${esc(s.http_proxy || "")}">`)}
          ${field(t("proxySocks5"), `<input name="socks5_proxy" value="${esc(s.socks5_proxy || "")}">`)}
        </div>
      </fieldset>
      <fieldset><legend>${esc(t("libraryRoots"))}</legend>
        <p class="notice">${esc(t("libraryRootsHint"))}</p>
        <textarea name="library_roots" rows="4">${esc((s.library_roots || []).join("\n"))}</textarea>
        ${warnings}
      </fieldset>
      <fieldset><legend>Downloads</legend>
        <div class="form-grid">
          ${field(t("downloadRoot"), `<input name="download_root" value="${esc(s.download_root || "")}">`)}
          <p class="notice">${esc(t("downloadRootHint"))}</p>
          ${field(t("concurrency"), `<input name="download_concurrency" type="number" min="1" max="32" value="${s.download_concurrency != null ? s.download_concurrency : 2}">`)}
          ${field(t("quality"), `<select name="download_quality">
            <option value="original"${(s.download_quality || "resample") === "original" ? " selected" : ""}>${esc(t("qualityOriginal"))}</option>
            <option value="resample"${(s.download_quality || "resample") === "resample" ? " selected" : ""}>${esc(t("qualityResample"))}</option>
          </select>`)}
          ${field(t("titleDisplay"), `<select name="title_display">${["japanese", "english", "directory"].map(o => `<option value="${o}"${o === (s.title_display || "japanese") ? " selected" : ""}>${o}</option>`).join("")}</select>`)}
        </div>
        <label class="checkbox"><input type="checkbox" name="use_hah"${s.use_hah ? " checked" : ""}> ${esc(t("useHah"))}</label>
        <label class="checkbox"><input type="checkbox" name="download_favorites_enabled"${s.download_favorites_enabled ? " checked" : ""}> download favorites</label>
      </fieldset>
      <fieldset><legend>Tags</legend>
        <label class="checkbox"><input type="checkbox" name="auto_sync_tags"${s.auto_sync_tags ? " checked" : ""}> ${esc(t("autoSyncTags"))}</label>
        <div class="form-grid">
          ${field(t("tagSyncInterval"), `<input name="tag_sync_interval_seconds" type="number" step="0.1" min="0.1" value="${s.tag_sync_interval_seconds != null ? s.tag_sync_interval_seconds : 1}">`)}
          ${field(t("tagSyncConcurrency"), `<input name="tag_sync_concurrency" type="number" min="1" max="32" value="${s.tag_sync_concurrency != null ? s.tag_sync_concurrency : 2}">`)}
        </div>
        <div class="toolbar"><button class="secondary" data-action="sync-all-tags" type="button">${esc(t("syncAllTags"))}</button></div>
      </fieldset>
      <fieldset><legend>Thumbnails</legend>
        <label class="checkbox"><input type="checkbox" name="generate_thumbnails"${s.generate_thumbnails ? " checked" : ""}> ${esc(t("generateThumbnails"))}</label>
        <div class="toolbar">
          <button class="secondary" data-action="gen-thumbs" type="button">${esc(t("genThumbs"))}</button>
        </div>
        <p class="notice">${esc(t("thumbs"))}</p>
      </fieldset>
      <fieldset><legend>${esc(t("translationUpdate"))}</legend>
        ${field(t("translationInterval"), `<input name="tag_translation_update_interval_minutes" type="number" min="0" value="${s.tag_translation_update_interval_minutes != null ? s.tag_translation_update_interval_minutes : 720}">`)}
        <div class="toolbar"><button class="secondary" data-action="force-update" type="button">${esc(t("forceUpdate"))}</button></div>
        <p class="notice">${esc(t("translationStatus"))}: <span id="trans-status">${esc(s.translation ? s.translation : "")}</span></p>
      </fieldset>
      <fieldset><legend>Telegram</legend>
        ${field(t("botToken"), `<input name="telegram_bot_token" type="password" autocomplete="new-password" placeholder="${s.telegram_bot_configured ? t("cookieSet") : t("cookieUnset")}">`)}
        <div class="form-grid">
          ${field(t("chatIds"), `<input name="telegram_chat_ids" value="${esc((s.telegram_chat_ids || []).join(","))}">`)}
          ${field(t("allowedIds"), `<input name="telegram_allowed_user_ids" value="${esc((s.telegram_allowed_user_ids || []).join(","))}">`)}
        </div>
        <button class="secondary" data-action="test-telegram" type="button">${esc(t("testTelegram"))}</button>
      </fieldset>
      <div class="toolbar"><button class="primary" type="submit">${esc(t("save"))}</button></div>
    </form>`;
  api("GET", "/api/tags/search/status").then(status => {
    const el = document.getElementById("trans-status");
    if (el && status) {
      const n = status.entries ? parseInt(status.entries, 10) : 0;
      const last = status.last ? new Date(status.last) : null;
      const when = last && !isNaN(last) ? last.toLocaleString() : (status.last || "");
      const err = status.last_error ? ` — ${esc(status.last_error)}` : "";
      el.textContent = (n > 0 ? `${n} entries, updated ${when}` : when) + err;
    }
  }).catch(() => {});
}

function collectSettings(form) {
  const val = n => form[n] ? form[n].value.trim() : "";
  const num = (n, d) => { const v = parseFloat(val(n)); return Number.isFinite(v) ? v : d; };
  const lines = a => a.split(/[\n,]/).map(x => x.trim()).filter(Boolean);
  const body = {
    library_roots: val("library_roots"),
    exhentai_base_url: val("exhentai_base_url"),
    http_proxy: val("http_proxy"),
    socks5_proxy: val("socks5_proxy"),
    download_root: val("download_root"),
    download_concurrency: Math.min(32, Math.max(1, num("download_concurrency", 2))),
    download_quality: val("download_quality") || "resample",
    title_display: val("title_display") || "japanese",
    use_hah: form.use_hah.checked,
    download_favorites_enabled: form.download_favorites_enabled.checked,
    auto_sync_tags: form.auto_sync_tags.checked,
    generate_thumbnails: form.generate_thumbnails ? form.generate_thumbnails.checked : undefined,
    tag_sync_interval_seconds: Math.max(0.1, num("tag_sync_interval_seconds", 1)),
    tag_sync_concurrency: Math.min(32, Math.max(1, num("tag_sync_concurrency", 2))),
    telegram_chat_ids: lines(val("telegram_chat_ids")),
    telegram_allowed_user_ids: lines(val("telegram_allowed_user_ids")).map(Number).filter(Number.isFinite),
    auth_required: form.auth_required.checked,
    tag_translation_update_interval_minutes: Math.max(0, num("tag_translation_update_interval_minutes", 720)),
  };
  for (const k of ["ipb_member_id", "ipb_pass_hash", "igneous", "telegram_bot_token"]) {
    if (val(k)) body[k] = val(k);
  }
  return body;
}

const FAV_MODES = ["incremental", "monitor_only", "force"];

async function renderFavorites() {
  $view().innerHTML = `
    <header><p class="eyebrow">EXHENTAI FOLDERS</p><h1>${esc(t("favcatTitle"))}</h1>
    <p class="sub">${esc(t("favcatSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="favcats-save" type="button">${esc(t("save"))}</button>
      <button class="secondary" data-action="favcats-sync" type="button">${esc(t("syncFavcats"))}</button>
      <button class="secondary" data-action="favcats-check-all" type="button">${esc(t("checkAll"))}</button>
      <a class="secondary" href="#/favorites/manage" style="padding:8px 14px;border-radius:4px;margin-left:auto">${esc(t("favManage"))}</a>
    </div>
    <div id="fav-list"><p>${esc(t("loading"))}</p></div>`;
  try {
    const cats = await api("GET", "/api/favorites/categories");
    const rows = (Array.isArray(cats) ? cats : []).map(c => `
      <tr data-favcat="${c.favcat}">
        <td class="fav-name"><a href="#/favorites/${c.favcat}" class="fav-link">${esc(c.name || ("Folder " + c.favcat))}</a> <span class="badge">#${c.favcat}</span></td>
        <td class="muted">${c.cloud_count || 0} / ${c.local_count || 0}</td>
        <td class="muted">${(c.cloud_size ? "~" : "") + fmtSize(c.cloud_size || 0)} / ${fmtSize(c.local_size || 0)}</td>
        <td><input type="checkbox" class="fav-enabled"${c.enabled ? " checked" : ""}></td>
        <td><select class="fav-mode">${FAV_MODES.map(m => `<option value="${m}"${m === (c.mode || "incremental") ? " selected" : ""}>${esc(t("favMode" + m.split("_").map(s => s[0].toUpperCase() + s.slice(1)).join("")))}</option>`).join("")}</select></td>
        <td><input type="number" min="1" class="fav-interval" value="${c.poll_interval_minutes != null ? c.poll_interval_minutes : 720}"></td>
        <td><button class="secondary" data-action="favcat-check" data-favcat="${c.favcat}" type="button">${esc(t("checkNow"))}</button></td>
      </tr>`).join("");
    document.getElementById("fav-list").innerHTML = `
      <table class="table">
        <thead><tr><th>${esc(t("favorites"))}</th><th>${esc(t("favCount"))}</th><th>${esc(t("favSize"))}</th><th>${esc(t("enabled"))}</th><th>${esc(t("mode"))}</th><th>${esc(t("intervalMin"))}</th><th></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="7">—</td></tr>`}</tbody>
      </table>`;
    pollFavoriteRings();
  } catch (e) { document.getElementById("fav-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

let favTimer = null;

const selFav = new Set();

async function renderFavList() {
  const favcat = parseInt(app.params.id, 10);
  if (isNaN(favcat)) { location.hash = "#/favorites"; return; }
  const page = app.query.page || "1";
  const selCount = selFav.size;
  const from = app.query.from;
  const backLinks = `<a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>`
    + (from ? ` <a class="link-button" href="#/gallery/${esc(from)}">← ${esc(t("backToGallery"))}</a>` : "");
  $view().innerHTML = `
    <div class="toolbar" style="margin-bottom:0">
      ${backLinks}
    </div>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITE FOLDER</p><h1>#${favcat}</h1>
    <p class="sub">${esc(t("favListSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="favlist-download" data-favcat="${favcat}" type="button">${esc(t("favDl"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary danger" data-action="favlist-unfav" data-favcat="${favcat}" type="button">${esc(t("favRemove"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-clear" type="button">${esc(t("clearSel"))}</button>
    </div>
    <div id="fav-items"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="favlist-pager"></div>`;
  try {
    const data = await api("GET", `/api/favorites/${favcat}/items?page=${encodeURIComponent(page)}&page_size=${app.query.page_size || 20}`);
    const el = document.getElementById("fav-items");
    if (!data.items.length) { el.innerHTML = `<p>${esc(t("noGalleries"))}</p>`; }
    else {
      el.innerHTML = `<div class="grid gc-grid">` + data.items.map(favCard).join("") + `</div>`;
      document.querySelectorAll('#fav-items input[data-fav-gid]').forEach(cb => {
        cb.checked = selFav.has(parseInt(cb.dataset.favGid, 10));
      });
      renderCardCheckboxes();
    }
    renderFavPager("favlist-pager", data, page);
  } catch (e) { document.getElementById("fav-items").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

function favCard(it) {
  const cat = it.category ? esc(catLabel(it.category)) : "";
  const cover = it.cover_url || it.cover_data || null;
  const inner = cover
    ? `<img loading="lazy" src="${cover}" alt="">`
    : `<span class="badge">no cover</span>`;
  const stateBadge = it.gallery_id != null
    ? `<span class="fav-state local">${esc(t("favLocal"))}</span>`
    : `<span class="fav-state cloud">${esc(t("favCloud"))}</span>`;
  const size = it.file_size ? `<span class="gc-size">${fmtSize(it.file_size)}</span>` : "";
  const link = it.gallery_id != null ? `href="${navHash("gallery", { id: it.gallery_id })}"` : `href="${esc(it.url || "#")}" target="_blank" rel="noopener"`;
  return `<div class="gc-wrap">
    <a class="gc" ${link}>
      <div class="gc-cover">${inner}${stateBadge}${cat ? `<span class="gc-cat">${cat}</span>` : ""}${it.page_count ? `<span class="gc-pages">${it.page_count} P</span>` : ""}</div>
      <div class="gc-title">${esc(it.title || ("gid " + it.gid))}${size}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-fav-gid="${it.gid}"${selFav.has(it.gid) ? " checked" : ""}></label>
  </div>`;
}

function renderFavPager(elId, data, page) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const favcat = parseInt(app.params.id, 10);
  const total = data.total, pageSize = data.page_size || 20;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const parts = [];
  for (let p = Math.max(1, parseInt(page, 10) - 2); p <= Math.min(pages, parseInt(page, 10) + 2); p++) {
    parts.push(p === parseInt(page, 10)
      ? `<strong class="cur">${p}</strong>`
      : `<a class="page-link" href="${navHash("favlist", { id: favcat }, { page: p })}">${p}</a>`);
  }
  el.innerHTML = `${parts.join(" ")} <span class="muted">${pages}</span> · ${pageSizeSelect(pageSize, "favlist")}`;
}

const selDup = new Set();
let dupFilter = "all";
let dupPage = 1;
const dupLocallyIgnored = new Set();
const favCatNames = {};

async function loadFavNames() {
  if (Object.keys(favCatNames).length) return;
  try {
    const c = await api("GET", "/api/favorites/categories");
    (Array.isArray(c) ? c : []).forEach(x => { favCatNames[x.favcat] = x.name || ""; });
  } catch (_) {}
}

function dupThumbHtml(it) {
  const src = it.gallery_id != null
    ? `/api/galleries/${it.gallery_id}/thumb/0`
    : (it.gid && it.token ? `/api/favorites/cover?gid=${it.gid}&token=${encodeURIComponent(it.token)}` : null);
  return src ? `<img class="dup-thumb" loading="lazy" src="${src}" alt="">` : `<span class="dup-thumb dup-thumb-empty"></span>`;
}

function dupItemState(it) {
  return it.gallery_id != null ? "local" : "cloud";
}

function applyDupFilter(groups) {
  if (dupFilter === "all") return groups;
  return groups
    .map(g => ({ ...g, items: g.items.filter(it => dupItemState(it) === dupFilter) }))
    .filter(g => g.items.length >= 1);
}

async function renderFavManage() {
  await loadFavNames();
  const filterBtn = (val, label) =>
    `<button class="secondary${dupFilter === val ? " active-pill" : ""}" data-action="dup-filter" data-value="${val}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITES</p><h1>${esc(t("favManageTitle"))}</h1>
    <p class="sub">${esc(t("favManageSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="dup-scan" type="button">${esc(t("dupScan"))}</button>
      ${filterBtn("all", t("dupFilterAll"))}
      ${filterBtn("local", t("dupFilterLocal"))}
      ${filterBtn("cloud", t("dupFilterCloud"))}
      <button class="secondary danger" data-action="dup-unfav" type="button">${esc(t("dupUnfav"))}${selDup.size ? ` (${selDup.size})` : ""}</button>
      <button class="secondary danger" data-action="dup-unfav-delete" type="button">${esc(t("dupUnfavDelete"))}${selDup.size ? ` (${selDup.size})` : ""}</button>
      <button class="secondary" data-action="dup-ignore-selected" type="button">${esc(t("dupIgnoreSel"))}${selDup.size ? ` (${selDup.size})` : ""}</button>
      <button class="secondary" data-action="dup-clear" type="button">${esc(t("clearSel"))}</button>
      <a class="secondary" href="#/favorites/ignored" style="padding:8px 14px;border-radius:4px;margin-left:auto">${esc(t("dupIgnoredPage"))}</a>
    </div>
    <div id="dup-progress" hidden>
      <div class="progress-bar"><div class="progress-fill" id="dup-progress-fill"></div></div>
      <p class="muted" id="dup-progress-text"></p>
    </div>
    <div id="dup-groups"><p class="muted">${esc(t("dupHint"))}</p></div>`;
}

async function runDupScan() {
  const bar = document.getElementById("dup-progress");
  const fill = document.getElementById("dup-progress-fill");
  const text = document.getElementById("dup-progress-text");
  const groupsEl = document.getElementById("dup-groups");
  selDup.clear();
  dupPage = 1;
  dupLocallyIgnored.clear();
  bar.hidden = false;
  groupsEl.innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    await api("POST", "/api/favorites/duplicates/scan");
  } catch (e) { groupsEl.innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
  for (let i = 0; i < 120; i++) {
    let st;
    try { st = await api("GET", "/api/favorites/duplicates/status"); }
    catch (e) { groupsEl.innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
    if (st.total > 0) {
      const pct = Math.min(100, Math.round((st.done / st.total) * 100));
      fill.style.width = pct + "%";
      text.textContent = `${esc(st.stage || "")} ${st.done}/${st.total}`;
    }
    if (!st.running) {
      fill.style.width = "100%";
      if (st.last_error) { groupsEl.innerHTML = `<p class="error">${esc(st.last_error)}</p>`; return; }
      lastDupStatus = st;
      renderDupGroups(st);
      renderCardCheckboxes();
      updateDupButtons();
      bar.hidden = true;
      return;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  groupsEl.innerHTML = `<p class="muted">${esc(t("loading"))}</p>`;
}

function dupThumbHtml(it) {
  const src = it.gallery_id != null
    ? `/api/galleries/${it.gallery_id}/thumb/0`
    : (it.cover_data || null);
  return src ? `<img class="dup-thumb" loading="lazy" src="${src}" alt="">` : `<span class="dup-thumb dup-thumb-empty"></span>`;
}

function renderDupGroups(st) {
  const el = document.getElementById("dup-groups");
  if (!el) return;
  const groups = applyDupFilter(st.groups || []);
  if (!groups.length) { el.innerHTML = `<p class="muted">${esc(t("dupNone"))}</p>`; return; }
  const perPage = 20;
  const totalPages = Math.max(1, Math.ceil(groups.length / perPage));
  const page = Math.max(1, Math.min(dupPage, totalPages));
  const slice = groups.slice((page - 1) * perPage, page * perPage);
  const renderGroup = (g, gi) => {
    const hidden = dupLocallyIgnored.has(g.key);
    return `
      <div class="panel dup-group ${hidden ? "dup-hidden" : ""}" style="margin-top:14px">
        <div class="dup-group-head">
          <span class="dup-count">${esc(g.items.length)} ×</span>
          <a class="dup-main-title" href="${esc(g.items[0].url)}" target="_blank" rel="noopener">${esc(g.items[0].title)}</a>
          ${g.artist ? `<span class="dup-artist">${esc(g.artist)}</span>` : ""}
          ${hidden ? `<span class="badge dup-ignored-badge">${esc(t("dupIgnored"))}</span>` : ""}
          <span class="dup-head-actions"><button class="secondary" data-action="dup-group-sel" data-gi="${gi}" type="button">${esc(t("select"))}</button></span>
        </div>
        ${g.items.map((it, ii) => `
          <div class="dup-row">
            <label class="checkbox"><input type="checkbox" data-dup-gid="${it.gid}" data-key="${esc(g.key)}" data-gi="${gi}" data-ii="${ii}"${selDup.has(it.gid) ? " checked" : ""}>
              <span class="dup-thumb-wrap">${dupThumbHtml(it)}</span>
              <span class="dup-body">
                <span class="dup-title">
                  <a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>
                </span>
                <span class="dup-meta">
                  ${it.gallery_id != null ? `<a class="badge dup-badge-local" href="${navHash("gallery", { id: it.gallery_id })}">${esc(t("favLocal"))}</a>` : `<span class="badge dup-badge-cloud">${esc(t("favCloud"))}</span>`}
                  <span class="badge">#${it.favcat}${favCatNames[it.favcat] ? " " + esc(favCatNames[it.favcat]) : ""}</span>
                  ${fmtDate(it.posted_at) ? `<span class="badge">${esc(t("postedDate"))} ${fmtDate(it.posted_at)}</span>` : ""}
                  ${it.file_size ? `<span class="badge">${fmtSize(it.file_size)}</span>` : ""}
                </span>
                ${(it.tags || []).length ? `<span class="dup-tags">${it.tags.map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</span>` : ""}
              </span>
            </label>
          </div>`).join("")}
      </div>`;
  };
  const pageLinks = [];
  for (let p = Math.max(1, page - 2); p <= Math.min(totalPages, page + 2); p++) {
    pageLinks.push(p === page
      ? `<strong class="cur">${p}</strong>`
      : `<a class="page-link" href="#" data-action="dup-page" data-page="${p}">${p}</a>`);
  }
  const pagerHtml = groups.length > perPage
    ? `<div class="pages pager" style="margin-top:16px">${pageLinks.join(" ")} <span class="muted">${totalPages}</span></div>`
    : "";
  el.innerHTML = `
    <p class="sub">${esc(t("dupFound"))}: ${groups.length} ${esc(t("dupGroups"))} · ${groups.reduce((n, g) => n + g.items.length, 0)} ${esc(t("dupItems"))}</p>
    ${slice.map((g, i) => renderGroup(g, (page - 1) * perPage + i)).join("")}
    ${pagerHtml}`;
}

function favRingHtml(done, total) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const r = 15.9, c = 2 * Math.PI * r;
  const off = c * (1 - pct / 100);
  return `<span class="fav-ring" title="${esc(done + " / " + total)}">
    <svg viewBox="0 0 36 36"><circle class="ring-bg" cx="18" cy="18" r="${r}"></circle>
    <circle class="ring-fg" cx="18" cy="18" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${off}"></circle></svg>
  </span>`;
}

async function pollFavoriteRings() {
  if (favTimer) clearInterval(favTimer);
  const tick = async () => {
    try {
      const st = await api("GET", "/api/favorites/check-status");
      const cats = (st && st.categories) || {};
      document.querySelectorAll("#fav-list tr[data-favcat]").forEach(tr => {
        const nameCell = tr.querySelector(".fav-name");
        if (!nameCell) return;
        const old = nameCell.querySelector(".fav-ring");
        if (old) old.remove();
        const e = cats[tr.dataset.favcat];
        if (e && e.running) {
          nameCell.insertAdjacentHTML("beforeend", favRingHtml(e.done || 0, e.total || 0));
        }
      });
    } catch (_) { /* transient */ }
  };
  tick();
  favTimer = setInterval(tick, 3000);
}

function fmtSize(bytes) {
  if (!bytes || bytes < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (v >= 100 ? v.toFixed(0) : v.toFixed(1)) + " " + units[i];
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

async function saveFavoriteCategories() {
  const favorites = [...document.querySelectorAll("#fav-list tr[data-favcat]")].map(tr => ({
    favcat: parseInt(tr.dataset.favcat, 10),
    enabled: tr.querySelector(".fav-enabled").checked,
    mode: tr.querySelector(".fav-mode").value,
    poll_interval_minutes: Math.max(1, parseInt(tr.querySelector(".fav-interval").value, 10) || 720),
  }));
  try {
    await api("POST", "/api/settings", { favorites });
    app.settings = null;
    toast(t("saveOk"));
  } catch (e) { toast(e.message); }
}

async function syncFavoriteCategories() {
  try {
    await api("POST", "/api/favorites/sync-categories");
    app.settings = null;
    toast(t("saveOk"));
    renderFavorites();
  } catch (e) { toast(e.message); }
}

async function checkFavoriteCategory(favcat) {
  try {
    await api("POST", `/api/favorites/${favcat}/check`);
    toast("#" + favcat + " · " + t("checkNow"));
  } catch (e) { toast(e.message); }
}

async function checkAllFavorites() {
  try {
    await api("POST", "/api/favorites/check-all");
    toast(t("checkAll"));
    pollFavoriteRings();
  } catch (e) { toast(e.message); }
}

function onClick(e) {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const action = el.getAttribute("data-action");
  if (action === "toggle-lang") { toggleLang(); return; }
  if (action === "logout") { doLogout(); return; }
  if (action === "random") { randomGallery(); return; }
  if (action === "scan") { scanLibrary(); return; }
  if (action === "clear-tag") { e.preventDefault(); location.hash = navHash("library", {}, { q: app.query.q || "", category: app.query.category || "" }); return; }
  if (action === "clear-history") { clearHistory(); return; }
  if (action === "cancel-download") { cancelDownload(el.getAttribute("data-id")); return; }
  if (action === "retry-download") { retryDownload(el.getAttribute("data-id")); return; }
  if (action === "delete-download") { deleteDownload(el.getAttribute("data-id")); return; }
  if (action === "dl-select-all") { selectAllDownloads(); return; }
  if (action === "dl-retry-selected") { retrySelectedDownloads(); return; }
  if (action === "dl-delete-selected") { deleteSelectedDownloads(); return; }
  if (action === "test-exhentai") { testExhentai(); return; }
  if (action === "favcats-save") { saveFavoriteCategories(); return; }
  if (action === "favcats-sync") { syncFavoriteCategories(); return; }
  if (action === "favcats-check-all") { checkAllFavorites(); return; }
  if (action === "favcat-check") { checkFavoriteCategory(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-download") { favListDownload(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-unfav") { favListUnfavorite(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-clear") { selFav.clear(); router(); return; }
  if (action === "dup-scan") { runDupScan(); return; }
  if (action === "dup-unfav") { dupAction(false); return; }
  if (action === "dup-unfav-delete") { dupAction(true); return; }
  if (action === "dup-clear") { selDup.clear(); renderDupGroupsFromCache(); return; }
  if (action === "dup-group-sel") { dupSelectGroup(el.getAttribute("data-gi")); return; }
  if (action === "dup-filter") { dupFilter = el.getAttribute("data-value") || "all"; dupPage = 1; renderFavManage().then(() => renderDupGroupsFromCache()); return; }
  if (action === "dup-ignore-selected") { dupIgnoreSelected(); return; }
  if (action === "dup-unignore") { dupUnignore(el.getAttribute("data-key")); return; }
  if (action === "dup-unignore-one") { dupUnignore(el.getAttribute("data-key")); return; }
  if (action === "dup-unignore-selected") { dupUnignoreSelected(); return; }
  if (action === "dup-ignored-clear") { document.querySelectorAll('#ignored-list input[data-ignore-key]').forEach(cb => cb.checked = false); renderFavIgnored(); return; }
  if (action === "dup-page") { e.preventDefault(); dupPage = parseInt(el.getAttribute("data-page"), 10) || 1; renderDupGroupsFromCache(); return; }
  if (action === "sync-tags") { syncTags(el.getAttribute("data-id")); return; }
  if (action === "change-password") { e.preventDefault(); changePassword(); return; }
  if (action === "test-telegram") { testTelegram(); return; }
  if (action === "force-update") { forceUpdate(); return; }
  if (action === "gen-thumbs") { generateThumbnails(); return; }
  if (action === "sync-all-tags") { syncAllTags(); return; }
  if (action === "delete-gallery") { deleteGallery(el.getAttribute("data-id")); return; }
  if (action === "unfavorite-gallery") { unfavoriteGallery(el); return; }
  if (action === "delete-filtered") { deleteFiltered(); return; }
  if (action === "sel-clear") { selGalleries.clear(); renderCardCheckboxes(); router(); return; }
  if (action === "sel-delete") { deleteSelected(); return; }
  if (action === "tag-ns") { e.preventDefault(); selectTagNamespace(el.getAttribute("data-ns")); return; }
}

function onSubmit(e) {
  const form = e.target;
  if (form.tagName !== "FORM") return;
  const action = form.getAttribute("data-action");
  if (action === "login") { e.preventDefault(); doLogin(form.password.value); return; }
  if (action === "change-password") { e.preventDefault(); changePassword(form); return; }
  if (action === "search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim() }); return; }
  if (action === "library-search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim(), category: form.category.value }); return; }
  if (action === "tags-search") { e.preventDefault(); location.hash = navHash("tags", {}, { ns: app.query.ns || "", q: form.q.value.trim() }); return; }
  if (action === "browse-search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim() }); return; }
  if (action === "settings-save") { e.preventDefault(); saveSettings(form); return; }
}

function toggleLang() {
  app.lang = app.lang === "zh" ? "en" : "zh";
  localStorage.setItem("gv_lang", app.lang);
  updateLangButton();
  router();
}

async function randomGallery() {
  try { const d = await api("GET", "/api/galleries/random"); location.hash = navHash("gallery", { id: d.id }); }
  catch (e) { toast(e.message); }
}

async function scanLibrary() {
  try { await api("POST", "/api/scan"); toast("Scan started"); pollTaskProgress(); }
  catch (e) { toast(e.message); }
}

let taskTimer = null;

function progressHtml(label, done, total, extra) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  return `<div class="task-row">
    <span class="row-title">${esc(label)}</span>
    ${pct !== null
      ? `<div class="dl-progress"><div class="dl-progress-bar" style="width:${pct}%"></div></div>
         <span class="row-meta">${done}/${total} · ${pct}%${extra ? " · " + esc(extra) : ""}</span>`
      : `<div class="dl-progress dl-progress-indet"></div><span class="row-meta">${esc(extra || "…")}</span>`}
  </div>`;
}

async function pollTaskProgress() {
  if (taskTimer) clearInterval(taskTimer);
  const tick = async () => {
    const sec = document.getElementById("task-progress");
    if (!sec) return;
    try {
      const [scan, ts, th, md] = await Promise.all([
        api("GET", "/api/scan").catch(() => null),
        api("GET", "/api/tag-sync/status").catch(() => null),
        api("GET", "/api/thumbs/status").catch(() => null),
        api("GET", "/api/favorites/metadata-status").catch(() => null),
      ]);
      const rows = [];
      const isDone = st => !!(st && !st.running && st.completed_at);
      const tickText = "✓ " + t("completed") + " ";
      if (scan && (scan.running || isDone(scan))) {
        const done = isDone(scan);
        rows.push(progressHtml(
          done ? t("scanDone") : t("scanning"),
          scan.scanned || 0, 0,
          done
            ? tickText + (scan.scanned ? `${t("scanned")} ${scan.scanned} · ` : "") + `${t("persisted")} ${scan.persisted || 0}`
            : `${t("scanned")} ${scan.scanned || 0} · ${t("persisted")} ${scan.persisted || 0}`
        ));
      }
      if (ts && (ts.running || isDone(ts))) {
        const done = isDone(ts);
        rows.push(progressHtml(
          done ? t("tagSyncDone") : t("tagSyncing"),
          ts.processed || 0, ts.total || 0,
          (done ? tickText : "") + `ok ${ts.succeeded || 0} / fail ${ts.failed || 0}`
        ));
      }
      if (th && (th.running || isDone(th))) {
        const done = isDone(th);
        const doneCount = (th.succeeded || 0) + (th.failed || 0);
        rows.push(progressHtml(
          done ? t("thumbsDone") : t("thumbs"),
          doneCount, th.total || 0,
          (done ? tickText : "") + `ok ${th.succeeded || 0} / fail ${th.failed || 0}`
        ));
      }
      if (md && (md.running || isDone(md))) {
        const done = isDone(md);
        const applying = (md.stage || "") === "apply";
        rows.push(progressHtml(
          done ? t("metaDone") : (applying ? t("favMetaApply") : t("favMetaSync")),
          md.done || 0, md.total || 0,
          (done ? tickText : "") + `${t("applied")} ${md.applied || 0}`
        ));
      }
      const body = document.getElementById("task-progress-body");
      if (rows.length) {
        sec.hidden = false;
        body.innerHTML = rows.join("");
      } else {
        sec.hidden = true;
        body.innerHTML = "";
        clearInterval(taskTimer);
        taskTimer = null;
      }
    } catch (_) { /* transient */ }
  };
  tick();
  taskTimer = setInterval(tick, 2000);
}

async function clearHistory() {
  try { await api("DELETE", "/api/history"); renderHistory(); }
  catch (e) { toast(e.message); }
}

async function cancelDownload(id) {
  try { await api("POST", `/api/downloads/${id}/cancel`); toast("#" + id + " cancelled"); loadDownloads(app.query.filter || "all", app.query.page || "1"); }
  catch (e) { toast(e.message); }
}

async function retryDownload(id) {
  try { await api("POST", `/api/downloads/${id}/retry`); toast("#" + id + " queued"); loadDownloads(app.query.filter || "all", app.query.page || "1"); }
  catch (e) { toast(e.message); }
}

async function deleteDownload(id) {
  if (!window.confirm(t("deleteDl") + " #" + id + "?")) return;
  try { await api("DELETE", `/api/downloads/${id}`); toast("#" + id + " " + t("deleted")); loadDownloads(app.query.filter || "all", app.query.page || "1"); }
  catch (e) { toast(e.message); }
}

function selectAllDownloads() {
  const boxes = document.querySelectorAll(".dl-check");
  const all = boxes.length && [...boxes].every(b => b.checked);
  boxes.forEach(b => { b.checked = !all; });
}

async function deleteSelectedDownloads() {
  const ids = [...document.querySelectorAll(".dl-check:checked")].map(b => b.getAttribute("data-id"));
  if (!ids.length) { toast(t("deleteSel")); return; }
  if (!window.confirm(t("deleteSel") + " (" + ids.length + ")?")) return;
  let ok = 0, fail = 0;
  for (const id of ids) {
    try { await api("DELETE", `/api/downloads/${id}`); ok++; }
    catch (_) { fail++; }
  }
  toast(`${ok} ${t("deleted")}${fail ? `, ${fail} failed` : ""}`);
  loadDownloads(app.query.filter || "all", app.query.page || "1");
}

async function retrySelectedDownloads() {
  const ids = [...document.querySelectorAll(".dl-check:checked")].map(b => b.getAttribute("data-id"));
  if (!ids.length) { toast(t("retrySelected")); return; }
  let ok = 0, fail = 0;
  for (const id of ids) {
    try { await api("POST", `/api/downloads/${id}/retry`); ok++; }
    catch (_) { fail++; }
  }
  toast(`${ok} queued${fail ? `, ${fail} failed` : ""}`);
  loadDownloads(app.query.filter || "all", app.query.page || "1");
}

async function deleteGallery(id) {
  if (!window.confirm(t("confirmDelete"))) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    await api("DELETE", `/api/galleries/${id}?delete_files=${deleteFiles}`);
    toast(t("deleted"));
    location.hash = navHash("library");
  } catch (e) { toast(e.message); }
}

async function unfavoriteGallery(el) {
  const gid = parseInt(el.dataset.gid, 10);
  if (!gid) { toast(t("unfavoriteFail")); return; }
  if (!window.confirm(t("confirmUnfavorite"))) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: [gid], delete_local: false });
    if (r.cloud_ok) toast(t("unfavorited"));
    else toast(t("unfavoritedLocal"));
    el.hidden = true;
  } catch (e) { toast(e.message); }
}

async function favListDownload(favcat) {
  if (!selFav.size) { toast(t("select")); return; }
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  const data = await api("GET", `/api/favorites/${favcat}/items?page=1&page_size=100`);
  const total = data.total || 0;
  const pages = Math.max(1, Math.ceil(total / 100));
  const byGid = new Map(data.items.map(i => [i.gid, i]));
  for (let p = 2; p <= pages; p++) {
    const d = await api("GET", `/api/favorites/${favcat}/items?page=${p}&page_size=100`);
    (d.items || []).forEach(i => byGid.set(i.gid, i));
  }
  let queued = 0, skip = 0;
  for (const gid of selected) {
    const meta = byGid.get(gid);
    if (!meta || !meta.token) { skip++; continue; }
    if (meta.gallery_id != null) { skip++; continue; }
    try {
      await api("POST", "/api/downloads", { gid: meta.gid, token: meta.token, title: meta.title, mode: "favorites" });
      queued++;
    } catch (_) { skip++; }
  }
  toast(t("favDlQueued") + ": " + queued + (skip ? " · " + t("favDlSkip") + ": " + skip : ""));
  selFav.clear();
}

async function favListUnfavorite(favcat) {
  const items = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!items.length) { toast(t("select")); return; }
  if (!window.confirm(t("confirmFavRemove") + " " + items.length)) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: items, delete_local: false });
    toast(t("unfavorited") + (r.cloud_ok ? "" : " · " + t("unfavoritedLocal")));
    selFav.clear();
    router();
  } catch (e) { toast(e.message); }
}

let lastDupStatus = null;

async function dupAction(deleteLocal) {
  const items = [...document.querySelectorAll('#dup-groups [data-dup-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.dupGid, 10));
  if (!items.length) { toast(t("select")); return; }
  const msg = deleteLocal ? t("confirmDupDelete") : t("confirmDupUnfav");
  if (!window.confirm(msg + " " + items.length)) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: items, delete_local: deleteLocal });
    toast(t("unfavorited") + (r.cloud_ok ? "" : " · " + t("unfavoritedLocal"))
      + (r.deleted_local_galleries ? " · " + t("deleted") + " " + r.deleted_local_galleries : ""));
    selDup.clear();
    runDupScan();
  } catch (e) { toast(e.message); }
}

function dupSelectGroup(gi) {
  const filtered = lastDupStatus ? applyDupFilter(lastDupStatus.groups || []) : [];
  const group = filtered[gi];
  if (!group) return;
  const gids = group.items.map(it => it.gid);
  const allSel = gids.every(gid => selDup.has(gid));
  const cbs = [...document.querySelectorAll(`#dup-groups input[data-gi="${gi}"]`)];
  cbs.forEach(cb => {
    const gid = parseInt(cb.dataset.dupGid, 10);
    if (allSel) selDup.delete(gid); else selDup.add(gid);
    cb.checked = !allSel;
  });
  updateDupButtons();
}

async function dupIgnoreSelected() {
  const keys = new Set();
  document.querySelectorAll('#dup-groups input[data-dup-gid]:checked').forEach(cb => {
    const k = cb.getAttribute("data-key");
    if (k) keys.add(k);
  });
  if (!keys.size) { toast(t("select")); return; }
  const groupsByKey = new Map((lastDupStatus.groups || []).map(g => [g.key, g]));
  let ok = 0;
  for (const key of keys) {
    const group = groupsByKey.get(key);
    try {
      await api("POST", "/api/favorites/duplicates/ignore", {
        key,
        title: group ? group.items[0].title : "",
        gids: group ? group.items.map(it => it.gid) : [],
      });
      ok++;
    } catch (_) { /* keep going */ }
  }
  keys.forEach(k => dupLocallyIgnored.add(k));
  selDup.clear();
  toast(t("dupIgnoredOk") + ": " + ok);
  renderDupGroupsFromCache();
  renderCardCheckboxes();
  updateDupButtons();
}

async function dupUnignore(key) {
  if (!key) return;
  try {
    await api("DELETE", `/api/favorites/duplicates/ignore?key=${encodeURIComponent(key)}`);
    toast(t("dupUnignoredOk"));
    if (app.view === "favignored") { renderFavIgnored(); }
    else { dupLocallyIgnored.delete(key); renderDupGroupsFromCache(); }
  } catch (e) { toast(e.message); }
}

async function renderFavIgnored() {
  let list = [];
  try { list = await api("GET", "/api/favorites/duplicates/ignored"); }
  catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
  await loadFavNames();
  $view().innerHTML = `
    <a class="link-button" href="#/favorites/manage">← ${esc(t("favManage"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITES</p><h1>${esc(t("dupIgnoredPage"))}</h1>
    <p class="sub">${esc(t("dupIgnoredSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="dup-unignore-selected" type="button">${esc(t("dupUnignoreSel"))}</button>
      <button class="secondary" data-action="dup-ignored-clear" type="button">${esc(t("clearSel"))}</button>
    </div>
    <div id="ignored-list">${list.length ? "" : `<p class="muted">${esc(t("dupNone"))}</p>`}</div>`;
  const el = document.getElementById("ignored-list");
  if (!list.length) return;
  el.innerHTML = list.map(g => `
    <div class="panel dup-group" style="margin-top:14px">
      <div class="dup-group-head">
        <label class="checkbox" style="margin:0"><input type="checkbox" data-ignore-key="${esc(g.key)}"> <strong>${esc((g.items || []).length)} ×</strong></label>
        <span class="dup-main-title">${esc(g.title || g.key)}</span>
        <span class="dup-head-actions"><button class="secondary" data-action="dup-unignore-one" data-key="${esc(g.key)}" type="button">${esc(t("dupUnignore"))}</button></span>
      </div>
      ${(g.items || []).map(it => `
        <div class="dup-row">
          <span class="dup-thumb-wrap">${it.cover_url ? `<img class="dup-thumb" loading="lazy" src="${it.cover_url}" alt="">` : (it.cover_data ? `<img class="dup-thumb" loading="lazy" src="${it.cover_data}" alt="">` : `<span class="dup-thumb dup-thumb-empty"></span>`)}</span>
          <span class="dup-body">
            <span class="dup-title"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></span>
            <span class="dup-meta">
              ${it.gallery_id != null ? `<a class="badge dup-badge-local" href="${navHash("gallery", { id: it.gallery_id })}">${esc(t("favLocal"))}</a>` : `<span class="badge dup-badge-cloud">${esc(t("favCloud"))}</span>`}
              <span class="badge">#${it.favcat}${favCatNames[it.favcat] ? " " + esc(favCatNames[it.favcat]) : ""}</span>
              ${fmtDate(it.posted_at) ? `<span class="badge">${esc(t("postedDate"))} ${fmtDate(it.posted_at)}</span>` : ""}
              ${it.file_size ? `<span class="badge">${fmtSize(it.file_size)}</span>` : ""}
            </span>
            ${(it.tags || []).length ? `<span class="dup-tags">${it.tags.map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</span>` : ""}
          </span>
        </div>`).join("")}
    </div>`).join("");
  document.querySelectorAll('#ignored-list input[data-ignore-key]').forEach(cb => {
    cb.addEventListener("change", updateIgnoredSelBtn);
  });
}

function updateIgnoredSelBtn() {
  const n = document.querySelectorAll('#ignored-list input[data-ignore-key]:checked').length;
  const btn = document.querySelector('[data-action="dup-unignore-selected"]');
  if (btn) btn.textContent = t("dupUnignoreSel") + (n ? ` (${n})` : "");
}

async function dupUnignoreSelected() {
  const keys = [...document.querySelectorAll('#ignored-list input[data-ignore-key]:checked')]
    .map(cb => cb.getAttribute("data-ignore-key"));
  if (!keys.length) { toast(t("select")); return; }
  let ok = 0;
  for (const key of keys) {
    try { await api("DELETE", `/api/favorites/duplicates/ignore?key=${encodeURIComponent(key)}`); ok++; }
    catch (_) { /* keep going */ }
  }
  toast(t("dupUnignoredOk") + ": " + ok);
  renderFavIgnored();
}

function updateDupButtons() {
  document.querySelectorAll('[data-action="dup-unfav"], [data-action="dup-unfav-delete"]').forEach(b => {
    b.textContent = (b.getAttribute("data-action") === "dup-unfav" ? t("dupUnfav") : t("dupUnfavDelete")) + (selDup.size ? ` (${selDup.size})` : "");
  });
}

async function renderDupGroupsFromCache() {
  if (!lastDupStatus) return;
  renderDupGroups(lastDupStatus);
  updateDupButtons();
}

async function deleteFiltered() {
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  if (!window.confirm(t("confirmDeleteFiltered"))) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    // Resolve the current filter to a list of gallery ids (all pages), then bulk delete.
    const allIds = [];
    let page = 1, total = Infinity;
    while (allIds.length < total) {
      const extra = { page, page_size: 100 };
      if (q) extra.q = q;
      if (category) extra.category = category;
      if (tags) extra.tags = tags;
      const data = await galleryGrid(null, page, extra);
      if (!data || !data.items.length) break;
      allIds.push(...data.items.map(it => it.id));
      total = data.total;
      page += 1;
    }
    if (!allIds.length) { toast(t("noGalleries")); return; }
    await api("POST", "/api/galleries/delete-bulk", { ids: allIds, delete_files: deleteFiles });
    toast(t("deleted") + ": " + allIds.length);
    location.hash = navHash("library");
  } catch (e) { toast(e.message); }
}

async function deleteSelected() {
  const ids = [...selGalleries];
  if (!ids.length) { toast(t("deleteSel")); return; }
  if (!window.confirm(t("confirmDeleteSel") + " (" + ids.length + ")")) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    await api("POST", "/api/galleries/delete-bulk", { ids, delete_files: deleteFiles });
    selGalleries.clear();
    toast(t("deleted") + ": " + ids.length);
    router();
  } catch (e) { toast(e.message); }
}

function bindTagSuggest() {
  document.querySelectorAll('.search-box input[name="q"]').forEach(input => {
    if (input.dataset.suggestBound) return;
    input.dataset.suggestBound = "1";
    const box = input.parentElement.querySelector(".tag-suggest");
    if (!box) return;
    input.addEventListener("input", () => {
      clearTimeout(suggestTimer);
      const value = input.value.trim();
      if (!value) { box.hidden = true; return; }
      suggestTimer = setTimeout(() => loadTagSuggest(value, box), 200);
    });
    input.addEventListener("focus", () => {
      const value = input.value.trim();
      if (value) loadTagSuggest(value, box);
    });
    box.addEventListener("click", (e) => e.stopPropagation());
  });
  if (!window.__gvSuggestBound) {
    window.__gvSuggestBound = true;
    document.addEventListener("click", dismiss);
  }
}

function dismiss(e) {
  document.querySelectorAll(".tag-suggest").forEach(box => {
    if (!e.target.closest(".search-box")) box.hidden = true;
  });
}

async function loadTagSuggest(q, box) {
  if (!box) return;
  try {
    const isCjk = /[\u3400-\u9fff\uf900-\ufaff]/u.test(q);
    const url = `/api/tags/search?q=${encodeURIComponent(q)}&page_size=8${isCjk ? "&zh=1" : ""}`;
    const data = await api("GET", url);
    const items = (data && data.items) || [];
    if (!items.length) { box.hidden = true; return; }
    box.innerHTML = items.map(it => `
      <div class="suggest-item" data-tags="${esc(`${it.namespace}:${it.name}`)}">
        <span class="suggest-name">${esc(tagText(it))}</span>
        <span class="suggest-ns">${esc(nsLabel(it.namespace))} · ${it.usage_count}</span>
      </div>`).join("");
    box.hidden = false;
    box.querySelectorAll(".suggest-item").forEach(item => {
      item.addEventListener("click", () => {
        box.hidden = true;
        const tags = item.getAttribute("data-tags");
        location.hash = navHash("library", {}, { tags });
      });
    });
  } catch (_) { box.hidden = true; }
}

async function testExhentai() {
  try {
    const r = await api("POST", "/api/settings/exhentai/test");
    toast(r.message || r.status);
  } catch (e) { toast(e.message); }
}

async function changePassword() {
  const form = document.querySelector('[data-action="settings-save"]');
  const current = form.querySelector('[name="current_password"]').value;
  const next = form.querySelector('[name="new_password"]').value;
  if (!next) { toast(t("newPassword")); return; }
  try {
    await api("POST", "/api/auth/change-password", { current, new: next });
    app.session.must_change_password = false;
    toast(t("changePwOk"));
    updateBanner();
  } catch (e) { toast(e.message); }
}

async function testTelegram() {
  try {
    const r = await api("POST", "/api/telegram/test");
    toast(r.ok ? t("testTelegram") + " OK" : JSON.stringify(r.results));
  } catch (e) { toast(e.message); }
}

async function forceUpdate() {
  try {
    const r = await api("POST", "/api/tags/search/reload");
    const el = document.getElementById("trans-status");
    if (el) el.textContent = r.ok ? t("transUpdated") : (r.last_error || "?");
    toast(t("forceUpdate") + (r.ok ? " OK" : " :: " + (r.last_error || "?")));
  } catch (e) { toast(e.message); }
}

async function generateThumbnails() {
  try {
    const r = await api("POST", "/api/thumbs/generate");
    toast(t("genThumbs") + (r && r.queued ? ` (${r.queued})` : ""));
    pollTaskProgress();
  } catch (e) { toast(e.message); }
}

async function syncAllTags() {
  try {
    const r = await api("POST", "/api/tag-sync/start");
    toast(t("syncAllTags") + (r && r.queued ? ` (${r.queued})` : ""));
    pollTaskProgress();
  } catch (e) { toast(e.message); }
}

async function syncTags(id) {
  try {
    const r = await api("POST", `/api/galleries/${id}/sync-tags`);
    toast((r && r.source === "cache") ? t("tagSyncFromCache") : t("tagSyncFromNetwork") + (r ? ` · ${r.count}` : ""));
  }
  catch (e) { toast(e.message); }
}

async function saveSettings(form) {
  try {
    const data = await api("POST", "/api/settings", collectSettings(form));
    app.settings = data && data.library_roots !== undefined ? data : null;
    toast(t("saveOk"));
    renderSettings();
  } catch (e) { toast(e.message); }
}

function onChange(e) {
  const el = e.target;
  if (!el || !el.matches(".page-size")) return;
  const view = el.getAttribute("data-view") || app.view;
  const params = (view === "gallery" || view === "favlist") ? { id: app.params.id } : {};
  const q = { ...app.query, page_size: el.value, page: undefined };
  Object.keys(q).forEach(k => { if (q[k] === undefined) delete q[k]; });
  location.hash = navHash(view, params, q);
}

function init() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("submit", onSubmit);
  window.addEventListener("hashchange", router);
  updateLangButton();
  checkAuth();
}

init();
