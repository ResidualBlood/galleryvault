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
  if (action === "clear-progress") { clearProgress(); return; }
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

function dismissTagSuggest(e) {
  document.querySelectorAll(".tag-suggest").forEach(b => {
    if (!b.contains(e.target) && (!b.parentElement || !b.parentElement.contains(e.target))) {
      b.hidden = true;
    }
  });
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
        // Consume the clicked tag's text from the input so it does not also
        // act as a title keyword; the remaining words stay the text query.
        const consumed = new Set([name, display, tag, ns ? `${ns}:${display}` : ""]
          .filter(Boolean).map(s => s.trim()));
        const remaining = (input ? input.value : "").split(/\s+/).map(s => s.trim())
          .filter(s => s && !consumed.has(s)).join(" ");
        if (input) input.value = remaining;
        const curTags = parseTags(app.query.tags);
        if (!curTags.includes(tag)) curTags.push(tag);
        location.hash = navHash("library", {}, {
          ...(remaining ? { q: remaining } : {}),
          ...(app.query.category ? { category: app.query.category } : {}),
          tags: curTags.join(","),
          tag_mode: "and",
        });
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
  let next = idx;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = Math.min(idx + 1, cards.length - 1);
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = Math.max(idx - 1, 0);
  if (next !== idx) cards[next].focus();
});
