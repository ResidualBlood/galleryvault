"use strict";

// views/favorites.js — Phase 1 continue
// renderFavorites, renderFavList, favCard, renderFavPager moved from app.js

async function renderFavorites() {
  $view().innerHTML = `
    <header><p class="eyebrow">EXHENTAI FOLDERS</p><h1>${esc(t("favcatTitle"))}</h1>
    <p class="sub">${esc(t("favcatSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="favcats-save" type="button">${esc(t("save"))}</button>
      <button class="secondary" data-action="favcats-sync" type="button">${esc(t("syncFavcats"))}</button>
      <button class="secondary" data-action="favcats-check-all" type="button">${esc(t("checkAll"))}</button>
      <button class="secondary" data-action="favcats-download-missing" type="button">${esc(t("downloadMissing"))}</button>
      <a class="secondary" href="#/updates" style="padding:8px 14px;border-radius:4px">${esc(t("galleryUpdates"))}</a>
      <a class="secondary" href="#/favorites/manage" style="padding:8px 14px;border-radius:4px;margin-left:auto">${esc(t("favManage"))}</a>
    </div>
    <div id="fav-list"><p>${esc(t("loading"))}</p></div>`;
  try {
    const cats = await api("GET", "/api/favorites/categories");
    (Array.isArray(cats) ? cats : []).forEach(c => { favCatNames[c.favcat] = c.name || ""; });
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
        <thead><tr><th scope="col">${esc(t("favorites"))}</th><th scope="col">${esc(t("favCount"))}</th><th scope="col">${esc(t("favSize"))}</th><th scope="col">${esc(t("enabled"))}</th><th scope="col">${esc(t("mode"))}</th><th scope="col">${esc(t("intervalMin"))}</th><th scope="col"></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="7">—</td></tr>`}</tbody>
      </table>`;
    pollFavoriteRings();
  } catch (e) { document.getElementById("fav-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

// favTimer + selFav moved to state.js

async function renderFavList() {
  const favcat = parseInt(app.params.id, 10);
  if (isNaN(favcat)) { location.hash = "#/favorites"; return; }
  const page = app.query.page || "1";
  const state = app.query.state || "all";
  const q = app.query.q || "";
  const order_by = app.query.order_by || "last_seen_desc";
  const selCount = selFav.size;
  const from = app.query.from;
  const backLinks = `<a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>`
    + (from ? ` <a class="link-button" href="#/gallery/${esc(from)}">← ${esc(t("backToGallery"))}</a>` : "");
  const stateBtn = (s, label) =>
    `<button class="secondary${state === s ? " active-pill" : ""}" data-action="favlist-state" data-state="${s}" type="button">${esc(label)}</button>`;
  await loadFavNames();
  const folderName = (favCatNames[favcat] || "").trim();
  const folderTitle = folderName
    ? `${esc(folderName)} <span class="badge">#${favcat}</span>`
    : `#${favcat}`;
  $view().innerHTML = `
    <div class="toolbar" style="margin-bottom:0">
      ${backLinks}
    </div>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITE FOLDER</p><h1>${folderTitle}</h1>
    <p class="sub">${esc(t("favListSub"))}</p></header>
    <form class="toolbar" data-action="favlist-search" style="margin-bottom:8px;">
      <div class="search-box">
        <input name="q" value="${esc(q)}" placeholder="${esc(t("favSearchPlaceholder"))}" autocomplete="off">
      </div>
      <select name="order_by">
        <option value="last_seen_desc"${order_by === "last_seen_desc" ? " selected" : ""}>${esc(t("orderDefault"))}</option>
        <option value="first_seen_desc"${order_by === "first_seen_desc" ? " selected" : ""}>${esc(t("orderFirstSeen"))}</option>
        <option value="posted_at_desc"${order_by === "posted_at_desc" ? " selected" : ""}>${esc(t("orderPosted"))}</option>
        <option value="title_asc"${order_by === "title_asc" ? " selected" : ""}>${esc(t("orderTitle"))}</option>
        <option value="file_size_desc"${order_by === "file_size_desc" ? " selected" : ""}>${esc(t("orderSize"))}</option>
      </select>
      <button class="btn btn-primary" type="submit">${esc(t("search"))}</button>
    </form>
    <div class="toolbar">
      <button class="primary" data-action="favlist-download" data-favcat="${favcat}" type="button">${esc(t("favDl"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-download-orig" data-favcat="${favcat}" type="button">${esc(t("favDlOrig"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-archive" data-favcat="${favcat}" type="button">${esc(t("favDlArchive"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-move" data-favcat="${favcat}" type="button">${esc(t("favMove"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary danger" data-action="favlist-unfav" data-favcat="${favcat}" type="button">${esc(t("favRemove"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-clear" type="button">${esc(t("clearSel"))}</button>
      <span class="fav-state-filter">
        ${stateBtn("all", t("favStateAll"))}
        ${stateBtn("local", t("favStateLocal"))}
        ${stateBtn("cloud", t("favStateCloud"))}
      </span>
    </div>
    <div id="fav-items"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="favlist-pager"></div>`;
  try {
    const params = new URLSearchParams({
      page,
      page_size: String(prefPageSize()),
      state,
      ...(q ? { q } : {}),
      ...(order_by && order_by !== "last_seen_desc" ? { order_by } : {})
    });
    const data = await api("GET", `/api/favorites/${favcat}/items?${params.toString()}`);
    const el = document.getElementById("fav-items");
    if (!data.items.length) { el.innerHTML = `<p>${esc(t("noGalleries"))}</p>`; }
    else {
      el.innerHTML = `<div class="grid gc-grid">` + data.items.map(favCard).join("") + `</div>`;
      document.querySelectorAll('#fav-items input[data-fav-gid]').forEach(cb => {
        cb.checked = selFav.has(parseInt(cb.dataset.favGid, 10));
      });
      renderCardCheckboxes();
      startInfinite("fav-items", async (p) => {
        const pParams = new URLSearchParams({
          page: String(p),
          page_size: String(prefPageSize()),
          state,
          ...(q ? { q } : {}),
          ...(order_by && order_by !== "last_seen_desc" ? { order_by } : {})
        });
        return await api("GET", `/api/favorites/${favcat}/items?${pParams.toString()}`);
      }, favCard);
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
      <div class="gc-title">${esc(it.title || ("gid " + it.gid))}${size}${it.note ? `<div class="sub">${esc(it.note)}</div>` : ""}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-fav-gid="${it.gid}"${selFav.has(it.gid) ? " checked" : ""}></label>
  </div>`;
}

function renderFavPager(elId, data, page) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const favcat = parseInt(app.params.id, 10);
  const state = app.query.state || "all";
  const q = app.query.q || "";
  const order_by = app.query.order_by || "last_seen_desc";
  const total = data.total, pageSize = data.page_size || 24;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const cur = parseInt(page, 10) || 1;
  const qp = p => navHash("favlist", { id: favcat }, {
    page: p,
    page_size: pageSize,
    ...(state !== "all" ? { state } : {}),
    ...(q ? { q } : {}),
    ...(order_by !== "last_seen_desc" ? { order_by } : {})
  });
  const parts = [];
  if (cur > 1) parts.push(`<a class="page-link" href="${qp(cur - 1)}">&lt;</a>`);
  for (let p = Math.max(1, cur - 2); p <= Math.min(pages, cur + 2); p++) {
    parts.push(p === cur
      ? `<strong class="cur" aria-current="page">${p}</strong>`
      : `<a class="page-link" href="${qp(p)}">${p}</a>`);
  }
  if (cur < pages) parts.push(`<a class="page-link" href="${qp(cur + 1)}">&gt;</a>`);
  el.innerHTML = `${parts.join(" ")} ${pagerJump(cur, pages)} · ${esc(t("perPage"))} ${pageSizeSelect(pageSize, "favlist")}`;
}

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

async function favListMove(favcat) {
  const items = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!items.length) { toast(t("select")); return; }
  const targetFavcat = await showMoveFavoritesDialog(items, favcat);
  if (targetFavcat == null || targetFavcat === favcat) return;
  try {
    const r = await api("POST", "/api/favorites/move", { gids: items, target_favcat: targetFavcat });
    if (r.cloud_ok) {
      toast(t("favMoved"));
    } else {
      const failedCount = (r.cloud_failed || []).length;
      toast(t("favMovedPartial").replace("{count}", r.local_moved).replace("{failed}", failedCount));
    }
    selFav.clear();
    router();
  } catch (e) { toast(e.message); }
}
