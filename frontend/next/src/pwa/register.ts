/**
 * Service worker registration and update lifecycle.
 *
 * Registration is deliberately not automatic in the SW itself: a new worker
 * installs but waits (`registerType: prompt`), and the page announces it so
 * the user can finish reading before applying the update.
 */

export const PWA_UPDATE_EVENT = "gv-pwa-update-available";

/** Query marker the worker adds to force a fresh document during a takeover. */
const MIGRATION_PARAM = "gv_sw_migrate";

const RELOAD_MARKER = "gv_sw_forced_reload_at";
const RELOAD_WINDOW_MS = 30_000;

let registration: ServiceWorkerRegistration | null = null;
let applyRequested = false;
let reloading = false;

/**
 * Reload at most once per takeover burst. The marker survives the reload (it
 * is in sessionStorage), so a controller that keeps firing controllerchange
 * cannot turn the migration into a reload loop.
 */
function reloadOnce(): void {
  if (reloading) return;
  try {
    const last = Number(sessionStorage.getItem(RELOAD_MARKER) ?? 0);
    if (Number.isFinite(last) && Date.now() - last < RELOAD_WINDOW_MS) return;
    sessionStorage.setItem(RELOAD_MARKER, String(Date.now()));
  } catch {
    // Storage can be unavailable (private mode); the in-memory guard remains.
  }
  reloading = true;
  window.location.reload();
}

/** Ask a waiting worker to take over; the controllerchange handler reloads. */
export function applyUpdate(): void {
  const waiting = registration?.waiting;
  if (!waiting) return;
  applyRequested = true;
  waiting.postMessage({ type: "SKIP_WAITING" });
}

/** Drop the migration marker so the address bar keeps the plain route. */
function clearMigrationMarker(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has(MIGRATION_PARAM)) return;
  url.searchParams.delete(MIGRATION_PARAM);
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function announce(): void {
  window.dispatchEvent(new Event(PWA_UPDATE_EVENT));
}

function watch(reg: ServiceWorkerRegistration): void {
  const track = (worker: ServiceWorker | null): void => {
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      if (worker.state === "installed" && navigator.serviceWorker.controller) {
        announce();
      }
    });
  };

  if (reg.waiting && navigator.serviceWorker.controller) announce();
  track(reg.installing);

  reg.addEventListener("updatefound", () => {
    track(reg.installing);
  });
}

/** Register `/sw.js` (same URL as the legacy worker) once per page load. */
export function registerPwa(): void {
  clearMigrationMarker();
  if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return;

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    // `clients.claim()` also fires on the very first install; only reload when
    // the user explicitly accepted an update.
    if (applyRequested) reloadOnce();
  });

  const start = () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((reg) => {
        registration = reg;
        watch(reg);
        // Check for a new build on focus, at most once every 30 minutes.
        let checked = Date.now();
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState !== "visible") return;
          if (Date.now() - checked < 30 * 60 * 1000) return;
          checked = Date.now();
          void reg.update().catch(() => undefined);
        });
      })
      .catch(() => undefined);
  };

  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
}
