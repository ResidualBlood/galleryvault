"use strict";

// views/browse.js — Phase 1
// renderBrowse moved from app.js

async function renderBrowse() {
  renderView(`
    <header><p class="eyebrow">GALLERYVAULT</p><h1>${esc(t("browse"))}</h1></header>
    <form class="toolbar" data-action="browse-search">
      <div class="search-box">
        <input name="q" value="" placeholder="${esc(t("searchPlaceholder"))}" autocomplete="off">
        <div id="tag-suggest" class="tag-suggest" hidden></div>
      </div>
      <button class="btn btn-primary" type="submit">${esc(t("search"))}</button>
      <button class="btn btn-secondary big" data-action="random" type="button">🎲 ${esc(t("random"))}</button>
    </form>
    <div id="browse-cr"></div>
    <section>
      <h2>${esc(t("latest"))} <span class="muted" id="browse-total"></span></h2>
      <div id="browse-grid">${renderLoading()}</div>
      <div class="pages pager" id="browse-pager"></div>
    </section>
    <section>
      <h2>${esc(t("tags"))}</h2>
      <div id="browse-ns" class="ns-strip"></div>
    </section>`);
  let data = null;
  let tagData = null;
  let historyData = null;
  const [dataResult, tagDataResult, historyResult] = await Promise.allSettled([
    galleryGrid("browse-grid", app.query.page || "1", { page_size: prefPageSize() }),
    api("GET", "/api/tags/search?page=1&page_size=1"),
    api("GET", "/api/history?page=1&page_size=8"),
  ]);
  if (dataResult.status === "fulfilled") {
    data = dataResult.value;
  } else {
    const el = document.getElementById("browse-grid");
    if (el) el.innerHTML = renderError(dataResult.reason?.message || "Failed to load");
  }
  if (tagDataResult.status === "fulfilled") {
    tagData = tagDataResult.value;
  }
  if (historyResult.status === "fulfilled") {
    historyData = historyResult.value;
  }
  try {
    const crEl = document.getElementById("browse-cr");
    if (crEl && historyData && historyData.items && historyData.items.length) {
      crEl.innerHTML = renderContinueReadingHtml(historyData.items);
    }
    const totalEl = document.getElementById("browse-total");
    if (totalEl && data) totalEl.textContent = `· ${data.total}`;
    if (data) {
      gridPager("browse-pager", data, p => ({ ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
      startInfinite("browse-grid", p => galleryGrid(null, p, { page_size: prefPageSize() }), galleryCard);
    }
    const strip = document.getElementById("browse-ns");
    if (strip && tagData) {
      const counts = {};
      for (const f of tagData.facets || []) counts[f.namespace] = f.total;
      strip.innerHTML = TAG_NAMESPACES
        .filter(g => g.ns && counts[g.ns])
        .map(g => `<a class="pill" href="${navHash("tags", {}, { ns: g.ns })}">${esc(groupLabel(g.key))} <b>${counts[g.ns]}</b></a>`)
        .join("");
    } else if (strip && !tagData) {
      strip.innerHTML = `<span class="muted">${esc(t("noData"))}</span>`;
    }
  } catch (e) {
    // Pager/infinite errors should not wipe the whole view
    console.warn("browse pager error", e);
  }
}

function renderContinueReadingHtml(items) {
  if (!items || !items.length) return "";
  const cards = items.map(h => {
    const cur = h.current_page || 0;
    const total = h.total_pages || 1;
    const pct = Math.min(100, Math.round(((cur + 1) / total) * 100));
    const title = h.display_title || h.title || ("#" + h.gallery_id);
    const readUrl = navHash("reader", { id: h.gallery_id, page: cur });
    const galUrl = navHash("gallery", { id: h.gallery_id });
    return `
      <div class="cr-card">
        <a class="cr-thumb-wrap" href="${readUrl}">
          <img loading="lazy" src="/api/galleries/${h.gallery_id}/thumb/0" alt="${esc(title)}">
          <div class="cr-progress-wrap">
            <div class="cr-progress-bar"><div class="cr-progress-fill" style="width:${pct}%"></div></div>
            <div class="cr-progress-text"><span>${esc(t("progress"))} ${cur + 1}/${total}</span><span>${pct}%</span></div>
          </div>
        </a>
        <div class="cr-body">
          <a class="cr-title" href="${galUrl}" title="${esc(title)}">${esc(title)}</a>
          <div class="cr-actions">
            <a class="btn btn-secondary btn-sm" href="${readUrl}" style="padding:2px 8px;font-size:12px;">${esc(t("readNow"))}</a>
            <button class="cr-btn-clear" data-action="clear-single-progress" data-id="${h.gallery_id}" type="button" title="${esc(t("markUnread"))}">✕</button>
          </div>
        </div>
      </div>`;
  }).join("");

  return `
    <section class="cr-section">
      <div class="cr-header">
        <h2>${esc(t("continueReading"))}</h2>
        <a class="link-button" href="#/history" style="font-size:13px;">${esc(t("viewAllHistory"))} →</a>
      </div>
      <div class="cr-grid">${cards}</div>
    </section>`;
}

async function randomGallery() {
  try { const d = await api("GET", "/api/galleries/random"); location.hash = navHash("gallery", { id: d.id }); }
  catch (e) { toast(e.message); }
}
