"use strict";

const CACHE = "gv-shell-v13";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest?v=v6",
  "/assets/styles.css?v=v6",
  "/assets/icon.svg?v=v7",
  "/assets/i18n.js?v=v6",
  "/assets/locales/zh.js?v=v6",
  "/assets/locales/en.js?v=v6",
  "/assets/core.js?v=v6",
  "/assets/state.js?v=v6",
  "/assets/utils.js?v=v6",
  "/assets/components.js?v=v6",
  "/assets/events.js?v=v6",
  "/assets/view-runtime.js?v=v6",
  "/assets/app.js?v=v6",
  "/assets/views/welcome.js?v=v6",
  "/assets/views/browse.js?v=v6",
  "/assets/views/library.js?v=v6",
  "/assets/views/discover.js?v=v6",
  "/assets/views/gallery.js?v=v6",
  "/assets/views/reader.js?v=v6",
  "/assets/views/reader-webtoon.js?v=v6",
  "/assets/views/favorites.js?v=v6",
  "/assets/views/downloads.js?v=v6",
  "/assets/views/tags.js?v=v6",
  "/assets/views/history.js?v=v6",
  "/assets/views/settings.js?v=v6",
  "/assets/views/logs.js?v=v6",
  "/assets/views/updates.js?v=v6",
  "/assets/views/duplicates.js?v=v6",
  "/assets/views/recycle.js?v=v6",
  "/assets/views/integrity.js?v=v6",
  "/assets/views/series.js?v=v6",
  "/assets/views/archive.js?v=v6"
];

// Direct gallery media and thumbnails bypass SW CacheStorage to rely on browser HTTP cache (immutable / ETag)
function isGalleryMedia(url) {
  const path = url.pathname || "";
  if (path.includes("/pages/") || path.includes("/thumb/")) return true;
  if (path.startsWith("/api/favorites/cover")) return true;
  return false;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || isGalleryMedia(url)) return;
  const dest = req.destination;
  if (dest === "image" || dest === "video" || dest === "audio") return;
  const isAsset = dest === "script" || dest === "style" ||
    url.pathname.endsWith(".js") || url.pathname.endsWith(".css");
  const isShell = dest === "document" ||
    url.pathname.endsWith(".html") || url.pathname === "/" ||
    url.pathname === "/manifest.webmanifest";
  if (!isAsset && !isShell) return;
  const put = (res) => {
    if (res && res.ok && res.type === "basic") {
      const copy = res.clone();
      // The write must be tied to the event: otherwise the worker can be
      // terminated before cache.put() finishes and the entry is lost.
      event.waitUntil(
        caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {})
      );
    }
    return res;
  };
  // ignoreSearch: dynamic imports (e.g. locales/en.js) omit the ?v= query
  // string used by the SHELL entries, so match by path.
  if (isAsset) {
    event.respondWith(
      fetch(req).then(put).catch(() =>
        caches.match(req, {ignoreSearch: true})
      )
    );
    return;
  }
  // Documents (and the manifest): network-first so a new deploy is picked up
  // immediately. cache:"no-store" bypasses the HTTP cache, otherwise the
  // browser could answer this "network-first" request from its own cache.
  // Fall back to the cached shell only when the network fails.
  event.respondWith(
    fetch(req, {cache: "no-store"}).then(put).catch(() =>
      caches.match(req, {ignoreSearch: true}).then((hit) =>
        hit || caches.match("/index.html", {ignoreSearch: true})
      )
    )
  );
});
