"use strict";

// views/reader.js — Reader with LTR, RTL Manga, and Double-page modes + gestures

let readerTouchCleanup = null;
let progressDebounceTimer = null;

function updateProgressDebounced(id, target, total) {
  if (progressDebounceTimer) {
    clearTimeout(progressDebounceTimer);
  }
  progressDebounceTimer = setTimeout(() => {
    progressDebounceTimer = null;
    api("PUT", `/api/galleries/${id}/progress`, { current_page: target, total_pages: total }).catch(() => {});
  }, 500);
}

function swapImageSmoothly(img, src, page, alt, onSwapComplete) {
  if (typeof page === "function") {
    onSwapComplete = page;
    page = undefined;
    alt = undefined;
  } else if (typeof alt === "function") {
    onSwapComplete = alt;
    alt = undefined;
  }
  const notifyComplete = () => {
    if (typeof onSwapComplete === "function") {
      try { onSwapComplete(); } catch (_) {}
    }
  };

  if (!img) {
    notifyComplete();
    return;
  }
  if (img.getAttribute("src") === src && img.dataset.page === String(page)) {
    notifyComplete();
    return;
  }

  const reqId = (img._swapReqId = (img._swapReqId || 0) + 1);
  const newImg = document.createElement("img");
  newImg.decoding = "async";
  if (img.id) newImg.id = img.id;
  if (img.className) newImg.className = img.className;
  if (alt !== undefined) newImg.alt = alt;
  if (page !== undefined && page !== null) newImg.dataset.page = String(page);
  newImg.src = src;

  const finish = () => {
    if (img._swapReqId !== reqId) return;
    if (img.parentNode) {
      newImg._swapReqId = reqId;
      img.replaceWith(newImg);
    }
    notifyComplete();
  };

  if (typeof newImg.decode === "function") {
    newImg.decode().then(finish).catch(finish);
  } else {
    finish();
  }
}

function readerContext() {
  return {
    ...libraryContext(),
    ...(app.query.from ? { from: app.query.from } : {}),
    ...(app.query.slideshow ? { slideshow: app.query.slideshow } : {}),
  };
}

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
  if (mode === "webtoon") return t("readerModeWebtoon") || "Webtoon";
  return t("readerModeLtr") || "LTR";
}

function readerJumpSuffix(p1, p2, total, fileSize, isDouble) {
  if (isDouble && p2 != null) {
    return `${p1 + 1}-${p2 + 1} / ${total}`;
  }
  return `/ ${total} · ${fmtSize(fileSize || 0)}`;
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
  const modes = ["ltr", "rtl", "double", "double-rtl", "webtoon"];
  const current = getReaderMode();
  const next = modes[(modes.indexOf(current) + 1) % modes.length];
  setReaderMode(next);
  renderReader();
}

function buildReaderInnerHtml(id, page, total, mode, gallery) {
  const g = gallery || app.readerGallery || {};
  const isDoubleMode = mode.startsWith("double");
  const isDouble = isDoubleMode && page > 0;
  const isRtl = mode === "rtl" || mode === "double-rtl";

  // Directional Preloading
  let preload = "";
  const preloadStep = isDoubleMode ? 4 : 3;
  for (let i = 1; i <= preloadStep && page + i < total; i++) {
    preload += `<link rel="preload" as="image" href="/api/galleries/${id}/pages/${page + i}">`;
  }

  let imgHtml = "";
  if (isDoubleMode) {
    const p1 = page;
    const p2 = page > 0 && page + 1 < total ? page + 1 : null;
    const rtlClass = mode === "double-rtl" ? " reader-spread-rtl" : "";
    const p2Img = p2 !== null
      ? `<img decoding="async" src="/api/galleries/${id}/pages/${p2}" alt="Page ${p2 + 1}" data-page="${p2}">`
      : `<img decoding="async" alt="" data-page="">`;
    imgHtml = `
      <div class="reader-spread${rtlClass}">
        <div class="reader-img-wrap"><img id="reader-img" decoding="async" src="/api/galleries/${id}/pages/${p1}" alt="Page ${p1 + 1}" data-page="${p1}"></div>
        <div class="reader-img-wrap"${p2 === null ? ' style="display:none"' : ''}>${p2Img}</div>
      </div>`;
  } else {
    imgHtml = `
      <div class="reader-img-wrap">
        <img id="reader-img" decoding="async" src="/api/galleries/${id}/pages/${page}" alt="Page ${page + 1}" data-page="${page}" data-next="${page + 1 < total ? page + 1 : ""}">
      </div>`;
  }

  const nav = getReaderNav(page, total, mode);
  const prevBtn = nav.prevPage !== null
    ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nav.prevPage }, readerContext())}">${esc(t("prev"))}</a>`
    : `<span>${esc(t("prev"))}</span>`;
  const nextBtn = nav.nextPage !== null
    ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nav.nextPage }, readerContext())}">${esc(t("next"))}</a>`
    : `<span>${esc(t("next"))}</span>`;

  const navHtml = isRtl
    ? `<div class="nav">${nextBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, readerContext())}">${esc(t("allPages"))}</a>${prevBtn}</div>`
    : `<div class="nav">${prevBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, readerContext())}">${esc(t("allPages"))}</a>${nextBtn}</div>`;

  const ssSec = parseInt(localStorage.getItem("gv_slideshow_interval"), 10) || 5;

  return `
    <div class="reader-bar toolbar">
      <a class="link-button" href="${navHash("gallery", { id }, readerContext())}">← ${esc(t("details"))}</a>
      <span class="reader-page-indicator" style="display:inline-flex;align-items:center;gap:4px;">
        <form data-action="reader-jump" style="display:inline-flex;align-items:center;margin:0;padding:0;">
          <input id="reader-jump-input" class="reader-jump-input" type="number" min="1" max="${total}" value="${page + 1}" style="width:4.2em;padding:2px 4px;text-align:center;font-size:13px;border-radius:4px;border:1px solid var(--line);background:var(--panel-2);color:inherit;" title="${esc(t("jumpToPageHint"))}" aria-label="${esc(t("pageNumber"))}">
        </form>
        <span>${readerJumpSuffix(page, isDouble && page + 1 < total ? page + 1 : null, total, g.file_size || 0, isDouble)}</span>
      </span>
      <span class="reader-actions">
        ${esc(t("slideshowInterval"))} <input type="number" id="reader-slideshow-sec" class="form-control form-control-sm" style="min-width: 0 !important; width: 3.5rem; display: inline-block; margin-right: 0.5rem;" value="${ssSec}" min="1" title="${esc(t("slideshowInterval"))}">
        <button class="btn btn-sm btn-icon" data-action="reader-slideshow" title="${esc(t("slideshow"))}">▶</button>
        <button class="btn btn-secondary" data-action="reader-mode" type="button" title="${esc(t("readerMode"))}">${esc(t("readerMode"))}: ${esc(readerModeLabel(mode))}</button>
        <button class="btn btn-secondary" data-action="reader-fit" type="button">${esc(t("readerFit"))}</button>
        <button class="btn btn-secondary" data-action="reader-fullscreen" type="button">${esc(t("readerFullscreen"))}</button>
      </span>
    </div>
    ${preload}
    ${imgHtml}
    ${navHtml}`;
}

async function renderReader() {
  if (readerTouchCleanup) {
    readerTouchCleanup();
    readerTouchCleanup = null;
  }
  if (typeof cleanupWebtoon === "function") cleanupWebtoon();
  const id = app.params.id;
  const rawPage = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const mode = getReaderMode();
  if (mode === "webtoon") {
    return renderWebtoonReader();
  }
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

    const innerHtml = buildReaderInnerHtml(id, page, total, mode, g);

    const existingReader = $view().querySelector(".reader");
    if (existingReader) {
      existingReader.classList.remove("reader-webtoon");
      existingReader.innerHTML = innerHtml;
    } else {
      $view().innerHTML = `<div class="reader">${innerHtml}</div>`;
    }

    initReaderGestures();
    try { await api("PUT", `/api/galleries/${id}/progress`, { current_page: page, total_pages: total }); } catch (_) {}
    const ssSec = parseInt(app.query && app.query.slideshow, 10);
    if (ssSec > 0) {
      startSlideshow(ssSec);
    }
  } catch (e) {
    $view().innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function jumpToReaderPage(targetPage) {
  if (getReaderMode() === "webtoon") {
    jumpToWebtoonPage(targetPage);
    return;
  }
  const id = app.params.id;
  const total = app.readerTotal || 1;
  const clamped = Math.max(0, Math.min(total - 1, targetPage));
  const mode = getReaderMode();
  const isDoubleMode = mode.startsWith("double");
  const normalized = isDoubleMode && clamped > 0 && clamped % 2 === 0 ? clamped - 1 : clamped;
  if (app.query && app.query.slideshow) {
    readerSlideshowSession++;
    if (slideshowTimer) {
      clearTimeout(slideshowTimer);
      slideshowTimer = null;
    }
    const currentSession = readerSlideshowSession;
    readerSwapPage(id, normalized, () => {
      if (currentSession !== readerSlideshowSession || app.view !== "reader") return;
      const sec = parseInt(app.query && app.query.slideshow, 10) || parseInt(localStorage.getItem("gv_slideshow_interval"), 10) || 5;
      scheduleNextSlide(Math.max(1, sec) * 1000, currentSession);
    });
  } else {
    readerSwapPage(id, normalized);
  }
}

function bindReaderKeys() {
  if (readerKeyHandler) {
    document.removeEventListener("keydown", readerKeyHandler);
    document.removeEventListener("click", readerKeyHandler);
    readerKeyHandler = null;
  }
  if (app.view !== "reader") {
    stopSlideshow();
    return;
  }

  const id = app.params.id;
  const current = () => Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const mode = () => getReaderMode();
  const isRtl = () => mode() === "rtl" || mode() === "double-rtl";

  const advance = () => {
    const total = Number(app.readerTotal);
    if (!Number.isFinite(total) || total <= 0) return;
    const cur = current();
    const nav = getReaderNav(cur, total, mode());
    if (nav.nextPage !== null) {
      if (app.query && app.query.slideshow) {
        readerSlideshowSession++;
        if (slideshowTimer) {
          clearTimeout(slideshowTimer);
          slideshowTimer = null;
        }
        const currentSession = readerSlideshowSession;
        readerSwapPage(id, nav.nextPage, () => {
          if (currentSession !== readerSlideshowSession || app.view !== "reader") return;
          const sec = parseInt(app.query && app.query.slideshow, 10) || parseInt(localStorage.getItem("gv_slideshow_interval"), 10) || 5;
          scheduleNextSlide(Math.max(1, sec) * 1000, currentSession);
        });
      } else {
        readerSwapPage(id, nav.nextPage);
      }
    } else {
      exitReaderFullscreen();
      goReaderNext(id);
    }
  };

  const retreat = () => {
    const total = Number(app.readerTotal);
    if (!Number.isFinite(total) || total <= 0) return;
    const cur = current();
    const nav = getReaderNav(cur, total, mode());
    if (nav.prevPage !== null) {
      if (app.query && app.query.slideshow) {
        readerSlideshowSession++;
        if (slideshowTimer) {
          clearTimeout(slideshowTimer);
          slideshowTimer = null;
        }
        const currentSession = readerSlideshowSession;
        readerSwapPage(id, nav.prevPage, () => {
          if (currentSession !== readerSlideshowSession || app.view !== "reader") return;
          const sec = parseInt(app.query && app.query.slideshow, 10) || parseInt(localStorage.getItem("gv_slideshow_interval"), 10) || 5;
          scheduleNextSlide(Math.max(1, sec) * 1000, currentSession);
        });
      } else {
        readerSwapPage(id, nav.prevPage);
      }
    }
  };

  let lastKeyTime = 0;
  readerKeyHandler = (e) => {
    if (e.type === "keydown") {
      const now = Date.now();
      if (now - lastKeyTime < 150) return;
      lastKeyTime = now;
    }

    if (e.type === "click") {
      if (mode() === "webtoon") return;
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

    if (mode() === "webtoon") {
      if (e.key === "g" || e.key === "G") {
        e.preventDefault();
        const input = document.getElementById("reader-jump-input");
        if (readerFsActive || !input || input.offsetParent === null) {
          const val = window.prompt(t("jumpToPage") || `Jump to page (1-${app.readerTotal || 1}):`, String(current() + 1));
          if (val) {
            const p = parseInt(val, 10);
            if (!isNaN(p) && p >= 1) jumpToReaderPage(p - 1);
          }
        } else {
          input.focus();
          input.select();
        }
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        toggleReaderFullscreen();
      }
      return;
    }

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
    } else if (e.key === "g" || e.key === "G") {
      e.preventDefault();
      const input = document.getElementById("reader-jump-input");
      if (readerFsActive || !input || input.offsetParent === null) {
        const val = window.prompt(t("jumpToPage") || `Jump to page (1-${app.readerTotal || 1}):`, String(current() + 1));
        if (val) {
          const p = parseInt(val, 10);
          if (!isNaN(p) && p >= 1) jumpToReaderPage(p - 1);
        }
      } else {
        input.focus();
        input.select();
      }
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
          imgs.forEach(img => {
            const rect = img.getBoundingClientRect();
            const isTapped = rect.width > 0 && rect.height > 0 &&
              lastTapX >= rect.left && lastTapX <= rect.right &&
              lastTapY >= rect.top && lastTapY <= rect.bottom;
            if (isTapped) {
              const originX = Math.max(0, Math.min(100, Math.round(((lastTapX - rect.left) / rect.width) * 100)));
              const originY = Math.max(0, Math.min(100, Math.round(((lastTapY - rect.top) / rect.height) * 100)));
              img.style.transformOrigin = `${originX}% ${originY}%`;
            } else {
              img.style.transformOrigin = "50% 50%";
            }
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
  if (!document.fullscreenElement) {
    stopSlideshow();
    if (readerFsActive) {
      clearReaderFsState();
      syncReaderUrl();
    }
  }
}

function syncReaderUrl() {
  if (app.view !== "reader" || !app.params.id) return;
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  const target = navHash("reader", { id: app.params.id, page }, readerContext());
  if (location.hash !== target) {
    history.replaceState(null, "", target);
  }
}

function readerSwapPage(id, target, onSwapComplete) {
  if (typeof id === "number" && (typeof target === "function" || target === undefined)) {
    onSwapComplete = target;
    target = id;
    id = app.params.id;
  }
  const total = Number(app.readerTotal);
  if (!Number.isFinite(total) || total <= 0) { exitReaderFullscreen(); return; }
  if (target >= total) { exitReaderFullscreen(); goReaderNext(id); return; }
  if (target < 0) { exitReaderFullscreen(); return; }

  const mode = getReaderMode();
  const isDoubleMode = mode.startsWith("double");
  if (isDoubleMode && target > 0 && target % 2 === 0) {
    target = target - 1;
  }
  app.params.page = String(target);

  const spreadEl = document.querySelector(".reader-spread");

  // Reset zoom if active
  const readerArea = spreadEl || document.querySelector(".reader-img-wrap");
  if (readerArea && readerArea.classList.contains("zoomed")) {
    readerArea.classList.remove("zoomed");
    readerArea.querySelectorAll("img").forEach(img => {
      img.style.transform = "";
      img.style.transformOrigin = "";
    });
  }

  if (isDoubleMode && spreadEl) {
    const p1 = target;
    const p2 = target > 0 && (target + 1 < total) ? target + 1 : null;
    const imgs = spreadEl.querySelectorAll("img");
    if (imgs.length >= 2) {
      if (p2 !== null) {
        imgs[1].parentElement.style.display = "";
        if (typeof onSwapComplete === "function") {
          let pending = 2;
          const done = () => {
            pending--;
            if (pending === 0) onSwapComplete();
          };
          swapImageSmoothly(imgs[0], `/api/galleries/${id}/pages/${p1}`, p1, `Page ${p1 + 1}`, done);
          swapImageSmoothly(imgs[1], `/api/galleries/${id}/pages/${p2}`, p2, `Page ${p2 + 1}`, done);
        } else {
          swapImageSmoothly(imgs[0], `/api/galleries/${id}/pages/${p1}`, p1, `Page ${p1 + 1}`);
          swapImageSmoothly(imgs[1], `/api/galleries/${id}/pages/${p2}`, p2, `Page ${p2 + 1}`);
        }
      } else {
        swapImageSmoothly(imgs[0], `/api/galleries/${id}/pages/${p1}`, p1, `Page ${p1 + 1}`, onSwapComplete);
        imgs[1]._swapReqId = (imgs[1]._swapReqId || 0) + 1;
        imgs[1].removeAttribute("src");
        imgs[1].dataset.page = "";
        imgs[1].alt = "";
        imgs[1].parentElement.style.display = "none";
      }
      const jump = document.getElementById("reader-jump-input");
      if (jump) jump.value = String(p1 + 1);
      const suffix = document.querySelector(".reader-page-indicator > span");
      if (suffix) suffix.textContent = readerJumpSuffix(p1, p2, total, (app.readerGallery && app.readerGallery.file_size) || 0, p2 !== null);
    } else {
      renderReader();
      if (typeof onSwapComplete === "function") onSwapComplete();
      return;
    }
  } else if (!isDoubleMode && !spreadEl) {
    const img = document.getElementById("reader-img");
    if (img) {
      swapImageSmoothly(img, `/api/galleries/${id}/pages/${target}`, target, `Page ${target + 1}`, onSwapComplete);
      img.dataset.next = target + 1 < total ? String(target + 1) : "";
    } else {
      if (typeof onSwapComplete === "function") onSwapComplete();
    }
    const jump = document.getElementById("reader-jump-input");
    if (jump) jump.value = String(target + 1);
    const suffix = document.querySelector(".reader-page-indicator > span");
    if (suffix) suffix.textContent = readerJumpSuffix(target, null, total, (app.readerGallery && app.readerGallery.file_size) || 0, false);
  } else {
    // Mode mismatch transition: in-place re-render (preserves .reader fullscreen)
    const readerEl = document.querySelector(".reader");
    if (readerEl) {
      readerEl.innerHTML = buildReaderInnerHtml(id, target, total, mode, app.readerGallery);
      initReaderGestures();
      if (typeof onSwapComplete === "function") {
        const firstImg = readerEl.querySelector("img");
        if (firstImg && typeof firstImg.decode === "function") {
          firstImg.decode().then(onSwapComplete).catch(onSwapComplete);
        } else {
          onSwapComplete();
        }
      }
    } else {
      renderReader();
      if (typeof onSwapComplete === "function") onSwapComplete();
      return;
    }
  }

  // Update nav buttons in DOM if present (non-fullscreen mode)
  const navContainer = document.querySelector(".reader .nav");
  if (navContainer) {
    const nav = getReaderNav(target, total, mode);
    const isRtl = mode === "rtl" || mode === "double-rtl";
    const prevBtn = nav.prevPage !== null
      ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nav.prevPage }, readerContext())}">${esc(t("prev"))}</a>`
      : `<span>${esc(t("prev"))}</span>`;
    const nextBtn = nav.nextPage !== null
      ? `<a class="btn btn-secondary" href="${navHash("reader", { id, page: nav.nextPage }, readerContext())}">${esc(t("next"))}</a>`
      : `<span>${esc(t("next"))}</span>`;
    navContainer.innerHTML = isRtl
      ? `${nextBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, readerContext())}">${esc(t("allPages"))}</a>${prevBtn}`
      : `${prevBtn}<a class="btn btn-secondary" href="${navHash("gallery", { id }, readerContext())}">${esc(t("allPages"))}</a>${nextBtn}`;
  }

  updateProgressDebounced(id, target, total);
  if (target + 1 < total) { const pre = new Image(); pre.src = `/api/galleries/${id}/pages/${target + 1}`; }
  if (isDoubleMode && target + 2 < total) { const pre2 = new Image(); pre2.src = `/api/galleries/${id}/pages/${target + 2}`; }
  syncReaderUrl();
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
    location.hash = navHash("reader", { id: r.id, page: 0 }, readerContext());
  } catch (_) { /* no next gallery */ }
}

let readerSlideshowSession = 0;

async function scheduleNextSlide(userIntervalMs, sessionId) {
  if (sessionId !== readerSlideshowSession || app.view !== "reader") {
    return;
  }
  const id = app.params.id;
  const total = Number(app.readerTotal);
  if (!Number.isFinite(total) || total <= 0) {
    stopSlideshow();
    return;
  }
  const cur = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  let delayMs = userIntervalMs;

  const g = app.readerGallery;
  const pageObj = g && Array.isArray(g.pages) ? g.pages[cur] : null;
  const mediaType = pageObj && pageObj.media_type ? String(pageObj.media_type).toLowerCase() : "";

  if (mediaType.includes("gif") || mediaType.includes("webp")) {
    try {
      const res = await fetch(`/api/galleries/${id}/pages/${cur}/meta`).then(r => r.ok ? r.json() : null);
      if (sessionId !== readerSlideshowSession || app.view !== "reader") {
        return;
      }
      if (res && res.animated && typeof res.duration_ms === "number" && res.duration_ms > 0) {
        delayMs = Math.max(res.duration_ms, userIntervalMs);
      }
    } catch (_) {
      // ignore network errors and fallback to userIntervalMs
    }
  }

  if (sessionId !== readerSlideshowSession || app.view !== "reader") {
    return;
  }

  slideshowTimer = setTimeout(() => {
    slideshowTimer = null;
    if (sessionId !== readerSlideshowSession || app.view !== "reader") {
      return;
    }
    const currentId = app.params.id;
    const currentTotal = Number(app.readerTotal);
    if (!Number.isFinite(currentTotal) || currentTotal <= 0) {
      stopSlideshow();
      return;
    }
    const currentPage = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
    const mode = getReaderMode();
    const nav = getReaderNav(currentPage, currentTotal, mode);
    if (nav.nextPage !== null) {
      readerSwapPage(currentId, nav.nextPage, () => {
        if (sessionId !== readerSlideshowSession || app.view !== "reader") {
          return;
        }
        scheduleNextSlide(userIntervalMs, sessionId);
      });
    } else {
      stopSlideshow();
      exitReaderFullscreen();
      goReaderNext(currentId);
    }
  }, delayMs);
}

function resetSlideshow() {
  readerSlideshowSession++;
  if (slideshowTimer) {
    clearTimeout(slideshowTimer);
    slideshowTimer = null;
  }
  if (app.view !== "reader" || !app.query || !app.query.slideshow) {
    return;
  }
  const sec = parseInt(app.query.slideshow, 10) || parseInt(localStorage.getItem("gv_slideshow_interval"), 10) || 5;
  const intervalMs = Math.max(1, sec) * 1000;
  scheduleNextSlide(intervalMs, readerSlideshowSession);
}
window.resetSlideshow = resetSlideshow;

function startSlideshow(sec) {
  readerSlideshowSession++;
  if (slideshowTimer) {
    clearTimeout(slideshowTimer);
    slideshowTimer = null;
  }
  const intervalMs = Math.max(1, parseInt(sec, 10) || 5) * 1000;
  if (!document.fullscreenElement) {
    enterReaderFullscreen();
  }
  scheduleNextSlide(intervalMs, readerSlideshowSession);
}
window.startSlideshow = startSlideshow;

function stopSlideshow() {
  readerSlideshowSession++;
  if (slideshowTimer) {
    clearTimeout(slideshowTimer);
    slideshowTimer = null;
  }
  if (app.query && app.query.slideshow !== undefined) {
    delete app.query.slideshow;
    syncReaderUrl();
  }
}
window.stopSlideshow = stopSlideshow;

window.startReaderSlideshow = function() {
  const el = document.getElementById("reader-slideshow-sec");
  const raw = el ? parseInt(el.value, 10) : 0;
  const sec = (raw && raw > 0) ? raw : (parseInt(localStorage.getItem("gv_slideshow_interval"), 10) || 5);
  localStorage.setItem("gv_slideshow_interval", String(sec));
  app.query.slideshow = String(sec);
  syncReaderUrl();
  startSlideshow(sec);
};
