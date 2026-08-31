"use strict";

// events.js — 事件委托 (onClick/onSubmit/onChange + bind*)
// 扩展现有 document 级委托

function onClick(e) {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const action = el.getAttribute("data-action");
  if (action === "toggle-lang") { toggleLang(); return; }
  if (action === "logout") { doLogout(); return; }
  if (action === "random") { randomGallery(); return; }
  if (action === "toggle-nav") {
    const nav = document.getElementById('topbar');
    if (nav) {
      nav.classList.toggle('nav-open');
      const expanded = nav.classList.contains('nav-open');
      el.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
    return;
  }
  if (action === "scan") { scanLibrary(); return; }
  if (action === "welcome-change-password") { welcomeChangePassword(); return; }
  if (action === "welcome-save-cookie") { welcomeSaveCookie(); return; }
  if (action === "welcome-test-exhentai") { testExhentai(); return; }
  if (action === "welcome-scan") { welcomeScan(); return; }
  if (action === "welcome-check-favs") { checkAllFavorites(); return; }
  if (action === "welcome-finish") { welcomeFinish(); return; }
  if (action === "welcome-later") { welcomeLater(); return; }
  if (action === "cancel-task") { cancelTask(el.getAttribute("data-task")); return; }
  if (action === "clear-tag") { e.preventDefault(); location.hash = navHash("library", {}, { q: app.query.q || "", category: app.query.category || "" }); return; }
  if (action === "remove-tag") { e.preventDefault(); location.hash = removeTagHash(el.getAttribute("data-tag")); return; }
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
  if (action === "favcats-download-missing") { downloadMissingFavorites(); return; }
  if (action === "favlist-state") { e.preventDefault(); location.hash = navHash("favlist", { id: app.params.id }, { ...app.query, state: el.getAttribute("data-state") || "all", page: undefined }); return; }
  if (action === "favcat-check") { checkFavoriteCategory(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-download") { favListDownload(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-download-orig") { favListDownloadOrig(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-archive") { favListArchive(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-unfav") { favListUnfavorite(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-clear") { selFav.clear(); router(); return; }
  if (action === "upd-scan") { updScan(); return; }
  if (action === "upd-state") { e.preventDefault(); location.hash = navHash("updates", {}, { state: el.getAttribute("data-state") || "active", page: undefined }); return; }
  if (action === "upd-update") { updRunSelected(); return; }
  if (action === "upd-update-orig") { updRunSelectedOrig(); return; }
  if (action === "upd-archive") { updArchiveSelected(); return; }
  if (action === "upd-ignore") { updIgnoreSelected(); return; }
  if (action === "upd-delete-selected") { updDeleteSelected(); return; }
  if (action === "upd-retry") { updRunIds([parseInt(el.getAttribute("data-id"), 10)]); return; }
  if (action === "upd-unignore") { updUnignore([parseInt(el.getAttribute("data-id"), 10)]); return; }
  if (action === "upd-unignore-selected") { updUnignoreSelected(); return; }
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
  if (action === "dupgal-scan") { scanLibrary(); return; }
  if (action === "dupgal-refresh") { loadDuplicates().then(renderDuplicatesList); return; }
  if (action === "dupgal-filter") { dupGalFilter = el.getAttribute("data-value") || "all"; renderDuplicatesList(); return; }
  if (action === "dupgal-keep") { dupGalResolve(el.getAttribute("data-gid"), el.getAttribute("data-path"), false); return; }
  if (action === "dupgal-keep-del") { dupGalResolve(el.getAttribute("data-gid"), el.getAttribute("data-path"), true); return; }
  if (action === "dupgal-dismiss") { dupGalSetStatus(el.getAttribute("data-gid"), "dismiss"); return; }
  if (action === "dupgal-restore") { dupGalSetStatus(el.getAttribute("data-gid"), "restore"); return; }
  if (action === "sync-tags") { syncTags(el.getAttribute("data-id")); return; }
  if (action === "change-password") { e.preventDefault(); changePassword(); return; }
  if (action === "test-telegram") { testTelegram(); return; }
  if (action === "force-update") { forceUpdate(); return; }
  if (action === "gen-thumbs") { generateThumbnails(); return; }
  if (action === "sync-all-tags") { syncAllTags(); return; }
  if (action === "delete-gallery") { deleteGallery(el.getAttribute("data-id")); return; }
  if (action === "download-original") { downloadOriginalGallery(el.getAttribute("data-id"), el.getAttribute("data-gid"), false); return; }
  if (action === "download-original-archive") { downloadOriginalGallery(el.getAttribute("data-id"), el.getAttribute("data-gid"), true); return; }
  if (action === "unfavorite-gallery") { unfavoriteGallery(el); return; }
  if (action === "delete-filtered") { deleteFiltered(); return; }
  if (action === "sel-clear") { selGalleries.clear(); renderCardCheckboxes(); router(); return; }
  if (action === "sel-delete") { deleteSelected(); return; }
  if (action === "tag-ns") { e.preventDefault(); selectTagNamespace(el.getAttribute("data-ns")); return; }
  if (action === "reader-fit") { toggleReaderFit(); return; }
  if (action === "reader-fullscreen") { toggleReaderFullscreen(); return; }
}

function onSubmit(e) {
  const form = e.target;
  if (form.tagName !== "FORM") return;
  const action = form.getAttribute("data-action");
  if (action === "login") { e.preventDefault(); doLogin(form.password.value); return; }
  if (action === "change-password") { e.preventDefault(); changePassword(form); return; }
  if (action === "search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim() }); return; }
  if (action === "library-search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim(), category: form.category.value, ...(app.query.tags ? { tags: app.query.tags, tag_mode: "and" } : {}) }); return; }
  if (action === "tags-search") { e.preventDefault(); location.hash = navHash("tags", {}, { ns: app.query.ns || "", q: form.q.value.trim() }); return; }
  if (action === "browse-search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim() }); return; }
  if (action === "settings-save") { e.preventDefault(); saveSettings(form); return; }
}

async function toggleLang() {
  const targetLang = app.lang === "zh" ? "en" : "zh";
  await loadLocale(targetLang);
  app.lang = targetLang;
  localStorage.setItem("gv_lang", app.lang);
  updateLangButton();
  router();
}

window.addEventListener("offline", () => {
  toast(t("offlineNotice"));
});

window.addEventListener("online", () => {
  toast(t("onlineNotice"));
});

function bindTagSuggest() {
  const input = document.getElementById("global-search");
  const box = document.getElementById("tag-suggest-top");
  if (!input || !box) return;
  input.oninput = () => {
    clearTimeout(suggestTimer);
    const q = input.value.trim();
    if (!q) { box.hidden = true; return; }
    suggestTimer = setTimeout(async () => {
      try {
        const data = await api("GET", `/api/tags/search?q=${encodeURIComponent(q)}&page_size=8`);
        box.innerHTML = (data.items || []).map(t => `<div class="sug-item" data-action="pick-tag" data-tag="${esc(t.namespace ? t.namespace+':'+t.name : t.name)}">${esc(tagText(t))}</div>`).join("");
        box.hidden = false;
        box.querySelectorAll(".sug-item").forEach(it => it.onclick = () => {
          const tag = it.getAttribute("data-tag");
          const cur = parseTags(app.query.tags || "");
          if (!cur.includes(tag)) cur.push(tag);
          location.hash = tagFilterHash(cur);
          box.hidden = true;
        });
      } catch (_) { box.hidden = true; }
    }, 180);
  };
  document.addEventListener("click", ev => {
    if (!box.contains(ev.target) && ev.target !== input) box.hidden = true;
  });
}

// onChange moved here too for completeness
function onChange(e) {
  const el = e.target;
  if (!el) return;
  if (el.matches("select[data-eh-select]")) { toggleEhCustom(el); return; }
  if (el.matches(".page-jump")) {
    const last = parseInt(el.max, 10) || 1;
    jumpPage(el, last);
    return;
  }
  if (!el.matches(".page-size")) return;
  localStorage.setItem("gv_page_size", el.value);
  const view = el.getAttribute("data-view") || app.view;
  const params = (view === "gallery" || view === "favlist") ? { id: app.params.id } : {};
  const q = { ...app.query, page_size: el.value, page: undefined };
  Object.keys(q).forEach(k => { if (q[k] === undefined) delete q[k]; });
  location.hash = navHash(view, params, q);
}

// Phase 2 keyboard: / focuses global search (if not in input)
document.addEventListener('keydown', e => {
  if (e.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) {
    e.preventDefault();
    const s = document.getElementById('global-search') || document.querySelector('input[name="q"]');
    if (s) s.focus();
  }
});

// Phase 2 keyboard: arrow keys navigate .gc cards (when focused)
document.addEventListener('keydown', e => {
  if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) return;
  const active = document.activeElement;
  if (!active || !active.classList.contains('gc')) return;
  e.preventDefault();
  const cards = Array.from(document.querySelectorAll('#view .gc'));
  const idx = cards.indexOf(active);
  if (idx < 0) return;
  let next = idx;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = Math.min(idx + 1, cards.length - 1);
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = Math.max(idx - 1, 0);
  if (next !== idx) cards[next].focus();
});
