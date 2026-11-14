/**
 * Decision table for opening a favourites entry.
 *
 * Favourites mix two sources: local galleries (``gallery_id``) and cloud-only
 * entries that only exist on E-Hentai (``gid`` + ``token``). Local rows always
 * open the in-app detail. Cloud rows follow the ``favorites_cloud_open`` user
 * setting (J6 x J5): ``app`` keeps the reader inside the app so online reading
 * progress and download context stay continuous, ``external`` opens the
 * E-Hentai page in a new tab.
 *
 * Two degenerate cases always fall back to the external page rather than
 * pushing a guaranteed-broken online detail:
 *
 * * dirty data without a token (the online-detail route needs ``gid/token``);
 * * no ExHentai cookies configured, which makes ``/api/eh/status`` and the
 *   online detail unusable (caller may surface a hint for that case).
 */
import type { FavoriteItem } from "@/api/favorites";
import type { AppSettings } from "@/api/settings";

export type CloudOpenMode = "app" | "external";

export type FavoriteOpenTarget =
  | { kind: "local"; id: number }
  | { kind: "online"; gid: number; token: string }
  | { kind: "external"; url: string };

export interface FavoriteOpenPlan {
  target: FavoriteOpenTarget;
  /**
   * True when the preference is ``app`` but the entry fell back to the
   * external page because no ExHentai cookies are configured.
   */
  cookieFallback: boolean;
}

/** ``app`` unless the saved value is explicitly ``external``. */
export function cloudOpenMode(settings: AppSettings | null | undefined): CloudOpenMode {
  return settings?.favorites_cloud_open === "external" ? "external" : "app";
}

/**
 * Whether the app can serve an online detail request. Only an explicit
 * ``false`` from the backend disables it; an unread settings payload keeps the
 * documented default instead of silently changing behaviour.
 */
export function onlineAccessAvailable(settings: AppSettings | null | undefined): boolean {
  return settings?.exhentai_cookie_configured !== false;
}

export function externalUrl(item: FavoriteItem): string {
  if (item.url && /^https?:\/\//i.test(item.url)) return item.url;
  return `https://e-hentai.org/g/${item.gid}/${encodeURIComponent(item.token)}/`;
}

export function planFavoriteOpen(
  item: FavoriteItem,
  settings: AppSettings | null | undefined,
): FavoriteOpenPlan {
  if (item.gallery_id) {
    return { target: { kind: "local", id: item.gallery_id }, cookieFallback: false };
  }
  const token = typeof item.token === "string" ? item.token.trim() : "";
  if (cloudOpenMode(settings) === "app" && token && onlineAccessAvailable(settings)) {
    return { target: { kind: "online", gid: item.gid, token }, cookieFallback: false };
  }
  return {
    target: { kind: "external", url: externalUrl(item) },
    cookieFallback: cloudOpenMode(settings) === "app" && Boolean(token) && !onlineAccessAvailable(settings),
  };
}
