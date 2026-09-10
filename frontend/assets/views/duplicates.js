"use strict";

// views/duplicates.js — Phase 1 continue (favmanage + dup groups)
// extracted renderFavManage, runDupScan, renderDupGroups + dup helpers

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
let isPollingDupScan = false;

function setDupScanBtn(scanning) {
  const btn = document.querySelector('[data-action="dup-scan"]');
  if (btn) {
    btn.disabled = scanning;
    btn.textContent = scanning ? "扫描中..." : t("dupScan");
  }
}

async function renderFavManage() {
  await loadFavNames();
  const filterBtn = (val, label) =>
    `<button class="secondary${dupFilter === val ? " active-pill" : ""}" data-action="dup-filter" data-value="${val}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <header><p class="eyebrow">DUPLICATES</p><h1>${esc(t("dupFavTitle"))}</h1>
    <p class="sub">${esc(t("dupFavSub"))}</p></header>
    ${manageTabsHtml("dupfav")}
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

  if (isPollingDupScan || (lastDupStatus && lastDupStatus.running)) {
    setDupScanBtn(true);
    const bar = document.getElementById("dup-progress");
    if (bar) bar.hidden = false;
    if (!isPollingDupScan) {
      runDupScan(true);
    }
  } else if (lastDupStatus) {
    if (lastDupStatus.last_error) {
      const gEl = document.getElementById("dup-groups");
      if (gEl) gEl.innerHTML = `<p class="error">${esc(lastDupStatus.last_error)}</p>`;
    } else if (lastDupStatus.groups) {
      renderDupGroups(lastDupStatus);
      renderCardCheckboxes();
      updateDupButtons();
    }
  } else {
    try {
      const st = await api("GET", "/api/favorites/duplicates/status");
      if (st) {
        if (st.running) {
          lastDupStatus = st;
          setDupScanBtn(true);
          const bar = document.getElementById("dup-progress");
          if (bar) bar.hidden = false;
          runDupScan(true);
        } else if (st.groups && st.groups.length > 0) {
          lastDupStatus = st;
          renderDupGroups(st);
          renderCardCheckboxes();
          updateDupButtons();
        }
      }
    } catch (_) {}
  }
}

async function runDupScan(isPolling = false) {
  if (isPollingDupScan && !isPolling) return;
  const resetBtn = () => {
    isPollingDupScan = false;
    setDupScanBtn(false);
  };

  setDupScanBtn(true);

  if (!isPolling) {
    selDup.clear();
    dupPage = 1;
    dupLocallyIgnored.clear();
    const bar = document.getElementById("dup-progress");
    const groupsEl = document.getElementById("dup-groups");
    if (bar) bar.hidden = false;
    if (groupsEl) groupsEl.innerHTML = `<p>${esc(t("loading"))}</p>`;
    try {
      await api("POST", "/api/favorites/duplicates/scan");
    } catch (e) {
      const gEl = document.getElementById("dup-groups");
      if (gEl) gEl.innerHTML = `<p class="error">${esc(e.message)}</p>`;
      resetBtn();
      return;
    }
  }

  isPollingDupScan = true;
  if (!lastDupStatus) lastDupStatus = { running: true };
  else lastDupStatus.running = true;

  try {
    for (let i = 0; i < 120; i++) {
      let st;
      try {
        st = await api("GET", "/api/favorites/duplicates/status");
      } catch (e) {
        const gEl = document.getElementById("dup-groups");
        if (gEl) gEl.innerHTML = `<p class="error">${esc(e.message)}</p>`;
        resetBtn();
        return;
      }

      lastDupStatus = st;

      const bar = document.getElementById("dup-progress");
      const fill = document.getElementById("dup-progress-fill");
      const text = document.getElementById("dup-progress-text");
      const groupsEl = document.getElementById("dup-groups");
      const curBtn = document.querySelector('[data-action="dup-scan"]');
      if (curBtn && !curBtn.disabled) {
        setDupScanBtn(true);
      }

      if (bar) bar.hidden = false;
      if (st.total > 0 && fill && text) {
        const pct = Math.min(100, Math.round((st.done / st.total) * 100));
        fill.style.width = pct + "%";
        text.textContent = `${esc(st.stage || "")} ${st.done}/${st.total}`;
      }

      if (!st.running) {
        if (fill) fill.style.width = "100%";
        if (st.last_error) {
          if (groupsEl) groupsEl.innerHTML = `<p class="error">${esc(st.last_error)}</p>`;
          resetBtn();
          return;
        }
        renderDupGroups(st);
        renderCardCheckboxes();
        updateDupButtons();
        if (bar) bar.hidden = true;
        resetBtn();
        return;
      }
      await new Promise(r => setTimeout(r, 300));
    }

    const groupsEl = document.getElementById("dup-groups");
    if (groupsEl) groupsEl.innerHTML = `<p class="muted">${esc(t("loading"))}</p>`;
  } finally {
    resetBtn();
  }
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
                  ${it.gallery_id != null ? `<a class="badge dup-badge-local" href="${navHash("gallery", { id: it.gallery_id }, { from: currentFromPath() })}">${esc(t("favLocal"))}</a>` : `<span class="badge dup-badge-cloud">${esc(t("favCloud"))}</span>`}
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
      ? `<strong class="cur" aria-current="page">${p}</strong>`
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
  renderDuplicatesList();
  return true;
}

function renderDuplicatesList() {
  document.querySelectorAll('[data-action="dupgal-filter"]').forEach(b => {
    b.classList.toggle("active-pill", b.getAttribute("data-value") === dupGalFilter);
  });
  const el = document.getElementById("dupgal-groups");
  if (!el) return;
  const groups = (dupGalCache || []).filter(g => dupGalFilter === "all" || g.status === dupGalFilter);
  if (!groups.length) {
    const noneKey = dupGalFilter === "open" ? "dupGalNoneOpen" : dupGalFilter === "dismissed" ? "dupGalNoneDismissed" : "dupGalNone";
    el.innerHTML = `<p class="muted">${esc(t(noneKey))}</p>`;
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
    ${manageTabsHtml("duplicates")}
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

// --- Cross-GID duplicates (library + cloud favorites) ---------------------

function updateXgidButtons() {
  document.querySelectorAll('[data-action="dupxgid-unfav"], [data-action="dupxgid-unfav-delete"]').forEach(b => {
    const act = b.getAttribute("data-action");
    const base = act === "dupxgid-unfav" ? t("dupUnfav") : t("dupUnfavDelete");
    b.textContent = base + (selXgid.size ? ` (${selXgid.size})` : "");
  });
  document.querySelectorAll('[data-action="dupxgid-ignore-selected"]').forEach(b => {
    b.textContent = t("dupIgnoreSel") + (selXgid.size ? ` (${selXgid.size})` : "");
  });
}

function applyCrossGidFilter(groups) {
  if (dupXgidFilter === "all") return groups;
  return groups
    .map(g => ({
      ...g,
      items: (g.items || []).filter(it => {
        const isLocal = it.gallery_id != null;
        return dupXgidFilter === "local" ? isLocal : !isLocal;
      }),
    }))
    .filter(g => g.items.length >= 1);
}

async function renderCrossGidDuplicates() {
  const filterBtn = (val, label) =>
    `<button class="secondary${dupXgidFilter === val ? " active-pill" : ""}" data-action="dupxgid-filter" data-value="${val}" type="button">${esc(label)}</button>`;
  $view().innerHTML = `
    <header><p class="eyebrow">DUPLICATES</p><h1>${esc(t("dupXgidTitle"))}</h1>
    <p class="sub">${esc(t("dupXgidSub"))}</p></header>
    ${manageTabsHtml("dupxgid")}
    <div class="toolbar">
      <button class="primary" data-action="dupxgid-recompute" type="button">${esc(t("dupXgidRecompute"))}</button>
      <button class="secondary" data-action="dupxgid-refresh" type="button">${esc(t("dupXgidRefresh"))}</button>
      ${filterBtn("all", t("dupFilterAll"))}
      ${filterBtn("local", t("dupFilterLocal"))}
      ${filterBtn("cloud", t("dupFilterCloud"))}
      <button class="secondary danger" data-action="dupxgid-unfav" type="button">${esc(t("dupUnfav"))}${selXgid.size ? ` (${selXgid.size})` : ""}</button>
      <button class="secondary danger" data-action="dupxgid-unfav-delete" type="button">${esc(t("dupUnfavDelete"))}${selXgid.size ? ` (${selXgid.size})` : ""}</button>
      <button class="secondary" data-action="dupxgid-ignore-selected" type="button">${esc(t("dupIgnoreSel"))}${selXgid.size ? ` (${selXgid.size})` : ""}</button>
      <button class="secondary" data-action="dupxgid-clear" type="button">${esc(t("clearSel"))}</button>
      <a class="secondary" href="#/favorites/ignored" style="padding:8px 14px;border-radius:4px;margin-left:auto">${esc(t("dupIgnoredPage"))}</a>
    </div>
    <details class="panel" style="margin:12px 0 14px;padding:10px 14px;font-size:13px;border:1px solid var(--line);border-radius:6px;">
      <summary style="cursor:pointer;font-weight:600;color:var(--text);">${esc(t("dupXgidInfoSummary"))}</summary>
      ${t("dupXgidInfoDetail")}
    </details>
    <div id="dupxgid-groups"><p class="muted">${esc(t("loading"))}</p></div>`;
  if (dupXgidCache === null || !dupXgidReady) {
    await loadCrossGidDuplicates();
  } else {
    renderCrossGidList();
  }
}

async function loadCrossGidDuplicates(showLoading = true) {
  const el = document.getElementById("dupxgid-groups");
  if (showLoading && el) el.innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    const data = await api("GET", "/api/library/duplicates/cross-gid");
    dupXgidReady = !!(data && data.ready);
    dupXgidCache = (data && data.groups) || [];
  } catch (e) {
    if (el) el.innerHTML = `<p class="error">${esc(e.message)}</p>`;
    return;
  }
  renderCrossGidList();
}

async function recomputeCrossGidDuplicates() {
  const btn = document.querySelector('[data-action="dupxgid-recompute"]');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = `${t("dupXgidRecompute")}…`;
  }
  const el = document.getElementById("dupxgid-groups");
  if (el) el.innerHTML = `<p>${esc(t("loading"))}</p>`;
  try {
    const data = await api("POST", "/api/library/duplicates/cross-gid/refresh");
    dupXgidReady = !!(data && data.ready);
    dupXgidCache = (data && data.groups) || [];
    dupXgidPage = 1;
    selXgid.clear();
  } catch (e) {
    if (el) el.innerHTML = `<p class="error">${esc(e.message)}</p>`;
    return;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = t("dupXgidRecompute");
    }
  }
  renderCrossGidList();
}

function renderCrossGidList() {
  const el = document.getElementById("dupxgid-groups");
  if (!el) return;

  document.querySelectorAll('[data-action="dupxgid-filter"]').forEach(b => {
    b.classList.toggle("active-pill", b.getAttribute("data-value") === dupXgidFilter);
  });

  if (!dupXgidReady) {
    el.innerHTML = `<p class="muted">${esc(t("dupXgidHint"))}</p>`;
    return;
  }

  const rawGroups = dupXgidCache || [];
  const groups = applyCrossGidFilter(rawGroups);
  if (!groups.length) {
    el.innerHTML = `<p class="muted">${esc(t("dupXgidNone"))}</p>`;
    return;
  }

  const perPage = 24;
  const totalPages = Math.max(1, Math.ceil(groups.length / perPage));
  const page = Math.max(1, Math.min(dupXgidPage, totalPages));
  const slice = groups.slice((page - 1) * perPage, page * perPage);

  const renderGroup = (g, gi) => {
    const hidden = dupXgidLocallyIgnored.has(g.key);
    const firstItem = (g.items && g.items[0]) || {};
    const mainTitle = firstItem.display_title || firstItem.title || g.key;
    const mainTitleHtml = firstItem.gallery_id != null
      ? `<a class="dup-main-title" href="${navHash("gallery", { id: firstItem.gallery_id }, { from: currentFromPath() })}">${esc(mainTitle)}</a>`
      : (firstItem.url
        ? `<a class="dup-main-title" href="${esc(firstItem.url)}" target="_blank" rel="noopener">${esc(mainTitle)}</a>`
        : `<span class="dup-main-title">${esc(mainTitle)}</span>`);

    return `
      <div class="panel dup-group ${hidden ? "dup-hidden" : ""}" style="margin-top:14px">
        <div class="dup-group-head">
          <span class="dup-count">${esc(g.items.length)} ×</span>
          ${mainTitleHtml}
          ${g.artist ? `<span class="dup-artist">${esc(g.artist)}</span>` : ""}
          ${hidden ? `<span class="badge dup-ignored-badge">${esc(t("dupIgnored"))}</span>` : ""}
          <span class="dup-head-actions">
            <button class="secondary" data-action="dupxgid-group-sel" data-gi="${gi}" type="button">${esc(t("select"))}</button>
            <button class="secondary" data-action="dupxgid-group-toggle" onclick="this.closest('.dup-group').querySelectorAll('.dup-row').forEach(r => r.style.display = r.style.display === 'none' ? '' : 'none')" type="button" title="${esc(t("collapse"))}">⇕</button>
          </span>
        </div>
        ${g.items.map((it, ii) => {
          const isLocal = it.gallery_id != null;
          const titleText = it.display_title || it.title || (it.gid ? `gid ${it.gid}` : "");
          const titleHtml = isLocal
            ? `<a href="${navHash("gallery", { id: it.gallery_id }, { from: currentFromPath() })}">${esc(titleText)}</a>`
            : (it.url
              ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(titleText)}</a>`
              : `<span>${esc(titleText)}</span>`);
          const badgeHtml = isLocal
            ? `<a class="badge dup-badge-local" href="${navHash("gallery", { id: it.gallery_id }, { from: currentFromPath() })}">${esc(t("favLocal"))}</a>`
            : `<span class="badge dup-badge-cloud">${esc(t("favCloud"))}</span>`;
          const thumbSrc = isLocal
            ? `/api/galleries/${it.gallery_id}/thumb/0`
            : (it.cover_url || it.cover_data || null);
          const thumbHtml = thumbSrc
            ? `<img class="dup-thumb" loading="lazy" src="${thumbSrc}" alt="">`
            : `<span class="dup-thumb dup-thumb-empty"></span>`;
          const catText = it.category
            ? catLabel(it.category)
            : (it.favcat != null ? `#${it.favcat}${favCatNames[it.favcat] ? " " + favCatNames[it.favcat] : ""}` : "");
          return `
            <div class="dup-row">
              <label class="checkbox"><input type="checkbox" data-dup-gid="${it.gid}" data-key="${esc(g.key)}" data-favorited="${it.favorited ? "1" : "0"}" data-gi="${gi}" data-ii="${ii}"${selXgid.has(it.gid) ? " checked" : ""}>
                <span class="dup-thumb-wrap">${thumbHtml}</span>
                <span class="dup-body">
                  <span class="dup-title">${titleHtml}</span>
                  <span class="dup-meta">
                    ${badgeHtml}
                    <span class="badge">#${it.gid}</span>
                    ${catText ? `<span class="badge">${esc(catText)}</span>` : ""}
                    ${it.pages ? `<span class="badge">${it.pages} P</span>` : ""}
                    ${it.file_size ? `<span class="badge">${fmtSize(it.file_size)}</span>` : ""}
                    ${it.storage_type ? `<span class="badge">${esc(storageLabel(it.storage_type))}</span>` : ""}
                  </span>
                </span>
              </label>
            </div>`;
        }).join("")}
      </div>`;
  };

  const pageLinks = [];
  for (let p = Math.max(1, page - 2); p <= Math.min(totalPages, page + 2); p++) {
    pageLinks.push(p === page
      ? `<strong class="cur" aria-current="page">${p}</strong>`
      : `<a class="page-link" href="#" data-action="dupxgid-page" data-page="${p}">${p}</a>`);
  }
  const pagerHtml = groups.length > perPage
    ? `<div class="pages pager" style="margin-top:16px">${pageLinks.join(" ")} ${pagerJump(page, totalPages)}</div>`
    : "";

  el.innerHTML = `
    <p class="sub">${esc(t("dupFound"))}: ${groups.length} ${esc(t("dupGroups"))} · ${groups.reduce((n, g) => n + g.items.length, 0)} ${esc(t("dupItems"))}</p>
    ${slice.map((g, i) => renderGroup(g, (page - 1) * perPage + i)).join("")}
    ${pagerHtml}`;

  renderCardCheckboxes();
  updateXgidButtons();
}

function xgidSelectGroup(gi) {
  const filtered = dupXgidCache ? applyCrossGidFilter(dupXgidCache) : [];
  const group = filtered[gi];
  if (!group) return;
  const gids = group.items.map(it => it.gid);
  const allSel = gids.every(gid => selXgid.has(gid));
  const cbs = [...document.querySelectorAll(`#dupxgid-groups input[data-gi="${gi}"]`)];
  cbs.forEach(cb => {
    const gid = parseInt(cb.dataset.dupGid, 10);
    if (allSel) selXgid.delete(gid); else selXgid.add(gid);
    cb.checked = !allSel;
  });
  updateXgidButtons();
}

async function xgidDupAction(deleteLocal) {
  const checkedCbs = [...document.querySelectorAll('#dupxgid-groups input[data-dup-gid]:checked')];
  if (!checkedCbs.length) {
    toast(t("select"));
    return;
  }
  const favItems = checkedCbs
    .filter(cb => cb.getAttribute("data-favorited") === "1")
    .map(cb => parseInt(cb.dataset.dupGid, 10));

  if (!favItems.length) {
    toast(t("dupXgidNoFav"));
    return;
  }

  const msg = deleteLocal ? t("confirmDupDelete") : t("confirmDupUnfav");
  if (!window.confirm(msg + " " + favItems.length)) return;

  try {
    const r = await api("POST", "/api/favorites/remove", { gids: favItems, delete_local: deleteLocal });
    let toastMsg = t("unfavorited") + (r.cloud_ok ? "" : " · " + t("unfavoritedLocal"))
      + (r.deleted_local_galleries ? " · " + t("deleted") + " " + r.deleted_local_galleries : "");
    if (r.failed_deletions && r.failed_deletions.length) {
      toastMsg += " · " + t("dupDeleteFail") + r.failed_deletions.length;
      console.warn("local delete failed:", r.failed_deletions);
    }
    toast(toastMsg);
    selXgid.clear();
    if (dupXgidCache) {
      const favSet = new Set(favItems);
      const groups = Array.isArray(dupXgidCache) ? dupXgidCache : (dupXgidCache.groups || []);
      const updated = groups
        .map(g => ({
          ...g,
          items: (g.items || []).filter(it => !favSet.has(it.gid)),
        }))
        .filter(g => g.items.length > 0);
      if (Array.isArray(dupXgidCache)) {
        dupXgidCache = updated;
      } else {
        dupXgidCache.groups = updated;
      }
    }
    renderCrossGidList();
  } catch (e) {
    toast(e.message);
  }
}

async function xgidIgnoreSelected() {
  const keys = new Set();
  document.querySelectorAll('#dupxgid-groups input[data-dup-gid]:checked').forEach(cb => {
    const k = cb.getAttribute("data-key");
    if (k) keys.add(k);
  });
  if (!keys.size) { toast(t("select")); return; }
  const groupsByKey = new Map((dupXgidCache || []).map(g => [g.key, g]));
  let ok = 0;
  for (const key of keys) {
    const group = groupsByKey.get(key);
    try {
      await api("POST", "/api/favorites/duplicates/ignore", {
        key,
        title: group && group.items && group.items[0] ? group.items[0].title : "",
        gids: group && group.items ? group.items.map(it => it.gid) : [],
      });
      ok++;
    } catch (_) { /* keep going */ }
  }
  keys.forEach(k => dupXgidLocallyIgnored.add(k));
  selXgid.clear();
  toast(t("dupIgnoredOk") + ": " + ok);
  renderCrossGidList();
}
