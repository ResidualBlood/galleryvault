"use strict";

async function renderIntegrity() {
  const page = app.query.page || "1";
  const n = window.selIntegrity ? window.selIntegrity.size : 0;
  const suffix = n ? ` (${n})` : "";

  renderView(`
    <header><p class="eyebrow">INTEGRITY</p><h1>${esc(t("missingPagesTitle"))}</h1>
    <p class="sub">${esc(t("missingPagesSub"))}</p></header>
    ${manageTabsHtml("integrity")}
    <div class="toolbar">
      <button class="btn btn-secondary" data-action="integrity-scan" type="button">${esc(t("scan"))}</button>
      <button class="btn btn-secondary" data-action="integrity-select-all" type="button">${esc(t("selectAll"))}</button>
      <button class="btn btn-secondary" data-action="integrity-clear" type="button">${esc(t("clearSel"))}</button>
      <button class="btn btn-secondary" data-action="integrity-repair" type="button">${esc(t("retry"))} / ${esc(t("repair"))}${suffix}</button>
    </div>
    <details class="panel" style="margin:12px 0 14px;padding:10px 14px;font-size:13px;border:1px solid var(--line);border-radius:6px;">
      <summary style="cursor:pointer;font-weight:600;color:var(--text);">${esc(t("integrityInfoSummary"))}</summary>
      ${t("integrityInfoDetail")}
    </details>
    <div id="integrity-grid"><div class="grid gc-grid">${renderSkeleton(8)}</div></div>
    <div class="pages pager" id="integrity-pager"></div>`);
  try {
    const data = await api("GET", `/api/galleries/integrity?page=${encodeURIComponent(page)}&page_size=${prefPageSize()}`);
    const el = document.getElementById("integrity-grid");
    if (!data.items.length) el.innerHTML = `<p>${esc(t("noGalleries"))} — ${esc(t("noData"))}</p>`;
    else {
      el.innerHTML = `<div class="grid gc-grid">` + data.items.map(g => {
        const title = g.title || ("#" + g.id);
        const mismatch = `${g.page_count} vs ${g.actual_pages} (file:${g.file_count != null ? g.file_count : "—"})`;
        return `<div class="gc-wrap">
          <a class="gc" href="${navHash("gallery", { id: g.id }, { from: currentFromPath() })}">
            <div class="gc-cover">${g.cover_url ? `<img class="cover-bg" loading="lazy" src="${g.cover_url}" alt="" aria-hidden="true"><img class="cover-fg" loading="lazy" src="${g.cover_url}" alt="">` : `<div class="cover-placeholder">${esc(t("noCover"))}</div>`}<span class="gc-pages">${mismatch}</span></div>
            <div class="gc-title">${esc(title)}</div>
            <div class="muted" style="font-size:12px;">${esc(g.storage_path || "")}</div>
          </a>
          <label class="gc-check"><input type="checkbox" data-integrity-id="${g.id}"${selIntegrity && selIntegrity.has(g.id) ? " checked" : ""}></label>
        </div>`;
      }).join("") + `</div>`;
      document.querySelectorAll('#integrity-grid input[data-integrity-id]').forEach(cb => {
        if (cb.dataset.bound) return;
        cb.dataset.bound = "1";
        cb.addEventListener("change", () => {
          const id = parseInt(cb.getAttribute("data-integrity-id"), 10);
          if (!window.selIntegrity) window.selIntegrity = new Set();
          if (cb.checked) selIntegrity.add(id); else selIntegrity.delete(id);
          updateIntegrityButtons();
        });
      });
    }
    gridPager("integrity-pager", data, p => ({ ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
  } catch (e) { document.getElementById("integrity-grid").innerHTML = renderError(e.message); }
}

async function integrityScan() {
  try {
    const r = await api("POST", "/api/galleries/integrity/scan");
    if (r && r.status === "paused") {
      toast(r.detail || (t("paused") + " — " + t("pauseHint")));
      return r;
    }
    toast(t("scanning"));
    if (typeof pollLogs === "function") pollLogs();
    return r;
  } catch (e) { toast(e.message); }
}

async function integrityRepair() {
  const ids = (window.selIntegrity && [...window.selIntegrity]) || [];
  if (!ids.length) { toast(t("select")); return; }
  let ok = 0, fail = 0;
  for (const id of ids) {
    try {
      // Re-queue via redownload (existing) – will resume missing pages
      await api("POST", `/api/galleries/${id}/redownload`);
      ok++;
    } catch (_) { fail++; }
  }
  toast(`${ok} queued${fail ? `, ${fail} failed` : ""}`);
  if (window.selIntegrity) selIntegrity.clear();
  router();
}

function updateIntegrityButtons() {
  const btn = document.querySelector('[data-action="integrity-repair"]');
  if (!btn) return;
  const n = (window.selIntegrity && window.selIntegrity.size) || 0;
  btn.textContent = `${t("retry")} / ${t("repair")}${n ? ` (${n})` : ""}`;
}

function integritySelectAll() {
  if (!window.selIntegrity) window.selIntegrity = new Set();
  document.querySelectorAll('#integrity-grid input[data-integrity-id]').forEach(cb => {
    const id = parseInt(cb.getAttribute("data-integrity-id"), 10);
    selIntegrity.add(id);
    cb.checked = true;
  });
  updateIntegrityButtons();
}

function integrityClearSelection() {
  if (window.selIntegrity) selIntegrity.clear();
  document.querySelectorAll('#integrity-grid input[data-integrity-id]').forEach(cb => {
    cb.checked = false;
  });
  updateIntegrityButtons();
}

