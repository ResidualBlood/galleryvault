/// <reference lib="webworker" />
/**
 * GalleryVault service worker (injectManifest).
 *
 * The URL is the same as the legacy worker (`/sw.js`), so an existing install
 * replaces it in place. Three rules make the switch and an eventual rollback
 * safe:
 *
 * - a *normal* update (an earlier `gv-precache-*` build is live) never calls
 *   skipWaiting: it waits until the user confirms the prompt, so an open
 *   reader is never swapped mid-session;
 * - the old→new swap (a legacy `gv-shell-*` cache exists, or no earlier
 *   `gv-precache-*` build is live) skips waiting and claims immediately.
 *   A waiting worker would leave the first cold start after the deploy on the
 *   stale shell document, whose assets are gone (white screen);
 * - activate deletes every legacy `gv-shell-*` cache and every older
 *   `gv-precache-*` cache, and - when it took over a window that was already
 *   controlled - navigates that window once so the stale document is replaced
 *   during the same start instead of on the next one.
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
  registration: ServiceWorkerRegistration;
  addEventListener(type: "install" | "activate", listener: (event: ExtendableEvent) => void): void;
  addEventListener(type: "message", listener: (event: ExtendableMessageEvent) => void): void;
  addEventListener(type: "fetch", listener: (event: FetchEvent) => void): void;
  skipWaiting(): Promise<void>;
  clients: Clients;
}

const sw = self as unknown as ServiceWorkerScope;

const API_PREFIX = ["", "api", ""].join("/");
const CACHE_PREFIX = "gv-precache-";
const LEGACY_CACHE_PREFIX = "gv-shell-";
const MIGRATION_PARAM = "gv_sw_migrate";
/** How long activate stays alive so the forced navigation can commit. */
const MIGRATION_SETTLE_MS = 1_500;
const INDEX_URL = new URL("/index.html", sw.location.origin).href;
// Keep this exact expression: workbox-build replaces `self.__WB_MANIFEST`
// after the service worker is bundled.
const MANIFEST = (self as unknown as ServiceWorkerScope).__WB_MANIFEST;
const CACHE = `${CACHE_PREFIX}${manifestVersion(MANIFEST)}`;
const PRECACHED_PATHS = new Set(
  MANIFEST.map((entry) => new URL(entry.url, sw.location.origin).pathname),
);

/**
 * True when a worker was already in control while this one installed, i.e.
 * the install is an update over an open (possibly stale) page. A first-ever
 * install has no active worker and must not navigate anything.
 */
let tookOverFromActiveWorker = false;

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

/**
 * Cache state that decides the install strategy. `previousBuild` ignores our
 * own cache entry, which `precache()` may already have created.
 */
async function cacheState(): Promise<{ legacy: boolean; previousBuild: boolean }> {
  const keys = await caches.keys();
  return {
    legacy: keys.some((key) => key.startsWith(LEGACY_CACHE_PREFIX)),
    previousBuild: keys.some((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE),
  };
}

/**
 * Load controlled windows once with the new build. `clients.navigate()` works
 * for a stale shell too: the old page never runs this build's registration
 * code, so a page-side listener could not replace it.
 */
async function reloadControlledWindows(): Promise<void> {
  const windows = await sw.clients.matchAll({ type: "window" });
  const marker = CACHE.slice(CACHE_PREFIX.length);
  for (const client of windows) {
    if (!client.url.startsWith("http")) continue;
    const target = new URL(client.url);
    // A same-URL client.navigate() counts as a reload and makes the tab go
    // away while activate is still pending, so force a distinct document URL.
    // `register.ts` drops the marker again during boot.
    target.searchParams.set(MIGRATION_PARAM, marker);
    if (target.href === client.url) continue;
    // Not awaited: awaiting the navigation of a client that is being handed
    // over tears the tab down in Chromium. The settle wait below keeps this
    // worker alive until the navigation has committed instead.
    void client.navigate(target.href).catch(() => undefined);
  }
  await new Promise((resolve) => setTimeout(resolve, MIGRATION_SETTLE_MS));
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
  tookOverFromActiveWorker = Boolean(sw.registration.active);
  event.waitUntil(
    (async () => {
      await precache();
      const state = await cacheState();
      // Legacy shell present, or no new build was live yet: this is the
      // one-shot swap. Take over now so the very next document (including the
      // first cold start) is the new shell. A normal new→new update keeps the
      // waiting worker that drives the prompt.
      if (state.legacy || !state.previousBuild) await sw.skipWaiting();
    })(),
  );
});

sw.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      const legacyKeys = keys.filter((key) => key.startsWith(LEGACY_CACHE_PREFIX));
      const outdatedKeys = keys.filter(
        (key) => key.startsWith(CACHE_PREFIX) && key !== CACHE,
      );
      await Promise.all(
        [...legacyKeys, ...outdatedKeys].map((key) => caches.delete(key)),
      );
      await sw.clients.claim();
      // Only a takeover over legacy state needs the forced reload; a first
      // install has no stale document, and a user-approved new→new update is
      // reloaded by the page that asked for it.
      if (legacyKeys.length > 0 && tookOverFromActiveWorker) {
        await reloadControlledWindows();
      }
      tookOverFromActiveWorker = false;
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
