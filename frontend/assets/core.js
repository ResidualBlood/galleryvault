"use strict";

// Phase 3: I18N + t/nsLabel/groupLabel/tagText moved to i18n.js (split for future extraction / i18n tools)

function updateLangButton() {
  const b = document.querySelector('[data-action="toggle-lang"]');
  if (b) b.textContent = t("language");
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
}

let cookieHealthTimer = null;
let cookieHealthInFlight = false;
let pauseTimer = null;
let pauseInFlight = false;

function updateBanner() {
  const el = document.getElementById("banner");
  if (!el) return;
  if (app.authenticated && app.session && app.session.must_change_password) {
    el.hidden = false;
    el.innerHTML = `<span>${esc(t("mustChange"))}</span> <a class="btn btn-primary" href="#/welcome">${esc(t("changePassword"))}</a>`;
    return;
  }
  const parts = [];
  if (app.authenticated && app.paused) {
    parts.push(`<span style="color:var(--warning, #ff9800);font-weight:600;">⏸ ${esc(t("paused"))} — ${esc(t("pauseHint"))}</span> <button class="btn btn-secondary" data-action="toggle-pause" type="button" style="margin-left:8px;padding:2px 10px;font-size:12px;">${esc(t("resume"))}</button>`);
  }
  const ch = app.session && app.session.cookie_health;
  if (app.authenticated && ch && (ch.state === "not_logged_in" || ch.state === "no_exhentai_access")) {
    parts.push(`<span style="color:var(--danger, #e53935);font-weight:600;">⚠️ ${esc(t("cookieExpiredNotice"))}</span> <a class="btn btn-secondary" href="#/settings" style="margin-left:8px;padding:2px 10px;font-size:12px;">${esc(t("goToSettings"))}</a>`);
  } else if (app.authenticated && ch && ch.state === "failed") {
    parts.push(`<span style="color:var(--warning, #ff9800);font-weight:600;">⚠️ ${esc(t("cookieHealthFailed"))}${ch.detail ? ` (${esc(ch.detail)})` : ""}</span> <a class="btn btn-secondary" href="#/settings" style="margin-left:8px;padding:2px 10px;font-size:12px;">${esc(t("goToSettings"))}</a>`);
  }
  // Also show image limit warning if near limit (>80%)
  const quota = app.session && app.session.quota_warning;
  if (app.authenticated && quota) {
    parts.push(`<span style="color:var(--warning, #ff9800);font-weight:600;">⚠️ ${esc(quota)}</span>`);
  }
  if (parts.length) {
    el.hidden = false;
    el.innerHTML = parts.join('<br style="margin:4px 0;display:block;">');
  } else {
    el.hidden = true;
    el.innerHTML = "";
  }
}

async function refreshCookieHealth() {
  if (!app.authenticated || cookieHealthInFlight) return;
  cookieHealthInFlight = true;
  try {
    const h = await api("GET", "/api/settings/cookie-health");
    if (h && typeof h === "object") {
      app.session.cookie_health = h;
      updateBanner();
    }
  } catch (_) {
    // transient — keep last health, banner stays as-is
  } finally {
    cookieHealthInFlight = false;
  }
}

function startCookieHealthPolling() {
  if (cookieHealthTimer) return;
  // Short delay so startup probe can finish, then poll every 10 min while authenticated
  setTimeout(refreshCookieHealth, 3000);
  cookieHealthTimer = setInterval(refreshCookieHealth, 10 * 60 * 1000);
}

function stopCookieHealthPolling() {
  if (cookieHealthTimer) {
    clearInterval(cookieHealthTimer);
    cookieHealthTimer = null;
  }
}

async function refreshPause() {
  if (!app.authenticated || pauseInFlight) return;
  pauseInFlight = true;
  try {
    const r = await api("GET", "/api/pause");
    if (r && typeof r.paused === "boolean") {
      const wasPaused = !!app.paused;
      app.paused = r.paused;
      if (wasPaused !== r.paused) updateBanner();
    }
  } catch (_) {}
  finally { pauseInFlight = false; }
}

function startPausePolling() {
  if (pauseTimer) return;
  setTimeout(refreshPause, 1500);
  pauseTimer = setInterval(refreshPause, 30 * 1000);
}

function stopPausePolling() {
  if (pauseTimer) {
    clearInterval(pauseTimer);
    pauseTimer = null;
  }
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

function getCsrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)galleryvault_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}
async function api(method, path, body) {
  const opts = { method, credentials: "include", headers: {} };
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf) opts.headers["X-CSRF-Token"] = csrf;
  }
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (err) {
    if (!navigator.onLine || err.name === "TypeError") {
      const netMsg = t("networkError");
      toast(netMsg);
      throw new Error(netMsg);
    }
    throw err;
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") return null;
  let text = "";
  try { text = await res.text(); } catch (_) {}
  let data = null;
  if (text) { try { data = JSON.parse(text); } catch (_) {} }
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || text || res.statusText;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  // Empty body on success -> null, JSON object/array -> parsed, otherwise raw text
  if (data !== null) return data;
  return text ? text : null;
}

async function checkAuth() {
  try {
    const session = await api("GET", "/api/auth/session");
    app.authenticated = true;
    app.session = session || {};
    app.paused = false;
    $topbar().hidden = false;
    updateBanner();
    // Cookie health from session may be stale/"unknown" if startup probe
    // hasn't finished yet — fetch authoritative health once after login
    // and start periodic polling (every 10 min) while authenticated.
    {
      const ch = app.session && app.session.cookie_health;
      const needsRefresh = !ch || ch.state === "unknown" || ch.state == null;
      if (needsRefresh) {
        refreshCookieHealth();
      } else {
        // Even if session carries a state, refresh shortly in case it
        // changed since server start (server also polls every 30 min).
        setTimeout(refreshCookieHealth, 1500);
      }
      startCookieHealthPolling();
    }
    // Global pause polling (30s)
    {
      refreshPause();
      startPausePolling();
    }
    // Normalise the address bar: after logging in the SPA is served at /login
    // (the middleware redirect target) but the app lives at "/"; rewrite the
    // path so the URL reads e.g. /#/browse instead of /login#/browse.
    if (location.pathname.endsWith("/login")) {
      history.replaceState(null, "", "/" + location.hash);
    }
    if (!location.hash || location.hash === "#/" || location.hash === "#/login") {
      location.hash = app.session.must_change_password ? "#/welcome" : "#/browse";
    }
    router();
  } catch (_) {
    app.authenticated = false;
    app.session = {};
    app.paused = false;
    $topbar().hidden = true;
    stopCookieHealthPolling();
    stopPausePolling();
    renderLogin();
  }
}

async function doLogin(password) {
  const res = await fetch("/login", {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "password=" + encodeURIComponent(password || ""),
  });
  if (!res.ok) {
    app.authenticated = false;
    $topbar().hidden = true;
    toast(t("wrong"));
    renderLogin();
    return;
  }
  await checkAuth();
  if (!app.authenticated) toast(t("wrong"));
}

async function doLogout() {
  stopCookieHealthPolling();
  stopPausePolling();
  await fetch("/logout", { method: "POST", credentials: "include" });
  app.authenticated = false;
  app.paused = false;
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
  if (app.view === "updates") {
    if (parts[1] === "ignored") { app.view = "updignored"; }
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
  if (app.view !== "updates" && app.view !== "updignored" && updatesTimer) { clearInterval(updatesTimer); updatesTimer = null; }
  if (app.view !== "downloads" && dlTimer) { clearInterval(dlTimer); dlTimer = null; }
  if (app.view !== "logs" && logTimer) { clearInterval(logTimer); logTimer = null; }
  if (app.view !== "favlist") selFav.clear();
  if (app.view !== "favmanage" && app.view !== "favignored") { selDup.clear(); }
  if (app.view !== "recycle") selRecycle.clear();
  if (app.view !== "integrity") selIntegrity.clear();
  if (app.view !== "reader" && readerFsActive) exitReaderFullscreen();
  stopInfinite();
  beforeRender(app.view);
  switch (app.view) {
    case "browse": renderBrowse(); break;
    case "library": renderLibrary(); break;
    case "gallery": renderGallery(); break;
    case "reader": renderReader(); break;
    case "tags": renderTags(); break;
    case "history": renderHistory(); break;
    case "downloads": renderDownloads(); break;
    case "logs": renderLogs(); break;
    case "settings": renderSettings(); break;
    case "duplicates": renderDuplicates(); break;
    case "recycle": renderRecycle(); break;
    case "integrity": renderIntegrity(); break;
    case "welcome": renderWelcome(); break;
    case "favorites": renderFavorites(); break;
    case "favmanage": renderFavManage(); break;
    case "favignored": renderFavIgnored(); break;
    case "favlist": renderFavList(); break;
    case "updates": renderUpdates(); break;
    case "updignored": renderUpdateIgnored(); break;
    default: renderBrowse();
  }
  afterRender(app.view);
  bindTagSuggest();
  bindReaderKeys();
}

// --- Phase 1 render governance (renderView + hooks) ---
let currentViewCleanup = null;

function beforeRender(view) {
  if (currentViewCleanup) {
    try { currentViewCleanup(); } catch (_) {}
    currentViewCleanup = null;
  }
  stopInfinite();
  if (view !== "reader") {
    try { window.scrollTo({ top: 0, left: 0, behavior: "instant" }); }
    catch (_) { window.scrollTo(0, 0); }
  }
}

function afterRender(view) {
  // placeholder for future: bind common, a11y etc.
}

function renderView(html) {
  beforeRender(app.view);
  $view().innerHTML = html || "";
  afterRender(app.view);
}
