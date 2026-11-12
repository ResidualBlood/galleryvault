/// <reference lib="webworker" />
/**
 * GalleryVault service worker (injectManifest).
 *
 * The URL is the same as the legacy worker (`/sw.js`), so an existing install
 * replaces it in place. Two rules make the switch and an eventual rollback
 * safe:
 *
 * - install never calls skipWaiting: an update waits until the user confirms
 *   the prompt, so an open reader is never swapped mid-session;
 * - activate deletes every legacy `gv-shell-*` cache (the old worker's cache
 *   names) and every older `gv-precache-*` cache, so stale shells cannot win.
 *
 * API and media requests are never cached here, and cross-origin requests are
 * ignored entirely: EH image hosts stay on the browser HTTP cache.
 */

interface PrecacheEntry {
  url: string;
  revision: string | null;
}

interface ServiceWorkerScope {
  __WB_MANIFEST: PrecacheEntry[];
  location: Location;
  addEventListener(type: "install" | "activate", listener: (event: ExtendableEvent) => void): void;
  addEventListener(type: "message", listener: (event: ExtendableMessageEvent) => void): void;
  addEventListener(type: "fetch", listener: (event: FetchEvent) => void): void;
  skipWaiting(): Promise<void>;
  clients: { claim(): Promise<void> };
}

const sw = self as unknown as ServiceWorkerScope;

const API_PREFIX = ["", "api", ""].join("/");
const CACHE_PREFIX = "gv-precache-";
const LEGACY_CACHE_PREFIX = "gv-shell-";
const INDEX_URL = new URL("/index.html", sw.location.origin).href;
// Keep this exact expression: workbox-build replaces `self.__WB_MANIFEST`
// after the service worker is bundled.
const MANIFEST = (self as unknown as ServiceWorkerScope).__WB_MANIFEST;
const CACHE = `${CACHE_PREFIX}${manifestVersion(MANIFEST)}`;
const PRECACHED_PATHS = new Set(
  MANIFEST.map((entry) => new URL(entry.url, sw.location.origin).pathname),
);

/** Stable, build-sensitive cache name derived from the injected revisions. */
function manifestVersion(entries: PrecacheEntry[]): string {
  let hash = 5381;
  for (const entry of entries) {
    const value = `${entry.url}@${entry.revision ?? ""};`;
    for (let i = 0; i < value.length; i += 1) {
      hash = ((hash << 5) + hash + value.charCodeAt(i)) >>> 0;
    }
  }
  return hash.toString(36);
}

function revisionUrl(entry: PrecacheEntry): string {
  const url = new URL(entry.url, sw.location.origin);
  if (entry.revision) url.searchParams.set("__WB_REVISION__", entry.revision);
  return url.href;
}

async function precache(): Promise<void> {
  const cache = await caches.open(CACHE);
  await Promise.all(
    MANIFEST.map(async (entry) => {
      const response = await fetch(revisionUrl(entry), { cache: "reload" });
      if (!response.ok) {
        throw new Error(`precache ${entry.url}: HTTP ${response.status}`);
      }
      // Key by the clean URL so navigation and asset lookups can match it.
      await cache.put(new URL(entry.url, sw.location.origin).href, response);
    }),
  );
}

/** API/auth, gallery media and anything cross-origin bypass the worker. */
function bypassesWorker(request: Request, url: URL): boolean {
  if (request.method !== "GET") return true;
  if (url.origin !== sw.location.origin) return true;

  const path = url.pathname;
  if (path.startsWith(API_PREFIX)) return true;
  if (path === "/login" || path === "/logout") return true;
  if (path.includes("/pages/") || path.includes("/thumb/")) return true;
  if (path.startsWith(`${API_PREFIX}favorites/cover`)) return true;

  const destination = request.destination;
  if (destination === "image" || destination === "video" || destination === "audio") {
    return true;
  }
  return false;
}

function isAsset(request: Request, url: URL): boolean {
  const destination = request.destination;
  if (destination === "script" || destination === "style" || destination === "font") {
    return true;
  }
  return /\.(?:js|mjs|css|woff2?|ttf)$/i.test(url.pathname);
}

async function networkFirstDocument(request: Request): Promise<Response> {
  try {
    const response = await fetch(request, { cache: "no-store" });
    if (response.ok && response.type === "basic") {
      const copy = response.clone();
      const cache = await caches.open(CACHE);
      await cache.put(INDEX_URL, copy).catch(() => undefined);
    }
    return response;
  } catch {
    const cached = await caches.match(INDEX_URL, { ignoreSearch: true });
    return cached ?? Response.error();
  }
}

async function networkFirstAsset(request: Request): Promise<Response> {
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic") {
      const copy = response.clone();
      const cache = await caches.open(CACHE);
      await cache.put(request, copy).catch(() => undefined);
    }
    return response;
  } catch {
    const cached = await caches.match(request, { ignoreSearch: true });
    return cached ?? Response.error();
  }
}

sw.addEventListener("install", (event) => {
  // No skipWaiting on purpose: a waiting worker is what drives the update
  // prompt, and it keeps the current reader session on the old build.
  event.waitUntil(precache());
});

sw.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.map((key) => {
          const legacy = key.startsWith(LEGACY_CACHE_PREFIX);
          const outdated = key.startsWith(CACHE_PREFIX) && key !== CACHE;
          return legacy || outdated ? caches.delete(key) : Promise.resolve(false);
        }),
      );
      await sw.clients.claim();
    })(),
  );
});

sw.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    event.waitUntil(sw.skipWaiting());
  }
});

sw.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (bypassesWorker(request, url)) return;

  if (request.mode === "navigate" || request.destination === "document") {
    event.respondWith(networkFirstDocument(request));
    return;
  }

  if (PRECACHED_PATHS.has(url.pathname)) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(request, { ignoreSearch: true });
        return cached ?? fetch(request);
      })(),
    );
    return;
  }

  if (isAsset(request, url)) {
    event.respondWith(networkFirstAsset(request));
  }
});
