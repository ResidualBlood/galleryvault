"use strict";

// components.js — UI 组件 (galleryCard, renderCardCheckboxes, 以及未来 skeleton/pager/modal 等)
// 保持原有函数签名

function renderCardCheckboxes() {
  document.querySelectorAll(".gc-check input").forEach(cb => {
    cb.addEventListener("change", () => {
      const id = parseInt(cb.getAttribute("data-gallery-id"), 10);
      if (cb.checked) selGalleries.add(id); else selGalleries.delete(id);
      const btn = document.querySelector('[data-action="sel-delete"]');
      if (btn) btn.textContent = `${t("deleteSel")}${selGalleries.size ? ` (${selGalleries.size})` : ""}`;
    });
  });
  document.querySelectorAll('.gc-check input[data-fav-gid]').forEach(cb => {
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-fav-gid"), 10);
      if (cb.checked) selFav.add(gid); else selFav.delete(gid);
      const update = () => {
        document.querySelectorAll('[data-action="favlist-download"], [data-action="favlist-download-orig"], [data-action="favlist-archive"], [data-action="favlist-unfav"]').forEach(b => {
          const base = b.getAttribute("data-action") === "favlist-download" ? t("favDl")
            : b.getAttribute("data-action") === "favlist-download-orig" ? t("favDlOrig")
            : b.getAttribute("data-action") === "favlist-archive" ? t("favDlArchive")
            : t("favRemove");
          b.textContent = base + (selFav.size ? ` (${selFav.size})` : "");
        });
      };
      update();
    });
  });
  document.querySelectorAll('#dup-groups input[data-dup-gid]').forEach(cb => {
    cb.addEventListener("change", () => {
      const gid = parseInt(cb.getAttribute("data-dup-gid"), 10);
      if (cb.checked) selDup.add(gid); else selDup.delete(gid);
      updateDupButtons();
    });
  });
}

function galleryCard(it) {
  const cat = esc(catLabel(it.category));
  const ctx = app.view === "library" ? libraryContext() : {};
  return `<div class="gc-wrap">
    <a class="gc" href="${navHash("gallery", { id: it.id }, ctx)}">
      <div class="gc-cover">
        ${it.cover_url ? `<img loading="lazy" src="${it.cover_url}" alt="">` : `<span class="badge">no cover</span>`}
        <span class="gc-cat">${cat}</span>
        <span class="gc-pages">${it.page_count} P</span>
      </div>
      <div class="gc-title">${esc(it.title)}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-gallery-id="${it.id}"${selGalleries.has(it.id) ? " checked" : ""}></label>
  </div>`;
}

// 占位：未来加 favCard, modal, skeleton, empty-state 等
// function renderPager(...) {}
