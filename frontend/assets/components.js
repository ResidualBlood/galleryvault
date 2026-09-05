"use strict";

// components.js — UI 组件 (galleryCard, renderCardCheckboxes, 以及未来 skeleton/pager/modal 等)
// 保持原有函数签名

function renderCardCheckboxes() {
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
    ? { ...libraryContext(), ...(app.query.page ? { page: app.query.page } : {}), from }
    : { from };
  return `<div class="gc-wrap" data-gid="${esc(it.gid || "")}" data-token="${esc(it.token || "")}">
    <a class="gc" href="${navHash("gallery", { id: it.id }, ctx)}" role="link" aria-label="${esc(it.title)} (${cat}, ${it.page_count} pages)">
      <div class="gc-cover">
        ${it.cover_url ? `<img class="cover-bg" loading="lazy" src="${it.cover_url}" alt="" aria-hidden="true"><img class="cover-fg" loading="lazy" src="${it.cover_url}" alt="">` : `<div class="cover-placeholder" style="width:100%;height:100%;background:var(--panel-2);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">${esc(t("noCover") || "no cover")}</div>`}
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

function renderSkeleton(count = 6) {
  return Array.from({length: count}, () => `<div class="skeleton gc"></div>`).join("");
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
    overlay.innerHTML = `<div class="gv-modal" role="dialog" aria-modal="true" aria-labelledby="archive-title">
      <h3 id="archive-title">${esc(t("archiveTitle"))}</h3>
      <div class="gv-modal-body">${esc(t("loading"))}</div>
      <div class="gv-modal-foot">
        <span class="archive-funds"></span>
        <span class="archive-tiers">
          ${tiersHtml}
        </span>
        <button class="btn btn-primary" data-archive-confirm disabled type="button">${esc(t("archiveConfirm"))}</button>
        <button class="btn btn-secondary" data-archive-cancel type="button">${esc(t("cancel"))}</button>
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
    overlay.querySelector("[data-archive-cancel]").addEventListener("click", () => close(null));
    overlay.querySelector("[data-archive-confirm]").addEventListener("click", () => {
      const tier = overlay.querySelector('input[name="archive-tier"]:checked');
      close(tier ? tier.value : null);
    });
    document.body.appendChild(overlay);
    cleanupFocus = trapModalFocus(overlay, close);
    const previewBody = (opts.items && opts.items.length)
      ? { gids, items: opts.items }
      : { gids };
    api("POST", "/api/archives/preview", previewBody)
      .then(data => {
        if (settled) return;
        const bodyEl = overlay.querySelector(".gv-modal-body");
        if (!bodyEl) return;
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
          bodyEl.innerHTML = `<table class="table archive-table"><thead><tr><th scope="col">${esc(t("gallery"))}</th><th scope="col">${esc(t("archiveTierOriginal"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
          const first = items[0];
          if (confirm) confirm.disabled = !!(first && !first.error && first.original_cost != null && !first.original_available);
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
          bodyEl.innerHTML = `<table class="table archive-table"><thead><tr><th scope="col">${esc(t("gallery"))}</th><th scope="col">${esc(t("archiveTierOriginal"))}</th><th scope="col">${esc(t("archiveTierResample"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
          if (confirm) confirm.disabled = false;
        }
        if (data && data.funds != null) {
          const fundsEl = overlay.querySelector(".archive-funds");
          if (fundsEl) fundsEl.textContent = t("archiveFunds") + ": " + data.funds + " GP";
        }
        if (!lockTier) {
          const defaultTier = app.settings && app.settings.archive_quality === "original" ? "original" : "resample";
          const radio = overlay.querySelector(`input[name="archive-tier"][value="${defaultTier}"]`);
          if (radio) radio.checked = true;
        }
      })
      .catch(err => {
        if (settled) return;
        const bodyEl = overlay.querySelector(".gv-modal-body");
        if (bodyEl) bodyEl.innerHTML = `<p class="error">${esc(err.message || t("archivePreviewFail"))}</p>`;
      });
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
    { key: "integrity", href: "#/integrity", label: t("missingPagesTitle") },
    { key: "archive", href: "#/archive", label: t("archiveTitle") },
  ];
  return `<nav class="manage-tabs" role="tablist" aria-label="${esc(t("navManage"))}">
    ${tabs.map(tb => `<a class="manage-tab${active === tb.key ? " active" : ""}" href="${tb.href}" role="tab" aria-selected="${active === tb.key ? "true" : "false"}">${esc(tb.label)}</a>`).join("")}
  </nav>`;
}
