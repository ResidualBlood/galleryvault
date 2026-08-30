"use strict";

// views/downloads.js — Phase 1 continue
// renderDownloads + dl helpers moved from app.js

async function renderDownloads() {
  const filter = app.query.filter || "all";
  $view().innerHTML = `
    <header><p class="eyebrow">DOWNLOADS</p><h1>${esc(t("downloads"))}</h1>
    <p class="sub">${esc(t("downloadsSub"))}</p></header>
    <h2 style="margin-top:20px">${esc(t("dlTasks"))}</h2>
    <div class="toolbar">
      <div class="pills" style="margin:0">
        ${DL_STATUSES.map(s => `<a class="pill${s === filter ? " active" : ""}" href="${navHash("downloads", {}, s !== "all" ? { filter: s } : {})}">${esc(s === "all" ? t("filterAll") : s)}</a>`).join("")}
      </div>
      <button class="secondary" data-action="dl-select-all" type="button">${esc(t("selectAll"))}</button>
      <button class="primary" data-action="dl-retry-selected" type="button">${esc(t("retrySelected"))}</button>
      <button class="secondary danger" data-action="dl-delete-selected" type="button">${esc(t("deleteSel"))}</button>
    </div>
    <div id="dl-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages" id="dl-pages"></div>`;
  loadDownloads(filter, app.query.page || "1");
  if (dlTimer) clearInterval(dlTimer);
  dlTimer = setInterval(() => {
    if (location.hash.startsWith("#/downloads")) loadDownloads(filter, app.query.page || "1");
  }, 2000);
}

// fmtDur moved to utils.js

function dlProgressHtml(x) {
  if (!x || x.total_pages <= 0) return "";
  const pct = Math.min(100, Math.round((x.current_page / x.total_pages) * 100));
  return `<div class="progress"><div class="bar" style="width:${pct}%"></div><span>${x.current_page}/${x.total_pages}</span></div>`;
}

async function loadDownloads(filter, page) {
  const el = document.getElementById("dl-list");
  const pager = document.getElementById("dl-pages");
  if (!el) return;
  try {
    const qs = `filter=${encodeURIComponent(filter)}&page=${encodeURIComponent(page)}&page_size=${prefPageSize(50)}`;
    const data = await api("GET", `/api/downloads?${qs}`);
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = `<p>${esc(t("noDownloads"))}</p>`;
    } else {
      el.innerHTML = items.map(d => {
        const status = d.status || "pending";
        const badge = `<span class="badge status-${status}">${esc(status)}</span>`;
        const prog = dlProgressHtml(d);
        const err = d.error_message ? `<div class="error small">${esc(d.error_message)}</div>` : "";
        const actions = (status === "failed" || status === "cancelled") ? `<button class="small" data-action="dl-retry" data-id="${d.id}">重试</button>` : "";
        return `<div class="dl-row" data-id="${d.id}">
          <div class="dl-title">${esc(d.title || ("#" + d.gallery_id))}</div>
          <div class="dl-meta">${badge} ${fmtDur(d.elapsed_seconds)} ${prog}</div>
          ${err}
          <div class="dl-actions">
            ${actions}
            <button class="small danger" data-action="dl-cancel" data-id="${d.id}">取消</button>
          </div>
        </div>`;
      }).join("");
    }
    if (pager) {
      const last = Math.max(1, Math.ceil(data.total / data.page_size));
      const qp = p => navHash("downloads", {}, { ...(filter !== "all" ? { filter } : {}), page: p, page_size: prefPageSize(50) });
      const parts = [];
      if (data.page > 1) parts.push(`<a class="page-link" href="${qp(data.page-1)}">&lt;</a>`);
      for (let p = Math.max(1, data.page-2); p <= Math.min(last, data.page+2); p++) {
        parts.push(p === data.page ? `<strong class="cur">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
      }
      if (data.page < last) parts.push(`<a class="page-link" href="${qp(data.page+1)}">&gt;</a>`);
      pager.innerHTML = parts.join(" ") + ` ${pagerJump(data.page, last)} · ${pageSizeSelect(data.page_size, "downloads")}`;
    }
  } catch (e) {
    if (el) el.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}
