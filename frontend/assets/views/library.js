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
  renderView(`
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
      <button class="btn btn-primary" type="submit">${esc(t("search"))}</button>
      <button class="btn btn-secondary" data-action="scan" type="button">${esc(t("scan"))}</button>
      <button class="btn btn-secondary" data-action="sel-clear" type="button">${esc(t("clearSel"))}</button>
      <button class="btn btn-danger" data-action="sel-delete" type="button">${esc(t("deleteSel"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="btn btn-danger" data-action="delete-filtered" type="button">${esc(t("deleteFiltered"))}</button>
    </form>
    <div class="filters">${filterPill}</div>
    <div id="lib-grid"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="lib-pager"></div>`);
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
  } catch (e) { $view().innerHTML = renderError(esc(e.message)); }
}

async function deleteFiltered() {
  const q = app.query.q || "";
  const category = app.query.category || "";
  const tags = app.query.tags || "";
  const tag_mode = app.query.tag_mode || "or";
  if (!window.confirm(t("confirmDeleteFiltered"))) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    // Server-side filtered delete: pass the filter, not a resolved id list.
    const r = await api("POST", "/api/galleries/delete-filtered", {
      q, category, tags, tag_mode, delete_files: deleteFiles
    });
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

function dismiss(e) {
  document.querySelectorAll(".tag-suggest").forEach(box => {
    if (!e.target.closest(".search-box")) box.hidden = true;
  });
}

async function loadTagSuggest(q, box, input) {
  if (!box) return;
  try {
    const isCjk = /[\u3400-\u9fff\uf900-\ufaff]/u.test(q);
    const url = `/api/tags/search?q=${encodeURIComponent(q)}&page_size=8${isCjk ? "&zh=1" : ""}`;
    const data = await api("GET", url);
    const items = (data && data.items) || [];
    if (!items.length) { box.hidden = true; return; }
    box.innerHTML = items.map(it => {
      const display = tagText(it);
      return `
      <div class="suggest-item" data-tags="${esc(`${it.namespace}:${it.name}`)}" data-display="${esc(display)}">
        <span class="suggest-name">${esc(display)}</span>
        <span class="suggest-ns">${esc(nsLabel(it.namespace))} · ${it.usage_count}</span>
      </div>`;
    }).join("");
    box.hidden = false;
    box.querySelectorAll(".suggest-item").forEach(item => {
      item.addEventListener("click", () => {
        box.hidden = true;
        const tag = item.getAttribute("data-tags");
        const display = item.getAttribute("data-display") || "";
        const i = tag.indexOf(":");
        const ns = tag.slice(0, i);
        const name = tag.slice(i + 1);
        // Consume the clicked tag's text from the input so it does not also
        // act as a title keyword; the remaining words stay the text query.
        const consumed = new Set([name, display, tag, ns ? `${ns}:${display}` : ""]
          .filter(Boolean).map(s => s.trim()));
        const remaining = (input ? input.value : "").split(/\s+/).map(s => s.trim())
          .filter(s => s && !consumed.has(s)).join(" ");
        if (input) input.value = remaining;
        const curTags = parseTags(app.query.tags);
        if (!curTags.includes(tag)) curTags.push(tag);
        location.hash = navHash("library", {}, {
          ...(remaining ? { q: remaining } : {}),
          ...(app.query.category ? { category: app.query.category } : {}),
          tags: curTags.join(","),
          tag_mode: "and",
        });
      });
    });
  } catch (_) { box.hidden = true; }
}
