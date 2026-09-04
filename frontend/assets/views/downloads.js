"use strict";

// views/downloads.js — Phase 1 continue
// renderDownloads + dl helpers + actions consolidated here for slimming app.js

async function renderDownloads() {
  const filter = app.query.filter || "all";
  // Fetch pause status and GP in background
  let pauseInfo = null;
  try { pauseInfo = await api("GET", "/api/pause"); } catch (_) {}
  const isPaused = !!(pauseInfo && pauseInfo.paused);
  renderView(`
    <header><p class="eyebrow">DOWNLOADS</p><h1>${esc(t("downloads"))}</h1>
    <p class="sub">${esc(t("downloadsSub"))}</p></header>
    <div class="toolbar" style="margin-bottom:12px;gap:8px;flex-wrap:wrap;">
      <button class="btn ${isPaused ? "btn-primary" : "btn-secondary"}" data-action="toggle-pause" type="button" title="${esc(t("pauseHint"))}">${esc(isPaused ? t("resume") : t("pause"))} ${isPaused ? "▶" : "⏸"}</button>
      <span id="gp-display" class="muted" style="font-size:13px;">${esc(t("gpTitle"))}: …</span>
      <span id="quota-display" class="muted" style="font-size:13px;"></span>
      ${isPaused ? `<span class="badge" style="background:var(--warning, #ff9800);color:#000;padding:4px 8px;border-radius:4px;font-weight:600;">${esc(t("paused"))}</span>` : ""}
    </div>
    <div class="dl-add-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px;">
        <strong style="font-size:14px;">${esc(t("dlAddTitle"))}</strong>
        <span class="muted" style="font-size:12px;">${esc(t("dlAddHint"))}</span>
      </div>
      <form data-action="dl-add-urls" style="display:flex;flex-direction:column;gap:8px;">
        <textarea id="dl-urls-input" rows="2" placeholder="${esc(t("dlAddPlaceholder"))}"></textarea>
        <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;flex-wrap:wrap;">
          <select id="dl-urls-quality" class="select" style="font-size:13px;padding:6px 10px;">
            <option value="">${esc(t("dlDefaultQuality"))}</option>
            <option value="resample">${esc(t("qualityResample"))}</option>
            <option value="original">${esc(t("qualityOriginal"))}</option>
          </select>
          <button class="btn btn-primary" type="submit" style="padding:6px 14px;">${esc(t("dlAddSubmit"))}</button>
          <button class="btn btn-secondary" data-action="dl-add-archive" type="button" style="padding:6px 14px;">${esc(t("dlAddArchive"))}</button>
        </div>
      </form>
    </div>
    <h2>${esc(t("dlTasks"))}</h2>
    <div class="toolbar">
      <div class="pills" style="margin:0">
        ${DL_STATUSES.map(s => `<a class="pill${s === filter ? " active" : ""}" href="${navHash("downloads", {}, s !== "all" ? { filter: s } : {})}">${esc(s === "all" ? t("filterAll") : s)}</a>`).join("")}
      </div>
      <button class="secondary" data-action="dl-select-all" type="button">${esc(t("selectAll"))}</button>
      <button class="primary" data-action="dl-retry-selected" type="button">${esc(t("retrySelected"))}</button>
      <button class="secondary danger" data-action="dl-delete-selected" type="button">${esc(t("deleteSel"))}</button>
      <button class="secondary danger" data-action="dl-clear-success" type="button">${esc(t("clearSuccessDl"))}</button>
    </div>
    <div id="dl-list"><p>${esc(t("loading"))}</p></div>
    <div class="pages" id="dl-pages"></div>`);
  loadDownloads(filter, app.query.page || "1");
  loadQuota();
  if (dlTimer) clearInterval(dlTimer);
  dlTimer = setInterval(() => {
    if (location.hash.startsWith("#/downloads")) loadDownloads(filter, app.query.page || "1");
  }, 2000);
}

async function loadQuota() {
  const gpEl = document.getElementById("gp-display");
  const quotaEl = document.getElementById("quota-display");
  if (!gpEl) return;
  try {
    const data = await api("GET", "/api/quota");
    const gp = data.gp != null ? `${data.gp} GP` : "—";
    const at = data.checked_at ? fmtDateTime(data.checked_at) : "";
    gpEl.textContent = `${t("gpTitle")}: ${gp}${at ? ` (${at})` : ""}` + (data.cached ? " · cached" : "");
    if (quotaEl) {
      const lim = data.image_limit || data.image_limits || null;
      let limText = "";
      if (lim && lim.current != null && lim.limit) {
        limText = ` · ${t("imageLimitTitle")}: ${lim.current}/${lim.limit}`;
        // Near limit warning (>80%) – also push to top banner with dedicated quota copy
        try {
          if (lim.limit > 0 && lim.current / lim.limit > 0.8) {
            const near = t("quotaNearLimit");
            const hint = (near && near !== "quotaNearLimit")
              ? near.replace("{current}", lim.current).replace("{limit}", lim.limit)
              : (t("quotaWarningHint") && t("quotaWarningHint") !== "quotaWarningHint")
                ? t("quotaWarningHint").replace("{current}", lim.current).replace("{limit}", lim.limit)
                : `${t("quotaWarning") || t("imageLimitTitle")}: ${lim.current}/${lim.limit}`;
            app.session.quota_warning = hint;
            updateBanner();
          } else if (app.session && app.session.quota_warning) {
            delete app.session.quota_warning;
            updateBanner();
          }
        } catch (_) {}
      }
      if (data.error) quotaEl.textContent = limText + ` · ${data.error}`;
      else quotaEl.textContent = limText;
    }
  } catch (_) {
    gpEl.textContent = `${t("gpTitle")}: —`;
  }
}

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
  const err = dlErrorText(x.error_message);
  return `<span class="row-meta">${esc(x.status)}${total ? ` · ${cur}/${total}` : ""}${x.retry_count ? ` · retry ${x.retry_count}` : ""}${err ? ` · ${esc(t("error"))}: ${esc(err)}` : ""}</span>`;
}

function dlErrorText(msg) {
  if (!msg) return "";
  const lower = String(msg).toLowerCase();
  if (lower.includes("gallerygoneerror") || lower.includes("deleted or not found") || lower.includes("does not exist on exhentai")) {
    return t("dlGone");
  }
  return msg;
}

function parseDlItems(rawText) {
  const lines = String(rawText || "").split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const compact = line.match(/^(\d+)[\s/]+([a-f0-9]+)$/i);
    if (compact) {
      items.push({ gid: parseInt(compact[1], 10), token: compact[2] });
      continue;
    }
    const href = line.match(/\/g\/(\d+)\/([A-Za-z0-9]+)/);
    if (href) {
      items.push({ gid: parseInt(href[1], 10), token: href[2] });
      continue;
    }
  }
  return items;
}

function toastDlBatch(data, extraFailed) {
  const queued = (data && data.queued) || 0;
  const skipped = (data && data.skipped) || 0;
  const gone = (data && data.gone) || 0;
  const updated = (data && data.updated) || 0;
  const failed = ((data && data.failed) || 0) + (extraFailed || 0);
  const msgParts = [];
  if (queued) msgParts.push(t("dlQueuedCount").replace("{count}", String(queued)));
  if (updated) msgParts.push(t("dlUpdatedCount").replace("{count}", String(updated)));
  if (gone) msgParts.push(t("dlGoneCount").replace("{count}", String(gone)));
  if (skipped) msgParts.push(t("dlSkippedCount").replace("{count}", String(skipped)));
  if (failed) msgParts.push(t("dlFailedCount").replace("{count}", String(failed)));
  toast(msgParts.join(" · ") || t("dlAddEmpty"));
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
        const badge = (isArchive && !x.archive_fallback)
          ? `<span class="badge dl-badge">${esc(t("dlBadgeArchive"))} · ${esc(x.quality === "original" ? t("archiveTierOriginal") : t("archiveTierResample"))}</span>`
          : (isArchive && x.archive_fallback)
          ? `<span class="badge dl-badge">${esc(t("dlBadgeArchiveFallback"))}</span>`
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
      pages.push(p === data.page ? `<strong class="cur" aria-current="page">${p}</strong>` : `<a class="page-link" href="${qp(p)}">${p}</a>`);
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

async function clearSuccessDownloads() {
  let total = 0;
  try {
    const data = await api("GET", "/api/downloads?page=1&page_size=1&status=success");
    total = (data && data.total) || 0;
  } catch (e) { toast(e.message); return; }
  if (!total) { toast(t("noTasks")); return; }
  if (!window.confirm(t("confirmClearSuccessDl") + " (" + total + ")")) return;
  try {
    const res = await api("POST", "/api/downloads/clear-success");
    toast(t("clearedSuccessDl").replace("{count}", String((res && res.deleted) || 0)));
    loadDownloads(app.query.filter || "all", app.query.page || "1");
  } catch (e) { toast(e.message); }
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

async function addDownloadsFromInput(form) {
  const textarea = form.querySelector("#dl-urls-input") || document.getElementById("dl-urls-input");
  const qualitySelect = form.querySelector("#dl-urls-quality") || document.getElementById("dl-urls-quality");
  const items = parseDlItems((textarea && textarea.value) || "");
  if (!items.length) {
    toast(t("dlAddEmpty"));
    return;
  }
  const quality = (qualitySelect && qualitySelect.value) || undefined;
  const submitBtn = form.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.disabled = true;
  const body = { items };
  if (quality) body.quality = quality;
  try {
    const data = await api("POST", "/api/downloads/batch", body);
    if (textarea) textarea.value = "";
    toastDlBatch(data);
  } catch (e) {
    toast(e.message || t("dlFailedCount").replace("{count}", "1"));
  }
  if (submitBtn) submitBtn.disabled = false;
  loadDownloads(app.query.filter || "all", app.query.page || "1");
}

async function addArchiveFromInput() {
  const textarea = document.getElementById("dl-urls-input");
  const items = parseDlItems((textarea && textarea.value) || "");
  const resolved = items.filter(it => it.gid && it.token);
  if (!resolved.length) {
    toast(t("dlAddEmpty"));
    return;
  }
  const gids = resolved.map(it => it.gid);
  const tier = await showArchiveDialog(gids, { items: resolved });
  if (!tier) return;
  try {
    const data = await api("POST", "/api/downloads/batch", {
      items: resolved,
      mode: "archive",
      quality: tier,
    });
    if (textarea) textarea.value = "";
    toastDlBatch(data);
  } catch (e) {
    toast(e.message || t("archivePreviewFail"));
  }
  loadDownloads(app.query.filter || "all", app.query.page || "1");
}
