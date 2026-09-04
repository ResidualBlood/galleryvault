"use strict";

async function renderIntegrity() {
  const page = app.query.page || "1";
  renderView(`
    <header><p class="eyebrow">INTEGRITY</p><h1>${esc(t("missingPagesTitle"))}</h1>
    <p class="sub">${esc(t("missingPagesSub"))}</p></header>
    ${manageTabsHtml("integrity")}
    <div class="toolbar">
      <button class="btn btn-secondary" data-action="integrity-repair" type="button">${esc(t("retry"))} / ${esc(t("repair") || "Repair")}</button>
    </div>
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
          <a class="gc" href="${navHash("gallery", { id: g.id }, { from: "integrity" })}">
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
        });
      });
    }
    gridPager("integrity-pager", data, p => ({ ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
  } catch (e) { document.getElementById("integrity-grid").innerHTML = renderError(e.message); }
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
