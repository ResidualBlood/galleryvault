"use strict";

// views/recycle.js — Recycle bin (trash vs expunged) + integrity placeholder
async function renderRecycle() {
  const tab = app.query.tab || "trash"; // trash | expunged
  const page = app.query.page || "1";
  renderView(`
    <header><p class="eyebrow">RECYCLE BIN</p><h1>${esc(t("recycleTitle"))}</h1>
    <p class="sub">${esc(t("recycleSub"))}</p></header>
    <div class="toolbar">
      <a class="pill${tab === "trash" ? " active" : ""}" href="${navHash("recycle", {}, { tab: "trash" })}">🗑 ${esc(t("trash")) || "Trash"} (${esc(t("userDeleted") || "User")})</a>
      <a class="pill${tab === "expunged" ? " active" : ""}" href="${navHash("recycle", {}, { tab: "expunged" })}">👻 ${esc(t("expunged") || "Missing")} (${esc(t("scanMissing") || "Scan")})</a>
      <a class="pill" href="#/integrity">${esc(t("missingPagesTitle"))}</a>
      <button class="btn btn-secondary" data-action="recycle-restore" type="button">${esc(t("restore"))}</button>
      <button class="btn btn-danger" data-action="recycle-purge" type="button">${esc(t("purge"))}</button>
    </div>
    <div id="recycle-grid"><div class="grid gc-grid">${renderSkeleton(8)}</div></div>
    <div class="pages pager" id="recycle-pager"></div>`);
  try {
    const endpoint = tab === "expunged" ? "/api/galleries/expunged" : "/api/galleries/trash";
    const data = await api("GET", `${endpoint}?page=${encodeURIComponent(page)}&page_size=${prefPageSize()}`);
    const el = document.getElementById("recycle-grid");
    if (!data.items.length) el.innerHTML = renderEmpty(t("noGalleries"));
    else {
      el.innerHTML = `<div class="grid gc-grid">` + data.items.map(g => {
        const title = g.title || ("#" + g.id);
        return `<div class="gc-wrap">
          <a class="gc" href="${navHash("gallery", { id: g.id })}">
            <div class="gc-cover">${g.cover_url ? `<img loading="lazy" src="${g.cover_url}" alt="">` : `<div class="cover-placeholder">${esc(t("noCover"))}</div>`}<span class="gc-pages">${g.page_count} P</span></div>
            <div class="gc-title">${esc(title)}</div>
            <div class="muted" style="font-size:12px;">${esc(g.trashed_at || g.updated_at || "")} · ${esc(g.storage_path || "")}</div>
          </a>
          <label class="gc-check"><input type="checkbox" data-recycle-id="${g.id}"${selRecycle && selRecycle.has(g.id) ? " checked" : ""}></label>
        </div>`;
      }).join("") + `</div>`;
      document.querySelectorAll('#recycle-grid input[data-recycle-id]').forEach(cb => {
        if (cb.dataset.bound) return;
        cb.dataset.bound = "1";
        cb.addEventListener("change", () => {
          const id = parseInt(cb.getAttribute("data-recycle-id"), 10);
          if (!selRecycle) window.selRecycle = new Set();
          if (cb.checked) selRecycle.add(id); else selRecycle.delete(id);
        });
      });
    }
    gridPager("recycle-pager", data, p => ({ tab, ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
  } catch (e) { document.getElementById("recycle-grid").innerHTML = renderError(e.message); }
}

async function recycleRestore() {
  const ids = selRecycle ? [...selRecycle] : [];
  if (!ids.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/galleries/restore", { ids });
    toast(`${esc(t("restore"))}: ${r.restored}`);
    selRecycle.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function recyclePurge() {
  const ids = selRecycle ? [...selRecycle] : [];
  if (!ids.length) { toast(t("select")); return; }
  if (!window.confirm(t("confirmDelete") + " (" + ids.length + ")")) return;
  const delFiles = window.confirm(t("deleteFiles"));
  // purge currently hard-deletes DB; files already gone for expunged, for trash we hard-delete DB only (files kept unless delFiles)
  // For simplicity, call purge (hard delete) – backend will delete row
  try {
    const r = await api("POST", "/api/galleries/purge", { ids });
    toast(`${esc(t("purge"))}: ${r.purged}`);
    selRecycle.clear();
    router();
  } catch (e) { toast(e.message); }
}
