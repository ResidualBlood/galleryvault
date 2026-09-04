"use strict";

// views/series.js — 系列作品管理视图 (Series)

async function renderSeries() {
  renderView(`
    <div id="series-view">
      <header>
        <p class="eyebrow">SERIES</p>
        <h1>${esc(t("seriesTitle"))}</h1>
        <p class="sub">${esc(t("seriesSub"))}</p>
      </header>
      <div class="toolbar" style="margin-bottom: 16px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <button class="btn btn-primary" data-action="series-create" type="button">${esc(t("seriesCreate"))}</button>
        <button class="btn btn-secondary" data-action="series-rebuild" type="button">🔄 ${esc(t("seriesRebuild"))}</button>
        <span id="series-stats" class="muted" style="margin-left: auto; font-size: 0.9rem;"></span>
      </div>
      <div id="series-list">
        <div class="grid gc-grid">${renderSkeleton(6)}</div>
      </div>
    </div>
  `);

  await loadSeriesList();
}

async function loadSeriesList() {
  const container = document.getElementById("series-list");
  if (!container) return;

  try {
    const data = await api("GET", "/api/series");
    const items = (data && data.items) || [];
    const statsEl = document.getElementById("series-stats");
    if (statsEl) {
      const totalGalleries = items.reduce((acc, it) => acc + (it.count || 0), 0);
      statsEl.textContent = `${items.length} ${t("groups") || "groups"} · ${totalGalleries} ${t("details") || "items"}`;
    }

    if (!items.length) {
      container.innerHTML = renderEmpty(t("seriesEmpty"));
      return;
    }

    app._libCache = app._libCache || new Map();
    container.innerHTML = items.map(s => {
      const isManual = !s.match_key;
      const tagBadge = isManual
        ? `<span class="badge">${esc(t("seriesManual") || "Manual")}</span>`
        : `<span class="badge">${esc(t("seriesAuto") || "Auto")}</span>`;

      const gList = s.galleries || [];
      for (const it of gList) {
        if (it && it.id != null) app._libCache.set(Number(it.id), { gid: it.gid, token: it.token, title: it.title });
      }

      const gridHtml = gList.length
        ? `<div class="grid gc-grid">${gList.map(galleryCard).join("")}</div>`
        : renderEmpty(t("noGalleries"));

      return `
        <div class="panel series-group" data-series-id="${s.id}" style="margin-top: 16px; padding: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid var(--line); padding-bottom: 10px; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <h3 style="margin: 0; font-size: 1.15rem;">${esc(s.name)}</h3>
              <span class="badge">${s.count || 0}</span>
              ${tagBadge}
            </div>
            <div class="toolbar" style="margin: 0; display: flex; gap: 6px;">
              <button class="btn btn-secondary btn-sm" data-action="series-add-item" data-series-id="${s.id}" type="button">${esc(t("seriesAddItem"))}</button>
              <button class="btn btn-secondary btn-sm danger" data-action="series-remove-item" data-series-id="${s.id}" type="button">${esc(t("seriesRemoveItem"))}</button>
              <button class="btn btn-secondary btn-sm" data-action="series-rename" data-series-id="${s.id}" type="button">${esc(t("seriesRename"))}</button>
              <button class="btn btn-danger btn-sm" data-action="series-delete" data-series-id="${s.id}" type="button">${esc(t("seriesDelete"))}</button>
            </div>
          </div>
          ${gridHtml}
        </div>
      `;
    }).join("");

    renderCardCheckboxes();
  } catch (err) {
    if (container) container.innerHTML = renderError(err.message || String(err));
  }
}

async function seriesCreate() {
  const name = window.prompt(t("seriesPromptName"));
  if (!name || !name.trim()) return;
  try {
    await api("POST", "/api/series", { name: name.trim() });
    toast(t("saveOk"));
    await loadSeriesList();
  } catch (err) {
    toast(err.message || String(err));
  }
}

async function seriesRebuild() {
  try {
    toast(t("loading"));
    const res = await api("POST", "/api/series/rebuild");
    const msg = (t("seriesRebuilt") || "Rebuild complete: {created} groups, {merged} merged")
      .replace("{created}", res.created ?? 0)
      .replace("{merged}", res.merged ?? 0);
    toast(msg);
    await loadSeriesList();
  } catch (err) {
    toast(err.message || String(err));
  }
}

async function seriesRename(seriesId) {
  const name = window.prompt(t("seriesPromptNewName"));
  if (!name || !name.trim()) return;
  try {
    await api("PATCH", `/api/series/${seriesId}`, { name: name.trim() });
    toast(t("saveOk"));
    await loadSeriesList();
  } catch (err) {
    toast(err.message || String(err));
  }
}

async function seriesDelete(seriesId) {
  if (!window.confirm(t("seriesConfirmDelete"))) return;
  try {
    await api("DELETE", `/api/series/${seriesId}`);
    toast(t("deleted") || "Deleted");
    await loadSeriesList();
  } catch (err) {
    toast(err.message || String(err));
  }
}

async function seriesAddItem(seriesId) {
  const input = window.prompt(t("seriesPromptGalleryIds"));
  if (!input || !input.trim()) return;
  const ids = input.split(/[,\s]+/).map(x => parseInt(x, 10)).filter(x => Number.isFinite(x) && x > 0);
  if (!ids.length) return;
  try {
    const res = await api("POST", `/api/series/${seriesId}/items`, { gallery_ids: ids });
    toast(`${t("saveOk")} (+${res.added || 0})`);
    await loadSeriesList();
  } catch (err) {
    toast(err.message || String(err));
  }
}

async function seriesRemoveItem(seriesId, galleryId) {
  let ids = [];
  if (galleryId) {
    ids = [galleryId];
  } else {
    const input = window.prompt(t("seriesPromptGalleryIds"));
    if (!input || !input.trim()) return;
    ids = input.split(/[,\s]+/).map(x => parseInt(x, 10)).filter(x => Number.isFinite(x) && x > 0);
  }
  if (!ids.length) return;
  if (!window.confirm(t("seriesConfirmRemove"))) return;
  try {
    await api("POST", `/api/series/${seriesId}/items/remove`, { gallery_ids: ids });
    toast(t("saveOk"));
    await loadSeriesList();
  } catch (err) {
    toast(err.message || String(err));
  }
}

// 监听 series 页面操作
document.addEventListener("click", e => {
  if (app.view !== "series") return;
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.getAttribute("data-action");
  if (action === "series-create") {
    e.preventDefault();
    seriesCreate();
  } else if (action === "series-rebuild") {
    e.preventDefault();
    seriesRebuild();
  } else if (action === "series-rename") {
    e.preventDefault();
    const sid = parseInt(btn.getAttribute("data-series-id"), 10);
    if (sid) seriesRename(sid);
  } else if (action === "series-delete") {
    e.preventDefault();
    const sid = parseInt(btn.getAttribute("data-series-id"), 10);
    if (sid) seriesDelete(sid);
  } else if (action === "series-add-item") {
    e.preventDefault();
    const sid = parseInt(btn.getAttribute("data-series-id"), 10);
    if (sid) seriesAddItem(sid);
  } else if (action === "series-remove-item") {
    e.preventDefault();
    const sid = parseInt(btn.getAttribute("data-series-id"), 10);
    const gidAttr = btn.getAttribute("data-gallery-id");
    const gid = gidAttr ? parseInt(gidAttr, 10) : null;
    if (sid) seriesRemoveItem(sid, gid);
  }
});
