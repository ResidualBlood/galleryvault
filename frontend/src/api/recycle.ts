import { ep, request } from "./client";

export const trashGalleriesEp = ep("GET", "/api/galleries/trash");
export const expungedGalleriesEp = ep("GET", "/api/galleries/expunged");
export const restoreGalleriesEp = ep("POST", "/api/galleries/restore");
export const purgeGalleriesEp = ep("POST", "/api/galleries/purge");
export const redownloadExpungedEp = ep(
  "POST",
  "/api/galleries/expunged/redownload",
);

export interface RecycleTag {
  namespace: string | null;
  name: string;
  display?: string | null;
}

export interface TrashGallery {
  id: number;
  gid?: number | null;
  token?: string | null;
  title: string;
  title_jpn?: string | null;
  category?: string | null;
  page_count: number;
  cover_url?: string | null;
  trashed_at?: string | null;
  storage_path?: string | null;
  tags?: RecycleTag[];
  reading_progress?: number | null;
}

export interface ExpungedGallery {
  id: number;
  gid?: number | null;
  token?: string | null;
  title: string;
  page_count: number;
  cover_url?: string | null;
  updated_at?: string | null;
  storage_path?: string | null;
  tags?: RecycleTag[];
}

export interface RecyclePage<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface RestoreResult {
  restored: number;
}

export interface PurgeResult {
  purged: number;
  failed_deletions?: string[];
}

export interface ExpungedRedownloadResult {
  queued: number;
  skipped_no_gid?: number;
  skipped_no_token?: number;
}

function pagePath(base: string, page: number, pageSize: number): string {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return `${base}?${params.toString()}`;
}

export function fetchTrash(
  page = 1,
  pageSize = 24,
  signal?: AbortSignal,
): Promise<RecyclePage<TrashGallery>> {
  return request<RecyclePage<TrashGallery>>(
    { method: trashGalleriesEp.method, path: pagePath(trashGalleriesEp.path, page, pageSize) },
    { signal },
  );
}

export function fetchExpunged(
  page = 1,
  pageSize = 24,
  signal?: AbortSignal,
): Promise<RecyclePage<ExpungedGallery>> {
  return request<RecyclePage<ExpungedGallery>>(
    {
      method: expungedGalleriesEp.method,
      path: pagePath(expungedGalleriesEp.path, page, pageSize),
    },
    { signal },
  );
}

export function restoreGalleries(
  ids: number[],
  signal?: AbortSignal,
): Promise<RestoreResult> {
  return request<RestoreResult>(restoreGalleriesEp, { body: { ids }, signal });
}

export function purgeGalleries(
  ids: number[],
  deleteFiles: boolean,
  signal?: AbortSignal,
): Promise<PurgeResult> {
  return request<PurgeResult>(purgeGalleriesEp, {
    body: { ids, delete_files: deleteFiles },
    signal,
  });
}

export function redownloadExpunged(
  ids: number[],
  signal?: AbortSignal,
): Promise<ExpungedRedownloadResult> {
  return request<ExpungedRedownloadResult>(redownloadExpungedEp, {
    body: { ids },
    signal,
  });
}
