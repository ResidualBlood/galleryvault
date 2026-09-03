"use strict";

const CACHE = "gv-shell-v3";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/assets/styles.css",
  "/assets/icon.svg",
  "/assets/i18n.js",
  "/assets/locales/zh.js",
  "/assets/locales/en.js",
  "/assets/core.js",
  "/assets/state.js",
  "/assets/utils.js",
  "/assets/components.js",
  "/assets/events.js",
  "/assets/app.js",
  "/assets/views/welcome.js",
  "/assets/views/browse.js",
  "/assets/views/library.js",
  "/assets/views/discover.js",
  "/assets/views/gallery.js",
  "/assets/views/reader.js",
  "/assets/views/reader-webtoon.js",
  "/assets/views/favorites.js",
  "/assets/views/downloads.js",
  "/assets/views/tags.js",
  "/assets/views/history.js",
  "/assets/views/settings.js",
  "/assets/views/logs.js",
  "/assets/views/updates.js",
  "/assets/views/duplicates.js",
  "/assets/views/recycle.js",
  "/assets/views/integrity.js"
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
