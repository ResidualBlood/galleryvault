"use strict";

const CACHE = "gv-shell-v4";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest?v=v4",
  "/assets/styles.css?v=v4",
  "/assets/icon.svg?v=v4",
  "/assets/i18n.js?v=v4",
  "/assets/locales/zh.js?v=v4",
  "/assets/locales/en.js?v=v4",
  "/assets/core.js?v=v4",
  "/assets/state.js?v=v4",
  "/assets/utils.js?v=v4",
  "/assets/components.js?v=v4",
  "/assets/events.js?v=v4",
  "/assets/app.js?v=v4",
  "/assets/views/welcome.js?v=v4",
  "/assets/views/browse.js?v=v4",
  "/assets/views/library.js?v=v4",
  "/assets/views/discover.js?v=v4",
  "/assets/views/gallery.js?v=v4",
  "/assets/views/reader.js?v=v4",
  "/assets/views/reader-webtoon.js?v=v4",
  "/assets/views/favorites.js?v=v4",
  "/assets/views/downloads.js?v=v4",
  "/assets/views/tags.js?v=v4",
  "/assets/views/history.js?v=v4",
  "/assets/views/settings.js?v=v4",
  "/assets/views/logs.js?v=v4",
  "/assets/views/updates.js?v=v4",
  "/assets/views/duplicates.js?v=v4",
  "/assets/views/recycle.js?v=v4",
  "/assets/views/integrity.js?v=v4",
  "/assets/views/series.js?v=v4",
  "/assets/views/archive.js?v=v4"
];

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
      caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
    }
    return res;
  };
  if (isAsset) {
    event.respondWith(
      fetch(req).then(put).catch(() => caches.match(req))
    );
    return;
  }
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then(put).catch(() => caches.match("/index.html")))
  );
});
