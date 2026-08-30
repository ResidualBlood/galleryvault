"use strict";

// views/history.js — Phase 1 continue
// renderHistory moved from app.js

async function renderHistory() {
  const page = app.query.page || "1";
  renderView(`
    <header><p class="eyebrow">READING LOG</p><h1>${esc(t("history"))}</h1>
    <button class="secondary" data-action="clear-history" type="button">${esc(t("clearHistory"))}</button></header>
    <div id="hist-list">${renderLoading()}</div>
    <div class="pages" id="hist-pages"></div>`);
  try {
    const pageSize = prefPageSize();
    const data = await api("GET", `/api/history?page=${encodeURIComponent(page)}&page_size=${pageSize}`);
    const el = document.getElementById("hist-list");
    const items = (data && data.items) || [];
    if (!items.length) { el.innerHTML = renderEmpty(t("noHistory")); return; }
    el.innerHTML = `<div class="rows">` + items.map(h => `
      <a class="row" href="${navHash("gallery", { id: h.gallery_id })}">
        <span class="row-title">${esc(h.title || ("#" + h.gallery_id))}</span>
        <span class="row-meta">${esc(t("progress"))} ${h.current_page}/${h.total_pages} · ${h.last_read_at ? esc(String(h.last_read_at).slice(0, 10)) : ""}</span>
      </a>`).join("") + `</div>`;
    const last = Math.max(1, Math.ceil(data.total / data.page_size));
    const qp = p => navHash("history", {}, { page: p, page_size: prefPageSize() });
    const pages = [];
    for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
      pages.push(p === data.page ? `<strong class="cur">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
    }
    document.getElementById("hist-pages").innerHTML =
      `${data.page > 1 ? `<a class="page-link" href="${qp(data.page - 1)}">&lt;</a>` : ""} ` +
      pages.join(" ") +
      ` ${pagerJump(data.page, last)} · ${esc(t("perPage"))} ${pageSizeSelect(data.page_size, "history")}`;
  } catch (e) { document.getElementById("hist-list").innerHTML = renderError(esc(e.message)); }
}
