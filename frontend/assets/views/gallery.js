"use strict";

// views/gallery.js — Phase 1
// renderGallery moved from app.js

async function renderGallery() {
  const id = app.params.id;
  $view().innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    const [galleryRes, progressRes] = await Promise.allSettled([
      api("GET", `/api/galleries/${id}`),
      api("GET", `/api/galleries/${id}/progress`),
    ]);
    if (galleryRes.status !== "fulfilled") {
      throw galleryRes.reason || new Error("Failed to load gallery");
    }
    const g = galleryRes.value;
    const qualityBadge = g.image_quality === "original"
      ? `<span class="badge quality-badge">${esc(t("origBadge"))}</span>`
      : g.image_quality === "resample"
        ? `<span class="badge quality-badge">${esc(t("resampleBadge"))}</span>`
        : "";
    const showOrigBtns = !!(g.gid && g.image_quality !== "original");
    let progress = progressRes.status === "fulfilled" && progressRes.value
      ? progressRes.value
      : { current_page: 0, total_pages: g.page_count };
    const order = ["parody", "character", "group", "artist", "language", "category", "misc"];
    const byNs = {};
    for (const tg of (g.tags || [])) (byNs[tg.namespace] = byNs[tg.namespace] || []).push(tg);
    const nsList = Object.keys(byNs).sort((a, b) => order.indexOf(a) - order.indexOf(b));
    const tagHtml = nsList.map(ns => `
      <div class="tag-group"><strong>${esc(nsLabel(ns))}</strong><div class="tag-list">
        ${byNs[ns].map(tg => `<a class="tag ${nsClass(tg.namespace)}" href="${addTagHash(tg.namespace, tg.name)}">${esc(tagText(tg))}</a>`).join("")}
      </div></div>`).join("");
    const thumbsAll = g.pages || [];
    const perPage = prefPageSize(30);
    const totalPages = Math.max(1, Math.ceil(thumbsAll.length / perPage));
    const explicitPage = parseInt(app.query.page || "", 10);
    let thumbPage;
    if (explicitPage > 0) {
      thumbPage = Math.min(explicitPage, totalPages);
    } else if (progress.current_page > 0) {
      thumbPage = Math.min(Math.floor(progress.current_page / perPage) + 1, totalPages);
    } else {
      thumbPage = 1;
    }
    const pageStart = (thumbPage - 1) * perPage;
    const thumbsVisible = thumbsAll.slice(pageStart, pageStart + perPage);
    const thumbs = thumbsVisible.map(p => `
      <a class="thumb" href="${navHash("reader", { id, page: p.index }, libraryContext())}">
        <img loading="lazy" src="/api/galleries/${id}/thumb/${p.index}" alt="Page ${p.index + 1}">
      </a>`).join("");
    const thumbPagerParts = [];
    if (thumbPage > 1) {
      thumbPagerParts.push(`<a class="page-link" href="${navHash("gallery", { id }, { ...libraryContext(), page: thumbPage - 1, page_size: perPage })}">&lt;</a>`);
    }
    for (let p = Math.max(1, thumbPage - 2); p <= Math.min(totalPages, thumbPage + 2); p++) {
      thumbPagerParts.push(p === thumbPage
        ? `<strong class="cur" aria-current="page">${p}</strong>`
        : `<a class="page-link" href="${navHash("gallery", { id }, { ...libraryContext(), page: p, page_size: perPage })}">${p}</a>`);
    }
    if (thumbPage < totalPages) {
      thumbPagerParts.push(`<a class="page-link" href="${navHash("gallery", { id }, { ...libraryContext(), page: thumbPage + 1, page_size: perPage })}">&gt;</a>`);
    }
    $view().innerHTML = `
      <a class="link-button" href="${navHash("library", {}, libraryContext())}">← ${esc(t("library"))}</a>
      <header style="margin-top:16px"><p class="eyebrow">${esc(g.storage_type)} · LOCAL GALLERY</p><h1>${esc(g.title)}</h1>
      <p class="sub">gid ${esc(g.gid || "local")} · ${g.page_count} pages · ${esc(t("progress"))} ${progress.current_page}/${progress.total_pages || g.page_count} · ${fmtSize(g.file_size || 0)} <span id="gallery-favcats"></span> ${qualityBadge}</p></header>
      <div class="toolbar">
        <a class="btn btn-primary" href="${navHash("reader", { id, page: progress.current_page }, libraryContext())}" style="padding:8px 14px;border-radius:4px">${esc(t("readNow"))}</a>
        ${g.eh_url ? `<a class="btn btn-secondary" href="${esc(g.eh_url)}" target="_blank" rel="noopener" title="${esc(t("ehLoginNote"))}">${esc(t("openEh"))}</a>` : ""}
        <button class="btn btn-secondary" data-action="sync-tags" data-id="${id}" type="button">${esc(t("syncTags"))}</button>
        <button class="btn btn-secondary" data-action="favorite-gallery" data-id="${id}" data-gid="${g.gid || ""}" data-token="${g.token || ""}" type="button" hidden>⭐ ${esc(t("addToFavorites"))}</button>
        <button class="btn btn-secondary" data-action="move-gallery-favorite" data-id="${id}" data-gid="${g.gid || ""}" type="button" hidden>${esc(t("changeFavCategory"))}</button>
        <button class="btn btn-secondary" data-action="unfavorite-gallery" data-id="${id}" data-gid="${g.gid || ""}" type="button" hidden>${esc(t("unfavorite"))}</button>
        ${showOrigBtns ? `<button class="btn btn-secondary" data-action="download-original" data-id="${g.id}" data-gid="${g.gid}" type="button">${esc(t("dlOrig"))}</button>
        <button class="btn btn-secondary" data-action="download-original-archive" data-id="${g.id}" data-gid="${g.gid}" type="button">${esc(t("dlOrigArchive"))}</button>` : ""}
        <button class="btn btn-danger" data-action="delete-gallery" data-id="${g.id}" type="button">${esc(t("deleteGallery"))}</button>
      </div>
      <section><h2>${esc(t("tagSection"))}</h2><div class="tag-groups">${tagHtml || `<span class="muted">${esc(t("noTags"))}</span>`}</div></section>
      <section><h2>${esc(t("pagesSection"))}</h2>
        <div class="thumbs">${thumbs}</div>
        <div class="pages pager">${thumbPagerParts.join(" ")} ${pagerJump(thumbPage, totalPages)} · ${esc(t("perPage"))} ${pageSizeSelect(perPage, "gallery")}</div>
      </section>`;
    if (g.gid) {
      try {
        const fav = await api("GET", `/api/galleries/${id}/favorite`);
        const favcatEl = document.getElementById("gallery-favcats");
        const addBtn = document.querySelector('[data-action="favorite-gallery"]');
        const moveBtn = document.querySelector('[data-action="move-gallery-favorite"]');
        const unfavBtn = document.querySelector('[data-action="unfavorite-gallery"]');
        if (fav.favorite) {
          if (addBtn) addBtn.hidden = true;
          if (moveBtn) {
            moveBtn.hidden = false;
            moveBtn.dataset.gid = fav.gid;
            moveBtn.dataset.favcat = (fav.favcats && fav.favcats[0] != null) ? fav.favcats[0] : 0;
          }
          if (unfavBtn) {
            unfavBtn.hidden = false;
            unfavBtn.dataset.gid = fav.gid;
          }
          if (favcatEl) {
            favcatEl.innerHTML = (fav.favcat_names || []).map(n =>
              `<a class="badge" href="#/favorites/${n.favcat}?from=${id}" style="color:var(--accent)">${esc(n.name || ("#" + n.favcat))}</a>`
            ).join(" ");
          }
        } else {
          if (addBtn) {
            addBtn.hidden = false;
            addBtn.dataset.gid = fav.gid || g.gid;
            addBtn.dataset.token = fav.token || g.token || "";
          }
          if (moveBtn) moveBtn.hidden = true;
          if (unfavBtn) unfavBtn.hidden = true;
          if (favcatEl) favcatEl.innerHTML = "";
        }
      } catch (_) {}
    }
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function deleteGallery(id) {
  if (!window.confirm(t("confirmDelete"))) return;
  const deleteFiles = window.confirm(t("deleteFiles"));
  try {
    await api("DELETE", `/api/galleries/${id}?delete_files=${deleteFiles}`);
    toast(t("deleted"));
    location.hash = navHash("library");
  } catch (e) { toast(e.message); }
}

async function downloadOriginalGallery(id, gid, archive) {
  if (archive) {
    const tier = await showArchiveDialog([parseInt(gid, 10)], { lockTier: "original" });
    if (!tier) return;
  }
  try {
    await api("POST", `/api/galleries/${id}/download-original`, { archive });
    toast(t(archive ? "dlOrigArchiveQueued" : "dlOrigQueued"));
  } catch (e) { toast(e.message); }
}

async function favoriteGallery(el) {
  const gid = parseInt(el.dataset.gid, 10);
  const token = el.dataset.token || "";
  if (!gid) { toast(t("favAddFail")); return; }
  const targetFavcat = await showMoveFavoritesDialog([gid], null, {
    title: t("favAddTitle"),
    confirmText: t("favAddConfirm"),
    targetLabel: t("favMoveTarget"),
  });
  if (targetFavcat == null) return;
  try {
    const r = await api("POST", "/api/favorites/add", {
      gid,
      token,
      target_favcat: targetFavcat,
    });
    if (r.cloud_ok) {
      toast(t("favAdded"));
    } else {
      toast(t("favAddFail"));
    }
    renderGallery();
  } catch (e) {
    toast(e.message || t("favAddFail"));
  }
}

async function moveGalleryFavorite(el) {
  const gid = parseInt(el.dataset.gid, 10);
  const curFavcat = parseInt(el.dataset.favcat, 10);
  if (!gid) return;
  const targetFavcat = await showMoveFavoritesDialog([gid], curFavcat);
  if (targetFavcat == null || targetFavcat === curFavcat) return;
  try {
    const r = await api("POST", "/api/favorites/move", {
      gids: [gid],
      target_favcat: targetFavcat,
    });
    if (r.cloud_ok) {
      toast(t("favMoved"));
    } else {
      toast(t("favMovedPartial").replace("{count}", r.local_moved).replace("{failed}", (r.cloud_failed || []).length));
    }
    renderGallery();
  } catch (e) {
    toast(e.message);
  }
}

async function unfavoriteGallery(el) {
  const gid = parseInt(el.dataset.gid, 10);
  if (!gid) { toast(t("unfavoriteFail")); return; }
  if (!window.confirm(t("confirmUnfavorite"))) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: [gid], delete_local: false });
    if (r.cloud_ok) toast(t("unfavorited"));
    else toast(t("unfavoritedLocal"));
    renderGallery();
  } catch (e) { toast(e.message); }
}
