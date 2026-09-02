"use strict";

// views/library.js — Phase 1
// renderLibrary moved from app.js

async function renderLibrary() {
  const page = app.query.page || "1";
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  const order_by = app.query.order_by || "id_desc";
  const read_status = app.query.read_status || "";
  const filterPill = tagFilterPills(tags);
  const selCount = selGalleries.size;
  renderView(`
    <header><p class="eyebrow">LOCAL LIBRARY</p><h1>${esc(t("library"))}</h1></header>
    <form class="toolbar" data-action="library-search">
      <div class="search-box">
        <input name="q" value="${esc(q)}" placeholder="${esc(t("searchPlaceholder"))}" autocomplete="off">
        <div id="tag-suggest" class="tag-suggest" hidden></div>
      </div>
      <select name="category">
        <option value="">${esc(t("allCategories"))}</option>
        ${["doujinshi","manga","artistcg","gamecg","western","non-h","image_set","cosplay","asianporn","misc","deleted"].map(c => `<option value="${c}" ${c === category ? "selected" : ""}>${esc(catLabel(c))}</option>`).join("")}
        <option value="__not_fav__" ${"__not_fav__" === category ? "selected" : ""}>${esc(t("notFavorited"))}</option>
      </select>
      <select name="order_by">
        <option value="id_desc"${order_by === "id_desc" ? " selected" : ""}>${esc(t("orderDefault"))}</option>
        <option value="posted_at_desc"${order_by === "posted_at_desc" ? " selected" : ""}>${esc(t("orderPosted"))}</option>
        <option value="title_asc"${order_by === "title_asc" ? " selected" : ""}>${esc(t("orderTitle"))}</option>
        <option value="page_count_desc"${order_by === "page_count_desc" ? " selected" : ""}>${esc(t("orderPages"))}</option>
        <option value="file_size_desc"${order_by === "file_size_desc" ? " selected" : ""}>${esc(t("orderSize"))}</option>
        <option value="rating_desc"${order_by === "rating_desc" ? " selected" : ""}>${esc(t("orderRating"))}</option>
      </select>
      <select name="read_status">
        <option value=""${!read_status ? " selected" : ""}>${esc(t("readStatusAll"))}</option>
        <option value="unread"${read_status === "unread" ? " selected" : ""}>${esc(t("readStatusUnread"))}</option>
        <option value="reading"${read_status === "reading" ? " selected" : ""}>${esc(t("readStatusReading"))}</option>
        <option value="completed"${read_status === "completed" ? " selected" : ""}>${esc(t("readStatusCompleted"))}</option>
      </select>
      <button class="btn btn-primary" type="submit">${esc(t("search"))}</button>
      <button class="btn btn-secondary" data-action="scan" type="button">${esc(t("scan"))}</button>
      <button class="btn btn-secondary" data-action="sel-clear" type="button">${esc(t("clearSel"))}</button>
      <button class="btn btn-danger" data-action="sel-delete" type="button">${esc(t("deleteSel"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="btn btn-danger" data-action="delete-filtered" type="button">${esc(t("deleteFiltered"))}</button>
    </form>
    <div class="filters">${filterPill}</div>
    <div id="lib-grid"><div class="grid gc-grid">${renderSkeleton(8)}</div></div>
    <div class="pages pager" id="lib-pager"></div>`);
  // Advanced filters that have API support but no dedicated UI yet remain sticky via query string
  const min_rating = app.query.min_rating || "";
  const page_min = app.query.page_min || app.query.min_pages || "";
  const page_max = app.query.page_max || app.query.max_pages || "";
  const tag_mode = app.query.tag_mode || "and";
  const tag_match = app.query.tag_match || "exact";
  try {
    const extra = { page_size: prefPageSize() };
    if (q) extra.q = q;
    if (category) extra.category = category;
    if (tags) { extra.tags = tags; extra.tag_mode = tag_mode; if (tag_match !== "exact") extra.tag_match = tag_match; }
    if (order_by && order_by !== "id_desc") extra.order_by = order_by;
    if (read_status) extra.read_status = read_status;
    if (min_rating) extra.min_rating = min_rating;
    if (page_min) extra.page_min = page_min;
    if (page_max) extra.page_max = page_max;
    const data = await galleryGrid("lib-grid", page, extra);
    if (data && data.resolved && (data.q !== (app.query.q || "") || data.tags !== (app.query.tags || ""))) {
      location.hash = navHash("library", {}, {
        q: data.q,
        category: data.category,
        tags: data.tags,
        tag_mode: tag_mode,
        ...(tag_match !== "exact" ? { tag_match } : {}),
        ...(order_by && order_by !== "id_desc" ? { order_by } : {}),
        ...(read_status ? { read_status } : {}),
        ...(min_rating ? { min_rating } : {}),
        ...(page_min ? { page_min } : {}),
        ...(page_max ? { page_max } : {})
      });
      return;
    }
    renderCardCheckboxes();
    gridPager("lib-pager", data, p => ({
      ...(q ? { q } : {}),
      ...(category ? { category } : {}),
      ...(tags ? { tags, tag_mode: tag_mode, ...(tag_match !== "exact" ? { tag_match } : {}) } : {}),
      ...(order_by && order_by !== "id_desc" ? { order_by } : {}),
      ...(read_status ? { read_status } : {}),
      ...(min_rating ? { min_rating } : {}),
      ...(page_min ? { page_min } : {}),
      ...(page_max ? { page_max } : {}),
      ...(p > 1 ? { page: p } : {}),
      page_size: prefPageSize()
    }));
    bindTagSuggest();
    startInfinite("lib-grid", p => galleryGrid(null, p, extra), galleryCard);
  } catch (e) { $view().innerHTML = renderError(e.message); }
}

async function deleteFiltered() {
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  const tag_mode = app.query.tag_mode || "and";
  const tag_match = app.query.tag_match || "exact";
  const order_by = app.query.order_by || "";
  const read_status = app.query.read_status || "";
  if (!window.confirm(t("confirmDeleteFiltered"))) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    // Server-side filtered delete: pass the filter, not a resolved id list.
    // Must mirror the current browse filter, especially read_status.
    const payload = {
      q, category, tags, tag_mode, tag_match, delete_files: deleteFiles
    };
    if (order_by && order_by !== "id_desc") payload.order_by = order_by;
    if (read_status) payload.read_status = read_status;
    const urlParams = new URLSearchParams(location.hash.split("?")[1] || "");
    const minRating = urlParams.get("min_rating");
    const pageMin = urlParams.get("page_min") || urlParams.get("min_pages");
    const pageMax = urlParams.get("page_max") || urlParams.get("max_pages");
    if (minRating) payload.min_rating = parseFloat(minRating);
    if (pageMin) payload.min_pages = parseInt(pageMin, 10);
    if (pageMax) payload.max_pages = parseInt(pageMax, 10);
    const r = await api("POST", "/api/galleries/delete-filtered", payload);
    toast(t("deleted") + ": " + (r.deleted !== undefined ? r.deleted : (r.matched || 0))
      + ((r.failed_deletions || []).length ? " · " + t("dupDeleteFail") + r.failed_deletions.length : ""));
    location.hash = navHash("library");
  } catch (e) { toast(e.message); }
}

async function deleteSelected() {
  const ids = [...selGalleries];
  if (!ids.length) { toast(t("deleteSel")); return; }
  if (!window.confirm(t("confirmDeleteSel") + " (" + ids.length + ")")) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    const r = await api("POST", "/api/galleries/delete-bulk", { ids, delete_files: deleteFiles });
    selGalleries.clear();
    toast(t("deleted") + ": " + (r.deleted !== undefined ? r.deleted : ids.length)
      + ((r.failed_deletions || []).length ? " · " + t("dupDeleteFail") + r.failed_deletions.length : ""));
    router();
  } catch (e) { toast(e.message); }
}
