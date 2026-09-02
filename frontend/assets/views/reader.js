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

function getReaderNav(page, total, mode) {
  mode = mode || getReaderMode();
  const isDouble = mode.startsWith("double");
  if (!isDouble) {
    const prevPage = page > 0 ? page - 1 : null;
    const nextPage = page + 1 < total ? page + 1 : null;
    return { prevPage, nextPage, curPage: page };
  }
  // Double mode: page 0 is single cover; page 1+ are spreads [1,2], [3,4], [5,6]...
  const normalized = page === 0 ? 0 : (page % 2 === 1 ? page : page - 1);
  let prevPage = null;
  if (normalized === 1) {
    prevPage = 0;
  } else if (normalized > 1) {
    prevPage = Math.max(1, normalized - 2);
  }
  let nextPage = null;
  if (normalized === 0) {
    nextPage = total > 1 ? 1 : null;
  } else if (normalized + 2 < total) {
    nextPage = normalized + 2;
  }
  return { prevPage, nextPage, curPage: normalized };
}

function cycleReaderMode() {
  const modes = ["ltr", "rtl", "double", "double-rtl"];
  const current = getReaderMode();
  const next = modes[(modes.indexOf(current) + 1) % modes.length];
  setReaderMode(next);
  renderReader();
}

async function renderReader() {
  if (readerTouchCleanup) {
    readerTouchCleanup();
    readerTouchCleanup = null;
  }
  const id = app.params.id;
  const rawPage = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const mode = getReaderMode();
  const isDoubleMode = mode.startsWith("double");
  const page = isDoubleMode && rawPage > 0 && rawPage % 2 === 0 ? rawPage - 1 : rawPage;
  if (page !== rawPage) {
    app.params.page = String(page);
    syncReaderUrl();
  }
  const isDouble = isDoubleMode && page > 0;
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
          <div class="reader-img-wrap"${p2 === null ? ' style="display:none"' : ''}><img src="${p2 !== null ? `/api/galleries/${id}/pages/${p2}` : ''}" alt="${p2 !== null ? `Page ${p2 + 1}` : ''}" data-page="${p2 !== null ? p2 : ''}"></div>
        </div>`;
    } else {
      imgHtml = `
        <div class="reader-img-wrap">
          <img id="reader-img" src="/api/galleries/${id}/pages/${page}" alt="Page ${page + 1}" data-page="${page}" data-next="${page + 1 < total ? page + 1 : ""}">
        </div>`;
    }

    const nav = getReaderNav(page, total, mode);
    const prevBtn = nav.prevPage !== null
      ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nav.prevPage }, libraryContext())}">${esc(t("prev"))}</a>`
      : `<span>${esc(t("prev"))}</span>`;
    const nextBtn = nav.nextPage !== null
      ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nav.nextPage }, libraryContext())}">${esc(t("next"))}</a>`
      : `<span>${esc(t("next"))}</span>`;

    const navHtml = isRtl
      ? `<div class="nav">${nextBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, libraryContext())}">${esc(t("allPages"))}</a>${prevBtn}</div>`
      : `<div class="nav">${prevBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, libraryContext())}">${esc(t("allPages"))}</a>${nextBtn}</div>`;

    const innerHtml = `
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
      ${navHtml}`;

    const existingReader = $view().querySelector(".reader");
    if (existingReader) {
      existingReader.innerHTML = innerHtml;
    } else {
      $view().innerHTML = `<div class="reader">${innerHtml}</div>`;
    }

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

  const advance = () => {
    const cur = current();
    const nav = getReaderNav(cur, app.readerTotal || 0, mode());
    if (nav.nextPage !== null) {
      if (readerFsActive) { readerSwapPage(id, nav.nextPage); return; }
      location.hash = navHash("reader", { id, page: nav.nextPage }, libraryContext());
    } else {
      exitReaderFullscreen();
      goReaderNext(id);
    }
  };

  const retreat = () => {
    const cur = current();
    const nav = getReaderNav(cur, app.readerTotal || 0, mode());
    if (nav.prevPage !== null) {
      if (readerFsActive) { readerSwapPage(id, nav.prevPage); return; }
      location.hash = navHash("reader", { id, page: nav.prevPage }, libraryContext());
    }
  };

  readerKeyHandler = (e) => {
    if (e.type === "click") {
      const isInteractive = e.target.closest && e.target.closest(".reader-bar, .toolbar, .nav, button, a, input, select, textarea");
      if (isInteractive) return;

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
  let lastTapX = 0;
  let lastTapY = 0;
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
          imgs.forEach(img => {
            img.style.transform = "";
            img.style.transformOrigin = "";
          });
          container.classList.remove("zoomed");
        } else {
          currentScale = 2.2;
          const rect = container.getBoundingClientRect();
          const originX = rect.width > 0 ? Math.max(0, Math.min(100, Math.round(((lastTapX - rect.left) / rect.width) * 100))) : 50;
          const originY = rect.height > 0 ? Math.max(0, Math.min(100, Math.round(((lastTapY - rect.top) / rect.height) * 100))) : 50;
          imgs.forEach(img => {
            img.style.transformOrigin = `${originX}% ${originY}%`;
            img.style.transform = `scale(${currentScale})`;
          });
          container.classList.add("zoomed");
        }
      }
      lastTap = now;
      if (currentScale <= 1.05) {
        currentScale = 1;
        const imgs = container.querySelectorAll("img");
        imgs.forEach(img => {
          img.style.transform = "";
          img.style.transformOrigin = "";
        });
        container.classList.remove("zoomed");
      }
    }
  };

  const onTouchStart = (e) => {
    if (e.touches.length === 1) {
      lastTapX = e.touches[0].clientX;
      lastTapY = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
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
  const targetEl = document.querySelector(".reader");
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
  const el = document.querySelector(".reader");
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

  const mode = getReaderMode();
  const isDoubleMode = mode.startsWith("double");
  if (isDoubleMode && target > 0 && target % 2 === 0) {
    target = target - 1;
  }
  app.params.page = String(target);

  const isDouble = isDoubleMode && target > 0;
  const spreadEl = document.querySelector(".reader-spread");

  if (isDouble && spreadEl) {
    const p1 = target;
    const p2 = target + 1 < total ? target + 1 : null;
    const imgs = spreadEl.querySelectorAll("img");
    if (imgs.length >= 2) {
      imgs[0].src = `/api/galleries/${id}/pages/${p1}`;
      imgs[0].dataset.page = String(p1);
      imgs[0].alt = `Page ${p1 + 1}`;
      if (p2 !== null) {
        imgs[1].src = `/api/galleries/${id}/pages/${p2}`;
        imgs[1].dataset.page = String(p2);
        imgs[1].alt = `Page ${p2 + 1}`;
        imgs[1].parentElement.style.display = "";
      } else {
        imgs[1].parentElement.style.display = "none";
      }
      const bar = document.querySelector(".reader-bar span");
      if (bar) bar.textContent = `${p1 + 1}${p2 !== null ? `-${p2 + 1}` : ""} / ${total} · ${fmtSize((app.readerGallery && app.readerGallery.file_size) || 0)}`;
    } else {
      renderReader();
      return;
    }
  } else if (!isDouble && !spreadEl) {
    const img = document.getElementById("reader-img");
    if (img) {
      img.src = `/api/galleries/${id}/pages/${target}`;
      img.dataset.page = String(target);
      img.alt = `Page ${target + 1}`;
      img.dataset.next = target + 1 < total ? String(target + 1) : "";
    }
    const bar = document.querySelector(".reader-bar span");
    if (bar) bar.textContent = `${target + 1} / ${total} · ${fmtSize((app.readerGallery && app.readerGallery.file_size) || 0)}`;
  } else {
    // Structural transition between single cover and double spread: in-place re-render (preserves .reader fullscreen)
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
