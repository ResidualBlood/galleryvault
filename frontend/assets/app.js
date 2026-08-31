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
