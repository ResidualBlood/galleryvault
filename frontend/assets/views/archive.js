"use strict";

// views/archive.js — Cold storage archive view

let archiveTimer = null;

async function renderArchive() {
  currentViewCleanup = () => {
    if (archiveTimer) {
      clearInterval(archiveTimer);
      archiveTimer = null;
    }
  };

  renderView(`
    <header>
      <p class="eyebrow">COLD ARCHIVE</p>
      <h1>${esc(t("archiveTitle"))}</h1>
      <p class="sub">${esc(t("archiveSub"))}</p>
    </header>
    ${manageTabsHtml("archive")}
    <div class="toolbar" id="archive-toolbar">
      <button class="btn btn-primary" data-action="archive-start" type="button" id="archive-start-btn">${esc(t("archiveStart"))}</button>
      <button class="btn btn-secondary" data-action="archive-cancel" type="button" id="archive-cancel-btn" disabled>${esc(t("archiveCancel"))}</button>
    </div>
    <div id="archive-status-panel"><div class="panel" style="margin:16px 0;padding:20px;max-width:640px">${renderLoading()}</div></div>
  `);

  await pollArchive();
}

async function updateArchiveState() {
  const panel = document.getElementById("archive-status-panel");
  const startBtn = document.getElementById("archive-start-btn");
  const cancelBtn = document.getElementById("archive-cancel-btn");
  if (!panel) return;

  try {
    const data = await api("GET", "/api/archive");
    if (!data) return;

    const isRunning = Boolean(data.running);
    if (startBtn) startBtn.disabled = isRunning;
    if (cancelBtn) cancelBtn.disabled = !isRunning;

    const done = Number(data.done) || 0;
    const skipped = Number(data.skipped) || 0;
    const failed = Number(data.failed) || 0;
    const total = Number(data.total) || 0;
    const processed = done + skipped + failed;
    const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : (isRunning ? null : 0);

    let statusHtml = "";
    if (isRunning) {
      statusHtml = `<span class="log-status run" style="font-size:1rem;font-weight:600">${esc(t("archiveRunning"))}</span>`;
    } else if (data.completed_at || data.started_at) {
      const statusText = failed > 0 ? t("taskFailed") : t("taskSuccess");
      const badgeClass = failed > 0 ? "fail" : "ok";
      statusHtml = `<span class="log-status ${badgeClass}" style="font-size:1rem;font-weight:600">${esc(statusText)}</span>`;
    } else {
      statusHtml = `<span class="muted" style="font-size:1rem">${esc(t("noTasks"))}</span>`;
    }

    let progressHtml = "";
    if (isRunning) {
      if (pct !== null) {
        progressHtml = `
          <div style="margin:16px 0">
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:13px;color:var(--muted)">
              <span>${esc(t("taskRunning"))}</span>
              <span>${pct}% (${processed} / ${total})</span>
            </div>
            <div class="dl-progress" style="width:100%"><div class="dl-progress-bar" style="width:${pct}%"></div></div>
          </div>
        `;
      } else {
        progressHtml = `
          <div style="margin:16px 0">
            <div class="dl-progress dl-progress-indet" style="width:100%"></div>
          </div>
        `;
      }
    } else if ((data.completed_at || data.started_at) && total > 0) {
      const finPct = Math.min(100, Math.round((processed / total) * 100));
      progressHtml = `
        <div style="margin:16px 0">
          <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:13px;color:var(--muted)">
            <span>${esc(t("finishedTasks"))}</span>
            <span>${finPct}% (${processed} / ${total})</span>
          </div>
          <div class="dl-progress" style="width:100%"><div class="dl-progress-bar" style="width:${finPct}%"></div></div>
        </div>
      `;
    }

    const statsHtml = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:12px;margin:16px 0;padding:12px;background:var(--panel-2);border-radius:var(--radius-md)">
        <div><div class="muted" style="font-size:12px">${esc(t("archiveDone"))}</div><div style="font-size:1.2rem;font-weight:600;color:var(--ink)">${done}</div></div>
        <div><div class="muted" style="font-size:12px">${esc(t("archiveSkip"))}</div><div style="font-size:1.2rem;font-weight:600;color:var(--ink)">${skipped}</div></div>
        <div><div class="muted" style="font-size:12px">${esc(t("taskFailed"))}</div><div style="font-size:1.2rem;font-weight:600;color:${failed > 0 ? "var(--danger)" : "var(--ink)"}">${failed}</div></div>
      </div>
    `;

    let timeHtml = "";
    if (data.started_at || data.completed_at) {
      timeHtml = `
        <div style="font-size:12px;color:var(--muted);display:flex;flex-wrap:wrap;gap:16px;margin-top:8px">
          ${data.started_at ? `<span>${esc(t("startedAt"))}: ${fmtDateTime(data.started_at)}</span>` : ""}
          ${data.completed_at ? `<span>${esc(t("finishedAt"))}: ${fmtDateTime(data.completed_at)}</span>` : ""}
        </div>
      `;
    }

    let errorHtml = "";
    if (data.last_error) {
      errorHtml = `<div class="danger" style="margin-top:12px;font-size:13px;word-break:break-all">${esc(data.last_error)}</div>`;
    }

    panel.innerHTML = `
      <section class="panel" style="margin:16px 0;padding:20px;max-width:640px">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div>${statusHtml}</div>
        </div>
        ${progressHtml}
        ${statsHtml}
        ${timeHtml}
        ${errorHtml}
      </section>
    `;
  } catch (err) {
    panel.innerHTML = renderError(err.message || String(err));
  }
}

async function pollArchive() {
  if (archiveTimer) clearInterval(archiveTimer);
  await updateArchiveState();
  archiveTimer = setInterval(async () => {
    if (app.view !== "archive") {
      if (archiveTimer) clearInterval(archiveTimer);
      archiveTimer = null;
      return;
    }
    await updateArchiveState();
  }, 2000);
}

async function archiveStart() {
  const startBtn = document.getElementById("archive-start-btn");
  if (startBtn) startBtn.disabled = true;
  try {
    const res = await api("POST", "/api/archive");
    if (res && res.status === "paused") {
      toast(res.detail || t("paused"));
    } else {
      toast(t("archiveRunning"));
    }
  } catch (err) {
    toast(err.message || String(err));
  } finally {
    await updateArchiveState();
  }
}

async function archiveCancel() {
  const cancelBtn = document.getElementById("archive-cancel-btn");
  if (cancelBtn) cancelBtn.disabled = true;
  try {
    await api("POST", "/api/logs/archive/cancel");
    toast(t("taskCancelling"));
  } catch (err) {
    toast(err.message || String(err));
  } finally {
    await updateArchiveState();
  }
}
