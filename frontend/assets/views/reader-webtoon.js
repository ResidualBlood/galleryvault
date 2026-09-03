"use strict";

let webtoonObserver = null;
let webtoonProgressTimer = null;
let webtoonLastPage = null;

function cleanupWebtoon() {
  if (webtoonObserver) {
    webtoonObserver.disconnect();
    webtoonObserver = null;
  }
  if (webtoonProgressTimer) {
    clearTimeout(webtoonProgressTimer);
    webtoonProgressTimer = null;
  }
  webtoonLastPage = null;
}

function jumpToWebtoonPage(targetPage) {
  const id = app.params.id;
  const total = app.readerTotal || 1;
  const clamped = Math.max(0, Math.min(total - 1, targetPage));
  const img = document.querySelector(`.webtoon-strip img[data-page="${clamped}"]`);
  if (img) img.scrollIntoView({ block: "start" });
  app.params.page = String(clamped);
  webtoonLastPage = clamped;
  syncReaderUrl();
  const jump = document.getElementById("reader-jump-input");
  if (jump) jump.value = String(clamped + 1);
  api("PUT", `/api/galleries/${id}/progress`, { current_page: clamped, total_pages: total }).catch(() => {});
}

function bindWebtoonObserver(id, total) {
  cleanupWebtoon();
  const imgs = document.querySelectorAll(".webtoon-strip img");
  if (!imgs.length) return;
  const visible = new Map();
  const commit = (page) => {
    if (page === webtoonLastPage) return;
    webtoonLastPage = page;
    app.params.page = String(page);
    syncReaderUrl();
    const jump = document.getElementById("reader-jump-input");
    if (jump) jump.value = String(page + 1);
    clearTimeout(webtoonProgressTimer);
    webtoonProgressTimer = setTimeout(() => {
      api("PUT", `/api/galleries/${id}/progress`, { current_page: page, total_pages: total }).catch(() => {});
    }, 400);
  };
  webtoonObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const page = parseInt(entry.target.getAttribute("data-page"), 10);
      if (Number.isNaN(page)) continue;
      if (entry.isIntersecting && entry.intersectionRatio > 0.12) visible.set(page, entry);
      else visible.delete(page);
    }
    if (!visible.size) return;
    let bestPage = null;
    let bestDist = Infinity;
    visible.forEach((entry, page) => {
      const dist = Math.abs(entry.boundingClientRect.top);
      if (dist < bestDist) {
        bestDist = dist;
        bestPage = page;
      }
    });
    if (bestPage != null) commit(bestPage);
  }, { root: null, threshold: [0.12, 0.35, 0.6, 0.85] });
  imgs.forEach((img) => webtoonObserver.observe(img));
}

async function renderWebtoonReader() {
  if (readerTouchCleanup) {
    readerTouchCleanup();
    readerTouchCleanup = null;
  }
  cleanupWebtoon();
  const id = app.params.id;
  const page = Math.max(0, parseInt(app.params.page || "0", 10) || 0);
  try {
    let g = app.readerGallery;
    if (!g || String(g.id) !== String(id)) {
      g = await api("GET", `/api/galleries/${id}`);
      app.readerGallery = g;
    }
    const total = g.page_count;
    app.readerTotal = total;
    const imgs = [];
    for (let i = 0; i < total; i++) {
      imgs.push(
        `<img loading="lazy" data-page="${i}" src="/api/galleries/${id}/pages/${i}" alt="Page ${i + 1}">`
      );
    }
    const innerHtml = `
      <div class="reader-bar toolbar">
        <a class="link-button" href="${navHash("gallery", { id }, libraryContext())}">← ${esc(t("details"))}</a>
        <span class="reader-page-indicator" style="display:inline-flex;align-items:center;gap:4px;">
          <form data-action="reader-jump" style="display:inline-flex;align-items:center;margin:0;padding:0;">
            <input id="reader-jump-input" class="reader-jump-input" type="number" min="1" max="${total}" value="${page + 1}" style="width:4.2em;padding:2px 4px;text-align:center;font-size:13px;border-radius:4px;border:1px solid var(--line);background:var(--panel-2);color:inherit;" title="${esc(t("jumpToPageHint"))}" aria-label="${esc(t("pageNumber"))}">
          </form>
          <span>/ ${total} · ${fmtSize(g.file_size || 0)}</span>
        </span>
        <span class="reader-actions">
          <button class="btn btn-secondary" data-action="reader-mode" type="button" title="${esc(t("readerMode"))}">${esc(t("readerMode"))}: ${esc(readerModeLabel("webtoon"))}</button>
          <button class="btn btn-secondary" data-action="reader-fit" type="button">${esc(t("readerFit"))}</button>
          <button class="btn btn-secondary" data-action="reader-fullscreen" type="button">${esc(t("readerFullscreen"))}</button>
        </span>
      </div>
      <div class="webtoon-strip">${imgs.join("")}</div>`;
    const existingReader = $view().querySelector(".reader");
    if (existingReader) {
      existingReader.classList.add("reader-webtoon");
      existingReader.innerHTML = innerHtml;
    } else {
      $view().innerHTML = `<div class="reader reader-webtoon">${innerHtml}</div>`;
    }
    requestAnimationFrame(() => {
      const target = document.querySelector(`.webtoon-strip img[data-page="${page}"]`);
      if (target) target.scrollIntoView({ block: "start" });
      bindWebtoonObserver(id, total);
      webtoonLastPage = page;
      api("PUT", `/api/galleries/${id}/progress`, { current_page: page, total_pages: total }).catch(() => {});
    });
  } catch (e) {
    $view().innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}
