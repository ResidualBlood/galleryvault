"use strict";

// views/logs.js — Phase 1 continue
// renderLogs + task helpers + poll + cancel moved here

async function renderLogs() {
  renderView(`
    <header><p class="eyebrow">ACTIVITY</p><h1>${esc(t("logs"))}</h1>
    <p class="sub">${esc(t("logsSub"))}</p></header>
    <section class="log-block">
      <h2>${esc(t("runningTasks"))}</h2>
      <div id="log-running"><p>${esc(t("loading"))}</p></div>
    </section>
    <section class="log-block">
      <h2>${esc(t("finishedTasks"))}</h2>
      <div id="log-finished"><p>${esc(t("loading"))}</p></div>
    </section>`);
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
    case "favcheck": return { label: t("checkAll"), desc: t("favCheckDesc") };
    case "translation": return { label: t("translationUpdate"), desc: t("transDesc") };
    case "gallery-delete": return { label: t("deleteGalleryLog"), desc: t("deleteFiles") };
    case "favorites-remove": return { label: t("favoritesRemoveLog"), desc: t("confirmDupDelete") };
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
