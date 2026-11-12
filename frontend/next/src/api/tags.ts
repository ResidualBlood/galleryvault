import { request } from "./client";
import { syncGalleryTagsEp } from "./galleries";
import {
  reloadTagsEp,
  startTagSyncEp,
  tagsSearchEp,
  type TagSearchPage,
} from "./library";

export interface TagsQuery {
  q?: string;
  namespace?: string;
  page?: number;
  page_size?: number;
}

export interface TagReloadResult {
  accepted: boolean;
  ok: boolean;
  last_error?: string | null;
}

export interface TagSyncStartResult {
  status?: string;
  queued?: number;
  detail?: string;
}

export interface GalleryTagSyncResult {
  source?: "cache" | "network" | string;
  count?: number;
}

const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff]/u;

export function isCjkQuery(q: string): boolean {
  return CJK_RE.test(q);
}

/**
 * Tag cloud search. Mirrors the legacy page: CJK queries always use page 1
 * with `zh=1` (the translation index returns a single page), and the namespace
 * filter is dropped for those queries.
 */
export function fetchTags(
  query: TagsQuery = {},
  signal?: AbortSignal,
): Promise<TagSearchPage> {
  const q = (query.q ?? "").trim();
  const cjk = isCjkQuery(q);
  const params = new URLSearchParams();
  params.set("page", String(cjk ? 1 : Math.max(1, query.page ?? 1)));
  params.set("page_size", "100");
  if (!cjk && query.namespace) params.set("namespace", query.namespace);
  if (q) params.set("q", q);
  if (cjk && q) params.set("zh", "1");
  return request<TagSearchPage>(
    { method: tagsSearchEp.method, path: `${tagsSearchEp.path}?${params}` },
    { signal },
  );
}

export function reloadTags(signal?: AbortSignal): Promise<TagReloadResult> {
  return request<TagReloadResult>(reloadTagsEp, { signal });
}

export function startTagSync(signal?: AbortSignal): Promise<TagSyncStartResult> {
  return request<TagSyncStartResult>(startTagSyncEp, { signal });
}

export function syncGalleryTags(
  galleryId: number,
  signal?: AbortSignal,
): Promise<GalleryTagSyncResult> {
  return request<GalleryTagSyncResult>(
    { method: syncGalleryTagsEp.method, path: syncGalleryTagsEp.path.replace("{id}", String(galleryId)) },
    { signal },
  );
}
