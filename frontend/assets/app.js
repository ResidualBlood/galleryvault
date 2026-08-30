"use strict";

// I18N moved to /assets/core.js (loaded first in index.html)

const app = {
  authenticated: false, settings: null, session: {}, view: "browse", params: {}, query: {},
  lang: (localStorage.getItem("gv_lang") === "en" ? "en" : "zh"),
};

// renderCardCheckboxes moved to components.js
// $view/$topbar/sel*/timers moved to state.js

// core functions moved to /assets/core.js (t, esc, toast, api, auth, parse/nav/router etc.)

// Phase 1: renderWelcome/browse/library/gallery/reader/favorites/downloads moved to views/
// remaining (settings, logs, updates, tags, duplicates, history...) transitional here
// renderView + hooks active in core

// nsClass moved to utils.js
// (catLabel stays for now with galleryCard)

// galleryCard moved to components.js
// galleryGrid moved to utils.js (Phase 1)

// --- utils moved to utils.js (Phase 0 cleanup in Phase 1) ---
// stopInfinite, startInfinite, pageSizeSelect, jumpPage, pagerJump, gridPager,
// parseTags, prefPageSize, libraryContext, tagFilterHash, addTagHash, removeTagHash, tagFilterPills, catLabel, galleryGrid

// renderBrowse moved to assets/views/browse.js
// renderLibrary moved to assets/views/library.js

// renderGallery moved to assets/views/gallery.js

// renderReader + reader helpers moved to assets/views/reader.js (Phase 1)

// TAG_NAMESPACES moved to state.js

// tag helpers + renderTags + loads moved to assets/views/tags.js (Phase 1)

// renderHistory moved to assets/views/history.js (Phase 1)

// DL_STATUSES + dlTimer moved to state.js

// renderDownloads moved to assets/views/downloads.js

// fmtDur moved to utils.js


function field(label, inputHtml) {
  return `<label class="field"><span>${esc(label)}</span>${inputHtml}</label>`;
}

// EH_* moved to state.js

function ehBaseUrlControl(value, prefix) {
  const fixed = EH_BASE_URLS.some(o => o.v === value);
  const options = EH_BASE_URLS.map(o =>
    `<option value="${o.v}"${value === o.v ? " selected" : ""}>${o.label}</option>`
  ).join("") + `<option value="${EH_CUSTOM}"${fixed ? "" : " selected"}>${esc(t("custom"))}</option>`;
  return `<select name="${prefix}exhentai_base_url" data-eh-select>${options}</select>
  <input name="${prefix}exhentai_base_url_custom" data-eh-custom value="${fixed ? "" : esc(value || "")}" placeholder="https://proxy.exhentai.org"${fixed ? " hidden" : ""}>`;
}

function toggleEhCustom(select) {
  const input = select.parentElement.querySelector("[data-eh-custom]");
  if (input) input.hidden = select.value !== EH_CUSTOM;
}


async function refreshThumbsStatus() {
  const el = document.getElementById("thumbs-status");
  if (!el) return;
  try {
    const st = await api("GET", "/api/thumbs/status");
    if (st && st.running) el.textContent = t("thumbs");
    else if (st && (st.completed_at || st.succeeded)) {
      el.textContent = t("thumbsDone") + (st.succeeded ? ` (${st.succeeded})` : "");
    } else {
      el.textContent = t("thumbsHint");
    }
  } catch (_) { /* transient */ }
}

function collectSettings(form) {
  const val = n => form[n] ? form[n].value.trim() : "";
  const num = (n, d) => { const v = parseFloat(val(n)); return Number.isFinite(v) ? v : d; };
  const lines = a => a.split(/[\n,]/).map(x => x.trim()).filter(Boolean);
  const body = {
    library_roots: val("library_roots"),
    exhentai_base_url: val("exhentai_base_url") === EH_CUSTOM
      ? (val("exhentai_base_url_custom") || "https://exhentai.org")
      : val("exhentai_base_url"),
    http_proxy: val("http_proxy"),
    socks5_proxy: val("socks5_proxy"),
    download_root: val("download_root"),
    download_concurrency: Math.min(32, Math.max(1, num("download_concurrency", 2))),
    page_concurrency: Math.min(16, Math.max(1, num("page_concurrency", 4))),
    download_quality: val("download_quality") || "resample",
    archive_quality: val("archive_quality") || "resample",
    favorites_archive_max_pages: Math.max(0, Math.round(num("favorites_archive_max_pages", 0))),
    favorites_archive_enabled: form.favorites_archive_enabled.checked,
    archive_fallback_pages: form.archive_fallback_pages.checked,
    download_title: val("download_title") || "japanese",
    title_display: val("title_display") || "japanese",
    image_download_timeout_seconds: Math.max(1, Math.round(num("image_download_timeout_seconds", 120))),
    image_slow_warmup_seconds: Math.max(1, Math.round(num("image_slow_warmup_seconds", 30))),
    image_min_speed_kb_s: Math.max(1, Math.round(num("image_min_speed_kb_s", 20))),
    use_hah: form.use_hah.checked,
    download_favorites_enabled: form.download_favorites_enabled.checked,
    auto_sync_tags: form.auto_sync_tags.checked,
    generate_thumbnails: form.generate_thumbnails ? form.generate_thumbnails.checked : undefined,
    tag_sync_interval_seconds: Math.max(0.1, num("tag_sync_interval_seconds", 1)),
    tag_sync_concurrency: Math.min(32, Math.max(1, num("tag_sync_concurrency", 2))),
    telegram_chat_ids: lines(val("telegram_chat_ids")),
    telegram_allowed_user_ids: lines(val("telegram_allowed_user_ids")).map(Number).filter(Number.isFinite),
    telegram_notify_level: val("telegram_notify_level") || "summary",
    telegram_notify_lang: val("telegram_notify_lang") || app.lang,
    duplicate_policy: val("duplicate_policy") || "keep_first",
    auth_required: form.auth_required.checked,
    tag_translation_update_interval_minutes: Math.max(0, num("tag_translation_update_interval_minutes", 720)),
  };
  for (const k of ["ipb_member_id", "ipb_pass_hash", "igneous", "telegram_bot_token"]) {
    if (val(k)) body[k] = val(k);
  }
  return body;
}

// FAV_MODES moved to state.js

// renderFavorites, renderFavList, favCard, renderFavPager moved to assets/views/favorites.js

// selDup/dup*/favCatNames moved to state.js

async function loadFavNames() {
  if (Object.keys(favCatNames).length) return;
  try {
    const c = await api("GET", "/api/favorites/categories");
    (Array.isArray(c) ? c : []).forEach(x => { favCatNames[x.favcat] = x.name || ""; });
  } catch (_) {}
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

// fmtSize, fmtDate moved to utils.js

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

async function downloadMissingFavorites() {
  try {
    await api("POST", "/api/favorites/download-missing");
    toast(t("downloadMissingStarted"));
    if (app.view === "favorites") pollFavoriteRings();
    else location.hash = "#/logs";
  } catch (e) { toast(e.message); }
}

// onClick / onSubmit / toggleLang moved to events.js


async function randomGallery() {
  try { const d = await api("GET", "/api/galleries/random"); location.hash = navHash("gallery", { id: d.id }); }
  catch (e) { toast(e.message); }
}

// logTimer moved to state.js


async function clearHistory() {
  try { await api("DELETE", "/api/history"); renderHistory(); }
  catch (e) { toast(e.message); }
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

async function downloadOriginalGallery(id, gid, archive) {
  if (archive) {
    const tier = await showArchiveDialog([parseInt(gid, 10)], { lockTier: "original" });
    if (!tier) return;
  }
  try {
    await api("POST", `/api/galleries/${id}/download-original`, { archive });
    toast(t(archive ? "dlOrigArchiveQueued" : "dlOrigQueued"));
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
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!selected.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/favorites/download-selected", { favcat, gids: selected });
    toast(t("favDlQueued") + ": " + r.queued + (r.skipped ? " · " + t("favDlSkip") + ": " + r.skipped : ""));
  } catch (e) { toast(e.message); }
  selFav.clear();
}

async function favListDownloadOrig(favcat) {
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!selected.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/favorites/download-selected", { favcat, gids: selected, quality: "original" });
    toast(t("favDlQueued") + ": " + r.queued + (r.skipped ? " · " + t("favDlSkip") + ": " + r.skipped : ""));
  } catch (e) { toast(e.message); }
  selFav.clear();
}

async function favListArchive(favcat) {
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!selected.length) { toast(t("select")); return; }
  const tier = await showArchiveDialog(selected);
  if (!tier) return;
  try {
    const r = await api("POST", "/api/favorites/download-selected", { favcat, gids: selected, archive: true, quality: tier });
    toast(t("archiveQueued") + ": " + r.queued + (r.skipped ? " · " + t("archiveUnsupported") : ""));
  } catch (e) { toast(e.message); }
  selFav.clear();
}

function showArchiveDialog(gids, opts) {
  opts = opts || {};
  const lockTier = opts.lockTier || null;
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "gv-overlay";
    const tiersHtml = lockTier
      ? `<label><input type="radio" name="archive-tier" value="${lockTier}" checked> ${esc(t(lockTier === "original" ? "archiveTierOriginal" : "archiveTierResample"))}</label>`
      : `<label><input type="radio" name="archive-tier" value="original"> ${esc(t("archiveTierOriginal"))}</label>
        <label><input type="radio" name="archive-tier" value="resample"> ${esc(t("archiveTierResample"))}</label>`;
    overlay.innerHTML = `<div class="gv-modal" role="dialog" aria-modal="true">
      <h3>${esc(t("archiveTitle"))}</h3>
      <div class="gv-modal-body">${esc(t("loading"))}</div>
      <div class="gv-modal-foot">
        <span class="archive-funds"></span>
        <span class="archive-tiers">
          ${tiersHtml}
        </span>
        <button class="primary" data-archive-confirm disabled type="button">${esc(t("archiveConfirm"))}</button>
        <button class="secondary" data-archive-cancel type="button">${esc(t("cancel"))}</button>
      </div>
    </div>`;
    let settled = false;
    const close = (value) => {
      if (settled) return;
      settled = true;
      overlay.remove();
      resolve(value);
    };
    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("[data-archive-cancel]").addEventListener("click", () => close(null));
    overlay.querySelector("[data-archive-confirm]").addEventListener("click", () => {
      const tier = overlay.querySelector('input[name="archive-tier"]:checked');
      close(tier ? tier.value : null);
    });
    document.body.appendChild(overlay);
    api("POST", "/api/archives/preview", { gids })
      .then(data => {
        const bodyEl = overlay.querySelector(".gv-modal-body");
        const items = data && data.items ? data.items : [];
        if (!items.length) {
          bodyEl.innerHTML = `<p>${esc(t("archiveNoItems"))}</p>`;
          return;
        }
        const confirm = overlay.querySelector("[data-archive-confirm]");
        if (lockTier === "original") {
          const rows = items.map(it => {
            if (it.error) {
              return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td colspan="1"><span class="error">${esc(it.error)}</span></td></tr>`;
            }
            const orig = it.original_cost == null
              ? `<span class="muted">N/A</span>`
              : (it.original_available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + it.original_cost + " GP · " + fmtSize(it.original_size);
            return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td>${orig}</td></tr>`;
          }).join("");
          bodyEl.innerHTML = `<table class="table archive-table"><thead><tr><th>${esc(t("gallery"))}</th><th>${esc(t("archiveTierOriginal"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
          const first = items[0];
          confirm.disabled = !!(first && !first.error && first.original_cost != null && !first.original_available);
        } else {
          const rows = items.map(it => {
            if (it.error) {
              return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td colspan="2"><span class="error">${esc(it.error)}</span></td></tr>`;
            }
            const orig = it.original_cost == null
              ? `<span class="muted">N/A</span>`
              : (it.original_available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + it.original_cost + " GP · " + fmtSize(it.original_size);
            const res = it.resample_cost == null
              ? `<span class="muted">N/A</span>`
              : (it.resample_available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + it.resample_cost + " GP · " + fmtSize(it.resample_size);
            return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td>${orig}</td><td>${res}</td></tr>`;
          }).join("");
          bodyEl.innerHTML = `<table class="table archive-table"><thead><tr><th>${esc(t("gallery"))}</th><th>${esc(t("archiveTierOriginal"))}</th><th>${esc(t("archiveTierResample"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
          confirm.disabled = false;
        }
        if (data && data.funds != null) {
          overlay.querySelector(".archive-funds").textContent = t("archiveFunds") + ": " + data.funds + " GP";
        }
        if (!lockTier) {
          const defaultTier = app.settings && app.settings.archive_quality === "original" ? "original" : "resample";
          const radio = overlay.querySelector(`input[name="archive-tier"][value="${defaultTier}"]`);
          if (radio) radio.checked = true;
        }
      })
      .catch(err => {
        const bodyEl = overlay.querySelector(".gv-modal-body");
        bodyEl.innerHTML = `<p class="error">${esc(err.message || t("archivePreviewFail"))}</p>`;
      });
  });
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

// lastDupStatus moved to state.js

async function dupAction(deleteLocal) {
  const items = [...document.querySelectorAll('#dup-groups [data-dup-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.dupGid, 10));
  if (!items.length) { toast(t("select")); return; }
  const msg = deleteLocal ? t("confirmDupDelete") : t("confirmDupUnfav");
  if (!window.confirm(msg + " " + items.length)) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: items, delete_local: deleteLocal });
    let msg = t("unfavorited") + (r.cloud_ok ? "" : " · " + t("unfavoritedLocal"))
      + (r.deleted_local_galleries ? " · " + t("deleted") + " " + r.deleted_local_galleries : "");
    if (r.failed_deletions && r.failed_deletions.length) {
      msg += " · " + t("dupDeleteFail") + r.failed_deletions.length;
      console.warn("local delete failed:", r.failed_deletions);
    }
    toast(msg);
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

// --- Gallery updates (re-uploaded / new-version tracking) ------------------

// updatesTimer/selUpdate/UPD_* moved to state.js

function updStatusKey(st) { return UPD_STATUS_KEYS[st] || st; }

function updateUpdSelBtn() {
  const n = selUpdate.size;
  const labels = {
    "upd-update": t("updateSelected"),
    "upd-update-orig": t("updOrig"),
    "upd-archive": t("updArchive"),
    "upd-ignore": t("ignoreSelected"),
    "upd-delete-selected": t("deleteSel"),
  };
  for (const [action, base] of Object.entries(labels)) {
    const btn = document.querySelector(`[data-action="${action}"]`);
    if (btn) btn.textContent = base + (n ? ` (${n})` : "");
  }
}




async function deleteFiltered() {
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  const tag_mode = app.query.tag_mode || "or";
  if (!window.confirm(t("confirmDeleteFiltered"))) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    // Server-side filtered delete: pass the filter, not a resolved id list.
    const r = await api("POST", "/api/galleries/delete-filtered", {
      q, category, tags, tag_mode, delete_files: deleteFiles
    });
    toast(t("deleted") + ": " + (r.deleted !== undefined ? r.deleted : (r.matched || 0))
      + ((r.failed_deletions || []).length ? " · " + t("dupDeleteFail") + r.failed_deletions.length : ""));
    location.hash = navHash("library");
  } catch (e) { toast(e.message); }
}

async function deleteSelected() {
  const ids = [...selGalleries];
  if (!ids.length) { toast(t("deleteSel")); return; }
  if (!window.confirm(t("confirmDeleteSel") + " (" + ids.length + ")")) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    const r = await api("POST", "/api/galleries/delete-bulk", { ids, delete_files: deleteFiles });
    selGalleries.clear();
    toast(t("deleted") + ": " + (r.deleted !== undefined ? r.deleted : ids.length)
      + ((r.failed_deletions || []).length ? " · " + t("dupDeleteFail") + r.failed_deletions.length : ""));
    router();
  } catch (e) { toast(e.message); }
}

// bindTagSuggest moved to events.js

function dismiss(e) {
  document.querySelectorAll(".tag-suggest").forEach(box => {
    if (!e.target.closest(".search-box")) box.hidden = true;
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

function welcomeInputs() {
  const form = document.querySelector(".welcome .wizard");
  const v = n => { const el = form && form.querySelector(`[name="${n}"]`); return el ? el.value.trim() : ""; };
  return { v, form };
}

async function welcomeChangePassword() {
  const { v } = welcomeInputs();
  const current = v("current_password");
  const next = v("new_password");
  if (!next) { toast(t("newPassword")); return; }
  try {
    await api("POST", "/api/auth/change-password", { current, new: next });
    app.session.must_change_password = false;
    toast(t("changePwOk"));
    updateBanner();
    renderWelcome();
  } catch (e) { toast(e.message); }
}

async function welcomeSaveCookie() {
  const { v } = welcomeInputs();
  const baseSel = v("w_exhentai_base_url");
  const body = {
    exhentai_base_url: baseSel === EH_CUSTOM
      ? (v("w_exhentai_base_url_custom") || "https://exhentai.org")
      : baseSel,
  };
  for (const k of ["ipb_member_id", "ipb_pass_hash", "igneous"]) {
    if (v("w_" + k)) body[k] = v("w_" + k);
  }
  try {
    await api("POST", "/api/settings", body);
    app.settings = null;
    toast(t("saveOk"));
    renderWelcome();
  } catch (e) { toast(e.message); }
}

async function scanLibrary() {
  try {
    await api("POST", "/api/scan");
    toast(t("scanning"));
    pollLogs();
  } catch (e) { toast(e.message); }
}

function welcomeScan() { return scanLibrary(); }

async function welcomeFinish() {
  try {
    const st = await api("GET", "/api/onboarding/status");
    if (st.password_default) { toast(t("welcomePasswordTitle")); return; }
  } catch (_) { /* fall through */ }
  toast(t("welcomeDone"));
  location.hash = "#/browse";
}

function welcomeLater() { location.hash = "#/browse"; }

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
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function generateThumbnails() {
  try {
    const r = await api("POST", "/api/thumbs/generate");
    toast(t("genThumbs") + (r && r.queued ? ` (${r.queued})` : ""));
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function syncAllTags() {
  try {
    const r = await api("POST", "/api/tag-sync/start");
    toast(t("syncAllTags") + (r && r.queued ? ` (${r.queued})` : ""));
    pollLogs();
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

// onChange moved to events.js

function init() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("submit", onSubmit);
  document.addEventListener("fullscreenchange", onFullscreenChange);
  window.addEventListener("hashchange", router);
  updateLangButton();
  checkAuth();
}

init();
