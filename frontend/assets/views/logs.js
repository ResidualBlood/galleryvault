"use strict";

// views/logs.js — Phase 1 continue
// renderLogs moved from app.js

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
