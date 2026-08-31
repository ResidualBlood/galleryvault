"use strict";

// app.js — pure entry after Phase 1 extraction
// all renders + support moved to views/ + core/state/utils/components/events
// only shared scanLibrary + bootstrap remain here

const app = {
  authenticated: false, settings: null, session: {}, view: "browse", params: {}, query: {},
  lang: (localStorage.getItem("gv_lang") === "en" ? "en" : "zh"),
};
async function scanLibrary() {
  try {
    await api("POST", "/api/scan");
    toast(t("scanning"));
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function init() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("submit", onSubmit);
  document.addEventListener("fullscreenchange", onFullscreenChange);
  window.addEventListener("hashchange", router);
  await loadLocale(app.lang);
  updateLangButton();
  checkAuth();
}

init();

// Global namespace convergence for legacy vanilla scripts (Phase 0-3).
// All view/core modules currently pollute window; expose the canonical
// app object via window.GV so future type=module migration can import from
// a single entry. Script order in index.html is still required.
window.GV = window.GV || {};
window.GV.app = app;
if (typeof esc !== "undefined") window.GV.esc = esc;
if (typeof api !== "undefined") window.GV.api = api;
if (typeof router !== "undefined") window.GV.router = router;
if (typeof navHash !== "undefined") window.GV.navHash = navHash;
