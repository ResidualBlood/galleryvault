"use strict";

// views/library.js — Phase 1
// renderLibrary moved from app.js

async function renderLibrary() {
  const page = app.query.page || "1";
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  const filterPill = tagFilterPills(tags);
  const selCount = selGalleries.size;
  $view().innerHTML = `
    <header><p class="eyebrow">LOCAL LIBRARY</p><h1>${esc(t("library"))}</h1></header>
    <form class="toolbar" data-action="library-search">
      <div class="search-box">
        <input name="q" value="${esc(q)}" placeholder="${esc(t("searchPlaceholder"))}" autocomplete="off">
        <div id="tag-suggest" class="tag-suggest" hidden></div>
      </div>
      <select name="category">
        <option value="">All categories</option>
        ${["doujinshi","manga","artistcg","gamecg","western","non-h","image_set","cosplay","asianporn","misc","deleted"].map(c => `<option value="${c}" ${c === category ? "selected" : ""}>${esc(catLabel(c))}</option>`).join("")}
        <option value="__not_fav__" ${"__not_fav__" === category ? "selected" : ""}>${esc(t("notFavorited"))}</option>
      </select>
      <button class="primary" type="submit">${esc(t("search"))}</button>
      <button class="secondary" data-action="scan" type="button">${esc(t("scan"))}</button>
      <button class="secondary" data-action="sel-clear" type="button">${esc(t("clearSel"))}</button>
      <button class="secondary danger" data-action="sel-delete" type="button">${esc(t("deleteSel"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary danger" data-action="delete-filtered" type="button">${esc(t("deleteFiltered"))}</button>
    </form>
    <div class="filters">${filterPill}</div>
    <div id="lib-grid"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="lib-pager"></div>`;
  try {
    const extra = { page_size: prefPageSize() };
    if (q) extra.q = q;
    if (category) extra.category = category;
    if (tags) { extra.tags = tags; extra.tag_mode = "and"; }
    const data = await galleryGrid("lib-grid", page, extra);
    if (data && data.resolved && (data.q !== (app.query.q || "") || data.tags !== (app.query.tags || ""))) {
      location.hash = navHash("library", {}, { q: data.q, category: data.category, tags: data.tags, tag_mode: "and" });
      return;
    }
    renderCardCheckboxes();
    gridPager("lib-pager", data, p => ({ ...(q ? { q } : {}), ...(category ? { category } : {}), ...(tags ? { tags, tag_mode: "and" } : {}), ...(p > 1 ? { page: p } : {}), page_size: prefPageSize() }));
    bindTagSuggest();
    startInfinite("lib-grid", p => galleryGrid(null, p, extra), galleryCard);
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}
