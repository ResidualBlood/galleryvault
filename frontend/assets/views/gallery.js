"use strict";

// views/gallery.js — Phase 1
// renderGallery moved from app.js

let preserveMoreExpandedOnce = false;

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
    const FROM_LABELS = {
      favorites: t("favorites"),
      discover: t("discover"),
      history: t("history"),
      updates: t("galleryUpdates"),
      duplicates: t("dupGalTitle"),
      integrity: t("missingPagesTitle"),
      recycle: t("recycleTitle") || t("recycle") || "Recycle",
      browse: t("browse") || "Browse",
      settings: t("settings") || "Settings",
      series: t("seriesTitle") || t("series") || "Series",
      library: t("library"),
      downloads: t("downloads") || "Downloads",
      logs: t("logs") || "Logs",
      tags: t("tags") || "Tags",
    };
    let rawFrom = (app.query.from ? String(app.query.from) : "").trim();
    rawFrom = rawFrom.replace(/^#\/?/, "").replace(/^\//, "");
    const fromPath = rawFrom.split("?")[0];
    const fromView = fromPath.split("/")[0];
    const isInvalidFrom = !rawFrom || !FROM_LABELS[fromView] || rawFrom.includes("://") || rawFrom.startsWith("//") || /^javascript:/i.test(rawFrom);

    let backHref;
    let backLabel;
    if (isInvalidFrom) {
      backHref = navHash("library", {}, libraryContext());
      backLabel = t("library");
    } else {
      backLabel = FROM_LABELS[fromView];
      const isOnlyView = FROM_LABELS[rawFrom] && !rawFrom.includes("?") && !rawFrom.includes("/");
      if (isOnlyView) {
        backHref = rawFrom === "library" ? navHash("library", {}, libraryContext()) : navHash(rawFrom);
      } else {
        backHref = "#/" + rawFrom;
      }
    }
    const galleryCtx = { ...libraryContext(), ...(!isInvalidFrom ? { from: rawFrom } : {}) };
    const pageStart = (thumbPage - 1) * perPage;
    const thumbsVisible = thumbsAll.slice(pageStart, pageStart + perPage);
    const thumbs = thumbsVisible.map(p => `
      <a class="thumb" href="${navHash("reader", { id, page: p.index }, galleryCtx)}">
        <img loading="lazy" src="/api/galleries/${id}/thumb/${p.index}" alt="Page ${p.index + 1}">
      </a>`).join("");
    const thumbPagerParts = [];
    if (thumbPage > 1) {
      thumbPagerParts.push(`<a class="page-link" href="${navHash("gallery", { id }, { ...galleryCtx, page: thumbPage - 1, page_size: perPage })}">&lt;</a>`);
    }
    for (let p = Math.max(1, thumbPage - 2); p <= Math.min(totalPages, thumbPage + 2); p++) {
      thumbPagerParts.push(p === thumbPage
        ? `<strong class="cur" aria-current="page">${p}</strong>`
        : `<a class="page-link" href="${navHash("gallery", { id }, { ...galleryCtx, page: p, page_size: perPage })}">${p}</a>`);
    }
    if (thumbPage < totalPages) {
      thumbPagerParts.push(`<a class="page-link" href="${navHash("gallery", { id }, { ...galleryCtx, page: thumbPage + 1, page_size: perPage })}">&gt;</a>`);
    }
    const txtMore = app.lang === "zh" ? "更多" : (t("navMore") || "More");
    const txtCollapse = app.lang === "zh" ? "收起" : "Collapse";
    const isMoreExpanded = preserveMoreExpandedOnce;
    preserveMoreExpandedOnce = false;
    $view().innerHTML = `
      <div class="gallery-detail">
        <a class="link-button" href="${backHref}">← ${esc(backLabel)}</a>
        <header style="margin-top:16px"><p class="eyebrow">${esc(g.storage_type)} · LOCAL GALLERY</p><h1>${esc(g.title)}</h1>
        <p class="sub">gid ${esc(g.gid || "local")} · ${g.page_count} pages · ${esc(t("progress"))} ${progress.current_page + 1}/${progress.total_pages || g.page_count} · ${fmtSize(g.file_size || 0)} <span id="gallery-favcats"></span> ${qualityBadge}</p></header>
        <div class="toolbar">
          <a class="btn btn-primary" href="${navHash("reader", { id, page: progress.current_page }, galleryCtx)}" style="padding:8px 14px;border-radius:4px">${esc(t("readNow"))}</a>
          ${g.eh_url ? `<a class="btn btn-secondary" href="${esc(g.eh_url)}" target="_blank" rel="noopener" title="${esc(t("ehLoginNote"))}">${esc(t("openEh"))}</a>` : ""}
          <button class="btn btn-secondary" data-action="sync-tags" data-id="${id}" type="button">${esc(t("syncTags"))}</button>
          <button class="btn btn-secondary" data-action="favorite-gallery" data-id="${id}" data-gid="${g.gid || ""}" data-token="${g.token || ""}" type="button" hidden>⭐ ${esc(t("addToFavorites"))}</button>
          <button class="btn btn-secondary" data-action="move-gallery-favorite" data-id="${id}" data-gid="${g.gid || ""}" type="button" hidden>${esc(t("changeFavCategory"))}</button>
          <button class="btn btn-secondary" data-action="unfavorite-gallery" data-id="${id}" data-gid="${g.gid || ""}" type="button" hidden>${esc(t("unfavorite"))}</button>
          ${showOrigBtns ? `<button class="btn btn-secondary" data-action="download-original" data-id="${g.id}" data-gid="${g.gid}" type="button">${esc(t("dlOrig"))}</button>
          <button class="btn btn-secondary" data-action="download-original-archive" data-id="${g.id}" data-gid="${g.gid}" type="button">${esc(t("dlOrigArchive"))}</button>` : ""}
          <button class="btn btn-secondary" data-action="export-cbz" data-id="${g.id}" type="button">${esc(t("exportCbz"))}</button>
          <button class="btn btn-secondary" id="gallery-more-btn" type="button">${isMoreExpanded ? esc(txtCollapse) : esc(txtMore)}</button>
          <button class="btn btn-danger" data-action="delete-gallery" data-id="${g.id}" type="button">${esc(t("deleteGallery"))}</button>
        </div>
        <section id="gallery-more-section"${isMoreExpanded ? "" : " hidden"}>
          <details open>
            <summary>${esc(t("localRating"))}</summary>
            <div class="toolbar">
              <select id="local-rating">
                <option value="">—</option>
                ${[1,2,3,4,5].map(n => `<option value="${n}"${g.local_rating === n ? " selected" : ""}>${n}★</option>`).join("")}
              </select>
              <button class="btn btn-secondary" data-action="save-local" data-id="${id}" type="button">${esc(t("saveLocal"))}</button>
            </div>
          </details>
          <details open>
            <summary>${esc(t("localTags"))}</summary>
            <div class="toolbar">
              <input id="local-tags" value="${esc((g.tags || []).filter(tg => tg.namespace === "local").map(tg => tg.name).join(", "))}" placeholder="${esc(t("localTags"))}" style="min-width:180px">
              <button class="btn btn-secondary" data-action="save-local" data-id="${id}" type="button">${esc(t("saveLocal"))}</button>
            </div>
          </details>
          <details open>
            <summary>${esc(t("localNote"))}</summary>
            <div class="toolbar">
              <textarea id="local-note" rows="2" placeholder="${esc(t("localNote"))}" style="width:100%">${esc(g.local_note || "")}</textarea>
              <button class="btn btn-secondary" data-action="save-local" data-id="${id}" type="button">${esc(t("saveLocal"))}</button>
            </div>
          </details>
          <details open>
            <summary>${esc(t("galleryLists"))}</summary>
            <div class="toolbar" id="gallery-lists"></div>
          </details>
        </section>
        <section><h2>${esc(t("tagSection"))}</h2><div class="tag-groups">${tagHtml || `<span class="muted">${esc(t("noTags"))}</span>`}</div></section>
        <section><h2>${esc(t("pagesSection"))}</h2>
          <div class="thumbs">${thumbs}</div>
          <div class="pages pager">${thumbPagerParts.join(" ")} ${pagerJump(thumbPage, totalPages)} · ${esc(t("perPage"))} ${pageSizeSelect(perPage, "gallery")}</div>
        </section>
      </div>`;

    const moreBtn = document.getElementById("gallery-more-btn");
    const moreSection = document.getElementById("gallery-more-section");
    if (moreBtn && moreSection) {
      moreBtn.addEventListener("click", () => {
        const expanded = !moreSection.hidden;
        moreSection.hidden = expanded;
        moreBtn.textContent = expanded ? txtMore : txtCollapse;
      });
    }
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
          const oldNote = $view().querySelector("#fav-note");
          if (oldNote) oldNote.closest("details")?.remove();
          const noteWrap = document.createElement("details");
          noteWrap.innerHTML = `<summary>${esc(t("favNote"))}</summary>
            <div class="toolbar">
              <input id="fav-note" value="${esc(fav.note || "")}" placeholder="${esc(t("favNote"))}" style="min-width:220px">
              <button class="btn btn-secondary" data-action="save-fav-note" data-gid="${fav.gid}" data-token="${esc(fav.token || g.token || "")}" data-favcat="${(fav.favcats && fav.favcats[0] != null) ? fav.favcats[0] : 0}" type="button">${esc(t("saveFavNote"))}</button>
            </div>`;
          const header = $view().querySelector("header");
          if (header) header.insertAdjacentElement("afterend", noteWrap);
        } else {
          if (addBtn) {
            addBtn.hidden = false;
            addBtn.dataset.gid = fav.gid || g.gid;
            addBtn.dataset.token = fav.token || g.token || "";
          }
          if (moveBtn) moveBtn.hidden = true;
          if (unfavBtn) unfavBtn.hidden = true;
          if (favcatEl) favcatEl.innerHTML = "";
          const oldNote = $view().querySelector("#fav-note");
          if (oldNote) oldNote.closest("details")?.remove();
        }
      } catch (_) {}
    }
    fillGalleryLists(id);
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function fillGalleryLists(id) {
  const el = document.getElementById("gallery-lists");
  if (!el) return;
  try {
    const [all, mine] = await Promise.all([
      api("GET", "/api/lists"),
      api("GET", `/api/galleries/${id}/lists`),
    ]);
    const mineIds = new Set(((mine && mine.items) || []).map(it => it.id));
    const items = (all && all.items) || [];
    el.innerHTML = items.map(it => mineIds.has(it.id)
      ? `<button class="btn btn-secondary" data-action="gallery-list-remove" data-id="${id}" data-list="${it.id}" type="button">${esc(t("listRemove"))}: ${esc(it.name)}</button>`
      : `<button class="btn btn-secondary" data-action="gallery-list-add" data-id="${id}" data-list="${it.id}" type="button">${esc(t("listAdd"))}: ${esc(it.name)}</button>`
    ).join("");
  } catch (_) {}
}

async function saveGalleryLocal() {
  const id = app.params.id;
  const ratingEl = document.getElementById("local-rating");
  const noteEl = document.getElementById("local-note");
  const tagsEl = document.getElementById("local-tags");
  const rating = ratingEl && ratingEl.value ? parseInt(ratingEl.value, 10) : null;
  const local_tags = tagsEl && tagsEl.value
    ? tagsEl.value.split(/[,，]/).map(s => s.trim()).filter(Boolean)
    : [];
  try {
    await api("PATCH", `/api/galleries/${id}/local`, {
      local_rating: rating,
      local_note: noteEl ? noteEl.value : "",
      local_tags,
    });
    toast(t("saveLocal"));
    preserveMoreExpandedOnce = true;
    renderGallery();
  } catch (e) { toast(e.message); }
}

async function saveGalleryFavNote() {
  const el = document.querySelector('[data-action="save-fav-note"]');
  const input = document.getElementById("fav-note");
  if (!el) return;
  const gid = parseInt(el.getAttribute("data-gid"), 10);
  try {
    const r = await api("POST", "/api/favorites/note", {
      gid,
      token: el.getAttribute("data-token") || "",
      favcat: parseInt(el.getAttribute("data-favcat"), 10) || 0,
      note: input ? input.value : "",
    });
    toast(r.cloud_ok ? t("saveFavNote") : t("favAddFail"));
  } catch (e) { toast(e.message || t("favAddFail")); }
}

async function galleryAddToList(el) {
  try {
    await api("POST", `/api/lists/${el.getAttribute("data-list")}/items`, {
      gallery_ids: [parseInt(el.getAttribute("data-id"), 10)],
    });
    fillGalleryLists(el.getAttribute("data-id"));
  } catch (e) { toast(e.message); }
}

async function galleryRemoveFromList(el) {
  try {
    await api("POST", `/api/lists/${el.getAttribute("data-list")}/items/remove`, {
      gallery_ids: [parseInt(el.getAttribute("data-id"), 10)],
    });
    fillGalleryLists(el.getAttribute("data-id"));
  } catch (e) { toast(e.message); }
}

function exportGalleryCbz(id) {
  const a = document.createElement("a");
  a.href = `/api/galleries/${id}/export.cbz`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
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
