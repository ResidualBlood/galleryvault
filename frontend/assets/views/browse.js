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
      <button class="primary" type="submit">${esc(t("search"))}</button>
      <button class="secondary big" data-action="random" type="button">🎲 ${esc(t("random"))}</button>
    </form>
    <section>
      <h2>${esc(t("latest"))} <span class="muted" id="browse-total"></span></h2>
      <div id="browse-grid"><p>${esc(t("loading"))}</p></div>
      <div class="pages pager" id="browse-pager"></div>
    </section>
    <section>
      <h2>${esc(t("tags"))}</h2>
      <div id="browse-ns" class="ns-strip"></div>
    </section>`);
  try {
    const [data, tagData] = await Promise.all([
      galleryGrid("browse-grid", app.query.page || "1", { page_size: prefPageSize() }),
      api("GET", "/api/tags/search?page=1&page_size=1").catch(() => null),
    ]);
    const totalEl = document.getElementById("browse-total");
    if (totalEl && data) totalEl.textContent = `· ${data.total}`;
    gridPager("browse-pager", data, p => ({ ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
    const strip = document.getElementById("browse-ns");
    if (strip && tagData) {
      const counts = {};
      for (const f of tagData.facets || []) counts[f.namespace] = f.total;
      strip.innerHTML = TAG_NAMESPACES
        .filter(g => g.ns && counts[g.ns])
        .map(g => `<a class="pill" href="${navHash("tags", {}, { ns: g.ns })}">${esc(groupLabel(g.key))} <b>${counts[g.ns]}</b></a>`)
        .join("");
    }
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}
