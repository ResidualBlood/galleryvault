"use strict";

// I18N moved to /assets/core.js (loaded first in index.html)

const app = {
  authenticated: false, settings: null, session: {}, view: "browse", params: {}, query: {},
  lang: (localStorage.getItem("gv_lang") === "en" ? "en" : "zh"),
};

// renderCardCheckboxes moved to components.js
// $view/$topbar/sel*/timers moved to state.js

// core functions moved to /assets/core.js (t, esc, toast, api, auth, parse/nav/router etc.)

// Phase 1: renderWelcome/browse/library/gallery/reader/favorites/downloads moved to views/
// remaining (settings, logs, updates, tags, duplicates, history...) transitional here
// renderView + hooks active in core

// nsClass moved to utils.js
// (catLabel stays for now with galleryCard)

// galleryCard moved to components.js
// galleryGrid moved to utils.js (Phase 1)

// --- utils moved to utils.js (Phase 0 cleanup in Phase 1) ---
// stopInfinite, startInfinite, pageSizeSelect, jumpPage, pagerJump, gridPager,
// parseTags, prefPageSize, libraryContext, tagFilterHash, addTagHash, removeTagHash, tagFilterPills, catLabel, galleryGrid

// renderBrowse moved to assets/views/browse.js
// renderLibrary moved to assets/views/library.js

// renderGallery moved to assets/views/gallery.js

// renderReader + reader helpers moved to assets/views/reader.js (Phase 1)

// TAG_NAMESPACES moved to state.js

// tag helpers + renderTags + loads moved to assets/views/tags.js (Phase 1)

// renderHistory moved to assets/views/history.js (Phase 1)

// DL_STATUSES + dlTimer moved to state.js

// renderDownloads moved to assets/views/downloads.js

// fmtDur moved to utils.js



// FAV_MODES moved to state.js

// renderFavorites, renderFavList, favCard, renderFavPager moved to assets/views/favorites.js

// selDup/dup*/favCatNames moved to state.js

// fav support moved to views/favorites.js (loadFavNames, poll*, save*, sync*, check*, downloadMissing, favList*)

// onClick / onSubmit / toggleLang moved to events.js


async function randomGallery() {
  try { const d = await api("GET", "/api/galleries/random"); location.hash = navHash("gallery", { id: d.id }); }
  catch (e) { toast(e.message); }
}

// logTimer moved to state.js


async function clearHistory() {
  try { await api("DELETE", "/api/history"); renderHistory(); }
  catch (e) { toast(e.message); }
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

async function unfavoriteGallery(el) {
  const gid = parseInt(el.dataset.gid, 10);
  if (!gid) { toast(t("unfavoriteFail")); return; }
  if (!window.confirm(t("confirmUnfavorite"))) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: [gid], delete_local: false });
    if (r.cloud_ok) toast(t("unfavorited"));
    else toast(t("unfavoritedLocal"));
    el.hidden = true;
  } catch (e) { toast(e.message); }
}

// favList* moved to views/favorites.js

// dup support moved to views/duplicates.js (dupAction, dupSelectGroup, dupIgnoreSelected, dupUnignore)

// updates support moved to views/updates.js (updStatusKey, updateUpdSelBtn)

// delete* + tag suggest moved to views/library.js

// testExhentai/changePassword/testTelegram/generateThumbnails moved to views/settings.js

// welcome* moved to views/welcome.js
// scanLibrary kept here (called from events + welcomeScan)

async function scanLibrary() {
  try {
    await api("POST", "/api/scan");
    toast(t("scanning"));
    pollLogs();
  } catch (e) { toast(e.message); }
}

// forceUpdate/sync* moved to views/tags.js

// onChange moved to events.js

function init() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("submit", onSubmit);
  document.addEventListener("fullscreenchange", onFullscreenChange);
  window.addEventListener("hashchange", router);
  updateLangButton();
  checkAuth();
}

init();
