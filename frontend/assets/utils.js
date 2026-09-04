"use strict";

// utils.js — 工具函数 (fmt* / parse* / nsClass / cloudSize / pager / libraryContext 等)
// 按 Phase 0 拆分，保持函数名不变（全局）

function nsClass(ns) {
  return "nst-" + (ns && ["artist","character","parody","group","language","category","female","male","mixed","other","misc"].includes(ns) ? ns : "misc");
}

function stopInfinite() {
  if (infiniteState) {
    try { infiniteState.observer && infiniteState.observer.disconnect(); } catch (_) {}
    try { infiniteState.controller && infiniteState.controller.abort(); } catch (_) {}
    try { infiniteState.sentinel && infiniteState.sentinel.parentNode && infiniteState.sentinel.remove(); } catch (_) {}
  }
  infiniteState = null;
}

function startInfinite(containerId, fetchPage, buildItem) {
  stopInfinite();
  const container = document.getElementById(containerId);
  if (!container) return;
  const grid = container.querySelector(".grid.gc-grid");
  if (!grid) return;
  let page = parseInt((app.query.page || "1"), 10) || 1;
  let loading = false;
  let finished = false;
  const sentinel = document.createElement("div");
  sentinel.className = "inf-scroll-sentinel";
  grid.appendChild(sentinel);
  const controller = new AbortController();
  const observer = new IntersectionObserver(async (entries) => {
    if (finished || loading) return;
    if (!(entries[0] && entries[0].isIntersecting)) return;
    if (controller.signal.aborted) return;
    loading = true;
    try {
      const data = await fetchPage(page + 1);
      if (controller.signal.aborted) return;
      // Route may have changed while fetching — abort append to detached DOM
      if (!document.contains(grid) || !document.contains(sentinel)) { finished = true; return; }
      const items = (data && data.items) || [];
      if (!items.length) { finished = true; try{observer.disconnect();}catch(_){} sentinel.remove(); return; }
      page = data.page || (page + 1);
      sentinel.insertAdjacentHTML("beforebegin", items.map(buildItem).join(""));
      if ((data.page * (data.page_size || 24)) >= (data.total || 0)) {
        finished = true;
        try{observer.disconnect();}catch(_){}
        sentinel.remove();
      }
      if (["lib-grid", "fav-items", "browse-grid"].includes(containerId)) {
        renderCardCheckboxes();
      }
    } catch (_) {
      if (controller.signal.aborted) return;
      finished = true; try{observer.disconnect();}catch(_){} sentinel.remove();
    }
    finally { loading = false; }
  }, { rootMargin: "900px" });
  observer.observe(sentinel);
  infiniteState = { observer, controller, sentinel };
}

function pageSizeSelect(current, view) {
  const opts = [...PAGE_SIZES];
  if (!opts.some(n => String(n) === String(current))) opts.push(parseInt(current, 10));
  return `<select class="page-size" data-action="page-size" data-view="${view}" aria-label="page size">
    ${opts.map(n => `<option value="${n}"${String(n) === String(current) ? " selected" : ""}>${n}</option>`).join("")}
  </select>`;
}

function jumpPage(input, last) {
  const cur = parseInt(input.getAttribute("data-current") || input.defaultValue, 10) || 1;
  const p = Math.max(1, Math.min(parseInt(input.value, 10) || 1, last));
  input.value = p;
  if (p === cur) return;
  input.setAttribute("data-current", String(p));
  if (app.view === "favmanage" || app.view === "favignored") {
    dupPage = p;
    renderDupGroupsFromCache();
    return;
  }
  location.hash = navHash(app.view, app.params, { ...app.query, page: String(p) });
}

function pagerJump(page, last) {
  return `<span class="page-jump-wrap">
    <input class="page-jump" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" min="1" max="${last}" value="${page}" data-current="${page}" aria-label="page">
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
    parts.push(p === data.page ? `<strong class="cur" aria-current="page">${p}</strong>` : link(p, String(p)));
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
  const clamp = n => Math.max(1, Math.min(500, n));
  const fromUrl = parseInt(app.query.page_size, 10);
  if (fromUrl > 0) return clamp(fromUrl);
  const saved = parseInt(localStorage.getItem("gv_page_size") || "", 10);
  if (saved > 0) return clamp(saved);
  return clamp(fallback);
}

function libraryContext() {
  const c = {};
  for (const k of ["q", "tags", "tag_mode", "tag_match", "category", "order_by", "read_status", "min_rating", "page_min", "page_max", "min_pages", "max_pages", "page_size", "size_min", "size_max", "posted_from", "posted_to", "uploader", "image_quality", "min_local_rating", "list_id"]) {
    if (app.query[k]) c[k] = app.query[k];
  }
  return c;
}

function tagFilterHash(tagsArr) {
  const query = { tag_mode: "and" };
  if (app.query.q) query.q = app.query.q;
  if (app.query.category) query.category = app.query.category;
  if (app.query.order_by) query.order_by = app.query.order_by;
  if (app.query.read_status) query.read_status = app.query.read_status;
  if (app.query.tag_match) query.tag_match = app.query.tag_match;
  if (app.query.tag_mode && app.query.tag_mode !== "and") query.tag_mode = app.query.tag_mode;
  if (app.query.min_rating) query.min_rating = app.query.min_rating;
  if (app.query.page_min) query.page_min = app.query.page_min;
  if (app.query.page_max) query.page_max = app.query.page_max;
  if (app.query.min_pages) query.min_pages = app.query.min_pages;
  if (app.query.max_pages) query.max_pages = app.query.max_pages;
  if (app.query.size_min) query.size_min = app.query.size_min;
  if (app.query.size_max) query.size_max = app.query.size_max;
  if (app.query.posted_from) query.posted_from = app.query.posted_from;
  if (app.query.posted_to) query.posted_to = app.query.posted_to;
  if (app.query.uploader) query.uploader = app.query.uploader;
  if (app.query.image_quality) query.image_quality = app.query.image_quality;
  if (app.query.min_local_rating) query.min_local_rating = app.query.min_local_rating;
  if (app.query.list_id) query.list_id = app.query.list_id;
  if (app.view === "favlist" && app.query.state) query.state = app.query.state;
  // preserve hash-level page reset: filter changes always go to page 1 (no page param)
  if (tagsArr && tagsArr.length) query.tags = tagsArr.join(",");
  if (app.view === "favlist") {
    return navHash("favlist", { id: app.params.id }, query);
  }
  return navHash("library", {}, query);
}

function addTagHash(ns, name) {
  const key = ns ? `${ns}:${name}` : name;
  const cur = parseTags(app.query.tags || "");
  if (!cur.includes(key)) {
    // if an exclude version exists, replace it with include
    const exKey = `-${key}`;
    const idx = cur.indexOf(exKey);
    if (idx !== -1) cur.splice(idx, 1);
    cur.push(key);
  }
  return tagFilterHash(cur);
}

function removeTagHash(tag) {
  const cur = parseTags(app.query.tags || "").filter(t => t !== tag);
  return tagFilterHash(cur);
}

function addExcludeTagHash(ns, name) {
  const key = ns ? `${ns}:${name}` : name;
  const exKey = `-${key}`;
  let cur = parseTags(app.query.tags || "");
  // If already excluded, no-op; if included, replace include with exclude
  if (cur.includes(exKey)) return tagFilterHash(cur);
  cur = cur.filter(t => t !== key);
  cur.push(exKey);
  return tagFilterHash(cur);
}

function tagFilterPills(tags) {
  const arr = parseTags(tags);
  if (!arr.length) return "";
  const tagMode = (app.query && app.query.tag_mode === "or") ? "OR" : "AND";
  const pills = arr.map(t => {
    const isExclude = t.startsWith("-");
    const displayTag = isExclude ? t.slice(1) : t;
    const cls = isExclude ? "tag tag-exclude" : "tag";
    const label = isExclude ? `- ${displayTag}` : displayTag;
    return `<span class="${cls}" title="${esc(t)}">${esc(label)} <a class="tag-x" data-action="remove-tag" data-tag="${esc(t)}" href="#">×</a></span>`;
  }).join("");
  return `<a class="mode pill" data-action="toggle-tag-mode" href="#" title="Toggle AND/OR" style="cursor:pointer;font-weight:700;">${tagMode}</a>${pills} <a class="clear-all" data-action="clear-tag" href="#">${esc(t("clearAll"))}</a>`;
}

function cloudSizeClass(count, max) {
  if (!count) return "s1";
  const ratio = max > 0 ? Math.log(count + 1) / Math.log(max + 1) : 0;
  if (ratio > 0.8) return "s5";
  if (ratio > 0.55) return "s4";
  if (ratio > 0.3) return "s3";
  if (ratio > 0.1) return "s2";
  return "s1";
}

function fmtDur(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60), rem = s % 60;
  if (m < 60) return m + "m" + (rem ? " " + rem + "s" : "");
  const h = Math.floor(m / 60), rm = m % 60;
  return h + "h" + (rm ? " " + rm + "m" : "");
}

function fmtSize(bytes) {
  if (!bytes || bytes < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (v >= 100 ? v.toFixed(0) : v.toFixed(1)) + " " + units[i];
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fmtDuration(startIso, endIso) {
  if (!startIso || !endIso) return "";
  const ms = new Date(endIso) - new Date(startIso);
  if (!isFinite(ms) || ms < 0) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), rem = s % 60;
  return m < 60 ? `${m}m ${rem}s` : `${Math.floor(m / 60)}h ${m % 60}m ${rem}s`;
}

function catLabel(c) {
  if (!c) return "";
  const key = (typeof CATEGORY_LABELS !== "undefined" && CATEGORY_LABELS[c]) || c;
  return t(key) || c;
}

async function galleryGrid(container, page, extraQuery) {
  const rawSize = extraQuery && extraQuery.page_size ? extraQuery.page_size : prefPageSize();
  const pageSize = Math.max(1, Math.min(500, parseInt(rawSize, 10) || 24));
  const q = Object.assign({ page, page_size: pageSize }, extraQuery || {});
  q.page_size = pageSize;
  const qs = Object.entries(q).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
  let data;
  try {
    data = await api("GET", `/api/galleries?${qs}`);
  } catch (e) {
    // 422 from bad page_size should not white-screen; clamp and retry once
    if (String(e.message).includes("422") && pageSize !== 24) {
      q.page_size = 24;
      const retryQs = Object.entries(q).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
      data = await api("GET", `/api/galleries?${retryQs}`);
    } else {
      throw e;
    }
  }
  // cache for batch operations (id -> {gid, token, title})
  if (data && Array.isArray(data.items)) {
    app._libCache = app._libCache || new Map();
    for (const it of data.items) {
      if (it && it.id != null) app._libCache.set(Number(it.id), { gid: it.gid, token: it.token, title: it.title });
    }
  }
  if (container == null) return data;
  const el = document.getElementById(container);
  if (!el) return data;
  if (!document.contains(el)) return data;
  if (!data.items.length) { el.innerHTML = renderEmpty(t("noGalleries")); }
  else { el.innerHTML = `<div class="grid gc-grid">` + data.items.map(galleryCard).join("") + `</div>`; }
  return data;
}
