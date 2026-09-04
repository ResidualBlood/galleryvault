"use strict";

// events.js — 事件委托 (onClick/onSubmit/onChange + bind*)
// 扩展现有 document 级委托

async function onClick(e) {
  const notifWrap = document.getElementById("notif-wrap");
  if (notifWrap && !notifWrap.contains(e.target)) closeNotificationPanel();
  const moreWrap = document.getElementById("nav-more");
  if (moreWrap && !moreWrap.contains(e.target)) closeMorePanel();
  if (e.target.closest("#more-panel a")) closeMorePanel();
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const action = el.getAttribute("data-action");
  if (action === "toggle-lang") { toggleLang(); return; }
  if (action === "toggle-theme") { toggleTheme(); return; }
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
  if (action === "log-tab") { switchLogTab(el.getAttribute("data-tab")); return; }
  if (action === "refresh-system-logs") { fetchSystemLogs(); return; }
  if (action === "clear-system-logs") { clearSystemLogs(); return; }
  if (action === "cancel-task") { cancelTask(el.getAttribute("data-task")); return; }
  if (action === "clear-tag") { e.preventDefault(); location.hash = tagFilterHash([]); return; }
  if (action === "remove-tag") { e.preventDefault(); location.hash = removeTagHash(el.getAttribute("data-tag")); return; }
  if (action === "clear-history") { clearHistory(); return; }
  if (action === "clear-progress") { clearProgress(); return; }
  if (action === "cancel-download") { cancelDownload(el.getAttribute("data-id")); return; }
  if (action === "retry-download") { retryDownload(el.getAttribute("data-id")); return; }
  if (action === "delete-download") { deleteDownload(el.getAttribute("data-id")); return; }
  if (action === "dl-select-all") { selectAllDownloads(); return; }
  if (action === "dl-retry-selected") { retrySelectedDownloads(); return; }
  if (action === "dl-delete-selected") { deleteSelectedDownloads(); return; }
  if (action === "dl-clear-success") { clearSuccessDownloads(); return; }
  if (action === "dl-add-archive") { addArchiveFromInput(); return; }
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
  if (action === "favlist-move") { favListMove(parseInt(el.getAttribute("data-favcat"), 10)); return; }
  if (action === "favlist-unfav") { favListUnfavorite(el.getAttribute("data-favcat")); return; }
  if (action === "favlist-select-all") { favListSelectAll(); return; }
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
  if (action === "dupgal-scan") {
    scanLibrary().then(async (r) => {
      if (!r || r.status === "paused") return;
      for (let i = 0; i < 120; i++) {
        await new Promise(res => setTimeout(res, 1000));
        try {
          const st = await api("GET", "/api/scan");
          if (!st || !st.running) break;
        } catch (_) { break; }
      }
      await loadDuplicates();
      renderDuplicatesList();
    });
    return;
  }
  if (action === "dupgal-refresh") { loadDuplicates().then(renderDuplicatesList); return; }
  if (action === "dupgal-filter") {
    dupGalFilter = el.getAttribute("data-value") || "all";
    document.querySelectorAll('[data-action="dupgal-filter"]').forEach(b => {
      b.classList.toggle("active-pill", b.getAttribute("data-value") === dupGalFilter);
    });
    renderDuplicatesList();
    return;
  }
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
  if (action === "toggle-notifications") { toggleNotificationPanel(); return; }
  if (action === "toggle-more") { toggleMorePanel(); return; }
  if (action === "delete-gallery") { deleteGallery(el.getAttribute("data-id")); return; }
  if (action === "export-cbz") { exportGalleryCbz(el.getAttribute("data-id")); return; }
  if (action === "download-original") { downloadOriginalGallery(el.getAttribute("data-id"), el.getAttribute("data-gid"), false); return; }
  if (action === "download-original-archive") { downloadOriginalGallery(el.getAttribute("data-id"), el.getAttribute("data-gid"), true); return; }
  if (action === "favorite-gallery") { favoriteGallery(el); return; }
  if (action === "move-gallery-favorite") { moveGalleryFavorite(el); return; }
  if (action === "unfavorite-gallery") { unfavoriteGallery(el); return; }
  if (action === "clear-single-progress") {
    e.preventDefault();
    e.stopPropagation();
    clearSingleProgress(el.getAttribute("data-id"));
    return;
  }
  if (action === "toggle-tag-mode") {
    e.preventDefault();
    const curMode = (app.query.tag_mode === "or") ? "and" : "or";
    location.hash = navHash("library", {}, { ...app.query, tag_mode: curMode, page: undefined });
    return;
  }
  if (action === "filter-tag") {
    e.preventDefault();
    e.stopPropagation();
    const ns = el.getAttribute("data-ns") || "";
    const name = el.getAttribute("data-name") || "";
    if (!name) return;
    // Shift/Alt/Ctrl/Cmd+click → exclude tag (add "-ns:name"), otherwise include
    if (e.shiftKey || e.altKey || e.ctrlKey || e.metaKey) {
      location.hash = addExcludeTagHash(ns || null, name);
    } else {
      location.hash = addTagHash(ns || null, name);
    }
    return;
  }
  if (action === "toggle-pause") {
    e.preventDefault();
    try {
      const cur = await api("GET", "/api/pause");
      const next = !cur.paused;
      await api("POST", "/api/pause", { paused: next });
      app.paused = next;
      updateBanner();
      toast(next ? t("paused") : t("resume"));
      router();
    } catch (err) { toast(err.message); }
    return;
  }
  if (action === "lib-batch-fav") { libraryBatchAddFavorite(); return; }
  if (action === "discover-list") {
    e.preventDefault();
    const list = el.getAttribute("data-list") || "search";
    const next = { ...app.query, page: undefined };
    if (list === "search") delete next.list;
    else next.list = list;
    if (list !== "toplist") delete next.tl;
    location.hash = navHash("discover", {}, next);
    return;
  }
  if (action === "save-search") { saveCurrentSearch(); return; }
  if (action === "apply-search") { applySavedSearch(el); return; }
  if (action === "delete-search") { deleteSavedSearch(); return; }
  if (action === "lib-add-list") { libraryAddToList(); return; }
  if (action === "list-create") { createLocalList(); return; }
  if (action === "save-local") { saveGalleryLocal(); return; }
  if (action === "save-fav-note") { saveGalleryFavNote(); return; }
  if (action === "gallery-list-add") { galleryAddToList(el); return; }
  if (action === "gallery-list-remove") { galleryRemoveFromList(el); return; }
  if (action === "discover-dl") { discoverDownloadOne(el); return; }
  if (action === "discover-fav") { discoverFavoriteOne(el); return; }
  if (action === "disc-batch-dl") { discoverBatchDownload(); return; }
  if (action === "disc-batch-fav") { discoverBatchFavorite(); return; }
  if (action === "disc-clear") { selDiscover.clear(); renderCardCheckboxes(); router(); return; }
  if (action === "recycle-restore") { recycleRestore(); return; }
  if (action === "recycle-purge") { recyclePurge(); return; }
  if (action === "integrity-repair") { integrityRepair(); return; }
  if (action === "delete-filtered") { deleteFiltered(); return; }
  if (action === "sel-clear") { selGalleries.clear(); renderCardCheckboxes(); router(); return; }
  if (action === "sel-delete") { deleteSelected(); return; }
  if (action === "tag-ns") { e.preventDefault(); selectTagNamespace(el.getAttribute("data-ns")); return; }
  if (action === "reader-mode") { cycleReaderMode(); return; }
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
  if (action === "discover-search") {
    e.preventDefault();
    const getVal = (name) => {
      const el = form.elements[name];
      return el && el.value ? String(el.value).trim() : "";
    };
    const fCats = discoverFCatsFromForm(form);
    const minRating = getVal("min_rating");
    const quality = getVal("quality");
    const list = getVal("list") || app.query.list || "search";
    const tl = getVal("tl");
    location.hash = navHash("discover", {}, {
      ...(form.q.value.trim() ? { q: form.q.value.trim() } : {}),
      ...(fCats ? { category: fCats } : {}),
      ...(minRating ? { min_rating: minRating } : {}),
      ...(quality && quality !== "resample" ? { quality } : {}),
      ...(list && list !== "search" ? { list } : {}),
      ...(list === "toplist" && tl ? { tl } : {}),
    });
    return;
  }
  if (action === "library-search") {
    e.preventDefault();
    const getVal = (name) => {
      const el = form.elements[name];
      return el && el.value ? String(el.value).trim() : "";
    };
    const pageMin = getVal("page_min");
    const pageMax = getVal("page_max");
    const minRating = getVal("min_rating");
    const sizeMin = getVal("size_min");
    const sizeMax = getVal("size_max");
    const postedFrom = getVal("posted_from");
    const postedTo = getVal("posted_to");
    const uploader = getVal("uploader");
    const imageQuality = getVal("image_quality");
    const minLocal = getVal("min_local_rating");
    const listId = getVal("list_id");
    const language = getVal("language");
    let tags = app.query.tags || "";
    if (language) {
      const langTag = "language:" + language;
      const cur = parseTags(tags).filter(x => !x.startsWith("language:") && !x.startsWith("-language:"));
      cur.push(langTag);
      tags = cur.join(",");
    }
    location.hash = navHash("library", {}, {
      ...(form.q.value.trim() ? { q: form.q.value.trim() } : {}),
      ...(form.category.value ? { category: form.category.value } : {}),
      ...(form.order_by && form.order_by.value !== "id_desc" ? { order_by: form.order_by.value } : {}),
      ...(form.read_status && form.read_status.value ? { read_status: form.read_status.value } : {}),
      ...(pageMin ? { page_min: pageMin } : {}),
      ...(pageMax ? { page_max: pageMax } : {}),
      ...(minRating ? { min_rating: minRating } : {}),
      ...(sizeMin ? { size_min: sizeMin } : {}),
      ...(sizeMax ? { size_max: sizeMax } : {}),
      ...(postedFrom ? { posted_from: postedFrom } : {}),
      ...(postedTo ? { posted_to: postedTo } : {}),
      ...(uploader ? { uploader } : {}),
      ...(imageQuality ? { image_quality: imageQuality } : {}),
      ...(minLocal ? { min_local_rating: minLocal } : {}),
      ...(listId ? { list_id: listId } : {}),
      ...(tags ? { tags, tag_mode: app.query.tag_mode || "and", ...(app.query.tag_match && app.query.tag_match !== "exact" ? { tag_match: app.query.tag_match } : {}) } : {}),
    });
    return;
  }
  if (action === "favlist-search") {
    e.preventDefault();
    const favcat = app.params.id;
    location.hash = navHash("favlist", { id: favcat }, {
      ...(form.q.value.trim() ? { q: form.q.value.trim() } : {}),
      ...(form.order_by && form.order_by.value !== "last_seen_desc" ? { order_by: form.order_by.value } : {}),
      ...(app.query.state && app.query.state !== "all" ? { state: app.query.state } : {})
    });
    return;
  }
  if (action === "tags-search") { e.preventDefault(); location.hash = navHash("tags", {}, { ns: app.query.ns || "", q: form.q.value.trim() }); return; }
  if (action === "browse-search") { e.preventDefault(); location.hash = navHash("library", {}, { q: form.q.value.trim() }); return; }
  if (action === "settings-save") { e.preventDefault(); saveSettings(form); return; }
  if (action === "dl-add-urls") { e.preventDefault(); addDownloadsFromInput(form); return; }
  if (action === "reader-jump") {
    e.preventDefault();
    const input = form.querySelector("#reader-jump-input") || form.querySelector("input");
    if (input) {
      const val = parseInt(input.value, 10);
      if (!isNaN(val) && val >= 1) jumpToReaderPage(val - 1);
    }
    return;
  }
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

function dismissTagSuggest(e) {
  document.querySelectorAll(".tag-suggest").forEach(b => {
    if (!b.contains(e.target) && (!b.parentElement || !b.parentElement.contains(e.target))) {
      b.hidden = true;
    }
  });
}

function tokenCoveredByTag(token, name, display, tag) {
  const t = String(token || "").trim().toLowerCase();
  if (!t) return false;
  const isCjk = /[\u3400-\u9fff\uf900-\ufaff]/u.test(t);
  if (!isCjk && t.length < 2) return false;
  return [name, display, tag].some(s => s && String(s).toLowerCase().includes(t));
}

async function loadTagSuggest(q, box, input) {
  if (!box) return;
  try {
    const isCjk = /[\u3400-\u9fff\uf900-\ufaff]/u.test(q);
    const url = `/api/tags/search?q=${encodeURIComponent(q)}&page_size=8${isCjk ? "&zh=1" : ""}`;
    const data = await api("GET", url);
    const items = (data && data.items) || [];
    if (!items.length) { box.hidden = true; return; }
    box.innerHTML = items.map(it => {
      const display = tagText(it);
      return `
      <div class="suggest-item" data-tags="${esc(`${it.namespace}:${it.name}`)}" data-display="${esc(display)}">
        <span class="suggest-name">${esc(display)}</span>
        <span class="suggest-ns">${esc(nsLabel(it.namespace))} · ${it.usage_count}</span>
      </div>`;
    }).join("");
    box.hidden = false;
    box.querySelectorAll(".suggest-item").forEach(item => {
      item.addEventListener("click", () => {
        box.hidden = true;
        const tag = item.getAttribute("data-tags");
        const display = item.getAttribute("data-display") || "";
        const i = tag.indexOf(":");
        const ns = tag.slice(0, i);
        const name = tag.slice(i + 1);
        const form = input && input.closest("form");
        if (form && form.getAttribute("data-action") === "tags-search") {
          location.hash = navHash("tags", {}, {
            ...(name ? { q: name } : {}),
            ...(ns ? { ns } : {}),
          });
          return;
        }
        const remaining = (input ? input.value : "").split(/\s+/).map(s => s.trim())
          .filter(s => s && !tokenCoveredByTag(s, name, display, tag)).join(" ");
        if (input) input.value = remaining;
        const curTags = parseTags(app.query.tags);
        if (!curTags.includes(tag)) curTags.push(tag);
        const savedQ = app.query.q;
        if (remaining) app.query.q = remaining;
        else delete app.query.q;
        location.hash = tagFilterHash(curTags);
        if (savedQ) app.query.q = savedQ;
        else delete app.query.q;
      });
    });
  } catch (_) { box.hidden = true; }
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
      suggestTimer = setTimeout(() => loadTagSuggest(value, box, input), 200);
    });
    input.addEventListener("focus", () => {
      const value = input.value.trim();
      if (value) loadTagSuggest(value, box, input);
    });
    box.addEventListener("click", (e) => e.stopPropagation());
  });
  if (!window.__gvSuggestBound) {
    window.__gvSuggestBound = true;
    document.addEventListener("click", dismissTagSuggest);
  }
}

// onChange moved here too for completeness
function onChange(e) {
  const el = e.target;
  if (!el) return;
  if (el.matches("#syslog-runtime-level")) { changeRuntimeLogLevel(el.value); return; }
  if (el.matches("#syslog-filter-level")) { systemLogMinLevel = el.value; fetchSystemLogs(); return; }
  if (el.matches("#syslog-search-input")) { systemLogSearch = el.value; fetchSystemLogs(); return; }
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
  if (['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) return;

  // Allow navigation when focus is on the card, its wrapper, or an image inside
  const active = document.activeElement;
  let activeCard = null;
  if (active) {
    activeCard = active.closest ? active.closest('.gc') : null;
    if (!activeCard && active.classList && active.classList.contains('gc')) activeCard = active;
  }
  // If nothing focused but grid exists, allow arrow keys to focus first card
  if (!activeCard && ['ArrowRight','ArrowDown'].includes(e.key)) {
    const first = document.querySelector('#view .gc');
    if (first) { e.preventDefault(); first.focus(); return; }
  }
  if (!activeCard) return;
  e.preventDefault();
  const cards = Array.from(document.querySelectorAll('#view .gc'));
  const idx = cards.indexOf(activeCard);
  if (idx < 0) return;

  // Calculate dynamic grid columns
  let cols = 1;
  const gridEl = activeCard.closest('.gc-grid, .grid') || activeCard.parentElement;
  if (gridEl) {
    const style = window.getComputedStyle(gridEl);
    if (style.display === 'grid' || style.display === 'inline-grid') {
      const template = style.gridTemplateColumns;
      if (template && template !== 'none') {
        const count = template.split(/\s+/).filter(Boolean).length;
        if (count > 0) cols = count;
      }
    }
  }
  if (cols <= 1 && cards.length > 1) {
    const firstTop = cards[0].offsetTop;
    let count = 0;
    for (let i = 0; i < cards.length; i++) {
      if (Math.abs(cards[i].offsetTop - firstTop) < 4) count++;
      else break;
    }
    if (count > 0) cols = count;
  }

  let next = idx;
  if (e.key === 'ArrowRight') {
    next = Math.min(idx + 1, cards.length - 1);
  } else if (e.key === 'ArrowLeft') {
    next = Math.max(idx - 1, 0);
  } else if (e.key === 'ArrowDown') {
    if (idx + cols < cards.length) {
      next = idx + cols;
    }
  } else if (e.key === 'ArrowUp') {
    if (idx - cols >= 0) {
      next = idx - cols;
    }
  }
  if (next !== idx) cards[next].focus();
});

let _syslogSearchTimer = null;
document.addEventListener("input", e => {
  if (e.target && e.target.id === "syslog-search-input") {
    if (_syslogSearchTimer) clearTimeout(_syslogSearchTimer);
    _syslogSearchTimer = setTimeout(() => {
      systemLogSearch = e.target.value.trim();
      fetchSystemLogs();
    }, 300);
  }
});

// filter-tag keyboard: Enter/Space triggers same as click, Shift+Enter/Space excludes
document.addEventListener("keydown", e => {
  const el = e.target.closest && e.target.closest('[data-action="filter-tag"]');
  if (!el) return;
  if (e.key !== "Enter" && e.key !== " ") return;
  e.preventDefault();
  e.stopPropagation();
  const ns = el.getAttribute("data-ns") || "";
  const name = el.getAttribute("data-name") || "";
  if (!name) return;
  if (e.shiftKey || e.altKey || e.ctrlKey || e.metaKey) {
    location.hash = addExcludeTagHash(ns || null, name);
  } else {
    location.hash = addTagHash(ns || null, name);
  }
});

