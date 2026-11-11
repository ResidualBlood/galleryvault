"use strict";

// components.js — UI 组件 (galleryCard, renderCardCheckboxes, 以及未来 skeleton/pager/modal 等)
// renderCardCheckboxes(opts) 选择裁剪由显式 pruneSelection 控制，默认不裁剪

function renderCardCheckboxes(opts = {}) {
  const { pruneSelection = false } = opts;
  document.querySelectorAll(".gc-check input[data-gallery-id]").forEach(cb => {
    if (cb.dataset.bound) return;
    cb.dataset.bound = "1";
    cb.addEventListener("change", () => {
      const id = parseInt(cb.getAttribute("data-gallery-id"), 10);
      if (cb.checked) selGalleries.add(id); else selGalleries.delete(id);
      const btn = document.querySelector('[data-action="sel-delete"]');
      if (btn) btn.textContent = `${t("deleteSel")}${selGalleries.size ? ` (${selGalleries.size})` : ""}`;
      const favBtn = document.querySelector('[data-action="lib-batch-fav"]');
      if (favBtn) {
        const count = selGalleries.size;
        favBtn.textContent = count ? t("batchFavCount").replace("{count}", count) : t("batchFav");
      }
    });
  });
  document.querySelectorAll('.gc-check input[data-fav-gid]').forEach(cb => {
    if (cb.dataset.bound) return;
    cb.dataset.bound = "1";
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-fav-gid"), 10);
      if (cb.checked) selFav.add(gid); else selFav.delete(gid);
      const update = () => {
        document.querySelectorAll('[data-action="favlist-download"], [data-action="favlist-download-orig"], [data-action="favlist-archive"], [data-action="favlist-move"], [data-action="favlist-unfav"]').forEach(b => {
          const act = b.getAttribute("data-action");
          const base = act === "favlist-download" ? t("favDl")
            : act === "favlist-download-orig" ? t("favDlOrig")
            : act === "favlist-archive" ? t("favDlArchive")
            : act === "favlist-move" ? t("favMove")
            : t("favRemove");
          b.textContent = base + (selFav.size ? ` (${selFav.size})` : "");
        });
      };
      update();
    });
  });
  document.querySelectorAll('.gc-check input[data-discover-gid]').forEach(cb => {
    if (cb.dataset.bound) return;
    cb.dataset.bound = "1";
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-discover-gid"), 10);
      if (cb.checked) selDiscover.add(gid); else selDiscover.delete(gid);
      const count = selDiscover.size;
      const dl = document.querySelector('[data-action="disc-batch-dl"]');
      if (dl) dl.textContent = count ? `${t("discoverBatchDl")} (${count})` : t("discoverBatchDl");
      const fav = document.querySelector('[data-action="disc-batch-fav"]');
      if (fav) fav.textContent = count ? `${t("discoverBatchFav")} (${count})` : t("discoverBatchFav");
    });
  });
  document.querySelectorAll('#dup-groups input[data-dup-gid]').forEach(cb => {
    if (cb.dataset.bound) return;
    cb.dataset.bound = "1";
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-dup-gid"), 10);
      if (cb.checked) selDup.add(gid); else selDup.delete(gid);
      updateDupButtons();
    });
  });
  document.querySelectorAll('#dupxgid-groups input[data-dup-gid]').forEach(cb => {
    if (cb.dataset.bound) return;
    cb.dataset.bound = "1";
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-dup-gid"), 10);
      if (cb.checked) selXgid.add(gid); else selXgid.delete(gid);
      if (typeof updateXgidButtons === "function") updateXgidButtons();
    });
  });

  if (pruneSelection) {
    const visibleGalleryIds = new Set(
      [...document.querySelectorAll(".gc-check input[data-gallery-id]")]
        .map(cb => parseInt(cb.getAttribute("data-gallery-id"), 10))
        .filter(n => !isNaN(n))
    );
    for (const id of selGalleries) {
      if (!visibleGalleryIds.has(id)) selGalleries.delete(id);
    }

    const visibleFavGids = new Set(
      [...document.querySelectorAll(".gc-check input[data-fav-gid]")]
        .map(cb => parseInt(cb.getAttribute("data-fav-gid"), 10))
        .filter(n => !isNaN(n))
    );
    for (const gid of selFav) {
      if (!visibleFavGids.has(gid)) selFav.delete(gid);
    }

    const visibleDiscoverGids = new Set(
      [...document.querySelectorAll(".gc-check input[data-discover-gid]")]
        .map(cb => parseInt(cb.getAttribute("data-discover-gid"), 10))
        .filter(n => !isNaN(n))
    );
    for (const gid of selDiscover) {
      if (!visibleDiscoverGids.has(gid)) selDiscover.delete(gid);
    }
  }

  const delBtn = document.querySelector('[data-action="sel-delete"]');
  if (delBtn) delBtn.textContent = `${t("deleteSel")}${selGalleries.size ? ` (${selGalleries.size})` : ""}`;
  const favBtn = document.querySelector('[data-action="lib-batch-fav"]');
  if (favBtn) {
    const count = selGalleries.size;
    favBtn.textContent = count ? t("batchFavCount").replace("{count}", count) : t("batchFav");
  }
}

// 选择裁剪判定：仅当视图或筛选条件变化时返回 true；翻页与调整每页数量不算筛选变化，
// 以便跨页选择得以保留（S4）。调用方把它作为 pruneSelection 显式传入 renderCardCheckboxes。
let lastSelectionScope = null;
function selectionScopeChanged() {
  const query = { ...(app.query || {}) };
  delete query.page;
  delete query.page_size;
  const key = JSON.stringify({ view: app.view, params: app.params || {}, query });
  const changed = key !== lastSelectionScope;
  lastSelectionScope = key;
  return changed;
}

function currentFromPath() {
  const h = (location.hash || "").replace(/^#\/?/, "");
  if (h) return h;
  const p = navHash(app.view || "library", app.params, app.query);
  return p.replace(/^#\/?/, "");
}

function galleryCard(it) {
  const cat = esc(catLabel(it.category));
  const from = currentFromPath();
  const ctx = app.view === "library"
    ? { ...libraryContext(), from }
    : { from };
  return `<div class="gc-wrap" data-gid="${esc(it.gid || "")}" data-token="${esc(it.token || "")}">
    <a class="gc" href="${navHash("gallery", { id: it.id }, ctx)}" role="link" aria-label="${esc(it.title)} (${cat}, ${it.page_count} pages)">
      <div class="gc-cover"${it.cover_url ? ` style="--cover-url:url('${esc(it.cover_url).replace(/&#39;/g, "%27")}')"` : ""}>
        ${it.cover_url ? `<img class="cover-fg" loading="lazy" src="${esc(it.cover_url)}" alt="">` : `<div class="cover-placeholder" style="width:100%;height:100%;background:var(--panel-2);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">${esc(t("noCover") || "no cover")}</div>`}
        <span class="gc-cat">${cat}</span>
        <span class="gc-pages">${it.page_count} P</span>
      </div>
      <div class="gc-title">${esc(it.title)}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}" data-action="filter-tag" data-ns="${esc(tg.namespace)}" data-name="${esc(tg.name)}" role="button" tabindex="0" title="${esc(tg.namespace ? tg.namespace + ':' + tg.name : tg.name)} — ${esc(t("tagFilterHint"))} / ${esc(t("tagExcludeHint"))}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-gallery-id="${it.id}" data-gid="${esc(it.gid || "")}" data-token="${esc(it.token || "")}"${selGalleries.has(it.id) ? " checked" : ""}></label>
  </div>`;
}

// 占位：未来加 favCard, modal, skeleton, empty-state 等
// function renderPager(...) {}

// Phase 1 unified status (loading/skeleton/empty/error)
function renderLoading(msg) {
  return `<p class="loading">${esc(msg || t("loading"))}</p>`;
}

function renderEmpty(msg, opts) {
  opts = opts || {};
  const icon = opts.icon || "📂";
  const actionHtml = opts.actionHtml || "";
  return `<div class="empty-state" role="status">
    <div class="empty-icon">${icon}</div>
    <p>${esc(msg || t("noData"))}</p>
    ${actionHtml ? `<div class="empty-action" style="margin-top:8px">${actionHtml}</div>` : ""}
  </div>`;
}

function trapModalFocus(overlay, closeFn) {
  const previouslyFocused = document.activeElement;
  const modalEl = overlay.querySelector('.gv-modal') || overlay;
  const getFocusables = () => Array.from(modalEl.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'));

  requestAnimationFrame(() => {
    const initial = getFocusables();
    if (initial.length) initial[0].focus();
  });

  const onKey = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeFn(null);
      return;
    }
    if (e.key === 'Tab') {
      const els = getFocusables();
      if (!els.length) {
        e.preventDefault();
        return;
      }
      const first = els[0];
      const last = els[els.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !modalEl.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (active === last || !modalEl.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  };

  document.addEventListener('keydown', onKey);
  return () => {
    try { document.removeEventListener('keydown', onKey); } catch (_) {}
    if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
      try { previouslyFocused.focus(); } catch (_) {}
    }
  };
}

function renderError(msg) {
  return `<p class="error">${esc(msg || t("error"))}</p>`;
}

// Render an error into an existing container. Returns false (no-op) when the
// node is gone — the view was replaced while the request was in flight.
function renderErrorInto(containerId, msg) {
  if (typeof document === "undefined" || !document.getElementById) return false;
  const el = document.getElementById(containerId);
  if (!el) return false;
  el.innerHTML = renderError(msg);
  return true;
}

function renderSkeleton(count = 6) {
  return Array.from({length: count}, () => `<div class="skeleton gc"></div>`).join("");
}

function showArchiveDialog(gids, opts) {
  opts = opts || {};
  const lockTier = opts.lockTier || null;
  // Preselect at render time: the radios must never show an unselected state
  // while the preview request is in flight.
  const defaultTier = lockTier || archiveDefaultTier(app.settings);
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "gv-overlay";
    const tierLabel = tier => esc(t(tier === "original" ? "archiveTierOriginal" : "archiveTierResample"));
    const tiersHtml = lockTier
      ? `<label><input type="radio" name="archive-tier" value="${esc(lockTier)}" checked> ${tierLabel(lockTier)}</label>`
      : `<label><input type="radio" name="archive-tier" value="original"${defaultTier === "original" ? " checked" : ""}> ${tierLabel("original")}</label>
        <label><input type="radio" name="archive-tier" value="resample"${defaultTier === "resample" ? " checked" : ""}> ${tierLabel("resample")}</label>`;
    overlay.innerHTML = `<div class="gv-modal" role="dialog" aria-modal="true" aria-labelledby="archive-title">
      <h3 id="archive-title">${esc(t("archiveTitle"))}</h3>
      <div class="gv-modal-body">${esc(t("loading"))}</div>
      <div class="gv-modal-foot">
        <span class="archive-funds"></span>
        <span class="archive-tiers">
          ${tiersHtml}
        </span>
        <button class="btn btn-primary" data-archive-confirm disabled type="button">${esc(t("archiveConfirm"))}</button>
        <button class="btn btn-secondary" data-archive-retry type="button" hidden>${esc(t("archiveRetry"))}</button>
        <button class="btn btn-secondary" data-archive-cancel type="button">${esc(t("cancel"))}</button>
      </div>
    </div>`;
    let settled = false;
    let cleanupFocus = null;
    let ctrl = new AbortController();
    let previewItems = null;
    let previewFailed = false;
    const bodyEl = overlay.querySelector(".gv-modal-body");
    const confirmEl = overlay.querySelector("[data-archive-confirm]");
    const retryEl = overlay.querySelector("[data-archive-retry]");
    const setRadiosDisabled = disabled => {
      overlay.querySelectorAll('input[name="archive-tier"]').forEach(r => { r.disabled = disabled; });
    };
    // Single source of truth for the confirm button, shared by every outcome.
    const syncConfirm = () => {
      if (!confirmEl) return;
      confirmEl.disabled = !archiveConfirmEnabled({items: previewItems, lockTier, failed: previewFailed});
    };
    const close = (value) => {
      if (settled) return;
      settled = true;
      // Cancelling the dialog cancels the in-flight preview request.
      try { ctrl.abort(); } catch (_) {}
      if (cleanupFocus) cleanupFocus();
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
    cleanupFocus = trapModalFocus(overlay, close);

    const errorRow = (it, colspan) =>
      `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td colspan="${colspan}"><span class="error">${esc(it.error)}</span></td></tr>`;
    const costCell = (cost, available, size) =>
      cost == null
        ? `<span class="muted">N/A</span>`
        : (available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + cost + " GP · " + fmtSize(size);

    const renderPreview = items => {
      previewItems = items;
      previewFailed = false;
      const allFailed = items.length > 0 && items.every(it => it.error);
      let html;
      if (lockTier === "original") {
        const rows = items.map(it => it.error
          ? errorRow(it, 1)
          : `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td>${costCell(it.original_cost, it.original_available, it.original_size)}</td></tr>`
        ).join("");
        html = `<table class="table archive-table"><thead><tr><th scope="col">${esc(t("gallery"))}</th><th scope="col">${esc(t("archiveTierOriginal"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
      } else {
        const rows = items.map(it => it.error
          ? errorRow(it, 2)
          : `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td>${costCell(it.original_cost, it.original_available, it.original_size)}</td><td>${costCell(it.resample_cost, it.resample_available, it.resample_size)}</td></tr>`
        ).join("");
        html = `<table class="table archive-table"><thead><tr><th scope="col">${esc(t("gallery"))}</th><th scope="col">${esc(t("archiveTierOriginal"))}</th><th scope="col">${esc(t("archiveTierResample"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
      }
      if (allFailed) {
        // Nothing can be archived: surface the first error above the table and
        // keep the confirm button disabled.
        const first = items.find(it => it.error);
        html = `<p class="error">${esc(first.error)}</p>` + html;
      }
      if (bodyEl) bodyEl.innerHTML = html;
      setRadiosDisabled(allFailed);
      syncConfirm();
    };

    const loadPreview = () => {
      previewItems = null;
      previewFailed = false;
      retryEl.hidden = true;
      if (bodyEl) bodyEl.innerHTML = `<p>${esc(t("loading"))}</p>`;
      syncConfirm();
      ctrl = new AbortController();
      const previewBody = (opts.items && opts.items.length)
        ? { gids, items: opts.items }
        : { gids };
      api("POST", "/api/archives/preview", previewBody, {signal: ctrl.signal})
        .then(data => {
          if (settled) return;
          const items = data && data.items ? data.items : [];
          if (!items.length) {
            previewItems = [];
            setRadiosDisabled(false);
            if (bodyEl) bodyEl.innerHTML = `<p>${esc(t("archiveNoItems"))}</p>`;
            syncConfirm();
            return;
          }
          if (data && data.funds != null) {
            const fundsEl = overlay.querySelector(".archive-funds");
            if (fundsEl) fundsEl.textContent = t("archiveFunds") + ": " + data.funds + " GP";
          }
          renderPreview(items);
        })
        .catch(err => {
          if (settled) return;
          // Closing the dialog aborts the request; that is not an error.
          if (err && err.name === "AbortError") return;
          previewFailed = true;
          setRadiosDisabled(true);
          retryEl.hidden = false;
          if (bodyEl) bodyEl.innerHTML = `<p class="error">${esc((err && err.message) || t("archivePreviewFail"))}</p>`;
          syncConfirm();
        });
    };
    retryEl.addEventListener("click", loadPreview);
    loadPreview();
  });
}

async function showMoveFavoritesDialog(gids, currentFavcat, opts = {}) {
  let categories = [];
  try {
    categories = await api("GET", "/api/favorites/categories");
  } catch (_) {}
  if (!Array.isArray(categories) || !categories.length) {
    categories = Array.from({length: 10}, (_, i) => ({
      favcat: i,
      name: favCatNames[i] || ("Folder " + i),
      cloud_count: 0
    }));
  }

  const title = (opts && opts.title) || t("favMoveTitle");
  const confirmText = (opts && opts.confirmText) || t("favMoveConfirm");
  const targetLabel = (opts && opts.targetLabel) || t("favMoveTarget");

  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "gv-overlay";

    const optionsHtml = categories.map(c => {
      const isCurrent = currentFavcat != null && c.favcat === currentFavcat;
      const label = `#${c.favcat} ${c.name || ("Folder " + c.favcat)}` + (c.cloud_count != null ? ` (${c.cloud_count})` : "");
      return `<option value="${c.favcat}"${isCurrent ? " disabled" : ""}>${esc(label)}${isCurrent ? ` (${esc(t("current") || "current")})` : ""}</option>`;
    }).join("");

    overlay.innerHTML = `<div class="gv-modal" role="dialog" aria-modal="true" aria-labelledby="move-title" style="max-width:440px">
      <h3 id="move-title">${esc(title)}</h3>
      <div class="gv-modal-body">
        <p style="margin-bottom:12px">${esc(t("select"))}: <strong>${gids.length}</strong></p>
        <label style="display:flex;flex-direction:column;gap:6px;font-weight:600">
          <span>${esc(targetLabel)}</span>
          <select class="select" data-move-target style="width:100%;padding:8px 10px;font-size:14px">
            ${optionsHtml}
          </select>
        </label>
      </div>
      <div class="gv-modal-foot" style="justify-content:flex-end">
        <button class="btn btn-secondary" data-move-cancel type="button">${esc(t("cancel"))}</button>
        <button class="btn btn-primary" data-move-confirm type="button">${esc(confirmText)}</button>
      </div>
    </div>`;

    let settled = false;
    let cleanupFocus = null;
    const close = (value) => {
      if (settled) return;
      settled = true;
      if (cleanupFocus) cleanupFocus();
      overlay.remove();
      resolve(value);
    };

    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("[data-move-cancel]").addEventListener("click", () => close(null));
    overlay.querySelector("[data-move-confirm]").addEventListener("click", () => {
      const sel = overlay.querySelector("[data-move-target]");
      const target = sel ? parseInt(sel.value, 10) : null;
      if (target != null && !isNaN(target) && target >= 0 && target <= 9) {
        close(target);
      } else {
        close(null);
      }
    });

    document.body.appendChild(overlay);

    const selEl = overlay.querySelector("[data-move-target]");
    const confirmBtn = overlay.querySelector("[data-move-confirm]");
    if (selEl) {
      const validOpt = Array.from(selEl.options).find(o => !o.disabled);
      if (validOpt) {
        selEl.value = validOpt.value;
      } else if (confirmBtn) {
        confirmBtn.disabled = true;
      }
    }

    cleanupFocus = trapModalFocus(overlay, close);
  });
}

function manageTabsHtml(active) {
  const recycleHref = active === "recycle"
    ? ((app && app.query && app.query.tab) ? navHash("recycle", {}, { tab: app.query.tab }) : (location.hash || "#/recycle"))
    : "#/recycle";
  const tabs = [
    { key: "recycle", href: recycleHref, label: t("recycleTitle") },
    { key: "duplicates", href: "#/duplicates", label: t("dupGalTitle") },
    { key: "dupfav", href: "#/duplicates/favorites", label: t("dupFavTitle") },
    { key: "dupxgid", href: "#/duplicates/cross-gid", label: t("dupXgidTitle") },
    { key: "integrity", href: "#/integrity", label: t("missingPagesTitle") },
    { key: "archive", href: "#/archive", label: t("archiveTitle") },
  ];
  return `<nav class="manage-tabs" role="tablist" aria-label="${esc(t("navManage"))}">
    ${tabs.map(tb => `<a class="manage-tab${active === tb.key ? " active" : ""}" href="${tb.href}" role="tab" aria-selected="${active === tb.key ? "true" : "false"}">${esc(tb.label)}</a>`).join("")}
  </nav>`;
}
