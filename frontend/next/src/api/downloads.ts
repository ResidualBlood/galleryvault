import { ep, request } from "./client";

export const downloadsEp = ep("GET", "/api/downloads");
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

export interface DownloadTask {
  id: number;
  gid: number;
  title: string;
  status: string;
  retry_count?: number;
  max_retries?: number;
  current_page?: number;
  total_pages?: number | null;
  error_message?: string | null;
  mode?: string | null;
  quality?: string | null;
  speed?: number | null;
  eta_seconds?: number | null;
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
