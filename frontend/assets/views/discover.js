"use strict";

const DISC_CATS = ["doujinshi","manga","artistcg","gamecg","western","non-h","image_set","cosplay","asianporn","misc"];
const DISC_CAT_BITS = {
  doujinshi: 1, manga: 2, artistcg: 4, gamecg: 8, western: 16,
  "non-h": 32, image_set: 64, cosplay: 128, asianporn: 256, misc: 512
};

function discoverFCatsFromForm(form) {
  let disabled = 0, anyOn = false, allOn = true;
  DISC_CATS.forEach(c => {
    const el = form.querySelector(`input[name="cat"][value="${c}"]`);
    const on = !el || el.checked;
    if (on) anyOn = true;
    else { allOn = false; disabled |= DISC_CAT_BITS[c]; }
  });
  if (!anyOn || allOn) return "";
  return String(disabled);
}

function discoverCatsChecked(maskStr) {
  const mask = parseInt(maskStr || "0", 10) || 0;
  const set = {};
  DISC_CATS.forEach(c => { set[c] = !(mask & DISC_CAT_BITS[c]); });
  return set;
}

function discoverQuality() {
  const el = document.getElementById("discover-quality");
  return (el && el.value === "original") ? "original" : "resample";
}

function discoverStateMessage(state) {
  if (state === "empty") return renderEmpty(t("discoverEmpty"));
  if (state === "no_exhentai_access") return renderError(t("discoverSadPanda"));
  if (state === "not_logged_in") return renderError(t("cookieExpiredNotice"));
  if (state === "challenge") return renderError(t("discoverChallenge"));
  if (state === "rate_limited") return renderError(t("discoverRateLimited"));
  return renderError(t("discoverError"));
}

async function fetchDiscover(nextCursor) {
  const params = new URLSearchParams();
  if (app.query.q) params.set("q", app.query.q);
  if (app.query.category) params.set("category", app.query.category);
  if (app.query.min_rating) params.set("min_rating", app.query.min_rating);
  if (app.query.list && app.query.list !== "search") params.set("list", app.query.list);
  if (app.query.list === "toplist") params.set("tl", app.query.tl || "15");
  if (nextCursor) params.set("next", nextCursor);
  return await api("GET", "/api/eh/search?" + params.toString());
}

function discoverCard(it) {
  const cat = it.category ? esc(catLabel(it.category)) : "";
  const badges = [];
  if (it.in_library) badges.push(`<span class="disc-badge in">${esc(t("discoverInLibrary"))}</span>`);
  if (it.favorited) badges.push(`<span class="disc-badge fav">${esc(t("discoverFavorited"))}</span>`);
  if (!it.downloaded) badges.push(`<span class="disc-badge nodl">${esc(t("discoverNotDownloaded"))}</span>`);
  const thumb = String(it.thumb || "");
  const thumbLow = thumb.toLowerCase();
  const ehgtThumb = thumbLow.startsWith("https://ehgt.org/");
  let cover;
  if (it.gallery_id) {
    cover = `<img loading="lazy" src="/api/galleries/${it.gallery_id}/thumb/0" alt="">`;
  } else if (ehgtThumb) {
    cover = `<img loading="lazy" src="${esc(it.thumb)}" alt="" referrerpolicy="no-referrer">`;
  } else {
    cover = `<div class="cover-placeholder" style="width:100%;height:100%;background:var(--panel-2);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">${esc(t("noCover"))}</div>`;
  }
  const href = it.gallery_id ? navHash("gallery", { id: it.gallery_id }) : esc(it.url || "#");
  const extra = it.gallery_id ? "" : ` target="_blank" rel="noopener"`;
  const rating = it.rating != null ? `<span class="gc-size">★ ${esc(it.rating)}</span>` : "";
  const gid = it.gid;
  const token = esc(it.token || "");
  const title = esc(it.title || "");
  return `<div class="gc-wrap" data-gid="${gid}" data-token="${token}">
    <a class="gc" href="${href}"${extra} role="link" aria-label="${title}">
      <div class="gc-cover">
        ${cover}
        <span class="disc-badges">${badges.join("")}</span>
        ${cat ? `<span class="gc-cat">${cat}</span>` : ""}
        ${it.pages ? `<span class="gc-pages">${it.pages} P</span>` : ""}
      </div>
      <div class="gc-title">${title}</div>
      ${rating}
    </a>
    <div class="disc-actions">
      <button type="button" class="btn btn-secondary" data-action="discover-dl" data-gid="${gid}" data-token="${token}" data-title="${title}">${esc(t("discoverDownload"))}</button>
      <button type="button" class="btn btn-secondary" data-action="discover-fav" data-gid="${gid}" data-token="${token}" data-title="${title}">${esc(t("addToFavorites"))}</button>
    </div>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-discover-gid="${gid}" data-token="${token}" data-title="${title}"${selDiscover.has(gid) ? " checked" : ""}></label>
  </div>`;
}

function startDiscoverInfinite(nextCursor) {
  stopInfinite();
  const container = document.getElementById("disc-grid");
  if (!container || !nextCursor) return;
  const grid = container.querySelector(".grid.gc-grid");
  if (!grid) return;
  let cursor = nextCursor;
  let loading = false;
  let finished = false;
  const sentinel = document.createElement("div");
  sentinel.className = "inf-scroll-sentinel";
  grid.appendChild(sentinel);
  const controller = new AbortController();
  const observer = new IntersectionObserver(async (entries) => {
    if (finished || loading) return;
    if (!(entries[0] && entries[0].isIntersecting)) return;
    if (controller.signal.aborted || !cursor) return;
    loading = true;
    try {
      const data = await fetchDiscover(cursor);
      if (controller.signal.aborted) return;
      if (!document.contains(grid) || !document.contains(sentinel)) { finished = true; return; }
      if (data && data.state && data.state !== "ok") {
        finished = true;
        toast(t(data.state === "rate_limited" ? "discoverRateLimited"
          : data.state === "challenge" ? "discoverChallenge"
          : data.state === "no_exhentai_access" ? "discoverSadPanda"
          : data.state === "not_logged_in" ? "cookieExpiredNotice"
          : "discoverError"));
        if (data.state === "not_logged_in" || data.state === "no_exhentai_access") refreshCookieHealth();
        try { observer.disconnect(); } catch (_) {}
        sentinel.remove();
        return;
      }
      const items = (data && data.items) || [];
      if (!items.length) {
        finished = true;
        try { observer.disconnect(); } catch (_) {}
        sentinel.remove();
        return;
      }
      cursor = data.next || null;
      sentinel.insertAdjacentHTML("beforebegin", items.map(discoverCard).join(""));
      renderCardCheckboxes();
      if (!cursor) {
        finished = true;
        try { observer.disconnect(); } catch (_) {}
        sentinel.remove();
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      finished = true;
      toast(err.message || t("discoverError"));
      try { observer.disconnect(); } catch (_) {}
      sentinel.remove();
    } finally { loading = false; }
  }, { rootMargin: "900px" });
  observer.observe(sentinel);
  infiniteState = { observer, controller, sentinel };
}

async function renderDiscover() {
  const q = app.query.q || "";
  const category = app.query.category || "";
  const min_rating = app.query.min_rating || "";
  const quality = app.query.quality || "resample";
  const list = app.query.list || "search";
  const tl = app.query.tl || "15";
  const cats = discoverCatsChecked(category);
  const selCount = selDiscover.size;
  const listBtn = (id, label) =>
    `<button class="btn ${list === id ? "btn-primary" : "btn-secondary"}" data-action="discover-list" data-list="${id}" type="button">${esc(label)}</button>`;
  renderView(`
    <header><p class="eyebrow">EXHENTAI</p><h1>${esc(t("discover"))}</h1><p class="sub">${esc(t("discoverSub"))}</p></header>
    <form class="toolbar" data-action="discover-search">
      <input type="hidden" name="list" value="${esc(list)}">
      ${listBtn("search", t("discoverSearch"))}
      ${listBtn("popular", t("discoverPopular"))}
      ${listBtn("watched", t("discoverWatched"))}
      ${listBtn("toplist", t("discoverToplist"))}
      ${list === "toplist" ? `<select name="tl">
        <option value="11"${tl === "11" ? " selected" : ""}>${esc(t("toplistYesterday"))}</option>
        <option value="12"${tl === "12" ? " selected" : ""}>${esc(t("toplistMonth"))}</option>
        <option value="13"${tl === "13" ? " selected" : ""}>${esc(t("toplistYear"))}</option>
        <option value="15"${tl === "15" || !tl ? " selected" : ""}>${esc(t("toplistAll"))}</option>
      </select>` : ""}
      <div class="search-box">
        <input name="q" value="${esc(q)}" placeholder="${esc(t("discoverPlaceholder"))}" autocomplete="off">
      </div>
      <select name="min_rating" title="${esc(t("minRating"))}">
        <option value=""${!min_rating ? " selected" : ""}>${esc(t("minRating"))}</option>
        <option value="2"${min_rating === "2" ? " selected" : ""}>≥2</option>
        <option value="3"${min_rating === "3" ? " selected" : ""}>≥3</option>
        <option value="4"${min_rating === "4" ? " selected" : ""}>≥4</option>
        <option value="5"${min_rating === "5" ? " selected" : ""}>≥5</option>
      </select>
      <select name="quality" id="discover-quality" title="${esc(t("quality"))}">
        <option value="resample"${quality !== "original" ? " selected" : ""}>${esc(t("qualityResample"))}</option>
        <option value="original"${quality === "original" ? " selected" : ""}>${esc(t("qualityOriginal"))}</option>
      </select>
      <button class="btn btn-primary" type="submit">${esc(t("search"))}</button>
      <button class="btn btn-secondary" data-action="disc-clear" type="button">${esc(t("clearSel"))}</button>
      <button class="btn btn-secondary" data-action="disc-batch-dl" type="button">${esc(selCount ? t("discoverBatchDl") + " (" + selCount + ")" : t("discoverBatchDl"))}</button>
      <button class="btn btn-secondary" data-action="disc-batch-fav" type="button">${esc(selCount ? t("discoverBatchFav") + " (" + selCount + ")" : t("discoverBatchFav"))}</button>
      <div class="disc-cats">
        ${DISC_CATS.map(c => `<label><input type="checkbox" name="cat" value="${c}" ${cats[c] ? "checked" : ""}> ${esc(catLabel(c))}</label>`).join("")}
      </div>
    </form>
    <div id="disc-grid"><div class="grid gc-grid">${renderSkeleton(8)}</div></div>`);
  try {
    const data = await fetchDiscover(null);
    const el = document.getElementById("disc-grid");
    if (!el) return;
    if (data.state === "not_logged_in" || data.state === "no_exhentai_access") refreshCookieHealth();
    if (!data || (data.state && data.state !== "ok")) {
      el.innerHTML = discoverStateMessage(data && data.state);
      return;
    }
    if (!data.items || !data.items.length) {
      el.innerHTML = renderEmpty(t("discoverEmpty"));
      return;
    }
    el.innerHTML = `<div class="grid gc-grid">` + data.items.map(discoverCard).join("") + `</div>`;
    renderCardCheckboxes();
    startDiscoverInfinite(data.next);
  } catch (e) {
    const el = document.getElementById("disc-grid");
    if (el) el.innerHTML = renderError(e.message || t("discoverError"));
    else $view().innerHTML = renderError(e.message || t("discoverError"));
  }
}

function discoverSelectedItems() {
  const items = [];
  selDiscover.forEach(gid => {
    const el = document.querySelector(`.gc-check input[data-discover-gid="${gid}"]`);
    if (!el) return;
    items.push({
      gid,
      token: el.getAttribute("data-token") || "",
      title: el.getAttribute("data-title") || "",
    });
  });
  return items;
}

async function discoverDownloadOne(el) {
  const gid = parseInt(el.getAttribute("data-gid"), 10);
  const token = el.getAttribute("data-token") || "";
  const title = el.getAttribute("data-title") || "";
  if (!gid || !token) { toast(t("discoverError")); return; }
  try {
    await api("POST", "/api/downloads", { gid, token, title, quality: discoverQuality() });
    toast(t("dlQueuedCount").replace("{count}", "1"));
  } catch (e) { toast(e.message || t("discoverError")); }
}

async function discoverFavoriteOne(el) {
  const gid = parseInt(el.getAttribute("data-gid"), 10);
  const token = el.getAttribute("data-token") || "";
  const title = el.getAttribute("data-title") || "";
  if (!gid || !token) { toast(t("favAddFail")); return; }
  const targetFavcat = await showMoveFavoritesDialog([gid], null, {
    title: t("favAddTitle"),
    confirmText: t("favAddConfirm"),
    targetLabel: t("favMoveTarget"),
  });
  if (targetFavcat == null) return;
  try {
    const r = await api("POST", "/api/favorites/add", { gid, token, title, target_favcat: targetFavcat });
    if (r && r.cloud_ok) toast(t("favAdded"));
    else toast(t("favAddFail"));
  } catch (e) { toast(e.message || t("favAddFail")); }
}

async function discoverBatchDownload() {
  const items = discoverSelectedItems().filter(it => it.token);
  if (!items.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/downloads/batch", {
      items: items.map(it => ({ gid: it.gid, token: it.token, title: it.title })),
      quality: discoverQuality(),
    });
    const queued = (r && r.queued) || 0;
    const skipped = (r && r.skipped) || 0;
    toast(t("dlQueuedCount").replace("{count}", queued) + (skipped ? " · " + t("dlSkippedCount").replace("{count}", skipped) : ""));
  } catch (e) { toast(e.message || t("discoverError")); }
}

async function discoverBatchFavorite() {
  const items = discoverSelectedItems().filter(it => it.gid);
  if (!items.length) { toast(t("select")); return; }
  const targetFavcat = await showMoveFavoritesDialog(items.map(it => it.gid), null, {
    title: t("favAddTitle"),
    confirmText: t("favAddConfirm"),
    targetLabel: t("favMoveTarget"),
  });
  if (targetFavcat == null) return;
  try {
    const CHUNK = 25;
    let totalAdded = 0, totalFailed = 0;
    for (let i = 0; i < items.length; i += CHUNK) {
      const chunk = items.slice(i, i + CHUNK);
      const r = await api("POST", "/api/favorites/add", { items: chunk, target_favcat: targetFavcat });
      totalAdded += r.local_added != null ? r.local_added : (r.successful_gids ? r.successful_gids.length : 0);
      totalFailed += r.cloud_failed ? r.cloud_failed.length : 0;
      if (r.cloud_ok === false && r.cloud_failed && r.cloud_failed.length === chunk.length) {
        toast(t("favAddFail"));
        break;
      }
      if (i + CHUNK < items.length) await new Promise(res => setTimeout(res, 200));
    }
    toast(t("favAddBatch").replace("{count}", totalAdded).replace("{failed}", totalFailed));
  } catch (e) { toast(e.message || t("favAddFail")); }
}
