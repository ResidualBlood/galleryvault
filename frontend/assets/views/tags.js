"use strict";

// views/tags.js — Phase 1 continue
// tag helpers + renderTags + load* moved from app.js

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
