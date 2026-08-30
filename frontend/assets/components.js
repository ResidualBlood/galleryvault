"use strict";

// components.js — UI 组件 (galleryCard, renderCardCheckboxes, 以及未来 skeleton/pager/modal 等)
// 保持原有函数签名

function renderCardCheckboxes() {
  document.querySelectorAll(".gc-check input").forEach(cb => {
    cb.addEventListener("change", () => {
      const id = parseInt(cb.getAttribute("data-gallery-id"), 10);
      if (cb.checked) selGalleries.add(id); else selGalleries.delete(id);
      const btn = document.querySelector('[data-action="sel-delete"]');
      if (btn) btn.textContent = `${t("deleteSel")}${selGalleries.size ? ` (${selGalleries.size})` : ""}`;
    });
  });
  document.querySelectorAll('.gc-check input[data-fav-gid]').forEach(cb => {
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-fav-gid"), 10);
      if (cb.checked) selFav.add(gid); else selFav.delete(gid);
      const update = () => {
        document.querySelectorAll('[data-action="favlist-download"], [data-action="favlist-download-orig"], [data-action="favlist-archive"], [data-action="favlist-unfav"]').forEach(b => {
          const base = b.getAttribute("data-action") === "favlist-download" ? t("favDl")
            : b.getAttribute("data-action") === "favlist-download-orig" ? t("favDlOrig")
            : b.getAttribute("data-action") === "favlist-archive" ? t("favDlArchive")
            : t("favRemove");
          b.textContent = base + (selFav.size ? ` (${selFav.size})` : "");
        });
      };
      update();
    });
  });
  document.querySelectorAll('#dup-groups input[data-dup-gid]').forEach(cb => {
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-dup-gid"), 10);
      if (cb.checked) selDup.add(gid); else selDup.delete(gid);
      updateDupButtons();
    });
  });
}

function galleryCard(it) {
  const cat = esc(catLabel(it.category));
  const ctx = app.view === "library" ? libraryContext() : {};
  return `<div class="gc-wrap">
    <a class="gc" href="${navHash("gallery", { id: it.id }, ctx)}">
      <div class="gc-cover">
        ${it.cover_url ? `<img loading="lazy" src="${it.cover_url}" alt="">` : `<span class="badge">no cover</span>`}
        <span class="gc-cat">${cat}</span>
        <span class="gc-pages">${it.page_count} P</span>
      </div>
      <div class="gc-title">${esc(it.title)}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-gallery-id="${it.id}"${selGalleries.has(it.id) ? " checked" : ""}></label>
  </div>`;
}

// 占位：未来加 favCard, modal, skeleton, empty-state 等
// function renderPager(...) {}

// Phase 1 unified status (loading/skeleton/empty/error)
function renderLoading(msg) {
  return `<p class="loading">${esc(msg || t("loading"))}</p>`;
}

function renderEmpty(msg) {
  return `<div class="empty-state"><p>${esc(msg || t("noData"))}</p></div>`;
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
