/**
 * Online reader endpoints.
 *
 * Contract: PLAN-frontend-rewrite §3.3 / §3.4.
 *
 * - `resolve` turns one page index into a short-lived direct H@H image URL;
 *   the browser then fetches the bytes itself (no server image budget).
 * - `/image` is the optional per-device fallback through the server proxy.
 * - progress / history only persist the page counter and display metadata;
 *   resolved image URLs are never stored anywhere.
 */
import { ApiError, ep, request, type RequestOptions } from "./client";

export const onlineResolveEp = ep(
  "GET",
  "/api/eh/galleries/{gid}/{token}/pages/{n}/resolve",
);
export const onlineProgressEp = ep("GET", "/api/eh/galleries/{gid}/{token}/progress");
export const onlineSaveProgressEp = ep(
  "PUT",
  "/api/eh/galleries/{gid}/{token}/progress",
);
export const onlineHistoryEp = ep("GET", "/api/eh/history");
export const onlineQuotaEp = ep("GET", "/api/quota");

/** `retry` ladder used by the direct page source: 0 → 1 → 2. */
export const ONLINE_RESOLVE_MAX_RETRY = 2;

export interface ResolvedOnlinePage {
  state: string;
  /** 1-based page number as returned by the backend. */
  page: number;
  url: string;
  width: number;
  height: number;
  /** ISO timestamp; the reader re-resolves before using an expired URL. */
  expires_at: string | null;
}

export interface OnlineProgress {
  page: number;
  total_pages: number;
  updated_at?: string | null;
}

export interface OnlineProgressInput {
  page: number;
  total_pages?: number;
  title?: string | null;
  thumb?: string | null;
}

export interface OnlineHistoryItem {
  gid: number;
  token: string;
  title: string | null;
  thumb: string | null;
  page: number;
  total_pages: number | null;
  updated_at?: string | null;
}

export interface OnlineHistoryResponse {
  page: number;
  page_size: number;
  total: number;
  items: OnlineHistoryItem[];
}

export interface ImageLimit {
  current: number;
  limit: number;
}

export interface OnlineQuota {
  gp: number | null;
  image_limit: ImageLimit | null;
  checked_at: string | null;
  error: string | null;
}

export type OnlineResolveCode =
  | "page_out_of_range"
  | "image_limit"
  | "upstream"
  | "host_not_allowed"
  | "auth"
  | "challenge"
  | "banned"
  | "unknown";

/** `/api/eh/galleries/{gid}/{token}` with both params URL-encoded. */
export function onlineGalleryPath(gid: number, token: string, suffix = ""): string {
  return `/api/eh/galleries/${encodeURIComponent(String(gid))}/${encodeURIComponent(token)}${suffix}`;
}

/** 1-based server proxy URL for one reader page (fallback mode). */
export function onlineImagePath(gid: number, token: string, page: number): string {
  return onlineGalleryPath(gid, token, `/pages/${Math.max(1, Math.trunc(page))}/image`);
}

function numberOr(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Extract `detail.code` from a resolve failure (null when not a contract error). */
export function onlineResolveCode(error: unknown): OnlineResolveCode | null {
  if (!(error instanceof ApiError)) return null;
  const detail = error.detail;
  const code =
    detail && typeof detail === "object" && "code" in detail
      ? String((detail as { code?: unknown }).code ?? "")
      : "";
  switch (code) {
    case "page_out_of_range":
    case "image_limit":
    case "upstream":
    case "host_not_allowed":
    case "auth":
    case "challenge":
    case "banned":
      return code;
    default:
      return error.status === 429 ? "image_limit" : null;
  }
}

/**
 * Resolve one page to a direct image URL.
 *
 * `page` is 1-based (backend contract). `retry >= 1` asks the backend to
 * re-fetch the viewer with `nl=` so ExHentai picks another H@H node.
 */
export async function resolveOnlinePage(
  gid: number,
  token: string,
  page: number,
  retry = 0,
  options: RequestOptions = {},
): Promise<ResolvedOnlinePage> {
  const safeRetry = Math.min(
    ONLINE_RESOLVE_MAX_RETRY,
    Math.max(0, Math.trunc(retry)),
  );
  const path = onlineGalleryPath(gid, token, `/pages/${Math.max(1, Math.trunc(page))}/resolve`);
  const search = safeRetry > 0 ? `?retry=${safeRetry}` : "";
  const data = await request<ResolvedOnlinePage>(
    { method: onlineResolveEp.method, path: `${path}${search}` },
    options,
  );
  return {
    state: data?.state ?? "error",
    page: numberOr(data?.page, page),
    url: typeof data?.url === "string" ? data.url : "",
    width: Math.max(0, numberOr(data?.width, 0)),
    height: Math.max(0, numberOr(data?.height, 0)),
    expires_at:
      typeof data?.expires_at === "string" && data.expires_at ? data.expires_at : null,
  };
}

/** Stored progress, or null when the gallery has never been read online. */
export async function fetchOnlineProgress(
  gid: number,
  token: string,
  options: RequestOptions = {},
): Promise<OnlineProgress | null> {
  try {
    const data = await request<OnlineProgress>(
      { method: onlineProgressEp.method, path: onlineGalleryPath(gid, token, "/progress") },
      options,
    );
    return {
      page: Math.max(1, numberOr(data?.page, 1)),
      total_pages: Math.max(0, numberOr(data?.total_pages, 0)),
      updated_at: data?.updated_at ?? null,
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function saveOnlineProgress(
  gid: number,
  token: string,
  input: OnlineProgressInput,
  options: RequestOptions = {},
): Promise<OnlineProgress | null> {
  const body: Record<string, unknown> = { page: Math.max(1, Math.trunc(input.page)) };
  if (typeof input.total_pages === "number" && input.total_pages > 0) {
    body.total_pages = Math.trunc(input.total_pages);
  }
  if (input.title) body.title = input.title;
  if (input.thumb) body.thumb = input.thumb;
  const data = await request<OnlineProgress>(
    { method: onlineSaveProgressEp.method, path: onlineGalleryPath(gid, token, "/progress") },
    { ...options, body },
  );
  return data ?? null;
}

export async function fetchOnlineHistory(
  page = 1,
  pageSize = 20,
  options: RequestOptions = {},
): Promise<OnlineHistoryResponse> {
  const params = new URLSearchParams({
    page: String(Math.max(1, Math.trunc(page))),
    page_size: String(Math.min(100, Math.max(1, Math.trunc(pageSize)))),
  });
  const data = await request<OnlineHistoryResponse>(
    { method: onlineHistoryEp.method, path: `${onlineHistoryEp.path}?${params.toString()}` },
    options,
  );
  return {
    page: numberOr(data?.page, page),
    page_size: numberOr(data?.page_size, pageSize),
    total: numberOr(data?.total, 0),
    items: Array.isArray(data?.items) ? data.items : [],
  };
}

export async function fetchOnlineQuota(
  options: RequestOptions = {},
): Promise<OnlineQuota> {
  const data = await request<{
    gp?: number | null;
    image_limit?: ImageLimit | null;
    image_limits?: ImageLimit | null;
    checked_at?: string | null;
    error?: string | null;
  }>({ method: onlineQuotaEp.method, path: onlineQuotaEp.path }, options);
  const limit = data?.image_limit ?? data?.image_limits ?? null;
  return {
    gp: typeof data?.gp === "number" ? data.gp : null,
    image_limit:
      limit && typeof limit.current === "number" && typeof limit.limit === "number"
        ? { current: limit.current, limit: limit.limit }
        : null,
    checked_at: data?.checked_at ?? null,
    error: data?.error ?? null,
  };
}
