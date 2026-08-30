"use strict";

// views/updates.js — Phase 1 continue (updates + helpers)
// extracted from app.js

async function renderUpdates() {
  const page = app.query.page || "1";
  const state = app.query.state || "active";
  const selCount = selUpdate.size;
  const stateBtn = (s, label) =>
    `<button class="secondary${state === s ? " active-pill" : ""}" data-action="upd-state" data-state="${s}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">GALLERY UPDATES</p><h1>${esc(t("galleryUpdates"))}</h1>
    <p class="sub"><span id="upd-status">…</span></p></header>
    <div class="toolbar">
      <button class="primary" data-action="upd-update" type="button">${esc(t("updateSelected"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="upd-update-orig" type="button">${esc(t("updOrig"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="upd-archive" type="button">${esc(t("updArchive"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="upd-ignore" type="button">${esc(t("ignoreSelected"))}${selCount ? ` (${selCount})` : ""}</button>
      ${state === "failed" ? `<button class="secondary danger" data-action="upd-delete-selected" type="button">${esc(t("deleteSel"))}${selCount ? ` (${selCount})` : ""}</button>` : ""}
      <button class="secondary" data-action="upd-scan" type="button">${esc(t("scanNow"))}</button>
      <label class="checkbox" style="margin-left:12px"><input type="checkbox" data-action="upd-select-all"> ${esc(t("selectAll"))}</label>
      <a class="link-button" href="#/updates/ignored" style="margin-left:auto">${esc(t("updIgnoredPage"))}</a>
    </div>
    <div class="fav-state-filter">
      ${stateBtn("active", t("updStateActive"))}
      ${stateBtn("pending", t("updStatePending"))}
      ${stateBtn("downloading", t("updStateDownloading"))}
      ${stateBtn("failed", t("updStateFailed"))}
      ${stateBtn("all", t("updStateAll"))}
    </div>
    <div id="upd-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="upd-pager"></div>`;
  pollUpdatesStatus();
  try {
    const qs = `page=${encodeURIComponent(page)}&page_size=${prefPageSize()}&state=${encodeURIComponent(state)}`;
    const data = await api("GET", `/api/updates?${qs}`);
    const el = document.getElementById("upd-list");
    if (!data.items.length) { el.innerHTML = `<p>${esc(t("updNoUpdates"))}</p>`; }
    else {
      el.innerHTML = `<table class="table"><thead><tr><th></th><th></th><th>${esc(t("gallery"))}</th><th>${esc(t("gid"))}</th><th>${esc(t("favorites"))}</th><th>${esc(t("status"))}</th></tr></thead><tbody>`
        + data.items.map(updRow).join("") + `</tbody></table>`;
      document.querySelectorAll('#upd-list input[data-upd-id]').forEach(cb => {
        cb.checked = selUpdate.has(parseInt(cb.dataset.updId, 10));
        cb.addEventListener("change", () => {
          const id = parseInt(cb.dataset.updId, 10);
          if (cb.checked) selUpdate.add(id); else selUpdate.delete(id);
          updateUpdSelBtn();
        });
      });
      const allBtn = document.querySelector('[data-action="upd-select-all"]');
      if (allBtn) allBtn.addEventListener("change", e => updSelectAll(e.target.checked));
    }
    updPager("upd-pager", data, page, state);
  } catch (e) { document.getElementById("upd-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

function updRow(u) {
  const cover = u.cover_url ? `<img loading="lazy" src="${u.cover_url}" alt="">` : `<span class="badge">no cover</span>`;
  const retry = u.status === "failed"
    ? ` <button class="secondary" data-action="upd-retry" data-id="${u.id}" type="button">${esc(t("retry"))}</button>`
    : "";
  return `<tr data-upd-id="${u.id}" data-new-gid="${u.new_gid}">
    <td><input type="checkbox" data-upd-id="${u.id}" aria-label="${esc(t("select"))}"></td>
    <td><a class="upd-cover" href="${navHash("gallery", { id: u.gallery_id })}">${cover}</a></td>
    <td><a href="${navHash("gallery", { id: u.gallery_id })}">${esc(u.title)}</a></td>
    <td class="muted">${u.old_gid} <span class="muted">${esc(t("updToNewer"))}</span> ${u.new_gid}</td>
    <td><a class="badge" href="#/favorites/${u.favcat}">#${u.favcat}${u.favcat_name ? " " + esc(u.favcat_name) : ""}</a></td>
    <td><span class="badge upd-st-${u.status}">${esc(t(updStatusKey(u.status)))}</span>${retry}${u.error_message ? `<p class="muted">${esc(u.error_message)}</p>` : ""}</td>
  </tr>`;
}

function updPager(elId, data, page, state) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const total = data.total, pageSize = data.page_size || 24;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const cur = parseInt(page, 10) || 1;
  const qp = p => navHash("updates", {}, { page: p, page_size: pageSize, state });
  const parts = [];
  if (cur > 1) parts.push(`<a class="page-link" href="${qp(cur - 1)}">&lt;</a>`);
  for (let p = Math.max(1, cur - 2); p <= Math.min(pages, cur + 2); p++) {
    parts.push(p === cur
      ? `<strong class="cur">${p}</strong>`
      : `<a class="page-link" href="${qp(p)}">${p}</a>`);
  }
  if (cur < pages) parts.push(`<a class="page-link" href="${qp(cur + 1)}">&gt;</a>`);
  el.innerHTML = `${parts.join(" ")} ${pagerJump(cur, pages)} · ${esc(t("perPage"))} ${pageSizeSelect(pageSize, "updates")}`;
}

async function pollUpdatesStatus() {
  if (updatesTimer) clearInterval(updatesTimer);
  const tick = async () => {
    try {
      const st = await api("GET", "/api/updates/status");
      const el = document.getElementById("upd-status");
      if (!el) return;
      const counts = st.counts || {};
      const total = (counts.pending || 0) + (counts.downloading || 0) + (counts.failed || 0);
      const parts = [];
      if (st.detecting) parts.push(`<b>${esc(t("updScanning"))}</b>`);
      if (st.last_detected_at) parts.push(`${esc(t("updDetectedAt"))} ${fmtDate(st.last_detected_at)}`);
      if (st.last_error) parts.push(`<span class="error">${esc(st.last_error)}</span>`);
      parts.push(`<b>${total}</b>`);
      el.innerHTML = parts.join(" · ");
    } catch (_) { /* transient */ }
  };
  tick();
  updatesTimer = setInterval(tick, 5000);
}

function updSelectAll(checked) {
  selUpdate.clear();
  document.querySelectorAll('#upd-list input[data-upd-id]').forEach(cb => {
    cb.checked = checked;
    if (checked) selUpdate.add(parseInt(cb.dataset.updId, 10));
  });
  updateUpdSelBtn();
}

async function updScan() {
  try {
    await api("POST", "/api/updates/scan");
    router();
  } catch (e) { toast(e.message); }
}

async function updRunIds(ids, quality) {
  if (!ids.length) { toast(t("select")); return; }
  try {
    const body = { ids };
    if (quality) body.quality = quality;
    const r = await api("POST", "/api/updates/update", body);
    selUpdate.clear();
    toast(t("updateSelected") + ": " + (r.started || 0) + (r.skipped ? ` (skip ${r.skipped})` : ""));
    router();
  } catch (e) { toast(e.message); }
}

async function updRunSelected() {
  await updRunIds([...selUpdate]);
}

async function updRunSelectedOrig() {
  await updRunIds([...selUpdate], "original");
}

async function updArchiveSelected() {
  const ids = [...selUpdate];
  if (!ids.length) { toast(t("select")); return; }
  const gids = ids.map(id => {
    const el = document.querySelector(`#upd-list [data-upd-id="${id}"]`);
    return el ? parseInt(el.getAttribute("data-new-gid"), 10) : null;
  }).filter(Boolean);
  if (!gids.length) { toast(t("select")); return; }
  const tier = await showArchiveDialog(gids);
  if (!tier) return;
  try {
    const r = await api("POST", "/api/updates/update", { ids, archive: true, quality: tier });
    selUpdate.clear();
    toast(t("archiveQueued") + ": " + (r.started || 0) + (r.skipped ? ` (skip ${r.skipped})` : ""));
    router();
  } catch (e) { toast(e.message); }
}

async function updIgnoreSelected() {
  const ids = [...selUpdate];
  if (!ids.length) { toast(t("select")); return; }
  try {
    await api("POST", "/api/updates/ignore", { ids });
    selUpdate.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function updDeleteSelected() {
  const ids = [...selUpdate];
  if (!ids.length) { toast(t("select")); return; }
  if (!window.confirm(t("deleteSel") + " (" + ids.length + ")?")) return;
  try {
    await api("POST", "/api/updates/delete", { ids });
    selUpdate.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function updUnignore(ids) {
  if (!ids.length) { toast(t("select")); return; }
  try {
    await api("POST", "/api/updates/unignore", { ids });
    router();
  } catch (e) { toast(e.message); }
}

async function updUnignoreSelected() {
  const ids = [...document.querySelectorAll('#upd-ignored input[data-upd-id]:checked')]
    .map(cb => parseInt(cb.dataset.updId, 10));
  await updUnignore(ids);
}

async function renderUpdateIgnored() {
  let data;
  try { data = await api("GET", "/api/updates/ignored?page=1&page_size=500"); }
  catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
  $view().innerHTML = `
    <a class="link-button" href="#/updates">← ${esc(t("galleryUpdates"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">GALLERY UPDATES</p><h1>${esc(t("updIgnoredPage"))}</h1></header>
    <div class="toolbar">
      <button class="primary" data-action="upd-unignore-selected" type="button">${esc(t("updUnignoreSel"))}</button>
    </div>
    <div id="upd-ignored">${(data.items || []).length ? "" : `<p class="muted">${esc(t("updNone"))}</p>`}</div>`;
  const el = document.getElementById("upd-ignored");
  if (!(data.items || []).length) return;
  el.innerHTML = data.items.map(u => `
    <div class="panel" style="margin-top:10px;padding:10px 14px">
      <label class="checkbox" style="margin:0"><input type="checkbox" data-upd-id="${u.id}"> <a href="${navHash("gallery", { id: u.gallery_id })}">${esc(u.title)}</a></label>
      <span class="badge">${u.old_gid} → ${u.new_gid}</span>
      <button class="secondary" data-action="upd-unignore" data-id="${u.id}" type="button">${esc(t("updUnignore"))}</button>
    </div>`).join("");
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
