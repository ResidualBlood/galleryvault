"use strict";

// views/logs.js — Activity & System runtime logs viewer

let currentLogsTab = "activity";
let systemLogSearch = "";
let systemLogMinLevel = "INFO";
let systemLogLevel = "INFO";
let systemLogAutoScroll = true;
let isUserScrolledUp = false;
let lastRenderedLogId = null;
let lastSearchQuery = "";
let lastMinLevel = "INFO";
const MAX_SYSLOG_DOM_NODES = 1000;

function scrollSyslogToBottom() {
  const container = document.getElementById("syslog-container");
  if (!container) return;
  container.scrollTop = container.scrollHeight;
}

function bindSyslogEvents() {
  const container = document.getElementById("syslog-container");
  if (container && !container.__gvScrollBound) {
    container.__gvScrollBound = true;
    container.addEventListener("scroll", () => {
      const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 40;
      isUserScrolledUp = !atBottom;
    });
  }

  const autoScrollToggle = document.getElementById("syslog-autoscroll");
  if (autoScrollToggle && !autoScrollToggle.__gvBound) {
    autoScrollToggle.__gvBound = true;
    autoScrollToggle.addEventListener("change", (e) => {
      systemLogAutoScroll = Boolean(e.target.checked);
      if (systemLogAutoScroll) {
        isUserScrolledUp = false;
        scrollSyslogToBottom();
      }
    });
  }
}

async function renderLogs() {
  const tab = app.query.tab || currentLogsTab;
  currentLogsTab = tab;
  lastRenderedLogId = null;
  isUserScrolledUp = false;
  lastSearchQuery = systemLogSearch;
  lastMinLevel = systemLogMinLevel;

  renderView(`
    <header>
      <p class="eyebrow">ACTIVITY & DIAGNOSTICS</p>
      <h1>${esc(t("logs"))}</h1>
      <p class="sub">${esc(t("logsSub"))}</p>
    </header>

    <div class="log-tabs">
      <button class="log-tab-btn ${currentLogsTab === "activity" ? "active" : ""}" data-action="log-tab" data-tab="activity" type="button">${esc(t("taskLogs"))}</button>
      <button class="log-tab-btn ${currentLogsTab === "system" ? "active" : ""}" data-action="log-tab" data-tab="system" type="button">${esc(t("systemLogs"))}</button>
    </div>

    <div id="log-activity-panel" style="display: ${currentLogsTab === "activity" ? "block" : "none"}">
      <section class="log-block">
        <h2>${esc(t("runningTasks"))}</h2>
        <div id="log-running"><p>${esc(t("loading"))}</p></div>
      </section>
      <section class="log-block">
        <h2>${esc(t("finishedTasks"))}</h2>
        <div id="log-finished"><p>${esc(t("loading"))}</p></div>
      </section>
    </div>

    <div id="log-system-panel" style="display: ${currentLogsTab === "system" ? "block" : "none"}">
      <div class="syslog-controls">
        <label>
          ${esc(t("logLevel"))}:
          <select id="syslog-runtime-level" data-action="change-log-level">
            <option value="DEBUG" ${systemLogLevel === "DEBUG" ? "selected" : ""}>DEBUG</option>
            <option value="INFO" ${systemLogLevel === "INFO" ? "selected" : ""}>INFO</option>
            <option value="WARNING" ${systemLogLevel === "WARNING" ? "selected" : ""}>WARNING</option>
            <option value="ERROR" ${systemLogLevel === "ERROR" ? "selected" : ""}>ERROR</option>
          </select>
        </label>
        <label>
          ${esc(t("filterAll"))}:
          <select id="syslog-filter-level" data-action="filter-log-level">
            <option value="DEBUG" ${systemLogMinLevel === "DEBUG" ? "selected" : ""}>DEBUG+</option>
            <option value="INFO" ${systemLogMinLevel === "INFO" ? "selected" : ""}>INFO+</option>
            <option value="WARNING" ${systemLogMinLevel === "WARNING" ? "selected" : ""}>WARNING+</option>
            <option value="ERROR" ${systemLogMinLevel === "ERROR" ? "selected" : ""}>ERROR+</option>
          </select>
        </label>
        <input type="search" id="syslog-search-input" placeholder="${esc(t("searchLogs"))}" value="${esc(systemLogSearch)}" style="flex:1; min-width:180px;">
        <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-size:13px;user-select:none;">
          <input type="checkbox" id="syslog-autoscroll" ${systemLogAutoScroll ? "checked" : ""}>
          <span>${esc(t("autoScroll") || (document.documentElement.lang === "en" ? "Auto-scroll" : "自动滚动"))}</span>
        </label>
        <a class="btn btn-secondary" href="/api/system/logs/download" download style="display:inline-flex;align-items:center;padding:5px 12px;font-size:13px;text-decoration:none;border-radius:4px" target="_blank">${esc(t("downloadLogs"))}</a>
        <button class="secondary" data-action="refresh-system-logs" type="button">${esc(t("refreshLogs"))}</button>
        <button class="secondary" data-action="clear-system-logs" type="button">${esc(t("clearLogs"))}</button>
      </div>
      <div id="syslog-storage-info" style="font-size:11px;color:var(--muted);margin-bottom:8px;"></div>
      <div id="syslog-container" style="max-height:72vh;overflow-y:auto;scroll-behavior:smooth;"><p>${esc(t("loading"))}</p></div>
    </div>
  `);

  bindSyslogEvents();
  pollLogs();
}

function taskMeta(task, stage) {
  switch (task) {
    case "scan": return { label: t("scanning"), desc: t("scanDesc") };
    case "tag-sync": return { label: t("tagSyncing"), desc: t("tagSyncDesc") };
    case "thumbs": return { label: t("thumbs"), desc: t("thumbsDesc") };
    case "metadata": return {
      label: stage === "apply" ? t("favMetaApply") : t("favMetaSync"),
      desc: t("metaDesc"),
    };
    case "favcheck":
    case "favorites-check": return { label: t("checkAll"), desc: t("favCheckDesc") };
    case "duplicates": return { label: t("tasks.duplicates"), desc: t("tasks.duplicatesDesc") };
    case "gallery-updates": return { label: t("tasks.galleryUpdates"), desc: t("tasks.galleryUpdatesDesc") };
    case "orphan-thumbnail-cleanup": return { label: t("tasks.orphanThumbnailCleanup"), desc: t("tasks.orphanThumbnailCleanupDesc") };
    case "thumbnail-periodic-seed": return { label: t("tasks.thumbnailPeriodicSeed"), desc: t("tasks.thumbnailPeriodicSeedDesc") };
    case "download-retry-sweep": return { label: t("tasks.downloadRetrySweep"), desc: t("tasks.downloadRetrySweepDesc") };
    case "cookie-health": return { label: t("tasks.cookieHealth"), desc: t("tasks.cookieHealthDesc") };
    case "calibrate-storage": return { label: t("tasks.calibrateStorage"), desc: t("tasks.calibrateStorageDesc") };
    case "translation": return { label: t("translationUpdate"), desc: t("transDesc") };
    case "gallery-delete": return { label: t("deleteGalleryLog"), desc: t("deleteFiles") };
    case "favorites-remove": return { label: t("favoritesRemoveLog"), desc: t("confirmDupDelete") };
    case "favorites-move": return { label: t("favoritesMoveLog"), desc: t("favMoveTitle") };
    case "favorites-add": return { label: t("favoritesAddLog"), desc: t("favAddTitle") };
    case "series-rebuild": return { label: t("seriesRebuild"), desc: t("seriesSub") };
    case "download-clear-success": return { label: t("clearSuccessDlLog"), desc: t("downloadsSub") };
    case "archive": return { label: t("archiveLogLabel"), desc: t("archiveLogDesc") };
    case "purge-archived-sources": return {
      label: t("tasks.purgeArchivedSources") || "Purge Archived Sources",
      desc: t("tasks.purgeArchivedSourcesDesc") || "Scan and purge leftover source files",
    };
    case "integrity": return { label: t("tasks.integrity"), desc: t("tasks.integrityDesc") };
    default: return { label: task, desc: "" };
  }
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

function renderSystemLogRow(row) {
  const ctx = row.context || {};
  const tags = Object.keys(ctx).map(k => `<span class="syslog-tag">${esc(k)}=${esc(String(ctx[k]))}</span>`).join(" ");
  const req = row.request_id ? `<span class="syslog-tag">req=${esc(row.request_id)}</span>` : "";
  const exc = row.exception
    ? `<details class="syslog-trace-details">
        <summary>${esc(row.exception_type || "Exception Traceback")}</summary>
        <pre class="syslog-trace">${esc(row.exception)}</pre>
       </details>`
    : "";

  return `
    <div class="syslog-row">
      <div class="syslog-meta">
        <span class="syslog-time">${esc(row.time || "")}</span>
        <span class="syslog-level syslog-${esc(row.level)}">${esc(row.level)}</span>
        <span class="syslog-logger">${esc(row.logger || "")}</span>
        ${req}
        <span class="syslog-context">${tags}</span>
      </div>
      <div class="syslog-msg">${esc(row.message || "")}</div>
      ${exc}
    </div>
  `;
}

async function fetchSystemLogs() {
  const container = document.getElementById("syslog-container");
  if (!container) return;
  bindSyslogEvents();

  if (systemLogSearch !== lastSearchQuery || systemLogMinLevel !== lastMinLevel) {
    lastRenderedLogId = null;
    lastSearchQuery = systemLogSearch;
    lastMinLevel = systemLogMinLevel;
  }

  try {
    const q = new URLSearchParams({
      min_level: systemLogMinLevel,
      limit: "200",
    });
    if (systemLogSearch) q.set("search", systemLogSearch);
    const data = await api("GET", `/api/system/logs?${q.toString()}`);
    if (data.level) {
      systemLogLevel = data.level;
      const sel = document.getElementById("syslog-runtime-level");
      if (sel && sel.value !== data.level) sel.value = data.level;
    }
    const infoEl = document.getElementById("syslog-storage-info");
    if (infoEl) {
      infoEl.textContent = data.log_mode === "file" && data.log_file
        ? `Storage: File (${data.log_file})`
        : "Storage: In-memory RingBuffer";
    }
    const logs = data.logs || [];
    if (!logs.length) {
      lastRenderedLogId = null;
      container.innerHTML = `<p class="muted">${esc(t("noLogs"))}</p>`;
      return;
    }

    let rowsEl = container.querySelector(".syslog-rows");
    const maxIncomingId = logs.reduce((acc, it) => Math.max(acc, Number(it.id) || 0), 0);
    const needsFullRender = (
      !rowsEl ||
      lastRenderedLogId === null ||
      (maxIncomingId > 0 && lastRenderedLogId > maxIncomingId)
    );

    if (needsFullRender) {
      const chronological = logs.slice().reverse();
      container.innerHTML = `<div class="syslog-rows">${chronological.map(renderSystemLogRow).join("")}</div>`;
      lastRenderedLogId = maxIncomingId;
      if (systemLogAutoScroll && !isUserScrolledUp) {
        scrollSyslogToBottom();
      }
    } else {
      const newLogs = logs.filter(l => (Number(l.id) || 0) > lastRenderedLogId);
      if (newLogs.length > 0) {
        newLogs.sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0));
        const html = newLogs.map(renderSystemLogRow).join("");
        rowsEl.insertAdjacentHTML("beforeend", html);
        lastRenderedLogId = Math.max(lastRenderedLogId, ...newLogs.map(l => Number(l.id) || 0));

        while (rowsEl.children.length > MAX_SYSLOG_DOM_NODES) {
          rowsEl.removeChild(rowsEl.firstElementChild);
        }

        if (systemLogAutoScroll && !isUserScrolledUp) {
          scrollSyslogToBottom();
        }
      }
    }
  } catch (err) {
    if (container && !container.querySelector(".syslog-rows")) {
      container.innerHTML = `<p class="danger">${esc(err.message)}</p>`;
    }
  }
}

async function pollLogs() {
  if (logTimer) clearInterval(logTimer);
  const tick = async () => {
    if (currentLogsTab === "system") {
      await fetchSystemLogs();
      return;
    }
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
  logTimer = setInterval(tick, 3000);
}

async function switchLogTab(tab) {
  currentLogsTab = tab;
  const actPanel = document.getElementById("log-activity-panel");
  const sysPanel = document.getElementById("log-system-panel");
  document.querySelectorAll(".log-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
  });
  if (actPanel && sysPanel) {
    actPanel.style.display = tab === "activity" ? "block" : "none";
    sysPanel.style.display = tab === "system" ? "block" : "none";
  }
  if (tab === "system") {
    bindSyslogEvents();
  }
  pollLogs();
}

async function changeRuntimeLogLevel(newLevel) {
  try {
    const res = await api("POST", "/api/system/logs/level", { level: newLevel });
    systemLogLevel = res.level || newLevel;
    toast(`${t("logLevelChanged")} ${systemLogLevel}`);
    fetchSystemLogs();
  } catch (err) {
    toast(err.message);
  }
}

async function clearSystemLogs() {
  try {
    await api("DELETE", "/api/system/logs");
    toast(t("logsCleared"));
    lastRenderedLogId = null;
    fetchSystemLogs();
  } catch (err) {
    toast(err.message);
  }
}

async function cancelTask(task) {
  try {
    await api("POST", `/api/logs/${encodeURIComponent(task)}/cancel`);
    toast(t("cancelTask") + " · " + task);
    pollLogs();
  } catch (e) { toast(e.message); }
}
