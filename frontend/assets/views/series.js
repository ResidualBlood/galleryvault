"use strict";

// views/series.js — 系列作品管理视图 (Series)

const selSeriesCloud = new Set();

function updateSeriesToolbarButtons() {
  const total = selGalleries.size + selSeriesCloud.size;
  document.querySelectorAll('[data-action="series-download"], [data-action="series-download-orig"], [data-action="series-archive"]').forEach(b => {
    const act = b.getAttribute("data-action");
    const base = act === "series-download" ? t("favDl")
      : act === "series-download-orig" ? t("favDlOrig")
      : t("favDlArchive");
    b.textContent = base + (total ? ` (${total})` : "");
  });
}

function seriesMemberCard(it) {
  const isLocal = !!it.is_local;
  const cat = it.category ? esc(catLabel(it.category)) : "";
  const cover = it.cover_url || null;
  const inner = cover
    ? `<img class="cover-bg" loading="lazy" src="${cover}" alt="" aria-hidden="true"><img class="cover-fg" loading="lazy" src="${cover}" alt="">`
    : `<div class="cover-placeholder" style="width:100%;height:100%;background:var(--panel-2);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">${esc(t("noCover") || "no cover")}</div>`;
  const stateBadge = isLocal
    ? `<span class="fav-state local">${esc(t("favLocal") || "Local")}</span>`
    : `<span class="fav-state cloud">${esc(t("favCloud") || "Cloud")}</span>`;
  const link = isLocal
    ? `href="${navHash("gallery", { id: it.gallery_id || it.id }, { from: currentFromPath() })}"`
    : `href="${esc(it.url || "#")}" target="_blank" rel="noopener"`;
  const check = isLocal
    ? `<label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-gallery-id="${it.gallery_id || it.id}" data-gid="${esc(it.gid || "")}"${selGalleries.has(it.gallery_id || it.id) ? " checked" : ""}></label>`
    : `<label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-series-gid="${it.gid}" data-favcat="${it.favcat != null ? it.favcat : ""}"${selSeriesCloud.has(it.gid) ? " checked" : ""}></label>`;

  return `<div class="gc-wrap" data-gid="${esc(it.gid || "")}" data-token="${esc(it.token || "")}">
    <a class="gc" ${link}>
      <div class="gc-cover">
        ${inner}
        ${stateBadge}
        ${cat ? `<span class="gc-cat">${cat}</span>` : ""}
        ${it.page_count ? `<span class="gc-pages">${it.page_count} P</span>` : ""}
      </div>
      <div class="gc-title">${esc(it.title || ("gid " + it.gid))}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}" data-action="filter-tag" data-ns="${esc(tg.namespace)}" data-name="${esc(tg.name)}" role="button" tabindex="0" title="${esc(tg.namespace ? tg.namespace + ':' + tg.name : tg.name)} — ${esc(t("tagFilterHint"))} / ${esc(t("tagExcludeHint"))}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    ${check}
  </div>`;
}

function getSeriesSelected() {
  const checkedCloud = [...document.querySelectorAll('#series-list input[data-series-gid]:checked')];
  const checkedLocal = [...document.querySelectorAll('#series-list input[data-gallery-id]:checked')];
  const cloudByFavcat = new Map();
  const cloudGids = [];
  for (const cb of checkedCloud) {
    const gid = parseInt(cb.getAttribute("data-series-gid"), 10);
    const favcat = parseInt(cb.getAttribute("data-favcat"), 10);
    if (!gid || isNaN(favcat)) continue;
    if (!cloudByFavcat.has(favcat)) cloudByFavcat.set(favcat, []);
    cloudByFavcat.get(favcat).push(gid);
    cloudGids.push(gid);
  }
  const localItems = [];
  for (const cb of checkedLocal) {
    const id = parseInt(cb.getAttribute("data-gallery-id"), 10);
    const gid = parseInt(cb.getAttribute("data-gid"), 10);
    if (id) localItems.push({ id, gid: isNaN(gid) ? null : gid });
  }
  return { checkedCloud, checkedLocal, cloudByFavcat, cloudGids, localItems };
}

function clearSeriesSelection() {
  selSeriesCloud.clear();
  selGalleries.clear();
  document.querySelectorAll('#series-list input[type="checkbox"]').forEach(cb => { cb.checked = false; });
  updateSeriesToolbarButtons();
}

async function seriesDownload() {
  const { cloudByFavcat, localItems } = getSeriesSelected();
  if (!cloudByFavcat.size && !localItems.length) { toast(t("select")); return; }
  let queued = 0;
  let skipped = 0;
  try {
    for (const [favcat, gids] of cloudByFavcat.entries()) {
      const r = await api("POST", "/api/favorites/download-selected", { favcat, gids });
      queued += r.queued || 0;
      skipped += r.skipped || 0;
    }
    for (const item of localItems) {
      try {
        await api("POST", `/api/galleries/${item.id}/redownload`);
        queued++;
      } catch {
        skipped++;
      }
    }
    toast(t("favDlQueued") + ": " + queued + (skipped ? " · " + t("favDlSkip") + ": " + skipped : ""));
  } catch (e) {
    toast(e.message || String(e));
  }
  clearSeriesSelection();
}

async function seriesDownloadOrig() {
  const { cloudByFavcat, localItems } = getSeriesSelected();
  if (!cloudByFavcat.size && !localItems.length) { toast(t("select")); return; }
  let queued = 0;
  let skipped = 0;
  try {
    for (const [favcat, gids] of cloudByFavcat.entries()) {
      const r = await api("POST", "/api/favorites/download-selected", { favcat, gids, quality: "original" });
      queued += r.queued || 0;
      skipped += r.skipped || 0;
    }
    for (const item of localItems) {
      try {
        await api("POST", `/api/galleries/${item.id}/download-original`, { archive: false });
        queued++;
      } catch {
        skipped++;
      }
    }
    toast(t("favDlQueued") + ": " + queued + (skipped ? " · " + t("favDlSkip") + ": " + skipped : ""));
  } catch (e) {
    toast(e.message || String(e));
  }
  clearSeriesSelection();
}

async function seriesArchive() {
  const { cloudByFavcat, cloudGids, localItems } = getSeriesSelected();
  if (!cloudByFavcat.size && !localItems.length) { toast(t("select")); return; }
  const allGids = [...cloudGids, ...localItems.map(x => x.gid).filter(Boolean)];
  const tier = await showArchiveDialog(allGids);
  if (!tier) return;
  let queued = 0;
  let skipped = 0;
  try {
    for (const [favcat, gids] of cloudByFavcat.entries()) {
      const r = await api("POST", "/api/favorites/download-selected", { favcat, gids, archive: true, quality: tier });
      queued += r.queued || 0;
      skipped += r.skipped || 0;
    }
    for (const item of localItems) {
      try {
        await api("POST", `/api/galleries/${item.id}/download-original`, { archive: true });
        queued++;
      } catch {
        skipped++;
      }
    }
    toast(t("archiveQueued") + ": " + queued + (skipped ? " · " + t("archiveUnsupported") : ""));
  } catch (e) {
    toast(e.message || String(e));
  }
  clearSeriesSelection();
}

async function renderSeries() {
  const showAll = app.query.show_all === "1";
  const showAllClass = showAll ? "btn btn-primary" : "btn btn-secondary";
  const showAllLabel = t("favStateAll") || "Show all";

  selSeriesCloud.clear();
  selGalleries.clear();

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
        <button class="${showAllClass}" data-action="series-toggle-all" type="button">${showAll ? "✓ " : ""}${esc(showAllLabel)}</button>
        <button class="btn btn-secondary" data-action="series-download" type="button">${esc(t("favDl"))}</button>
        <button class="btn btn-secondary" data-action="series-download-orig" type="button">${esc(t("favDlOrig"))}</button>
        <button class="btn btn-secondary" data-action="series-archive" type="button">${esc(t("favDlArchive"))}</button>
        <span id="series-stats" class="muted" style="margin-left: auto; font-size: 0.9rem;"></span>
      </div>
      <div class="pages pager" id="series-pager" style="margin-bottom: 12px;"></div>
      <div id="series-list">
        <div class="grid gc-grid">${renderSkeleton(6)}</div>
      </div>
      <div class="pages pager" id="series-pager-bottom" style="margin-top: 16px;"></div>
    </div>
  `);

  await loadSeriesList();
}

async function loadSeriesList() {
  const container = document.getElementById("series-list");
  if (!container) return;

  const showAll = app.query.show_all === "1";
  const page = Math.max(1, parseInt(app.query.page, 10) || 1);
  const pageSize = prefPageSize();

  const qs = new URLSearchParams();
  qs.set("page", String(page));
  qs.set("page_size", String(pageSize));
  if (showAll) qs.set("show_all", "1");

  try {
    const data = await api("GET", `/api/series?${qs.toString()}`);
    const items = (data && data.items) || [];
    const total = (data && typeof data.total === "number") ? data.total : items.length;
    const statsEl = document.getElementById("series-stats");
    if (statsEl) {
      const totalGalleries = items.reduce((acc, it) => acc + (it.count || 0), 0);
      statsEl.textContent = `${total} ${t("groups") || "groups"} · ${totalGalleries} ${t("details") || "items"}`;
    }

    const buildQuery = p => ({
      ...(p > 1 ? { page: p } : {}),
      ...(showAll ? { show_all: "1" } : {}),
      page_size: prefPageSize(),
    });
    gridPager("series-pager", data, buildQuery);
    gridPager("series-pager-bottom", data, buildQuery);

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
        if (it && it.is_local && it.gallery_id != null) {
          app._libCache.set(Number(it.gallery_id), { gid: it.gid, token: it.token, title: it.title });
        }
      }

      const gridHtml = gList.length
        ? `<div class="grid gc-grid">${gList.map(seriesMemberCard).join("")}</div>`
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
    updateSeriesToolbarButtons();
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

function showSeriesAddModal(seriesId) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "gv-overlay";
    overlay.innerHTML = `
      <div class="gv-modal" role="dialog" aria-modal="true" style="max-width: 540px; width: 90%;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); padding-bottom: 10px; margin-bottom: 14px;">
          <h3 style="margin: 0; font-size: 1.15rem;">${esc(t("seriesAddItem") || "添加作品到系列")}</h3>
          <button class="btn btn-secondary btn-sm" data-modal-close type="button" style="padding: 2px 8px;">✕</button>
        </div>
        <div class="gv-modal-body" style="display: flex; flex-direction: column; gap: 12px;">
          <div>
            <label class="form-label" style="display: block; margin-bottom: 6px; font-weight: 500;">${esc(t("seriesInputGidsHint") || "输入 gid（多个用逗号或空格分隔）：")}</label>
            <input type="text" class="form-input" id="series-manual-gids" placeholder="e.g. 123456, 789012" style="width: 100%; box-sizing: border-box;">
          </div>
          <div>
            <label class="form-label" style="display: block; margin-bottom: 6px; font-weight: 500;">${esc(t("seriesCloudCandidates") || "勾选未入组收藏：")}</label>
            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
              <input type="text" id="series-cand-search" class="form-input" placeholder="${esc(t("searchFavorites") || "搜索收藏夹...")}" style="flex: 1;">
              <button class="btn btn-secondary btn-sm" id="series-cand-search-btn" type="button">${esc(t("search") || "搜索")}</button>
            </div>
            <div id="series-cand-list" style="max-height: 220px; min-height: 80px; overflow-y: auto; border: 1px solid var(--line); border-radius: 4px; padding: 8px; display: flex; flex-direction: column; gap: 6px; background: var(--bg-card, var(--panel));">
              <div class="muted" style="font-size: 0.85rem; padding: 8px; text-align: center;">${esc(t("loading") || "Loading...")}</div>
            </div>
          </div>
        </div>
        <div class="gv-modal-foot" style="display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--line); padding-top: 12px; margin-top: 16px;">
          <button class="btn btn-secondary" data-modal-cancel type="button">${esc(t("cancel"))}</button>
          <button class="btn btn-primary" data-modal-submit type="button">${esc(t("confirm") || "确定添加")}</button>
        </div>
      </div>
    `;

    let settled = false;
    let cleanupFocus = null;
    const close = (val) => {
      if (settled) return;
      settled = true;
      if (cleanupFocus) cleanupFocus();
      overlay.remove();
      resolve(val);
    };

    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("[data-modal-close]").addEventListener("click", () => close(null));
    overlay.querySelector("[data-modal-cancel]").addEventListener("click", () => close(null));

    const listEl = overlay.querySelector("#series-cand-list");
    const searchInput = overlay.querySelector("#series-cand-search");
    const searchBtn = overlay.querySelector("#series-cand-search-btn");

    async function loadCandidates(q) {
      if (!listEl) return;
      listEl.innerHTML = `<div class="muted" style="font-size: 0.85rem; padding: 8px; text-align: center;">${esc(t("loading") || "Loading...")}</div>`;
      try {
        const url = `/api/series/${seriesId}/cloud-candidates` + (q ? `?q=${encodeURIComponent(q)}` : "");
        const res = await api("GET", url);
        const candidates = (res && res.items) || [];
        if (!candidates.length) {
          listEl.innerHTML = `<div class="muted" style="font-size: 0.85rem; padding: 8px; text-align: center;">${esc(t("noCandidates") || "无可选候选")}</div>`;
          return;
        }
        listEl.innerHTML = candidates.map(c => `
          <label style="display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 3px; cursor: pointer; user-select: none;" class="cand-row">
            <input type="checkbox" class="series-cand-cb" data-gid="${c.gid}">
            ${c.thumb ? `<img src="${esc(c.thumb)}" style="width: 36px; height: 36px; object-fit: cover; border-radius: 2px;" alt="">` : `<div style="width: 36px; height: 36px; background: var(--line); border-radius: 2px;"></div>`}
            <div style="flex: 1; min-width: 0;">
              <div style="font-size: 0.85rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${esc(c.title || "")}">${esc(c.title || ("gid " + c.gid))}</div>
              <div style="font-size: 0.75rem; color: var(--muted);">gid: ${c.gid}</div>
            </div>
          </label>
        `).join("");
      } catch (err) {
        listEl.innerHTML = `<div class="danger" style="font-size: 0.85rem; padding: 8px;">${esc(err.message || String(err))}</div>`;
      }
    }

    searchBtn.addEventListener("click", () => {
      loadCandidates(searchInput.value.trim());
    });
    searchInput.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        e.preventDefault();
        loadCandidates(searchInput.value.trim());
      }
    });

    overlay.querySelector("[data-modal-submit]").addEventListener("click", async () => {
      const manualInput = overlay.querySelector("#series-manual-gids");
      const manualGids = (manualInput ? manualInput.value : "")
        .split(/[,\s]+/)
        .map(x => parseInt(x, 10))
        .filter(x => Number.isFinite(x) && x > 0);
      const checkedGids = [...overlay.querySelectorAll(".series-cand-cb:checked")]
        .map(cb => parseInt(cb.getAttribute("data-gid"), 10))
        .filter(x => Number.isFinite(x) && x > 0);

      const allGids = [...new Set([...manualGids, ...checkedGids])];
      if (!allGids.length) {
        toast(t("select") || "请至少输入或勾选一个作品");
        return;
      }
      try {
        const res = await api("POST", `/api/series/${seriesId}/cloud-items`, { gids: allGids });
        const localCount = res.added_local || 0;
        const cloudCount = res.added_cloud || 0;
        const skipCount = res.skipped || 0;
        const msg = `${t("saveOk")} (+${localCount + cloudCount}` + (skipCount ? ` · skip: ${skipCount}` : "") + ")";
        toast(msg);
        close(true);
      } catch (err) {
        toast(err.message || String(err));
      }
    });

    document.body.appendChild(overlay);
    if (typeof trapModalFocus === "function") {
      cleanupFocus = trapModalFocus(overlay, close);
    }
    loadCandidates("");
  });
}

function showSeriesRemoveModal(seriesId, groupEl) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "gv-overlay";
    overlay.innerHTML = `
      <div class="gv-modal" role="dialog" aria-modal="true" style="max-width: 440px; width: 90%;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); padding-bottom: 10px; margin-bottom: 14px;">
          <h3 style="margin: 0; font-size: 1.15rem;">${esc(t("seriesRemoveItem") || "移出作品")}</h3>
          <button class="btn btn-secondary btn-sm" data-modal-close type="button" style="padding: 2px 8px;">✕</button>
        </div>
        <div class="gv-modal-body" style="display: flex; flex-direction: column; gap: 12px;">
          <div>
            <label class="form-label" style="display: block; margin-bottom: 6px; font-weight: 500;">${esc(t("seriesRemoveGidsHint") || "输入要移出的作品 gid（多个用逗号或空格分隔）：")}</label>
            <input type="text" class="form-input" id="series-remove-gids" placeholder="e.g. 123456, 789012" style="width: 100%; box-sizing: border-box;">
          </div>
        </div>
        <div class="gv-modal-foot" style="display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--line); padding-top: 12px; margin-top: 16px;">
          <button class="btn btn-secondary" data-modal-cancel type="button">${esc(t("cancel"))}</button>
          <button class="btn btn-danger" data-modal-submit type="button">${esc(t("seriesRemoveItem") || "确定移出")}</button>
        </div>
      </div>
    `;

    let settled = false;
    let cleanupFocus = null;
    const close = (val) => {
      if (settled) return;
      settled = true;
      if (cleanupFocus) cleanupFocus();
      overlay.remove();
      resolve(val);
    };

    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("[data-modal-close]").addEventListener("click", () => close(null));
    overlay.querySelector("[data-modal-cancel]").addEventListener("click", () => close(null));

    overlay.querySelector("[data-modal-submit]").addEventListener("click", async () => {
      const input = overlay.querySelector("#series-remove-gids");
      const gids = (input ? input.value : "")
        .split(/[,\s]+/)
        .map(x => parseInt(x, 10))
        .filter(x => Number.isFinite(x) && x > 0);
      if (!gids.length) {
        toast(t("select") || "请输入 gid");
        return;
      }
      try {
        const localIds = [];
        const cloudGids = [];
        for (const gid of gids) {
          const localInput = groupEl ? groupEl.querySelector(`input[data-gallery-id][data-gid="${gid}"]`) : null;
          if (localInput) {
            const lid = parseInt(localInput.getAttribute("data-gallery-id"), 10);
            if (lid) localIds.push(lid);
          } else {
            cloudGids.push(gid);
          }
        }
        if (localIds.length > 0) {
          await api("POST", `/api/series/${seriesId}/items/remove`, { gallery_ids: localIds });
        }
        if (cloudGids.length > 0) {
          await api("POST", `/api/series/${seriesId}/cloud-items/remove`, { gids: cloudGids });
        }
        toast(t("saveOk"));
        close(true);
      } catch (err) {
        toast(err.message || String(err));
      }
    });

    document.body.appendChild(overlay);
    if (typeof trapModalFocus === "function") {
      cleanupFocus = trapModalFocus(overlay, close);
    }
  });
}

async function seriesAddItem(seriesId) {
  const ok = await showSeriesAddModal(seriesId);
  if (ok) {
    await loadSeriesList();
  }
}

async function seriesRemoveItem(seriesId, galleryId) {
  const groupEl = document.querySelector(`.series-group[data-series-id="${seriesId}"]`);
  if (galleryId) {
    if (!window.confirm(t("seriesConfirmRemove"))) return;
    try {
      await api("POST", `/api/series/${seriesId}/items/remove`, { gallery_ids: [galleryId] });
      toast(t("saveOk"));
      await loadSeriesList();
    } catch (err) {
      toast(err.message || String(err));
    }
    return;
  }

  const localChecks = groupEl ? [...groupEl.querySelectorAll('input[data-gallery-id]:checked')] : [];
  const localIds = localChecks.map(cb => parseInt(cb.getAttribute("data-gallery-id"), 10)).filter(Boolean);
  const cloudChecks = groupEl ? [...groupEl.querySelectorAll('input[data-series-gid]:checked')] : [];
  const cloudGids = cloudChecks.map(cb => parseInt(cb.getAttribute("data-series-gid"), 10)).filter(Boolean);

  if (localIds.length > 0 || cloudGids.length > 0) {
    if (!window.confirm(t("seriesConfirmRemove"))) return;
    try {
      if (localIds.length > 0) {
        await api("POST", `/api/series/${seriesId}/items/remove`, { gallery_ids: localIds });
        for (const id of localIds) selGalleries.delete(id);
      }
      if (cloudGids.length > 0) {
        await api("POST", `/api/series/${seriesId}/cloud-items/remove`, { gids: cloudGids });
        for (const gid of cloudGids) selSeriesCloud.delete(gid);
      }
      toast(t("saveOk"));
      await loadSeriesList();
    } catch (err) {
      toast(err.message || String(err));
    }
    return;
  }

  const ok = await showSeriesRemoveModal(seriesId, groupEl);
  if (ok) {
    await loadSeriesList();
  }
}

document.addEventListener("change", e => {
  if (app.view !== "series") return;
  const cb = e.target;
  if (!cb || cb.type !== "checkbox") return;
  if (cb.hasAttribute("data-series-gid")) {
    const gid = parseInt(cb.getAttribute("data-series-gid"), 10);
    if (!isNaN(gid)) {
      if (cb.checked) selSeriesCloud.add(gid); else selSeriesCloud.delete(gid);
    }
  }
  updateSeriesToolbarButtons();
});

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
  } else if (action === "series-toggle-all") {
    e.preventDefault();
    const curShowAll = app.query.show_all === "1";
    const q = { page_size: prefPageSize() };
    if (!curShowAll) {
      q.show_all = "1";
    }
    location.hash = navHash("series", {}, q);
  } else if (action === "series-download") {
    e.preventDefault();
    seriesDownload();
  } else if (action === "series-download-orig") {
    e.preventDefault();
    seriesDownloadOrig();
  } else if (action === "series-archive") {
    e.preventDefault();
    seriesArchive();
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
