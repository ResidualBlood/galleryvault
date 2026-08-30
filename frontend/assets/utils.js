"use strict";

// utils.js — 工具函数 (fmt* / parse* / nsClass / cloudSize / pager / libraryContext 等)
// 按 Phase 0 拆分，保持函数名不变（全局）

function nsClass(ns) {
  return "nst-" + (ns && ["artist","character","parody","group","language","category","female","male","mixed","other","misc"].includes(ns) ? ns : "misc");
}

function stopInfinite() {
  if (infiniteState && infiniteState.observer) infiniteState.observer.disconnect();
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
  const observer = new IntersectionObserver(async (entries) => {
    if (finished || loading) return;
    if (!(entries[0] && entries[0].isIntersecting)) return;
    loading = true;
    try {
      const data = await fetchPage(page + 1);
      const items = (data && data.items) || [];
      if (!items.length) { finished = true; sentinel.remove(); return; }
      page = data.page || (page + 1);
      sentinel.insertAdjacentHTML("beforebegin", items.map(buildItem).join(""));
      if ((data.page * (data.page_size || 24)) >= (data.total || 0)) {
        finished = true;
        sentinel.remove();
      }
      if (containerId === "lib-grid") {
        renderCardCheckboxes();
      }
    } catch (_) { finished = true; sentinel.remove(); }
    finally { loading = false; }
  }, { rootMargin: "900px" });
  observer.observe(sentinel);
  infiniteState = { observer };
}

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
  const cur = parseTags(app.query.tags || "");
  if (!cur.includes(key)) cur.push(key);
  return tagFilterHash(cur);
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
