import { ep, request } from "./client";

/* ------------------------------------------------------------- updates list */

export const updatesEp = ep("GET", "/api/updates");
export const updatesIgnoredEp = ep("GET", "/api/updates/ignored");
export const updatesStatusEp = ep("GET", "/api/updates/status");
export const updatesScanEp = ep("POST", "/api/updates/scan");
export const updatesUpdateEp = ep("POST", "/api/updates/update");
export const updatesIgnoreEp = ep("POST", "/api/updates/ignore");
export const updatesUnignoreEp = ep("POST", "/api/updates/unignore");
export const updatesDeleteEp = ep("POST", "/api/updates/delete");

export type UpdateState =
  | "active"
  | "all"
  | "pending"
  | "downloading"
  | "failed"
  | "ignored";

export type UpdateStatus = "pending" | "downloading" | "failed" | "ignored" | string;

export interface GalleryUpdate {
  id: number;
  gallery_id: number;
  old_gid: number;
  new_gid: number;
  title: string;
  favcat: number;
  favcat_name?: string;
  status: UpdateStatus;
  error_message?: string | null;
  detected_at?: string | null;
  updated_at?: string | null;
  cover_url?: string | null;
}

export interface UpdatesPage {
  total: number;
  page: number;
  page_size: number;
  state: UpdateState;
  items: GalleryUpdate[];
}

export interface UpdatesStatusCounts {
  pending?: number;
  downloading?: number;
  failed?: number;
  ignored?: number;
}

export interface UpdatesStatus {
  detecting: boolean;
  last_detected_at?: string | null;
  last_run?: string | null;
  last_error?: string | null;
  last_found?: number;
  counts: UpdatesStatusCounts;
}

export interface UpdateRunOptions {
  archive?: boolean;
  quality?: "original" | "resample";
}

export interface UpdateRunResult {
  started?: number;
  skipped?: number;
}

function queryString(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export function fetchUpdates(
  query: { page?: number; page_size?: number; state?: UpdateState },
  signal?: AbortSignal,
): Promise<UpdatesPage> {
  const suffix = queryString(query);
  return request<UpdatesPage>(
    { method: updatesEp.method, path: `${updatesEp.path}?${suffix}` },
    { signal },
  );
}

/** Legacy loads the ignored page unpaginated (500 is the backend cap). */
export function fetchIgnoredUpdates(signal?: AbortSignal): Promise<UpdatesPage> {
  return request<UpdatesPage>(
    {
      method: updatesIgnoredEp.method,
      path: `${updatesIgnoredEp.path}?${queryString({ page: 1, page_size: 500 })}`,
    },
    { signal },
  );
}

export function fetchUpdatesStatus(signal?: AbortSignal): Promise<UpdatesStatus> {
  return request<UpdatesStatus>(updatesStatusEp, { signal });
}

export function scanUpdates(signal?: AbortSignal): Promise<{ status: string }> {
  return request<{ status: string }>(updatesScanEp, { signal });
}

export function runUpdates(
  ids: number[],
  options: UpdateRunOptions = {},
  signal?: AbortSignal,
): Promise<UpdateRunResult> {
  return request<UpdateRunResult>(updatesUpdateEp, {
    body: { ids, ...options },
    signal,
  });
}

export function ignoreUpdates(ids: number[], signal?: AbortSignal): Promise<unknown> {
  return request(updatesIgnoreEp, { body: { ids }, signal });
}

export function unignoreUpdates(ids: number[], signal?: AbortSignal): Promise<unknown> {
  return request(updatesUnignoreEp, { body: { ids }, signal });
}

export function deleteUpdates(ids: number[], signal?: AbortSignal): Promise<unknown> {
  return request(updatesDeleteEp, { body: { ids }, signal });
}
