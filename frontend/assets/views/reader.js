"use strict";

// views/reader.js — Phase 1 continue
// renderReader + reader helpers moved from app.js

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
            <button class="btn btn-secondary" data-action="reader-fit" type="button">${esc(t("readerFit"))}</button>
            <button class="btn btn-secondary" data-action="reader-fullscreen" type="button">${esc(t("readerFullscreen"))}</button>
          </span>
        </div>
        ${preload}
        <img id="reader-img" src="/api/galleries/${id}/pages/${page}" alt="Page ${page + 1}" data-next="${page + 1 < total ? page + 1 : ""}">
        <div class="nav">
          ${page > 0 ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: page - 1 }, libraryContext())}">${esc(t("prev"))}</a>` : `<span>${esc(t("prev"))}</span>`}
          <a class="btn btn-secondary" href="${navHash("gallery", { id }, libraryContext())}">${esc(t("allPages"))}</a>
          ${page + 1 < total ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: page + 1 }, libraryContext())}">${esc(t("next"))}</a>` : `<span>${esc(t("next"))}</span>`}
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
      // Allow clicking the image or empty reader area to advance (mobile)
      const img = e.target.closest && e.target.closest("#reader-img");
      const readerArea = e.target.closest && e.target.closest(".reader");
      const isButton = e.target.closest && e.target.closest("button, a");
      if (isButton) return;
      if (img) {
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
      if (readerArea) {
        // Click on empty reader background — advance
        if (readerFsActive) {
          const cur = current() + 1;
          if (cur < (app.readerTotal || 0)) readerSwapPage(id, cur);
          else { exitReaderFullscreen(); goReaderNext(id); }
        } else {
          advance();
        }
        return;
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
  img.classList.toggle("reader-fit");
  // Clear any legacy inline styles that conflict with CSS variables
  img.style.width = "";
  img.style.maxWidth = "";
  img.style.height = "";
}

async function goReaderNext(id) {
  try {
    const r = await api("GET", `/api/galleries/${id}/next`);
    location.hash = navHash("reader", { id: r.id, page: 0 }, libraryContext());
  } catch (_) { /* no next gallery */ }
}
