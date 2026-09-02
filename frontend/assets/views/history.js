"use strict";

// views/history.js — Phase 1 continue
// renderHistory moved from app.js

async function renderHistory() {
  const page = app.query.page || "1";
  renderView(`
    <header><p class="eyebrow">READING LOG</p><h1>${esc(t("history"))}</h1>
    <div class="row-actions" style="display:flex;gap:8px;align-items:center;">
      <button class="secondary" data-action="clear-history" type="button">${esc(t("clearHistory"))}</button>
      <button class="secondary" data-action="clear-progress" type="button">${esc(t("clearProgress"))}</button>
    </div></header>
    <div id="hist-list">${renderLoading()}</div>
    <div class="pages" id="hist-pages"></div>`);
  try {
    const pageSize = prefPageSize();
    const data = await api("GET", `/api/history?page=${encodeURIComponent(page)}&page_size=${pageSize}`);
    const el = document.getElementById("hist-list");
    const items = (data && data.items) || [];
    if (!items.length) { el.innerHTML = renderEmpty(t("noHistory")); return; }
    el.innerHTML = `<div class="rows">` + items.map(h => {
      const readUrl = navHash("reader", { id: h.gallery_id, page: h.current_page });
      const galUrl = navHash("gallery", { id: h.gallery_id });
      return `
        <div class="row" style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
          <a href="${galUrl}" style="text-decoration:none;color:inherit;flex:1;min-width:0;display:flex;flex-direction:column;gap:4px;">
            <span class="row-title">${esc(h.title || ("#" + h.gallery_id))}</span>
            <span class="row-meta">${esc(t("progress"))} ${(h.current_page || 0) + 1}/${h.total_pages} · ${h.last_read_at ? esc(String(h.last_read_at).slice(0, 10)) : ""}</span>
          </a>
          <div style="display:flex;gap:8px;align-items:center;">
            <a class="btn btn-secondary btn-sm" href="${readUrl}" style="padding:4px 10px;font-size:13px;">${esc(t("readNow"))}</a>
            <button class="btn btn-secondary danger btn-sm" data-action="clear-single-progress" data-id="${h.gallery_id}" type="button" title="${esc(t("markUnread"))}">✕</button>
          </div>
        </div>`;
    }).join("") + `</div>`;
    const last = Math.max(1, Math.ceil(data.total / data.page_size));
    const qp = p => navHash("history", {}, { page: p, page_size: prefPageSize() });
    const pages = [];
    for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
      pages.push(p === data.page ? `<strong class="cur" aria-current="page">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
    }
    document.getElementById("hist-pages").innerHTML =
      `${data.page > 1 ? `<a class="page-link" href="${qp(data.page - 1)}">&lt;</a>` : ""} ` +
      pages.join(" ") +
      ` ${pagerJump(data.page, last)} · ${esc(t("perPage"))} ${pageSizeSelect(data.page_size, "history")}`;
  } catch (e) { document.getElementById("hist-list").innerHTML = renderError(e.message); }
}

async function clearHistory() {
  try { await api("DELETE", "/api/history"); renderHistory(); }
  catch (e) { toast(e.message); }
}

async function clearProgress() {
  if (!window.confirm(t("confirmClearProgress"))) return;
  try {
    await api("DELETE", "/api/galleries/progress");
    toast(t("progressCleared"));
    renderHistory();
  } catch (e) {
    toast(e.message);
  }
}

async function clearSingleProgress(id) {
  try {
    await api("DELETE", `/api/galleries/${id}/progress`);
    toast(t("progressClearedSingle"));
    if (app.view === "browse") {
      renderBrowse();
    } else if (app.view === "history") {
      renderHistory();
    } else if (app.view === "gallery") {
      renderGallery();
    }
  } catch (e) {
    toast(e.message);
  }
}
