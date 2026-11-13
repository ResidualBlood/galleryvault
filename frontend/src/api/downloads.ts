import { ep, request } from "./client";

export const downloadsEp = ep("GET", "/api/downloads");
/** Remote cover fallback for download rows that are not in the library. */
export const favoriteCoverEp = ep("GET", "/api/favorites/cover");
export const createDownloadEp = ep("POST", "/api/downloads");
export const createDownloadBatchEp = ep("POST", "/api/downloads/batch");
export const cancelDownloadEp = ep("POST", "/api/downloads/{id}/cancel");
export const retryDownloadEp = ep("POST", "/api/downloads/{id}/retry");
export const deleteDownloadEp = ep("DELETE", "/api/downloads/{id}");
export const clearSuccessfulDownloadsEp = ep(
  "POST",
  "/api/downloads/clear-success",
);
export const retryAllDownloadsEp = ep("POST", "/api/downloads/retry-all");
export const quotaEp = ep("GET", "/api/quota");
export const pauseEp = ep("GET", "/api/pause");
export const setPauseEp = ep("POST", "/api/pause");

/* ------------------------------------------------------------ quick actions */

export type DownloadQuality = "original" | "resample";

export type DownloadStatus =
  | "pending"
  | "downloading"
  | "success"
  | "failed"
  | "cancelled";

export interface DownloadTask {
  id: number;
  gid: number;
  /** Local gallery primary key when this gid is already in the library. */
  gallery_id?: number | null;
  /** Local thumbnail when ingested, remote cover fallback otherwise. */
  cover_url?: string | null;
  title: string;
  status: string;
  retry_count?: number;
  max_retries?: number;
  current_page?: number;
  total_pages?: number | null;
  error_message?: string | null;
  mode?: string | null;
  quality?: string | null;
  archive_status?: string | null;
  archive_error?: string | null;
  archive_fallback?: boolean;
  speed?: number | null;
  eta_seconds?: number | null;
}

export interface DownloadBatchItem {
  gid: number;
  token: string;
  title?: string;
  quality?: DownloadQuality;
}

export interface DownloadBatchInput {
  items: DownloadBatchItem[];
  mode?: string;
  quality?: DownloadQuality;
  max_pages?: number;
}

export interface DownloadBatchResult {
  queued: number;
  skipped: number;
  gone: number;
  updated: number;
  failed: number;
  items: Array<{ gid?: number; status?: string }>;
}

export interface QuotaImageLimit {
  current: number;
  limit: number;
}

export interface QuotaInfo {
  gp: number | null;
  image_limit: QuotaImageLimit | null;
  image_limits: QuotaImageLimit | null;
  checked_at: string | null;
  error: string | null;
  cached: boolean;
}

export interface PauseState {
  paused: boolean;
}

export interface DownloadPage {
  total: number;
  page: number;
  page_size: number;
  items: DownloadTask[];
}

export interface CreateDownloadInput {
  gid: number;
  token: string;
  title?: string;
  quality?: DownloadQuality;
  mode?: string;
  max_pages?: number;
}

export interface CreateDownloadResult {
  id: number;
  gid: number;
  title: string;
  status: string;
}

export interface DownloadQuery {
  page?: number;
  page_size?: number;
  /** The backend supports one status value per request. */
  status?: "pending" | "downloading" | "success" | "failed" | "cancelled";
}

function queryPath(params: DownloadQuery): string {
  const search = new URLSearchParams();
  if (params.page) search.set("page", String(params.page));
  if (params.page_size) search.set("page_size", String(params.page_size));
  if (params.status) search.set("status", params.status);
  const suffix = search.toString();
  return suffix ? `${downloadsEp.path}?${suffix}` : downloadsEp.path;
}

export async function fetchDownloads(
  params: DownloadQuery = {},
  signal?: AbortSignal,
): Promise<DownloadPage> {
  const data = await request<DownloadPage>(
    { method: downloadsEp.method, path: queryPath(params) },
    { signal },
  );
  return {
    total: Number(data?.total) || 0,
    page: Number(data?.page) || params.page || 1,
    page_size: Number(data?.page_size) || params.page_size || 0,
    items: Array.isArray(data?.items) ? data.items : [],
  };
}

export async function createDownload(
  input: CreateDownloadInput,
  signal?: AbortSignal,
): Promise<CreateDownloadResult> {
  const body: Record<string, unknown> = { gid: input.gid, token: input.token };
  if (input.title) body.title = input.title;
  if (input.quality) body.quality = input.quality;
  if (input.mode) body.mode = input.mode;
  if (input.max_pages) body.max_pages = input.max_pages;
  const data = await request<CreateDownloadResult>(createDownloadEp, {
    body,
    signal,
  });
  return {
    id: Number(data?.id) || 0,
    gid: Number(data?.gid) || input.gid,
    title: typeof data?.title === "string" ? data.title : "",
    status: typeof data?.status === "string" ? data.status : "pending",
  };
}

export async function createDownloadsBatch(
  input: DownloadBatchInput,
  signal?: AbortSignal,
): Promise<DownloadBatchResult> {
  const body: Record<string, unknown> = {
    items: input.items.map((item) => {
      const next: Record<string, unknown> = {
        gid: Math.trunc(item.gid),
        token: item.token,
      };
      if (item.title) next.title = item.title;
      if (item.quality) next.quality = item.quality;
      return next;
    }),
  };
  if (input.mode) body.mode = input.mode;
  if (input.quality) body.quality = input.quality;
  if (input.max_pages) body.max_pages = input.max_pages;
  const data = await request<DownloadBatchResult>(createDownloadBatchEp, {
    body,
    signal,
  });
  return {
    queued: Number(data?.queued) || 0,
    skipped: Number(data?.skipped) || 0,
    gone: Number(data?.gone) || 0,
    updated: Number(data?.updated) || 0,
    failed: Number(data?.failed) || 0,
    items: Array.isArray(data?.items) ? data.items : [],
  };
}

function downloadTaskPath(template: string, id: number): string {
  return template.replace("{id}", String(id));
}

export async function cancelDownload(id: number, signal?: AbortSignal): Promise<void> {
  await request(
    { method: cancelDownloadEp.method, path: downloadTaskPath(cancelDownloadEp.path, id) },
    { signal },
  );
}

export async function retryDownload(id: number, signal?: AbortSignal): Promise<void> {
  await request(
    { method: retryDownloadEp.method, path: downloadTaskPath(retryDownloadEp.path, id) },
    { signal },
  );
}

export async function deleteDownloadTask(id: number, signal?: AbortSignal): Promise<void> {
  await request(
    { method: deleteDownloadEp.method, path: downloadTaskPath(deleteDownloadEp.path, id) },
    { signal },
  );
}

export async function clearSuccessfulDownloads(
  signal?: AbortSignal,
): Promise<number> {
  const data = await request<{ deleted?: number }>(clearSuccessfulDownloadsEp, {
    signal,
  });
  return Number(data?.deleted) || 0;
}

export async function retryAllDownloads(signal?: AbortSignal): Promise<number> {
  const data = await request<{ retried_count?: number; count?: number }>(
    retryAllDownloadsEp,
    { signal },
  );
  return Number(data?.retried_count ?? data?.count) || 0;
}

export async function fetchQuota(signal?: AbortSignal): Promise<QuotaInfo> {
  const data = await request<QuotaInfo>(quotaEp, { signal });
  const limit = data?.image_limit ?? data?.image_limits ?? null;
  return {
    gp: typeof data?.gp === "number" ? data.gp : null,
    image_limit:
      limit && Number.isFinite(limit.current) && Number.isFinite(limit.limit)
        ? { current: limit.current, limit: limit.limit }
        : null,
    image_limits: null,
    checked_at: typeof data?.checked_at === "string" ? data.checked_at : null,
    error: typeof data?.error === "string" ? data.error : null,
    cached: Boolean(data?.cached),
  };
}

export async function fetchPauseState(signal?: AbortSignal): Promise<boolean> {
  const data = await request<PauseState>(pauseEp, { signal });
  return Boolean(data?.paused);
}

export async function setPauseState(
  paused: boolean,
  signal?: AbortSignal,
): Promise<boolean> {
  const data = await request<PauseState>(setPauseEp, {
    body: { paused },
    signal,
  });
  return Boolean(data?.paused);
}
