/**
 * Shared, cached read of ``GET /api/settings``.
 *
 * Several views need one user preference at click time (the archive dialog
 * reads ``archive_quality`` today; the favourites list reads
 * ``favorites_cloud_open``). Fetching inside the click handler would race the
 * user gesture, so callers preload on mount and read the cached value.
 *
 * The cache is module-level: it lives as long as the SPA session. A failed
 * read leaves the previous value in place (or ``null``); callers must treat
 * ``null`` as "use the documented defaults", never as "settings are off".
 */
import { fetchSettings, type AppSettings } from "@/api/settings";

let cached: AppSettings | null = null;
let pending: Promise<AppSettings | null> | null = null;

/** Last successfully loaded settings, or ``null`` before the first read. */
export function peekAppSettings(): AppSettings | null {
  return cached;
}

/**
 * Resolve the cached settings, fetching when missing. ``force`` starts a
 * refresh but keeps serving the cached value until it lands.
 */
export function ensureAppSettings(force = false): Promise<AppSettings | null> {
  if (!force && cached) return Promise.resolve(cached);
  if (pending) return pending;
  pending = fetchSettings()
    .then((value) => {
      cached = value;
      return value;
    })
    .catch(() => cached)
    .finally(() => {
      pending = null;
    });
  return pending;
}

/** Drop the cache; used after a successful settings save and by tests. */
export function resetAppSettingsCache(): void {
  cached = null;
  pending = null;
}
