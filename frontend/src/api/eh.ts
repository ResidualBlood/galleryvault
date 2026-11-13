/**
 * Online (E-Hentai / ExHentai) endpoints.
 *
 * Contract: PLAN-frontend-rewrite §3.3 and backend `app/routers/eh.py` /
 * `app/routers/eh_online.py`. The browser never talks to ExHentai directly;
 * the backend parses pages and returns JSON. Thumbnails / gallery images are
 * hot-linked from `ehgt.org` by the views (CSP `img-src`).
 */
import { ep, request } from "./client";

export const ehSearchEp = ep("GET", "/api/eh/search");
export const ehGalleryEp = ep("GET", "/api/eh/galleries/{gid}/{token}");
export const ehPagesEp = ep("GET", "/api/eh/galleries/{gid}/{token}/pages");
export const ehStatusEp = ep("GET", "/api/eh/status");

export type OnlineListType = "search" | "popular" | "watched" | "toplist";
export type OnlineState = "ok" | "empty" | "challenge" | "banned" | "auth" | "error";

export const ONLINE_LIST_TYPES: readonly OnlineListType[] = [
  "search",
  "popular",
  "watched",
  "toplist",
];

export const ONLINE_TOPLIST_VALUES: readonly number[] = [11, 12, 13, 15];

export interface OnlineSearchQuery {
  q?: string;
  /** ExHentai `f_cats` disabled-category bitmask (0 = every category on). */
  category?: number | null;
  min_rating?: number | null;
  list?: OnlineListType;
  tl?: number | null;
  next?: string | null;
}

export interface OnlineDownloadState {
  id?: number;
  status?: string | null;
  current_page?: number | null;
  total_pages?: number | null;
}

export interface OnlineSearchItem {
  gid: number;
  token: string;
  title: string;
  url?: string | null;
  thumb?: string | null;
  category: string;
  pages: number;
  rating?: number | null;
  /** Tags parsed from the list-page HTML (no extra EH request). */
  tags?: OnlineTag[] | null;
  posted?: string | null;
  uploader?: string | null;
  in_library?: boolean;
  gallery_id?: number | null;
  favorited?: boolean;
  favcat?: number | null;
  download_status?: string | null;
}

export interface OnlineSearchResponse {
  state: string;
  items: OnlineSearchItem[];
  next: string | null;
  q?: string;
  category?: string | null;
  min_rating?: number | null;
  list?: string;
  tl?: number | null;
}

export interface OnlineThumb {
  url: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface OnlineTag {
  namespace: string;
  name: string;
  display?: string | null;
}

export interface OnlineNewer {
  gid: number;
  token: string;
}

export interface OnlineGallery {
  gid: number;
  token: string;
  title: string;
  title_jpn?: string | null;
  category: string;
  uploader?: string | null;
  posted?: string | null;
  pages: number;
  rating?: number | null;
  file_size?: number | null;
  thumb?: string | null;
  tags: OnlineTag[];
  newer: OnlineNewer | null;
  parent_gid?: number | null;
  in_library: boolean;
  gallery_id?: number | null;
  favorited: boolean;
  favcat?: number | null;
  download: OnlineDownloadState | null;
}

export interface OnlineDetailResponse {
  state: string;
  gallery: OnlineGallery | null;
}

export interface OnlinePreviewItem {
  index: number;
  thumb: OnlineThumb | null;
}

export interface OnlinePreviewPage {
  state: string;
  p: number;
  per_page: number;
  total: number | null;
  items: OnlinePreviewItem[];
}

export interface OnlineStatusItem {
  gid: number;
  in_library: boolean;
  gallery_id: number | null;
  favorited: boolean;
  favcat: number | null;
  download_status: string | null;
}

/**
 * Normalise every backend state into the four page-level states the views
 * render. `not_logged_in` / `no_exhentai_access` are both "auth" because the
 * fix is the same: refresh the configured ExHentai cookies in settings.
 */
export function mapOnlineState(raw: unknown): OnlineState {
  const value = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  switch (value) {
    case "ok":
      return "ok";
    case "empty":
      return "empty";
    case "challenge":
      return "challenge";
    case "banned":
    case "ip_banned":
      return "banned";
    case "auth":
    case "not_logged_in":
    case "no_exhentai_access":
      return "auth";
    default:
      return "error";
  }
}

export function isErrorState(state: OnlineState): boolean {
  return state !== "ok" && state !== "empty";
}

/** Cursor accepted by `/api/eh/search`: paginated (`1-2`) or toplist (`3`). */
export function isValidCursor(cursor: string, list: OnlineListType = "search"): boolean {
  if (!cursor) return false;
  if (list === "toplist") return /^\d+$/.test(cursor) && Number(cursor) < 200;
  return /^\d+(-\d+)?$/.test(cursor);
}

export function buildSearchParams(query: OnlineSearchQuery): Record<string, string> {
  const out: Record<string, string> = {};
  const q = typeof query.q === "string" ? query.q.trim() : "";
  if (q) out.q = q;
  if (typeof query.category === "number" && query.category > 0) {
    out.category = String(query.category);
  }
  if (typeof query.min_rating === "number" && Number.isFinite(query.min_rating)) {
    out.min_rating = String(query.min_rating);
  }
  if (query.list) out.list = query.list;
  if (query.list === "toplist" && typeof query.tl === "number") {
    out.tl = String(query.tl);
  }
  if (query.next) out.next = query.next;
  return out;
}

function pathWithQuery(path: string, params: Record<string, string>): string {
  const search = new URLSearchParams(params).toString();
  return search ? `${path}?${search}` : path;
}

function galleryPath(gid: number, token: string, suffix = ""): string {
  return `/api/eh/galleries/${encodeURIComponent(String(gid))}/${encodeURIComponent(token)}${suffix}`;
}

export async function searchOnline(
  query: OnlineSearchQuery,
  signal?: AbortSignal,
): Promise<OnlineSearchResponse> {
  const data = await request<OnlineSearchResponse>(
    { method: ehSearchEp.method, path: pathWithQuery(ehSearchEp.path, buildSearchParams(query)) },
    { signal },
  );
  return {
    state: data?.state ?? "error",
    items: Array.isArray(data?.items) ? data.items : [],
    next: typeof data?.next === "string" && data.next ? data.next : null,
    q: data?.q,
    category: data?.category ?? null,
    min_rating: data?.min_rating ?? null,
    list: data?.list,
    tl: data?.tl ?? null,
  };
}

export async function fetchOnlineDetail(
  gid: number,
  token: string,
  signal?: AbortSignal,
): Promise<OnlineDetailResponse> {
  const data = await request<OnlineDetailResponse>(
    { method: ehGalleryEp.method, path: galleryPath(gid, token) },
    { signal },
  );
  return {
    state: data?.state ?? "error",
    gallery: data?.gallery ?? null,
  };
}

export async function fetchOnlinePages(
  gid: number,
  token: string,
  p = 0,
  signal?: AbortSignal,
): Promise<OnlinePreviewPage> {
  const params: Record<string, string> = p > 0 ? { p: String(p) } : {};
  const data = await request<OnlinePreviewPage>(
    { method: ehPagesEp.method, path: pathWithQuery(galleryPath(gid, token, "/pages"), params) },
    { signal },
  );
  return {
    state: data?.state ?? "error",
    p: typeof data?.p === "number" ? data.p : p,
    per_page: Number(data?.per_page) || (Array.isArray(data?.items) ? data.items.length : 0),
    total: typeof data?.total === "number" ? data.total : null,
    items: Array.isArray(data?.items)
      ? data.items.map((item) => ({
          index: Number(item?.index) || 0,
          thumb:
            item?.thumb && typeof item.thumb.url === "string"
              ? {
                  url: item.thumb.url,
                  x: Number(item.thumb.x) || 0,
                  y: Number(item.thumb.y) || 0,
                  w: Number(item.thumb.w) || 0,
                  h: Number(item.thumb.h) || 0,
                }
              : null,
        }))
      : [],
  };
}

export async function fetchOnlineStatus(
  gids: number[],
  signal?: AbortSignal,
): Promise<OnlineStatusItem[]> {
  const list = gids.filter((gid) => Number.isInteger(gid) && gid > 0).slice(0, 100);
  if (!list.length) return [];
  const data = await request<{ items?: OnlineStatusItem[] }>(
    {
      method: ehStatusEp.method,
      path: pathWithQuery(ehStatusEp.path, { gids: list.join(",") }),
    },
    { signal },
  );
  return Array.isArray(data?.items) ? data.items : [];
}

/** Official ExHentai gallery page; always opened in a new tab. */
export function officialGalleryUrl(gid: number, token: string): string {
  return `https://exhentai.org/g/${gid}/${token}/`;
}
