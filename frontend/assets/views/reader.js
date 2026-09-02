"use strict";

// views/reader.js — Reader with LTR, RTL Manga, and Double-page modes + gestures

let readerTouchCleanup = null;

function getReaderMode() {
  return localStorage.getItem("gv_reader_mode") || "ltr";
}

function setReaderMode(mode) {
  localStorage.setItem("gv_reader_mode", mode);
}

function readerModeLabel(mode) {
  mode = mode || getReaderMode();
  if (mode === "rtl") return t("readerModeRtl") || "RTL";
  if (mode === "double") return t("readerModeDouble") || "Double";
  if (mode === "double-rtl") return t("readerModeDoubleRtl") || "Double RTL";
  return t("readerModeLtr") || "LTR";
}

function cycleReaderMode() {
  const modes = ["ltr", "rtl", "double", "double-rtl"];
  const current = getReaderMode();
  const next = modes[(modes.indexOf(current) + 1) % modes.length];
  setReaderMode(next);
  renderReader();
}

async function renderReader() {
  const id = app.params.id;
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const mode = getReaderMode();
  const isDouble = mode.startsWith("double") && page > 0;
  const isRtl = mode === "rtl" || mode === "double-rtl";

  try {
    let g = app.readerGallery;
    if (!g || String(g.id) !== String(id)) {
      g = await api("GET", `/api/galleries/${id}`);
      app.readerGallery = g;
    }
    const total = g.page_count;
    app.readerTotal = total;

    // Directional Preloading
    let preload = "";
    const preloadStep = isDouble ? 4 : 3;
    for (let i = 1; i <= preloadStep && page + i < total; i++) {
      preload += `<link rel="preload" as="image" href="/api/galleries/${id}/pages/${page + i}">`;
    }

    let imgHtml = "";
    if (isDouble) {
      const p1 = page;
      const p2 = page + 1 < total ? page + 1 : null;
      const rtlClass = mode === "double-rtl" ? " reader-spread-rtl" : "";
      imgHtml = `
        <div class="reader-spread${rtlClass}">
          <div class="reader-img-wrap"><img id="reader-img" src="/api/galleries/${id}/pages/${p1}" alt="Page ${p1 + 1}" data-page="${p1}"></div>
          ${p2 !== null ? `<div class="reader-img-wrap"><img src="/api/galleries/${id}/pages/${p2}" alt="Page ${p2 + 1}" data-page="${p2}"></div>` : ""}
        </div>`;
    } else {
      imgHtml = `
        <div class="reader-img-wrap">
          <img id="reader-img" src="/api/galleries/${id}/pages/${page}" alt="Page ${page + 1}" data-page="${page}" data-next="${page + 1 < total ? page + 1 : ""}">
        </div>`;
    }

    const step = isDouble ? 2 : 1;
    const prevPage = page === 1 ? 0 : Math.max(0, page - (page === 2 ? 1 : step));
    const nextPage = page === 0 ? 1 : (page + step < total ? page + step : null);

    const prevBtn = page > 0
      ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: prevPage }, libraryContext())}">${esc(t("prev"))}</a>`
      : `<span>${esc(t("prev"))}</span>`;
    const nextBtn = nextPage !== null
      ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nextPage }, libraryContext())}">${esc(t("next"))}</a>`
      : `<span>${esc(t("next"))}</span>`;

    const navHtml = isRtl
      ? `<div class="nav">${nextBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, libraryContext())}">${esc(t("allPages"))}</a>${prevBtn}</div>`
      : `<div class="nav">${prevBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, libraryContext())}">${esc(t("allPages"))}</a>${nextBtn}</div>`;

    $view().innerHTML = `
      <div class="reader">
        <div class="reader-bar toolbar">
          <a class="link-button" href="${navHash("gallery", { id }, libraryContext())}">← ${esc(t("details"))}</a>
          <span>${isDouble && page + 1 < total ? `${page + 1}-${page + 2}` : page + 1} / ${total} · ${fmtSize(g.file_size || 0)}</span>
          <span class="reader-actions">
            <button class="btn btn-secondary" data-action="reader-mode" type="button" title="${esc(t("readerMode"))}">${esc(t("readerMode"))}: ${esc(readerModeLabel(mode))}</button>
            <button class="btn btn-secondary" data-action="reader-fit" type="button">${esc(t("readerFit"))}</button>
            <button class="btn btn-secondary" data-action="reader-fullscreen" type="button">${esc(t("readerFullscreen"))}</button>
          </span>
        </div>
        ${preload}
        ${imgHtml}
        ${navHtml}
      </div>`;

    initReaderGestures();
    try { await api("PUT", `/api/galleries/${id}/progress`, { current_page: page, total_pages: total }); } catch (_) {}
  } catch (e) {
    $view().innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function bindReaderKeys() {
  if (readerKeyHandler) {
    document.removeEventListener("keydown", readerKeyHandler);
    document.removeEventListener("click", readerKeyHandler);
    readerKeyHandler = null;
  }
  if (app.view !== "reader") return;

  const id = app.params.id;
  const current = () => Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const mode = () => getReaderMode();
  const isRtl = () => mode() === "rtl" || mode() === "double-rtl";
  const isDouble = () => mode().startsWith("double");

  const advance = () => {
    const cur = current();
    const step = isDouble() && cur > 0 ? 2 : 1;
    const n = cur === 0 && isDouble() ? 1 : cur + step;
    if (app.readerTotal && n >= app.readerTotal) { goReaderNext(id); return; }
    if (readerFsActive) { readerSwapPage(id, n); return; }
    location.hash = navHash("reader", { id, page: n }, libraryContext());
  };

  const retreat = () => {
    const cur = current();
    const step = isDouble() && cur > 1 ? 2 : 1;
    const n = Math.max(0, cur - step);
    if (readerFsActive) { readerSwapPage(id, n); return; }
    location.hash = navHash("reader", { id, page: n }, libraryContext());
  };

  readerKeyHandler = (e) => {
    if (e.type === "click") {
      const isButton = e.target.closest && e.target.closest("button, a, input, select, textarea");
      if (isButton) return;

      const readerArea = e.target.closest && e.target.closest(".reader");
      if (!readerArea) return;

      const rect = readerArea.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const isRightSide = clickX > rect.width / 2;

      if (isRtl()) {
        if (isRightSide) retreat();
        else advance();
      } else {
        if (isRightSide) advance();
        else retreat();
      }
      return;
    }

    const tEl = e.target;
    if (tEl && (tEl.tagName === "INPUT" || tEl.tagName === "TEXTAREA" || tEl.tagName === "SELECT")) return;

    if (e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      advance();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (isRtl()) retreat();
      else advance();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (isRtl()) advance();
      else retreat();
    } else if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      toggleReaderFullscreen();
    }
  };

  document.addEventListener("keydown", readerKeyHandler);
  document.addEventListener("click", readerKeyHandler);
}

function initReaderGestures() {
  if (readerTouchCleanup) {
    readerTouchCleanup();
    readerTouchCleanup = null;
  }

  const container = document.querySelector(".reader-spread") || document.querySelector(".reader-img-wrap");
  if (!container) return;

  let lastTap = 0;
  let initialDist = 0;
  let currentScale = 1;

  const onTouchEnd = (e) => {
    if (e.touches.length === 0) {
      const now = Date.now();
      if (now - lastTap < 300) {
        e.preventDefault();
        const imgs = container.querySelectorAll("img");
        if (currentScale > 1.2) {
          currentScale = 1;
          imgs.forEach(img => { img.style.transform = ""; });
          container.classList.remove("zoomed");
        } else {
          currentScale = 2.2;
          imgs.forEach(img => { img.style.transform = `scale(${currentScale})`; });
          container.classList.add("zoomed");
        }
      }
      lastTap = now;
      if (currentScale <= 1.05) {
        currentScale = 1;
        const imgs = container.querySelectorAll("img");
        imgs.forEach(img => { img.style.transform = ""; });
        container.classList.remove("zoomed");
      }
    }
  };

  const onTouchStart = (e) => {
    if (e.touches.length === 2) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      initialDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
    }
  };

  const onTouchMove = (e) => {
    if (e.touches.length === 2 && initialDist > 0) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
      const factor = dist / initialDist;
      currentScale = Math.min(3.5, Math.max(1, currentScale * factor));
      initialDist = dist;
      const imgs = container.querySelectorAll("img");
      imgs.forEach(img => { img.style.transform = `scale(${currentScale})`; });
      if (currentScale > 1.2) container.classList.add("zoomed");
      else container.classList.remove("zoomed");
    }
  };

  container.addEventListener("touchend", onTouchEnd, { passive: false });
  container.addEventListener("touchstart", onTouchStart, { passive: true });
  container.addEventListener("touchmove", onTouchMove, { passive: true });

  readerTouchCleanup = () => {
    container.removeEventListener("touchend", onTouchEnd);
    container.removeEventListener("touchstart", onTouchStart);
    container.removeEventListener("touchmove", onTouchMove);
  };
}

function toggleReaderFullscreen() {
  if (document.fullscreenElement) { exitReaderFullscreen(); }
  else { enterReaderFullscreen(); }
}

function enterReaderFullscreen() {
  const mode = getReaderMode();
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const isDouble = mode.startsWith("double") && page > 0;
  const targetEl = isDouble
    ? (document.querySelector(".reader-spread") || document.getElementById("reader-img"))
    : document.getElementById("reader-img");
  if (!targetEl || !targetEl.requestFullscreen) return;

  readerFitBeforeFs = targetEl.getAttribute("style") || "";
  targetEl.removeAttribute("style");
  readerFsActive = true;
  const p = targetEl.requestFullscreen();
  if (p && p.catch) p.catch(() => { clearReaderFsState(); });
}

function exitReaderFullscreen() {
  clearReaderFsState();
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  syncReaderUrl();
}

function clearReaderFsState() {
  readerFsActive = false;
  const el = document.querySelector(".reader-spread") || document.getElementById("reader-img");
  if (el && readerFitBeforeFs) el.setAttribute("style", readerFitBeforeFs);
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

  const mode = getReaderMode();
  const isDouble = mode.startsWith("double") && target > 0;
  const spreadEl = document.querySelector(".reader-spread");

  if (isDouble && spreadEl) {
    const p1 = target;
    const p2 = target + 1 < total ? target + 1 : null;
    const imgs = spreadEl.querySelectorAll("img");
    if (imgs.length >= 1) {
      imgs[0].src = `/api/galleries/${id}/pages/${p1}`;
      imgs[0].dataset.page = String(p1);
    }
    if (imgs.length >= 2 && p2 !== null) {
      imgs[1].src = `/api/galleries/${id}/pages/${p2}`;
      imgs[1].dataset.page = String(p2);
      imgs[1].parentElement.style.display = "";
    } else if (imgs.length >= 2) {
      imgs[1].parentElement.style.display = "none";
    }
    const bar = document.querySelector(".reader-bar span");
    if (bar) bar.textContent = `${p1 + 1}${p2 !== null ? `-${p2 + 1}` : ""} / ${total} · ${fmtSize((app.readerGallery && app.readerGallery.file_size) || 0)}`;
  } else if (!isDouble && !spreadEl) {
    const img = document.getElementById("reader-img");
    if (img) {
      img.src = `/api/galleries/${id}/pages/${target}`;
      img.dataset.page = String(target);
      img.dataset.next = target + 1 < total ? String(target + 1) : "";
    }
    const bar = document.querySelector(".reader-bar span");
    if (bar) bar.textContent = `${target + 1} / ${total} · ${fmtSize((app.readerGallery && app.readerGallery.file_size) || 0)}`;
  } else {
    // Structural transition between single cover and double spread: full re-render
    renderReader();
    return;
  }

  api("PUT", `/api/galleries/${id}/progress`, { current_page: target, total_pages: total }).catch(() => {});
  if (target + 1 < total) { const pre = new Image(); pre.src = `/api/galleries/${id}/pages/${target + 1}`; }
  if (isDouble && target + 2 < total) { const pre2 = new Image(); pre2.src = `/api/galleries/${id}/pages/${target + 2}`; }
}

function toggleReaderFit() {
  const imgs = document.querySelectorAll(".reader img");
  imgs.forEach(img => {
    img.classList.toggle("reader-fit");
    img.style.width = "";
    img.style.maxWidth = "";
    img.style.height = "";
  });
}

async function goReaderNext(id) {
  try {
    const r = await api("GET", `/api/galleries/${id}/next`);
    location.hash = navHash("reader", { id: r.id, page: 0 }, libraryContext());
  } catch (_) { /* no next gallery */ }
}
