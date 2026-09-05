"use strict";

function recycleSelectedIds() {
  const listed = new Set(
    [...document.querySelectorAll("#recycle-grid input[data-recycle-id]")]
      .map(cb => parseInt(cb.getAttribute("data-recycle-id"), 10))
      .filter(Number.isFinite)
  );
  return (window.selRecycle ? [...selRecycle] : []).filter(id => listed.has(id));
}

function updateRecycleButtons() {
  const n = window.selRecycle ? selRecycle.size : 0;
  const suffix = n ? ` (${n})` : "";
  const restoreBtn = document.querySelector('[data-action="recycle-restore"]');
  const redownloadBtn = document.querySelector('[data-action="recycle-redownload"]');
  const purgeBtn = document.querySelector('[data-action="recycle-purge"]');
  if (restoreBtn) restoreBtn.textContent = `${t("restore")}${suffix}`;
  if (redownloadBtn) redownloadBtn.textContent = `${t("recycleRedownload") || "按 gid 重下"}${suffix}`;
  if (purgeBtn) purgeBtn.textContent = `${t("purge")}${suffix}`;
}

async function renderRecycle() {
  const tab = app.query.tab || "trash";
  const page = app.query.page || "1";
  if (window._recycleLastTab && window._recycleLastTab !== tab) {
    if (window.selRecycle) selRecycle.clear();
  }
  window._recycleLastTab = tab;
  const n = window.selRecycle ? selRecycle.size : 0;
  const suffix = n ? ` (${n})` : "";
  renderView(`
    <header><p class="eyebrow">RECYCLE BIN</p><h1>${esc(t("recycleTitle"))}</h1>
    <p class="sub">${esc(t("recycleSub"))}</p></header>
    ${manageTabsHtml("recycle")}
    <div class="toolbar">
      <a class="pill${tab === "trash" ? " active" : ""}" href="${navHash("recycle", {}, { tab: "trash" })}">🗑 ${esc(t("trash")) || "Trash"} (${esc(t("userDeleted") || "User")})</a>
      <a class="pill${tab === "expunged" ? " active" : ""}" href="${navHash("recycle", {}, { tab: "expunged" })}">👻 ${esc(t("expunged") || "Missing")} (${esc(t("scanMissing") || "Scan")})</a>
      <button class="btn btn-secondary" data-action="recycle-restore" type="button"${tab === "expunged" ? " hidden disabled" : ""}>${esc(t("restore"))}${suffix}</button>
      <button class="btn btn-secondary" data-action="recycle-redownload" type="button"${tab !== "expunged" ? " hidden disabled" : ""}>${esc(t("recycleRedownload") || "按 gid 重下")}${suffix}</button>
      <button class="btn btn-danger" data-action="recycle-purge" type="button">${esc(t("purge"))}${suffix}</button>
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
          <a class="gc" href="${navHash("gallery", { id: g.id }, { from: currentFromPath() })}">
            <div class="gc-cover">${g.cover_url ? `<img class="cover-bg" loading="lazy" src="${g.cover_url}" alt="" aria-hidden="true"><img class="cover-fg" loading="lazy" src="${g.cover_url}" alt="">` : `<div class="cover-placeholder">${esc(t("noCover"))}</div>`}<span class="gc-pages">${g.page_count} P</span></div>
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
          updateRecycleButtons();
        });
      });
    }
    gridPager("recycle-pager", data, p => ({ tab, ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
  } catch (e) { document.getElementById("recycle-grid").innerHTML = renderError(e.message); }
}

async function recycleRestore() {
  const ids = recycleSelectedIds();
  if (!ids.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/galleries/restore", { ids });
    toast(`${esc(t("restore"))}: ${r.restored}`);
    selRecycle.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function recycleRedownload() {
  const ids = recycleSelectedIds();
  if (!ids.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/galleries/expunged/redownload", { ids });
    const skipped = (r.skipped_no_gid || 0) + (r.skipped_no_token || 0);
    const skipText = skipped > 0 ? ` · ${esc(t("recycleRedownloadSkip") || "跳过")}: ${skipped}` : "";
    toast(`${esc(t("recycleRedownload") || "按 gid 重下")}: ${r.queued}${skipText}`);
    selRecycle.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function recyclePurge() {
  const ids = recycleSelectedIds();
  if (!ids.length) { toast(t("select")); return; }
  if (!window.confirm(t("confirmDelete") + " (" + ids.length + ")")) return;
  const delFiles = window.confirm(t("deleteFiles"));
  try {
    const r = await api("POST", "/api/galleries/purge", { ids, delete_files: delFiles });
    const ok = r.purged != null ? r.purged : (r.deleted != null ? r.deleted : ids.length);
    const failed = (r.failed_deletions || []).length;
    toast(`${esc(t("purge"))}: ${ok}` + (failed ? ` · ${esc(t("dupDeleteFail"))}${failed}` : ""));
    selRecycle.clear();
    router();
  } catch (e) { toast(e.message); }
}
