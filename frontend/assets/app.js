"use strict";

// I18N moved to /assets/core.js (loaded first in index.html)

const app = {
  authenticated: false, settings: null, session: {}, view: "browse", params: {}, query: {},
  lang: (localStorage.getItem("gv_lang") === "en" ? "en" : "zh"),
};

// renderCardCheckboxes moved to components.js
// $view/$topbar/sel*/timers moved to state.js

// core functions moved to /assets/core.js (t, esc, toast, api, auth, parse/nav/router etc.)

async function renderWelcome() {
  let st = {};
  try { st = await api("GET", "/api/onboarding/status"); } catch (_) {}
  app.onboarding = st;
  const step = (done, body) => `
    <li class="wizard-step${done ? " done" : ""}">
      <div class="w-step">${done ? "✓" : "·"}</div>
      <div class="w-body">${body}</div>
    </li>`;
  const passwordBlock = st.password_default ? `
    <div class="w-form">
      <input name="current_password" type="password" placeholder="${esc(t("currentPassword"))}" autocomplete="current-password">
      <input name="new_password" type="password" placeholder="${esc(t("newPassword"))}" autocomplete="new-password">
      <button class="primary" data-action="welcome-change-password" type="button">${esc(t("changePassword"))}</button>
    </div>` : `<p class="w-ok">${esc(t("stepDone"))}</p>`;
  const cookieBlock = st.exhentai_configured ? `<p class="w-ok">${esc(t("stepDone"))}</p>` : `
    <div class="w-form">
      ${ehBaseUrlControl("https://exhentai.org", "w_")}
      <div class="w-grid">
        <input name="w_ipb_member_id" placeholder="${esc(t("cookieId"))}" autocomplete="off">
        <input name="w_ipb_pass_hash" placeholder="${esc(t("cookieHash"))}" autocomplete="off">
        <input name="w_igneous" placeholder="${esc(t("cookieIgneous"))}" autocomplete="off">
      </div>
      <div class="w-btns">
        <button class="secondary" data-action="welcome-save-cookie" type="button">${esc(t("save"))}</button>
        <button class="secondary" data-action="welcome-test-exhentai" type="button">${esc(t("testExhentai"))}</button>
      </div>
    </div>`;
  const importBlock = st.library_count > 0 ? `<p class="w-ok">${esc(t("stepDone"))} (${st.library_count})</p>` : `
    <p>${esc(t("welcomeImportHint"))}</p>
    <div class="w-btns">
      <button class="primary" data-action="welcome-check-favs" type="button">${esc(t("checkAll"))}</button>
      <button class="secondary" data-action="welcome-scan" type="button">${esc(t("scan"))}</button>
    </div>`;
  $view().innerHTML = `
    <div class="welcome">
      <header><p class="eyebrow">GETTING STARTED</p><h1>${esc(t("welcome"))}</h1>
      <p class="sub">${esc(t("welcomeSub"))}</p></header>
      <ol class="wizard">
        ${step(!st.password_default, `<h3>${esc(t("welcomePasswordTitle"))}</h3><p>${esc(t("welcomePasswordDesc"))}</p>${passwordBlock}`)}
        ${step(st.exhentai_configured, `<h3>${esc(t("welcomeCookieTitle"))}</h3><p>${esc(t("welcomeCookieDesc"))}</p>${cookieBlock}`)}
        ${step(st.library_count > 0, `<h3>${esc(t("welcomeImportTitle"))}</h3><p>${esc(t("welcomeImportDesc"))}</p>${importBlock}`)}
      </ol>
      <div class="wizard-actions">
        <button class="primary" data-action="welcome-finish" type="button">${esc(t("welcomeFinish"))}</button>
        ${st.password_default ? "" : `<button class="link-button" data-action="welcome-later" type="button">${esc(t("welcomeLater"))}</button>`}
      </div>
    </div>`;
}

function renderLogin() {
  $view().innerHTML = `
    <div class="login-wrap"><div class="panel">
      <p class="eyebrow">PRIVATE LIBRARY</p>
      <h1>GalleryVault</h1>
      <p class="sub">${esc(t("loginSub"))}</p>
      <form data-action="login">
        <label>${esc(t("password"))}<input name="password" type="password" autocomplete="current-password" autofocus></label>
        <button class="primary" type="submit">${esc(t("login"))}</button>
      </form>
    </div></div>`;
}

// nsClass moved to utils.js
// (catLabel stays for now with galleryCard)

// galleryCard moved to components.js


async function galleryGrid(container, page, extraQuery) {
  const pageSize = extraQuery && extraQuery.page_size ? extraQuery.page_size : prefPageSize();
  const q = Object.assign({ page, page_size: pageSize }, extraQuery || {});
  delete q.page_size;
  q.page_size = pageSize;
  const qs = Object.entries(q).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
  const data = await api("GET", `/api/galleries?${qs}`);
  if (container == null) return data;
  const el = document.getElementById(container);
  if (!el) return data;
  if (!data.items.length) { el.innerHTML = `<p>${esc(t("noGalleries"))}</p>`; }
  else { el.innerHTML = `<div class="grid gc-grid">` + data.items.map(galleryCard).join("") + `</div>`; }
  return data;
}

// --- Infinite scroll -------------------------------------------------------
// Appends later pages to a grid as the user nears the bottom. The existing
// server-side pager stays as a fallback; navigation always re-renders.
// stopInfinite/startInfinite moved to utils.js
function stopInfinite() { if (infiniteState && infiniteState.observer) infiniteState.observer.disconnect(); infiniteState = null; }
function startInfinite(containerId, fetchPage, buildItem) { /* moved */ }

// PAGE_SIZES moved to state.js

function pageSizeSelect(current, view) {
  const opts = [...PAGE_SIZES];
  if (!opts.some(n => String(n) === String(current))) opts.push(parseInt(current, 10));
  return `<select class="page-size" data-action="page-size" data-view="${view}" aria-label="page size">
    ${opts.map(n => `<option value="${n}"${String(n) === String(current) ? " selected" : ""}>${n}</option>`).join("")}
  </select>`;
}

function jumpPage(input, last) {
  const p = Math.max(1, Math.min(parseInt(input.value, 10) || 1, last));
  input.value = p;
  if (app.view === "favmanage" || app.view === "favignored") {
    dupPage = p;
    renderDupGroupsFromCache();
    return;
  }
  location.hash = navHash(app.view, app.params, { ...app.query, page: String(p) });
}

function pagerJump(page, last) {
  return `<span class="page-jump-wrap">
    <input class="page-jump" type="number" min="1" max="${last}" value="${page}" aria-label="page">
    <span class="muted">/ ${last}</span></span>`;
}

function gridPager(elId, data, buildQuery) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const last = Math.max(1, Math.ceil(data.total / data.page_size));
  const link = (p, label) =>
    `<a class="page-link" href="${navHash(app.view, {}, buildQuery(p))}">${label}</a>`;
  const parts = [];
  if (data.page > 1) parts.push(link(data.page - 1, "‹"));
  for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
    parts.push(p === data.page ? `<strong class="cur">${p}</strong>` : link(p, String(p)));
  }
  if (data.page < last) parts.push(link(data.page + 1, "›"));
  el.innerHTML =
    parts.join(" ") +
    ` ${pagerJump(data.page, last)}` +
    ` · ${pageSizeSelect(data.page_size, app.view)}`;
}

function parseTags(s) {
  return (s || "").split(",").map(t => t.trim()).filter(Boolean);
}

function prefPageSize(fallback = 24) {
  const fromUrl = parseInt(app.query.page_size, 10);
  if (fromUrl > 0) return fromUrl;
  const saved = parseInt(localStorage.getItem("gv_page_size") || "", 10);
  return saved > 0 ? saved : fallback;
}

function libraryContext() {
  const c = {};
  for (const k of ["q", "tags", "tag_mode", "category", "page_size"]) {
    if (app.query[k]) c[k] = app.query[k];
  }
  return c;
}

function tagFilterHash(tagsArr) {
  const query = { tag_mode: "and" };
  if (app.query.q) query.q = app.query.q;
  if (app.query.category) query.category = app.query.category;
  if (tagsArr && tagsArr.length) query.tags = tagsArr.join(",");
  return navHash("library", {}, query);
}

function addTagHash(ns, name) {
  const key = `${ns}:${name}`;
  const cur = parseTags(app.query.tags);
  if (!cur.includes(key)) cur.push(key);
  return tagFilterHash(cur);
}

function removeTagHash(tag) {
  const cur = parseTags(app.query.tags).filter(t => t !== tag);
  return tagFilterHash(cur);
}

function tagFilterPills(tags) {
  const arr = parseTags(tags);
  if (!arr.length) return "";
  const pills = arr.map(t => {
    return `<span class="tag" title="${esc(t)}">${esc(t)} <a class="tag-x" data-action="remove-tag" data-tag="${esc(t)}" href="#">×</a></span>`;
  }).join("");
  return `<span class="mode">AND</span>${pills} <a class="clear-all" data-action="clear-tag" href="#">${esc(t("clearAll"))}</a>`;
}

async function renderBrowse() {
  $view().innerHTML = `
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
    </section>`;
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

async function renderGallery() {
  const id = app.params.id;
  $view().innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    const g = await api("GET", `/api/galleries/${id}`);
    const qualityBadge = g.image_quality === "original"
      ? `<span class="badge quality-badge">${esc(t("origBadge"))}</span>`
      : g.image_quality === "resample"
        ? `<span class="badge quality-badge">${esc(t("resampleBadge"))}</span>`
        : "";
    const showOrigBtns = !!(g.gid && g.image_quality !== "original");
    let progress = { current_page: 0, total_pages: g.page_count };
    try { progress = await api("GET", `/api/galleries/${id}/progress`); } catch (_) {}
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
        ? `<strong class="cur">${p}</strong>`
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
        <a class="primary" href="${navHash("reader", { id, page: progress.current_page }, libraryContext())}" style="padding:8px 14px;border-radius:4px">${esc(t("readNow"))}</a>
        ${g.eh_url ? `<a class="secondary" href="${esc(g.eh_url)}" target="_blank" rel="noopener" title="${esc(t("ehLoginNote"))}">${esc(t("openEh"))}</a>` : ""}
        <button class="secondary" data-action="sync-tags" data-id="${id}" type="button">${esc(t("syncTags"))}</button>
        <button class="secondary" data-action="unfavorite-gallery" data-id="${id}" type="button" hidden>${esc(t("unfavorite"))}</button>
        ${showOrigBtns ? `<button class="secondary" data-action="download-original" data-id="${g.id}" data-gid="${g.gid}" type="button">${esc(t("dlOrig"))}</button>
        <button class="secondary" data-action="download-original-archive" data-id="${g.id}" data-gid="${g.gid}" type="button">${esc(t("dlOrigArchive"))}</button>` : ""}
        <button class="secondary danger" data-action="delete-gallery" data-id="${g.id}" type="button">${esc(t("deleteGallery"))}</button>
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
        if (fav.favorite) {
          const btn = document.querySelector('[data-action="unfavorite-gallery"]');
          if (btn) { btn.hidden = false; btn.dataset.gid = fav.gid; }
          if (favcatEl) {
            favcatEl.innerHTML = (fav.favcat_names || []).map(n =>
              `<a class="badge" href="#/favorites/${n.favcat}?from=${id}" style="color:var(--accent)">${esc(n.name || ("#" + n.favcat))}</a>`
            ).join(" ");
          }
        }
      } catch (_) {}
    }
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function renderReader() {
  const id = app.params.id;
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  try {
    const g = await api("GET", `/api/galleries/${id}`);
    const total = g.page_count;
    app.readerTotal = total;
    let preload = "";
    for (let i = 1; i <= 3 && page + i < total; i++) {
      preload += `<link rel="preload" as="image" href="/api/galleries/${id}/pages/${page + i}">`;
    }
    $view().innerHTML = `
      <div class="reader">
        <div class="reader-bar toolbar">
          <a class="link-button" href="${navHash("gallery", { id }, libraryContext())}">← ${esc(t("details"))}</a>
          <span>${page + 1} / ${total} · ${fmtSize(g.file_size || 0)}</span>
          <span class="reader-actions">
            <button class="secondary" data-action="reader-fit" type="button">${esc(t("readerFit"))}</button>
            <button class="secondary" data-action="reader-fullscreen" type="button">${esc(t("readerFullscreen"))}</button>
          </span>
        </div>
        ${preload}
        <img id="reader-img" src="/api/galleries/${id}/pages/${page}" alt="Page ${page + 1}" data-next="${page + 1 < total ? page + 1 : ""}">
        <div class="nav">
          ${page > 0 ? `<a class="secondary" href="${navHash("reader", { id, page: page - 1 }, libraryContext())}">${esc(t("prev"))}</a>` : `<span>${esc(t("prev"))}</span>`}
          <a class="secondary" href="${navHash("gallery", { id }, libraryContext())}">${esc(t("allPages"))}</a>
          ${page + 1 < total ? `<a class="secondary" href="${navHash("reader", { id, page: page + 1 }, libraryContext())}">${esc(t("next"))}</a>` : `<span>${esc(t("next"))}</span>`}
        </div>
      </div>`;
    try { await api("PUT", `/api/galleries/${id}/progress`, { current_page: page, total_pages: total }); } catch (_) {}
  } catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

// readerKeyHandler moved to state.js

function bindReaderKeys() {
  if (readerKeyHandler) {
    document.removeEventListener("keydown", readerKeyHandler);
    document.removeEventListener("click", readerKeyHandler);
    readerKeyHandler = null;
  }
  if (app.view !== "reader") return;
  const id = app.params.id;
  const current = () => Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const advance = () => {
    const n = current() + 1;
    if (app.readerTotal && n >= app.readerTotal) { goReaderNext(id); return; }
    if (readerFsActive) { readerSwapPage(id, n); return; }
    location.hash = navHash("reader", { id, page: n }, libraryContext());
  };
  readerKeyHandler = (e) => {
    if (e.type === "click") {
      const img = e.target.closest && e.target.closest("#reader-img");
      if (!img) return;
      const next = parseInt(img.dataset.next, 10);
      if (readerFsActive) {
        if (!isNaN(next)) { readerSwapPage(id, next); }
        else { exitReaderFullscreen(); goReaderNext(id); }
        return;
      }
      if (img.dataset.next) {
        location.hash = navHash("reader", { id, page: next }, libraryContext());
      } else {
        goReaderNext(id);
      }
      return;
    }
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
    if (e.key === "ArrowRight" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      advance();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (readerFsActive) { readerSwapPage(id, current() - 1); }
      else { location.hash = navHash("reader", { id, page: Math.max(0, current() - 1) }, libraryContext()); }
    } else if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      toggleReaderFullscreen();
    }
  };
  document.addEventListener("keydown", readerKeyHandler);
  document.addEventListener("click", readerKeyHandler);
}

// readerFs* moved to state.js

function toggleReaderFullscreen() {
  if (document.fullscreenElement) { exitReaderFullscreen(); }
  else { enterReaderFullscreen(); }
}

function enterReaderFullscreen() {
  const img = document.getElementById("reader-img");
  if (!img || !img.requestFullscreen) return;
  readerFitBeforeFs = img.getAttribute("style") || "";
  img.removeAttribute("style");
  readerFsActive = true;
  const p = img.requestFullscreen();
  if (p && p.catch) p.catch(() => { clearReaderFsState(); });
}

function exitReaderFullscreen() {
  clearReaderFsState();
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  syncReaderUrl();
}

function clearReaderFsState() {
  readerFsActive = false;
  const img = document.getElementById("reader-img");
  if (img && readerFitBeforeFs) img.setAttribute("style", readerFitBeforeFs);
  readerFitBeforeFs = "";
}

function onFullscreenChange() {
  if (!document.fullscreenElement && readerFsActive) {
    clearReaderFsState();
    syncReaderUrl();
  }
}

function syncReaderUrl() {
  if (app.view !== "reader" || !app.params.id) return;
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const target = navHash("reader", { id: app.params.id, page }, libraryContext());
  if (location.hash !== target) location.hash = target;
}

function readerSwapPage(id, target) {
  const total = app.readerTotal || 0;
  if (target >= total) { exitReaderFullscreen(); goReaderNext(id); return; }
  if (target < 0) { exitReaderFullscreen(); return; }
  app.params.page = String(target);
  const img = document.getElementById("reader-img");
  if (!img) return;
  img.src = `/api/galleries/${id}/pages/${target}`;
  img.dataset.next = target + 1 < total ? String(target + 1) : "";
  const bar = document.querySelector(".reader-bar span");
  if (bar) bar.textContent = `${target + 1} / ${total}`;
  api("PUT", `/api/galleries/${id}/progress`, { current_page: target, total_pages: total }).catch(() => {});
  if (target + 1 < total) { const pre = new Image(); pre.src = `/api/galleries/${id}/pages/${target + 1}`; }
}

function toggleReaderFit() {
  const img = document.getElementById("reader-img");
  if (!img) return;
  const fitted = img.classList.toggle("reader-fit");
  if (fitted) {
    // Refit the current page once to the new mode.
    img.style.maxWidth = "none";
    img.style.width = "100%";
    img.style.height = "auto";
  } else {
    img.style.width = "";
    img.style.maxWidth = "";
    img.style.height = "";
  }
}

async function goReaderNext(id) {
  try {
    const r = await api("GET", `/api/galleries/${id}/next`);
    location.hash = navHash("reader", { id: r.id, page: 0 }, libraryContext());
  } catch (_) { /* no next gallery */ }
}

// TAG_NAMESPACES moved to state.js

function tagNsPillsHtml(activeNs, counts) {
  return TAG_NAMESPACES.map(g => {
    const active = (g.ns || "") === activeNs;
    const count = g.ns ? (counts[g.ns] || 0) : Object.values(counts).reduce((a, b) => a + b, 0);
    return `<a class="pill${active ? " active" : ""}${count ? "" : " empty"}"
      data-action="tag-ns" data-ns="${esc(g.ns || "")}"
      href="${navHash("tags", {}, g.ns ? { ns: g.ns } : {})}">
      ${esc(groupLabel(g.key))} <b>${count || 0}</b></a>`;
  }).join("");
}

function selectTagNamespace(ns) {
  // Update only the namespace pills + tag cloud (no full page re-render).
  app.query.ns = ns || "";
  delete app.query.page;
  const h1 = document.querySelector("main h1");
  if (h1) h1.textContent = app.query.ns ? nsLabel(app.query.ns) : t("tags");
  const pills = document.getElementById("tag-pills");
  if (pills) {
    pills.querySelectorAll(".pill").forEach(p => {
      p.classList.toggle("active", p.getAttribute("data-ns") === (app.query.ns || ""));
    });
  }
  const q = app.query.q || "";
  loadTags(q, app.query.ns, "1");
  history.replaceState(null, "", navHash("tags", {}, Object.assign({}, q ? { q } : {}, app.query.ns ? { ns: app.query.ns } : {})));
}

// cloudSizeClass moved to utils.js

async function renderTags() {
  const ns = app.query.ns || "";
  const q = app.query.q || "";
  const page = app.query.page || "1";
  const title = ns ? nsLabel(ns) : t("tags");
  $view().innerHTML = `
    <header><p class="eyebrow">LOCAL TAXONOMY</p><h1>${esc(title)}</h1></header>
    <div class="pills" id="tag-pills"></div>
    <form class="toolbar" data-action="tags-search">
      <input name="q" value="${esc(q)}" placeholder="${esc(t("searchPlaceholder"))}">
      <button class="primary" type="submit">${esc(t("tags"))}</button>
    </form>
    <div id="tag-cloud" class="cloud"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="tag-pages"></div>`;
  // Fill the namespace pills independently of the (namespace-filtered) tag
  // query below, so paging does not wipe the 全部/标签/作者 strip: the server
  // only returns facets when no namespace filter is given, but the strip must
  // persist on every page.
  if (tagFacetCounts) {
    const pills = document.getElementById("tag-pills");
    if (pills) pills.innerHTML = tagNsPillsHtml(ns, tagFacetCounts);
  }
  loadTagPills(ns);
  await loadTags(q, ns, page);
}

// tagFacetCounts moved to state.js

async function loadTagPills(activeNs) {
  if (!tagFacetCounts) {
    try {
      const data = await api("GET", "/api/tags/search?page=1&page_size=1");
      tagFacetCounts = {};
      for (const f of data.facets || []) tagFacetCounts[f.namespace] = f.total;
    } catch (_) { return; }
  }
  const pills = document.getElementById("tag-pills");
  if (pills) pills.innerHTML = tagNsPillsHtml(activeNs, tagFacetCounts);
}

async function loadTags(q, ns, page) {
  try {
    const url = `/api/tags/search?page=${encodeURIComponent(page)}&page_size=100`
      + `${ns ? `&namespace=${encodeURIComponent(ns)}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
    const data = await api("GET", url);
    const cloud = document.getElementById("tag-cloud");
    if (!cloud) return;
    const items = data.items;
    if (!items.length) { cloud.innerHTML = `<p>${esc(t("noTags"))}</p>`; }
    else {
      const max = items.reduce((m, it) => Math.max(m, it.usage_count), 0);
      cloud.innerHTML = items
        .map(it => `<a class="cloud-tag ${nsClass(it.namespace)} ${cloudSizeClass(it.usage_count, max)}" href="${addTagHash(it.namespace, it.name)}">${esc(tagText(it))}<small>${it.usage_count}</small></a>`)
        .join("");
    }
    const pagerEl = document.getElementById("tag-pages");
    if (pagerEl) {
      const last = Math.max(1, Math.ceil(data.total / data.page_size));
      const qp = p => navHash("tags", {}, { ...(ns ? { ns } : {}), ...(q ? { q } : {}), ...(p > 1 ? { page: p } : {}) });
      const pages = [];
      for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
        pages.push(p === data.page ? `<strong class="cur">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
      }
      pagerEl.innerHTML =
        `${data.page > 1 ? `<a class="page-link" href="${qp(data.page - 1)}">&lt;</a>` : ""} ` +
        pages.join(" ") +
        ` ${pagerJump(data.page, last)}` +
        `${data.page < last ? ` <a class="page-link" href="${qp(data.page + 1)}">&gt;</a>` : ""}`;
    }
  } catch (e) {
    const cloud = document.getElementById("tag-cloud");
    if (cloud) cloud.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

async function renderHistory() {
  const page = app.query.page || "1";
  $view().innerHTML = `
    <header><p class="eyebrow">READING LOG</p><h1>${esc(t("history"))}</h1>
    <button class="secondary" data-action="clear-history" type="button">${esc(t("clearHistory"))}</button></header>
    <div id="hist-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages" id="hist-pages"></div>`;
  try {
    const pageSize = prefPageSize();
    const data = await api("GET", `/api/history?page=${encodeURIComponent(page)}&page_size=${pageSize}`);
    const el = document.getElementById("hist-list");
    const items = (data && data.items) || [];
    if (!items.length) { el.innerHTML = `<p>${esc(t("noHistory"))}</p>`; return; }
    el.innerHTML = `<div class="rows">` + items.map(h => `
      <a class="row" href="${navHash("gallery", { id: h.gallery_id })}">
        <span class="row-title">${esc(h.title || ("#" + h.gallery_id))}</span>
        <span class="row-meta">${esc(t("progress"))} ${h.current_page}/${h.total_pages} · ${h.last_read_at ? esc(String(h.last_read_at).slice(0, 10)) : ""}</span>
      </a>`).join("") + `</div>`;
    const last = Math.max(1, Math.ceil(data.total / data.page_size));
    const qp = p => navHash("history", {}, { page: p, page_size: prefPageSize() });
    const pages = [];
    for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
      pages.push(p === data.page ? `<strong class="cur">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
    }
    document.getElementById("hist-pages").innerHTML =
      `${data.page > 1 ? `<a class="page-link" href="${qp(data.page - 1)}">&lt;</a>` : ""} ` +
      pages.join(" ") +
      ` ${pagerJump(data.page, last)} · ${esc(t("perPage"))} ${pageSizeSelect(data.page_size, "history")}`;
  } catch (e) { document.getElementById("hist-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

// DL_STATUSES + dlTimer moved to state.js

async function renderDownloads() {
  const filter = app.query.filter || "all";
  $view().innerHTML = `
    <header><p class="eyebrow">DOWNLOADS</p><h1>${esc(t("downloads"))}</h1>
    <p class="sub">${esc(t("downloadsSub"))}</p></header>
    <h2 style="margin-top:20px">${esc(t("dlTasks"))}</h2>
    <div class="toolbar">
      <div class="pills" style="margin:0">
        ${DL_STATUSES.map(s => `<a class="pill${s === filter ? " active" : ""}" href="${navHash("downloads", {}, s !== "all" ? { filter: s } : {})}">${esc(s === "all" ? t("filterAll") : s)}</a>`).join("")}
      </div>
      <button class="secondary" data-action="dl-select-all" type="button">${esc(t("selectAll"))}</button>
      <button class="primary" data-action="dl-retry-selected" type="button">${esc(t("retrySelected"))}</button>
      <button class="secondary danger" data-action="dl-delete-selected" type="button">${esc(t("deleteSel"))}</button>
    </div>
    <div id="dl-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages" id="dl-pages"></div>`;
  loadDownloads(filter, app.query.page || "1");
  if (dlTimer) clearInterval(dlTimer);
  dlTimer = setInterval(() => {
    if (location.hash.startsWith("#/downloads")) loadDownloads(filter, app.query.page || "1");
  }, 2000);
}

// fmtDur moved to utils.js

function dlProgressHtml(x) {
  const cur = x.current_page || 0;
  const total = x.total_pages;
  if (x.status === "downloading") {
    let speed = "";
    if (x.speed != null && x.speed > 0) {
      speed = ` · ${fmtSize(Math.round(x.speed))}/s`;
      if (x.eta_seconds != null && x.eta_seconds > 0) speed += ` · ETA ${fmtDur(x.eta_seconds)}`;
    }
    if (total) {
      const pct = Math.min(100, Math.round((cur / total) * 100));
      return `<div class="dl-progress"><div class="dl-progress-bar" style="width:${pct}%"></div></div>
        <span class="row-meta">${cur}/${total} · ${pct}%${speed}</span>`;
    }
    // Still enumerating the gallery / waiting to start: indeterminate bar.
    return `<div class="dl-progress dl-progress-indet"></div>
      <span class="row-meta">${esc(t("downloading"))}…</span>`;
  }
  return `<span class="row-meta">${esc(x.status)}${total ? ` · ${cur}/${total}` : ""}${x.retry_count ? ` · retry ${x.retry_count}` : ""}${x.error_message ? ` · ${esc(t("error"))}: ${esc(x.error_message)}` : ""}</span>`;
}

async function loadDownloads(filter, page) {
  try {
    const status = filter !== "all" ? `&status=${encodeURIComponent(filter)}` : "";
    const pageSize = prefPageSize();
    const data = await api("GET", `/api/downloads?page=${encodeURIComponent(page)}&page_size=${pageSize}${status}`);
    const items = (data && data.items) || [];
    const el = document.getElementById("dl-list");
    if (!el) return;
    // Preserve the user's selection across the auto-refresh re-render.
    const checked = new Set(
      [...document.querySelectorAll(".dl-check:checked")].map(b => b.getAttribute("data-id"))
    );
    if (!items.length) { el.innerHTML = `<p>${esc(t("noTasks"))}</p>`; }
    else {
      el.innerHTML = `<div class="rows">` + items.map(x => {
        const title = x.title || ("gid " + (x.gid != null ? x.gid : x.id));
        const isArchive = !!(x.mode && String(x.mode).includes("archive"));
        const badge = isArchive
          ? `<span class="badge dl-badge">${esc(t("dlBadgeArchive"))} · ${esc(x.quality === "original" ? t("archiveTierOriginal") : t("archiveTierResample"))}</span>`
          : `<span class="badge dl-badge">${esc(t("dlBadgePages"))}</span>`;
        const actions = [];
        if (x.status === "pending" || x.status === "downloading") {
          actions.push(`<button class="secondary" data-action="cancel-download" data-id="${x.id}" type="button">${esc(t("cancelDl"))}</button>`);
        }
        if (x.status === "failed" || x.status === "cancelled" || x.status === "success") {
          actions.push(`<button class="secondary" data-action="retry-download" data-id="${x.id}" type="button">${esc(t("retry"))}</button>`);
        }
        actions.push(`<button class="secondary danger" data-action="delete-download" data-id="${x.id}" type="button">${esc(t("deleteDl"))}</button>`);
        return `<div class="row" data-task-id="${x.id}">
          <input type="checkbox" class="dl-check" data-id="${x.id}"${checked.has(String(x.id)) ? " checked" : ""} aria-label="${esc(t("selectAll"))}">
          <span class="row-title dl-title" title="${esc(title)}">${esc(title)}</span>${badge}
          ${dlProgressHtml(x)}
          ${actions.join("")}
        </div>`;
      }).join("") + `</div>`;
    }
    const last = Math.max(1, Math.ceil(data.total / data.page_size));
    const qp = p => navHash("downloads", {}, { ...(filter !== "all" ? { filter } : {}), page: p, page_size: pageSize });
    const pages = [];
    for (let p = Math.max(1, data.page - 2); p <= Math.min(last, data.page + 2); p++) {
      pages.push(p === data.page ? `<strong class="cur">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
    }
    document.getElementById("dl-pages").innerHTML =
      `${data.page > 1 ? `<a class="page-link" href="${qp(data.page - 1)}">&lt;</a>` : ""} ` +
      pages.join(" ") +
      ` ${pagerJump(data.page, last)} · ${esc(t("perPage"))} ${pageSizeSelect(data.page_size, "downloads")}`;
  } catch (e) {
    const el = document.getElementById("dl-list");
    if (el) el.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function field(label, inputHtml) {
  return `<label class="field"><span>${esc(label)}</span>${inputHtml}</label>`;
}

// EH_* moved to state.js

function ehBaseUrlControl(value, prefix) {
  const fixed = EH_BASE_URLS.some(o => o.v === value);
  const options = EH_BASE_URLS.map(o =>
    `<option value="${o.v}"${value === o.v ? " selected" : ""}>${o.label}</option>`
  ).join("") + `<option value="${EH_CUSTOM}"${fixed ? "" : " selected"}>${esc(t("custom"))}</option>`;
  return `<select name="${prefix}exhentai_base_url" data-eh-select>${options}</select>
  <input name="${prefix}exhentai_base_url_custom" data-eh-custom value="${fixed ? "" : esc(value || "")}" placeholder="https://proxy.exhentai.org"${fixed ? " hidden" : ""}>`;
}

function toggleEhCustom(select) {
  const input = select.parentElement.querySelector("[data-eh-custom]");
  if (input) input.hidden = select.value !== EH_CUSTOM;
}

async function renderSettings() {
  if (!app.settings) {
    try { app.settings = await api("GET", "/api/settings"); } catch (_) { app.settings = {}; }
  }
  const s = app.settings;
  const warnings = (s.library_root_warnings || [])
    .map(w => `<p class="notice">${esc(w)}</p>`).join("");
  $view().innerHTML = `
    <header><p class="eyebrow">CONFIGURATION</p><h1>${esc(t("settings"))}</h1>
    <p class="sub">${esc(t("settingsSub"))}</p></header>
    <form data-action="settings-save">
      <fieldset><legend>${esc(t("authLogin"))}</legend>
        <label class="checkbox"><input type="checkbox" name="auth_required"${s.auth_required == null ? " checked" : (s.auth_required ? " checked" : "")}> ${esc(t("authRequired"))}</label>
        <p class="notice">${s.auth_hash_configured ? esc(t("pwConfigured")) : esc(t("pwDefault"))}</p>
      </fieldset>
      <fieldset><legend>${esc(t("changePassword"))}</legend>
        ${field(t("currentPassword"), `<input name="current_password" type="password" autocomplete="current-password">`)}
        ${field(t("newPassword"), `<input name="new_password" type="password" autocomplete="new-password">`)}
        <button class="secondary" data-action="change-password" type="button">${esc(t("changePassword"))}</button>
      </fieldset>
      <fieldset><legend>ExHentai</legend>
        ${field(t("baseUrl"), ehBaseUrlControl(s.exhentai_base_url || "", ""))}
        ${/e-hentai\.org/i.test(s.exhentai_base_url || "") ? `<p class="notice">${esc(t("ehPublicNotice"))}</p>` : ""}
        <p class="notice">Cookie: <strong>${s.exhentai_cookie_configured ? esc(t("cookieSet")) : esc(t("cookieUnset"))}</strong> · ${esc(t("cookiesNote"))}</p>
        <div class="form-grid">
          <input name="ipb_member_id" placeholder="${esc(t("cookieId"))}" autocomplete="off">
          <input name="ipb_pass_hash" placeholder="${esc(t("cookieHash"))}" autocomplete="off">
          <input name="igneous" placeholder="${esc(t("cookieIgneous"))}" autocomplete="off">
        </div>
        <button class="secondary" data-action="test-exhentai" type="button">${esc(t("testExhentai"))}</button>
      </fieldset>
      <fieldset><legend>Proxy</legend>
        <div class="form-grid">
          ${field(t("proxyHttp"), `<input name="http_proxy" value="${esc(s.http_proxy || "")}">`)}
          ${field(t("proxySocks5"), `<input name="socks5_proxy" value="${esc(s.socks5_proxy || "")}">`)}
        </div>
      </fieldset>
      <fieldset><legend>${esc(t("libraryRoots"))}</legend>
        <p class="notice">${esc(t("libraryRootsHint"))}</p>
        <textarea name="library_roots" rows="4">${esc((s.library_roots || []).join("\n"))}</textarea>
        ${warnings}
      </fieldset>
      <fieldset><legend>Downloads</legend>
        <div class="form-grid">
          ${field(t("downloadRoot"), `<input name="download_root" value="${esc(s.download_root || "")}">`)}
          <p class="notice">${esc(t("downloadRootHint"))}</p>
          ${field(t("concurrency"), `<input name="download_concurrency" type="number" min="1" max="32" value="${s.download_concurrency != null ? s.download_concurrency : 2}">`)}
          ${field(t("pageConcurrency"), `<input name="page_concurrency" type="number" min="1" max="16" value="${s.page_concurrency != null ? s.page_concurrency : 4}">`)}
          ${field(t("quality"), `<select name="download_quality">
            <option value="original"${(s.download_quality || "resample") === "original" ? " selected" : ""}>${esc(t("qualityOriginal"))}</option>
            <option value="resample"${(s.download_quality || "resample") === "resample" ? " selected" : ""}>${esc(t("qualityResample"))}</option>
          </select>`)}
          ${field(t("downloadTitle"), `<select name="download_title">
            <option value="japanese"${(s.download_title || "japanese") === "japanese" ? " selected" : ""}>Japanese (日文)</option>
            <option value="english"${(s.download_title || "japanese") === "english" ? " selected" : ""}>English (英文)</option>
          </select>`)}
          ${field(t("titleDisplay"), `<select name="title_display">${["japanese", "english", "directory"].map(o => `<option value="${o}"${o === (s.title_display || "japanese") ? " selected" : ""}>${o}</option>`).join("")}</select>`)}
        </div>
        <p class="notice">${esc(t("imageTimeoutHint"))}</p>
        <div class="form-grid">
          ${field(t("imageTimeout"), `<input name="image_download_timeout_seconds" type="number" min="1" value="${s.image_download_timeout_seconds != null ? s.image_download_timeout_seconds : 120}">`)}
          ${field(t("imageWarmup"), `<input name="image_slow_warmup_seconds" type="number" min="1" value="${s.image_slow_warmup_seconds != null ? s.image_slow_warmup_seconds : 30}">`)}
          ${field(t("imageMinSpeed"), `<input name="image_min_speed_kb_s" type="number" min="1" value="${s.image_min_speed_kb_s != null ? s.image_min_speed_kb_s : 20}">`)}
        </div>
        <p class="notice">${esc(t("imageSlowHint"))}</p>
        <label class="checkbox"><input type="checkbox" name="use_hah"${s.use_hah ? " checked" : ""}> ${esc(t("useHah"))}</label>
        <label class="checkbox"><input type="checkbox" name="download_favorites_enabled"${s.download_favorites_enabled ? " checked" : ""}> download favorites</label>
        <div class="form-grid">
          ${field(t("archiveQuality"), `<select name="archive_quality">
            <option value="original"${(s.archive_quality || "resample") === "original" ? " selected" : ""}>${esc(t("archiveTierOriginal"))}</option>
            <option value="resample"${(s.archive_quality || "resample") === "resample" ? " selected" : ""}>${esc(t("archiveTierResample"))}</option>
          </select>`)}
        </div>
        <p class="notice">${esc(t("archiveMaxPagesHint"))}</p>
        <div class="form-grid">
          ${field(t("archiveMaxPages"), `<input name="favorites_archive_max_pages" type="number" min="0" value="${s.favorites_archive_max_pages != null ? s.favorites_archive_max_pages : 0}">`)}
        </div>
        <label class="checkbox"><input type="checkbox" name="favorites_archive_enabled"${s.favorites_archive_enabled ? " checked" : ""}> ${esc(t("archiveScanEnabled"))}</label>
        <label class="checkbox"><input type="checkbox" name="archive_fallback_pages"${s.archive_fallback_pages === false ? "" : " checked"}> ${esc(t("archiveFallbackPages"))}</label>
        <p class="notice">${esc(t("archiveFallbackPagesHint"))}</p>
      </fieldset>
      <fieldset><legend>Tags</legend>
        <label class="checkbox"><input type="checkbox" name="auto_sync_tags"${s.auto_sync_tags ? " checked" : ""}> ${esc(t("autoSyncTags"))}</label>
        <div class="form-grid">
          ${field(t("tagSyncInterval"), `<input name="tag_sync_interval_seconds" type="number" step="0.1" min="0.1" value="${s.tag_sync_interval_seconds != null ? s.tag_sync_interval_seconds : 1}">`)}
          ${field(t("tagSyncConcurrency"), `<input name="tag_sync_concurrency" type="number" min="1" max="32" value="${s.tag_sync_concurrency != null ? s.tag_sync_concurrency : 2}">`)}
        </div>
        <div class="toolbar"><button class="secondary" data-action="sync-all-tags" type="button">${esc(t("syncAllTags"))}</button>
          <a class="secondary" href="#/logs" style="padding:8px 14px;border-radius:4px">${esc(t("logs"))}</a></div>
      </fieldset>
      <fieldset><legend>Thumbnails</legend>
        <label class="checkbox"><input type="checkbox" name="generate_thumbnails"${s.generate_thumbnails ? " checked" : ""}> ${esc(t("generateThumbnails"))}</label>
        <div class="toolbar">
          <button class="secondary" data-action="gen-thumbs" type="button">${esc(t("genThumbs"))}</button>
          <a class="secondary" href="#/logs" style="padding:8px 14px;border-radius:4px">${esc(t("logs"))}</a>
        </div>
        <p class="notice" id="thumbs-status">${esc(t("thumbsHint"))}</p>
      </fieldset>
      <fieldset><legend>${esc(t("dupPolicy"))}</legend>
        <p class="notice">${esc(t("dupPolicyHint"))}</p>
        ${field(t("dupPolicy"), `<select name="duplicate_policy">
          ${[["keep_first", t("dupPolicyKeepFirst")], ["prefer_more_pages", t("dupPolicyMorePages")], ["prefer_newer", t("dupPolicyNewer")], ["prefer_larger", t("dupPolicyLarger")], ["prefer_smaller", t("dupPolicySmaller")], ["manual", t("dupPolicyManual")]].map(([o, label]) => `<option value="${o}"${o === (s.duplicate_policy || "keep_first") ? " selected" : ""}>${esc(label)}</option>`).join("")}
        </select>`)}
        <div class="toolbar"><a class="secondary" href="#/duplicates" style="padding:8px 14px;border-radius:4px">${esc(t("dupGalTitle"))}</a></div>
      </fieldset>
      <fieldset><legend>${esc(t("translationUpdate"))}</legend>
        ${field(t("translationInterval"), `<input name="tag_translation_update_interval_minutes" type="number" min="0" value="${s.tag_translation_update_interval_minutes != null ? s.tag_translation_update_interval_minutes : 720}">`)}
        <div class="toolbar"><button class="secondary" data-action="force-update" type="button">${esc(t("forceUpdate"))}</button></div>
        <p class="notice">${esc(t("translationStatus"))}: <span id="trans-status">${esc(s.translation ? s.translation : "")}</span></p>
      </fieldset>
      <fieldset><legend>Telegram</legend>
        ${field(t("botToken"), `<input name="telegram_bot_token" type="password" autocomplete="new-password" placeholder="${s.telegram_bot_configured ? t("cookieSet") : t("cookieUnset")}">`)}
        <div class="form-grid">
          ${field(t("chatIds"), `<input name="telegram_chat_ids" value="${esc((s.telegram_chat_ids || []).join(","))}">`)}
          ${field(t("allowedIds"), `<input name="telegram_allowed_user_ids" value="${esc((s.telegram_allowed_user_ids || []).join(","))}">`)}
          ${field(t("notifyLevel"), `<select name="telegram_notify_level">
            ${[["summary", t("notifyLevelSummary")], ["immediate", t("notifyLevelImmediate")], ["failures_only", t("notifyLevelFailuresOnly")], ["off", t("notifyLevelOff")]].map(([o, label]) => `<option value="${o}"${o === (s.telegram_notify_level || "summary") ? " selected" : ""}>${esc(label)}</option>`).join("")}
          </select>`)}
          ${field(t("notifyLang"), `<select name="telegram_notify_lang">
            ${[["zh", t("langZh")], ["en", t("langEn")]].map(([o, label]) => `<option value="${o}"${o === (s.telegram_notify_lang || app.lang) ? " selected" : ""}>${esc(label)}</option>`).join("")}
          </select>`)}
        </div>
        <button class="secondary" data-action="test-telegram" type="button">${esc(t("testTelegram"))}</button>
      </fieldset>
      <div class="toolbar"><button class="primary" type="submit">${esc(t("save"))}</button></div>
    </form>`;
  api("GET", "/api/tags/search/status").then(status => {
    const el = document.getElementById("trans-status");
    if (el && status) {
      const n = status.entries ? parseInt(status.entries, 10) : 0;
      const last = status.last ? new Date(status.last) : null;
      const when = last && !isNaN(last) ? last.toLocaleString() : (status.last || "");
      const err = status.last_error ? ` — ${esc(status.last_error)}` : "";
      el.textContent = (n > 0 ? `${n} entries, updated ${when}` : when) + err;
    }
  }).catch(() => {});
  refreshThumbsStatus();
}

async function refreshThumbsStatus() {
  const el = document.getElementById("thumbs-status");
  if (!el) return;
  try {
    const st = await api("GET", "/api/thumbs/status");
    if (st && st.running) el.textContent = t("thumbs");
    else if (st && (st.completed_at || st.succeeded)) {
      el.textContent = t("thumbsDone") + (st.succeeded ? ` (${st.succeeded})` : "");
    } else {
      el.textContent = t("thumbsHint");
    }
  } catch (_) { /* transient */ }
}

function collectSettings(form) {
  const val = n => form[n] ? form[n].value.trim() : "";
  const num = (n, d) => { const v = parseFloat(val(n)); return Number.isFinite(v) ? v : d; };
  const lines = a => a.split(/[\n,]/).map(x => x.trim()).filter(Boolean);
  const body = {
    library_roots: val("library_roots"),
    exhentai_base_url: val("exhentai_base_url") === EH_CUSTOM
      ? (val("exhentai_base_url_custom") || "https://exhentai.org")
      : val("exhentai_base_url"),
    http_proxy: val("http_proxy"),
    socks5_proxy: val("socks5_proxy"),
    download_root: val("download_root"),
    download_concurrency: Math.min(32, Math.max(1, num("download_concurrency", 2))),
    page_concurrency: Math.min(16, Math.max(1, num("page_concurrency", 4))),
    download_quality: val("download_quality") || "resample",
    archive_quality: val("archive_quality") || "resample",
    favorites_archive_max_pages: Math.max(0, Math.round(num("favorites_archive_max_pages", 0))),
    favorites_archive_enabled: form.favorites_archive_enabled.checked,
    archive_fallback_pages: form.archive_fallback_pages.checked,
    download_title: val("download_title") || "japanese",
    title_display: val("title_display") || "japanese",
    image_download_timeout_seconds: Math.max(1, Math.round(num("image_download_timeout_seconds", 120))),
    image_slow_warmup_seconds: Math.max(1, Math.round(num("image_slow_warmup_seconds", 30))),
    image_min_speed_kb_s: Math.max(1, Math.round(num("image_min_speed_kb_s", 20))),
    use_hah: form.use_hah.checked,
    download_favorites_enabled: form.download_favorites_enabled.checked,
    auto_sync_tags: form.auto_sync_tags.checked,
    generate_thumbnails: form.generate_thumbnails ? form.generate_thumbnails.checked : undefined,
    tag_sync_interval_seconds: Math.max(0.1, num("tag_sync_interval_seconds", 1)),
    tag_sync_concurrency: Math.min(32, Math.max(1, num("tag_sync_concurrency", 2))),
    telegram_chat_ids: lines(val("telegram_chat_ids")),
    telegram_allowed_user_ids: lines(val("telegram_allowed_user_ids")).map(Number).filter(Number.isFinite),
    telegram_notify_level: val("telegram_notify_level") || "summary",
    telegram_notify_lang: val("telegram_notify_lang") || app.lang,
    duplicate_policy: val("duplicate_policy") || "keep_first",
    auth_required: form.auth_required.checked,
    tag_translation_update_interval_minutes: Math.max(0, num("tag_translation_update_interval_minutes", 720)),
  };
  for (const k of ["ipb_member_id", "ipb_pass_hash", "igneous", "telegram_bot_token"]) {
    if (val(k)) body[k] = val(k);
  }
  return body;
}

// FAV_MODES moved to state.js

async function renderFavorites() {
  $view().innerHTML = `
    <header><p class="eyebrow">EXHENTAI FOLDERS</p><h1>${esc(t("favcatTitle"))}</h1>
    <p class="sub">${esc(t("favcatSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="favcats-save" type="button">${esc(t("save"))}</button>
      <button class="secondary" data-action="favcats-sync" type="button">${esc(t("syncFavcats"))}</button>
      <button class="secondary" data-action="favcats-check-all" type="button">${esc(t("checkAll"))}</button>
      <button class="secondary" data-action="favcats-download-missing" type="button">${esc(t("downloadMissing"))}</button>
      <a class="secondary" href="#/updates" style="padding:8px 14px;border-radius:4px">${esc(t("galleryUpdates"))}</a>
      <a class="secondary" href="#/favorites/manage" style="padding:8px 14px;border-radius:4px;margin-left:auto">${esc(t("favManage"))}</a>
    </div>
    <div id="fav-list"><p>${esc(t("loading"))}</p></div>`;
  try {
    const cats = await api("GET", "/api/favorites/categories");
    const rows = (Array.isArray(cats) ? cats : []).map(c => `
      <tr data-favcat="${c.favcat}">
        <td class="fav-name"><a href="#/favorites/${c.favcat}" class="fav-link">${esc(c.name || ("Folder " + c.favcat))}</a> <span class="badge">#${c.favcat}</span></td>
        <td class="muted">${c.cloud_count || 0} / ${c.local_count || 0}</td>
        <td class="muted">${(c.cloud_size ? "~" : "") + fmtSize(c.cloud_size || 0)} / ${fmtSize(c.local_size || 0)}</td>
        <td><input type="checkbox" class="fav-enabled"${c.enabled ? " checked" : ""}></td>
        <td><select class="fav-mode">${FAV_MODES.map(m => `<option value="${m}"${m === (c.mode || "incremental") ? " selected" : ""}>${esc(t("favMode" + m.split("_").map(s => s[0].toUpperCase() + s.slice(1)).join("")))}</option>`).join("")}</select></td>
        <td><input type="number" min="1" class="fav-interval" value="${c.poll_interval_minutes != null ? c.poll_interval_minutes : 720}"></td>
        <td><button class="secondary" data-action="favcat-check" data-favcat="${c.favcat}" type="button">${esc(t("checkNow"))}</button></td>
      </tr>`).join("");
    document.getElementById("fav-list").innerHTML = `
      <table class="table">
        <thead><tr><th>${esc(t("favorites"))}</th><th>${esc(t("favCount"))}</th><th>${esc(t("favSize"))}</th><th>${esc(t("enabled"))}</th><th>${esc(t("mode"))}</th><th>${esc(t("intervalMin"))}</th><th></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="7">—</td></tr>`}</tbody>
      </table>`;
    pollFavoriteRings();
  } catch (e) { document.getElementById("fav-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

// favTimer + selFav moved to state.js

async function renderFavList() {
  const favcat = parseInt(app.params.id, 10);
  if (isNaN(favcat)) { location.hash = "#/favorites"; return; }
  const page = app.query.page || "1";
  const state = app.query.state || "all";
  const selCount = selFav.size;
  const from = app.query.from;
  const backLinks = `<a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>`
    + (from ? ` <a class="link-button" href="#/gallery/${esc(from)}">← ${esc(t("backToGallery"))}</a>` : "");
  const stateBtn = (s, label) =>
    `<button class="secondary${state === s ? " active-pill" : ""}" data-action="favlist-state" data-state="${s}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <div class="toolbar" style="margin-bottom:0">
      ${backLinks}
    </div>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITE FOLDER</p><h1>#${favcat}</h1>
    <p class="sub">${esc(t("favListSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="favlist-download" data-favcat="${favcat}" type="button">${esc(t("favDl"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-download-orig" data-favcat="${favcat}" type="button">${esc(t("favDlOrig"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-archive" data-favcat="${favcat}" type="button">${esc(t("favDlArchive"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary danger" data-action="favlist-unfav" data-favcat="${favcat}" type="button">${esc(t("favRemove"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="favlist-clear" type="button">${esc(t("clearSel"))}</button>
      <span class="fav-state-filter">
        ${stateBtn("all", t("favStateAll"))}
        ${stateBtn("local", t("favStateLocal"))}
        ${stateBtn("cloud", t("favStateCloud"))}
      </span>
    </div>
    <div id="fav-items"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="favlist-pager"></div>`;
  try {
    const qs = `page=${encodeURIComponent(page)}&page_size=${prefPageSize()}&state=${encodeURIComponent(state)}`;
    const data = await api("GET", `/api/favorites/${favcat}/items?${qs}`);
    const el = document.getElementById("fav-items");
    if (!data.items.length) { el.innerHTML = `<p>${esc(t("noGalleries"))}</p>`; }
    else {
      el.innerHTML = `<div class="grid gc-grid">` + data.items.map(favCard).join("") + `</div>`;
      document.querySelectorAll('#fav-items input[data-fav-gid]').forEach(cb => {
        cb.checked = selFav.has(parseInt(cb.dataset.favGid, 10));
      });
      renderCardCheckboxes();
    }
    renderFavPager("favlist-pager", data, page);
  } catch (e) { document.getElementById("fav-items").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

function favCard(it) {
  const cat = it.category ? esc(catLabel(it.category)) : "";
  const cover = it.cover_url || it.cover_data || null;
  const inner = cover
    ? `<img loading="lazy" src="${cover}" alt="">`
    : `<span class="badge">no cover</span>`;
  const stateBadge = it.gallery_id != null
    ? `<span class="fav-state local">${esc(t("favLocal"))}</span>`
    : `<span class="fav-state cloud">${esc(t("favCloud"))}</span>`;
  const size = it.file_size ? `<span class="gc-size">${fmtSize(it.file_size)}</span>` : "";
  const link = it.gallery_id != null ? `href="${navHash("gallery", { id: it.gallery_id })}"` : `href="${esc(it.url || "#")}" target="_blank" rel="noopener"`;
  return `<div class="gc-wrap">
    <a class="gc" ${link}>
      <div class="gc-cover">${inner}${stateBadge}${cat ? `<span class="gc-cat">${cat}</span>` : ""}${it.page_count ? `<span class="gc-pages">${it.page_count} P</span>` : ""}</div>
      <div class="gc-title">${esc(it.title || ("gid " + it.gid))}${size}</div>
      <div class="gc-tags">${(it.tags || []).map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</div>
    </a>
    <label class="gc-check" title="${esc(t("select"))}"><input type="checkbox" data-fav-gid="${it.gid}"${selFav.has(it.gid) ? " checked" : ""}></label>
  </div>`;
}

function renderFavPager(elId, data, page) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const favcat = parseInt(app.params.id, 10);
  const state = app.query.state || "all";
  const total = data.total, pageSize = data.page_size || 24;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const cur = parseInt(page, 10) || 1;
  const qp = p => navHash("favlist", { id: favcat }, { page: p, page_size: pageSize, state });
  const parts = [];
  if (cur > 1) parts.push(`<a class="page-link" href="${qp(cur - 1)}">&lt;</a>`);
  for (let p = Math.max(1, cur - 2); p <= Math.min(pages, cur + 2); p++) {
    parts.push(p === cur
      ? `<strong class="cur">${p}</strong>`
      : `<a class="page-link" href="${qp(p)}">${p}</a>`);
  }
  if (cur < pages) parts.push(`<a class="page-link" href="${qp(cur + 1)}">&gt;</a>`);
  el.innerHTML = `${parts.join(" ")} ${pagerJump(cur, pages)} · ${esc(t("perPage"))} ${pageSizeSelect(pageSize, "favlist")}`;
}

// selDup/dup*/favCatNames moved to state.js

async function loadFavNames() {
  if (Object.keys(favCatNames).length) return;
  try {
    const c = await api("GET", "/api/favorites/categories");
    (Array.isArray(c) ? c : []).forEach(x => { favCatNames[x.favcat] = x.name || ""; });
  } catch (_) {}
}

async function renderFavManage() {
  await loadFavNames();
  const filterBtn = (val, label) =>
    `<button class="secondary${dupFilter === val ? " active-pill" : ""}" data-action="dup-filter" data-value="${val}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITES</p><h1>${esc(t("favManageTitle"))}</h1>
    <p class="sub">${esc(t("favManageSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="dup-scan" type="button">${esc(t("dupScan"))}</button>
      ${filterBtn("all", t("dupFilterAll"))}
      ${filterBtn("local", t("dupFilterLocal"))}
      ${filterBtn("cloud", t("dupFilterCloud"))}
      <button class="secondary danger" data-action="dup-unfav" type="button">${esc(t("dupUnfav"))}${selDup.size ? ` (${selDup.size})` : ""}</button>
      <button class="secondary danger" data-action="dup-unfav-delete" type="button">${esc(t("dupUnfavDelete"))}${selDup.size ? ` (${selDup.size})` : ""}</button>
      <button class="secondary" data-action="dup-ignore-selected" type="button">${esc(t("dupIgnoreSel"))}${selDup.size ? ` (${selDup.size})` : ""}</button>
      <button class="secondary" data-action="dup-clear" type="button">${esc(t("clearSel"))}</button>
      <a class="secondary" href="#/favorites/ignored" style="padding:8px 14px;border-radius:4px;margin-left:auto">${esc(t("dupIgnoredPage"))}</a>
    </div>
    <div id="dup-progress" hidden>
      <div class="progress-bar"><div class="progress-fill" id="dup-progress-fill"></div></div>
      <p class="muted" id="dup-progress-text"></p>
    </div>
    <div id="dup-groups"><p class="muted">${esc(t("dupHint"))}</p></div>`;
}

async function runDupScan() {
  const bar = document.getElementById("dup-progress");
  const fill = document.getElementById("dup-progress-fill");
  const text = document.getElementById("dup-progress-text");
  const groupsEl = document.getElementById("dup-groups");
  selDup.clear();
  dupPage = 1;
  dupLocallyIgnored.clear();
  bar.hidden = false;
  groupsEl.innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    await api("POST", "/api/favorites/duplicates/scan");
  } catch (e) { groupsEl.innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
  for (let i = 0; i < 120; i++) {
    let st;
    try { st = await api("GET", "/api/favorites/duplicates/status"); }
    catch (e) { groupsEl.innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
    if (st.total > 0) {
      const pct = Math.min(100, Math.round((st.done / st.total) * 100));
      fill.style.width = pct + "%";
      text.textContent = `${esc(st.stage || "")} ${st.done}/${st.total}`;
    }
    if (!st.running) {
      fill.style.width = "100%";
      if (st.last_error) { groupsEl.innerHTML = `<p class="error">${esc(st.last_error)}</p>`; return; }
      lastDupStatus = st;
      renderDupGroups(st);
      renderCardCheckboxes();
      updateDupButtons();
      bar.hidden = true;
      return;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  groupsEl.innerHTML = `<p class="muted">${esc(t("loading"))}</p>`;
}

function dupThumbHtml(it) {
  const src = it.gallery_id != null
    ? `/api/galleries/${it.gallery_id}/thumb/0`
    : (it.cover_data || null);
  return src ? `<img class="dup-thumb" loading="lazy" src="${src}" alt="">` : `<span class="dup-thumb dup-thumb-empty"></span>`;
}

function dupItemState(it) {
  return it.gallery_id != null ? "local" : "cloud";
}

function applyDupFilter(groups) {
  if (dupFilter === "all") return groups;
  return groups
    .map(g => ({ ...g, items: g.items.filter(it => dupItemState(it) === dupFilter) }))
    .filter(g => g.items.length >= 1);
}

function renderDupGroups(st) {
  const el = document.getElementById("dup-groups");
  if (!el) return;
  const groups = applyDupFilter(st.groups || []);
  if (!groups.length) { el.innerHTML = `<p class="muted">${esc(t("dupNone"))}</p>`; return; }
  const perPage = 24;
  const totalPages = Math.max(1, Math.ceil(groups.length / perPage));
  const page = Math.max(1, Math.min(dupPage, totalPages));
  const slice = groups.slice((page - 1) * perPage, page * perPage);
  const renderGroup = (g, gi) => {
    const hidden = dupLocallyIgnored.has(g.key);
    return `
      <div class="panel dup-group ${hidden ? "dup-hidden" : ""}" style="margin-top:14px">
        <div class="dup-group-head">
          <span class="dup-count">${esc(g.items.length)} ×</span>
          <a class="dup-main-title" href="${esc(g.items[0].url)}" target="_blank" rel="noopener">${esc(g.items[0].display_title || g.items[0].title)}</a>
          ${g.artist ? `<span class="dup-artist">${esc(g.artist)}</span>` : ""}
          ${hidden ? `<span class="badge dup-ignored-badge">${esc(t("dupIgnored"))}</span>` : ""}
          <span class="dup-head-actions"><button class="secondary" data-action="dup-group-sel" data-gi="${gi}" type="button">${esc(t("select"))}</button></span>
        </div>
        ${g.items.map((it, ii) => `
          <div class="dup-row">
            <label class="checkbox"><input type="checkbox" data-dup-gid="${it.gid}" data-key="${esc(g.key)}" data-gi="${gi}" data-ii="${ii}"${selDup.has(it.gid) ? " checked" : ""}>
              <span class="dup-thumb-wrap">${dupThumbHtml(it)}</span>
              <span class="dup-body">
                <span class="dup-title">
                  <a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.display_title || it.title)}</a>
                </span>
                <span class="dup-meta">
                  ${it.gallery_id != null ? `<a class="badge dup-badge-local" href="${navHash("gallery", { id: it.gallery_id })}">${esc(t("favLocal"))}</a>` : `<span class="badge dup-badge-cloud">${esc(t("favCloud"))}</span>`}
                  <span class="badge">#${it.favcat}${favCatNames[it.favcat] ? " " + esc(favCatNames[it.favcat]) : ""}</span>
                  ${fmtDate(it.posted_at) ? `<span class="badge">${esc(t("postedDate"))} ${fmtDate(it.posted_at)}</span>` : ""}
                  ${it.file_size ? `<span class="badge">${fmtSize(it.file_size)}</span>` : ""}
                </span>
                ${(it.tags || []).length ? `<span class="dup-tags">${it.tags.map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</span>` : ""}
              </span>
            </label>
          </div>`).join("")}
      </div>`;
  };
  const pageLinks = [];
  for (let p = Math.max(1, page - 2); p <= Math.min(totalPages, page + 2); p++) {
    pageLinks.push(p === page
      ? `<strong class="cur">${p}</strong>`
      : `<a class="page-link" href="#" data-action="dup-page" data-page="${p}">${p}</a>`);
  }
  const pagerHtml = groups.length > perPage
    ? `<div class="pages pager" style="margin-top:16px">${pageLinks.join(" ")} ${pagerJump(page, totalPages)}</div>`
    : "";
  el.innerHTML = `
    <p class="sub">${esc(t("dupFound"))}: ${groups.length} ${esc(t("dupGroups"))} · ${groups.reduce((n, g) => n + g.items.length, 0)} ${esc(t("dupItems"))}</p>
    ${slice.map((g, i) => renderGroup(g, (page - 1) * perPage + i)).join("")}
    ${pagerHtml}`;
}

function favRingHtml(done, total) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const r = 15.9, c = 2 * Math.PI * r;
  const off = c * (1 - pct / 100);
  return `<span class="fav-ring" title="${esc(done + " / " + total)}">
    <svg viewBox="0 0 36 36"><circle class="ring-bg" cx="18" cy="18" r="${r}"></circle>
    <circle class="ring-fg" cx="18" cy="18" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${off}"></circle></svg>
  </span>`;
}

async function pollFavoriteRings() {
  if (favTimer) clearInterval(favTimer);
  const tick = async () => {
    try {
      const st = await api("GET", "/api/favorites/check-status");
      const cats = (st && st.categories) || {};
      document.querySelectorAll("#fav-list tr[data-favcat]").forEach(tr => {
        const nameCell = tr.querySelector(".fav-name");
        if (!nameCell) return;
        const old = nameCell.querySelector(".fav-ring");
        if (old) old.remove();
        const e = cats[tr.dataset.favcat];
        if (e && e.running) {
          nameCell.insertAdjacentHTML("beforeend", favRingHtml(e.done || 0, e.total || 0));
        }
      });
    } catch (_) { /* transient */ }
  };
  tick();
  favTimer = setInterval(tick, 3000);
}

// fmtSize, fmtDate moved to utils.js

async function saveFavoriteCategories() {
  const favorites = [...document.querySelectorAll("#fav-list tr[data-favcat]")].map(tr => ({
    favcat: parseInt(tr.dataset.favcat, 10),
    enabled: tr.querySelector(".fav-enabled").checked,
    mode: tr.querySelector(".fav-mode").value,
    poll_interval_minutes: Math.max(1, parseInt(tr.querySelector(".fav-interval").value, 10) || 720),
  }));
  try {
    await api("POST", "/api/settings", { favorites });
    app.settings = null;
    toast(t("saveOk"));
  } catch (e) { toast(e.message); }
}

async function syncFavoriteCategories() {
  try {
    await api("POST", "/api/favorites/sync-categories");
    app.settings = null;
    toast(t("saveOk"));
    renderFavorites();
  } catch (e) { toast(e.message); }
}

async function checkFavoriteCategory(favcat) {
  try {
    await api("POST", `/api/favorites/${favcat}/check`);
    toast("#" + favcat + " · " + t("checkNow"));
  } catch (e) { toast(e.message); }
}

async function checkAllFavorites() {
  try {
    await api("POST", "/api/favorites/check-all");
    toast(t("checkAll"));
    pollFavoriteRings();
  } catch (e) { toast(e.message); }
}

async function downloadMissingFavorites() {
  try {
    await api("POST", "/api/favorites/download-missing");
    toast(t("downloadMissingStarted"));
    if (app.view === "favorites") pollFavoriteRings();
    else location.hash = "#/logs";
  } catch (e) { toast(e.message); }
}

// onClick / onSubmit / toggleLang moved to events.js


async function randomGallery() {
  try { const d = await api("GET", "/api/galleries/random"); location.hash = navHash("gallery", { id: d.id }); }
  catch (e) { toast(e.message); }
}

// logTimer moved to state.js

function taskMeta(task, stage) {
  switch (task) {
    case "scan": return { label: t("scanning"), desc: t("scanDesc") };
    case "tag-sync": return { label: t("tagSyncing"), desc: t("tagSyncDesc") };
    case "thumbs": return { label: t("thumbs"), desc: t("thumbsDesc") };
    case "metadata": return {
      label: stage === "apply" ? t("favMetaApply") : t("favMetaSync"),
      desc: t("metaDesc"),
    };
    case "favcheck": return { label: t("checkAll"), desc: t("favCheckDesc") };
    case "translation": return { label: t("translationUpdate"), desc: t("transDesc") };
    case "gallery-delete": return { label: t("deleteGalleryLog"), desc: t("deleteFiles") };
    case "favorites-remove": return { label: t("favoritesRemoveLog"), desc: t("confirmDupDelete") };
    default: return { label: task, desc: "" };
  }
}

// fmtDateTime, fmtDuration moved to utils.js

async function renderLogs() {
  $view().innerHTML = `
    <header><p class="eyebrow">ACTIVITY</p><h1>${esc(t("logs"))}</h1>
    <p class="sub">${esc(t("logsSub"))}</p></header>
    <section class="log-block">
      <h2>${esc(t("runningTasks"))}</h2>
      <div id="log-running"><p>${esc(t("loading"))}</p></div>
    </section>
    <section class="log-block">
      <h2>${esc(t("finishedTasks"))}</h2>
      <div id="log-finished"><p>${esc(t("loading"))}</p></div>
    </section>`;
  pollLogs();
}

function runningTaskRow(it) {
  const meta = taskMeta(it.task, it.stage);
  const pct = it.total > 0 ? Math.min(100, Math.round((it.done / it.total) * 100)) : null;
  return `<div class="log-row">
    <span class="log-time" title="${esc(t("startedAt"))}">${fmtDateTime(it.started_at)}</span>
    <span class="log-title">${esc(meta.label)}</span>
    <span class="log-status run">${esc(t("taskRunning"))}${pct !== null ? ` · ${it.done}/${it.total}` : (it.done ? ` · ${it.done}` : "")}</span>
    <span class="log-progress">${pct !== null
      ? `<div class="dl-progress"><div class="dl-progress-bar" style="width:${pct}%"></div></div>`
      : `<div class="dl-progress dl-progress-indet"></div>`}</span>
    <span class="log-desc">${esc(meta.desc)}</span>
    ${it.cancellable ? `<button class="secondary" data-action="cancel-task" data-task="${esc(it.task)}" type="button">${esc(t("cancelTask"))}</button>` : ""}
  </div>`;
}

function finishedTaskRow(it) {
  const meta = taskMeta(it.task, it.stage);
  const badge = it.status === "success" ? "ok" : (it.status === "cancelled" ? "warn" : "fail");
  const statusText = it.status === "success" ? t("taskSuccess") : (it.status === "cancelled" ? t("taskCancelled") : t("taskFailed"));
  const reason = it.reason ? ` <span class="muted">${esc(it.reason)}</span>` : "";
  return `<div class="log-row">
    <span class="log-time" title="${esc(t("startedAt"))}">${fmtDateTime(it.started_at)}</span>
    <span class="log-title">${esc(meta.label)}</span>
    <span class="log-status ${badge}">${esc(statusText)}</span>
    <span class="log-desc">${esc(meta.desc)}${reason}</span>
    <span class="log-dur">${esc(t("duration"))} ${fmtDuration(it.started_at, it.completed_at)}</span>
    <span class="log-time" title="${esc(t("finishedAt"))}">${fmtDateTime(it.completed_at)}</span>
  </div>`;
}

async function pollLogs() {
  if (logTimer) clearInterval(logTimer);
  const tick = async () => {
    const runEl = document.getElementById("log-running");
    const finEl = document.getElementById("log-finished");
    if (!runEl || !finEl) return;
    try {
      const data = await api("GET", "/api/logs");
      const running = data.running || [];
      const finished = data.finished || [];
      runEl.innerHTML = running.length
        ? `<div class="log-rows">` + running.map(runningTaskRow).join("") + `</div>`
        : `<p class="muted">${esc(t("noRunningTasks"))}</p>`;
      finEl.innerHTML = finished.length
        ? `<div class="log-rows">` + finished.map(finishedTaskRow).join("") + `</div>`
        : `<p class="muted">${esc(t("noFinishedTasks"))}</p>`;
    } catch (_) { /* transient */ }
  };
  tick();
  logTimer = setInterval(tick, 2000);
}

async function cancelTask(task) {
  try {
    await api("POST", `/api/logs/${encodeURIComponent(task)}/cancel`);
    toast(t("cancelTask") + " · " + task);
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function clearHistory() {
  try { await api("DELETE", "/api/history"); renderHistory(); }
  catch (e) { toast(e.message); }
}

async function cancelDownload(id) {
  try { await api("POST", `/api/downloads/${id}/cancel`); toast("#" + id + " cancelled"); loadDownloads(app.query.filter || "all", app.query.page || "1"); }
  catch (e) { toast(e.message); }
}

async function retryDownload(id) {
  try { await api("POST", `/api/downloads/${id}/retry`); toast("#" + id + " queued"); loadDownloads(app.query.filter || "all", app.query.page || "1"); }
  catch (e) { toast(e.message); }
}

async function deleteDownload(id) {
  if (!window.confirm(t("deleteDl") + " #" + id + "?")) return;
  try { await api("DELETE", `/api/downloads/${id}`); toast("#" + id + " " + t("deleted")); loadDownloads(app.query.filter || "all", app.query.page || "1"); }
  catch (e) { toast(e.message); }
}

function selectAllDownloads() {
  const boxes = document.querySelectorAll(".dl-check");
  const all = boxes.length && [...boxes].every(b => b.checked);
  boxes.forEach(b => { b.checked = !all; });
}

async function deleteSelectedDownloads() {
  const ids = [...document.querySelectorAll(".dl-check:checked")].map(b => b.getAttribute("data-id"));
  if (!ids.length) { toast(t("deleteSel")); return; }
  if (!window.confirm(t("deleteSel") + " (" + ids.length + ")?")) return;
  let ok = 0, fail = 0;
  for (const id of ids) {
    try { await api("DELETE", `/api/downloads/${id}`); ok++; }
    catch (_) { fail++; }
  }
  toast(`${ok} ${t("deleted")}${fail ? `, ${fail} failed` : ""}`);
  loadDownloads(app.query.filter || "all", app.query.page || "1");
}

async function retrySelectedDownloads() {
  const ids = [...document.querySelectorAll(".dl-check:checked")].map(b => b.getAttribute("data-id"));
  if (!ids.length) { toast(t("retrySelected")); return; }
  let ok = 0, fail = 0;
  for (const id of ids) {
    try { await api("POST", `/api/downloads/${id}/retry`); ok++; }
    catch (_) { fail++; }
  }
  toast(`${ok} queued${fail ? `, ${fail} failed` : ""}`);
  loadDownloads(app.query.filter || "all", app.query.page || "1");
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

async function favListDownload(favcat) {
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!selected.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/favorites/download-selected", { favcat, gids: selected });
    toast(t("favDlQueued") + ": " + r.queued + (r.skipped ? " · " + t("favDlSkip") + ": " + r.skipped : ""));
  } catch (e) { toast(e.message); }
  selFav.clear();
}

async function favListDownloadOrig(favcat) {
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!selected.length) { toast(t("select")); return; }
  try {
    const r = await api("POST", "/api/favorites/download-selected", { favcat, gids: selected, quality: "original" });
    toast(t("favDlQueued") + ": " + r.queued + (r.skipped ? " · " + t("favDlSkip") + ": " + r.skipped : ""));
  } catch (e) { toast(e.message); }
  selFav.clear();
}

async function favListArchive(favcat) {
  const selected = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!selected.length) { toast(t("select")); return; }
  const tier = await showArchiveDialog(selected);
  if (!tier) return;
  try {
    const r = await api("POST", "/api/favorites/download-selected", { favcat, gids: selected, archive: true, quality: tier });
    toast(t("archiveQueued") + ": " + r.queued + (r.skipped ? " · " + t("archiveUnsupported") : ""));
  } catch (e) { toast(e.message); }
  selFav.clear();
}

function showArchiveDialog(gids, opts) {
  opts = opts || {};
  const lockTier = opts.lockTier || null;
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "gv-overlay";
    const tiersHtml = lockTier
      ? `<label><input type="radio" name="archive-tier" value="${lockTier}" checked> ${esc(t(lockTier === "original" ? "archiveTierOriginal" : "archiveTierResample"))}</label>`
      : `<label><input type="radio" name="archive-tier" value="original"> ${esc(t("archiveTierOriginal"))}</label>
        <label><input type="radio" name="archive-tier" value="resample"> ${esc(t("archiveTierResample"))}</label>`;
    overlay.innerHTML = `<div class="gv-modal" role="dialog" aria-modal="true">
      <h3>${esc(t("archiveTitle"))}</h3>
      <div class="gv-modal-body">${esc(t("loading"))}</div>
      <div class="gv-modal-foot">
        <span class="archive-funds"></span>
        <span class="archive-tiers">
          ${tiersHtml}
        </span>
        <button class="primary" data-archive-confirm disabled type="button">${esc(t("archiveConfirm"))}</button>
        <button class="secondary" data-archive-cancel type="button">${esc(t("cancel"))}</button>
      </div>
    </div>`;
    let settled = false;
    const close = (value) => {
      if (settled) return;
      settled = true;
      overlay.remove();
      resolve(value);
    };
    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("[data-archive-cancel]").addEventListener("click", () => close(null));
    overlay.querySelector("[data-archive-confirm]").addEventListener("click", () => {
      const tier = overlay.querySelector('input[name="archive-tier"]:checked');
      close(tier ? tier.value : null);
    });
    document.body.appendChild(overlay);
    api("POST", "/api/archives/preview", { gids })
      .then(data => {
        const bodyEl = overlay.querySelector(".gv-modal-body");
        const items = data && data.items ? data.items : [];
        if (!items.length) {
          bodyEl.innerHTML = `<p>${esc(t("archiveNoItems"))}</p>`;
          return;
        }
        const confirm = overlay.querySelector("[data-archive-confirm]");
        if (lockTier === "original") {
          const rows = items.map(it => {
            if (it.error) {
              return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td colspan="1"><span class="error">${esc(it.error)}</span></td></tr>`;
            }
            const orig = it.original_cost == null
              ? `<span class="muted">N/A</span>`
              : (it.original_available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + it.original_cost + " GP · " + fmtSize(it.original_size);
            return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td>${orig}</td></tr>`;
          }).join("");
          bodyEl.innerHTML = `<table class="table archive-table"><thead><tr><th>${esc(t("gallery"))}</th><th>${esc(t("archiveTierOriginal"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
          const first = items[0];
          confirm.disabled = !!(first && !first.error && first.original_cost != null && !first.original_available);
        } else {
          const rows = items.map(it => {
            if (it.error) {
              return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td colspan="2"><span class="error">${esc(it.error)}</span></td></tr>`;
            }
            const orig = it.original_cost == null
              ? `<span class="muted">N/A</span>`
              : (it.original_available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + it.original_cost + " GP · " + fmtSize(it.original_size);
            const res = it.resample_cost == null
              ? `<span class="muted">N/A</span>`
              : (it.resample_available ? "" : `<span class="error" title="${esc(t("archiveUnavailable"))}">⚠ </span>`) + it.resample_cost + " GP · " + fmtSize(it.resample_size);
            return `<tr><td>${esc(it.title || ("gid " + it.gid))}</td><td>${orig}</td><td>${res}</td></tr>`;
          }).join("");
          bodyEl.innerHTML = `<table class="table archive-table"><thead><tr><th>${esc(t("gallery"))}</th><th>${esc(t("archiveTierOriginal"))}</th><th>${esc(t("archiveTierResample"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
          confirm.disabled = false;
        }
        if (data && data.funds != null) {
          overlay.querySelector(".archive-funds").textContent = t("archiveFunds") + ": " + data.funds + " GP";
        }
        if (!lockTier) {
          const defaultTier = app.settings && app.settings.archive_quality === "original" ? "original" : "resample";
          const radio = overlay.querySelector(`input[name="archive-tier"][value="${defaultTier}"]`);
          if (radio) radio.checked = true;
        }
      })
      .catch(err => {
        const bodyEl = overlay.querySelector(".gv-modal-body");
        bodyEl.innerHTML = `<p class="error">${esc(err.message || t("archivePreviewFail"))}</p>`;
      });
  });
}

async function favListUnfavorite(favcat) {
  const items = [...document.querySelectorAll('#fav-items [data-fav-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.favGid, 10));
  if (!items.length) { toast(t("select")); return; }
  if (!window.confirm(t("confirmFavRemove") + " " + items.length)) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: items, delete_local: false });
    toast(t("unfavorited") + (r.cloud_ok ? "" : " · " + t("unfavoritedLocal")));
    selFav.clear();
    router();
  } catch (e) { toast(e.message); }
}

// lastDupStatus moved to state.js

async function dupAction(deleteLocal) {
  const items = [...document.querySelectorAll('#dup-groups [data-dup-gid]')]
    .filter(cb => cb.checked).map(cb => parseInt(cb.dataset.dupGid, 10));
  if (!items.length) { toast(t("select")); return; }
  const msg = deleteLocal ? t("confirmDupDelete") : t("confirmDupUnfav");
  if (!window.confirm(msg + " " + items.length)) return;
  try {
    const r = await api("POST", "/api/favorites/remove", { gids: items, delete_local: deleteLocal });
    let msg = t("unfavorited") + (r.cloud_ok ? "" : " · " + t("unfavoritedLocal"))
      + (r.deleted_local_galleries ? " · " + t("deleted") + " " + r.deleted_local_galleries : "");
    if (r.failed_deletions && r.failed_deletions.length) {
      msg += " · " + t("dupDeleteFail") + r.failed_deletions.length;
      console.warn("local delete failed:", r.failed_deletions);
    }
    toast(msg);
    selDup.clear();
    runDupScan();
  } catch (e) { toast(e.message); }
}

function dupSelectGroup(gi) {
  const filtered = lastDupStatus ? applyDupFilter(lastDupStatus.groups || []) : [];
  const group = filtered[gi];
  if (!group) return;
  const gids = group.items.map(it => it.gid);
  const allSel = gids.every(gid => selDup.has(gid));
  const cbs = [...document.querySelectorAll(`#dup-groups input[data-gi="${gi}"]`)];
  cbs.forEach(cb => {
    const gid = parseInt(cb.dataset.dupGid, 10);
    if (allSel) selDup.delete(gid); else selDup.add(gid);
    cb.checked = !allSel;
  });
  updateDupButtons();
}

async function dupIgnoreSelected() {
  const keys = new Set();
  document.querySelectorAll('#dup-groups input[data-dup-gid]:checked').forEach(cb => {
    const k = cb.getAttribute("data-key");
    if (k) keys.add(k);
  });
  if (!keys.size) { toast(t("select")); return; }
  const groupsByKey = new Map((lastDupStatus.groups || []).map(g => [g.key, g]));
  let ok = 0;
  for (const key of keys) {
    const group = groupsByKey.get(key);
    try {
      await api("POST", "/api/favorites/duplicates/ignore", {
        key,
        title: group ? group.items[0].title : "",
        gids: group ? group.items.map(it => it.gid) : [],
      });
      ok++;
    } catch (_) { /* keep going */ }
  }
  keys.forEach(k => dupLocallyIgnored.add(k));
  selDup.clear();
  toast(t("dupIgnoredOk") + ": " + ok);
  renderDupGroupsFromCache();
  renderCardCheckboxes();
  updateDupButtons();
}

async function dupUnignore(key) {
  if (!key) return;
  try {
    await api("DELETE", `/api/favorites/duplicates/ignore?key=${encodeURIComponent(key)}`);
    toast(t("dupUnignoredOk"));
    if (app.view === "favignored") { renderFavIgnored(); }
    else { dupLocallyIgnored.delete(key); renderDupGroupsFromCache(); }
  } catch (e) { toast(e.message); }
}

// --- Gallery updates (re-uploaded / new-version tracking) ------------------

// updatesTimer/selUpdate/UPD_* moved to state.js

function updStatusKey(st) { return UPD_STATUS_KEYS[st] || st; }

function updateUpdSelBtn() {
  const n = selUpdate.size;
  const labels = {
    "upd-update": t("updateSelected"),
    "upd-update-orig": t("updOrig"),
    "upd-archive": t("updArchive"),
    "upd-ignore": t("ignoreSelected"),
    "upd-delete-selected": t("deleteSel"),
  };
  for (const [action, base] of Object.entries(labels)) {
    const btn = document.querySelector(`[data-action="${action}"]`);
    if (btn) btn.textContent = base + (n ? ` (${n})` : "");
  }
}

async function renderUpdates() {
  const page = app.query.page || "1";
  const state = app.query.state || "active";
  const selCount = selUpdate.size;
  const stateBtn = (s, label) =>
    `<button class="secondary${state === s ? " active-pill" : ""}" data-action="upd-state" data-state="${s}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <a class="link-button" href="#/favorites">← ${esc(t("favorites"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">GALLERY UPDATES</p><h1>${esc(t("galleryUpdates"))}</h1>
    <p class="sub"><span id="upd-status">…</span></p></header>
    <div class="toolbar">
      <button class="primary" data-action="upd-update" type="button">${esc(t("updateSelected"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="upd-update-orig" type="button">${esc(t("updOrig"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="upd-archive" type="button">${esc(t("updArchive"))}${selCount ? ` (${selCount})` : ""}</button>
      <button class="secondary" data-action="upd-ignore" type="button">${esc(t("ignoreSelected"))}${selCount ? ` (${selCount})` : ""}</button>
      ${state === "failed" ? `<button class="secondary danger" data-action="upd-delete-selected" type="button">${esc(t("deleteSel"))}${selCount ? ` (${selCount})` : ""}</button>` : ""}
      <button class="secondary" data-action="upd-scan" type="button">${esc(t("scanNow"))}</button>
      <label class="checkbox" style="margin-left:12px"><input type="checkbox" data-action="upd-select-all"> ${esc(t("selectAll"))}</label>
      <a class="link-button" href="#/updates/ignored" style="margin-left:auto">${esc(t("updIgnoredPage"))}</a>
    </div>
    <div class="fav-state-filter">
      ${stateBtn("active", t("updStateActive"))}
      ${stateBtn("pending", t("updStatePending"))}
      ${stateBtn("downloading", t("updStateDownloading"))}
      ${stateBtn("failed", t("updStateFailed"))}
      ${stateBtn("all", t("updStateAll"))}
    </div>
    <div id="upd-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages pager" id="upd-pager"></div>`;
  pollUpdatesStatus();
  try {
    const qs = `page=${encodeURIComponent(page)}&page_size=${prefPageSize()}&state=${encodeURIComponent(state)}`;
    const data = await api("GET", `/api/updates?${qs}`);
    const el = document.getElementById("upd-list");
    if (!data.items.length) { el.innerHTML = `<p>${esc(t("updNoUpdates"))}</p>`; }
    else {
      el.innerHTML = `<table class="table"><thead><tr><th></th><th></th><th>${esc(t("gallery"))}</th><th>${esc(t("gid"))}</th><th>${esc(t("favorites"))}</th><th>${esc(t("status"))}</th></tr></thead><tbody>`
        + data.items.map(updRow).join("") + `</tbody></table>`;
      document.querySelectorAll('#upd-list input[data-upd-id]').forEach(cb => {
        cb.checked = selUpdate.has(parseInt(cb.dataset.updId, 10));
        cb.addEventListener("change", () => {
          const id = parseInt(cb.dataset.updId, 10);
          if (cb.checked) selUpdate.add(id); else selUpdate.delete(id);
          updateUpdSelBtn();
        });
      });
      const allBtn = document.querySelector('[data-action="upd-select-all"]');
      if (allBtn) allBtn.addEventListener("change", e => updSelectAll(e.target.checked));
    }
    updPager("upd-pager", data, page, state);
  } catch (e) { document.getElementById("upd-list").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

function updRow(u) {
  const cover = u.cover_url ? `<img loading="lazy" src="${u.cover_url}" alt="">` : `<span class="badge">no cover</span>`;
  const retry = u.status === "failed"
    ? ` <button class="secondary" data-action="upd-retry" data-id="${u.id}" type="button">${esc(t("retry"))}</button>`
    : "";
  return `<tr data-upd-id="${u.id}" data-new-gid="${u.new_gid}">
    <td><input type="checkbox" data-upd-id="${u.id}" aria-label="${esc(t("select"))}"></td>
    <td><a class="upd-cover" href="${navHash("gallery", { id: u.gallery_id })}">${cover}</a></td>
    <td><a href="${navHash("gallery", { id: u.gallery_id })}">${esc(u.title)}</a></td>
    <td class="muted">${u.old_gid} <span class="muted">${esc(t("updToNewer"))}</span> ${u.new_gid}</td>
    <td><a class="badge" href="#/favorites/${u.favcat}">#${u.favcat}${u.favcat_name ? " " + esc(u.favcat_name) : ""}</a></td>
    <td><span class="badge upd-st-${u.status}">${esc(t(updStatusKey(u.status)))}</span>${retry}${u.error_message ? `<p class="muted">${esc(u.error_message)}</p>` : ""}</td>
  </tr>`;
}

function updPager(elId, data, page, state) {
  const el = document.getElementById(elId);
  if (!el || !data) return;
  const total = data.total, pageSize = data.page_size || 24;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const cur = parseInt(page, 10) || 1;
  const qp = p => navHash("updates", {}, { page: p, page_size: pageSize, state });
  const parts = [];
  if (cur > 1) parts.push(`<a class="page-link" href="${qp(cur - 1)}">&lt;</a>`);
  for (let p = Math.max(1, cur - 2); p <= Math.min(pages, cur + 2); p++) {
    parts.push(p === cur
      ? `<strong class="cur">${p}</strong>`
      : `<a class="page-link" href="${qp(p)}">${p}</a>`);
  }
  if (cur < pages) parts.push(`<a class="page-link" href="${qp(cur + 1)}">&gt;</a>`);
  el.innerHTML = `${parts.join(" ")} ${pagerJump(cur, pages)} · ${esc(t("perPage"))} ${pageSizeSelect(pageSize, "updates")}`;
}

async function pollUpdatesStatus() {
  if (updatesTimer) clearInterval(updatesTimer);
  const tick = async () => {
    try {
      const st = await api("GET", "/api/updates/status");
      const el = document.getElementById("upd-status");
      if (!el) return;
      const counts = st.counts || {};
      const total = (counts.pending || 0) + (counts.downloading || 0) + (counts.failed || 0);
      const parts = [];
      if (st.detecting) parts.push(`<b>${esc(t("updScanning"))}</b>`);
      if (st.last_detected_at) parts.push(`${esc(t("updDetectedAt"))} ${fmtDate(st.last_detected_at)}`);
      if (st.last_error) parts.push(`<span class="error">${esc(st.last_error)}</span>`);
      parts.push(`<b>${total}</b>`);
      el.innerHTML = parts.join(" · ");
    } catch (_) { /* transient */ }
  };
  tick();
  updatesTimer = setInterval(tick, 5000);
}

function updSelectAll(checked) {
  selUpdate.clear();
  document.querySelectorAll('#upd-list input[data-upd-id]').forEach(cb => {
    cb.checked = checked;
    if (checked) selUpdate.add(parseInt(cb.dataset.updId, 10));
  });
  updateUpdSelBtn();
}

async function updScan() {
  try {
    await api("POST", "/api/updates/scan");
    router();
  } catch (e) { toast(e.message); }
}

async function updRunIds(ids, quality) {
  if (!ids.length) { toast(t("select")); return; }
  try {
    const body = { ids };
    if (quality) body.quality = quality;
    const r = await api("POST", "/api/updates/update", body);
    selUpdate.clear();
    toast(t("updateSelected") + ": " + (r.started || 0) + (r.skipped ? ` (skip ${r.skipped})` : ""));
    router();
  } catch (e) { toast(e.message); }
}

async function updRunSelected() {
  await updRunIds([...selUpdate]);
}

async function updRunSelectedOrig() {
  await updRunIds([...selUpdate], "original");
}

async function updArchiveSelected() {
  const ids = [...selUpdate];
  if (!ids.length) { toast(t("select")); return; }
  const gids = ids.map(id => {
    const el = document.querySelector(`#upd-list [data-upd-id="${id}"]`);
    return el ? parseInt(el.getAttribute("data-new-gid"), 10) : null;
  }).filter(Boolean);
  if (!gids.length) { toast(t("select")); return; }
  const tier = await showArchiveDialog(gids);
  if (!tier) return;
  try {
    const r = await api("POST", "/api/updates/update", { ids, archive: true, quality: tier });
    selUpdate.clear();
    toast(t("archiveQueued") + ": " + (r.started || 0) + (r.skipped ? ` (skip ${r.skipped})` : ""));
    router();
  } catch (e) { toast(e.message); }
}

async function updIgnoreSelected() {
  const ids = [...selUpdate];
  if (!ids.length) { toast(t("select")); return; }
  try {
    await api("POST", "/api/updates/ignore", { ids });
    selUpdate.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function updDeleteSelected() {
  const ids = [...selUpdate];
  if (!ids.length) { toast(t("select")); return; }
  if (!window.confirm(t("deleteSel") + " (" + ids.length + ")?")) return;
  try {
    await api("POST", "/api/updates/delete", { ids });
    selUpdate.clear();
    router();
  } catch (e) { toast(e.message); }
}

async function updUnignore(ids) {
  if (!ids.length) { toast(t("select")); return; }
  try {
    await api("POST", "/api/updates/unignore", { ids });
    router();
  } catch (e) { toast(e.message); }
}

async function updUnignoreSelected() {
  const ids = [...document.querySelectorAll('#upd-ignored input[data-upd-id]:checked')]
    .map(cb => parseInt(cb.dataset.updId, 10));
  await updUnignore(ids);
}

async function renderUpdateIgnored() {
  let data;
  try { data = await api("GET", "/api/updates/ignored?page=1&page_size=500"); }
  catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
  $view().innerHTML = `
    <a class="link-button" href="#/updates">← ${esc(t("galleryUpdates"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">GALLERY UPDATES</p><h1>${esc(t("updIgnoredPage"))}</h1></header>
    <div class="toolbar">
      <button class="primary" data-action="upd-unignore-selected" type="button">${esc(t("updUnignoreSel"))}</button>
    </div>
    <div id="upd-ignored">${(data.items || []).length ? "" : `<p class="muted">${esc(t("updNone"))}</p>`}</div>`;
  const el = document.getElementById("upd-ignored");
  if (!(data.items || []).length) return;
  el.innerHTML = data.items.map(u => `
    <div class="panel" style="margin-top:10px;padding:10px 14px">
      <label class="checkbox" style="margin:0"><input type="checkbox" data-upd-id="${u.id}"> <a href="${navHash("gallery", { id: u.gallery_id })}">${esc(u.title)}</a></label>
      <span class="badge">${u.old_gid} → ${u.new_gid}</span>
      <button class="secondary" data-action="upd-unignore" data-id="${u.id}" type="button">${esc(t("updUnignore"))}</button>
    </div>`).join("");
}

async function renderFavIgnored() {
  let list = [];
  try { list = await api("GET", "/api/favorites/duplicates/ignored"); }
  catch (e) { $view().innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
  await loadFavNames();
  $view().innerHTML = `
    <a class="link-button" href="#/favorites/manage">← ${esc(t("favManage"))}</a>
    <header style="margin-top:16px"><p class="eyebrow">FAVORITES</p><h1>${esc(t("dupIgnoredPage"))}</h1>
    <p class="sub">${esc(t("dupIgnoredSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="dup-unignore-selected" type="button">${esc(t("dupUnignoreSel"))}</button>
      <button class="secondary" data-action="dup-ignored-clear" type="button">${esc(t("clearSel"))}</button>
    </div>
    <div id="ignored-list">${list.length ? "" : `<p class="muted">${esc(t("dupNone"))}</p>`}</div>`;
  const el = document.getElementById("ignored-list");
  if (!list.length) return;
  el.innerHTML = list.map(g => `
    <div class="panel dup-group" style="margin-top:14px">
      <div class="dup-group-head">
        <label class="checkbox" style="margin:0"><input type="checkbox" data-ignore-key="${esc(g.key)}"> <strong>${esc((g.items || []).length)} ×</strong></label>
        <span class="dup-main-title">${esc(g.title || g.key)}</span>
        <span class="dup-head-actions"><button class="secondary" data-action="dup-unignore-one" data-key="${esc(g.key)}" type="button">${esc(t("dupUnignore"))}</button></span>
      </div>
      ${(g.items || []).map(it => `
        <div class="dup-row">
          <span class="dup-thumb-wrap">${it.cover_url ? `<img class="dup-thumb" loading="lazy" src="${it.cover_url}" alt="">` : (it.cover_data ? `<img class="dup-thumb" loading="lazy" src="${it.cover_data}" alt="">` : `<span class="dup-thumb dup-thumb-empty"></span>`)}</span>
          <span class="dup-body">
            <span class="dup-title"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></span>
            <span class="dup-meta">
              ${it.gallery_id != null ? `<a class="badge dup-badge-local" href="${navHash("gallery", { id: it.gallery_id })}">${esc(t("favLocal"))}</a>` : `<span class="badge dup-badge-cloud">${esc(t("favCloud"))}</span>`}
              <span class="badge">#${it.favcat}${favCatNames[it.favcat] ? " " + esc(favCatNames[it.favcat]) : ""}</span>
              ${fmtDate(it.posted_at) ? `<span class="badge">${esc(t("postedDate"))} ${fmtDate(it.posted_at)}</span>` : ""}
              ${it.file_size ? `<span class="badge">${fmtSize(it.file_size)}</span>` : ""}
            </span>
            ${(it.tags || []).length ? `<span class="dup-tags">${it.tags.map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</span>` : ""}
          </span>
        </div>`).join("")}
    </div>`).join("");
  document.querySelectorAll('#ignored-list input[data-ignore-key]').forEach(cb => {
    cb.addEventListener("change", updateIgnoredSelBtn);
  });
}

function updateIgnoredSelBtn() {
  const n = document.querySelectorAll('#ignored-list input[data-ignore-key]:checked').length;
  const btn = document.querySelector('[data-action="dup-unignore-selected"]');
  if (btn) btn.textContent = t("dupUnignoreSel") + (n ? ` (${n})` : "");
}

async function dupUnignoreSelected() {
  const keys = [...document.querySelectorAll('#ignored-list input[data-ignore-key]:checked')]
    .map(cb => cb.getAttribute("data-ignore-key"));
  if (!keys.length) { toast(t("select")); return; }
  let ok = 0;
  for (const key of keys) {
    try { await api("DELETE", `/api/favorites/duplicates/ignore?key=${encodeURIComponent(key)}`); ok++; }
    catch (_) { /* keep going */ }
  }
  toast(t("dupUnignoredOk") + ": " + ok);
  renderFavIgnored();
}

function updateDupButtons() {
  document.querySelectorAll('[data-action="dup-unfav"], [data-action="dup-unfav-delete"]').forEach(b => {
    b.textContent = (b.getAttribute("data-action") === "dup-unfav" ? t("dupUnfav") : t("dupUnfavDelete")) + (selDup.size ? ` (${selDup.size})` : "");
  });
}

// --- Duplicate copies (library scan) --------------------------------------
// dupGal* + DUPGAL_* moved to state.js

function storageLabel(type) {
  return { ehviewer_dir: "EhViewer", cbz: "CBZ", cbr: "CBR", folder: "Folder" }[type] || type || "";
}

function dupGalThumb(c) {
  const src = c.gallery_id != null
    ? `/api/galleries/${c.gallery_id}/thumb/0`
    : `/api/scan/duplicates/thumb/${encodeURIComponent(c.key)}`;
  return `<img class="dup-thumb" loading="lazy" src="${src}" alt="">`;
}

async function loadDuplicates(showLoading = true) {
  const el = document.getElementById("dupgal-groups");
  if (showLoading && el) el.innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    const data = await api("GET", "/api/scan/duplicates");
    dupGalCache = (data && data.groups) || [];
  } catch (e) {
    if (el) el.innerHTML = `<p class="error">${esc(e.message)}</p>`;
    return false;
  }
  return true;
}

function renderDuplicatesList() {
  const el = document.getElementById("dupgal-groups");
  if (!el) return;
  const groups = (dupGalCache || []).filter(g => dupGalFilter === "all" || g.status === dupGalFilter);
  if (!groups.length) {
    el.innerHTML = `<p class="muted">${esc(t("dupGalNone"))}</p>`;
    return;
  }
  const open = dupGalCache.filter(g => g.status === "open").length;
  const renderCopy = (c, g) => {
    const isCurrent = !!c.gallery_id;
    return `
      <div class="dup-row">
        <span class="dup-thumb-wrap">${dupGalThumb(c)}</span>
        <span class="dup-body">
          <span class="dup-title">${esc(c.display_title || c.title || c.path)}</span>
          <span class="dup-meta">
            ${isCurrent ? `<span class="badge dup-badge-local">${esc(t("dupGalCurrent"))}</span>` : `<span class="badge dup-badge-cloud">${esc(storageLabel(c.storage_type))}</span>`}
            ${c.page_count != null ? `<span class="badge">${c.page_count} P</span>` : ""}
            ${c.file_size ? `<span class="badge">${fmtSize(c.file_size)}</span>` : ""}
            ${fmtDate(c.posted_at) ? `<span class="badge">${esc(t("postedDate"))} ${fmtDate(c.posted_at)}</span>` : ""}
          </span>
          ${(c.tags || []).length ? `<span class="dup-tags">${c.tags.map(tg => `<span class="nst ${nsClass(tg.namespace)}">${esc(tagText(tg))}</span>`).join("")}</span>` : ""}
          <span class="dup-meta" style="margin-top:6px">
            <button class="secondary" data-action="dupgal-keep" data-gid="${g.gid}" data-path="${esc(c.path)}" type="button">${esc(t("dupGalKeep"))}</button>
            <button class="secondary danger" data-action="dupgal-keep-del" data-gid="${g.gid}" data-path="${esc(c.path)}" type="button">${esc(t("dupGalKeepDel"))}</button>
          </span>
        </span>
      </div>`;
  };
  el.innerHTML = `
    <p class="sub">${esc(t("dupGalFound"))}: ${groups.length} ${esc(t("dupGalGroups"))}${open ? ` · ${open} ${esc(t("dupGalOpen"))}` : ""}</p>
    ${groups.map(g => `
      <div class="panel dup-group" style="margin-top:14px">
        <div class="dup-group-head">
          <span class="dup-count">#${g.gid}</span>
          <span class="dup-main-title">${esc((g.copies && g.copies[0] && (g.copies[0].display_title || g.copies[0].title)) || ("gid " + g.gid))}</span>
          <span class="badge">${esc(g.policy || "")}</span>
          <span class="badge">${esc(t(DUPGAL_STATUSES[g.status] || "dupGalOpen"))}</span>
          <span class="dup-head-actions">
            ${g.status === "open"
              ? `<button class="secondary" data-action="dupgal-dismiss" data-gid="${g.gid}" type="button">${esc(t("dupGalDismiss"))}</button>`
              : `<button class="secondary" data-action="dupgal-restore" data-gid="${g.gid}" type="button">${esc(t("dupGalRestore"))}</button>`}
          </span>
        </div>
        ${(g.copies || []).map(c => renderCopy(c, g)).join("")}
      </div>`).join("")}`;
}

async function renderDuplicates() {
  const filterBtn = (val, label) =>
    `<button class="secondary${dupGalFilter === val ? " active-pill" : ""}" data-action="dupgal-filter" data-value="${val}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <header><p class="eyebrow">DUPLICATE COPIES</p><h1>${esc(t("dupGalTitle"))}</h1>
    <p class="sub">${esc(t("dupGalSub"))}</p></header>
    <div class="toolbar">
      <button class="primary" data-action="dupgal-scan" type="button">${esc(t("dupGalScan"))}</button>
      <button class="secondary" data-action="dupgal-refresh" type="button">${esc(t("dupGalRefresh"))}</button>
      ${filterBtn("all", t("dupGalAll"))}
      ${filterBtn("open", t("dupGalOpen"))}
      ${filterBtn("dismissed", t("dupGalDismissed"))}
    </div>
    <div id="dupgal-groups"><p class="muted">${esc(t("loading"))}</p></div>`;
  await loadDuplicates();
  renderDuplicatesList();
}

async function dupGalResolve(gid, path, deleteOthers) {
  if (!path) return;
  if (deleteOthers && !window.confirm(t("dupGalConfirmDel"))) return;
  if (!deleteOthers && !window.confirm(t("dupGalConfirmKeep"))) return;
  try {
    await api("POST", `/api/scan/duplicates/${gid}/resolve`, { path, delete_others: deleteOthers });
    toast(deleteOthers ? t("deleted") : t("saveOk"));
    await loadDuplicates(false);
    renderDuplicatesList();
  } catch (e) { toast(e.message); }
}

async function dupGalSetStatus(gid, status) {
  try {
    await api("POST", `/api/scan/duplicates/${gid}/${status}`);
    await loadDuplicates(false);
    renderDuplicatesList();
  } catch (e) { toast(e.message); }
}

async function renderDupGroupsFromCache() {
  if (!lastDupStatus) return;
  renderDupGroups(lastDupStatus);
  updateDupButtons();
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

// bindTagSuggest moved to events.js

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

async function testExhentai() {
  try {
    const r = await api("POST", "/api/settings/exhentai/test");
    toast(r.message || r.status);
  } catch (e) { toast(e.message); }
}

async function changePassword() {
  const form = document.querySelector('[data-action="settings-save"]');
  const current = form.querySelector('[name="current_password"]').value;
  const next = form.querySelector('[name="new_password"]').value;
  if (!next) { toast(t("newPassword")); return; }
  try {
    await api("POST", "/api/auth/change-password", { current, new: next });
    app.session.must_change_password = false;
    toast(t("changePwOk"));
    updateBanner();
  } catch (e) { toast(e.message); }
}

function welcomeInputs() {
  const form = document.querySelector(".welcome .wizard");
  const v = n => { const el = form && form.querySelector(`[name="${n}"]`); return el ? el.value.trim() : ""; };
  return { v, form };
}

async function welcomeChangePassword() {
  const { v } = welcomeInputs();
  const current = v("current_password");
  const next = v("new_password");
  if (!next) { toast(t("newPassword")); return; }
  try {
    await api("POST", "/api/auth/change-password", { current, new: next });
    app.session.must_change_password = false;
    toast(t("changePwOk"));
    updateBanner();
    renderWelcome();
  } catch (e) { toast(e.message); }
}

async function welcomeSaveCookie() {
  const { v } = welcomeInputs();
  const baseSel = v("w_exhentai_base_url");
  const body = {
    exhentai_base_url: baseSel === EH_CUSTOM
      ? (v("w_exhentai_base_url_custom") || "https://exhentai.org")
      : baseSel,
  };
  for (const k of ["ipb_member_id", "ipb_pass_hash", "igneous"]) {
    if (v("w_" + k)) body[k] = v("w_" + k);
  }
  try {
    await api("POST", "/api/settings", body);
    app.settings = null;
    toast(t("saveOk"));
    renderWelcome();
  } catch (e) { toast(e.message); }
}

async function scanLibrary() {
  try {
    await api("POST", "/api/scan");
    toast(t("scanning"));
    pollLogs();
  } catch (e) { toast(e.message); }
}

function welcomeScan() { return scanLibrary(); }

async function welcomeFinish() {
  try {
    const st = await api("GET", "/api/onboarding/status");
    if (st.password_default) { toast(t("welcomePasswordTitle")); return; }
  } catch (_) { /* fall through */ }
  toast(t("welcomeDone"));
  location.hash = "#/browse";
}

function welcomeLater() { location.hash = "#/browse"; }

async function testTelegram() {
  try {
    const r = await api("POST", "/api/telegram/test");
    toast(r.ok ? t("testTelegram") + " OK" : JSON.stringify(r.results));
  } catch (e) { toast(e.message); }
}

async function forceUpdate() {
  try {
    const r = await api("POST", "/api/tags/search/reload");
    const el = document.getElementById("trans-status");
    if (el) el.textContent = r.ok ? t("transUpdated") : (r.last_error || "?");
    toast(t("forceUpdate") + (r.ok ? " OK" : " :: " + (r.last_error || "?")));
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function generateThumbnails() {
  try {
    const r = await api("POST", "/api/thumbs/generate");
    toast(t("genThumbs") + (r && r.queued ? ` (${r.queued})` : ""));
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function syncAllTags() {
  try {
    const r = await api("POST", "/api/tag-sync/start");
    toast(t("syncAllTags") + (r && r.queued ? ` (${r.queued})` : ""));
    pollLogs();
  } catch (e) { toast(e.message); }
}

async function syncTags(id) {
  try {
    const r = await api("POST", `/api/galleries/${id}/sync-tags`);
    toast((r && r.source === "cache") ? t("tagSyncFromCache") : t("tagSyncFromNetwork") + (r ? ` · ${r.count}` : ""));
  }
  catch (e) { toast(e.message); }
}

async function saveSettings(form) {
  try {
    const data = await api("POST", "/api/settings", collectSettings(form));
    app.settings = data && data.library_roots !== undefined ? data : null;
    toast(t("saveOk"));
    renderSettings();
  } catch (e) { toast(e.message); }
}

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
