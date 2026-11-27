"use strict";

/**
 * Stand-in for the legacy frontend worker (`frontend/sw.js`, cache
 * `gv-shell-v14`), served at /legacy-sw.js only by the mock e2e harness.
 *
 * The real worker is served at /sw.js, which the new build occupies, so the
 * harness needs a second script URL to put a browser into the pre-swap state
 * (legacy worker active and controlling + `gv-shell-v14` populated) before it
 * registers the new build.
 *
 * The document strategy reproduces the reported failure: a navigation is
 * answered from the stale shell cache, so the deployed build sees the old
 * document with assets that no longer exist.
 */
self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (request.mode !== "navigate" && request.destination !== "document") return;

  event.respondWith(
    (async () => {
      const cached = await caches.match("/index.html", { ignoreSearch: true });
      return cached ?? fetch(request);
    })(),
  );
});
